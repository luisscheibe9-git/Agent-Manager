"""Dashboard API, preferences, reminders and read-only repository context."""
import json
import os
from pathlib import Path
import re
import subprocess
import time

import inbox
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
    rows = []
    for source, sid, title, cwd, mt, last, role in items:
        state = inbox.item_state(sid, mt, role, sid in pins)
        hook = inbox.HOOKS.get(sid)
        version = max(mt, hook["timestamp"]) if hook else mt
        is_read = read.get(sid, 0) >= version
        if state == "done":
            state = "read" if is_read else "unread"
        if state in ("settled", "idle"):
            is_read = True
        if hook and hook["state"] == "needs":
            state = "needs"
        extra = inbox.DETAILS.get(sid, records.get(sid, {}).get("extra", {}))
        folder = (cwd or "").rstrip("/\\")
        project = re.split(r"[/\\]", folder)[-1] if folder else "No project"
        rows.append({"id": sid, "source": source, "title": title, "cwd": cwd or "",
                     "project": project, "project_key": os.path.normcase(folder) or "__none__",
                     "updated_at": mt, "activity": version, "last": last or "",
                     "state": state, "read": is_read, "pinned": sid in pins,
                     "archived": sid in archived, "href": inbox.HREFS.get(sid, ""),
                     "branch": extra.get("branch", ""), "details": extra})
    rows.sort(key=lambda r: (not r["pinned"], -r["updated_at"]))
    active = [r for r in rows if not r["archived"]]
    return {"chats": rows, "counts": {"total": len(active),
            "needs": sum(r["state"] == "needs" for r in active),
            "working": sum(r["state"] == "working" for r in active),
            "unread": sum(r["state"] == "unread" for r in active)},
            "settings": prefs, "updated_at": time.time(), "version": 2,
            "title": os.environ.get("AGENT_MANAGER_LABEL", "Agent Manager")}


@inbox.locked
def action(name, body):
    if name == "settings":
        return update_settings(body)
    if name == "hook":
        return hook(body)
    rows = snapshot()["chats"]
    by_id = {r["id"]: r for r in rows}
    sid = body.get("id")
    if name == "mark-all":
        marks = inbox.load_state()
        for row in rows:
            if not row["archived"] and row["state"] not in ("working", "needs"):
                marks[row["id"]] = row["activity"]
        inbox.save_state(marks)
        return {"ok": True}
    if sid not in by_id:
        raise ValueError("Chat no longer exists")
    row = by_id[sid]
    if name == "read":
        marks = inbox.load_state()
        if body.get("read", True):
            marks[sid] = row["activity"]
        else:
            marks.pop(sid, None)
        inbox.save_state(marks)
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
            if row["archived"] or row["state"] not in ("needs", "unread"):
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
