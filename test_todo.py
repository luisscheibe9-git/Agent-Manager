import json
import unittest
from unittest.mock import patch

import dashboard
import inbox
from catalog import Catalog
import test_dashboard
from test_t3_sessions import make_db, add

SID = test_dashboard.SID


class TodoTests(unittest.TestCase):
    setUp = test_dashboard.DashboardTests.setUp
    write_events = test_dashboard.DashboardTests.write_events
    codex_rows = test_dashboard.DashboardTests.codex_rows
    fixture = test_dashboard.DashboardTests.fixture

    def test_done_and_return_to_todo_persist(self):
        self.fixture()
        dashboard.action('pin',{'id':SID,'pinned':True})
        dashboard.action('read',{'id':SID,'read':False})
        self.assertEqual(dashboard.snapshot()['counts']['todo'],1)
        dashboard.action('read',{'id':SID,'read':True})
        self.assertEqual(dashboard.snapshot()['counts']['todo'],0)
        self.assertTrue(dashboard.snapshot()['chats'][0]['pinned'])
        with Catalog(inbox.CATALOG) as db:
            self.assertEqual(len(db.records()),1)
        dashboard.action('read',{'id':SID,'read':False})
        self.assertEqual(dashboard.snapshot()['counts']['todo'],1)

    def test_done_clears_pending_question_and_reminders_without_answering(self):
        self.fixture(False)
        dashboard.hook({'session_id':SID,'hook_event_name':'PermissionRequest'})
        dashboard.action('read',{'id':SID,'read':True})
        state = dashboard.snapshot()
        self.assertEqual(state['chats'][0]['state'],'needs')
        self.assertTrue(state['chats'][0]['read'])
        self.assertEqual(state['counts']['todo'],0)
        self.assertEqual(state['counts']['needs'],0)
        self.assertEqual(dashboard.notify_due(lambda *_:self.fail('Cleared chat notified')),[])

    def test_progress_does_not_resurrect_done_but_completion_does(self):
        self.fixture(False)
        dashboard.action('read',{'id':SID,'read':True})
        rows=self.codex_rows(False)
        rows.append({'type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':{'total_tokens':123456}}}})
        rows.append({'type':'response_item','payload':{'type':'message','role':'assistant','phase':'commentary','content':[{'type':'output_text','text':'Still working'}]}})
        self.write_events(self.log, rows)
        self.assertEqual(dashboard.snapshot()['counts']['todo'],0)
        rows.extend([{'type':'response_item','payload':{'type':'message','role':'assistant','phase':'final_answer','content':[{'type':'output_text','text':'Finished new reply'}]}}, {'type':'event_msg','payload':{'type':'task_complete'}}])
        self.write_events(self.log,rows)
        self.assertEqual(dashboard.snapshot()['counts']['todo'],1)

    def test_identical_new_reply_is_still_new_activity(self):
        self.fixture()
        dashboard.action('read',{'id':SID,'read':True})
        rows=self.codex_rows(True)
        rows.extend(self.codex_rows(True)[1:])
        self.write_events(self.log,rows)
        self.assertEqual(dashboard.snapshot()['counts']['todo'],1)

    def test_t3_separate_excluded_from_todo_badge_and_mark_all(self):
        self.fixture()
        dashboard.action('read',{'id':SID,'read':False})
        _, db=make_db(self.root);add(db,native=SID);db.close()
        state=dashboard.snapshot()
        self.assertTrue(state['chats'][0]['managed_by_t3'])
        self.assertEqual(state['counts']['t3'],1)
        self.assertEqual(state['counts']['todo'],0)
        dashboard.action('mark-all',{})
        self.assertFalse(dashboard.snapshot()['chats'][0]['read'])

    def test_removal_from_t3_returns_original_unread_without_data_loss(self):
        self.fixture()
        dashboard.action('pin',{'id':SID,'pinned':True})
        dashboard.action('read',{'id':SID,'read':False})
        _, db=make_db(self.root);add(db,native=SID)
        self.assertEqual(dashboard.snapshot()['counts']['todo'],0)
        db.execute("UPDATE orchestration_v2_projection_threads SET deleted_at='now'");db.commit();db.close()
        state=dashboard.snapshot()
        self.assertEqual(state['counts']['todo'],1)
        self.assertTrue(state['chats'][0]['pinned'])

    def test_old_pinned_unread_is_not_silently_settled(self):
        self.fixture()
        with patch.object(inbox.time,'time',return_value=20000000000):
            dashboard.action('read',{'id':SID,'read':False})
            self.assertEqual(dashboard.snapshot()['counts']['todo'],1)

    def test_mark_all_clears_working_and_needs(self):
        self.fixture(False)
        dashboard.action('read',{'id':SID,'read':False})
        dashboard.action('mark-all',{})
        self.assertEqual(dashboard.snapshot()['counts']['todo'],0)

    def test_attachment_only_title_is_readable(self):
        self.assertEqual(inbox.clean_title('[File: Lecture 9.pdf; ref=file_ab12]'), '(attachment) Lecture 9.pdf')
        self.assertEqual(inbox.clean_title('[File: a.pdf; ref=x] summarize this'), 'summarize this')
        self.assertEqual(inbox.clean_title('plain  text'), 'plain text')
        codex = '\n# Files mentioned by the user:\n\n## WSR.docx: C:/x/WSR.docx\n\n## My request:\nfill out a wsr\n'
        self.assertEqual(inbox.clean_title(codex), 'fill out a wsr')
        self.assertEqual(inbox.clean_title('# Files mentioned by the user:\n\n## WSR.docx: C:/x'), '(attachment) WSR.docx')
        self.assertEqual(inbox.clean_title('quick rundown <t3_context version="1"> <context'), 'quick rundown')

    def test_resume_opens_terminal_only_for_valid_claude_chat(self):
        self.fixture()
        with patch.object(dashboard.subprocess, 'Popen') as popen:
            with self.assertRaises(ValueError):
                dashboard.action('resume', {'id': 'x; calc'})
            row = dashboard.snapshot()['chats'][0]
            if row['source'] == 'Claude':
                dashboard.action('resume', {'id': row['id']})
                self.assertIn(f"claude --resume {row['id']}", popen.call_args[0][0][-1])
            else:
                with self.assertRaises(ValueError):
                    dashboard.action('resume', {'id': row['id']})


if __name__ == '__main__':
    unittest.main()
