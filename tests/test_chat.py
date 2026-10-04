import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chat_gates as gates
from chat_stream import FinalStream
from bridge_layers import Bridge
from baseline_loops import summarize


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='.')
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'CHAT_GATES_ENABLED':'true','CHAT_AUDIT_PATH':str(self.root/'audit.jsonl')})
        self.env.start()
        gates.NAME_TO_ID.clear()
        gates.BOT_IDS.clear()
        gates.init_bot_registry({'bot-a':'111','bot-b':'222'})
        self.state = gates.ChatState()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def outbound(self, text, state=None):
        return gates.evaluate_outbound(text, me='111', channel='synthetic', state=state or self.state)

    def test_ack_opens_window(self):
        self.assertEqual(gates.evaluate_inbound('[ACK]',channel='synthetic',state=self.state).act, gates.Act.SUPPRESS)
        self.assertGreater(self.state.silence_until['synthetic'], time.time())

    def test_non_ack_no_window(self):
        gates.evaluate_inbound('please review',channel='synthetic',state=self.state)
        self.assertFalse(self.state.silence_until)

    def test_ack_casefold_and_leading_mentions(self):
        gates.evaluate_inbound('<@111> <@!222> [ack]',channel='synthetic',state=self.state)
        self.assertIn('synthetic',self.state.silence_until)

    def test_silence_suppresses(self):
        self.state.silence_until['synthetic']=time.time()+gates.ACK_TTL
        self.assertEqual(self.outbound('substantive reply').act,gates.Act.SUPPRESS)

    def test_silence_expires(self):
        self.state.silence_until['synthetic']=time.time()-1
        self.assertEqual(self.outbound('substantive reply').act,gates.Act.ALLOW)

    def test_trivial_words(self):
        for word in ('ok','OK','Ok.','k','noted','[SILENT]','*[ACK]*','\U0001f44d'):
            self.assertEqual(gates.gate_keep_silence(word).act,gates.Act.SUPPRESS,word)

    def test_substantive_short(self):
        self.assertEqual(gates.gate_keep_silence('true').act,gates.Act.ALLOW)

    def test_long_text_not_inspected(self):
        self.assertEqual(gates.gate_keep_silence('ok '*(gates.MAX_SILENCE_LEN)).act,gates.Act.ALLOW)

    def test_synthetic_secret(self):
        self.assertEqual(self.outbound('sk-FAKE.'+'fake.'*6).act,gates.Act.SUPPRESS)

    def test_plain_text(self):
        self.assertEqual(self.outbound('a substantive ordinary reply').act,gates.Act.ALLOW)

    def test_mention_rewrite(self):
        result=self.outbound('bot-b please check')
        self.assertEqual(result.act,gates.Act.REWRITE)
        self.assertEqual(result.content,'<@222> please check')

    def test_no_double_mention(self):
        self.assertEqual(gates.gate_fix_mention('<@222> please check').act,gates.Act.ALLOW)

    def test_cooldown_suppresses_repeat(self):
        self.outbound('<@222> first message')
        self.assertEqual(self.outbound('<@222> next message').act,gates.Act.SUPPRESS)

    def test_first_mention_records(self):
        self.outbound('<@222> first message')
        self.assertIn(('111','222'),self.state.last_mention)

    def test_nonbot_mention(self):
        self.assertEqual(self.outbound('<@999> please check').act,gates.Act.ALLOW)
        self.assertFalse(self.state.last_mention)

    def test_unknown_name(self):
        self.assertEqual(self.outbound('unknown-bot please check').act,gates.Act.ALLOW)

    def test_secret_precedes_silence(self):
        self.state.silence_until['synthetic']=time.time()+gates.ACK_TTL
        self.assertEqual(self.outbound('sk-FAKE.'+'fake.'*6).reason,'credential_shape')

    def test_null_state_fails_open(self):
        result=gates.evaluate_outbound('ok',me='111',channel='synthetic',state=None)
        self.assertEqual(result.act,gates.Act.ALLOW)
        self.assertEqual(result.reason,'gate error')

    def test_disabled_outbound(self):
        with patch.dict(os.environ,{'CHAT_GATES_ENABLED':'false'}):
            self.assertEqual(self.outbound('ok').act,gates.Act.ALLOW)

    def test_disabled_inbound(self):
        with patch.dict(os.environ,{'CHAT_GATES_ENABLED':'false'}):
            gates.evaluate_inbound('[ACK]',channel='synthetic',state=self.state)
        self.assertFalse(self.state.silence_until)

    def test_init_idempotent(self):
        gates.init_bot_registry({'bot-a':'111'})
        self.assertEqual(gates.NAME_TO_ID,{'bot-a':'111','bot-b':'222'})

    def test_no_implicit_registry(self):
        gates.NAME_TO_ID.clear(); gates.BOT_IDS.clear()
        gates.init_bot_registry()
        self.assertFalse(gates.health_summary()['registry_loaded'])

    def test_human_ack_carveout(self):
        gates.evaluate_inbound('[ACK] please do this',channel='synthetic',state=self.state,is_bot=False)
        self.assertFalse(self.state.silence_until)

    def test_persist_and_prune(self):
        now=time.time()
        self.state.silence_until={'live':now+gates.ACK_TTL,'expired':now-1}
        self.state.last_mention={('111','222'):now,('222','111'):now-gates.COOLDOWN-1}
        path=self.root/'state.json'
        gates.dump_state(self.state,path)
        loaded=gates.load_state(path)
        self.assertEqual(set(loaded.silence_until),{'live'})
        self.assertEqual(set(loaded.last_mention),{('111','222')})

    def test_missing_state_fails_open(self):
        self.assertEqual(gates.load_state(self.root/'missing').last_mention,{})

    def test_startup_alarm(self):
        with patch.dict(os.environ,{'CHAT_GATES_ENABLED':'false'}), self.assertLogs('chat_gates',level='ERROR'):
            gates.startup_check()

    def test_audit_never_records_text(self):
        secret='sk-FAKE.'+'fake.'*6
        self.outbound(secret)
        raw=(self.root/'audit.jsonl').read_text()
        row=json.loads(raw)
        self.assertNotIn(secret,raw)
        self.assertEqual(row['len'],len(secret))
        self.assertEqual(len(row['sha12']),12)

    def test_allow_has_no_audit(self):
        self.outbound('ordinary substantive response')
        self.assertFalse((self.root/'audit.jsonl').exists())

    def test_bug_reproducer_double_evaluation_suppresses_own_reply(self):
        # Deliberately reproduce the bug; the stream test guards the fix.
        first=self.outbound('bot-b please check')
        second=self.outbound(first.content)
        self.assertEqual(first.act,gates.Act.REWRITE)
        self.assertEqual(second.act,gates.Act.SUPPRESS)
        self.assertEqual(second.reason,'loop_cooldown')

    def test_stream_gate_exactly_once(self):
        sent=[]
        stream=FinalStream(sent.append,me='111',channel='synthetic',state=self.state)
        with patch.object(gates,'evaluate_outbound',wraps=gates.evaluate_outbound) as gate:
            stream.delta('bot-b '); stream.delta('please check')
            self.assertTrue(stream.finalize()); self.assertTrue(stream.finalize())
            self.assertEqual(gate.call_count,1)
        self.assertEqual(sent,['<@222> please check'])

    def test_double_evaluation_mutation_fails_stream_delivery(self):
        evaluate = gates.evaluate_outbound
        def twice(text, **kwargs):
            first = evaluate(text, **kwargs)
            return evaluate(first.content if first.content is not None else text, **kwargs)
        sent = []
        stream = FinalStream(sent.append, me='111', channel='synthetic', state=self.state)
        stream.delta('bot-b please check')
        with patch.object(gates, 'evaluate_outbound', side_effect=twice):
            with self.assertRaises(AssertionError):
                self.assertTrue(stream.finalize(), 'double evaluation loses the reply')
        self.assertEqual(sent, [])

    def test_stream_suppress_positive_control(self):
        sent=[]
        stream=FinalStream(sent.append,me='111',channel='synthetic',state=self.state)
        stream.delta('ok')
        self.assertFalse(stream.finalize())
        self.assertEqual(sent,[])

    def test_silent_noop_mutation_fails_positive_control(self):
        def positive_control():
            stream=FinalStream(lambda text:None,me='111',channel='synthetic',state=self.state)
            stream.delta('ok')
            self.assertFalse(stream.finalize())
        with patch.object(gates,'evaluate_outbound',return_value=gates.Decision()):
            with self.assertRaises(AssertionError):
                positive_control()

    def test_burst_rule_and_observed_cadence(self):
        bridge=Bridge()
        self.assertTrue(all(bridge.rate_allows('111','synthetic',i*60/0.6) for i in range(90)))
        burst=Bridge()
        self.assertTrue(burst.rate_allows('111','synthetic',0))
        self.assertTrue(burst.rate_allows('111','synthetic',1))
        self.assertFalse(burst.rate_allows('111','synthetic',2))

    def test_fixture_baseline(self):
        rows=[json.loads(line) for line in Path('fixtures/chat-loop.jsonl').read_text().splitlines()]
        result=summarize(rows)[0]
        self.assertEqual(result['messages'],90)
        self.assertEqual(result['max_repeats'],11)
        self.assertEqual(result['end']-result['start'],74*60)
