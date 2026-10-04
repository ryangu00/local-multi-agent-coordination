"""Synthetic CLI only. Echo, slow, noisy, process-tree, and delegation fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import time

mode, prompt = sys.argv[1:3]
if mode == 'echo':
    # Only a synthetic matrix request triggers a nested official helper call.
    if prompt.startswith('{') and '"target"' in prompt:
        request = json.loads(prompt)
        subprocess.run([sys.executable, "-B", str(Path(__file__).resolve().parents[1] / 'scripts/call.py'),
                        request['target'], request['token']], check=True)
    else:
        print(prompt)
elif mode == 'noisy':
    print('[noise] synthetic startup')
    print(prompt)
elif mode == 'slow':
    time.sleep(6)
    print(prompt)
elif mode == 'tree':
    subprocess.Popen([sys.executable, '-c',
        'import time,pathlib,sys; time.sleep(3); pathlib.Path(sys.argv[1]).write_text("alive")', prompt])
    time.sleep(30)
elif mode == 'delegate':
    # The matrix uses a local subprocess route, never claims A2A conformance.
    request = json.loads(prompt)
    subprocess.run([sys.executable, "-B", str(Path(__file__).resolve().parents[1] / 'scripts/mock_call.py'),
                    request['target'], request['token']], check=True)
else:
    raise SystemExit('unknown synthetic mode')
