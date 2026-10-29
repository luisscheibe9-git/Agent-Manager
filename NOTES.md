# Simple black inbox — agent handoff

Read this file first. Current branch: codex/simple-black. Workspace: C:/Users/Luis/.codex/worktrees/simple-black/agent manager.

Luis requested a separate branch returning to his original compact black inbox before further blue-dashboard work. Blue source and uncommitted cloud work remain untouched in D:/agent manager on main. Cloud publication was cancelled; no cloud files or sync client were imported into this branch. Branch starts from tested local backend commit1d95cfd; this restores the original visual concept without reverting persistence/status fixes.

Scope assumption pending Luis's optional clarification: local tray/badge, saved chat list, read/pin/search/new-chat links, inline previews, projects, green working/red needs-input, reminders, and optional inline branch/PR/token details. No sidebar, split inspector, command palette or cloud UI. Do not resume blue/cloud work until this simple version works well.

Key files: web/index.html, web/styles.css, web/app.js are the compact black frontend. inbox.py serves strict local APIs; dashboard.py handles state/settings/reminders/context; telemetry.py normalizes lifecycle/tokens; catalog.py persists chats; tray.py owns tray/taskbar and graceful controls. Backend tests: test_inbox.py and test_dashboard.py. Fixture generator: tools/qa_fixture.py creates only ignored notes/qa-data.

Use bundled Python C:/Users/Luis/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe and Node sibling dependencies/node/bin/node.exe. Plain python is a Store stub.

Current state: new frontend implemented; syntax/backend tests and interactive QA underway. Preview should use port8878 and isolated notes/qa-data/app, never production read state for mutation tests. Production8765 currently runs the blue app from original folder (last verified PID27636), syncing13chats to the already deployed owner-only cloud Site. Do not terminate it with old PID18892 authorization: that replacement is complete.

Next: complete actual browser interactions at desktop/390px, read/pin persistence, previews/inline details, needs state retained after read, project/search/group controls, settings, source metadata outage/restart/offline retention. Review screenshots and user scope reply; correct observed bugs. Keep NOTES.md current at milestones. No code commit/push without Luis's explicit approval. Branch creation was requested; commits were not.

## Verified black milestone — 2026-10-29
- Luis confirmed original scope and explicitly requested every feature be tested through computer use with screenshots. See notes/TEST_REPORT.md for precise results and limitations.
-26Python tests pass; JS syntax and diff checks pass. Actual UI verifies live needs→working→completed status updates; live tokens29,200→40,000 with Details kept open; read/pin/filter/group/preferences/settled controls; real read-only PR metadata; mobile fit; offline recovery. Eight JPEG screenshots saved in notes/screenshots/black-*.jpg.
- Fixed discovered Git change-count rendering bug (counts are strings). Added black_launcher.py and3tests so a separate branch reuses original durable data instead of silently baselining a new catalog. inbox.bat and startup installer target this launcher. It honors explicit data overrides and uses an ignored separate Chrome profile.
- QA graceful restart and quit/relaunch preserve8chats,2pins and settings; timed reminder notified marker remained1. Native OS badge/toast visuals, real app deep-link handoff, and real reboot remain explicit verification limits.
- Attempted production activation was rejected BEFORE execution by automatic approval review ('blocked by policy', no details). Blue remains running8765; black preview8878is isolated. Asked Luis for activation/startup approval and commit choice. Await actual replies; preselected options are not approval. No code committed/pushed.

## Commit authorization — 2026-10-29
Luis explicitly approved committing the black branch after asking what commit means. Commit locally only; code push was not approved. Activation/startup approval remains pending because Luis is on his phone and wants to review a working screenshot first. Local-path Markdown images failed to load on phone; try sending the screenshot as native inline image content before adding external hosting. Do not resume blue/cloud feature work for this image delivery fix.
