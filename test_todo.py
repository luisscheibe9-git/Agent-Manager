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

    def test_done_time_recorded_and_kept_by_mark_all(self):
        self.fixture()
        dashboard.action('read',{'id':SID,'read':False})
        self.assertEqual(dashboard.snapshot()['chats'][0]['done_at'],0)
        dashboard.action('read',{'id':SID,'read':True})
        first=dashboard.snapshot()['chats'][0]['done_at']
        self.assertGreater(first,0)
        dashboard.action('mark-all',{})
        self.assertEqual(dashboard.snapshot()['chats'][0]['done_at'],first)
        dashboard.action('read',{'id':SID,'read':False})
        self.assertEqual(dashboard.snapshot()['chats'][0]['done_at'],0)

    def test_attachment_only_title_is_readable(self):
        self.assertEqual(inbox.clean_title('[File: Lecture 9.pdf; ref=file_ab12]'), '(attachment) Lecture 9.pdf')
        self.assertEqual(inbox.clean_title('[File: a.pdf; ref=x] summarize this'), 'summarize this')
        self.assertEqual(inbox.clean_title('plain  text'), 'plain text')
        codex = '\n# Files mentioned by the user:\n\n## WSR.docx: C:/x/WSR.docx\n\n## My request:\nfill out a wsr\n'
        self.assertEqual(inbox.clean_title(codex), 'fill out a wsr')
        self.assertEqual(inbox.clean_title('# Files mentioned by the user:\n\n## WSR.docx: C:/x'), '(attachment) WSR.docx')
        self.assertEqual(inbox.clean_title('quick rundown <t3_context version="1"> <context'), 'quick rundown')

    def test_five_hour_usage_buckets(self):
        import time, telemetry
        now = time.time()
        stamp = lambda ago: time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now - ago))
        details = telemetry.empty()
        for ago, usage in ((3 * 3600, {'input_tokens': 100, 'output_tokens': 50, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 1000}),
                           (7 * 3600, {'input_tokens': 400, 'output_tokens': 100})):
            telemetry.claude({'type': 'assistant', 'timestamp': stamp(ago),
                              'message': {'id': f'm{ago}', 'usage': usage, 'content': [], 'stop_reason': 'end_turn'}}, details)
        telemetry.finish(details)
        recent = sum(v for k, v in details['usage_buckets'].items() if int(k) >= now - 5 * 3600)
        self.assertEqual(recent, 100 + 5 * 50 + 0.1 * 1000)  # cost-weighted; the 7-hour-old message is outside the window
        self.assertEqual(sum(details['usage_buckets'].values()), 450 + 400 + 500)

    def test_limit_estimate_and_context_window(self):
        rows = [{'details': {'usage_buckets': {'0': 600_000, '300': 700_000, '40000': 900_000}}}]
        self.assertEqual(dashboard.five_hour_limit(rows), (1_300_000, 'your busiest 5 hours'))
        self.assertEqual(dashboard.five_hour_limit(rows, 5_000_000), (5_000_000, 'your setting'))
        self.assertEqual(dashboard.five_hour_limit([])[0], 1_000_000)
        hit = {'at': 40_100, 'reset': 41_000 + 4 * 3600}  # window covers 41,000-5h..at: only the last bucket
        self.assertEqual(dashboard.five_hour_limit([{'details': {'usage_buckets': {'0': 600_000, '40000': 2_000_000}, 'limit_hits': [hit]}}]),
                         (2_000_000, '1 times you hit the limit'))
        self.assertEqual(dashboard.context_window({'context_window': 258000}), 258000)
        self.assertEqual(dashboard.context_window({'model': 'claude-opus', 'context_tokens': 90_000}), 200_000)
        self.assertEqual(dashboard.context_window({'model': 'claude-opus', 'context_tokens': 300_000}), 1_000_000)

    def test_limit_hit_message_is_remembered(self):
        import telemetry
        details = telemetry.empty()
        record = {'type': 'assistant', 'timestamp': '2026-11-03T08:00:00Z', 'message': {'content': [{'type': 'text', 'text': "You've hit your session limit · resets 2am (America/Los_Angeles)"}], 'stop_reason': 'end_turn'}}
        telemetry.claude(record, details)
        telemetry.claude(dict(record, timestamp='2026-11-03T08:05:00Z'), details)  # repeats of the same window collapse
        self.assertEqual(len(details['limit_hits']), 1)
        self.assertGreater(details['limit_hits'][0]['reset'], details['limit_hits'][0]['at'])

    def test_ideas_are_saved_edited_sent_and_deleted(self):
        self.fixture()
        dashboard.action('idea-add', {'id': 'abc123', 'text': 'first'})
        dashboard.action('idea-update', {'id': 'abc123', 'text': 'second draft'})
        idea = dashboard.snapshot()['ideas'][0]
        self.assertEqual((idea['id'], idea['text'], idea['sent']), ('abc123', 'second draft', None))
        dashboard.action('idea-sent', {'id': 'abc123', 'target': 'codex'})
        self.assertEqual(dashboard.snapshot()['ideas'][0]['sent']['target'], 'codex')
        with self.assertRaises(ValueError):
            dashboard.action('idea-add', {'id': 'bad id!', 'text': 'x'})
        dashboard.action('idea-delete', {'id': 'abc123'})
        self.assertEqual(dashboard.snapshot()['ideas'], [])


    def test_snooze_hides_until_it_expires_and_can_be_woken(self):
        import time
        self.fixture()
        dashboard.action('read', {'id': SID, 'read': False})
        self.assertEqual(dashboard.snapshot()['counts']['todo'], 1)
        dashboard.action('snooze', {'id': SID, 'hours': 1})
        row = dashboard.snapshot()['chats'][0]
        self.assertGreater(row['snoozed_until'], time.time() + 3000)
        self.assertEqual(dashboard.snapshot()['counts']['todo'], 0)
        with self.assertRaises(ValueError):
            dashboard.action('snooze', {'id': SID, 'hours': 5})
        dashboard.action('unsnooze', {'id': SID})
        self.assertEqual(dashboard.snapshot()['counts']['todo'], 1)
        with Catalog(inbox.CATALOG) as db:
            db.set('snoozes', {SID: time.time() - 5})  # expired snoozes come back on their own
        self.assertEqual(dashboard.snapshot()['chats'][0]['snoozed_until'], 0)

    def test_ideas_can_be_reordered(self):
        self.fixture()
        for ident in ('aaa', 'bbb', 'ccc'):
            dashboard.action('idea-add', {'id': ident, 'text': ident})
        self.assertEqual([i['id'] for i in dashboard.snapshot()['ideas']], ['ccc', 'bbb', 'aaa'])
        dashboard.action('idea-reorder', {'ids': ['aaa', 'ccc', 'bbb']})
        self.assertEqual([i['id'] for i in dashboard.snapshot()['ideas']], ['aaa', 'ccc', 'bbb'])
        with self.assertRaises(ValueError):
            dashboard.action('idea-reorder', {'ids': ['bad id!']})


    def test_chats_can_be_reordered_by_hand(self):
        self.fixture()
        self.assertEqual(dashboard.snapshot()['chats'][0]['order'], -1)
        dashboard.action('chats-reorder', {'ids': [SID]})
        self.assertEqual(dashboard.snapshot()['chats'][0]['order'], 0)
        with self.assertRaises(ValueError):
            dashboard.action('chats-reorder', {'ids': ['bad id!']})
        self.assertEqual(dashboard._merge_order(['a', 'b', 'c'], ['c', 'x']), ['c', 'x', 'a', 'b'])


    def test_each_project_keeps_one_saved_hue(self):
        first = dashboard.project_hues(['alpha', 'beta', '__none__'])
        self.assertEqual(len(set(first.values())), 3)
        self.assertGreaterEqual(min(dashboard._gap(x, y) for x in first.values() for y in first.values() if x != y), 60)
        again = dashboard.project_hues(['alpha', 'gamma'])
        self.assertEqual(again['alpha'], first['alpha'])  # saved, so it never changes
        self.assertNotIn(again['gamma'], first.values())


if __name__ == '__main__':
    unittest.main()
