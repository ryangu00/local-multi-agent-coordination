"""Run corrected logic and an in-memory mutation of the original counting bug."""
import inspect
from pathlib import Path
import tempfile
import chain


def admitted(verdict, outcomes):
    original, ledger = chain._verdict, chain.LEDGER
    try:
        with tempfile.TemporaryDirectory(dir='.') as directory:
            chain.LEDGER = Path(directory) / 'ledger.jsonl'
            chain._verdict = verdict
            count = 0
            for i in range(chain.BREAKER_FLEET_MAX + 1):
                try:
                    chain.admit(f'ctx{i}', f'task{i}', f'agent-{i % 4}', f'question {i}', [])
                except chain.LoopRefused:
                    return count
                if outcomes:
                    chain.complete(f'task{i}', True, 0, 0)
                count += 1
            return count
    finally:
        chain._verdict, chain.LEDGER = original, ledger


if __name__ == '__main__':
    namespace = dict(vars(chain))
    source = inspect.getsource(chain._verdict)
    mutation = "r.get('kind', 'hop') == 'hop' and "
    assert mutation in source
    exec(source.replace(mutation, ''), namespace)
    old = namespace['_verdict']
    values = (admitted(old, True), admitted(old, False), admitted(chain._verdict, True))
    print('original with outcomes:', values[0])
    print('original without outcomes:', values[1])
    print('corrected with outcomes:', values[2])
    assert values == (15, 30, 30)
