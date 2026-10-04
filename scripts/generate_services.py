"""Print one registry-driven launchd plist. Never install or load a service."""
import argparse
from pathlib import Path
import plistlib
import sys
import cards


def definitions(root, python):
    root = Path(root)
    if not root.is_absolute() or not Path(python).is_absolute():
        raise ValueError('supply absolute local paths at generation time')
    for name in cards._load_registry():
        yield name, {
            'Label': 'local.coordination.' + name,
            'ProgramArguments': [python, str(root / 'scripts/serve.py'), name],
            'WorkingDirectory': str(root), 'RunAtLoad': True,
            'KeepAlive': {'SuccessfulExit': False}, 'ThrottleInterval': 10,
            'EnvironmentVariables': {'COORD_STATE_DIR': str(root / 'state')},
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--python', required=True)
    parser.add_argument('--agent', required=True)
    args = parser.parse_args()
    found = dict(definitions(args.root, args.python))
    sys.stdout.buffer.write(plistlib.dumps(found[args.agent]))
