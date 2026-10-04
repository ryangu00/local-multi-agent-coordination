"""Optional real loopback transport check, only with packages already installed.

This does not install anything. It runs synthetic CLI stubs, not remote agents.
All files and ephemeral server processes belong to this invocation.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def main():
    missing = [name for name in ('a2a', 'fastapi', 'uvicorn', 'httpx')
               if importlib.util.find_spec(name) is None]
    if missing:
        print('UNEXECUTED: missing optional packages: ' + ', '.join(missing))
        return 2
    with tempfile.TemporaryDirectory(dir='.') as scratch:
        root = Path(scratch).resolve()
        ports = []
        for _ in range(2):
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                ports.append(sock.getsockname()[1])
        registry = root / 'agents.toml'
        registry.write_text('\n'.join(
            f'[{name}]\nport={port}\nmax_concurrency=6\ntimeout_s=6\n'
            'command="python3 fixtures/stub_agent.py echo {prompt}"\nskills=["echo"]\n'
            for name, port in zip(('agent-a','agent-b'), ports)))
        os.environ.update(COORD_STATE_DIR=str(root), COORD_REGISTRY=str(registry))
        import cards
        import chain
        import token_store
        from call import call
        from fanout import fanout
        cards.REGISTRY = registry
        chain.LEDGER = root / 'chain-ledger.jsonl'
        token_store.TOKEN_PATH = root / 'token'
        token_store.load_or_create_token()
        servers = []
        try:
            for name in ('agent-a','agent-b'):
                servers.append(subprocess.Popen([sys.executable,'-B','scripts/serve.py',name],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True))
            for port in ports:
                deadline = time.monotonic() + 30
                while True:
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/.well-known/agent-card.json',timeout=1) as response:
                            assert response.status == 200
                            break
                    except (urllib.error.URLError, TimeoutError):
                        if time.monotonic() >= deadline or any(p.poll() is not None for p in servers):
                            raise RuntimeError('synthetic SDK server did not become ready')
                        time.sleep(0.1)
            request = urllib.request.Request(f'http://127.0.0.1:{ports[0]}/', data=b'{}', headers={'Content-Type':'application/json'})
            try:
                urllib.request.urlopen(request)
                raise AssertionError('unauthenticated request unexpectedly accepted')
            except urllib.error.HTTPError as error:
                assert error.code == 401
            async def checks():
                assert await call('agent-a','synthetic-token') == 'synthetic-token'
                prompt=json.dumps({'target':'agent-b','token':'SYNTHETICTOKEN'})
                assert await call('agent-a',prompt) == 'SYNTHETICTOKEN'
                result=await fanout('synthetic-token',['agent-a','agent-b'],deadline=6)
                assert result['answered'] == 2
                for i in range(chain.BREAKER_MAX):
                    reply=await call('agent-a',f'distinct question {i}')
                    if chain.is_refusal(reply):
                        break
                else:
                    raise AssertionError('expected per-agent loop refusal')
            asyncio.run(checks())
            print('SDK loopback: card/auth, call, nested call, fan-out, refusal PASS')
            return 0
        finally:
            for process in servers:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == '__main__':
    raise SystemExit(main())
