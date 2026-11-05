"""Dashboard API, preferences, reminders and read-only repository context."""
import json
import os
from pathlib import Path
import re
import subprocess
import time
import hashlib
import queue
import threading

import inbox
import t3_sessions
from catalog import Catalog

DEFAULTS = {"reminders_enabled": True, "reminder_delay_seconds": 180,
            "keep_taskbar": True, "settle_days": 7, "group_by_project": True}


def settings():
    with Catalog(inbox.CATALOG) as db:
        return {**DEFAULTS, **db.get("preferences", {})}


def update_settings(values):
    current = settings()
    for key, value in values.items():
        if key not in DEFAULTS:
            raise ValueError("Unknown setting")
        if isinstance(DEFAULTS[key], bool):
            if not isinstance(value, bool):
                raise ValueError("Expected true or false")
        elif not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("Expected a whole number")
        if key == "reminder_delay_seconds" and not 60 <= value <= 86400:
            raise ValueError("Reminder delay must be between 1 minute and 1 day")
        if key == "settle_days" and not 1 <= value <= 365:
            raise ValueError("Settled age must be between 1 and 365 days")
        current[key] = value
    with Catalog(inbox.CATALOG) as db:
        db.set("preferences", current)
    return current


def counts(rows):
    active = [r for r in rows if not r["archived"] and not r["managed_by_t3"]]
    todo = [r for r in active if not r["read"]]
    return {"total": len(active), "todo": len(todo),
            "t3": sum(r["managed_by_t3"] and not r["archived"] for r in rows),
            "needs": sum(r["state"] == "needs" for r in todo),
            "working": sum(r["state"] == "working" for r in todo),
            "unread": sum(r["state"] == "unread" for r in todo)}


_CACHE = {"data": None}
_WAKE = threading.Event()
_ACTION_LOCK = threading.Lock()
_STARTED = []
_GEN = [0]


def _refresher():
    while True:
        try:
            gen = _GEN[0]
            fresh = snapshot()
            if gen == _GEN[0]:  # an action landed mid-scan; this scan may predate it
                _CACHE["data"] = fresh
            else:
                _WAKE.set()
        except Exception as exc:
            inbox.log("refresh error: " + repr(exc))
        _WAKE.wait(2)
        _WAKE.clear()


def start_refresher():
    """Called by the server; tests and one-shot tools skip it and scan on demand."""
    if not _STARTED:
        _STARTED.append(1)
        _CACHE["data"] = snapshot()
        threading.Thread(target=_refresher, daemon=True).start()
        threading.Thread(target=_writer, daemon=True).start()


def cached_snapshot():
    """Last scan, refreshed in the background so requests never wait on the log scan."""
    if not _STARTED or _CACHE["data"] is None:
        return snapshot()
    return _CACHE["data"]


def _patch(sid, **fields):
    data = _CACHE["data"]
    if not data:
        return
    for row in data["chats"]:
        if row["id"] == sid:
            row.update(fields)
    data["chats"].sort(key=lambda r: (not r["pinned"], -r["updated_at"]))
    data["counts"] = counts(data["chats"])


@inbox.locked
def snapshot():
    drain_hooks()
    prefs = settings()
    inbox.SETTLE_DAYS = prefs["settle_days"]
    items = inbox.collect_sessions()
    if inbox.read_json(inbox.STATE, None) is None:
        inbox.save_state({r[1]: max(r[4], inbox.HOOKS.get(r[1], {}).get("timestamp", 0)) for r in items})
    read = inbox.merged_state()
    pins = inbox.load_pins()
    with Catalog(inbox.CATALOG) as db:
        archived = set(db.get("archived", []))
        records = {r["item"][1]: r for r in db.records()}
        decisions = db.get("todo_decisions", {})
    t3 = t3_sessions.scan(inbox.HOME)
    rows = []
    for source, sid, title, cwd, mt, last, role in items:
        title = inbox.app_title(title, None) or inbox.clean_title(title)  # retained rows can hold old placeholder titles
        state = inbox.item_state(sid, mt, role, sid in pins)
        hook = inbox.HOOKS.get(sid)
        version = max(mt, hook["timestamp"]) if hook else mt
        is_read = read.get(sid, 0) >= version
        if hook and hook["state"] == "needs":
            state = "needs"
        extra = inbox.DETAILS.get(sid, records.get(sid, {}).get("extra", {}))
        # Routine token/tool progress must not resurrect a cleared task. A final
        # answer, new turn, or new pending request changes this attention token.
        attention = hashlib.sha256(json.dumps([state,
                    last if state not in ("working", "needs") else None,
                    extra.get("attention_sequence", 0),
                    hook["timestamp"] if hook and hook["state"] == "needs" else None],
                    sort_keys=True).encode()).hexdigest()
        decision = decisions.get(sid, {})
        if decision.get("attention") == attention:
            is_read = decision.get("done", False)
        if state == "done" or state == "settled" and not is_read:
            state = "read" if is_read else "unread"
        folder = (cwd or "").rstrip("/\\")
        project = re.split(r"[/\\]", folder)[-1] if folder else "No project"
        rows.append({"id": sid, "source": source, "title": title, "cwd": cwd or "",
                     "project": project, "project_key": os.path.normcase(folder) or "__none__",
                     "updated_at": mt, "activity": version, "last": last or "",
                     "state": state, "read": is_read, "pinned": sid in pins,
                     "done_at": decision.get("done_at", 0) if is_read else 0,
                     "archived": sid in archived, "href": inbox.HREFS.get(sid, ""),
                     "branch": extra.get("branch", ""), "details": extra,
                     "attention": attention, "managed_by_t3": (source, sid) in t3["sessions"]})
    rows.sort(key=lambda r: (not r["pinned"], -r["updated_at"]))
    return {"chats": rows, "counts": counts(rows),
            "t3": {"status": t3["status"], "reason": t3["reason"]},
            "settings": prefs, "updated_at": time.time(), "version": 2,
            "title": os.environ.get("AGENT_MANAGER_LABEL", "Agent Manager")}


def action(name, body):
    if name == "resume":
        return resume(body.get("id"))
    if name in ("settings", "hook"):
        with inbox.DATA_LOCK:
            return update_settings(body) if name == "settings" else hook(body)
    return _action(name, body)


_QUEUE = queue.Queue()


def _writer():
    while True:
        job = _QUEUE.get()
        try:
            with _ACTION_LOCK:
                _apply(*job)
        except Exception as exc:
            inbox.log("action error: " + repr(exc))
        finally:
            _QUEUE.task_done()
        _GEN[0] += 1
        _WAKE.set()


def flush():
    """Wait for queued clicks to reach disk (called before the app exits)."""
    _QUEUE.join()


def resume(sid):
    """Open a terminal running `claude --resume` for a Claude chat that has no app deep link."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", str(sid)):
        raise ValueError("Invalid chat id")
    row = next((r for r in cached_snapshot()["chats"] if r["id"] == sid), None)
    if row is None or row["source"] != "Claude":
        raise ValueError("Only Claude chats can be resumed in a terminal")
    cwd = row["cwd"] if os.path.isdir(row["cwd"] or "") else inbox.HOME
    subprocess.Popen(["powershell", "-NoExit", "-Command", f"claude --resume {sid}"],
                     cwd=cwd, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return {"ok": True}


def _preview(name, body, rows, sid):
    """Validate and show the change in the cached list at once."""
    if name == "mark-all":
        for row in rows:
            if not row["archived"] and not row["managed_by_t3"] and not row["read"]:
                _patch(row["id"], read=True, done_at=time.time())
    elif name == "read":
        if not isinstance(body.get("read", True), bool):
            raise ValueError("Expected read true or false")
        _patch(sid, read=body.get("read", True), done_at=time.time() if body.get("read", True) else 0)
    elif name == "pin":
        if not isinstance(body.get("pinned"), bool):
            raise ValueError("Expected pinned true or false")
        _patch(sid, pinned=body["pinned"])
    elif name == "archive":
        if not isinstance(body.get("archived"), bool):
            raise ValueError("Expected archived true or false")
        _patch(sid, archived=body["archived"])
    else:
        raise ValueError("Unknown action")


def _action(name, body):
    rows = cached_snapshot()["chats"]
    by_id = {r["id"]: r for r in rows}
    sid = body.get("id")
    if name != "mark-all" and sid not in by_id:
        rows = snapshot()["chats"]
        by_id = {r["id"]: r for r in rows}
        if sid not in by_id:
            raise ValueError("Chat no longer exists")
    job = (name, body, [dict(r) for r in rows], by_id, sid)
    if not _STARTED:  # tests and one-shot tools: save before returning
        with _ACTION_LOCK:
            return _apply(*job)
    _GEN[0] += 1
    _preview(name, body, rows, sid)
    _QUEUE.put(job)
    return {"ok": True}


def _apply(name, body, rows, by_id, sid):
    now = time.time()
    if name == "mark-all":
        marks = inbox.load_state()
        with Catalog(inbox.CATALOG) as db:
            decisions = db.get("todo_decisions", {})
            for row in rows:
                if not row["archived"] and not row["managed_by_t3"]:
                    marks[row["id"]] = row["activity"]
                    if not row["read"]:  # already-done chats keep their original done time
                        decisions[row["id"]] = {"attention": row["attention"], "done": True, "done_at": now}
            db.set("todo_decisions", decisions)
        inbox.save_state(marks)
        return {"ok": True}
    if sid not in by_id:
        raise ValueError("Chat no longer exists")
    row = by_id[sid]
    if name == "read":
        done = body.get("read", True)
        if not isinstance(done, bool):
            raise ValueError("Expected read true or false")
        marks = inbox.load_state()
        if done:
            marks[sid] = row["activity"]
        else:
            marks.pop(sid, None)
        inbox.save_state(marks)
        with Catalog(inbox.CATALOG) as db:
            decisions = db.get("todo_decisions", {})
            decisions[sid] = {"attention": row["attention"], "done": done, "done_at": now if done else 0}
            db.set("todo_decisions", decisions)
    elif name == "pin":
        if not isinstance(body.get("pinned"), bool):
            raise ValueError("Expected pinned true or false")
        pins = inbox.load_pins()
        if body["pinned"]:
            pins[sid] = True
        else:
            pins.pop(sid, None)
        inbox.write_json(inbox.PINS, pins)
    elif name == "archive":
        if not isinstance(body.get("archived"), bool):
            raise ValueError("Expected archived true or false")
        with Catalog(inbox.CATALOG) as db:
            archived = set(db.get("archived", []))
            (archived.add if body["archived"] else archived.discard)(sid)
            db.set("archived", sorted(archived))
    else:
        raise ValueError("Unknown action")
    return {"ok": True}


def hook(body):
    sid = body.get("session_id", "")
    event = body.get("hook_event_name", "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,150}", sid):
        raise ValueError("Invalid session ID")
    working = {"UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "ElicitationResult"}
    if event in working:
        state = "needs" if event == "PreToolUse" and body.get("tool_name") in ("AskUserQuestion", "ExitPlanMode") else "working"
    elif event in ("PermissionRequest", "Elicitation"):
        state = "needs"
    elif event == "Notification":
        if body.get("notification_type") not in ("permission_prompt", "idle_prompt", "elicitation_dialog"):
            return {"ok": True, "ignored": True}
        state = "needs"
    elif event in ("Stop", "StopFailure", "SessionEnd"):
        state = "done"
    else:
        raise ValueError("Unsupported hook event")
    # Timestamp is captured when received; callers cannot forge future status leases.
    now = time.time()
    observed = body.get("observed_at", now)
    if not isinstance(observed, (int, float)) or not 0 < observed <= now + 5:
        raise ValueError("Invalid event timestamp")
    now = min(now, observed)
    with Catalog(inbox.CATALOG) as db:
        db.hook(sid, now, {"state": state, "source": "Claude", "event": event})
    return {"ok": True}


def drain_hooks():
    folder = Path(inbox.DATA_DIR) / "hook_queue"
    for path in list(folder.glob("*.json"))[:500]:
        try:
            data = json.loads(path.read_text(encoding="utf8"))
            hook(data)
            path.unlink()
        except (ValueError, OSError, TypeError):
            # Ignore malformed input without losing unrelated queued events.
            continue


@inbox.locked
def notify_due(notify, now=None):
    data = snapshot()
    now = time.time() if now is None else now
    prefs = data["settings"]
    if not prefs["reminders_enabled"]:
        return []
    due = []
    with Catalog(inbox.CATALOG) as db:
        relevant = []
        for row in data["chats"]:
            sid = row["id"]
            if row["archived"] or row["read"] or row["managed_by_t3"] or row["state"] not in ("needs", "unread"):
                db.db.execute("DELETE FROM reminders WHERE id=?", (sid,))
                continue
            relevant.append(sid)
            old = db.db.execute("SELECT activity, first_seen, notified FROM reminders WHERE id=?", (sid,)).fetchone()
            if old is None or old[0] != row["activity"]:
                db.db.execute("INSERT OR REPLACE INTO reminders VALUES (?, ?, ?, 0)", (sid, row["activity"], now))
            elif not old[2] and now - old[1] >= prefs["reminder_delay_seconds"]:
                due.append(row)
        if due:
            notify("\n".join(r["title"][:80] for r in due[:3]) +
                   (f"\n+{len(due)-3} more" if len(due) > 3 else ""),
                   f"Agent Manager · {len(due)} chat{'s' if len(due) != 1 else ''} still need attention")
            for row in due:
                db.db.execute("UPDATE reminders SET notified=1 WHERE id=?", (row["id"],))
    return [r["id"] for r in due]


def repository_context(sid):
    row = next((r for r in snapshot()["chats"] if r["id"] == sid), None)
    if row is None:
        raise ValueError("Chat no longer exists")
    result = {"branch": row["branch"], "files": [], "pull_request": None, "available": False}
    if not row["cwd"] or not Path(row["cwd"]).is_dir():
        return result
    def run(args, timeout=3):
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        return subprocess.run(args, cwd=row["cwd"], capture_output=True, text=True,
                              encoding="utf8", errors="replace", timeout=timeout, **flags)
    git = ["git", "-c", "core.fsmonitor=false"]
    try:
        branch = run(git + ["branch", "--show-current"])
        if branch.returncode:
            return result
        result.update(available=True, branch=branch.stdout.strip() or row["branch"])
        diff = run(git + ["diff", "--no-ext-diff", "--numstat", "HEAD"])
        for line in diff.stdout.splitlines()[:100]:
            fields = line.split("\t", 2)
            if len(fields) == 3:
                result["files"].append({"path": fields[2], "added": fields[0], "removed": fields[1]})
        untracked = run(git + ["ls-files", "--others", "--exclude-standard"])
        result["files"].extend({"path": p, "added": "new", "removed": ""} for p in untracked.stdout.splitlines()[:100])
        pr = run(["gh", "pr", "view", "--json", "url,title,state"], timeout=8)
        if pr.returncode == 0:
            result["pull_request"] = json.loads(pr.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return result
