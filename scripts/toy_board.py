"""Re-created SQLite review controls; not the production runtime patch.

The tool gate is lenient. The dispatcher scan is stricter and detect-only.
Only the root-aware reviewer lookup is shared. Same-user database writes remain
outside the boundary. Timestamps and identifiers in the tests are synthetic.
"""
import fcntl
import json
import logging
import os
from pathlib import Path
import sqlite3

LOG = logging.getLogger(__name__)
SCHEMA = '''
CREATE TABLE tasks (id TEXT PRIMARY KEY, assignee TEXT, status TEXT, created_at REAL);
CREATE TABLE task_runs (id INTEGER PRIMARY KEY, task_id TEXT, profile TEXT,
                       started_at REAL, ended_at REAL);
CREATE TABLE task_events (id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, payload TEXT);
CREATE TABLE task_links (parent_id TEXT, child_id TEXT);
'''


def root_config(home=None):
    current = Path(home or os.environ.get('APP_HOME', './state/app'))
    root = current.parent.parent if current.parent.name == 'profiles' else current
    try:
        return json.loads((root / 'config.json').read_text())
    except (OSError, ValueError):
        try:
            return json.loads((current / 'config.json').read_text())
        except (OSError, ValueError):
            return {}


def reviewer_for(assignee, config):
    if not assignee:
        return None
    who = config.get('kanban', {}).get('default_reviewer_map', {}).get(assignee.strip().lower())
    if not isinstance(who, str) or not who.strip():
        return None
    return None if who.strip().lower() == assignee.strip().lower() else who.strip()


class Board:
    def __init__(self, path, config=None, name='synthetic-board'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=DELETE')
        if not self.conn.execute("SELECT name FROM sqlite_master WHERE name='tasks'").fetchone():
            self.conn.executescript(SCHEMA)
        self.config = config if config is not None else root_config()
        self.name = name
        self.lock_warned = False

    def close(self):
        self.conn.close()

    def event(self, task, kind, payload=None):
        """Caller must hold an open transaction, matching the recorded contract."""
        if not self.conn.in_transaction:
            raise RuntimeError('event append requires a transaction')
        return self.conn.execute('INSERT INTO task_events(task_id,kind,payload) VALUES (?,?,?)',
                   (task, kind, json.dumps(payload or {}))).lastrowid

    def create(self, task, assignee='worker-a', created_at=0, parents=()):
        with self.conn:
            self.conn.execute('INSERT INTO tasks VALUES (?,?,?,?)',
                              (task, assignee, 'ready', created_at))
            self.event(task, 'created', {'parents': list(parents)})
            for parent in parents:
                self.conn.execute('INSERT INTO task_links VALUES (?,?)', (parent, task))

    def add_run(self, task, profile='worker-a', start=0, end=None):
        with self.conn:
            return self.conn.execute('INSERT INTO task_runs(task_id,profile,started_at,ended_at) VALUES (?,?,?,?)',
                                  (task, profile, start, end)).lastrowid

    def task(self, task):
        return self.conn.execute('SELECT * FROM tasks WHERE id=?', (task,)).fetchone()

    def events(self, task, kind):
        return self.conn.execute('SELECT * FROM task_events WHERE task_id=? AND kind=? ORDER BY id',
                                 (task, kind)).fetchall()

    def link(self, parent, child):
        with self.conn:
            self.conn.execute('INSERT INTO task_links VALUES (?,?)', (parent, child))
            self.event(child, 'linked', {'parent': parent})

    def request_review(self, task, reviewer=None, synthetic_runs=True, now=0):
        implementer = self.task(task)['assignee']
        reviewer = reviewer or reviewer_for(implementer, self.config) or implementer
        with self.conn:
            self.conn.execute("UPDATE tasks SET assignee=?,status='review' WHERE id=?", (reviewer, task))
            self.event(task, 'review_requested', {'implementer': implementer, 'reviewer': reviewer})
            if synthetic_runs:
                for _ in range(2):
                    self.conn.execute('INSERT INTO task_runs(task_id,profile,started_at,ended_at) VALUES (?,?,?,?)',
                                      (task, reviewer, now, now))
        return reviewer

    def precreated_child(self, task, require_creation_link=False):
        first = self.conn.execute('SELECT MIN(started_at) FROM task_runs WHERE task_id=?', (task,)).fetchone()[0]
        if first is None:
            return False
        children = self.conn.execute('SELECT c.id FROM task_links l JOIN tasks c ON c.id=l.child_id '
            'WHERE l.parent_id=? AND c.created_at<?', (task, first)).fetchall()
        for child in children:
            if not require_creation_link:
                return True
            events = self.events(child['id'], 'created')
            try:
                if events and task in json.loads(events[0]['payload']).get('parents', []):
                    return True
            except (ValueError, TypeError):
                continue
        return False

    def rejection(self, task):
        """E1, retry, E2, E3, E4, E5 in order; any internal error allows."""
        try:
            if not self.config.get('kanban', {}).get('require_review_before_complete', True):
                return None
            row = self.task(task)
            if row['status'] in ('done', 'archived'):
                return None
            reviewer = reviewer_for(row['assignee'], self.config)
            if reviewer is None:
                return None
            events = self.events(task, 'review_requested')
            if events:
                impl = rev = None
                try:
                    data = json.loads(events[-1]['payload'])
                    impl = str(data.get('implementer') or '').strip().lower()
                    rev = str(data.get('reviewer') or '').strip().lower()
                except Exception:
                    pass
                # Deliberately lenient: malformed handover events also exempt.
                # The observing verdict below requires another real run.
                if not (impl and rev and impl == rev):
                    return None
            if self.precreated_child(task):
                return None
            if os.environ.get('WORKER_TASK') != task or not os.environ.get('WORKER_RUN', '').isdigit():
                return None
            return (f'Completion refused: the producer cannot be the acceptor. Use reviewer {reviewer}. '
                    f'request_review(task={task!r}, reviewer={reviewer!r}, '
                    'summary=<carry summary>, metadata=<carry metadata>, board=<same board>). '
                    'Do not escape by marking the card blocked.')
        except Exception:
            return None

    def complete(self, task, via_tool=True):
        if via_tool and (reason := self.rejection(task)):
            return reason
        if self.task(task)['status'] in ('done', 'archived'):
            return None
        with self.conn:
            self.conn.execute("UPDATE tasks SET status='done' WHERE id=?", (task,))
            self.event(task, 'completed')
        return None

    def verdict(self, task):
        if self.task(task)['status'] != 'done':
            return None
        runs = self.conn.execute('SELECT profile FROM task_runs WHERE task_id=? '
             'AND (ended_at IS NULL OR started_at<ended_at) ORDER BY started_at,id', (task,)).fetchall()
        workers = [r['profile'].strip().lower() for r in runs if r['profile'] and r['profile'].strip()]
        if not workers:
            return None
        implementer = workers[0]
        reviewer = reviewer_for(implementer, self.config)
        if not reviewer or any(w != implementer for w in workers):
            return None
        if self.precreated_child(task, require_creation_link=True):
            return None
        return implementer, reviewer

    def scan(self, watermark):
        if self.config.get('kanban', {}).get('review_enforcement', {}).get('enabled', True) is False:
            return []
        flags = []
        try:
            path = Path(watermark)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a+') as stream:
                locked = False
                try:
                    try:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                        locked = True
                    except OSError:
                        if not self.lock_warned:
                            LOG.warning('watermark lock unavailable; best-effort write')
                            self.lock_warned = True
                    stream.seek(0)
                    try:
                        doc = json.loads(stream.read() or '{}')
                    except ValueError:
                        doc = {}
                    end = self.conn.execute('SELECT COALESCE(MAX(id),0) FROM task_events').fetchone()[0]
                    # Key presence also handles an initially empty toy board.
                    if self.name in doc:
                        previous = doc[self.name]
                        candidates = self.conn.execute("SELECT DISTINCT task_id FROM task_events WHERE id>? AND id<=? AND kind='completed'", (previous, end)).fetchall()
                        for candidate in candidates:
                            task = candidate['task_id']
                            verdict = self.verdict(task)
                            if verdict and not self.events(task, 'review_enforcement_flagged'):
                                payload = {'implementer': verdict[0], 'expected_reviewer': verdict[1],
                                    'reason': 'completed without independent review evidence', 'board': self.name}
                                with self.conn:
                                    self.conn.execute('BEGIN')
                                    self.event(task, 'review_enforcement_flagged', payload)
                                LOG.warning('review evidence missing: task=%s board=%s', task, self.name)
                                flags.append(task)
                    doc[self.name] = end
                    stream.seek(0)
                    stream.truncate()
                    stream.write(json.dumps(doc, sort_keys=True))
                    stream.flush()
                    os.fsync(stream.fileno())
                finally:
                    if locked:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        except Exception:
            LOG.debug('scan failed open', exc_info=True)
        return flags

    def tick(self, watermark, after_scan=lambda: None):
        """Step zero under a per-board single-writer lock; no worker spawn here."""
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                flags = self.scan(watermark)
                after_scan()
                return flags
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
