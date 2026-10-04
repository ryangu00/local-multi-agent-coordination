"""Offline subprocess route for fixtures; deliberately not an A2A transport."""
import asyncio
import json
import os
import sys
import time
import uuid
import cards
import chain
from process_runner import ProcessRunner


async def call_local(agent, prompt, delegate=False):
    spec = cards._load_registry()[agent]
    context = os.environ.get('LOCAL_HUB_CONTEXT') or uuid.uuid4().hex
    task = uuid.uuid4().hex
    refs = json.loads(os.environ.get('LOCAL_HUB_REFS', '[]'))
    parent = os.environ.get('LOCAL_HUB_TASK')
    if parent and parent not in refs:
        refs.append(parent)
    try:
        chain.admit(context, task, agent, prompt, refs)
    except chain.LoopRefused as error:
        return chain.REFUSAL_MARK + ' ' + str(error)
    command = 'python3 -B fixtures/stub_agent.py delegate {prompt}' if delegate else spec['command']
    runner = ProcessRunner(agent, command, timeout_s=spec['timeout_s'],
                           max_concurrency=spec['max_concurrency'],
                           drop_line_regex=spec.get('drop_line_regex', ''))
    env = dict(os.environ, COORD_LEDGER_PATH=str(chain.LEDGER.resolve()),
               COORD_REGISTRY=str(cards.REGISTRY.resolve()),
               COORD_MOCK_FLEET_CAP=str(chain.BREAKER_FLEET_MAX),
               LOCAL_HUB_CONTEXT=context, LOCAL_HUB_TASK=task,
               LOCAL_HUB_REFS=json.dumps(refs))
    started = time.monotonic()
    result = await runner._run(runner._argv(prompt, context), env)
    chain.complete(task, not chain.is_refusal(result) and not result.startswith(f'[{agent} '),
                   int((time.monotonic()-started)*1000), len(result))
    return result


if __name__ == '__main__':
    # Only the explicit mock route inherits its parent's isolated test cap.
    chain.BREAKER_FLEET_MAX = int(os.environ.get('COORD_MOCK_FLEET_CAP', chain.BREAKER_FLEET_MAX))
    print(asyncio.run(call_local(sys.argv[1], sys.argv[2])))
