# Chat inbox
Double-click `inbox.bat` (or run `python inbox.py`) -> opens http://localhost:8765.
Lists Claude Code + Codex chats from the last 7 days, newest first, with the last answer.
Red = finished and unread, orange = still working, faded = read. Opening "Last answer" or
clicking "Mark read" clears it; new activity makes it unread again. Page refreshes every 30 s.
Read-state is in the browser (localStorage). Reads ~/.claude/projects and ~/.codex/sessions only.
Tip: pin the tab, or put a shortcut to inbox.bat in shell:startup.

## Mod (pane inside Claude)
`chat-inbox-mod/` is a Claude Code mod: pane of unread/working chats, refreshed every 30 s.
Commands: `/inbox` opens it, `/inbox-clear` marks all read. Load with `claude --plugin-dir <path to chat-inbox-mod>`.
First `--json` run baselines all existing chats as read (read_state.json).

## Desktop icon
The 'Chat Inbox' shortcut on the Desktop runs (launcher is the Desktop shortcut, which opens Chrome directly)

Clicking a row opens that chat in the desktop app (claude://claude.ai/epitaxy/<id> or codex://threads/<id>); 'Preview' expands the last answer. Logo: make_icon.py -> inbox.ico.

Desktop shortcut now targets Chrome directly (own profile in chrome_profile/ so it pins with its own icon). Server autostarts via Startup folder shortcut 'Chat Inbox server'.


## Tray app
`tray.py` = server + system-tray icon with a red unread badge (refreshes every 20 s). Left-click opens the Chrome app window;
right-click: Mark all read, Quit. Autostart: Startup-folder shortcut "Chat Inbox server" -> pythonw tray.py. Needs `pip install pystray pillow`.
Read state is now server-side in read_state.json (shared by page, tray and the mod).

## Roadmap (agreed order)
1. [done] Tray icon + badge
2. Reminder notification a few minutes after the app's own notification if still unread
3. "Needs your input" state
4. Accurate working status (hooks instead of the 90 s mtime guess)
5. Projects (group chats by project)
6. Per-chat context (branch, PR) + token usage window with breakdown
7. Cloud and remote sessions
(Reply/peek dropped: the click-through link to the chat is enough.)

## Ideas from T3 Code (not built yet)
Search/command palette (search box done), auto-settle chats idle >N days into a collapsed section, branch/worktree label per chat,
status chips, keyboard shortcuts (j/k to move, e = done), diff summary per chat.
Header buttons: + Claude chat / + Claude code / + Codex (deep links claude://claude.ai/new?surface=chat, claude://code/new, codex://threads/new).

## Reliability
Startup: Task Scheduler task 'Chat Inbox' (at logon + every 5 min, no duplicates thanks to a mutex, restarts on failure). Replaces the Startup-folder shortcut.
Data (read_state.json, pins.json) is written atomically with a .bak copy and survives restarts/crashes; corrupt files fall back to the .bak. Errors go to inbox.log.
The tray watchdog restarts the web server thread if it dies. Settled = idle >7 days and not pinned (collapsed, not counted).
