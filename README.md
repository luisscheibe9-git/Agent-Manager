# Agent Manager

A local inbox/to-do list for Claude Code and Codex chats. It runs on Windows with
a tray icon, an unread badge, and a Chrome app window at http://localhost:8765.

## Run

Install Python dependencies with `python -m pip install -r requirements.txt`, then
run `pythonw tray.py --open`. `inbox.bat` launches the tray app using the bundled
Python runtime currently available on Luis's computer. Running it again focuses
the existing window rather than starting a second server.

For a plain browser window, `python inbox.py` serves the inbox without the tray.

## Start at Windows sign-in

Run `./install-startup.ps1` in PowerShell. It installs a per-user shortcut named
**Agent Manager** in the Windows Startup folder. The default interpreter is the
bundled runtime under `%USERPROFILE%/.cache/codex-runtimes/`; pass
`-Pythonw 'C:/path/to/pythonw.exe'` to use another installation with the dependencies.
Rerun the script if Python or the project moves. No administrator access is needed.

At sign-in the app starts in the tray and opens its taskbar window minimized.
Remove the **Agent Manager** shortcut from the Startup folder to disable autostart.
The tray's **Quit** command stops the app for the current login session.

## Saved chats and state

- `chat_catalog.sqlite3`: durable chat list, last known previews/deep links, and
  a cache of parsed transcripts. Chats remain saved even if their original log
  files disappear or become older than 30 days. SQLite transactions protect writes.
- `read_state.json` and `pins.json`: read marks and pinned chats, written atomically
  with `.bak` recovery. Existing read marks/pins from older rollout-style IDs are
  recognized under the canonical chat ID.
- `chrome_profile/`: the dedicated Chrome profile and browser preferences.
- `inbox.log`: background errors and server startup events.

These files are local and ignored by Git. Keep the catalog and JSON files when
moving or backing up the project. Deleting them resets the corresponding saved data.

Unpinned chats idle for seven days move into the expandable **Settled** section;
they are retained, but do not contribute to the unread badge. Pinned chats stay above
the recent list. **Done** marks a chat read; new activity makes it unread again.
Chats archived in the source app are hidden. On a fresh install, existing chats are
initially marked read to avoid a flood of notifications.

## Detection and interface

`inbox.py` discovers local Claude transcripts under `~/.claude/projects` and Codex
transcripts under `~/.codex/sessions`. It reads Claude desktop metadata from the
legacy location, the roaming profile, and the Windows Store app location. Codex
titles and current folders come from its index/local metadata when available.
This does not fetch cloud-only chat history.

The page refreshes every 30 seconds; the tray checks every 10 seconds. Unchanged
transcripts are cached. Codex completion/start events distinguish final answers
from progress commentary; old logs and Claude still use timing/role heuristics
where lifecycle information is unavailable. Long-running/interrupted status
accuracy remains an area for improvement.

Rows open the original chat using its desktop deep link. **Preview** expands the
last answer. Search, pins, unread filtering, and mark-all-read are available.

## Components

- `inbox.py`: discovery, status/read rules, HTML/CSS/JavaScript, local HTTP endpoints.
- `catalog.py`: SQLite catalog and transcript cache.
- `tray.py`: tray icon, Chrome app launcher, single-instance mutex, server watchdog.
- `taskbar.py`: Windows taskbar icon and unread overlay.
- `chat-inbox-mod/`: optional Claude Code pane with `/inbox` and `/inbox-clear`.
  Its interpreter/script paths must be configured for the machine where it runs.
- `make_icon.py`: generates the icon assets.

## Verification

Run `python -m unittest -v test_inbox`. Tests use temporary synthetic session files,
including restoring a catalog/read marks/pins in a new process without the source logs.

See `NOTES.md` for decisions and the feature roadmap. Current direction: refine the
local app first, with an optional owner-only remote view later. No cloud sync is enabled.
