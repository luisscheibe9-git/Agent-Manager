# Black branch handoff

Read ../NOTES.md first. Active branch codex/simple-black in C:/Users/Luis/.codex/worktrees/simple-black/agent manager. Blue/cloud work is paused and preserved at D:/agent manager onmain.

Implementation and extensive isolated browser QA are complete for the first black milestone. See TEST_REPORT.md for exact26tests, actual UI checks,8screenshots and remaining OS/app-handoff/reboot limits.

Current QA app runs8878using this checkout's notes/qa-data/home and notes/qa-data/app, labelSimple black inbox · QA. Relaunched with black_launcher.py; it honors explicit QA environment overrides. Do not run qa_fixture.py against production data. tools/qa_update.py appends only fixture lifecycle/token events for live refresh checks.

Production8765still uses the blue checkout. Attempt to stop it gracefully and startblack was blocked before execution by automatic approval review. Asked Luis for explicit approval to activateblack/update startup and whether tocommit/push. Do not infer approval from the default selected options.

When activation is approved: use /api/control commandquit against8765, then launch black_launcher.py from this checkout. It discovers the primary repo via git worktree list and reusesD:/agent manager as data root; inspect --describe first. Update startup with install-startup.ps1 only after approval. Existing blue source remains preserved; no cloud sync code exists onblack. Verify shared chat IDs/pins/preferences survived and fresh root servesblack. Code commits require Luis's answer. Do not publish blue/cloud changes.
