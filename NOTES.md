# Chat Inbox (Agent Manager): handoff notes

## CURRENT STATE (2026-11-05) - read this block first
- What: Windows tray app + local dashboard at http://localhost:8765 that turns Luis's Claude and Codex chats into a to-do list. Repo (PUBLIC): https://github.com/luisscheibe9-git/Agent-Manager. Checkout: `%USERPROFILE%\Desktop\Chat_Inbox`, branch `codex/simple-black` (main is fast-forwarded to it after pushes). Commit author email is his personal address (set in repo git config; never use the Cal Poly address).
- Full detail, run/restart/test steps, decisions, open items and gotchas: `notes/HANDOFF.md`. Paste-ready prompt for a new chat: `notes/NEW_CHAT_PROMPT.md`. The sections further down are chronological history and may be outdated (for example the old "opening a chat clears it" rule and old machine paths).
- Behavior in one paragraph: only Done resolves a chat (new activity brings it back); T3 chats, scheduled/automated chats and snoozed chats are kept off the list; flat list with a project label above each chat, each project has one saved tint; drag the grip to reorder; down arrow sends a chat to the bottom; chips show tokens, context % and an estimated "Limit %"; ideas ("+ New to-do") become thin rows you can turn into Claude/Codex chats; blue banner shows T3 Code's unresolved threads; Recently done and Snoozed blocks sit under the list; toolbar is behind a small triangle; header shows "N done today".
- Run: Task Scheduler task "Chat Inbox" runs `pythonw tray.py` (Python313). Tests: `python -X utf8 -m unittest test_inbox test_dashboard test_todo test_t3_sessions test_black_launcher` (57 pass).
- Rules: repo is public (no private data); do not commit/push without Luis's yes (docs excepted); never mutate his real list while testing; do not commit his local AGENTS.md/CLAUDE.md edits.
- 2026-11-08 scanner fixes (uncommitted until Luis says): (1) transcripts whose full path is >= 260 chars (Claude scratch chats, e.g. a long-lived pinned chat that is cleared often) were silently skipped; `inbox.lp()` adds the `\\?\` prefix. (2) Earlier transcripts of a cleared (/clear) desktop chat, listed in the session JSON's `priorCliSessionIds`, are hidden (`inbox.SUPERSEDED`). (3) A chat seen for the first time whose activity is older than the previous scan (`last_scan_at` catalog setting, minus 10 min) is baselined as read so scanner fixes don't flood the list. The 5 old long-path chats already surfaced were marked read once with `tools/baseline_read.py` (not Done). Reboot check: logon task starts the server ~8 s after sign-in; simulated reboot keeps the same to-do set.
- Next: see "Open items" in `notes/HANDOFF.md` (keyboard shortcuts, usage meter, quick filters, reboot test, deep-link verification, LICENSE/README, cloud view parked).

---
(older notes below)


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

## 2026-11-05 Per-chat usage on every row
- Each row shows `<total tokens> tokens · <N>% of 5h usage` (`usageHTML` in `web/app.js`, `row.usage` from `dashboard.snapshot`). Total tokens = provider-reported total (includes cached input). The percentage is this chat's share of all token spend on this computer in the last 5 hours (Claude: input+output+cache creation; Codex: non-cached input+output; cache reads excluded), computed from 5-minute buckets in `telemetry.py` (`usage_buckets`, parser version 6). It is NOT the plan's 5-hour limit percentage: neither Claude nor Codex logs expose that locally (Codex `rate_limits` is null here). If Anthropic/OpenAI usage endpoints become usable, replace the share with real limit percent. Not committed.

## 2026-11-05 Usage chips revised (supersedes the earlier "share of 5h" wording)
- Row chips (`usageHTML`, `.chip` styles): purple `<tokens> tok` (provider total, compact), teal `ctx N%` (context_tokens / window), orange `5h N%` (estimated % of the 5-hour limit used by this chat in the last 5 hours).
- 5-hour limit is an ESTIMATE: `dashboard.five_hour_limit()` = busiest rolling 5-hour spend seen in the last 14 days per provider (Claude: input+output+cache creation; Codex: non-cached input+output; cache reads excluded), floor 1M tokens. Currently about 2.5M (Claude) / 2.4M (Codex). Override with Settings > "5-hour limit estimate" (`five_hour_limit_tokens`, 0 = automatic). Exposed as `limits` in `/api/state`.
- Context window: Codex reports it; Claude is assumed 200K, or 1M when the model name has "1m" or usage exceeds 200K (`dashboard.context_window`). Parser version 7 (14-day buckets). 48 tests pass. Not committed.

## 2026-11-05 Cards, limit calibration, ideas
- Row layout: removed the status/project/branch line and the Preview/Details row. Card = status dot + title + three chips + Pin/Done, then a 4-line preview with the timestamp overlaid bottom-right (`.snippet-wrap`, `.stamp`). Branch/PR "context" UI is gone from the page (API `/api/context` remains).
- 5-hour limit (Claude Team Standard seat = 1.25x Pro per session per Anthropic's support page; no absolute token numbers are published): `telemetry.note_limit_hit` records "You've hit your session limit · resets 2am" messages; `dashboard.five_hour_limit` takes the median cost-weighted spend in the 5 hours before each hit (currently 5 hits, about 22.6M weighted units); with no hits it falls back to the busiest 5 hours. Units are cost-weighted (Claude: input + 5x output + 1.25x cache creation + 0.1x cache read; Codex: uncached input + 0.1x cached + 8x output) in `telemetry.py`. Buckets are kept 60 days; parser version 9. Codex still uses its busiest 5 hours (no limit-hit calibration). Settings override remains.
- Ideas: green "+ New to-do" button (header) adds a chat-looking text card under an "Ideas" heading (above the chats). Stored in catalog setting `ideas` ({id,text,created_at,sent}); API actions `idea-add/update/delete/sent` (cache-patched, persisted by the writer thread). Buttons "Claude chat", "Claude Code", "Codex" copy the text to the clipboard and open `claude://claude.ai/new?surface=chat&source=desktop_action&q=`, `claude://code/new?q=`, `codex://threads/new?prompt=` (params found in each app's asar; prefill not yet verified in the real apps; very long text may be truncated by the app, clipboard has all of it). Sent ideas stay, labeled "Sent to X".
- 49 tests pass. Not committed.

## 2026-11-05 Ideas as compact rows
- "+ New to-do" opens a composer (textarea + green check). Enter (Shift+Enter for a new line) or the check adds the idea; Esc/x cancels; an empty composer adds nothing. Each idea then shows as a thin row (purple dot, first line as title, "Idea" chip, time, "Sent to X" once used) in the "Ideas" block above the chats. Click a row to expand it: editable text, "Make this a chat" buttons (Claude chat, Claude Code, Codex) and delete. Multiple ideas supported. Code: web/app.js (composerHTML, ideaHTML, 
enderIdeas), web/styles.css (.idea*).

## 2026-11-05 Snooze, reorder, done today, collapsed toolbar, Limit chip
- Snooze: each card has Snooze > 1 hour / 1 day (snooze/unsnooze actions; catalog setting snoozes {id: epoch}; row field snoozed_until). Snoozed chats leave the to-do list, badge and reminders until the time passes, then return on their own; a collapsed "Snoozed" block under the chats lists them with "Wake now".
- Ideas can be reordered by dragging their rows (idea-reorder action; HTML5 drag in web/app.js).
- Header shows "N done today" (local midnight, from done_at). The search/project/All chats/Mark all done/Settings row and the summary are hidden behind a small triangle next to the badge (#toolbar-panel, #toolbar-toggle, remembered in localStorage lack-inbox-panel; closing it resets search/project/All chats; / opens it and focuses search).
- The orange usage chip now reads "Limit N%" (tooltip still explains it is an estimate of the 5-hour limit).
- 52 tests pass. Not committed.

## 2026-11-05 Flat list with project labels; drag to reorder chats
- The to-do list is no longer grouped: every chat card has its project name as a small label above it, in one flat list (pinned first). The "Group by project" footer checkbox was removed (setting `group_by_project` is now unused).
- Chats can be dragged by the dotted grip at the left of the card. Manual order is stored in catalog setting `chat_order` (action `chats-reorder`, `dashboard._reorder_chats/_patch_order/_merge_order`); rows expose `order` (-1 = never placed). Sort: pinned, then `order`, then newest; chats you never placed (including new ones) appear above placed ones. Working chats still render in the "Working" block at the bottom. `web/app.js` keeps the dropped order for 6 s so an in-flight poll cannot undo it (`orderOverride`).
- 53 tests pass. Not committed.

## 2026-11-05 Down arrow, project hues, handoff
- The card's Snooze button was replaced by a down arrow (`data-action="to-bottom"`) that sends the chat to the bottom of the manual order (`commitOrder` in `web/app.js`; pinned chats show "Pinned chats stay at the top. Unpin it first."). Snooze backend and the Snoozed block remain.
- Project hues: every project (key = normalized cwd) gets one saved hue in catalog setting `project_colors` (`dashboard.project_hues`; 24 hues; new projects take the unused hue farthest from those in use, most recent projects first). Rows expose `hue`; `.row.hued` styles tint card, border and label (`web/styles.css`); needs/working still blend red/green on top.
- Wrote `notes/HANDOFF.md` and `notes/NEW_CHAT_PROMPT.md`; added the CURRENT STATE block above. 54 tests pass.
