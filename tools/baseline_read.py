"""Mark chats as already read at their current activity (not "Done", so they don't count as done today).

One-off repair for chats that suddenly became visible (for example after a scanner fix) and flooded the
to-do list. They stay under All chats and return to the to-do list on new activity.
Stop the app first so it does not write read_state.json at the same time.

    python tools/baseline_read.py <chat-id-prefix> [...]          # dry run
    python tools/baseline_read.py --apply <chat-id-prefix> [...]
Set AGENT_MANAGER_DATA_DIR to work on a copy.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import inbox  # noqa: E402

apply = "--apply" in sys.argv
prefixes = [a for a in sys.argv[1:] if a != "--apply"]
items = inbox.collect_sessions()
state = inbox.load_state()
for src, sid, title, cwd, mt, last, role in items:
    if any(sid.startswith(p) for p in prefixes):
        version = max(mt, inbox.HOOKS.get(sid, {}).get("timestamp", 0))
        print(("mark read: " if apply else "would mark read: ") + sid)
        state[sid] = max(state.get(sid, 0), version)
if apply:
    inbox.save_state(state)
