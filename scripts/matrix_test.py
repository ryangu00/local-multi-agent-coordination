"""Row-paced matrix. Default: offline subprocess mock, not a live A2A result."""
import argparse
import asyncio
from pathlib import Path
import sys
import tempfile
import uuid

import cards
import chain
from process_runner import ProcessRunner


async def run_matrix(names, by_row=True, sdk=False):
    specs = cards._load_registry()
    if sdk:
        from call import call
    async def cell(caller, target):
        token = 'PONG' + uuid.uuid4().hex.upper()
        if sdk:
            # Stub understands a deterministic request, without model interpretation.
            import json
            prompt = json.dumps({'target': target, 'token': token})
            reply = await call(caller, prompt)
        else:
            # A parent stub delegates through a subprocess helper; the helper
            # reads the target's config, inherits the chain, and admits itself.
            import json
            from mock_call import call_local
            reply = await call_local(caller, json.dumps({'target': target, 'token': token}), delegate=True)
        return {'caller': caller, 'target': target, 'ok': reply == token}
    results = []
    if by_row:
        for caller in names:
            results.extend(await asyncio.gather(*(cell(caller, target) for target in names)))
    else:
        results = await asyncio.gather(*(cell(c, t) for c in names for t in names))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--by-row', action='store_true')
    parser.add_argument('--sdk', action='store_true')
    parser.add_argument('agents', nargs='*')
    args = parser.parse_args()
    if args.sdk:
        results = asyncio.run(run_matrix(args.agents or list(cards._load_registry()), args.by_row, True))
    else:
        # A full matrix exceeds the default fleet cap. This isolated fixture
        # explicitly raises it to the required number of hops, never live state.
        with tempfile.TemporaryDirectory(dir='.') as scratch:
            chain.LEDGER = Path(scratch) / 'ledger.jsonl'
            names = args.agents or list(cards._load_registry())
            chain.BREAKER_FLEET_MAX = len(names) * len(names) * 2
            results = asyncio.run(run_matrix(names, args.by_row))
    for result in results:
        print(result['caller'], '->', result['target'], 'PASS' if result['ok'] else 'FAIL')
    print('matrix:', sum(r['ok'] for r in results), '/', len(results), 'passed')
    raise SystemExit(not all(r['ok'] for r in results))
