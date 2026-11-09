# Handoff (written 2026-11-05, end of a long session)

Read `../NOTES.md` first (top "CURRENT STATE" block), then this file. A paste-ready prompt for a new chat is in `NEW_CHAT_PROMPT.md`.
Older sections of `NOTES.md` are chronological history; where they disagree with this file, this file wins.

## What the app is
A Windows tray app plus local web dashboard ("Chat inbox") that turns Luis's Claude and Codex chats into a to-do list. It reads local transcripts and app metadata, shows a badge, and serves a page at `http://localhost:8765` that Chrome shows as an app window.
Repo: https://github.com/luisscheibe9-git/Agent-Manager (PUBLIC since 2026-11-05). Local checkout: `%USERPROFILE%\Desktop\Chat_Inbox`. Working branch `codex/simple-black`; `main` was fast-forwarded to it at `ac96177` and should be fast-forwarded again after the next push (`git branch -f main codex/simple-black`, push both). Git author email is his personal address already set in this repo's config (history was rewritten; never reintroduce the Cal Poly address).

## How to run, restart, test
- Python: `%USERPROFILE%\AppData\Local\Programs\Python\Python313\python.exe` (`pythonw.exe` for the tray). Plain `python` may not be on PATH in PowerShell.
- The app starts at sign-in from Task Scheduler task **Chat Inbox** (logon trigger plus a 5-minute repeat, IgnoreNew) running `pythonw tray.py`. Restart: kill `pythonw.exe` processes whose command line contains `Chat_Inbox`, wait 2 s, `Start-ScheduledTask 'Chat Inbox'`, wait about 30 s (first scan re-parses logs). Check `http://127.0.0.1:8765/api/state`.
- Tests: `python -X utf8 -m unittest test_inbox test_dashboard test_todo test_t3_sessions test_black_launcher` (57 pass). Windows temp-file cleanup occasionally makes one test flake; rerun.
- JS check: `node --check web/app.js`.
- Page files in `web/` are served fresh; `/api/state` returns a `build` id and open windows reload themselves when it changes (a window opened before that feature needs one Ctrl+R).
- Verify UI in the Browser pane at `http://localhost:8765`. **Never click Done / Snooze / reorder on the real list while testing** (an earlier test woke a snoozed chat of Luis's). For mutation tests run a copy: copy `chat_catalog.sqlite3*`, `read_state.json`, `pins.json` to a temp dir, then `AGENT_MANAGER_DATA_DIR=<dir> AGENT_MANAGER_PORT=8791 python inbox.py --no-browser` and use `localhost:8791`. If you must touch real data through the API, undo it afterwards.

## Files
- `inbox.py` HTTP server (`H` handler, allowed POST action names list), transcript scanners (`scan_claude`, `scan_codex`), title cleaning (`clean_title`, `app_title`), parser cache (`parser_version` currently 9; bump it when parsed fields change).
- `dashboard.py` snapshot (`snapshot`, rows), background refresher + cache (`start_refresher`, `cached_snapshot`), actions and writer queue (`action`, `_preview`, `_apply`, `_idea_action`, `_reorder_chats`), usage estimates (`five_hour_limit`, `context_window`), project hues (`project_hues`), reminders (`notify_due`), `freeze_focus_reads`.
- `telemetry.py` per-chat details from transcripts: tokens, usage buckets (5-minute, kept 60 days), limit-hit detection, needs/working state.
- `t3_sessions.py` read-only scan of T3 Code's SQLite for membership and the unresolved list.
- `catalog.py` SQLite catalog and settings store. `tray.py` tray icon, server thread, window launching. `taskbar.py` Windows badge and window helpers. `black_launcher.py` launcher for worktrees. `web/` index.html, app.js, styles.css. `tools/` QA and hook helpers. `chat-inbox-mod/` Claude Code mod (status unknown). `notes/` docs and synthetic screenshots.
- Data (gitignored): `read_state.json`, `pins.json`, `chat_catalog.sqlite3`, `inbox.log`, `chrome_profile/`. Catalog settings keys: `preferences`, `todo_decisions`, `archived`, `ideas`, `snoozes`, `chat_order`, `project_colors`, `focus_reads_frozen`, plus tables for hooks, reminders, sessions, file cache.

## Behavior as built (decisions Luis made)
- A chat leaves the to-do list ONLY when he presses Done (or Mark all done). Opening a chat, focusing it in the Claude app, or resuming does not resolve it. New activity after Done (new answer, turn or question) returns it.
- Hidden from the to-do list, badge and reminders: T3 Code chats (also anything started under `~/.t3/`), scheduled/automated chats (Claude `scheduledTaskId` unless he replied; Codex non-user threads and `exec`), snoozed chats until their time. They are still visible under All chats.
- Top banner: blue "N unresolved T3 Code chats" mirrors T3 Code's own unsettled threads (informational, no links).
- Cards: flat list, project name label above each chat, dotted grip (drag to reorder, saved), status dot, title, three chips (purple tokens, teal context %, orange "Limit N%"), down arrow (send to bottom; pinned chats refuse), Pin, big green Done; 4-line preview with timestamp bottom-right. Working chats render in a "Working" block at the bottom. Each project has one saved hue that tints its cards and label (24 hues, farthest-point assignment, most recent projects first).
- Header: "N done today", small triangle that reveals the search/project/All chats/Mark all done/Settings row (hidden by default; closing it resets filters; `/` opens it).
- Blocks under the list: Snoozed (collapsed), Recently done (done in the last 7 days, newest first, undo button).
- Ideas: green "+ New to-do" opens a composer; Enter or the check adds a thin "Idea" row; click to expand, edit, or "Make this a chat" with Claude chat / Claude Code / Codex (copies text to clipboard and opens `claude://claude.ai/new?surface=chat&source=desktop_action&q=`, `claude://code/new?q=`, `codex://threads/new?prompt=`). Drag rows to reorder; sent ideas stay labeled "Sent to X".
- Usage chips: total tokens are provider-reported (include cache). "Limit %" is an ESTIMATE of this chat's share of the 5-hour limit: cost-weighted spend in the last 5 hours divided by an estimated limit. Claude limit = median spend before each "You've hit your session limit" message found in transcripts (about 5 hits, roughly 22M weighted units); Codex has no such calibration so it uses the busiest 5 hours seen. Luis's plan is Claude Team Standard (1.25x Pro per session per Anthropic; no absolute numbers published). Settings has an override.
- Snooze: the card button was replaced by the down arrow, but the backend (`snooze`/`unsnooze`, `snoozed_until`) and the Snoozed block remain; there is currently no button to create a snooze. Decide whether to restore it or remove the dead code.

## Done in this project (high level)
Tray badge, hooks-based working/needs state, reminders, projects, tokens and context, T3 separation, speed (background scan cache + optimistic UI), single window at startup, only-Done resolve, Recently done, scheduled chats hidden, usage chips with calibrated limit, ideas, flat reorderable list with project hues, public repo with scrubbed history.

## 2026-11-08 missing chats and post-reboot flood
- Cause of a missing chat: Windows MAX_PATH. Claude scratch-chat project folders are ~220 chars, so `<folder>\<uuid>.jsonl` hits 261 and `os.stat`/`open` fail. All transcript stat/open go through `inbox.lp()`. Folder paths themselves are still under 248, so `glob` works; if Claude ever makes deeper folders, glob would need the prefix too.
- "Clear" in the Claude app starts a new CLI transcript in the same desktop session; the old ids go in `priorCliSessionIds`. Those are hidden (`SUPERSEDED`), never if they are some chat's current id.
- Late-discovered chats: `collect_sessions` stores `last_scan_at` (at most once a minute); a never-seen chat whose activity is older than that minus `LATE_MARGIN` (600 s) gets a read_state baseline. New chats made while the app was off still appear. Codex threads synced in from elsewhere with old timestamps would also be baselined (accepted).
- The flood Luis saw (19 after reboot, ~5 expected) came from fix (1) going live on reboot before (2)/(3) existed. `tools/baseline_read.py` (dry run unless `--apply`; stop the app first) marked the 5 old ones read; backup of the previous file at `%TEMP%
ead_state.before-baseline.json` (temporary).
- Reboot: task "Chat Inbox" logon trigger worked on 2026-11-08 (logon 15:36:19, server 15:36:27). Done writes both a decision and read_state, so the working -> interrupted state flip after a reboot does not resurrect done chats (simulated with `boot_time` patched: same 10 to-dos).

## Open items and ideas (not built)
- Cloud or phone view of the list (paused; hosting and access undecided); cloud and remote sessions.
- Rust/Tauri packaging (not needed for speed).
- Reboot: startup and done-state persistence verified 2026-11-08 (see above); tray badge pixels and window position after reboot not checked.
- Verify in the real apps: new-chat deep links with prefill, taskbar badge, toasts; verify Claude counts against the Claude sidebar.
- No known deep link to open a T3 chat.
- Google Keep sync: parked (only Google Tasks is a clean API; nothing is frictionless).
- Real plan percentages instead of estimates; Codex limit calibration.
- Feature ideas Luis liked: keyboard shortcuts (J/K, E done, P pin, N new idea, Enter open), usage meter in the header with reset countdown, quick filters (Needs you / Working / Unread), "finished" notification, Space-bar quick peek, idea folders and "turn last answer into idea".
- Housekeeping: add a LICENSE (Luis's choice) and a fuller README for the public repo; delete the old stash `stash@{0}` ("pre-simple-black local changes" on main) when sure; `chat-inbox-mod/` status unknown.

## Rules and gotchas
- Repo is PUBLIC: never commit chat contents, real titles, tokens, cookies, local runtime data, or personal links/paths. Screenshots in `notes/screenshots/` must stay synthetic.
- Do not commit or push without Luis's yes (he usually says "Commit" or "Commit and push" after each feature). Handoff/status docs may be committed and pushed automatically per his global rules.
- `AGENTS.md` and `CLAUDE.md` have local uncommitted lines pointing at a private hub. Do not commit them (use `git add` with explicit paths, never `git add -A`).
- In the bash tool, large heredocs containing quotes can break; write patch scripts to a file (scratchpad) and run them. When replacing text in a file with an inserted copy of the same text, anchor `str.index` carefully (an earlier patch cut the wrong block).
- Resetting a catalog setting while the app runs can be undone by the running (old) process within 2 s; restart first, then reset.
- The server refreshes its cache every 2 s; the page polls every 5 s. Actions patch the cache instantly and persist on a writer thread (`_QUEUE`). `render()` in `app.js` returns early when its signature is unchanged; include any new visible state in that signature.
- Hooks, other tools or other chats' servers may hold port 8765 (a poster tool did once and caused 501 errors).
- Tell Luis what is unverified; do not claim the real Claude/Codex apps accepted deep links.
