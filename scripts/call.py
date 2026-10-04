"""Adapted official-SDK helper; use tests for the offline mock route."""
from __future__ import annotations
import asyncio
import json
import os
import sys
import uuid
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import Message, Part, Role, SendMessageConfiguration, SendMessageRequest
import cards
from token_store import load_or_create_token

async def call(agent: str, prompt: str, context_id: str='', refs: list[str] | None=None) -> str:
    spec = cards._load_registry()[agent]
    card = cards.build_card(agent, spec)
    token = load_or_create_token()
    async with httpx.AsyncClient(timeout=1800, headers={'Authorization': f'Bearer {token}'}) as http:
        client = ClientFactory(ClientConfig(httpx_client=http)).create(card)
        msg = Message(message_id=uuid.uuid4().hex, role=Role.ROLE_USER, parts=[Part(text=prompt)])
        msg.context_id = context_id or os.environ.get('LOCAL_HUB_CONTEXT') or f'ctx-{uuid.uuid4().hex[:8]}'
        try:
            inherited = json.loads(os.environ.get('LOCAL_HUB_REFS') or '[]')
        except ValueError:
            inherited = []
        parent = os.environ.get('LOCAL_HUB_TASK', '')
        if parent:
            inherited.append(parent)
        for task in list(inherited) + list(refs or []):
            if task and task not in msg.reference_task_ids:
                msg.reference_task_ids.append(task)
        req = SendMessageRequest(message=msg, configuration=SendMessageConfiguration())
        chunks: list[str] = []
        async for event in client.send_message(req):
            msg = getattr(event, 'message', None)
            if msg is not None and getattr(msg, 'parts', None):
                chunks += [p.text for p in msg.parts if getattr(p, 'text', '')]
            task = getattr(event, 'task', None)
            if task is not None:
                for art in getattr(task, 'artifacts', []) or []:
                    chunks += [p.text for p in getattr(art, 'parts', []) if getattr(p, 'text', '')]
        return '\n'.join(chunks).strip()
if __name__ == '__main__':
    agent, prompt = (sys.argv[1], sys.argv[2])
    ctx = sys.argv[3] if len(sys.argv) > 3 else ''
    refs = sys.argv[4:] if len(sys.argv) > 4 else []
    print(asyncio.run(call(agent, prompt, ctx, refs)))
