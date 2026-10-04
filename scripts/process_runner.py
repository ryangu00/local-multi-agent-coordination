"""Subprocess half of the adapter, testable without the protocol SDK.

Whole-argv substitution, bounded concurrency, error-preserving denoise,
DEVNULL stdin, and process-group timeout/cancellation cleanup.
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
DEFAULT_MAX_CONCURRENCY = 4
_ERROR_LINE = re.compile('\\b(error|fatal|denied|unauthorized|forbidden|traceback|exception|refused|failed|failure|timed out|not permitted|no such)\\b', re.IGNORECASE)

class ProcessRunner:

    def __init__(self, name: str, command_template: str, timeout_s: int=600, max_concurrency: int=DEFAULT_MAX_CONCURRENCY, env_unset: tuple[str, ...]=(), env_set: dict[str, str] | None=None, drop_line_regex: str='', cwd: str='') -> None:
        if max_concurrency < 1:
            raise ValueError(f'{name}: max_concurrency must be >= 1, got {max_concurrency}')
        if timeout_s < 1:
            raise ValueError(f'{name}: timeout_s must be >= 1, got {timeout_s}')
        self.name = name
        self.command_template = command_template
        self.timeout_s = timeout_s
        self.env_unset = tuple(env_unset)
        self.env_set = dict(env_set or {})
        self._drop = re.compile(drop_line_regex) if drop_line_regex else None
        self.cwd = cwd or None
        self._slots = asyncio.Semaphore(max_concurrency)

    def _denoise(self, text: str) -> str:
        if not self._drop:
            return text
        kept = '\n'.join((line for line in text.splitlines() if _ERROR_LINE.search(line) or not self._drop.match(line))).strip()
        return kept or text

    def _argv(self, prompt: str, session: str) -> list[str]:
        subs = {'{prompt}': prompt, '{session}': session}
        return [subs.get(part, part) for part in shlex.split(self.command_template)]

    @staticmethod
    async def _terminate(proc) -> None:
        if proc is None or proc.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()

    async def _run(self, argv: list[str], env: dict) -> str:
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env, cwd=self.cwd, start_new_session=True)
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s)
            body = self._denoise((stdout or b'').decode('utf-8', errors='replace').strip())
            if proc.returncode != 0:
                body = f'[{self.name} exited {proc.returncode}]\n{body}'
            return body
        except asyncio.TimeoutError:
            await self._terminate(proc)
            return f'[{self.name} timed out after {self.timeout_s}s; child killed]'
        except asyncio.CancelledError:
            await self._terminate(proc)
            raise
        except OSError as err:
            return f'[{self.name} not runnable: {type(err).__name__}: {err}]'
