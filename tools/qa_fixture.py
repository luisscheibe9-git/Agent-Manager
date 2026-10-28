"""Reproducible UI scenarios; writes only under the ignored notes/qa-data folder."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def prepare():
    root = ROOT / "notes/qa-data"
    home = root / "home"
    data = root / "app"
    data.mkdir(parents=True, exist_ok=True)
    project = root / "Orion"
    project.mkdir(exist_ok=True)
    if not (project / ".git").exists():
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        (project / "README.md").write_text("Fixture project\n", encoding="utf8")
        subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixture baseline"], cwd=project, check=True)
    (project / "README.md").write_text("Fixture project\nA change for context testing.\n", encoding="utf8")
    second = root / "Atlas"
    second.mkdir(exist_ok=True)
    home.joinpath('.codex/sessions').mkdir(parents=True, exist_ok=True)
    index = []
    ids = {}
    cases = [
        ("working", "Build the project dashboard", project),
        ("needs", "Choose the deployment target", project),
        ("unread", "Review the API changes", second),
        ("read", "Clean up the sidebar layout", second),
        ("settled", "Last month's archived research", second),
        ("pinned", "Keep the release checklist handy", project),
        ("interrupted", "Resume interrupted build", project),
        ("unicode", 'Résumé & 東京 <script>alert("no")</script>', second),
    ]
    now = time.time()
    for i, (key, title, cwd) in enumerate(cases):
        sid = f"f1234567-0000-0000-0000-{i+1:012d}"
        ids[key] = sid
        index.append({"id": sid, "thread_name": title})
        rows = [
            {"type": "session_meta", "payload": {"id": sid, "cwd": str(cwd), "source": "vscode", "git": {"branch": "feature/dashboard"}}},
            {"type": "event_msg", "payload": {"type": "task_started", "model_context_window": 200000}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": title}]}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 24000, "cached_input_tokens": 18000, "output_tokens": 5200, "reasoning_output_tokens": 1200, "total_tokens": 29200}, "last_token_usage": {"total_tokens": 13000}, "model_context_window": 200000}}},
        ]
        if key == "needs":
            rows.append({"type": "response_item", "payload": {"type": "function_call", "name": "request_user_input_async", "call_id": "fixture-question", "arguments": "{}"}})
        if key not in ("working", "needs", "interrupted"):
            rows.extend([
                {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer", "content": [{"type": "output_text", "text": "The fixture work is complete.\n\n• Project list and filters are ready.\n• Read state is saved.\n\nThis is synthetic test data, not a real agent answer."}]}},
                {"type": "event_msg", "payload": {"type": "task_complete"}},
            ])
        path = home / '.codex/sessions' / (sid+'.jsonl')
        path.write_text('\n'.join(json.dumps(row) for row in rows)+'\n', encoding='utf8')
        if key in ("settled", "pinned", "interrupted"):
            os.utime(path, (now-45*86400, now-45*86400))
    (home / '.codex/session_index.jsonl').write_text('\n'.join(json.dumps(row) for row in index), encoding='utf8')
    marks = {sid: now+1 for key,sid in ids.items() if key not in ('unread','needs','unicode')}
    (data / 'read_state.json').write_text(json.dumps(marks), encoding='utf8')
    (data / 'pins.json').write_text(json.dumps({ids['pinned']:True}), encoding='utf8')
    import inbox
    from catalog import Catalog
    with Catalog(str(data / 'chat_catalog.sqlite3')) as db:
        db.set('preferences', {'reminders_enabled':False,'reminder_delay_seconds':60,'keep_taskbar':True,'settle_days':7,'group_by_project':True})
    (root / 'ids.json').write_text(json.dumps(ids,indent=2),encoding='utf8')
    print(json.dumps({'home':str(home),'data':str(data),'port':8877}))


if __name__ == '__main__':
    prepare()
