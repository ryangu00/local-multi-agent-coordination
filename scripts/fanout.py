"""Adapted official-SDK helper; use tests for the offline mock route."""
from __future__ import annotations
import asyncio
import os
import sys
import time
import uuid
import cards
import chain
from call import call
DEFAULT_DEADLINE_S = 600

async def _one(agent: str, prompt: str, context_id: str, deadline: float) -> dict:
    started = time.monotonic()
    try:
        reply = await asyncio.wait_for(call(agent, prompt, context_id), timeout=deadline)
        if chain.is_refusal(reply):
            return {'agent': agent, 'ok': False, 'error': reply, 'seconds': round(time.monotonic() - started, 1)}
        return {'agent': agent, 'ok': True, 'reply': reply, 'seconds': round(time.monotonic() - started, 1)}
    except asyncio.TimeoutError:
        return {'agent': agent, 'ok': False, 'error': f'deadline {deadline}s exceeded', 'seconds': round(time.monotonic() - started, 1)}
    except Exception as err:
        return {'agent': agent, 'ok': False, 'error': f'{type(err).__name__}: {err}', 'seconds': round(time.monotonic() - started, 1)}

async def fanout(prompt: str, agents: list[str] | None=None, context_id: str='', deadline: float=DEFAULT_DEADLINE_S) -> dict:
    targets = agents or list(cards._load_registry())
    os.environ['LOCAL_HUB_MODE'] = 'fanout'
    ctx = context_id or os.environ.get('LOCAL_HUB_CONTEXT') or f'fan-{uuid.uuid4().hex[:8]}'
    results = await asyncio.gather(*(_one(a, prompt, ctx, deadline) for a in targets))
    return {'context_id': ctx, 'asked': len(targets), 'answered': sum((1 for r in results if r['ok'])), 'results': list(results)}

def main() -> int:
    prompt = sys.argv[1]
    agents = sys.argv[2:] or None
    out = asyncio.run(fanout(prompt, agents))
    print(f"context={out['context_id']}  {out['answered']}/{out['asked']} answered\n")
    for r in out['results']:
        if r['ok']:
            print(f"── {r['agent']} ({r['seconds']}s) ──\n{r['reply']}\n")
        else:
            print(f"── {r['agent']} ({r['seconds']}s) no answer ──\n{r['error']}\n")
    return 0 if out['answered'] else 1
if __name__ == '__main__':
    raise SystemExit(main())
