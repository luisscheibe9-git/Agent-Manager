# Chat Inbox: handoff notes (any AI agent: read this first)

Last updated: 2026-10-27. Owner: Luis (lscheibe). Windows 11, PowerShell. Don't commit/push unless asked.

Active continuation details and exact testing/cloud steps: `notes/HANDOFF.md`. User authorized periodic GitHub updates during this implementation. Local backend currently passes 20 distinct regression tests; interactive QA is ongoing. Private cloud implementation follows only once local checks pass.

## Current machine setup (2026-10-27)
- Active milestone: implement all local wishlist features, test them extensively through computer use, then build the private cloud view only after local checks pass. Luis supplied `https://github.com/pingdotgg/t3code` as an architectural reference and authorized periodic GitHub updates. Use tested code milestones; keep this document current between them.
- Git authentication is now working through GitHub CLI. Repaired the interrupted clone by fetching origin/main and restoring HEAD/index without overwriting local changes. Working branch: `main`; repository is private, with no existing PR workflow. Code below is in progress until the validation report records otherwise.
- In progress: split dashboard frontend under `web/`, `dashboard.py` APIs/preferences/reminders/context, `telemetry.py` lifecycle and usage readers, hook ingestion and graceful app controls. Original regression suite (8 cases) and JavaScript syntax checks pass so far; expanded tests and desktop checks are still pending. Nothing has been published to the cloud yet.
- Repository renamed on GitHub to `luisscheibe9-git/Agent-Manager`.
- Downloaded the main-branch files at `e442b8a3e535d82625c44acbbbb51346db53a178` into `D:\agent manager` through the GitHub connector. Git clone stalled on credential-manager authentication; `.git` has origin configured but no fetched history yet. Do not commit the downloaded files as a new initial commit; finish fetching the existing history when Git authentication is available.
- Python on this machine: `C:\Users\Luis\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` (adjacent `pythonw.exe` for the tray). Installed `pystray`; Pillow was already installed. Updated `inbox.bat` to this interpreter.
- Baseline run found 3 untitled Codex rows. Fixed detection: current Codex input/output text blocks, final-vs-commentary phases, canonical session IDs, desktop/index titles and current folders; Claude metadata now includes the Windows Store location. The updated collector finds 10 titled chats with previews (4 Claude, 6 Codex).
- Latest direction: keep the app local while refining it, inspired by T3 Code. Its purpose is a to-do list for running agents. Required: preserve the chat list across computer restarts. Optional later: an owner-only website to check the last synced list from anywhere, including while the computer is off. GitHub Pages is familiar to Luis, but hosting/access-control choices are undecided. No website migration has been started.
- Added `catalog.py` and ignored `chat_catalog.sqlite3`: transactional chat catalog plus file fingerprint cache. Discover all log ages; retain last-known rows, previews and links if logs disappear. Keep explicit source archives hidden. Existing rollout-style read/pin keys normalize to canonical IDs; page read timestamps now retain fractional seconds.
- Installed per-user **Agent Manager.lnk** in the Windows Startup folder through `install-startup.ps1`. Targets the bundled `pythonw.exe` and this folder's `tray.py`; starts minimized at sign-in. `inbox.bat` now opens/focuses the tray app. No scheduled task is required on this machine.
- Eight tests pass, including separate-process restoration without source logs, old pinned chats, current parsers, source archive retention, incomplete-source recovery, read-state backup recovery and precise read timestamps. An actual Windows reboot has not been performed.
- Reload pending: automatic approval review blocked the command that stopped the original running process (PID 10228). Luis has been asked to choose Quit from the tray menu; relaunch using the installed startup shortcut or `inbox.bat`, then verify HTTP/UI. Launching the shortcut while the old app runs correctly exits without creating a second instance. The modified source and catalog are on disk, but the original running process has not loaded them yet.
- Rust/Tauri is a candidate for future desktop packaging (web UI + Rust backend + system webview), not part of this change. No commit/push or cloud publishing authorized/performed.

## Goal
Luis starts many Claude (desktop app) and Codex (desktop app) chats, clicks away, and never reads the output. This tool keeps
track of them: a tray icon + Windows taskbar badge with the unread count, and a clean inbox window. Clicking a row opens that
chat in its own app (deep link). No in-tool chat/reply, no worktrees (explicitly dropped).

## How it works
- `inbox.py`: scans Claude transcripts (`~/.claude/projects/*/*.jsonl`) and Codex rollouts (`~/.codex/sessions/**/*.jsonl`),
  builds the page (HTML/CSS/JS inline), serves it on `http://localhost:8765` (read/pin POST endpoints, `/open` focuses window).
  Claude chats use the desktop app's own metadata (`%LOCALAPPDATA%\Claude-Data\*\claude-code-sessions\**\local_*.json`:
  `cliSessionId`, `title`, `lastFocusedAt`, `lastTurnEdgeAt`, `isArchived`, `interruptedAwaitingPerson`) so counts match the app's sidebar.
  Codex titles/folders/archive state are read from its index and local SQLite metadata when available, with transcript fallback.
- `tray.py`: runs the server + system tray icon (pystray) with badge; every 10 s refreshes, sets the taskbar overlay badge, restarts
  the server if it died. Single instance via mutex. `--open` focuses the existing window (or starts one). Opens the window once at login.
- `taskbar.py`: ctypes COM: taskbar overlay icon (ITaskbarList3.SetOverlayIcon), finds the Chrome app window ("Chat inbox" title),
  sets window icon + AppUserModel ID/relaunch command so pinning keeps our logo.
- `chat-inbox-mod/`: Claude Code mod (pane + /inbox, /inbox-clear). Live copy is under `~/.claude/dev-mods/<session>/chat-inbox`.
- `make_icon.py` draws the six-colour pinwheel logo -> `inbox.ico`, `inbox_512.png`.
- Data: SQLite `chat_catalog.sqlite3` for saved chats/cache; atomic JSON + `.bak` for `read_state.json` and `pins.json`. Log: `inbox.log`.
- Startup on this machine: Startup-folder **Agent Manager.lnk** runs `pythonw.exe tray.py`. A Task Scheduler setup documented by the original machine is not installed here.
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
verify after a real Windows reboot that the tray, badge and pins come back.

## Gotchas for the next agent
- Python: use the bundled interpreter in Current machine setup above; plain `python` is the Store stub. Dependencies are in `requirements.txt`.
- Bash tool heredocs mangle backslashes (`\n`, `\x00`, Windows paths). Write patch scripts with the Write tool, not heredocs.
- Restart after code changes: Quit this app through its tray menu, then run `inbox.bat`. Never stop unrelated Python processes.
- Don't Move-Item the project folder while a shell has it as cwd (it failed once).
- Claude mod text must not contain control characters (the pane refuses them).
- First run of `unread_json` baselines everything as read if no `read_state.json` (and no `.bak`) exists.
