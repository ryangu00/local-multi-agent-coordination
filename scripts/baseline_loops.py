"""Count mention-bearing inbound fixtures from CSV or JSONL; no database access."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import sys


def normalize(text):
    return re.sub(r'\d{4}-\d{2}-\d{2}T?\d{0,2}:?\d{0,2}', '<T>',
                  re.sub(r'\s+', ' ', text or ''))[:120]


def summarize(rows):
    events = defaultdict(list)
    for row in rows:
        if '<@' in row['text']:
            events[row['session']].append(row)
    out = []
    for session, messages in events.items():
        counts = Counter(normalize(m['text']) for m in messages)
        out.append({'session': session, 'messages': len(messages),
                    'max_repeats': max(counts.values()),
                    'start': min(float(m['timestamp']) for m in messages),
                    'end': max(float(m['timestamp']) for m in messages)})
    return out


if __name__ == '__main__':
    path = Path(sys.argv[1])
    with path.open() as stream:
        rows = list(csv.DictReader(stream)) if path.suffix == '.csv' else [json.loads(s) for s in stream]
    print(json.dumps(summarize(rows), indent=2))
