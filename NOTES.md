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

Phone deliverables: Downloads/Agent-Manager-Todo-T3-Preview.jpg and Agent-Manager-Todo-T3-Test-Report.md. Original small synthetic screenshot: notes/screenshots/todo-phone-preview.jpg. Private Drive preview: https://drive.google.com/file/d/1wa_OlDy3zkGlDUacw1wRYFnsnNBrVRZ1/view?usp=drivesdk . No public permissions added.

## Launch repair — 2026-11-02
The app failed silently because Codex's shared Python runtime no longer contained pystray. Created D:/agent manager/.venv with requirements.txt; keep it ignored. black_launcher.py now hands off to that environment when invoked by the shared runtime. Desktop, Downloads and Startup Agent Manager.lnk now target D:/agent manager/.venv/Scripts/pythonw.exe and this checkout's black_launcher.py (Desktop/Downloads use --open). Startup now uses black, superseding the older blue-startup warning above. install-startup.ps1 defaults to the primary checkout's .venv. Rebuild environment using bundled python -m venv 'D:/agent manager/.venv', then .venv/Scripts/python.exe -m pip install -r requirements.txt. This environment still requires its base Python installation to remain installed.
Verified native Chrome inbox visibly open, health version2 PID27104, 15 currently discovered saved chats,9to-dos,2T3; all43 regression tests pass. No chat states were cleared during repair. Original blue/cloud work remains paused and untouched except ignoring .venv. Desktop/Downloads shortcut filename: Agent Manager.lnk.

