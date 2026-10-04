# Public-copy validation

These synthetic checks were rerun for this review update. They are separate from the historical results in [results](results.md). No remote model, chat account, production database or Git command was used.

Command:

```sh
python3 -B -m unittest discover -s tests -v
```

Exact result lines:

```text
Ran 109 tests in 4.730s

OK
```

The suite has no dependency-based skips. It uses explicit dependency mocks for the optional SDK helpers. It exercises real local subprocesses, a child/grandchild timeout, real SQLite writes, file locks, the synthetic matrix and JSON-board state transitions. It does not test real HTTP transport or compatibility with installed SDK classes.

The counting mutation fails the twenty-completed-hop acceptance at 15 hops, with 15 outcome rows in the isolated ledger; the restored rule admits the refused hop against the same rows. The chat bug reproducer intentionally observes double-evaluation suppression, while the stream regression requires one evaluation and a delivered reply. A double-evaluation mutation fails that delivery assertion.

Command:

```sh
python3 -B scripts/baseline_loops.py fixtures/chat-loop.jsonl
```

Exact output:

```json
[
  {
    "session": "synthetic-loop",
    "messages": 90,
    "max_repeats": 11,
    "start": 0.0,
    "end": 4440.0
  }
]
```

The fixture matches the recorded event's size, span and maximum repeat count. Its sentences, exact cadence and remaining repeat distribution are synthetic.

Command:

```sh
python3 -B scripts/repro_fleet_cap_double_count.py
```

Exact output:

```text
original with outcomes: 15
original without outcomes: 30
corrected with outcomes: 30
```

Command:

```sh
python3 -B scripts/matrix_test.py --by-row
```

Exact final line:

```text
matrix: 16 / 16 passed
```

The matrix is a subprocess mock. Its parent delegates through `mock_call.py`, which reads the target's registry entry, inherits chain references, records admission, runs the target and writes the outcome. Its test also checks the expected hop/outcome rows. The test-only cap override travels only through the mock helper, not the official server.

Commands:

```sh
python3 -B scripts/bridge_layers.py
python3 -B scripts/reviewer_map_consistency.py configs/board.example.json fixtures/reviewer-table.json fixtures/profiles.json
```

Exact output lines:

```text
uniform cadence at 0.6 messages/minute/sender: burst rule never fires
reviewer map: consistent; profiles exist; no self-review
```

The config-trap script was run with `TMPDIR` set to an isolated directory inside the repository. A fresh-process check confirmed that `tempfile` selected that directory, and a readback confirmed the toy removed its temporary files. Exact toy output:

```text
default-home block(needs review) block(needs review)
profile-home allow(exempt) block(needs review)
```

The JSON-board CLI was run twice on a fresh copied fixture with workdirs redirected inside the same temporary directory. Exact output:

```text
synthetic-success PASS complete
synthetic-unsatisfiable FAIL ready; evidence feeds next pass
synthetic-dirty DEFER dirty fixture; no attempt counted
synthetic-unsatisfiable FAIL blocked
synthetic-dirty DEFER dirty fixture; no attempt counted
JSON board end-to-end: PASS
```

The final board was independently read and required to be done/blocked/ready in fixture order. The plist generator's stdout was parsed as a plist and checked for the clean-exit restart policy; no service was installed or loaded.

The earlier public-copy validation attempted the optional command; this review update did not rerun the real transport check:

```sh
python3 -B scripts/sdk_smoke.py
```

It exited 2 before starting servers, with this exact output:

```text
UNEXECUTED: missing optional packages: a2a, fastapi, uvicorn
```

Nothing was installed or downloaded. MCP registry/router code is optional in the plan and is not shipped. Real SDK transport, hosted-agent behaviour, the removed local executor and production runtime integration remain unverified here.

Publication checks inspected text for CJK characters, private names and paths, real-looking chat identifiers, non-loopback addresses, syntax errors and broken local links. The supplied banner image exists at `docs/assets/banner.png`; it is not a deferred target. LICENSE, the image and the banner script were checked against their pre-edit hashes and left unchanged. The generator was not run. All five related cookbook links point to public repositories.
