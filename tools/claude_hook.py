"""Fail-open Claude lifecycle observer. Never returns an approval or blocks a turn."""
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent.parent


def main():
    try:
        raw = json.load(sys.stdin)
        event = {key: raw[key] for key in ("session_id", "hook_event_name", "notification_type", "tool_name", "cwd") if key in raw}
        event["observed_at"] = time.time()
        port = int(os.environ.get("AGENT_MANAGER_PORT", "8765"))
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/hook", data=json.dumps(event).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=0.4) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        folder = Path(os.environ.get("AGENT_MANAGER_DATA_DIR", ROOT)) / "hook_queue"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (str(uuid.uuid4()) + ".json")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(event), encoding="utf8")
        temporary.replace(target)
    except Exception:
        pass  # monitoring must never interfere with an agent


if __name__ == "__main__":
    main()
