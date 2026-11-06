"""Chat inbox: one page listing recent Claude Code + Codex chats and their last answer.

Run:  python inbox.py          (serves http://localhost:8765 and opens it)
Unread = the chat has new activity since you last clicked "Mark read".
Chat catalog, read marks and pins are saved locally and survive restarts.
"""
import glob
import html
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from functools import wraps
from contextlib import closing
from urllib.parse import urlsplit, parse_qs

from catalog import Catalog
import telemetry

HOME = os.environ.get("AGENT_MANAGER_HOME", os.path.expanduser("~"))
SETTLE_DAYS = 7   # idle longer than this and not pinned -> settled (collapsed, not counted)
WORKING_SECS = 90  # modified this recently = probably still working
REPLY_SECS = 1200  # after you reply, count as working this long
PORT = int(os.environ.get("AGENT_MANAGER_PORT", "8765"))
DATA_DIR = os.environ.get("AGENT_MANAGER_DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
os.makedirs(DATA_DIR, exist_ok=True)
CATALOG = os.path.join(DATA_DIR, "chat_catalog.sqlite3")
DATA_LOCK = threading.RLock()


def locked(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        with DATA_LOCK:
            return fn(*args, **kwargs)
    return call


def write_json(path, obj):
    """Atomic write: temp file -> fsync -> replace, keeping the previous version as .bak."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump(obj, f)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path):
            try:
                shutil.copy2(path, path + ".bak")
            except OSError:
                pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path, default):
    """Read JSON; if the file is missing/corrupt fall back to the .bak copy, then the default."""
    for p in (path, path + ".bak"):
        try:
            with open(p, encoding="utf8") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return default


def safe_lines(path):
    """Yield a file's lines; a file that vanishes or is locked just ends early."""
    try:
        with open(path, encoding="utf8", errors="replace") as f:
            for line in f:
                yield line
    except OSError:
        return


def log(msg):
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "inbox.log"), "a", encoding="utf8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


ATTACHMENT = re.compile(r"\[(?:File|Image|Attachment)[^\]]*\]")


def clean_title(text):
    """Title from the user's real request: skips attachment blocks, placeholders and injected context."""
    request = re.search(r"^## My request[^\n]*:\s*(.+)", text, re.M | re.S)
    if request and request.group(1).strip():
        text = request.group(1)
    elif text.lstrip().startswith("# Files mentioned"):
        names = re.findall(r"^## ([^\n:]+):", text, re.M)
        return ("(attachment) " + names[0])[:80] if names else "(attachment)"
    head = re.split(r"<t3_context", text)[0]
    text = head if head.strip() else text
    text = " ".join(text.split())
    rest = ATTACHMENT.sub("", text).strip(" ;")
    if rest:
        return rest[:80]
    m = re.search(r"\[(?:File|Image): ([^;\]]+)", text)
    return ("(attachment) " + m.group(1))[:80] if m else text[:80]


def app_title(title, parsed):
    """Prefer the app's own title unless it is just a pasted attachment block or injected context."""
    if title and not re.match(r"\s*(?:# Files mentioned|\[(?:File|Image|Attachment))", title) and "<t3_context" not in title:
        return title
    return parsed


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") in ("text", "input_text", "output_text"))


def canonical_id(sid):
    match = re.search(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", sid)
    return match.group(0) if match else sid


def codex_metadata():
    """Read titles/current folders from the app when available; logs still work alone."""
    meta = {}
    for line in safe_lines(os.path.join(HOME, ".codex", "session_index.jsonl")):
        try:
            row = json.loads(line)
            meta[row["id"]] = {"title": row.get("thread_name")}
        except (ValueError, KeyError, TypeError):
            continue
    paths = glob.glob(os.path.join(HOME, ".codex", "state_*.sqlite"))
    paths.sort(key=lambda p: int(re.search(r"state_(\d+)", p).group(1)), reverse=True)
    for path in paths:
        try:
            from pathlib import Path
            with closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(threads)")}
                wanted = [c for c in ("id", "title", "cwd", "archived", "git_branch", "git_origin_url", "tokens_used", "source", "thread_source") if c in columns]
                if "id" not in wanted:
                    continue
                for values in db.execute("SELECT " + ",".join(wanted) + " FROM threads"):
                    row = dict(zip(wanted, values))
                    meta.setdefault(row["id"], {}).update(row)
            break
        except (sqlite3.Error, OSError):
            continue
    return meta


def scan_claude(cutoff, catalog=None):
    out = []
    for p in glob.glob(os.path.join(HOME, ".claude", "projects", "*", "*.jsonl")):
        try:
            stat = os.stat(p)
            mt = stat.st_mtime
        except OSError:  # path too long on Windows
            continue
        if mt < cutoff:
            continue
        cached = catalog.cached_file(p, stat) if catalog else None
        if cached and cached.get("parser_version") != 5:
            cached = None
        if cached is None:
            extra = telemetry.empty()
            title = first_user = last = cwd = role = None
            for line in safe_lines(p):
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(o, dict):
                    continue
                telemetry.claude(o, extra)
                t = o.get("type")
                if t == "custom-title":
                    title = o.get("customTitle") or title
                if o.get("isSidechain"):
                    continue
                cwd = o.get("cwd") or cwd
                msg = o.get("message") or {}
                if t == "user" and not o.get("isMeta"):
                    s = text_of(msg.get("content")).strip()
                    if s and not s.startswith("<"):
                        first_user = first_user or s
                        role = "user"
                elif t == "assistant":
                    s = text_of(msg.get("content")).strip()
                    if s:
                        last = s
                        role = "assistant"
            if not (title or first_user or last):
                continue  # empty/locked/partially written source: retain the saved entry
            cached = {"title": app_title(title, clean_title(first_user or "(untitled)")),
                      "last": (last or "")[:16000], "cwd": cwd, "role": role,
                      "extra": telemetry.finish(extra), "parser_version": 5}
            if catalog:
                catalog.cache_file(p, stat, cached)
        sid = os.path.basename(p)[:-6]
        meta = META.get(sid)
        if meta and meta.get("isArchived"):
            continue
        meta = meta or {}
        mt = (meta.get("lastTurnEdgeAt") or meta.get("lastActivityAt") or mt * 1000) / 1000
        DETAILS[sid] = dict(cached["extra"], automated=bool(meta.get("scheduledTaskId")) and not meta.get("scheduledRunContinued"))
        RUNNING[sid] = cached["extra"]["running"]
        NEEDS[sid] = bool(meta.get("interruptedAwaitingPerson")) or cached["extra"]["needs"]
        out.append(("Claude", sid, app_title(meta.get("title"), cached["title"]), meta.get("cwd") or cached["cwd"], mt, cached["last"], cached["role"]))
    return out


def scan_codex(cutoff, catalog=None, metadata=None):
    metadata = metadata if metadata is not None else codex_metadata()
    out = []
    for p in glob.glob(os.path.join(HOME, ".codex", "sessions", "**", "*.jsonl"), recursive=True):
        try:
            stat = os.stat(p)
            mt = stat.st_mtime
        except OSError:  # path too long on Windows
            continue
        if mt < cutoff:
            continue
        cached = catalog.cached_file(p, stat) if catalog else None
        if cached and cached.get("parser_version") != 5:
            cached = None
        if cached is None:
            extra = telemetry.empty()
            first_user = last = cwd = role = running = None
            sid = canonical_id(os.path.basename(p)[:-6])
            sidechain = False
            for line in safe_lines(p):
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(o, dict):
                    continue
                telemetry.codex(o, extra)
                pl = o.get("payload") or {}
                if o.get("type") == "session_meta":
                    cwd = pl.get("cwd")
                    sid = pl.get("id") or sid
                    source = pl.get("source")
                    sidechain = isinstance(source, dict) and "subagent" in source
                elif o.get("type") == "event_msg":
                    event = pl.get("type")
                    if event == "task_started":
                        running = True
                    elif event in ("task_complete", "task_completed", "turn_aborted", "task_failed"):
                        running = False
                        if pl.get("last_agent_message"):
                            last = pl["last_agent_message"]
                            role = "assistant"
                elif o.get("type") == "response_item" and pl.get("type") == "message":
                    s = text_of(pl.get("content")).strip()
                    if pl.get("role") == "user" and s and not s.startswith(("<", "# AGENTS.md")):
                        first_user = first_user or s
                        role = "user"
                    elif pl.get("role") == "assistant" and s and pl.get("phase") != "commentary":
                        last = s
                        role = "assistant"
            if not (first_user or last):
                continue  # do not replace a saved preview with an incomplete source
            cached = {"id": sid, "title": clean_title(first_user or "(untitled)"),
                      "last": (last or "")[:16000], "cwd": cwd, "role": role,
                      "running": extra["running"], "sidechain": sidechain,
                      "extra": telemetry.finish(extra), "parser_version": 5}
            if catalog:
                catalog.cache_file(p, stat, cached)
        sid = cached["id"]
        meta = metadata.get(sid, {})
        if cached["sidechain"] or meta.get("archived"):
            continue
        RUNNING[sid] = cached["running"]
        NEEDS[sid] = cached["extra"]["needs"]
        DETAILS[sid] = dict(cached["extra"])
        DETAILS[sid]["branch"] = meta.get("git_branch") or DETAILS[sid]["branch"]
        DETAILS[sid]["automated"] = meta.get("thread_source") not in (None, "user", "voice_chat") or meta.get("source") == "exec"
        if not DETAILS[sid]["tokens"] and meta.get("tokens_used"):
            DETAILS[sid]["tokens"] = {"total_tokens": meta["tokens_used"]}
        out.append(("Codex", sid, app_title(meta.get("title"), cached["title"])[:80],
                    meta.get("cwd") or cached["cwd"], mt, cached["last"], cached["role"]))
    return out


@locked
def collect_sessions():
    """Discover all ages once, cache unchanged files, and retain missing source logs."""
    links = claude_links()
    metadata = codex_metadata()
    hidden = {sid for sid, meta in META.items() if meta.get("isArchived")}
    hidden.update(sid for sid, meta in metadata.items() if meta.get("archived"))
    with Catalog(CATALOG) as catalog:
        previous = {record["item"][1]: record for record in catalog.records()}
        items = scan_claude(0, catalog) + scan_codex(0, catalog, metadata)
        live = {item[1] for item in items}
        for item in items:
            src, sid = item[:2]
            source_meta = metadata.get(sid, {}) if src == "Codex" else META.get(sid, {})
            archive_key = "archived" if src == "Codex" else "isArchived"
            unarchived = archive_key in source_meta and not source_meta[archive_key]
            catalog.remember({"item": item, "href": href_for(src, sid, links),
                              "needs": NEEDS.get(sid, False), "hidden": bool(previous.get(sid, {}).get("hidden")) and not unarchived,
                              "extra": DETAILS.get(sid, {})})
        saved = catalog.records()
        for record in saved:
            if record["item"][1] in hidden:
                record["hidden"] = True
                catalog.remember(record)
        hooks = catalog.hooks()
    for record in saved:
        sid = record["item"][1]
        HREFS[sid] = record["href"]
        DETAILS.setdefault(sid, record.get("extra", {}))
        if sid not in live:
            NEEDS[sid] = record["needs"]
            RUNNING[sid] = False  # an unavailable log cannot prove an agent is still running
        hook = hooks.get(sid)
        if hook and hook["timestamp"] >= record["item"][4]:
            HOOKS[sid] = hook
            NEEDS[sid] = hook["state"] == "needs"
            RUNNING[sid] = hook["state"] == "working"
    return sorted((tuple(r["item"]) for r in saved if not r.get("hidden")), key=lambda x: -x[4])


def item_state(sid, mt, role, pinned=False):
    age = time.time() - mt
    if NEEDS.get(sid):
        return "needs"
    evidence_at = max(mt, HOOKS.get(sid, {}).get("timestamp", 0))
    if RUNNING.get(sid) and evidence_at < boot_time():
        return "interrupted"
    if RUNNING.get(sid) is not None:
        if RUNNING[sid]:
            return "working"
        if age > SETTLE_DAYS * 86400 and not pinned:
            return "settled"
        return "idle" if role == "user" else "done"
    if age > SETTLE_DAYS * 86400 and not pinned:
        return "settled"
    if role == "user":
        return "unknown"
    return "idle" if role == "user" else "done"


def boot_time():
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.GetTickCount64.restype = ctypes.c_ulonglong
        return time.time() - kernel.GetTickCount64() / 1000
    return 0


STATE = os.path.join(DATA_DIR, "read_state.json")


def load_state():
    state = {}
    for sid, mt in read_json(STATE, {}).items():
        key = canonical_id(sid)
        state[key] = max(state.get(key, 0), mt)
    return state


def save_state(state):
    write_json(STATE, state)


PINS = os.path.join(DATA_DIR, "pins.json")


def load_pins():
    return {canonical_id(sid): value for sid, value in read_json(PINS, {}).items()}


def merged_state():
    """Our read marks plus the moment you last focused each chat in the Claude app."""
    st = dict(load_state())
    for sid, meta in META.items():
        f = (meta.get("lastFocusedAt") or 0) / 1000
        if f > st.get(sid, 0):
            st[sid] = f
    return st


def unread_count():
    return sum(1 for i in unread_json() if i["state"] in ("unread", "needs"))


@locked
def unread_json(mark_all=False):
    """Finished chats with activity since last marked read. First run baselines everything as read."""
    items = collect_sessions()
    state = read_json(STATE, None)
    if state is None:  # no state and no backup: first run, baseline existing chats as read
        state = {s[1]: s[4] for s in items}
        save_state(state)
    else:
        state = load_state()
    out = []
    pins = load_pins()
    merged = merged_state()
    for src, sid, title, cwd, mt, last, role in items:
        status = item_state(sid, mt, role, sid in pins)
        if status == "needs":
            out.append({"src": src, "title": title, "state": "needs", "mt": mt, "last": (last or "")[:300]})
            continue
        if status in ("settled", "idle"):
            continue
        if status == "working":
            out.append({"src": src, "title": title, "state": "working", "mt": mt, "last": ""})
        elif mt > merged.get(sid, 0):
            out.append({"src": src, "title": title, "state": "unread", "mt": mt, "last": (last or "")[:300]})
    if mark_all:
        state.update({s[1]: s[4] for s in items})
        write_json(STATE, state)
    return out


META = {}   # CLI session id -> desktop session metadata
NEEDS = {}  # CLI session id -> waiting on you
RUNNING = {}  # session id -> explicit Codex task lifecycle, or None for old logs
HREFS = {}  # last known deep link, retained even when the source file disappears
DETAILS = {}
HOOKS = {}


def claude_links():
    """CLI session id -> desktop app session id, from the app's own session files."""
    m = {}
    META.clear()
    NEEDS.clear()
    RUNNING.clear()
    DETAILS.clear()
    HOOKS.clear()
    roots = [
        os.path.join(HOME, "AppData", "Local", "Claude-Data", "*"),
        os.path.join(HOME, "AppData", "Roaming", "Claude"),
        os.path.join(HOME, "AppData", "Local", "Packages", "Claude_*", "LocalCache", "Roaming", "Claude"),
    ]
    paths = {p for root in roots for p in glob.glob(os.path.join(root, "claude-code-sessions", "**", "local_*.json"), recursive=True)}
    for p in sorted(paths):
        try:
            with open(p, encoding="utf8") as f:
                o = json.load(f)
            m[o["cliSessionId"]] = o["sessionId"]
            META[o["cliSessionId"]] = o
        except (OSError, ValueError, KeyError):
            pass
    return m


def href_for(src, sid, links):
    if src == "Codex":
        return "codex://threads/" + canonical_id(sid)
    lid = links.get(sid)
    return f"claude://claude.ai/epitaxy/{lid}" if lid else ""


@locked
def render():
    items = collect_sessions()
    pins = load_pins()
    cards, pinned_cards, settled_cards = [], [], []
    for src, sid, title, cwd, mt, last, role in items:
        is_pinned = sid in pins
        state = item_state(sid, mt, role, is_pinned)
        settled = state == "settled"
        when = time.strftime("%a %H:%M", time.localtime(mt))
        full = html.escape((last or "No answer yet")[:6000])
        snippet = html.escape(" ".join((last or "").split())[:200])
        folder = html.escape(os.path.basename(cwd or ""))
        card = (
            f'<article class="row {src}{" pinned" if is_pinned else ""}" data-href="{html.escape(HREFS.get(sid, ""), quote=True)}" data-id="{html.escape(sid, quote=True)}" data-mt="{mt}" data-state="{state}">'
            f'<i class="dot"></i><div class="main"><div class="top"><span class="title">{html.escape(title)}</span>'
            f'<span class="when">{when}<button class="pn" title="Pin">&#128204;</button><button class="dn" title="Mark done">&#10003; Done</button></span></div>'
            f'<div class="sub">{folder}<span class="pv">Preview</span></div><div class="snip">{snippet}</div>'
            f'<pre class="full">{full}</pre></div></article>'
        )
        (pinned_cards if is_pinned else settled_cards if settled else cards).append(card)
    if read_json(STATE, None) is None:
        unread_json()  # first run baselines existing chats as read
    body = ""
    if pinned_cards:
        body += '<div class="lab">Pinned</div>' + "\n".join(pinned_cards) + '<div class="lab">Recent</div>'
    body += "\n".join(cards) or '<p class="empty">No recent chats</p>'
    if settled_cards:
        body += f'<details class="settled"><summary>Settled ({len(settled_cards)}), idle over {SETTLE_DAYS} days</summary>' + "\n".join(settled_cards) + '</details>'
    return PAGE.replace("%READ%", json.dumps(merged_state())).replace("%CARDS%", body)


PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<meta http-equiv=refresh content=30><title>Chat inbox</title><link rel=icon href=/favicon.ico>
<style>
:root{--bg:#fafafa;--fg:#18181b;--mute:#71717a;--line:#e4e4e7;--hover:#f1f1f3;--acc:#4f46e5;--warn:#d97706}
@media(prefers-color-scheme:dark){:root{--bg:#0f0f11;--fg:#ececf0;--mute:#8b8b95;--line:#222226;--hover:#17171a;--acc:#818cf8;--warn:#fbbf24}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,"Segoe UI",sans-serif}
main{max-width:720px;margin:0 auto;padding:28px 20px 60px}
header{display:flex;align-items:center;gap:12px;margin-bottom:18px}
h1{font-size:20px;font-weight:600;margin:0;letter-spacing:-.01em}
.pill{background:var(--acc);color:#fff;border-radius:99px;padding:1px 9px;font-size:12px;font-weight:600}
.pill.zero{background:var(--line);color:var(--mute)}
.sp{flex:1}
.link{background:none;border:0;color:var(--mute);font:inherit;cursor:pointer;padding:4px 6px;border-radius:6px}
.link:hover{color:var(--fg);background:var(--hover)}
.row{display:flex;gap:12px;padding:12px 10px;border-bottom:1px solid var(--line);border-radius:8px;cursor:pointer}
.row:hover{background:var(--hover)}
.dot{width:8px;height:8px;border-radius:50%;margin-top:6px;flex:none;background:transparent}
.row{border-left:4px solid var(--c);padding-left:12px}
.Claude{--c:#f97316}.Codex{--c:#2563eb}
.tag{display:inline-block;padding:0 7px;border-radius:5px;font-size:11px;font-weight:700;letter-spacing:.02em;background:var(--c);color:#000;margin-right:6px}
.Codex .tag{color:#fff}
.row.unread .dot{background:var(--c)}
.row.working .dot{background:var(--c);animation:p 1.4s infinite}
@keyframes p{50%{opacity:.3}}
.main{min-width:0;flex:1}
.top{display:flex;justify-content:space-between;gap:12px}
.title{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row.unread .title{font-weight:650}
.row.read{opacity:.5}
.when,.sub{color:var(--mute);font-size:12px;white-space:nowrap}
.snip{color:var(--mute);margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.full{display:none;white-space:pre-wrap;font:13px/1.5 ui-monospace,Consolas,monospace;margin:10px 0 0;padding:12px;border-radius:8px;background:var(--hover);max-height:420px;overflow:auto;cursor:text}
.row.open .full{display:block}.row.open .snip{display:none}
.lab{color:var(--mute);font-size:11px;text-transform:uppercase;letter-spacing:.08em;margin:14px 10px 2px}
.settled summary{color:var(--mute);cursor:pointer;margin:22px 10px 4px}
.pn{opacity:0;border:0;background:none;cursor:pointer;filter:grayscale(1)}
.row:hover .pn,.row.pinned .pn{opacity:1}.row.pinned .pn{filter:none}
.nb{font-size:12px;font-weight:700;padding:3px 9px;border-radius:99px;text-decoration:none;background:var(--c);color:#000;white-space:nowrap}
.nb.Codex{color:#fff}.nb:hover{filter:brightness(1.12)}
#q{width:110px;background:var(--hover);border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:3px 8px;font:inherit}
.dn{opacity:0;border:1px solid var(--line);background:none;color:var(--mute);border-radius:6px;cursor:pointer;margin-left:8px}
.row:hover .dn{opacity:1}.dn:hover{color:var(--fg);background:var(--line)}
header{flex-wrap:wrap}
.pv{float:right;margin-left:10px;padding:0 6px;border-radius:5px}.pv:hover{background:var(--line);color:var(--fg)}
.empty{color:var(--mute);text-align:center;margin-top:60px}
</style>
<main><header><h1>Inbox</h1><span class=pill id=n>0</span><span class=sp></span><a class='nb Claude' href='claude://claude.ai/new?surface=chat&source=desktop_action'>+ Claude chat</a><a class='nb Claude' href='claude://code/new?source=desktop_action'>+ Claude code</a><a class='nb Codex' href='codex://threads/new'>+ Codex</a>
<input id=q placeholder='Search' oninput=apply()><button class=link id=f onclick=toggleOnly()>Unread only</button>
<button class=link onclick=markAll()>Mark all read</button></header>
%CARDS%</main>
<script>
const READ=%READ%,R=()=>READ,only=()=>localStorage.getItem('inbox-only')=='1';
function apply(){const r=R();let u=0;const q=document.getElementById('q').value.trim().toLowerCase();
 document.querySelectorAll('.row').forEach(c=>{const w=c.dataset.state=='working',rd=c.dataset.state!='needs'&&(c.dataset.state=='idle'||c.dataset.state=='settled'||r[c.dataset.id]>=+c.dataset.mt);
  c.classList.toggle('working',w);c.classList.toggle('unread',!w&&!rd);c.classList.toggle('read',!w&&rd);
  if(!w&&!rd)u++;c.style.display=((only()&&!w&&rd)||(q&&!c.textContent.toLowerCase().includes(q)))?'none':'';});
 const n=document.getElementById('n');n.textContent=u;n.classList.toggle('zero',!u);
 document.getElementById('f').style.color=only()?'var(--acc)':'';
 document.title=(u?'('+u+') ':'')+'Chat inbox';}
function save(c){const o={};o[c.dataset.id]=+c.dataset.mt;Object.assign(READ,o);fetch('/read',{method:'POST',body:JSON.stringify(o)});}
function markAll(){const o={};document.querySelectorAll('.row').forEach(c=>o[c.dataset.id]=+c.dataset.mt);Object.assign(READ,o);fetch('/read',{method:'POST',body:JSON.stringify(o)});apply();}
function toggleOnly(){localStorage.setItem('inbox-only',only()?'0':'1');apply();}
document.querySelectorAll('.row').forEach(c=>c.addEventListener('click',e=>{
 if(e.target.closest('.full'))return;
 if(e.target.closest('.dn')){save(c);apply();return;}
 if(e.target.closest('.pn')){fetch('/pin',{method:'POST',body:JSON.stringify({id:c.dataset.id,pinned:!c.classList.contains('pinned')})}).then(()=>location.reload());return;}
 if(e.target.classList.contains('pv')){c.classList.toggle('open');return;}
 save(c);apply();if(c.dataset.href)location.href=c.dataset.href;else c.classList.toggle('open');}));
apply();
</script>"""


ON_OPEN = None  # set by tray.py
ON_CONTROL = None
ON_NOTIFY = None


class H(BaseHTTPRequestHandler):
    def reply(self, status, data, content_type="application/json; charset=utf-8"):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode("utf8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    def local_request(self):
        allowed = ("localhost", "127.0.0.1", "[::1]")
        host = self.headers.get("Host", "").split(":")[0]
        origin = self.headers.get("Origin")
        if host not in allowed or (origin and urlsplit(origin).netloc != self.headers.get("Host")):
            self.reply(403, {"error": "This endpoint accepts same-origin local requests only"})
            return False
        return True

    def do_GET(self):
        if not self.local_request():
            return
        try:
            self._get()
        except Exception as e:  # keep serving no matter what
            log("GET error: " + repr(e))
            self.reply(500, {"error": "Could not load the inbox. See inbox.log."})

    def _get(self):
        import dashboard
        path = urlsplit(self.path).path
        if path == "/api/health":
            self.reply(200, {"ok": True, "version": 2, "pid": os.getpid()})
            return
        if path in ("/api/state", "/api/export"):
            self.reply(200, dashboard.cached_snapshot())
            return
        if path == "/api/context":
            sid = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
            try:
                self.reply(200, dashboard.repository_context(sid))
            except ValueError as exc:
                self.reply(404, {"error": str(exc)})
            return
        if path == "/open":
            if ON_OPEN:
                ON_OPEN()
            self.send_response(204)
            self.end_headers()
            return
        if path.startswith("/favicon"):
            data, ctype = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "inbox.ico"), "rb").read(), "image/x-icon"
        elif path in ("/", "/app.js", "/styles.css"):
            name = "index.html" if path == "/" else path[1:]
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", name), "rb") as f:
                data = f.read()
            ctype = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "styles.css": "text/css; charset=utf-8"}[name]
        else:
            self.reply(404, {"error": "Not found"})
            return
        self.reply(200, data, ctype)

    def do_POST(self):
        if not self.local_request():
            return
        try:
            self._post()
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(400, {"error": str(exc)})
        except Exception as e:
            log("POST error: " + repr(e))
            self.reply(500, {"error": "Could not save this change. See inbox.log."})

    def _post(self):
        import dashboard
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= 1_000_000:
            self.reply(413, {"error": "Invalid request size"})
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.reply(415, {"error": "Expected application/json"})
            return
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError("Expected an object")
        if self.path == "/api/control":
            command = body.get("command")
            if command not in ("restart", "quit"):
                raise ValueError("Unknown app control")
            if ON_CONTROL is None:
                self.reply(409, {"error": "App control requires the tray launcher"})
                return
            self.reply(200, {"ok": True})
            threading.Timer(0.3, lambda: ON_CONTROL(command)).start()
            return
        if self.path == "/api/test-notification":
            if ON_NOTIFY is None:
                self.reply(409, {"error": "Notifications require the tray launcher"})
                return
            ON_NOTIFY("Notifications are working. Unread chats get one reminder after your chosen delay.", "Agent Manager")
            self.reply(200, {"ok": True})
            return
        if self.path.startswith("/api/"):
            name = self.path[5:]
            if name not in ("read", "pin", "archive", "mark-all", "settings", "hook"):
                self.reply(404, {"error": "Not found"})
                return
            self.reply(200, dashboard.action(name, body))
            return
        if self.path == "/pin":
            pins = load_pins()
            if body.get("pinned"):
                pins[body["id"]] = True
            else:
                pins.pop(body["id"], None)
            write_json(PINS, pins)
        if self.path == "/read":
            state = load_state()
            state.update(body)
            save_state(state)
        if self.path not in ("/pin", "/read"):
            self.reply(404, {"error": "Not found"})
            return
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if "--json" in sys.argv:
        sys.stdout.buffer.write(json.dumps(unread_json("--mark-all" in sys.argv)).encode("utf8"))
        sys.exit()
    if "--print" in sys.argv:
        sys.stdout.buffer.write(render().encode("utf8"))
        sys.exit()
    try:
        srv = HTTPServer(("127.0.0.1", PORT), H)
    except OSError:  # already running
        sys.exit()
    if "--no-browser" not in sys.argv:
        threading.Timer(0.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    srv.serve_forever()
