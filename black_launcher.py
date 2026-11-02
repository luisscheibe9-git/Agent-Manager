"""Launch this branch using the original checkout's durable data when in a worktree."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def data_directory(source=ROOT, environ=None):
    environ = os.environ if environ is None else environ
    if environ.get("AGENT_MANAGER_DATA_DIR"):
        return Path(environ["AGENT_MANAGER_DATA_DIR"]).resolve()
    try:
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        result = subprocess.run(["git", "-C", str(source), "worktree", "list", "--porcelain"],
                                capture_output=True, text=True, encoding="utf8", errors="replace",
                                timeout=3, check=True, **flags)
        first = next(line[9:] for line in result.stdout.splitlines() if line.startswith("worktree "))
        primary = Path(first)
        if primary.is_dir():
            return primary.resolve()
    except (OSError, subprocess.SubprocessError, StopIteration):
        pass
    return Path(source).resolve()


def configure():
    data = data_directory()
    os.environ.setdefault("AGENT_MANAGER_DATA_DIR", str(data))
    os.environ.setdefault("AGENT_MANAGER_LABEL", "Chat inbox")
    os.environ.setdefault("AGENT_MANAGER_PROFILE_DIR", str(data / "data/black-chrome-profile"))
    return data


if __name__ == "__main__":
    data = configure()
    runtime = data / ".venv" / "Scripts" / ("pythonw.exe" if sys.executable.lower().endswith("pythonw.exe") else "python.exe")
    if "--describe" not in sys.argv and runtime.is_file() and Path(sys.prefix).resolve() != (data / ".venv").resolve():
        subprocess.Popen([str(runtime), str(ROOT / "black_launcher.py"), *sys.argv[1:]], cwd=ROOT)
        sys.exit()
    if "--describe" in sys.argv:
        print(json.dumps({"source": str(ROOT), "data": str(data), "profile": os.environ["AGENT_MANAGER_PROFILE_DIR"]}))
    else:
        runpy.run_path(str(ROOT / "tray.py"), run_name="__main__")
