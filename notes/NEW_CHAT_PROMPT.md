# New chat starting prompt

Paste everything below the line into a new chat opened in `%USERPROFILE%\Desktop\Chat_Inbox`.

---

I'm continuing work on my Chat Inbox app (Windows tray app plus local web dashboard that turns my Claude and Codex chats into a to-do list). The repo is public at https://github.com/luisscheibe9-git/Agent-Manager and the folder is `%USERPROFILE%\Desktop\Chat_Inbox`.

Before doing anything:
1. `git fetch` and check `git status` and `git log --oneline -8`. The working branch is `codex/simple-black` (main mirrors it after pushes).
2. Read `NOTES.md` (the CURRENT STATE block at the top) and `notes/HANDOFF.md` in full. They list what exists, how to restart and test, decisions I made, open items, and gotchas.
3. The app is running now (Task Scheduler task "Chat Inbox", port 8765). Restart steps and the test command are in `notes/HANDOFF.md`.

Rules:
- The repo is public: never commit private info, real chat titles or contents, tokens, or local runtime data. Do not commit my local `AGENTS.md` and `CLAUDE.md` edits; stage files by explicit path.
- Do not commit or push unless I say so. After each finished feature, ask me with a proposed commit message. Handoff and status docs are fine to commit and push yourself.
- Never click Done, Snooze, reorder or delete on my real to-do list while testing. Test mutations on a copy of the data on port 8791 (instructions in the handoff) or undo anything you touch.
- Keep the UI simple, sleek and dark, with minimal chrome. Be terse, lead with the result, and tell me plainly what is unverified.
- Update `NOTES.md` and `notes/HANDOFF.md` after substantial changes, and run the tests before saying something works.

Things I might ask for next (pick up what I say, don't start these on your own): keyboard shortcuts, a usage meter in the header with a reset countdown, quick filters (Needs you / Working / Unread), a "finished" notification, a quick-peek panel, idea folders, restoring a snooze button, a LICENSE and a better README, a reboot test, and verifying the new-chat deep links in the real Claude and Codex apps.

Start by telling me, in a few lines, what state the repo and the running app are in and anything that looks off.
