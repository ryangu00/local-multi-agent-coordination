"""Explicit protocol dependency mocks: these tests make no HTTP or MCP calls.

They exercise the shipped helpers and adapter wiring, not SDK compatibility.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chain


class Record:
    def __init__(self, **kwargs):
        self.context_id = ''
        self.task_id = ''
        self.reference_task_ids = []
        self.parts = []
        self.__dict__.update(kwargs)


def module(name, **fields):
    item=ModuleType(name)
    item.__dict__.update(fields)
    return item


def load(name):
    spec=importlib.util.spec_from_file_location('fixture_'+name,Path('scripts')/(name+'.py'))
    item=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(item)
    return item


class ProtocolMocks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='.')
        self.old=chain.LEDGER
        chain.LEDGER=Path(self.temp.name)/'ledger.jsonl'
        self.requests=[]
        async def messages(request):
            self.requests.append(request)
            yield Record(message=Record(parts=[Record(text='synthetic answer')]))
        class HTTP:
            def __init__(self,**kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self,*args):
                pass
        client=Record(send_message=messages)
        class Factory:
            def __init__(self,*args):
                pass
            def create(self,card):
                return client
        self.modules=patch.dict(sys.modules,{
            'a2a':module('a2a'),
            'a2a.server':module('a2a.server'),
            'a2a.server.agent_execution':module('a2a.server.agent_execution',AgentExecutor=object,RequestContext=Record),
            'a2a.server.events':module('a2a.server.events',EventQueue=Record),
            'a2a.types':module('a2a.types',Message=Record,Part=Record,
                Role=Record(ROLE_AGENT='agent',ROLE_USER='user'),
                SendMessageConfiguration=Record,SendMessageRequest=Record),
            'a2a.client':module('a2a.client',ClientFactory=Factory,ClientConfig=Record),
            'httpx':module('httpx',AsyncClient=HTTP),
        })
        self.modules.start()

    def tearDown(self):
        self.modules.stop()
        chain.LEDGER=self.old
        self.temp.cleanup()

    def test_call_merges_inherited_references_without_separator_split(self):
        helper=load('call')
        with patch.object(helper.cards,'build_card',return_value=Record()),patch.object(helper,'load_or_create_token',return_value='synthetic-token'),patch.dict(os.environ,{
             'LOCAL_HUB_CONTEXT':'synthetic-context','LOCAL_HUB_TASK':'parent,with-comma',
             'LOCAL_HUB_REFS':json.dumps(['ancestor,with-comma'])}):
            self.assertEqual(asyncio.run(helper.call('agent-a','prompt',refs=['extra','ancestor,with-comma'])),'synthetic answer')
        message=self.requests[0].message
        self.assertEqual(message.context_id,'synthetic-context')
        self.assertEqual(message.reference_task_ids,['ancestor,with-comma','parent,with-comma','extra'])

    def test_adapter_runs_stub_records_outcome_exports_chain(self):
        adapter=load('cli_agent_executor')
        executor=adapter.CliAgentExecutor('agent-a','python3 fixtures/stub_agent.py echo {prompt}')
        context=Record(message=Record(context_id='context',task_id='task',reference_task_ids=['ref,comma']),
                       get_user_input=lambda:'synthetic-token')
        queue=Record(enqueue_event=AsyncMock())
        real_run=executor._run
        environments=[]
        async def run(argv,env):
            environments.append(env)
            return await real_run(argv,env)
        with patch.object(executor,'_run',side_effect=run):
            asyncio.run(executor.execute(context,queue))
        self.assertEqual(queue.enqueue_event.call_args.args[0].parts[0].text,'synthetic-token')
        self.assertEqual(json.loads(environments[0]['LOCAL_HUB_REFS']),['ref,comma'])
        self.assertEqual([r['kind'] for r in chain._rows()],['hop','outcome'])

    def test_adapter_refuses_before_process_spawn(self):
        adapter=load('cli_agent_executor')
        executor=adapter.CliAgentExecutor('agent-a','unused')
        context=Record(message=Record(context_id='context',task_id='task',reference_task_ids=['ref']*6),
                       get_user_input=lambda:'synthetic')
        queue=Record(enqueue_event=AsyncMock())
        with patch.object(executor,'_run',new_callable=AsyncMock) as run:
            asyncio.run(executor.execute(context,queue))
            run.assert_not_called()
        self.assertTrue(chain.is_refusal(queue.enqueue_event.call_args.args[0].parts[0].text))

    def test_fanout_partial_timeout_refusal_and_failure(self):
        async def fake_call(agent,*args):
            if agent=='slow':
                await asyncio.sleep(6)
            if agent=='refused':
                return chain.REFUSAL_MARK+' synthetic'
            if agent=='failed':
                raise RuntimeError('synthetic transport failure')
            return 'synthetic answer'
        with patch.dict(sys.modules,{'call':module('call',call=fake_call)}):
            helper=load('fanout')
        with patch.dict(os.environ):
            result=asyncio.run(helper.fanout('prompt',['answered','slow','refused','failed'],deadline=0.01))
        self.assertEqual(result['asked'],4)
        self.assertEqual(result['answered'],1)
        self.assertEqual({r['agent'] for r in result['results'] if not r['ok']},{'slow','refused','failed'})

    def test_fanout_nobody_answered_exit_nonzero(self):
        async def refused(*args):
            return chain.REFUSAL_MARK+' synthetic'
        with patch.dict(sys.modules,{'call':module('call',call=refused)}):
            helper=load('fanout')
        with patch.dict(os.environ),patch.object(sys,'argv',['fanout.py','prompt','refused']),patch('builtins.print'):
            self.assertEqual(helper.main(),1)
