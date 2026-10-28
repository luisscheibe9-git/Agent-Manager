"""Chat inbox: one page listing recent Claude Code + Codex chats and their last answer.

Run:  python inbox.py          (serves http://localhost:8765 and opens it)
Unread = the chat has new activity since you last clicked "Mark read".
Read state lives in the browser (localStorage), so no hooks or config are needed.
"""
import glob
import html
import json
import os
import shutil
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

HOME = os.path.expanduser("~")
DAYS = 30         # how far back to scan
SETTLE_DAYS = 7   # idle longer than this and not pinned -> settled (collapsed, not counted)
WORKING_SECS = 90  # modified this recently = probably still working
REPLY_SECS = 1200  # after you reply, count as working this long
PORT = 8765


def write_json(path, obj):
    """Atomic write: temp file -> fsync -> replace, keeping the previous version as .bak."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf8") as f:
        json.dump(obj, f)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except OSError:
            pass
    os.replace(tmp, path)


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


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def scan_claude(cutoff):
    claude_links()  # refresh META
    out = []
    for p in glob.glob(os.path.join(HOME, ".claude", "projects", "*", "*.jsonl")):
        try:
            mt = os.path.getmtime(p)
        except OSError:  # path too long on Windows
            continue
        if mt < cutoff:
            continue
        title = first_user = last = cwd = role = None
        for line in safe_lines(p):
            try:
                o = json.loads(line)
            except ValueError:
                continue
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
                    role = "user"  # you replied: the chat is no longer waiting on you
            elif t == "assistant":
                s = text_of(msg.get("content")).strip()
                if s:
                    last = s
                    role = "assistant"
        sid = os.path.basename(p)[:-6]
        meta = META.get(sid)
        if meta is None or meta.get("isArchived"):
            continue  # not a desktop-app chat, or archived: the app's sidebar doesn't list it either
        mt = (meta.get("lastTurnEdgeAt") or meta.get("lastActivityAt") or mt * 1000) / 1000
        NEEDS[sid] = bool(meta.get("interruptedAwaitingPerson"))
        out.append(("Claude", sid, meta.get("title") or title or (first_user or "(untitled)")[:80], meta.get("cwd") or cwd, mt, last, role))
    return out


def scan_codex(cutoff):
    out = []
    for p in glob.glob(os.path.join(HOME, ".codex", "sessions", "**", "*.jsonl"), recursive=True):
        try:
            mt = os.path.getmtime(p)
        except OSError:  # path too long on Windows
            continue
        if mt < cutoff:
            continue
        first_user = last = cwd = role = None
        for line in safe_lines(p):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            pl = o.get("payload") or {}
            if o.get("type") == "session_meta":
                cwd = pl.get("cwd")
            elif o.get("type") == "response_item" and pl.get("type") == "message":
                s = text_of(pl.get("content")).strip()
                if pl.get("role") == "user" and s and not s.startswith("<"):
                    first_user = first_user or s
                    role = "user"
                elif pl.get("role") == "assistant" and s:
                    last = s
                    role = "assistant"
        out.append(("Codex", os.path.basename(p)[:-6], (first_user or "(untitled)")[:80], cwd, mt, last, role))
    return out


STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "read_state.json")


def load_state():
    return read_json(STATE, {})


def save_state(state):
    write_json(STATE, state)


PINS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pins.json")


def load_pins():
    return read_json(PINS, {})


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


def unread_json(mark_all=False):
    """Finished chats with activity since last marked read. First run baselines everything as read."""
    items = scan_claude(time.time() - DAYS * 86400) + scan_codex(time.time() - DAYS * 86400)
    now = time.time()
    state = read_json(STATE, None)
    if state is None:  # no state and no backup: first run, baseline existing chats as read
        state = {s[1]: s[4] for s in items}
        mark_all = True
    items.sort(key=lambda x: -x[4])
    out = []
    pins = load_pins()
    merged = merged_state()
    for src, sid, title, cwd, mt, last, role in items:
        if now - mt > SETTLE_DAYS * 86400 and sid not in pins:
            continue  # settled
        if NEEDS.get(sid):
            out.append({"src": src, "title": title, "state": "needs", "mt": mt, "last": (last or "")[:300]})
            continue
        if role == "user" and now - mt >= REPLY_SECS:
            continue  # you spoke last long ago: abandoned, not waiting on you
        if now - mt < WORKING_SECS or role == "user":
            out.append({"src": src, "title": title, "state": "working", "mt": mt, "last": ""})
        elif mt > merged.get(sid, 0):
            out.append({"src": src, "title": title, "state": "unread", "mt": mt, "last": (last or "")[:300]})
    if mark_all:
        state.update({s[1]: s[4] for s in items})
        write_json(STATE, state)
    return out


META = {}   # CLI session id -> desktop session metadata
NEEDS = {}  # CLI session id -> waiting on you


def claude_links():
    """CLI session id -> desktop app session id, from the app's own session files."""
    m = {}
    pat = os.path.join(HOME, "AppData", "Local", "Claude-Data", "*", "claude-code-sessions", "**", "local_*.json")
    for p in glob.glob(pat, recursive=True):
        try:
            o = json.load(open(p, encoding="utf8"))
            m[o["cliSessionId"]] = o["sessionId"]
            META[o["cliSessionId"]] = o
        except (OSError, ValueError, KeyError):
            pass
    return m


def href_for(src, sid, links):
    if src == "Codex":
        return "codex://threads/" + sid[-36:]
    lid = links.get(sid)
    return f"claude://claude.ai/epitaxy/{lid}" if lid else ""


def render():
    items = scan_claude(time.time() - DAYS * 86400) + scan_codex(time.time() - DAYS * 86400)
    items.sort(key=lambda x: -x[4])
    now = time.time()
    links = claude_links()
    pins = load_pins()
    cards, pinned_cards, settled_cards = [], [], []
    for src, sid, title, cwd, mt, last, role in items:
        is_pinned = sid in pins
        settled = now - mt > SETTLE_DAYS * 86400 and not is_pinned
        state = "settled" if settled else "needs" if NEEDS.get(sid) else "working" if now - mt < WORKING_SECS or (role == "user" and now - mt < REPLY_SECS) else "idle" if role == "user" else "done"
        when = time.strftime("%a %H:%M", time.localtime(mt))
        full = html.escape((last or "No answer yet")[:6000])
        snippet = html.escape(" ".join((last or "").split())[:200])
        folder = html.escape(os.path.basename(cwd or ""))
        card = (
            f'<article class="row {src}{" pinned" if is_pinned else ""}" data-href="{href_for(src, sid, links)}" data-id="{sid}" data-mt="{int(mt)}" data-state="{state}">'
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


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self._get()
        except Exception as e:  # keep serving no matter what
            log("GET error: " + repr(e))
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(("Inbox error, will retry: " + repr(e)).encode("utf8"))

    def _get(self):
        if self.path == "/open":
            if ON_OPEN:
                ON_OPEN()
            self.send_response(204)
            self.end_headers()
            return
        if self.path.startswith("/favicon"):
            data, ctype = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "inbox.ico"), "rb").read(), "image/x-icon"
        else:
            data, ctype = render().encode("utf8"), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            self._post()
        except Exception as e:
            log("POST error: " + repr(e))
            self.send_response(500)
            self.end_headers()

    def _post(self):
        if self.path == "/pin":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            pins = load_pins()
            if body.get("pinned"):
                pins[body["id"]] = True
            else:
                pins.pop(body["id"], None)
            write_json(PINS, pins)
        if self.path == "/read":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            state = load_state()
            state.update(body)
            save_state(state)
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
