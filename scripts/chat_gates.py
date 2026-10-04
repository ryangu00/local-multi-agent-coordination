"""Portable chat gate net, adapted with English cores and an injected registry.

Fail-open is intentional: this is not a permission boundary. Call once at the
finalize point, before posting. Audit rows contain hashes, never message text.
"""
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time

ACK_TTL = 8
COOLDOWN = 60
MAX_SILENCE_LEN = 30
NAME_TO_ID = {}
BOT_IDS = set()
SILENCE_CORES = frozenset({'', 'ack', 'noop', 'no-op', 'no op', 'silent',
    'staying silent', 'stay silent', 'no response', 'no reply', 'review_pass',
    'review pass', 'pass'})
TRIVIAL = frozenset({'', 'ok', 'okay', 'k', 'noted', 'ack', 'acknowledged',
    'will do', 'got it', 'sure', 'done'})
MENTION_RE = re.compile(r'<@!?(\d+)>')
SECRET_RE = re.compile(r'sk-[a-zA-Z0-9._-]{20,}|github_pat_[a-zA-Z0-9_]{20,}|Bearer\s+FAKE[\w.-]{20,}', re.I)
_EMOJI_RE = re.compile('[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F1E6-\U0001F1FF\ufe0f\u200d]+')


class Act(Enum):
    ALLOW = 0
    REWRITE = 1
    SUPPRESS = 2
    BLOCK = 3


@dataclass
class Decision:
    act: Act = Act.ALLOW
    content: str | None = None
    reason: str = ''


@dataclass
class ChatState:
    silence_until: dict = field(default_factory=dict)
    last_mention: dict = field(default_factory=dict)


def init_bot_registry(name_to_id=None):
    """Explicit injected names only; no hidden file or runtime lookup."""
    NAME_TO_ID.update({k.casefold(): str(v) for k, v in (name_to_id or {}).items()})
    BOT_IDS.clear()
    BOT_IDS.update(NAME_TO_ID.values())


def is_enabled():
    return os.environ.get('CHAT_GATES_ENABLED', 'true').lower() not in ('false', '0', 'no', 'off')


def audit_path():
    return Path(os.environ.get('CHAT_AUDIT_PATH', './state/chat-audit.jsonl'))


def audit(act, gate, channel, content):
    try:
        row = {'ts': time.time(), 'act': act.name, 'gate': gate, 'channel': channel,
               'len': len(content), 'sha12': hashlib.sha256(content.encode()).hexdigest()[:12]}
        audit_path().parent.mkdir(parents=True, exist_ok=True)
        with audit_path().open('a') as stream:
            stream.write(json.dumps(row) + '\n')
    except Exception:
        pass


def health_summary():
    return {'enabled': is_enabled(), 'registry_loaded': bool(NAME_TO_ID),
            'bot_ids': len(BOT_IDS), 'audit_path': str(audit_path())}


def startup_check():
    health = health_summary()
    if not health['enabled'] or not health['registry_loaded']:
        logging.getLogger(__name__).error('chat gates inactive: %s', health)
    return health


def dump_state(state, path):
    try:
        path = Path(path)
        data = {'silence_until': state.silence_until,
                'last_mention': {'\x01'.join(k): v for k, v in state.last_mention.items()}}
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(data))
        os.replace(temp, path)
    except Exception:
        pass


def load_state(path):
    state = ChatState()
    try:
        now = time.time()
        data = json.loads(Path(path).read_text())
        state.silence_until = {k: v for k, v in data['silence_until'].items() if v > now}
        state.last_mention = {tuple(k.split('\x01')): v for k, v in data['last_mention'].items()
                              if v > now - COOLDOWN}
    except Exception:
        pass
    return state


def gate_ack_window(content, *, channel, state, is_bot=True):
    clean = re.sub(r'^(?:\s*<@!?\d+>\s*)*', '', content).strip()
    if is_bot and re.match(r'^\[ACK\]', clean, re.I):
        state.silence_until[channel] = time.time() + ACK_TTL
        return Decision(Act.SUPPRESS, reason='ack_window')
    return Decision()


def gate_block_secrets(content):
    return Decision(Act.SUPPRESS, reason='credential_shape') if SECRET_RE.search(content) else Decision()


def gate_enforce_silence(content, *, channel, state):
    return Decision(Act.SUPPRESS, reason='silence_window') if time.time() < state.silence_until.get(channel, 0) else Decision()


def gate_keep_silence(content, extra_cores=()):
    """Extend English cores explicitly; longer text is never inspected here."""
    text = content.strip()
    if len(text) > MAX_SILENCE_LEN:
        return Decision()
    old = None
    while old != text:
        old = text
        text = _EMOJI_RE.sub('', text).strip(' \t\r\n*_~`\'"()[]{}<>.:!-')
    core = ' '.join(text.casefold().split())
    if core in TRIVIAL | SILENCE_CORES | set(extra_cores):
        return Decision(Act.SUPPRESS, reason='placeholder_silence')
    return Decision()


def gate_fix_mention(content):
    if not NAME_TO_ID:
        return Decision()
    pattern = r'\b(' + '|'.join(re.escape(n) for n in NAME_TO_ID) + r')\b'
    fixed = re.sub(pattern, lambda m: '<@' + NAME_TO_ID[m[0].casefold()] + '>', content, flags=re.I)
    return Decision(Act.REWRITE, fixed, 'mention_rewrite') if fixed != content else Decision()


def gate_loop_cooldown(content, *, me, state):
    now = time.time()
    for target in set(MENTION_RE.findall(content)) & BOT_IDS:
        key = (me, target)
        if now - state.last_mention.get(key, 0) < COOLDOWN:
            return Decision(Act.SUPPRESS, reason='loop_cooldown')
        state.last_mention[key] = now
    return Decision()


def evaluate_inbound(content, *, channel, state, is_bot=True):
    if not is_enabled():
        return Decision(content=content, reason='disabled')
    try:
        decision = gate_ack_window(content, channel=channel, state=state, is_bot=is_bot)
        if decision.act == Act.SUPPRESS:
            audit(decision.act, decision.reason, channel, content)
        return decision
    except Exception:
        return Decision(content=content, reason='gate error')


def evaluate_outbound(content, *, me, channel, state):
    if not is_enabled():
        return Decision(content=content, reason='disabled')
    current = content
    try:
        for gate in (gate_block_secrets,
            lambda c: gate_enforce_silence(c, channel=channel, state=state),
            gate_keep_silence, gate_fix_mention,
            lambda c: gate_loop_cooldown(c, me=me, state=state)):
            decision = gate(current)
            if decision.act in (Act.SUPPRESS, Act.BLOCK):
                audit(decision.act, decision.reason, channel, current)
                return Decision(decision.act, current, decision.reason)
            if decision.act == Act.REWRITE:
                current = decision.content
    except Exception:
        return Decision(content=content, reason='gate error')
    if current != content:
        audit(Act.REWRITE, 'chained', channel, content)
        return Decision(Act.REWRITE, current, 'chained')
    return Decision(content=current)
