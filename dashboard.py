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

T3_PATH = re.compile(r"[\\/]\.t3[\\/]")  # chats started inside T3 Code (scratch/worktree folders)
DEFAULTS = {"reminders_enabled": True, "reminder_delay_seconds": 180,
            "keep_taskbar": True, "settle_days": 7, "group_by_project": True,
            "five_hour_limit_tokens": 0}


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
        if key == "five_hour_limit_tokens" and not 0 <= value <= 10**10:
            raise ValueError("Five-hour limit must be 0 (automatic) or a token count")
        if key == "settle_days" and not 1 <= value <= 365:
            raise ValueError("Settled age must be between 1 and 365 days")
        current[key] = value
    with Catalog(inbox.CATALOG) as db:
        db.set("preferences", current)
    return current


def counts(rows):
    active = [r for r in rows if not r["archived"] and not r["managed_by_t3"] and not r["automated"]]
    todo = [r for r in active if not r["read"] and r.get("snoozed_until", 0) <= time.time()]
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
    data["chats"].sort(key=lambda r: (not r["pinned"], r["order"], -r["updated_at"]))
    data["counts"] = counts(data["chats"])


WEB = Path(__file__).resolve().parent / "web"


def web_build():
    """Changes whenever the page files change, so an open window can reload itself."""
    try:
        return max(f.stat().st_mtime_ns for f in WEB.iterdir())
    except OSError:
        return 0


def five_hour_limit(rows, override=0):
    """Estimated 5-hour budget as (units, basis).

    Claude: spend in the 5-hour window before each "You've hit your session limit" message is the limit itself;
    the median over recent hits is used. Otherwise the busiest 5 hours seen in the last 14 days. Units are
    cost-weighted tokens (see telemetry.claude_weight)."""
    if override:
        return override, "your setting"
    merged, hits = {}, {}
    for r in rows:
        for key, tokens in (r["details"].get("usage_buckets") or {}).items():
            merged[int(key)] = merged.get(int(key), 0) + tokens
        for hit in r["details"].get("limit_hits") or []:
            hits[round(hit["reset"] / 600)] = hit
    spends = sorted(sum(v for k, v in merged.items() if hit["reset"] - 5 * 3600 <= k <= hit["at"])
                    for hit in hits.values())
    spends = [x for x in spends if x > 0]
    if spends:
        return max(spends[len(spends) // 2], 1_000_000), f"{len(spends)} times you hit the limit"
    best = total = left = 0
    times = sorted(merged)
    for right, stamp in enumerate(times):
        total += merged[stamp]
        while times[left] <= stamp - 5 * 3600:
            total -= merged[times[left]]
            left += 1
        best = max(best, total)
    return max(best, 1_000_000), "your busiest 5 hours"


def context_window(details):
    """Context size in tokens: reported by Codex; estimated for Claude (200K, or 1M once a chat exceeds it)."""
    if details.get("context_window"):
        return details["context_window"]
    used = details.get("context_tokens") or 0
    if "1m" in (details.get("model") or "").lower() or used > 200_000:
        return 1_000_000
    return 200_000


HUES = list(range(0, 360, 15))


def _gap(a, b):
    return min(abs(a - b), 360 - abs(a - b))


def project_hues(keys):
    """One saved hue per project: same project, same color, kept across restarts.

    New projects (given most recent first) get the unused hue farthest from the hues already in use, so the
    projects you are working in look clearly different."""
    with Catalog(inbox.CATALOG) as db:
        saved = db.get("project_colors", {})
        missing = [k for k in dict.fromkeys(keys) if k not in saved]
        for key in missing:
            counts_by_hue = {}
            for hue in saved.values():
                counts_by_hue[hue] = counts_by_hue.get(hue, 0) + 1
            free = [h for h in HUES if h not in counts_by_hue]
            if not free:
                saved[key] = min(HUES, key=lambda h: counts_by_hue[h])
            elif not counts_by_hue:
                saved[key] = HUES[sum(map(ord, key)) % len(HUES)]
            else:
                saved[key] = max(free, key=lambda h: min(_gap(h, u) for u in counts_by_hue))
        if missing:
            db.set("project_colors", saved)
    return saved


def freeze_focus_reads():
    """One-time: keep chats that only counted as read because you focused them in the Claude app."""
    with Catalog(inbox.CATALOG) as db:
        if db.get("focus_reads_frozen"):
            return
        stored = inbox.load_state()
        changed = {sid: t for sid, t in inbox.merged_state().items() if t > stored.get(sid, 0)}
        if changed:
            stored.update(changed)
            inbox.save_state(stored)
        db.set("focus_reads_frozen", True)


@inbox.locked
def snapshot():
    drain_hooks()
    prefs = settings()
    inbox.SETTLE_DAYS = prefs["settle_days"]
    items = inbox.collect_sessions()
    if inbox.read_json(inbox.STATE, None) is None:
        inbox.save_state({r[1]: max(r[4], inbox.HOOKS.get(r[1], {}).get("timestamp", 0)) for r in items})
    freeze_focus_reads()
    read = inbox.load_state()  # only Done resolves a chat; opening or focusing it does not
    pins = inbox.load_pins()
    with Catalog(inbox.CATALOG) as db:
        archived = set(db.get("archived", []))
        records = {r["item"][1]: r for r in db.records()}
        decisions = db.get("todo_decisions", {})
        ideas = db.get("ideas", [])
        snoozes = db.get("snoozes", {})
        order_list = db.get("chat_order", [])
    positions = {sid: n for n, sid in enumerate(order_list)}
    hues = project_hues([os.path.normcase((item[3] or "").rstrip("/\\")) or "__none__" for item in items])
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
                     "order": positions.get(sid, -1),
                     "hue": hues.get(os.path.normcase(folder) or "__none__", 0),
                     "snoozed_until": snoozes.get(sid, 0) if snoozes.get(sid, 0) > time.time() else 0,
                     "archived": sid in archived, "href": inbox.HREFS.get(sid, ""),
                     "branch": extra.get("branch", ""), "details": extra,
                     "attention": attention, "automated": bool(extra.get("automated")), "managed_by_t3": (source, sid) in t3["sessions"] or bool(T3_PATH.search(cwd or ""))})
    now = time.time()
    estimates = {source: five_hour_limit([r for r in rows if r["source"] == source], prefs["five_hour_limit_tokens"])
                 for source in ("Claude", "Codex")}
    limits = {source: value[0] for source, value in estimates.items()}
    for r in rows:
        d = r["details"]
        spent = sum(v for k, v in (d.get("usage_buckets") or {}).items() if int(k) >= now - 5 * 3600)
        limit = limits.get(r["source"]) or 1
        window, used = context_window(d), d.get("context_tokens")
        r["usage"] = {"total_tokens": (d.get("tokens") or {}).get("total_tokens"),
                      "five_hour_tokens": spent,
                      "five_hour_pct": min(100.0, round(100 * spent / limit, 1)),
                      "context_pct": min(100.0, round(100 * used / window, 1)) if used and window else None}
    rows.sort(key=lambda r: (not r["pinned"], r["order"], -r["updated_at"]))
    return {"chats": rows, "ideas": ideas, "counts": counts(rows),
            "t3": {"status": t3["status"], "reason": t3["reason"], "unresolved": t3.get("unresolved", [])},
            "settings": prefs, "limits": limits, "limit_basis": {k: v[1] for k, v in estimates.items()}, "updated_at": time.time(), "version": 2, "build": web_build(),
            "title": os.environ.get("AGENT_MANAGER_LABEL", "Agent Manager")}


def action(name, body):
    if name == "chats-reorder":
        return _reorder_chats(body)
    if name.startswith("idea-"):
        return _idea_action(name, body)
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


IDEA_ACTIONS = ("idea-add", "idea-update", "idea-delete", "idea-sent", "idea-reorder")


def _clean_idea(body):
    ident = str(body.get("id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ident):
        raise ValueError("Invalid idea id")
    return ident


def _idea_action(name, body):
    """Ideas are to-do notes that are not chats yet; kept in the catalog and shown instantly from the cache."""
    if name not in IDEA_ACTIONS:
        raise ValueError("Unknown action")
    if name == "idea-reorder":
        ids = body.get("ids")
        if not isinstance(ids, list) or len(ids) > 500:
            raise ValueError("Expected a list of idea ids")
        ids = [_clean_idea({"id": i}) for i in ids]
        data = {"id": "", "ids": ids, "text": "", "target": "", "now": time.time()}
        if not _STARTED:
            with _ACTION_LOCK:
                return _apply_idea(name, data)
        _GEN[0] += 1
        _patch_ideas(name, data)
        _QUEUE.put(("idea", name, data, None, None))
        return {"ok": True}
    ident = _clean_idea(body)
    text = str(body.get("text", ""))[:20000]
    job = ("idea", name, {"id": ident, "text": text, "target": str(body.get("target", ""))[:40], "now": time.time()})
    if not _STARTED:
        with _ACTION_LOCK:
            return _apply_idea(job[1], job[2])
    _GEN[0] += 1
    _patch_ideas(job[1], job[2])
    _QUEUE.put((job[0], job[1], job[2], None, None))
    return {"ok": True}


def _edit_ideas(ideas, name, data):
    ideas = list(ideas)
    found = next((i for i in ideas if i["id"] == data["id"]), None)
    if name == "idea-add" and not found:
        ideas.insert(0, {"id": data["id"], "text": data["text"], "created_at": data["now"], "sent": None})
    elif name == "idea-update" and found:
        found["text"] = data["text"]
    elif name == "idea-delete":
        ideas = [i for i in ideas if i["id"] != data["id"]]
    elif name == "idea-reorder":
        order = {ident: n for n, ident in enumerate(data["ids"])}
        ideas.sort(key=lambda i: order.get(i["id"], len(order)))
    elif name == "idea-sent" and found:
        found["sent"] = {"target": data["target"], "at": data["now"]}
    return ideas


def _patch_ideas(name, data):
    cache = _CACHE["data"]
    if cache is not None:
        cache["ideas"] = _edit_ideas(cache.get("ideas", []), name, data)


def _apply_idea(name, data):
    with Catalog(inbox.CATALOG) as db:
        db.set("ideas", _edit_ideas(db.get("ideas", []), name, data))
    return {"ok": True}


def _merge_order(old, ids):
    chosen = set(ids)
    return (ids + [i for i in old if i not in chosen])[:5000]


def _patch_order(ids):
    cache = _CACHE["data"]
    if cache is None:
        return
    old = [r["id"] for r in sorted((r for r in cache["chats"] if r["order"] >= 0), key=lambda r: r["order"])]
    positions = {sid: n for n, sid in enumerate(_merge_order(old, ids))}
    for row in cache["chats"]:
        row["order"] = positions.get(row["id"], -1)
    cache["chats"].sort(key=lambda r: (not r["pinned"], r["order"], -r["updated_at"]))


def _reorder_chats(body):
    """Manual order of chats: the ids you dragged into place go first; chats you never placed stay on top by recency."""
    ids = body.get("ids")
    if not isinstance(ids, list) or len(ids) > 3000:
        raise ValueError("Expected a list of chat ids")
    ids = [str(i) for i in ids]
    if not all(re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", i) for i in ids):
        raise ValueError("Invalid chat id")
    if not _STARTED:
        with _ACTION_LOCK:
            return _apply("chat-order", ids, None, None, None)
    _GEN[0] += 1
    _patch_order(ids)
    _QUEUE.put(("chat-order", ids, None, None, None))
    return {"ok": True}


def flush():
    """Wait for queued clicks to reach disk (called before the app exits)."""
    _QUEUE.join()


def _preview(name, body, rows, sid):
    """Validate and show the change in the cached list at once."""
    if name == "mark-all":
        for row in rows:
            if not row["archived"] and not row["managed_by_t3"] and not row["automated"] and not row["read"]:
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
    elif name == "snooze":
        if body.get("hours") not in (1, 24):
            raise ValueError("Snooze for 1 or 24 hours")
        _patch(sid, snoozed_until=time.time() + body["hours"] * 3600)
    elif name == "unsnooze":
        _patch(sid, snoozed_until=0)
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
    if name == "idea":  # queued as ("idea", action, data, None, None)
        return _apply_idea(body, rows)
    if name == "chat-order":  # queued as ("chat-order", ids, None, None, None)
        with Catalog(inbox.CATALOG) as db:
            db.set("chat_order", _merge_order(db.get("chat_order", []), body))
        return {"ok": True}
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
    elif name in ("snooze", "unsnooze"):
        with Catalog(inbox.CATALOG) as db:
            snoozes = {k: v for k, v in db.get("snoozes", {}).items() if v > now}
            if name == "snooze":
                if body.get("hours") not in (1, 24):
                    raise ValueError("Snooze for 1 or 24 hours")
                snoozes[sid] = now + body["hours"] * 3600
            else:
                snoozes.pop(sid, None)
            db.set("snoozes", snoozes)
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
            if row["archived"] or row["read"] or row["managed_by_t3"] or row["automated"] or row["snoozed_until"] > now or row["state"] not in ("needs", "unread"):
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
