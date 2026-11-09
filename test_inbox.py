"""Regression tests use synthetic transcripts and temporary app data only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import inbox

SID = "12345678-1234-1234-1234-123456789abc"
CLAUDE_ID = "22345678-1234-1234-1234-123456789abc"


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = dict(HOME=str(self.root), STATE=str(self.root / "read_state.json"),
                          PINS=str(self.root / "pins.json"), CATALOG=str(self.root / "chats.sqlite3"))
        self.patcher = patch.multiple(inbox, **self.paths)
        self.patcher.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.patcher.stop)
        for mapping in (inbox.META, inbox.NEEDS, inbox.RUNNING, inbox.HREFS):
            mapping.clear()
        self.log = self.root / ".codex/sessions/2026/rollout-test-" / (SID + ".jsonl")

    def write_events(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf8")

    def codex_rows(self, complete=True):
        rows = [
            {"type": "session_meta", "payload": {"id": SID, "cwd": "C:/old-project", "source": "vscode"}},
            {"type": "event_msg", "payload": {"type": "task_started"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user",
                "content": [{"type": "input_text", "text": "Build the fixture project"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "commentary",
                "content": [{"type": "output_text", "text": "Still working"}]}},
        ]
        if complete:
            rows.extend([
                {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "Fixture complete"}]}},
                {"type": "event_msg", "payload": {"type": "task_complete"}},
            ])
        return rows

    def test_current_codex_text_titles_folder_and_completion(self):
        self.write_events(self.log, self.codex_rows())
        self.write_events(self.root / ".codex/session_index.jsonl", [{"id": SID, "thread_name": "Renamed fixture"}])
        import sqlite3
        with sqlite3.connect(self.root / ".codex/state_5.sqlite") as db:
            db.execute("CREATE TABLE threads (id TEXT, title TEXT, cwd TEXT, archived INTEGER)")
            db.execute("INSERT INTO threads VALUES (?, ?, ?, 0)", (SID, "Desktop fixture title", "C:/new-project"))
        db.close()
        row, = inbox.collect_sessions()
        self.assertEqual(row[1:4], (SID, "Desktop fixture title", "C:/new-project"))
        self.assertEqual(row[5], "Fixture complete")
        self.assertEqual(inbox.item_state(SID, row[4], row[6]), "done")
        self.assertEqual(inbox.HREFS[SID], "codex://threads/" + SID)

    def test_claude_transcript_beyond_windows_max_path_is_scanned(self):
        sid = "11111111-2222-3333-4444-555555555555"
        # Like Claude's scratch-chat folders: the folder fits under MAX_PATH, folder + file name does not.
        base = os.path.join(str(self.root), ".claude", "projects")
        folder = os.path.join(base, "C--scratch-" + "x" * (230 - len(base)))
        path = os.path.join(folder, sid + ".jsonl")
        self.assertLess(len(folder), 248)
        self.assertGreaterEqual(len(path), 260)
        os.makedirs(folder)
        self.addCleanup(lambda: os.path.exists(inbox.lp(path)) and os.remove(inbox.lp(path)))
        with open(inbox.lp(path), "w", encoding="utf8") as f:
            f.write(json.dumps({"type": "user", "cwd": "C:/scratch",
                                "message": {"content": "Long path fixture"}}) + "\n")
        rows = inbox.scan_claude(0)
        self.assertEqual([r[1] for r in rows], [sid])
        self.assertEqual(rows[0][2], "Long path fixture")

    def claude_chat(self, sid, text, mtime):
        path = self.root / ".claude/projects/C--proj" / (sid + ".jsonl")
        self.write_events(path, [{"type": "user", "cwd": "C:/proj", "message": {"content": text}},
                                 {"type": "assistant", "message": {"content": "Answer " + text}}])
        os.utime(path, (mtime, mtime))

    def test_cleared_transcripts_of_a_desktop_chat_are_hidden(self):
        old, cur = "aaaaaaaa-0000-0000-0000-000000000001", "aaaaaaaa-0000-0000-0000-000000000002"
        now = time.time()
        self.claude_chat(old, "Before clear", now - 100)
        self.claude_chat(cur, "After clear", now - 10)
        meta = self.root / "AppData/Roaming/Claude/claude-code-sessions/x/local_s1.json"
        meta.parent.mkdir(parents=True)
        meta.write_text(json.dumps({"sessionId": "local_s1", "cliSessionId": cur,
                                    "priorCliSessionIds": [old]}), encoding="utf8")
        self.assertEqual([r[1] for r in inbox.collect_sessions()], [cur])

    def test_chat_found_late_is_baselined_read_but_new_chat_is_not(self):
        now = time.time()
        self.claude_chat("bbbbbbbb-0000-0000-0000-000000000001", "Known", now - 5000)
        inbox.collect_sessions()  # app has run: catalog and last scan time exist
        inbox.save_state({})
        from catalog import Catalog
        with Catalog(inbox.CATALOG) as db:
            db.set("last_scan_at", now - 1000)  # the app last scanned a while ago
        hidden_old = "bbbbbbbb-0000-0000-0000-000000000002"
        fresh = "bbbbbbbb-0000-0000-0000-000000000003"
        self.claude_chat(hidden_old, "Old but newly readable", now - 3000)
        self.claude_chat(fresh, "Made while app was off", now - 100)
        inbox.collect_sessions()
        state = inbox.load_state()
        self.assertIn(hidden_old, state)
        self.assertNotIn(fresh, state)

    def test_active_commentary_is_not_a_finished_answer(self):
        self.write_events(self.log, self.codex_rows(complete=False))
        row, = inbox.collect_sessions()
        self.assertEqual(inbox.item_state(SID, row[4], row[6]), "working")
        self.assertFalse(row[5])
        self.write_events(self.log, self.codex_rows())
        row, = inbox.collect_sessions()
        self.assertEqual(row[5], "Fixture complete")
        self.assertEqual(inbox.item_state(SID, row[4], row[6]), "done")

    def test_catalog_read_and_pins_survive_new_process_without_logs(self):
        self.write_events(self.log, self.codex_rows())
        old = time.time() - 60 * 86400
        os.utime(self.log, (old, old))
        inbox.collect_sessions()
        inbox.save_state({"rollout-2026-01-01-" + SID: old})
        inbox.write_json(inbox.PINS, {"rollout-2026-01-01-" + SID: True})
        self.log.rename(self.log.with_suffix(".unavailable"))
        code = (
            "import inbox,json,sys; "
            "[setattr(inbox,k,v) for k,v in json.loads(sys.argv[1]).items()]; "
            "rows=inbox.collect_sessions(); "
            "print(json.dumps({'rows':rows,'read':inbox.load_state(),'pins':inbox.load_pins(),'html':inbox.render()}))"
        )
        child = subprocess.run([sys.executable, "-c", code, json.dumps(self.paths)],
                               cwd=Path(__file__).parent, check=True, text=True, capture_output=True)
        restored = json.loads(child.stdout)
        self.assertEqual(restored["rows"][0][1], SID)
        self.assertEqual(restored["rows"][0][5], "Fixture complete")
        self.assertEqual(restored["read"][SID], old)
        self.assertTrue(restored["pins"][SID])
        self.assertIn('row Codex pinned', restored["html"])
        self.assertIn('data-state="done"', restored["html"])

    def test_packaged_claude_metadata_and_saved_link(self):
        log = self.root / ".claude/projects/project" / (CLAUDE_ID + ".jsonl")
        self.write_events(log, [
            {"type": "user", "message": {"content": "Claude fixture"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Claude answer"}]}},
        ])
        meta = self.root / "AppData/Local/Packages/Claude_fixture/LocalCache/Roaming/Claude/claude-code-sessions/account/local_fixture.json"
        meta.parent.mkdir(parents=True)
        record = {"cliSessionId": CLAUDE_ID, "sessionId": "desktop-id", "title": "Desktop Claude",
                  "interruptedAwaitingPerson": True}
        meta.write_text(json.dumps(record), encoding="utf8")
        row, = inbox.collect_sessions()
        self.assertEqual(row[2], "Desktop Claude")
        self.assertEqual(row[5], "Claude answer")
        self.assertEqual(inbox.item_state(CLAUDE_ID, row[4], row[6]), "needs")
        meta.rename(meta.with_suffix(".unavailable"))
        log.rename(log.with_suffix(".unavailable"))
        inbox.collect_sessions()
        self.assertEqual(inbox.HREFS[CLAUDE_ID], "claude://claude.ai/epitaxy/desktop-id")

    def test_archived_chats_stay_hidden_if_metadata_later_disappears(self):
        self.write_events(self.log, self.codex_rows())
        inbox.collect_sessions()
        with patch.object(inbox, "codex_metadata", return_value={SID: {"archived": True}}):
            self.assertEqual(inbox.collect_sessions(), [])
        self.log.rename(self.log.with_suffix(".unavailable"))
        self.assertEqual(inbox.collect_sessions(), [])

    def test_corrupt_read_state_uses_backup_and_no_first_run_unread_flood(self):
        self.write_events(self.log, self.codex_rows())
        self.assertEqual(inbox.unread_json(), [])
        original = inbox.load_state()
        inbox.save_state(original)
        Path(inbox.STATE).write_text("corrupt", encoding="utf8")
        self.assertEqual(inbox.load_state(), original)
        self.assertEqual(inbox.unread_json(), [])

    def test_read_timestamp_keeps_fractional_precision(self):
        self.write_events(self.log, self.codex_rows())
        mt = time.time() - 100.625
        os.utime(self.log, (mt, mt))
        row, = inbox.collect_sessions()
        inbox.save_state({SID: row[4]})
        html = inbox.render()
        self.assertIn(f'data-mt="{row[4]}"', html)
        self.assertEqual(inbox.unread_json(), [])

    def test_incomplete_source_does_not_erase_saved_title_or_preview(self):
        self.write_events(self.log, self.codex_rows())
        inbox.collect_sessions()
        self.log.write_text('{"type":', encoding="utf8")
        restored, = inbox.collect_sessions()
        self.assertEqual(restored[2], "Build the fixture project")
        self.assertEqual(restored[5], "Fixture complete")


if __name__ == "__main__":
    unittest.main()
