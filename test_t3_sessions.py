"""Synthetic T3 databases only; never modify the installed T3 database."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import t3_sessions


def make_db(home):
    path = Path(home)/'.t3/userdata/statev2.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript('''
        CREATE TABLE orchestration_v2_projection_threads(thread_id TEXT PRIMARY KEY, deleted_at TEXT, archived_at TEXT);
        CREATE TABLE orchestration_v2_projection_provider_threads(thread_id TEXT, provider TEXT, payload_json TEXT);
        CREATE TABLE projection_threads(thread_id TEXT PRIMARY KEY, deleted_at TEXT);
        CREATE TABLE projection_thread_sessions(thread_id TEXT, provider_name TEXT, provider_thread_id TEXT);
        CREATE TABLE provider_session_runtime(thread_id TEXT, provider_name TEXT, resume_cursor_json TEXT, runtime_payload_json TEXT);
    ''')
    db.commit()
    return path, db


def add(db, native='native-1', source='codex', owner='t3-internal-1', deleted=None, archived=None):
    db.execute('INSERT OR REPLACE INTO orchestration_v2_projection_threads VALUES (?,?,?)', (owner,deleted,archived))
    db.execute('INSERT INTO orchestration_v2_projection_provider_threads VALUES (?,?,?)',
               (owner,source,json.dumps({'id': 'not-a-native-id', 'nativeThreadRef': {'driver':source,'nativeId':native,'strength':'strong'}})))
    db.commit()


class T3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ)
        self.env.start()
        os.environ.pop('AGENT_MANAGER_T3_DB',None)
        self.addCleanup(self.env.stop)

    def test_exact_provider_qualified_native_ids_only(self):
        path, db = make_db(self.home)
        with db:
            add(db)
            add(db, native='claude-1', source='claude', owner='t3-internal-2')
        db.close()
        before = path.read_bytes()
        result = t3_sessions.scan(self.home)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(set(result['sessions']), {('Codex','native-1'), ('Claude','claude-1')})
        self.assertNotIn(('Claude','native-1'), result['sessions'])
        self.assertNotIn(('Codex','t3-internal-1'), result['sessions'])
        self.assertNotIn(('Codex','not-a-native-id'), result['sessions'])
        self.assertEqual(before, path.read_bytes())

    def test_archived_still_managed_deleted_no_longer_managed(self):
        _, db = make_db(self.home)
        add(db, archived='yesterday')
        add(db, native='deleted-native',owner='deleted-owner',deleted='today')
        # An obsolete legacy row must not override V2's deleted flag.
        db.execute('INSERT INTO projection_threads VALUES (?,NULL)', ('deleted-owner',))
        db.execute('INSERT INTO projection_thread_sessions VALUES (?,?,?)', ('deleted-owner','codex','deleted-native'))
        db.commit(); db.close()
        self.assertEqual(set(t3_sessions.scan(self.home)['sessions']), {('Codex','native-1')})

    def test_legacy_resume_and_imported_original_ids(self):
        _, db = make_db(self.home)
        db.execute('INSERT INTO projection_threads VALUES (?,NULL)', ('owner',))
        db.execute('INSERT INTO provider_session_runtime VALUES (?,?,?,?)',
                   ('owner','codex',json.dumps({'threadId':'current-native'}),json.dumps({'cwd':'ignored','importedTranscripts':[{'provider':'codex','providerSessionId':'imported-original','filePath':'ignored'}]})))
        db.execute('INSERT INTO projection_thread_sessions VALUES (?,?,?)', ('owner','claude','legacy-claude'))
        db.commit(); db.close()
        self.assertEqual(set(t3_sessions.scan(self.home)['sessions']), {('Codex','current-native'),('Codex','imported-original'),('Claude','legacy-claude')})

    def test_claude_cursor_and_malformed_rows(self):
        _, db = make_db(self.home)
        add(db)
        db.execute('INSERT INTO provider_session_runtime VALUES (?,?,?,?)', ('t3-internal-1','claude',json.dumps({'sessionId':'claude-native'}),'{}'))
        db.execute('INSERT INTO orchestration_v2_projection_provider_threads VALUES (?,?,?)', ('t3-internal-1','codex','broken json'))
        db.execute('INSERT INTO orchestration_v2_projection_provider_threads VALUES (?,?,?)', ('t3-internal-1','codex',json.dumps({'nativeThreadRef': 'bad'})))
        db.commit(); db.close()
        self.assertEqual(set(t3_sessions.scan(self.home)['sessions']), {('Codex','native-1'),('Claude','claude-native')})

    def test_wal_add_remove_observed_without_process_restart(self):
        _, db = make_db(self.home)
        db.execute('PRAGMA journal_mode=WAL')
        self.assertEqual(t3_sessions.scan(self.home)['sessions'], {})
        add(db)
        self.assertIn(('Codex','native-1'), t3_sessions.scan(self.home)['sessions'])
        db.execute("UPDATE orchestration_v2_projection_threads SET deleted_at='now'");db.commit()
        self.assertEqual(t3_sessions.scan(self.home)['sessions'], {})
        db.close()

    def test_missing_corrupt_and_unknown_schema_fail_open(self):
        self.assertEqual(t3_sessions.scan(self.home)['status'],'not_found')
        path = self.home/'.t3/userdata/statev2.sqlite'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'not a database')
        self.assertEqual(t3_sessions.scan(self.home)['sessions'],{})
        path.unlink()
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE unrelated(name TEXT)')
        db.close()
        self.assertEqual(t3_sessions.scan(self.home)['status'],'unavailable')

    def test_locked_database_returns_no_guessed_membership(self):
        _, db = make_db(self.home)
        add(db)
        db.execute('BEGIN EXCLUSIVE')
        try:
            result = t3_sessions.scan(self.home)
            self.assertEqual(result['status'],'unavailable')
            self.assertEqual(result['sessions'],{})
        finally:
            db.rollback(); db.close()

    def test_custom_database_path(self):
        path, db = make_db(self.home)
        add(db);db.close()
        with patch.dict(os.environ, {'AGENT_MANAGER_T3_DB':str(path)}):
            self.assertIn(('Codex','native-1'),t3_sessions.scan(self.home/'different-home')['sessions'])

    def test_legacy_filename_fallback(self):
        path, db = make_db(self.home)
        add(db);db.close()
        path.rename(path.with_name('state.sqlite'))
        self.assertIn(('Codex','native-1'),t3_sessions.scan(self.home)['sessions'])


if __name__ == '__main__':
    unittest.main()
