"""Adapted ledger: atomic admission; outcomes do not spend session budget.

Defaults are reasoned starting values, not calibrated thresholds.
Rows without a kind remain compatible historical hop rows.
"""
from __future__ import annotations
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import time
LEDGER = pathlib.Path(os.environ.get('COORD_LEDGER_PATH') or (pathlib.Path(os.environ.get('COORD_STATE_DIR', './state')) / 'chain-ledger.jsonl'))
MAX_DEPTH = 6
MAX_REPEAT = 2
BREAKER_WINDOW_S = 300
BREAKER_MAX = 12
BREAKER_FLEET_MAX = 30
REFUSAL_MARK = '[local-hub:refused]'

class LoopRefused(Exception):
    pass

def is_refusal(text: str) -> bool:
    return REFUSAL_MARK in (text or '')

def fingerprint(prompt: str) -> str:
    return hashlib.sha256(' '.join(prompt.split()).encode()).hexdigest()[:16]

@contextlib.contextmanager
def _locked():
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    lock = LEDGER.with_suffix('.lock')
    for _ in range(5):
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            if os.fstat(fd).st_ino == os.stat(lock).st_ino:
                try:
                    yield
                finally:
                    with contextlib.suppress(Exception):
                        fcntl.flock(fd, fcntl.LOCK_UN)
                return
        except FileNotFoundError:
            pass
        finally:
            os.close(fd)
    raise LoopRefused('could not hold the chain ledger lock after 5 attempts; refusing rather than admitting a hop without serialisation')

def _rows():
    if not LEDGER.exists():
        return []
    out = []
    with LEDGER.open() as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out

def _append(row: dict) -> None:
    with os.fdopen(os.open(LEDGER, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), 'a') as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + '\n')

def _verdict(rows, context_id: str, agent: str, fp: str, depth: int) -> str | None:
    if depth >= MAX_DEPTH:
        return f"chain depth {depth} reached the limit of {MAX_DEPTH} (context {context_id or 'none'}); refusing to extend it"
    now = time.time()
    in_window = [r for r in rows if r.get('kind', 'hop') == 'hop' and now - r.get('epoch', 0) < BREAKER_WINDOW_S]
    recent = sum((1 for r in in_window if r.get('agent') == agent))
    if recent >= BREAKER_MAX:
        return f'circuit breaker: {agent} started {recent} sessions in the last {BREAKER_WINDOW_S}s (limit {BREAKER_MAX}); refusing regardless of context'
    if len(in_window) >= BREAKER_FLEET_MAX:
        return f'circuit breaker: the fleet started {len(in_window)} sessions in the last {BREAKER_WINDOW_S}s (limit {BREAKER_FLEET_MAX}); rotating between agents does not buy more headroom'
    if context_id:
        seen = sum((1 for r in rows if r.get('context_id') == context_id and r.get('agent') == agent and (r.get('fp') == fp)))
        if seen >= MAX_REPEAT:
            return f'{agent} has already been asked this same question {seen}x in context {context_id}; treating it as a cycle rather than a callback'
    return None

def complete(task_id: str, ok: bool, ms: int, chars: int) -> None:
    try:
        with _locked():
            _append({'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'epoch': time.time(), 'kind': 'outcome', 'task_id': task_id, 'ok': ok, 'ms': ms, 'result_chars': chars})
    except Exception:
        pass

def _caller_of(rows, refs: list[str]) -> str:
    if not refs:
        return 'external'
    parent = refs[-1]
    for r in reversed(rows):
        if r.get('kind') == 'hop' and r.get('task_id') == parent:
            return r.get('to') or r.get('agent') or 'unknown'
    return 'unknown'

def admit(context_id: str, task_id: str, agent: str, prompt: str, refs: list[str], mode: str='single') -> None:
    fp = fingerprint(prompt)
    depth = len(refs)
    with _locked():
        rows = _rows()
        why = _verdict(rows, context_id, agent, fp, depth)
        if why:
            raise LoopRefused(why)
        caller = _caller_of(rows, refs)
        _append({'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'epoch': time.time(), 'kind': 'hop', 'context_id': context_id, 'task_id': task_id, 'from': caller or 'external', 'to': agent, 'agent': agent, 'mode': mode, 'fp': fp, 'refs': list(refs), 'depth': depth})
