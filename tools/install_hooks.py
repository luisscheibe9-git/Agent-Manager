"""Idempotently add only Agent Manager's observers, preserving other Claude settings."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ("UserPromptSubmit", "Stop", "StopFailure", "Notification", "PermissionRequest",
          "PreToolUse", "PostToolUse", "PostToolUseFailure", "SessionEnd", "Elicitation", "ElicitationResult")


def install(path, python=sys.executable):
    path = Path(path)
    settings = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    command = f'"{Path(python).as_posix()}" "{(ROOT / "tools/claude_hook.py").as_posix()}"'
    hooks = settings.setdefault("hooks", {})
    for event in EVENTS:
        entries = hooks.setdefault(event, [])
        preserved = []
        for entry in entries:
            remaining = [h for h in entry.get("hooks", []) if "/tools/claude_hook.py" not in h.get("command", "").replace("\\", "/")]
            if remaining:
                preserved.append({**entry, "hooks": remaining})
        entries[:] = preserved
        entry = {"hooks": [{"type": "command", "command": command, "timeout": 3}]}
        if event == "Notification":
            entry["matcher"] = "permission_prompt|idle_prompt|elicitation_dialog"
        if event == "PreToolUse":
            entry["matcher"] = "AskUserQuestion|ExitPlanMode"
        entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".agent-manager.bak")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    temp = path.with_name(path.name + ".agent-manager.tmp")
    temp.write_text(json.dumps(settings, indent=2), encoding="utf8")
    temp.replace(path)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", default=str(Path.home() / ".claude/settings.json"))
    args = parser.parse_args()
    print("Installed fail-open lifecycle observers in", install(args.settings))
