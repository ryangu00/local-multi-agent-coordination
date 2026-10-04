"""User-only token file; never print its contents."""
from __future__ import annotations
import os
import pathlib
import secrets
import stat
TOKEN_PATH = pathlib.Path(os.environ.get('COORD_STATE_DIR', './state')) / 'token'
PUBLIC_PATHS = frozenset({'/.well-known/agent-card.json'})

def load_or_create_token() -> str:
    if (env := os.environ.get('LOCAL_HUB_TOKEN')):
        return env
    if TOKEN_PATH.exists():
        st = TOKEN_PATH.lstat()
        if stat.S_ISLNK(st.st_mode):
            raise RuntimeError(f'{TOKEN_PATH} is a symlink; refusing to read it')
        if st.st_uid != os.getuid():
            raise RuntimeError(f'{TOKEN_PATH} is not owned by this user')
        if st.st_mode & 0o077:
            raise RuntimeError(f'{TOKEN_PATH} is group/world accessible ({st.st_mode & 0o777:o}); run: chmod 600 on it')
        return TOKEN_PATH.read_text().strip()
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as fh:
        fh.write(token)
    return token
