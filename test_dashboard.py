import concurrent.futures
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import dashboard
import inbox
from catalog import Catalog
import test_inbox
from tools.install_hooks import install


SID = test_inbox.SID


class DashboardTests(unittest.TestCase):
    write_events = test_inbox.InboxTests.write_events
    codex_rows = test_inbox.InboxTests.codex_rows

    def setUp(self):
        test_inbox.InboxTests.setUp(self)
        self.dir_patch = patch.object(inbox, "DATA_DIR", str(self.root))
        self.dir_patch.start()
        self.addCleanup(self.dir_patch.stop)

    def fixture(self, complete=True):
        self.write_events(self.log, self.codex_rows(complete))
        return dashboard.snapshot()["chats"][0]

    def test_read_pin_archive_restore_and_preferences(self):
        row = self.fixture()
        self.assertEqual(row["state"], "read")
        dashboard.action("read", {"id": SID, "read": False})
        self.assertEqual(dashboard.snapshot()["counts"]["unread"], 1)
        dashboard.action("pin", {"id": SID, "pinned": True})
        dashboard.action("archive", {"id": SID, "archived": True})
        self.assertEqual(dashboard.snapshot()["counts"]["total"], 0)
        dashboard.action("archive", {"id": SID, "archived": False})
        self.assertTrue(dashboard.snapshot()["chats"][0]["pinned"])
        dashboard.update_settings({"reminder_delay_seconds": 60, "keep_taskbar": False})
        self.assertEqual(dashboard.settings()["reminder_delay_seconds"], 60)
        self.assertFalse(dashboard.settings()["keep_taskbar"])

    def test_exact_working_to_needs_to_completed(self):
        self.fixture(False)
        dashboard.action("read", {"id": SID, "read": False})
        self.assertEqual(dashboard.snapshot()["counts"]["working"], 1)
        dashboard.hook({"session_id": SID, "hook_event_name": "PermissionRequest"})
        self.assertEqual(dashboard.snapshot()["chats"][0]["state"], "needs")
        dashboard.action("read", {"id": SID, "read": True})
        self.assertEqual(dashboard.snapshot()["chats"][0]["state"], "needs")
        dashboard.hook({"session_id": SID, "hook_event_name": "PostToolUse"})
        self.assertEqual(dashboard.snapshot()["chats"][0]["state"], "working")
        dashboard.hook({"session_id": SID, "hook_event_name": "Stop"})
        self.assertNotEqual(dashboard.snapshot()["chats"][0]["state"], "working")

    def test_long_running_turn_and_boot_interruption(self):
        self.fixture(False)
        old = time.time() - 4000
        os.utime(self.log, (old, old))
        with patch.object(inbox, "boot_time", return_value=old - 1000):
            self.assertEqual(dashboard.snapshot()["chats"][0]["state"], "working")
        with patch.object(inbox, "boot_time", return_value=old + 1000):
            self.assertEqual(dashboard.snapshot()["chats"][0]["state"], "interrupted")

    def test_async_question_survives_immediate_tool_ack_and_clears_on_reply(self):
        rows = self.codex_rows(False)
        rows.extend([
            {"type": "response_item", "payload": {"type": "function_call", "name": "functions.request_user_input_async", "call_id": "q1", "arguments": "{}"}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "q1", "output": '{"accepted":true}'}},
        ])
        self.write_events(self.log, rows)
        self.assertEqual(dashboard.snapshot()["chats"][0]["state"], "needs")
        rows.append({"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Yes"}]}})
        self.write_events(self.log, rows)
        self.assertEqual(dashboard.snapshot()["chats"][0]["state"], "working")

    def test_reminders_once_per_activity_and_persisted_across_connections(self):
        self.fixture()
        dashboard.action("read", {"id": SID, "read": False})
        calls = []
        now = time.time()
        self.assertEqual(dashboard.notify_due(lambda *x: calls.append(x), now), [])
        self.assertEqual(dashboard.notify_due(lambda *x: calls.append(x), now+179), [])
        self.assertEqual(dashboard.notify_due(lambda *x: calls.append(x), now+180), [SID])
        self.assertEqual(dashboard.notify_due(lambda *x: calls.append(x), now+1000), [])
        self.assertEqual(len(calls), 1)
        with Catalog(inbox.CATALOG) as db:
            self.assertEqual(db.db.execute("SELECT notified FROM reminders WHERE id=?", (SID,)).fetchone()[0], 1)
        dashboard.action("read", {"id": SID, "read": True})
        self.assertEqual(dashboard.notify_due(lambda *x: calls.append(x), now+2000), [])

    def test_reminders_disabled_archived_and_notification_failure_retry(self):
        self.fixture()
        dashboard.action("read", {"id": SID, "read": False})
        now = time.time()
        dashboard.notify_due(lambda *x: None, now)
        dashboard.update_settings({"reminders_enabled": False})
        self.assertEqual(dashboard.notify_due(lambda *x: self.fail(), now+500), [])
        dashboard.update_settings({"reminders_enabled": True})
        def fail(*_):
            raise OSError("Synthetic unavailable notification service")
        with self.assertRaises(OSError):
            dashboard.notify_due(fail, now+500)
        self.assertEqual(dashboard.notify_due(lambda *x: None, now+500), [SID])
        dashboard.action("archive", {"id": SID, "archived": True})
        self.assertEqual(dashboard.notify_due(lambda *x: self.fail(), now+1000), [])

    def test_token_breakdown_and_branch(self):
        rows = self.codex_rows()
        rows[0]["payload"]["git"] = {"branch": "feature/fixture"}
        rows.append({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 200, "cached_input_tokens": 100, "output_tokens": 50, "reasoning_output_tokens": 20, "total_tokens": 250}, "last_token_usage": {"total_tokens": 80}, "model_context_window": 1000}}})
        self.write_events(self.log, rows)
        row = dashboard.snapshot()["chats"][0]
        self.assertEqual(row["branch"], "feature/fixture")
        self.assertEqual(row["details"]["tokens"]["total_tokens"], 250)
        self.assertEqual(row["details"]["context_tokens"], 80)

    def test_hook_queue_preserves_order_and_ignores_malformed_events(self):
        self.fixture()
        folder = self.root / "hook_queue"
        folder.mkdir()
        now = time.time()
        for name, event, timestamp in [("1", "Stop", now), ("2", "UserPromptSubmit", now-1)]:
            (folder / (name+'.json')).write_text(json.dumps({"session_id": SID, "hook_event_name": event, "observed_at": timestamp}), encoding="utf8")
        (folder / "bad.json").write_text("bad", encoding="utf8")
        dashboard.snapshot()
        with Catalog(inbox.CATALOG) as db:
            self.assertEqual(db.hooks()[SID]["state"], "done")
        self.assertEqual(len(list(folder.glob('*.json'))), 1)

    def test_hook_installer_is_idempotent_preserves_other_observers(self):
        path = self.root / "settings.json"
        original = {"theme": "dark", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "existing-observer"}]}]}}
        path.write_text(json.dumps(original), encoding="utf8")
        install(path)
        first = path.read_text(encoding="utf8")
        install(path)
        self.assertEqual(first, path.read_text(encoding="utf8"))
        restored = json.loads(first)
        self.assertEqual(restored["theme"], "dark")
        self.assertEqual(len(restored["hooks"]["Stop"]), 2)
        self.assertEqual(json.loads(path.with_name("settings.json.agent-manager.bak").read_text()), original)

    def test_concurrent_pin_read_and_catalog_requests(self):
        self.fixture()
        def work(i):
            if i % 3 == 0:
                dashboard.action("pin", {"id": SID, "pinned": True})
            elif i % 3 == 1:
                dashboard.action("read", {"id": SID, "read": True})
            else:
                self.assertEqual(len(dashboard.snapshot()["chats"]), 1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, range(60)))
        self.assertTrue(inbox.load_pins()[SID])
        self.assertIn(SID, inbox.load_state())

    def test_invalid_settings_and_missing_chat_do_not_mutate_state(self):
        self.fixture()
        for body in ({"reminder_delay_seconds": -1}, {"keep_taskbar": "yes"}, {"settle_days": 0}, {"unknown": 1}):
            with self.assertRaises(ValueError):
                dashboard.update_settings(body)
        with self.assertRaises(ValueError):
            dashboard.action("pin", {"id": "missing", "pinned": True})
        self.assertEqual(dashboard.settings(), dashboard.DEFAULTS)

    def test_archive_survives_metadata_outage_with_transcript_still_present(self):
        self.fixture()
        with patch.object(inbox, "codex_metadata", return_value={SID: {"archived": True}}):
            self.assertEqual(dashboard.snapshot()["counts"]["total"], 0)
        self.assertEqual(dashboard.snapshot()["counts"]["total"], 0)
        with patch.object(inbox, "codex_metadata", return_value={SID: {"archived": False}}):
            self.assertEqual(dashboard.snapshot()["counts"]["total"], 1)

    def test_hook_install_preserves_other_hooks_in_same_group(self):
        path = self.root / 'settings.json'
        path.write_text(json.dumps({'hooks': {'Stop': [{'matcher': '*', 'hooks': [
            {'type': 'command', 'command': 'existing-observer'},
            {'type': 'command', 'command': 'python D:/old/tools/claude_hook.py'}]}]}}), encoding='utf8')
        install(path)
        hooks = json.loads(path.read_text())['hooks']['Stop']
        self.assertEqual(hooks[0]['hooks'][0]['command'], 'existing-observer')
        self.assertEqual(hooks[0]['matcher'], '*')
        self.assertEqual(len(hooks), 2)

    def test_large_saved_catalog_and_missing_folders(self):
        with Catalog(inbox.CATALOG) as db:
            for i in range(300):
                db.remember({'item': ['Codex', 'saved-'+str(i), 'Saved chat '+str(i), 'Z:/missing', time.time(), 'A saved answer', 'assistant'], 'href': '', 'needs': False, 'hidden': False})
        started = time.monotonic()
        data = dashboard.snapshot()
        self.assertEqual(len(data['chats']), 300)
        self.assertLess(time.monotonic()-started, 5)
        self.assertFalse(dashboard.repository_context('saved-0')['available'])


class HttpTests(unittest.TestCase):
    setUp = DashboardTests.setUp
    fixture = DashboardTests.fixture
    write_events = DashboardTests.write_events
    codex_rows = DashboardTests.codex_rows
    def test_http_routes_errors_origins_and_asset_paths(self):
        self.fixture()
        server = ThreadingHTTPServer(("127.0.0.1", 0), inbox.H)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = 'http://127.0.0.1:'+str(server.server_port)
        def request(path, body=None, headers=None):
            raw = json.dumps(body).encode() if body is not None else None
            h = {"Content-Type": "application/json", **(headers or {})}
            try:
                with urllib.request.urlopen(urllib.request.Request(base+path,data=raw,headers=h),timeout=5) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()
        try:
            self.assertEqual(request('/')[0], 200)
            self.assertEqual(request('/app.js')[0], 200)
            self.assertEqual(request('/styles.css')[0], 200)
            self.assertEqual(request('/api/health')[0], 200)
            self.assertEqual(request('/api/state')[0], 200)
            self.assertEqual(request('/api/read', {"id": SID, "read": False})[0], 200)
            self.assertEqual(json.loads(request('/api/state')[1])["counts"]["unread"], 1)
            self.assertEqual(request('/api/pin', {"id": SID, "pinned": True})[0], 200)
            self.assertEqual(request('/api/read', {"id": SID}, {"Origin": "https://evil.example"})[0], 403)
            self.assertEqual(request('/api/settings', {"keep_taskbar": "yes"})[0], 400)
            self.assertEqual(request('/api/read', [], {})[0], 400)
            self.assertEqual(request('/api/read', {"id": SID}, {"Content-Type": "text/plain"})[0], 415)
            self.assertEqual(request('/../NOTES.md')[0], 404)
            self.assertEqual(request('/api/nope', {})[0], 404)
            self.assertEqual(request('/api/nope')[0], 404)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(3)


if __name__ == '__main__':
    unittest.main()
