# Agent Manager

Compact black to-do list for local Codex/Claude chats. Open a chat or click Done to clear it; All chats lets you restore it. New meaningful activity returns it. T3-managed chats have a separate section and do not count toward the badge.

Read NOTES.md before continuing. Run python black_launcher.py --open or inbox.bat; this branch reuses primary checkout data. Blue source remains preserved at D:/agent manager.

T3 detection reads native-session metadata without changing T3; imported chats are included. Unreadable T3 metadata keeps chats visible.

Checks: python -m unittest -q test_inbox test_dashboard test_black_launcher test_t3_sessions test_todo (43tests); node --check web/app.js. Use D:/agent manager/.venv/Scripts/python.exe on this machine; system python is a Store stub.

Isolated QA scripts: tools/qa_fixture.py, tools/qa_update.py, tools/qa_t3.py. See NOTES.md for environment/path details. Evidence: notes/TEST_REPORT.md and notes/screenshots/todo-*.jpg.

Desktop, Downloads and Windows sign-in shortcuts launch the black app using its project Python environment.

