"""Read-only, provider-qualified session membership from local T3 Code metadata.

Only explicit native IDs and imported transcript records are matched. Never use
titles, project paths, T3 internal IDs, auth/session cookies or message text.
"""
import json
import os
from pathlib import Path
import sqlite3
import time
from contextlib import closing


def provider(value):
    key = ''.join(c for c in str(value or '').lower() if c.isalnum())
    return {"codex": "Codex", "claude": "Claude", "claudecode": "Claude",
            "claudeagentsdk": "Claude"}.get(key)


def object_json(value):
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def unresolved_threads(db, tables):
    """Threads T3 Code itself shows as unsettled: live, not archived, not settled, not snoozed."""
    if 'orchestration_v2_projection_threads' not in tables:
        return []
    now = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())
    found = []
    try:
        for thread_id, raw in db.execute('SELECT thread_id,payload_json FROM orchestration_v2_projection_threads'):
            p = object_json(raw)
            if p.get('deletedAt') or p.get('archivedAt'):
                continue
            override, settled, unsettled = p.get('settledOverride'), p.get('settledAt'), p.get('unsettledAt')
            if override == 'settled':
                continue
            if override != 'unsettled' and settled and not (unsettled and unsettled > settled):
                continue
            if (p.get('snoozedUntil') or '') > now:
                continue
            found.append({"id": thread_id, "title": str(p.get('title') or '(untitled)')[:120],
                          "updated_at": str(p.get('updatedAt') or '')})
    except sqlite3.Error:
        return []
    return sorted(found, key=lambda t: t["updated_at"], reverse=True)


def scan(home):
    override = os.environ.get('AGENT_MANAGER_T3_DB')
    root = Path(home) / '.t3/userdata'
    path = Path(override) if override else root / 'statev2.sqlite'
    if not override and not path.exists():
        path = root / 'state.sqlite'
    result = {"status": "not_found", "sessions": {}, "reason": ""}
    if not path.is_file():
        return result
    deadline = time.monotonic() + .3
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=.15)) as db:
            db.execute('PRAGMA query_only=ON')
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            db.execute('BEGIN')  # One consistent snapshot, including current WAL contents.
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            owners = {}
            # V2 supersedes legacy deletion state for the same T3 thread.
            for table in ('projection_threads', 'orchestration_v2_projection_threads'):
                if table in tables:
                    for thread_id, deleted in db.execute('SELECT thread_id,deleted_at FROM '+table):
                        owners[thread_id] = deleted is None
            if not owners and not tables.intersection({'projection_threads','orchestration_v2_projection_threads'}):
                return {**result, "status": "unavailable", "reason": "unsupported_schema"}
            sessions = {}
            def add(source, native_id, owner):
                source = provider(source)
                if source and owners.get(owner) and isinstance(native_id, str) and 0 < len(native_id) <= 200 and not any(c.isspace() for c in native_id):
                    sessions[(source, native_id)] = owner
            table = 'orchestration_v2_projection_provider_threads'
            if table in tables:
                for owner, source, raw in db.execute('SELECT thread_id,provider,payload_json FROM '+table):
                    ref = object_json(raw).get('nativeThreadRef')
                    if isinstance(ref, dict):
                        add(ref.get('driver') or source, ref.get('nativeId'), owner)
            if 'projection_thread_sessions' in tables:
                for owner, source, native_id in db.execute('SELECT thread_id,provider_name,provider_thread_id FROM projection_thread_sessions'):
                    add(source, native_id, owner)
            if 'provider_session_runtime' in tables:
                for owner, source, cursor, raw in db.execute('SELECT thread_id,provider_name,resume_cursor_json,runtime_payload_json FROM provider_session_runtime'):
                    cursor = object_json(cursor)
                    if provider(source) == 'Codex':
                        add(source, cursor.get('threadId'), owner)
                    elif provider(source) == 'Claude':
                        add(source, cursor.get('sessionId'), owner)
                    imports = object_json(raw).get('importedTranscripts', [])
                    for item in imports if isinstance(imports, list) else []:
                        if isinstance(item, dict):
                            add(item.get('provider'), item.get('providerSessionId'), owner)
            return {"status": "ready", "sessions": sessions, "reason": "", "unresolved": unresolved_threads(db, tables)}
    except (sqlite3.Error, OSError, ValueError):
        # Fail open: never hide unrelated chats because T3 is locked or changed.
        return {**result, "status": "unavailable", "reason": "read_failed"}
