import asyncio
from concurrent.futures import ThreadPoolExecutor
import contextlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import FunctionType
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chain
from process_runner import ProcessRunner
import cards
import generate_services
import matrix_test
import token_store


class HubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='.')
        self.root = Path(self.temp.name)
        self.old = chain.LEDGER
        chain.LEDGER = self.root / 'ledger.jsonl'

    def tearDown(self):
        chain.LEDGER = self.old
        self.temp.cleanup()

    def admit(self, i, agent='agent-a', prompt=None, context=None, refs=()):
        chain.admit(context or f'ctx{i}', f't{i}', agent, prompt or f'question {i}', list(refs))

    def completed_hops(self, n):
        for i in range(n):
            self.admit(i, agent=f'agent-{i % 4}')
            chain.complete(f't{i}', True, 0, 0)

    def test_twenty_completed_hops_are_admitted(self):
        self.completed_hops(20)
        self.assertEqual(len(chain._rows()), 40)

    def test_thirty_completed_hops_limit_and_next_refused(self):
        self.completed_hops(30)
        with self.assertRaisesRegex(chain.LoopRefused, 'fleet started 30'):
            self.admit(30, agent='agent-2')
        self.assertEqual(sum(r['kind'] == 'hop' for r in chain._rows()), 30)

    def test_original_mutation_is_detected(self):
        corrected = chain._verdict
        original = inspect.getsource(corrected)
        needle = "r.get('kind', 'hop') == 'hop' and "
        self.assertEqual(original.count(needle), 1)
        namespace = dict(vars(chain))
        exec(original.replace(needle, '', 1), namespace)
        # Use the live module globals, including the isolated test ledger.
        mutated = FunctionType(namespace['_verdict'].__code__, vars(chain))
        with patch.object(chain, '_verdict', mutated):
            # The same twenty-hop acceptance must fail under the old rule.
            with self.assertRaisesRegex(chain.LoopRefused, 'fleet started 30'):
                self.completed_hops(20)
            rows = chain._rows()
            self.assertEqual(sum(r['kind'] == 'hop' for r in rows), 15)
            self.assertEqual(sum(r['kind'] == 'outcome' for r in rows), 15)
            self.assertEqual(chain.LEDGER, self.root / 'ledger.jsonl')
        self.assertIs(chain._verdict, corrected)
        # The corrected rule admits the refused hop against the same rows.
        self.admit(15, agent='agent-3')
        self.assertEqual(sum(r['kind'] == 'hop' for r in chain._rows()), 16)

    def test_callback_then_cycle(self):
        self.admit(0, prompt='same', context='cycle')
        self.admit(1, prompt='same', context='cycle', refs=['t0'])
        with self.assertRaisesRegex(chain.LoopRefused, 'cycle'):
            self.admit(2, prompt='same', context='cycle', refs=['t0','t1'])

    def test_legal_callback_different_question(self):
        self.admit(0, context='callback')
        self.admit(1, agent='agent-b', context='callback', refs=['t0'])
        self.admit(2, context='callback', refs=['t0','t1'])
        self.assertEqual(chain._rows()[-1]['from'], 'agent-b')

    def test_depth_boundary(self):
        self.admit(0, refs=['x'] * (chain.MAX_DEPTH - 1))
        with self.assertRaisesRegex(chain.LoopRefused, 'depth'):
            self.admit(1, refs=['x'] * chain.MAX_DEPTH)

    def test_context_isolation_and_whitespace(self):
        self.admit(0, prompt='same   question', context='one')
        self.admit(1, prompt='same\nquestion', context='one')
        self.admit(2, prompt='same question', context='two')
        with self.assertRaises(chain.LoopRefused):
            self.admit(3, prompt='same question', context='one')

    def test_paraphrase_new_context_hits_per_agent_breaker(self):
        for i in range(chain.BREAKER_MAX):
            self.admit(i)
        with self.assertRaisesRegex(chain.LoopRefused, 'circuit breaker'):
            self.admit(chain.BREAKER_MAX)

    def test_window_expiry(self):
        with patch.object(chain.time, 'time', return_value=time.time() - chain.BREAKER_WINDOW_S - 1):
            self.completed_hops(30)
        self.admit(31)

    def test_concurrent_identical_admission(self):
        def one(i):
            try:
                self.admit(i, prompt='identical', context='race')
                return True
            except chain.LoopRefused:
                return False
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(one, range(10)))
        self.assertEqual(sum(results), chain.MAX_REPEAT)

    def test_rotating_names_hits_fleet_breaker(self):
        for i in range(30):
            self.admit(i, agent=f'agent-{i % 4}')
        with self.assertRaises(chain.LoopRefused):
            self.admit(30, agent='fresh-name')

    def test_swapped_lock_refuses(self):
        lock = chain.LEDGER.with_suffix('.lock')
        real_stat = os.stat
        def swapping(path, *args, **kwargs):
            if Path(path) == lock:
                lock.unlink(missing_ok=True)
                lock.touch()
            return real_stat(path, *args, **kwargs)
        with patch.object(chain.os, 'stat', side_effect=swapping):
            with self.assertRaisesRegex(chain.LoopRefused, 'lock'):
                self.admit(0)

    def test_corrupt_line_and_legacy_rows(self):
        row = {'epoch':time.time(),'agent':'agent-a','context_id':'torn','fp':chain.fingerprint('same')}
        chain.LEDGER.write_text('{torn\n' + (json.dumps(row)+'\n')*2)
        with self.assertRaises(chain.LoopRefused):
            self.admit(0, prompt='same', context='torn')

    def test_refusal_marker(self):
        self.assertTrue(chain.is_refusal(chain.REFUSAL_MARK + ' cycle'))
        self.assertFalse(chain.is_refusal('normal answer'))

    def test_argv_is_not_reparsed(self):
        runner = ProcessRunner('stub', 'echo {prompt} {session}')
        prompt = 'hello; $(date) "quoted"'
        self.assertEqual(runner._argv(prompt,'session'), ['echo',prompt,'session'])

    def test_denoise_three_reproductions(self):
        runner = ProcessRunner('stub', 'echo {prompt}', drop_line_regex=r'^\[[^]]+\]')
        for text in ('[error] provider auth failed\nfinal answer',
                     '[fatal] cannot load credential\npartial reply',
                     '[401] unauthorized\nhere is your summary'):
            with self.subTest(text=text):
                self.assertIn(text.splitlines()[0], runner._denoise(text))
        self.assertEqual(runner._denoise('[noise] startup\nANSWER'), 'ANSWER')
        self.assertEqual(runner._denoise('- apples\n- oranges'), '- apples\n- oranges')
        self.assertEqual(runner._denoise('[noise] only'), '[noise] only')

    def test_process_tree_timeout(self):
        marker = self.root / 'grandchild.txt'
        runner = ProcessRunner('tree', 'unused', timeout_s=1)
        argv = [sys.executable,'fixtures/stub_agent.py','tree',str(marker.resolve())]
        output = asyncio.run(runner._run(argv, dict(os.environ)))
        self.assertIn('timed out', output)
        time.sleep(3)
        self.assertFalse(marker.exists())

    def test_missing_executable_is_agent_text(self):
        runner = ProcessRunner('stub', 'unused')
        output = asyncio.run(runner._run([str(self.root / 'absent')], dict(os.environ)))
        self.assertIn('not runnable: FileNotFoundError', output)

    def test_registry_driven_services(self):
        output = dict(generate_services.definitions(str(Path.cwd()), sys.executable))
        self.assertEqual(set(output), set(cards._load_registry()))
        self.assertTrue(all(p['KeepAlive'] == {'SuccessfulExit':False} for p in output.values()))

    def test_stop_file_exits_before_optional_imports(self):
        (self.root / 'disabled').touch()
        result = subprocess.run([sys.executable,'scripts/serve.py','agent-a'],
                 env=dict(os.environ, COORD_STATE_DIR=str(self.root)), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'hub disabled; exiting cleanly')

    def test_token_permissions_and_symlink(self):
        with patch.object(token_store, 'TOKEN_PATH', self.root / 'token'), patch.dict(os.environ, {}, clear=True):
            value = token_store.load_or_create_token()
            self.assertTrue(value)
            self.assertEqual((self.root/'token').stat().st_mode & 0o777, 0o600)
            self.assertEqual(token_store.load_or_create_token(), value)
            (self.root/'token').chmod(0o644)
            with self.assertRaises(RuntimeError):
                token_store.load_or_create_token()
            (self.root/'token').unlink()
            (self.root/'target').write_text('synthetic')
            (self.root/'token').symlink_to('target')
            with self.assertRaises(RuntimeError):
                token_store.load_or_create_token()

    def test_four_by_four_offline_matrix(self):
        # run_matrix() preserves the caller's cap; only the CLI sets its own.
        with patch.object(chain, 'BREAKER_FLEET_MAX', 4*4*2):
            results = asyncio.run(matrix_test.run_matrix(list(cards._load_registry())))
        self.assertEqual(len(results), 16)
        self.assertTrue(all(r['ok'] for r in results))
        rows = chain._rows()
        self.assertEqual(sum(r['kind']=='hop' for r in rows), 32)
        self.assertEqual(sum(r['kind']=='outcome' for r in rows), 32)
