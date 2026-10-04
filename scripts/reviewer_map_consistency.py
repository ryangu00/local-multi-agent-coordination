"""Compare neutral tables with an injected authoritative existence predicate."""
import argparse
import json
from pathlib import Path


def check(config_map, document_map, exists_fn):
    if exists_fn is None:
        raise RuntimeError('profile existence provider unavailable')
    issues = []
    for worker in sorted(set(config_map) | set(document_map)):
        if config_map.get(worker) != document_map.get(worker):
            issues.append(f'{worker}: config={config_map.get(worker)!r}, document={document_map.get(worker)!r}')
    for source, mapping in (('config', config_map), ('document', document_map)):
        for worker, reviewer in mapping.items():
            if worker.strip().lower() == reviewer.strip().lower():
                issues.append(f'{source}: self-review {worker} -> {reviewer}')
            for side, profile in (('implementer', worker), ('reviewer', reviewer)):
                if not exists_fn(profile):
                    issues.append(f'{source}: missing {side} {profile}, mapping {worker} -> {reviewer}')
    return issues


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config')
    parser.add_argument('document_table')
    parser.add_argument('profiles', help='JSON list: synthetic existence provider')
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text())['kanban']['default_reviewer_map']
        table = json.loads(Path(args.document_table).read_text())
        profiles = json.loads(Path(args.profiles).read_text())
        issues = check(config, table, lambda name: name in profiles)
    except Exception as error:
        print(f'environment error: {error}')
        raise SystemExit(2)
    print('\n'.join(issues) if issues else 'reviewer map: consistent; profiles exist; no self-review')
    raise SystemExit(bool(issues))
