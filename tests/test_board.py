import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from toy_board import Board, root_config, reviewer_for
from reviewer_map_consistency import check


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='.')
        self.root=Path(self.temp.name)
        self.config=json.loads(Path('configs/board.example.json').read_text())
        self.board=Board(self.root/'board.db',self.config)
        self.watermark=self.root/'watermark.json'
        self.board.create('synthetic-task',created_at=0)
        self.board.add_run('synthetic-task',start=30,end=60)
        self.env=patch.dict(os.environ,{'WORKER_TASK':'synthetic-task','WORKER_RUN':'1'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.board.close()
        self.temp.cleanup()

    def complete(self):
        return self.board.complete('synthetic-task')

    def direct_complete(self):
        return self.board.complete('synthetic-task',via_tool=False)

    def test_baseline_blocks(self):
        self.assertIn('producer cannot be the acceptor',self.complete())
        self.assertEqual(self.board.task('synthetic-task')['status'],'ready')

    def test_posthoc_child_blocks(self):
        self.board.create('synthetic-child',created_at=60,parents=['synthetic-task'])
        self.assertIsNotNone(self.complete())

    def test_self_named_reviewer_blocks(self):
        self.board.request_review('synthetic-task','worker-a')
        self.assertIsNotNone(self.complete())

    def test_case_variant_self_review_blocks(self):
        self.board.request_review('synthetic-task',' WORKER-A ')
        self.assertIsNotNone(self.complete())

    def test_genuine_precreated_child_allows(self):
        self.board.create('synthetic-child',created_at=13,parents=['synthetic-task'])
        self.assertIsNone(self.complete())

    def test_real_handover_allows(self):
        self.assertEqual(self.board.request_review('synthetic-task'),'reviewer-b')
        self.board.add_run('synthetic-task','reviewer-b',60,79)
        self.assertIsNone(self.complete())

    def test_event_without_run_allows(self):
        self.board.request_review('synthetic-task',synthetic_runs=False)
        self.assertIsNone(self.complete())

    def test_completion_retry_allows(self):
        self.direct_complete()
        self.assertIsNone(self.complete())
        self.assertEqual(len(self.board.events('synthetic-task','completed')),1)

    def test_nonworker_allows_despite_synthetic_run(self):
        self.board.add_run('synthetic-task',start=60,end=60)
        with patch.dict(os.environ,{'WORKER_TASK':'','WORKER_RUN':''}):
            self.assertIsNone(self.complete())

    def test_gate_kill_switch_and_unknown_lane(self):
        self.config['kanban']['require_review_before_complete']=False
        self.assertIsNone(self.board.rejection('synthetic-task'))
        self.config['kanban']['require_review_before_complete']=True
        self.config['kanban']['default_reviewer_map']={}
        self.assertIsNone(self.board.rejection('synthetic-task'))

    def test_gate_exception_fails_open(self):
        with patch.object(self.board,'events',side_effect=RuntimeError('fixture')):
            self.assertIsNone(self.board.rejection('synthetic-task'))

    def test_first_scan_baselines_history(self):
        self.direct_complete()
        self.assertEqual(self.board.tick(self.watermark),[])
        self.assertTrue(self.watermark.exists())
        self.assertEqual(self.board.events('synthetic-task','review_enforcement_flagged'),[])

    def test_cli_bypass_positive_control(self):
        self.board.tick(self.watermark)
        self.direct_complete()
        with self.assertLogs('toy_board',level='WARNING'):
            self.assertEqual(self.board.tick(self.watermark),['synthetic-task'])
        payload=json.loads(self.board.events('synthetic-task','review_enforcement_flagged')[0]['payload'])
        self.assertEqual(payload,{'implementer':'worker-a','expected_reviewer':'reviewer-b',
            'reason':'completed without independent review evidence','board':'synthetic-board'})
        self.assertEqual(self.board.task('synthetic-task')['status'],'done')

    def test_scan_negative_controls_really_enter_range(self):
        self.board.tick(self.watermark)
        previous=json.loads(self.watermark.read_text())['synthetic-board']
        self.board.create('synthetic-child',created_at=13,parents=['synthetic-task'])
        self.direct_complete()
        self.board.create('synthetic-review',created_at=60)
        self.board.add_run('synthetic-review','worker-a',60,79)
        self.board.add_run('synthetic-review','reviewer-b',79,90)
        self.board.complete('synthetic-review',via_tool=False)
        for task in ('synthetic-task','synthetic-review'):
            self.assertGreater(self.board.events(task,'completed')[0]['id'],previous)
        self.assertEqual(self.board.tick(self.watermark),[])

    def test_scan_rewind_idempotence(self):
        self.board.tick(self.watermark)
        baseline=self.watermark.read_text()
        self.direct_complete()
        with self.assertLogs('toy_board',level='WARNING'):
            self.board.tick(self.watermark)
        self.watermark.write_text(baseline)
        self.assertEqual(self.board.tick(self.watermark),[])
        self.assertEqual(len(self.board.events('synthetic-task','review_enforcement_flagged')),1)
        self.assertNotEqual(self.watermark.read_text(),baseline)

    def test_switch_off_preserves_watermark_then_catches_up(self):
        self.board.tick(self.watermark)
        baseline=self.watermark.read_text()
        self.config['kanban']['review_enforcement']['enabled']=False
        self.direct_complete()
        self.assertEqual(self.board.tick(self.watermark),[])
        self.assertEqual(self.board.tick(self.watermark),[])
        self.assertEqual(self.watermark.read_text(),baseline)
        self.config['kanban']['review_enforcement']['enabled']=True
        with self.assertLogs('toy_board',level='WARNING'):
            self.assertEqual(self.board.tick(self.watermark),['synthetic-task'])

    def test_older_card_posthoc_link_does_not_exempt_scan(self):
        self.board.tick(self.watermark)
        self.board.create('old-synthetic-card',created_at=0)
        self.board.link('synthetic-task','old-synthetic-card')
        self.assertIsNone(self.complete())
        self.assertEqual(self.board.verdict('synthetic-task'),('worker-a','reviewer-b'))

    def test_assignee_and_synthetic_runs_are_not_evidence(self):
        self.board.request_review('synthetic-task','unknown-profile',now=60)
        self.direct_complete()
        self.assertEqual(self.board.verdict('synthetic-task'),('worker-a','reviewer-b'))

    def test_malformed_event_gate_allows_scan_warns(self):
        with self.board.conn:
            self.board.conn.execute('BEGIN')
            self.board.event('synthetic-task','review_requested',{})
        self.assertIsNone(self.complete())
        self.assertIsNotNone(self.board.verdict('synthetic-task'))

    def test_real_review_then_self_handover_gate_blocks_scan_allows(self):
        self.board.request_review('synthetic-task','reviewer-b')
        self.board.add_run('synthetic-task','reviewer-b',60,79)
        self.board.request_review('synthetic-task','reviewer-b')
        self.assertIsNotNone(self.complete())
        self.direct_complete()
        self.assertIsNone(self.board.verdict('synthetic-task'))

    def test_manual_zero_length_run_exempt_scan(self):
        self.board.create('manual')
        self.board.add_run('manual',start=30,end=30)
        self.board.complete('manual',via_tool=False)
        self.assertIsNone(self.board.verdict('manual'))

    def test_lock_failure_still_writes_baseline(self):
        with patch('toy_board.fcntl.flock',side_effect=OSError('synthetic lock failure')):
            with self.assertLogs('toy_board',level='WARNING'):
                self.assertEqual(self.board.scan(self.watermark),[])
        self.assertIn('synthetic-board',json.loads(self.watermark.read_text()))
        self.direct_complete()
        with self.assertLogs('toy_board',level='WARNING'):
            self.assertEqual(self.board.scan(self.watermark),['synthetic-task'])

    def test_event_append_requires_transaction(self):
        with self.assertRaisesRegex(RuntimeError,'transaction'):
            self.board.event('synthetic-task','probe')

    def test_root_reader_in_profile_environment(self):
        profile=self.root/'profiles'/'worker-a'
        profile.mkdir(parents=True)
        (self.root/'config.json').write_text(json.dumps(self.config))
        (profile/'config.json').write_text('{}')
        with patch.dict(os.environ,{'APP_HOME':str(profile)}):
            self.assertEqual(reviewer_for('worker-a',root_config()),'reviewer-b')
        self.assertIsNone(reviewer_for('unknown',self.config))
        self.assertIsNone(reviewer_for('',self.config))
        self.assertIsNone(reviewer_for(None,self.config))

    def test_reconciliation_mutations(self):
        a={'worker-a':'reviewer-b','reviewer-b':'worker-a'}
        exists=lambda name:name in a
        self.assertEqual(check(a,a,exists),[])
        for bad in ({'worker-a':'worker-a'},{'worker-a':'missing'},{},dict(a,extra='reviewer-b')):
            self.assertTrue(check(a,bad,exists))
        with self.assertRaises(RuntimeError):
            check(a,a,None)
        self.assertTrue(any('missing reviewer' in s for s in check(a,a,lambda n:n=='worker-a')))
