# Agent Manager: simple black to-do list

Updated 2026-10-30. Branch: codex/simple-black. Read this first.
Source: C:/Users/Luis/.codex/worktrees/simple-black/agent manager.
Remote: https://github.com/luisscheibe9-git/Agent-Manager .

## Goal and behavior
Luis wants a simple reliable to-do list of chats outside T3 Code, with a separate T3 section. Opening a chat or clicking Done clears it; All chats offers Return to to-do. Clearing never deletes the saved chat, transcript, pin or T3 data. Routine tool/token progress stays cleared; a new turn, reply or question returns it. Mark all done also clears working/pending rows, without answering provider questions. T3-managed chats, including imports, are excluded from the badge/reminders and have informational rows without an unverified T3 deep link.

## Key files
- inbox.py: HTTP server/source scans; parser cache version3; durable read/pin files.
- telemetry.py: lifecycle/tokens and semantic attention_sequence.
- dashboard.py: snapshots, persisted todo_decisions, settings/reminders/context.
- t3_sessions.py: bounded read-only SQLite scan of ~/.t3/userdata/statev2.sqlite (legacy state.sqlite fallback). AGENT_MANAGER_T3_DB overrides. Exact provider-qualified native IDs from nativeThreadRef, legacy mappings, runtime cursors and importedTranscripts; never match titles/folders/internal T3 IDs. Includes WAL. Corrupt/locked/unsupported metadata fails open with a warning.
- catalog.py: saved catalog/settings. Done binds to semantic attention, not file mtime.
- web/: compact black To-do, All chats recovery, separate collapsible T3 section.
- tray.py: badge/mark-all use dashboard semantics.
- black_launcher.py: resolves primary checkout data from worktree; explicit overrides win.

## Running and preserved versions
Live8765 runs this black branch with shared data D:/agent manager. Latest verification: PID37804;17saved chats retained,9todo,2T3;0missing IDs; saved read/pin files unchanged. Existing browser windows may need F5 once.
Desktop/Downloads Agent Manager.lnk targets this checkout's black_launcher.py --open. Do not archive this worktree while shortcuts target it.
Windows sign-in shortcut STILL points to BLUE D:/agent manager/tray.py. Earlier automatic approval review rejected changing it before execution. Do not claim startup changed.
Blue source/uncommitted cloud work remain untouched at D:/agent manager on main. Cloud work paused; black has no sync worker.

## Run and verify
Bundled Python: C:/Users/Luis/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe. Plain python is a Store stub. Node is sibling dependencies/node/bin/node.exe.
Run: python black_launcher.py --open. Inspect: python black_launcher.py --describe.
Tests: python -m unittest -q test_inbox test_dashboard test_black_launcher test_t3_sessions test_todo
JS: node --check web/app.js
43tests pass. See notes/TEST_REPORT.md for interactive checks and limits.
tools/inspect_t3.py --summary reads mapping metadata and counts saved matches.

## Safe QA
Mutation tests use port8878 and ignored notes/qa-data/home and notes/qa-data/app. Set AGENT_MANAGER_HOME, AGENT_MANAGER_DATA_DIR, AGENT_MANAGER_PORT=8878, AGENT_MANAGER_LABEL before launching.
tools/qa_fixture.py resets synthetic fixtures; tools/qa_update.py appends lifecycle/token events; tools/qa_t3.py add/remove/unavailable/restore changes only synthetic T3 metadata. Never run mutation tests on production state.
Screenshots notes/screenshots/todo-*.jpg contain synthetic data only.

## Git and next steps
Luis explicitly authorized pushing the remaining To-do/T3 changes on 2026-11-02. The tested milestone is committed on codex/simple-black; blue/cloud changes in the primary checkout remain separate and paused.
Next: continue product changes from this branch. Real reboot and provider deep-link handoff remain verification gaps.
Limits: installed-app deep-link handoff, native badge/toast pixels and real reboot unverified. Browser policy blocked codex:// navigation during QA; click-to-clear still persisted and was observed.

Phone deliverables: Downloads/Agent-Manager-Todo-T3-Preview.jpg and Agent-Manager-Todo-T3-Test-Report.md. Original small synthetic screenshot: notes/screenshots/todo-phone-preview.jpg.

## Launch repair — 2026-11-02
The app failed silently because Codex's shared Python runtime no longer contained pystray. Created D:/agent manager/.venv with requirements.txt; keep it ignored. black_launcher.py now hands off to that environment when invoked by the shared runtime. Desktop, Downloads and Startup Agent Manager.lnk now target D:/agent manager/.venv/Scripts/pythonw.exe and this checkout's black_launcher.py (Desktop/Downloads use --open). Startup now uses black, superseding the older blue-startup warning above. install-startup.ps1 defaults to the primary checkout's .venv. Rebuild environment using bundled python -m venv 'D:/agent manager/.venv', then .venv/Scripts/python.exe -m pip install -r requirements.txt. This environment still requires its base Python installation to remain installed.
Verified native Chrome inbox visibly open, health version2 PID27104, 15 currently discovered saved chats,9to-dos,2T3; all43 regression tests pass. No chat states were cleared during repair. Original blue/cloud work remains paused and untouched except ignoring .venv. Desktop/Downloads shortcut filename: Agent Manager.lnk.


## 2026-11-02 Speed fix (branch codex/simple-black)
- Cause of slow pin/done: each click did a full log scan (~1s, mostly opening ~140 files) inside the global lock, then the UI awaited another full scan. Rust was not needed.
- Now: `dashboard.start_refresher()` (called by `tray.py`) rescans in a background thread every ~2s; `/api/state` serves `cached_snapshot()`. `dashboard.action` no longer scans or takes `DATA_LOCK`: it patches the cached row immediately and a writer thread persists (`_apply`). `_GEN` discards scans that started before an action. `web/app.js` updates optimistically (`optimistic()`/`pending` overrides for 8s).
- Tests/one-shot tools never start the refresher, so `action` saves synchronously there. Measured pin/read: 5-40 ms (was 1-3 s). 43 tests pass.

## 2026-11-03 Duplicate window at startup
- Cause: `tray.py` `open_minimized()` launched a new Chrome `--app` window on every tray start without checking for an existing one (and Chrome can restore a saved copy of the window next to it), so restarts/logins left 2-3 "Chat inbox" windows. The mutex already prevented duplicate tray processes.
- Fix: `open_minimized()` skips if a window exists; 10 s after launching, `taskbar.close_extra_windows()` closes any extras (`taskbar.find_windows()` returns all). Verified: 3 windows -> 1, two further restarts stay at 1. Not committed.

## 2026-11-04 Dead link, titles, persistence
- Dead title link: Claude chats started in T3 Code (cwd `~/.t3/scratch/...`) have no desktop-app session file, so `href_for` has no `claude://` link. Now their title is a link that POSTs `/api/resume`, which opens a PowerShell window running `claude --resume <id>` in the chat's folder (`dashboard.resume`, id validated, Claude rows only) and marks it done.
- Titles: `inbox.clean_title()` skips `[File: ...]` placeholders, Codex `# Files mentioned...`/`## My request:` blocks, `<t3_context>` tails; Codex scan skips the `# AGENTS.md instructions` preamble; `app_title()` ignores app/custom titles that are only placeholders. Parser version is now 5 (cache rebuilds once).
- Done persistence verified: restarting the tray keeps 150 read / 15 to-do unchanged. Added `dashboard.flush()` so queued clicks are written before a graceful quit/restart. Hard kills can lose a click made <1 s earlier.
- Tests: 45 pass (`python -X utf8 -m unittest test_inbox test_dashboard test_todo test_t3_sessions test_black_launcher`).

## 2026-11-04 Recently done section
- Done decisions now store `done_at` (in `todo_decisions`); snapshot rows expose `done_at` (0 if not done or done before this feature). Mark-all keeps the original `done_at` of already-done chats.
- UI: open-by-default "Recently done · N" box above the list (`#recent-done` in `web/index.html`, `doneHTML()` in `web/app.js`): chats done in the last 7 days, newest first, max 15, with a "↶ To-do" undo. Respects search/project filters. `RECENT_DAYS`/`RECENT_MAX` constants in app.js. Chats marked done before this change do not appear.
- 46 tests pass. Not committed.

## 2026-11-04 T3 chats out of the main feed
- T3 chats (`managed_by_t3`) now also include any chat whose folder is under `~/.t3/` (`dashboard.T3_PATH`), since those cannot be opened from here. They are excluded from the main list, the badge, and reminders.
- UI: a large amber banner at the very top ("N unresolved T3 Code chats"; `#t3-section` in `web/index.html`) expands to the unresolved ones, each with a Done button (resolve = mark done). Hidden when none. The banner count ignores search/project filters. The earlier resume-in-terminal link therefore no longer applies to T3 scratch chats (Claude Desktop's own `scratch-workspaces` chats are not T3 and stay in the feed). Not committed.

## 2026-11-05 Scheduled/automated chats hidden from to-do
- Rows get `automated: true` when they were not started by Luis: Claude app sessions with `scheduledTaskId` (unless `scheduledRunContinued`, i.e. he replied), Codex threads whose `thread_source` is not `user`/`voice_chat` (guardian, subagent, agent-created) or `source == exec`. Stored in `DETAILS[sid]["automated"]` (inbox.py scan_claude/scan_codex). Excluded from the to-do list, badge, counts, Recently done and reminders; still visible under "All chats". Currently 18 Claude chats flagged. Not committed.
- How to-do works: a chat is on the list until marked done (Done button, opening it from its link, Resume, or Mark all done); new activity after done (new answer, turn or question) puts it back; working/needs-input chats also count until done.

## 2026-11-05 T3 banner now mirrors T3 Code's own unsettled list
- Bug: the banner counted every T3-linked chat not marked done here (33). Now `t3_sessions.unresolved_threads()` reads T3's `orchestration_v2_projection_threads.payload_json` (live, not archived, not settled via `settledOverride`/`settledAt`/`unsettledAt`, not snoozed) and `/api/state` returns it as `t3.unresolved`; `web/app.js` renders the banner and its list from that. Today: 6 (T3 shows ~5; one is "Read T3 Code Thread"). Banner rows are informational (no Done button, no link).
- Gotcha found 2026-11-05: another session's `Senior Project/poster/tools/receive_server.py` (python 3.14, PID 49296) also listens on port 8765. Windows allowed the duplicate bind, so some requests hit that process (501 on GET) and the inbox looks broken. Stop it or give it another port; consider making the inbox bind exclusive. Not committed.

## 2026-11-05 Only Done resolves; bigger Done; green resolve animation; UI polish
- Resolve rules: a chat leaves the to-do list only via Done (or Mark all done). Opening a chat link, the terminal-resume link and focusing the chat in the Claude app no longer count. `dashboard.snapshot()` now uses `inbox.load_state()` instead of `merged_state()` (which folded in the app's `lastFocusedAt`); `freeze_focus_reads()` runs once (catalog flag `focus_reads_frozen`) so chats that were read only through focus stay read instead of flooding back. New activity after Done still returns a chat to to-do.
- UI: `web/styles.css` rewritten (rounded cards, Apple-like palette, 42px green Done button, ghost Pin button, blur dialog/toast, mobile layout). Resolve animation: `app.js` adds `.resolving` (green tint, check pop, glide-out and height collapse, 520 ms, transform/opacity/height only) before posting; skipped under `prefers-reduced-motion`. Recently done list scrolls after 340 px.
- Verified in a throwaway copy on port 8791 (copied data dir), then restarted the real app. 47 tests pass.

## 2026-11-05 Terminal-resume removed; auto-reload; open ideas
- Removed the "open terminal to resume this chat" feature (`dashboard.resume`, `/api/resume`, the title link, its test). Chats without a deep link now show a plain title.
- `/api/state` now returns `build` (newest mtime in `web/`); `web/app.js` reloads itself when it changes, so open windows pick up new versions after a restart. A window opened before this change needs one Ctrl+R.
- Restart check: 209 chats, 171 read, 3 to-do, 2 pinned identical before and after.
- Open ideas from earlier notes (not built): owner-only cloud/phone view of the last synced list (paused; blue work in `D:/agent manager` on main; hosting/access undecided, GitHub Pages familiar); cloud and remote sessions (old roadmap #6); Rust/Tauri desktop packaging; real Windows reboot test (tray, badge, pins, done state); verify claude:// and codex:// deep links end-to-end and the native badge/toast; verify Claude counts against the app sidebar; verified T3 deep link (none known); `chat-inbox-mod/` Claude Code pane status; merge `codex/simple-black` into `main` and push (6+ commits unpushed); the git stash "pre-simple-black local changes" still holds earlier uncommitted edits to `main`.

## 2026-11-05 Layout tweak
- T3 banner is about half as tall and blue (`.t3-section` in `web/styles.css`). "Recently done" moved below the chat list (`web/index.html`) and is larger (19px heading, 16px titles, 560px scroll area). Open windows reload themselves via the `build` id. Not committed.

## 2026-11-05 Working chats last; public repo prep
- Working chats (not pinned) now render in their own "Working · N" block at the bottom of the to-do list (`web/app.js`).
- Prepared the repo for going public: removed a private Drive link from NOTES, made `chat-inbox-mod/hooks/register.tsx` portable (env `CHAT_INBOX_PYTHON`, `CHAT_INBOX_SCRIPT`, default `python` and `~/Desktop/Chat_Inbox/inbox.py`), rewrote commit author email to Luis's personal address.

## 2026-11-05 Repo is PUBLIC
- https://github.com/luisscheibe9-git/Agent-Manager went public on 2026-11-05 (history rewritten first: author/committer email is now luis.scheibe9@gmail.com; repo-local `git config user.email` set to it). Audited: no secrets in any commit; screenshots in `notes/screenshots/` are synthetic.
- Rules from now on: never commit chat contents, real chat titles, tokens, cookies, `read_state.json`, `pins.json`, `chat_catalog.sqlite3`, `chrome_profile/`, or personal paths/links (all runtime data is gitignored). Old pre-rewrite commit hashes may stay fetchable on GitHub for a while.
- Local-only: `AGENTS.md`/`CLAUDE.md` have uncommitted "Related projects" lines pointing at a private hub; do not commit them.
