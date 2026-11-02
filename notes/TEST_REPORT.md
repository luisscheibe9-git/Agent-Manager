# To-do and T3 verification

2026-10-30. Branch codex/simple-black. Synthetic browser QA at http://127.0.0.1:8878.

## Automated
43distinct tests pass: python -m unittest -q test_inbox test_dashboard test_black_launcher test_t3_sessions test_todo.
node --check web/app.js passes.
Coverage: durable catalog, lifecycle/pending requests, reminders, concurrency/API validation, launcher paths, provider-qualified T3 IDs, V2/legacy schemas, imports, deletion/archive, WAL live updates, missing/corrupt/locked metadata, Done/restore/pin preservation, progress staying cleared, new/identical replies returning, mark-all.

## Actual browser checks
All mutations used isolated8chat fixtures, never production read marks.
- Done removed a pending question and lowered badge, retaining provider needs-input state.
- Clicking Codex title persisted clearing and showed All done. Browser policy blocked external codex:// navigation; actual app launch unverified.
- All chats/Return to to-do restored row. Done hid working row.
- Appended token/commentary progress stayed cleared; completion returned automatically.
- Synthetic T3 remove returned original row; add restored separate membership.
- Corrupt T3 metadata showed warning and kept affected chats visible; recovery separated them again.
- Mark all done cleared main list while retaining T3 section.
- Graceful restart PID29180 to28312 retained8saved,0todo,1T3. Identical new completion returned1todo.
- T3 titles have no Codex/Claude links. Expansion survived progress.
-390x844 mobile scrollWidth390; application console errors empty.
Earlier black milestone also exercised pins, search/Unicode escaping, project grouping, previews, branch/PR context, preferences/reminders and offline recovery.

## Real read-only checks
Installed T3 metadata:2native mappings,2saved matches. Live graceful restart: PID37804,17saved,9todo,2T3, status ready. Before/after IDs:0missing; read_state.json unchanged and pins.json absent before/after. No source transcripts or T3 database changed.

## Evidence and limits
Synthetic screenshots: todo-t3-separated.jpg, todo-t3-unavailable.jpg, todo-all-done.jpg, todo-t3-overview.jpg, todo-t3-mobile.jpg under notes/screenshots. Older black-*.jpg cover earlier controls.
Installed-app launch was blocked by browser policy; click clearing was observed. Native badge/toast pixels and real reboot remain unverified. Existing browser windows may need F5; startup shortcut still targets blue.
