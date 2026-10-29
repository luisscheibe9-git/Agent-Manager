# Simple black inbox

Branch `codex/simple-black` restores Luis's compact, always-dark chat list. It keeps the tested local persistence/lifecycle backend. Previews and project/token details expand inline; there is no dashboard sidebar or cloud sync on this branch.

Read NOTES.md for scope, current QA state and continuation steps.

Run with the bundled Python interpreter: `pythonw tray.py --open`. Use inbox.bat on Luis's machine. Running again focuses the current instance. Quit/restart through the tray rather than stopping unrelated Python processes.

Check: `python -m unittest -q test_inbox test_dashboard` and `node --check web/app.js`.

For isolated QA, run `python tools/qa_fixture.py`; set AGENT_MANAGER_HOME to the generated home, AGENT_MANAGER_DATA_DIR to its app folder, AGENT_MANAGER_PORT=8878, and AGENT_MANAGER_LABEL=Simple black inbox · QA before launching tray.py. Paths in the fixture are relative to this checkout. Production chat data is kept in ignored SQLite/JSON files; do not overwrite it with fixtures.

The blue design remains in D:/agent manager on main, including its uncommitted cloud work. This branch does not replace that checkout.

Use `black_launcher.py` for this branch: it reuses the primary checkout's saved catalog when launched from a Git worktree. `inbox.bat` and `install-startup.ps1` already target it. An explicit AGENT_MANAGER_DATA_DIR override is always respected. `python black_launcher.py --describe` prints the resolved paths without launching the app. Native browser data is isolated under the ignored data/black-chrome-profile folder.

Verification:26Python tests and actual browser checks; see notes/TEST_REPORT.md and notes/screenshots/black-*.jpg. Activation of this branch as the running8765app is pending explicit approval because automatic review rejected the attempted switch.
