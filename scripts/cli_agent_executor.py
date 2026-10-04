"""Official A2A adapter; requires a2a-sdk 1.1.2.

The process runner is shared with the stdlib offline tests.
"""
from __future__ import annotations
import asyncio
import contextlib
import json
import os
import pathlib
import signal
import re
import shlex
import sys
import time
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Message, Part, Role
import chain as chain_mod
from process_runner import ProcessRunner

def _agent_text(text: str, context_id: str='', task_id: str='') -> Message:
    msg = Message(role=Role.ROLE_AGENT, parts=[Part(text=text)])
    if context_id:
        msg.context_id = context_id
    if task_id:
        msg.task_id = task_id
    return msg

class CliAgentExecutor(ProcessRunner, AgentExecutor):

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        prompt = context.get_user_input()
        chain = {'context_id': getattr(context.message, 'context_id', '') or '', 'task_id': getattr(context.message, 'task_id', '') or '', 'reference_task_ids': list(getattr(context.message, 'reference_task_ids', []))}
        try:
            chain_mod.admit(chain['context_id'], chain['task_id'], self.name, prompt, chain['reference_task_ids'], mode='fanout' if os.environ.get('LOCAL_HUB_MODE') == 'fanout' else 'chained' if chain['reference_task_ids'] else 'single')
        except chain_mod.LoopRefused as err:
            await event_queue.enqueue_event(_agent_text(f'{chain_mod.REFUSAL_MARK} {self.name}: {err}', chain['context_id'], chain['task_id']))
            return
        env = {**os.environ, 'LOCAL_HUB_AGENT': self.name, 'LOCAL_HUB_CONTEXT': chain['context_id'], 'LOCAL_HUB_TASK': chain['task_id'], 'LOCAL_HUB_REFS': json.dumps(chain['reference_task_ids'])}
        for key in self.env_unset:
            env.pop(key, None)
        env.update(self.env_set)
        argv = self._argv(prompt, chain['context_id'] or 'local-hub')
        started = time.monotonic()
        async with self._slots:
            body = await self._run(argv, env)
        chain_mod.complete(chain['task_id'], ok=not body.startswith(f'[{self.name} '), ms=int((time.monotonic() - started) * 1000), chars=len(body))
        await event_queue.enqueue_event(_agent_text(body, chain['context_id'], chain['task_id']))
        self.last_chain = chain

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(_agent_text(f'[{self.name}] cancellation is not supported'))
