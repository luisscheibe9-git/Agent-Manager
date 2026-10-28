# Chat Inbox: handoff notes (any AI agent: read this first)

Last updated: 2026-10-27. Owner: Luis (lscheibe). Windows 11, PowerShell. Don't commit/push unless asked.

## Goal
Luis starts many Claude (desktop app) and Codex (desktop app) chats, clicks away, and never reads the output. This tool keeps
track of them: a tray icon + Windows taskbar badge with the unread count, and a clean inbox window. Clicking a row opens that
chat in its own app (deep link). No in-tool chat/reply, no worktrees (explicitly dropped).

## How it works
- `inbox.py`: scans Claude transcripts (`~/.claude/projects/*/*.jsonl`) and Codex rollouts (`~/.codex/sessions/**/*.jsonl`),
  builds the page (HTML/CSS/JS inline), serves it on `http://localhost:8765` (read/pin POST endpoints, `/open` focuses window).
  Claude chats use the desktop app's own metadata (`%LOCALAPPDATA%\Claude-Data\*\claude-code-sessions\**\local_*.json`:
  `cliSessionId`, `title`, `lastFocusedAt`, `lastTurnEdgeAt`, `isArchived`, `interruptedAwaitingPerson`) so counts match the app's sidebar.
  Codex has no such metadata: unread = finished + new activity since you last marked it read.
- `tray.py`: runs the server + system tray icon (pystray) with badge; every 10 s refreshes, sets the taskbar overlay badge, restarts
  the server if it died. Single instance via mutex. `--open` focuses the existing window (or starts one). Opens the window once at login.
- `taskbar.py`: ctypes COM: taskbar overlay icon (ITaskbarList3.SetOverlayIcon), finds the Chrome app window ("Chat inbox" title),
  sets window icon + AppUserModel ID/relaunch command so pinning keeps our logo.
- `chat-inbox-mod/`: Claude Code mod (pane + /inbox, /inbox-clear). Live copy is under `~/.claude/dev-mods/<session>/chat-inbox`.
- `make_icon.py` draws the six-colour pinwheel logo -> `inbox.ico`, `inbox_512.png`.
- Data (atomic writes + `.bak`): `read_state.json` (id -> last-read time), `pins.json`. Log: `inbox.log`.
- Startup: Task Scheduler task **Chat Inbox** (at logon + every 5 min, no duplicates, restart on failure) runs
  `pythonw.exe tray.py`. Desktop shortcut "Chat Inbox" runs `pythonw tray.py --open`.
- Window = Chrome `--app=http://localhost:8765 --user-data-dir=<this folder>\chrome_profile` (Luis uses Chrome, never Edge).

## Behaviour decisions
- Unread = finished chat with activity newer than the last read mark (or newer than last focus in the Claude app). If Luis's message
  is the latest in a chat it counts as working, not unread (for 20 min, then ignored).
- Settled = idle >7 days and not pinned: collapsed, not counted. Pinned float to top. "Done" button marks read without opening.
- Row colour = source (Claude orange/black, Codex blue/black); no "Claude"/"Codex" text on rows.
- **Status colours (Luis's rule): working and NOT needing input = highlighted GREEN; needs Luis's input = RED.** (Not built yet.)
- Header buttons: + Claude chat (`claude://claude.ai/new?surface=chat...`), + Claude code (`claude://code/new`), + Codex (`codex://threads/new`).
  Deep links found in the apps' app.asar; whether new chats start folder-free is decided by the apps, unverified.

## Roadmap (agreed order)
1. Needs-your-input state (field `interruptedAwaitingPerson` already read into `NEEDS`; not shown in UI yet) + green/red highlights.
2. Accurate working status (hooks instead of 90 s mtime guess).
3. Reminder notification a few minutes after the app's own, if still unread.
4. Projects: group chats by project (very important to Luis).
5. Per-chat context (branch/PR) + token-usage window with breakdown.
6. Cloud and remote sessions.
Also pending: private GitHub repo (gh is logged in as luisscheibe9-git; .gitignore chrome_profile/, *.json state, *.bak, inbox.log, __pycache__);
verify after reboot that the tray, badge and pins come back.

## Gotchas for the next agent
- Python: `C:\Users\lscheibe\AppData\Local\Programs\Python\Python313\python.exe` (plain `python` is the Store stub). Needs `pip install pystray pillow`.
- Bash tool heredocs mangle backslashes (`\n`, `\x00`, Windows paths). Write patch scripts with the Write tool, not heredocs.
- Restart after code changes: `Get-Process pythonw | Stop-Process -Force; Start-ScheduledTask -TaskName 'Chat Inbox'`.
- Don't Move-Item the project folder while a shell has it as cwd (it failed once).
- Claude mod text must not contain control characters (the pane refuses them).
- First run of `unread_json` baselines everything as read if no `read_state.json` (and no `.bak`) exists.
