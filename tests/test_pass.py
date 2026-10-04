import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import board_pass as bp


class PassTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='.')
        self.root=Path(self.temp.name)
        self.card={'id':'synthetic-task','assignee':'a2a:agent-a','status':'ready','comments':[],
            'body':'Create out.txt\nworkdir: '+str(self.root)+'\n## acceptance\n```json\n'+
            json.dumps([{'type':'file_exists','path':'out.txt'}])+'\n```'}
        self.path=self.root/'board.json'
        self.path.write_text(json.dumps({'cards':[self.card]}))
        self.board=bp.JsonBoard(self.path)
        self.card=self.board.cards[0]

    def tearDown(self):
        self.temp.cleanup()

    def run_card(self,**kwargs):
        return bp.run_card(self.board,self.card,**kwargs)

    def test_success_then_verify_complete(self):
        self.assertEqual(self.run_card(),'PASS complete')
        self.assertEqual(bp.JsonBoard(self.path).cards[0]['status'],'done')
        self.assertTrue((self.root/'out.txt').exists())

    def test_failing_executor_never_verifies_existing_artifact(self):
        (self.root/'out.txt').touch()
        verifier=Mock(side_effect=AssertionError('must not verify'))
        result=self.run_card(executor=lambda *a:{'exit_code':3,'status':'verify-failed'},verifier=verifier)
        self.assertTrue(result.startswith('FAIL'))
        verifier.assert_not_called()
        self.assertEqual(self.card['status'],'ready')

    def test_non_json_executor_never_verifies(self):
        verifier=Mock()
        self.run_card(executor=lambda *a:'not json',verifier=verifier)
        verifier.assert_not_called()

    def test_merge_conflict_contract_is_failure(self):
        # The removed executor's merge mechanics are not shipped. Its failure
        # envelope still cannot get to verification or completion.
        verifier=Mock()
        self.run_card(executor=lambda *a:{'exit_code':1,'status':'merge-conflict','worktree_kept':True},verifier=verifier)
        verifier.assert_not_called()
        self.assertNotEqual(self.card['status'],'done')

    def test_dirty_preflight_defers_without_attempt(self):
        self.card['dirty_fixture']=True
        executor=Mock()
        self.assertTrue(self.run_card(executor=executor).startswith('DEFER'))
        executor.assert_not_called()
        self.assertEqual(bp.attempts_so_far(self.card)[0],0)

    def test_second_failure_blocks_and_feeds_evidence(self):
        packets=[]
        def executor(card,packet,workdir):
            packets.append(packet)
            return {'exit_code':2,'status':'verify-failed'}
        self.run_card(executor=executor)
        self.assertEqual(self.run_card(executor=executor),'FAIL blocked')
        self.assertEqual(self.card['status'],'blocked')
        self.assertIn('evidence (untrusted)',packets[-1])
        self.assertEqual(bp.attempts_so_far(self.card)[0],2)

    def test_executor_exception_cleanup(self):
        self.run_card(executor=Mock(side_effect=RuntimeError('fixture executor')))
        self.assertEqual(self.card['status'],'blocked')
        self.assertNotIn('claim_expires',self.card)

    def test_no_report_success_contract(self):
        executor=lambda *a:{'exit_code':0,'status':'no-report'}
        verifier=Mock(return_value={'outcome':'passed','evidence':[]})
        self.assertEqual(self.run_card(executor=executor,verifier=verifier),'PASS complete')
        verifier.assert_called_once()

    def test_unknown_nonzero_exit(self):
        verifier=Mock()
        self.run_card(executor=lambda *a:{'exit_code':2,'status':'ok'},verifier=verifier)
        verifier.assert_not_called()

    def test_exit_zero_failure_status(self):
        verifier=Mock()
        self.run_card(executor=lambda *a:{'exit_code':0,'status':'verify-failed'},verifier=verifier)
        verifier.assert_not_called()

    def test_verify_exception_reclaims_and_blocks(self):
        self.run_card(verifier=Mock(side_effect=RuntimeError('fixture verifier')))
        self.assertEqual(self.card['status'],'blocked')
        self.assertNotIn('claim_expires',self.card)

    def test_comment_failure_blocks_uncounted_attempt(self):
        with patch.object(self.board,'comment',side_effect=RuntimeError('fixture comment')):
            self.run_card()
        self.assertEqual(self.card['status'],'blocked')

    def test_cleanup_reclaim_failure_still_blocks(self):
        with patch.object(self.board,'reclaim',side_effect=RuntimeError('fixture reclaim')):
            result=self.run_card(verifier=Mock(side_effect=RuntimeError('fixture verify')))
        self.assertIn('reclaim',result)
        self.assertEqual(self.card['status'],'blocked')

    def test_cap_precheck_never_dispatches(self):
        self.card['comments']=[{'body':bp.ATTEMPT_MARK+'1] verdict=FAIL'},{'body':bp.ATTEMPT_MARK+'2] verdict=FAIL'}]
        executor=Mock()
        self.assertEqual(self.run_card(executor=executor),'BLOCK cap pre-check')
        executor.assert_not_called()

    def test_dry_run_never_mutates(self):
        before=self.path.read_bytes()
        self.run_card(dry=True)
        self.assertEqual(self.path.read_bytes(),before)

    def test_packet_task_predicates_and_objections(self):
        workdir,predicates,task=bp.parse_card(self.card['body'])
        packet=bp.build_packet(task,workdir,predicates,['old','latest'])
        self.assertIn('Create out.txt',packet)
        self.assertIn('file_exists',packet)
        self.assertIn('latest',packet)
        self.assertNotIn('\nold',packet)

    def test_parser_rejects_malformed(self):
        for body in ('nothing','workdir: .\n## acceptance\n```json\n{\n```',
                     'workdir: .\n## acceptance\n```json\n[]\n```'):
            self.assertIsNone(bp.parse_card(body))

    def test_predicates_fail_closed(self):
        (self.root/'out.txt').write_text('hi\n')
        predicates=[{'type':'file_exists','path':'out.txt'},
                    {'type':'file_contains','path':'out.txt','pattern':'^hi\\n$'},
                    {'type':'cmd_succeeds','command':[sys.executable,'-c','pass']}]
        self.assertEqual(bp.evaluate(self.root,predicates)['outcome'],'passed')
        for bad in ([],[{'type':'unknown'}],[{'type':'file_contains','path':'out.txt','pattern':'['}],
                    [{'type':'file_exists','path':'../escape'}],
                    [{'type':'cmd_succeeds','command':[sys.executable,'-c','raise SystemExit(1)']}]):
            self.assertEqual(bp.evaluate(self.root,bad)['outcome'],'failed')

    def test_claim_ttl_recovers_when_all_cleanup_fails(self):
        with patch.object(self.board,'comment',side_effect=RuntimeError()),patch.object(self.board,'reclaim',side_effect=RuntimeError()),patch.object(self.board,'block',side_effect=RuntimeError()):
            self.run_card(executor=Mock(side_effect=RuntimeError()))
        self.assertEqual(self.card['status'],'claimed')
        with patch.object(bp.time,'time',return_value=self.card['claim_expires']):
            self.board.reclaim_expired()
        self.assertEqual(self.card['status'],'ready')

    def test_pass_lock_refuses_second_writer(self):
        lock=self.root/'pass.lock'
        with bp.pass_lock(lock):
            with self.assertRaisesRegex(RuntimeError,'another pass'):
                with bp.pass_lock(lock):
                    self.fail('second writer entered')

    def test_skipped_card_does_not_spend_maximum(self):
        malformed=dict(self.card,id='malformed',body='missing predicates')
        self.path.write_text(json.dumps({'cards':[malformed,self.card]}))
        results=bp.run_pass(self.path,maximum=1)
        self.assertEqual(len(results),2)
        self.assertEqual(results[-1][1],'PASS complete')

    def test_json_board_three_case_end_to_end(self):
        cards=copy.deepcopy(json.loads(Path('fixtures/board.json').read_text())['cards'])
        for card in cards:
            name=card['id']
            card['body']=card['body'].replace('./state/'+name.removeprefix('synthetic-'),str(self.root/name))
        self.path.write_text(json.dumps({'cards':cards}))
        bp.run_pass(self.path)
        first=bp.JsonBoard(self.path)
        self.assertEqual([c['status'] for c in first.cards],['done','ready','ready'])
        bp.run_pass(self.path)
        final=bp.JsonBoard(self.path)
        self.assertEqual([c['status'] for c in final.cards],['done','blocked','ready'])
        self.assertEqual(bp.attempts_so_far(final.cards[-1])[0],0)
