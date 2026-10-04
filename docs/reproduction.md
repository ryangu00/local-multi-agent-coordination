# Offline reproduction and implementation boundaries

Run from the repository root with Python >= 3.13 and a POSIX shell. The ordinary suite needs only the standard library. It creates fresh files under the repository and removes its own temporary directories. No live account, runtime installation, chat server, production board, model or GPU is used. No Git command is needed.

The historical measurements live in [results](results.md). The synthetic checks below are new acceptance checks of the shipped examples, not fresh measurements of those deployments.

## Run the complete stdlib suite

```sh
python3 -B -m unittest discover -s tests -v
```

The suite exercises the corrected completed-hop boundary, legal callbacks, concurrency, unstable lock files, timeout cleanup of grandchildren, denoise failures, the synthetic matrix, chat persistence and streaming, all completion-gate review cases, scan acceptance controls, and predicate-pass exceptions. Explicit protocol dependency mocks exercise the actual adapter and call/fan-out helpers without claiming SDK or HTTP conformance.

The regression suite temporarily removes the hop-only filter in memory. It requires the same twenty-completed-hop acceptance to fail at 15 hops, checks both hop and outcome rows in the isolated ledger, then restores the corrected rule and admits the refused hop against those same rows. No original source is modified.

## Hub counting and subprocess matrix

```sh
python3 -B scripts/repro_fleet_cap_double_count.py
python3 -B scripts/matrix_test.py --by-row
```

The counting reproduction expects 15 admissions with outcomes under the original mutated rule, 30 without outcomes, and 30 with outcomes under the corrected rule. The boundary unit test also requires the next admission to be refused.

The default matrix launches a delegating subprocess and an echo subprocess per cell and records both synthetic hops. It does not send A2A requests. Its isolated fleet cap is raised to the matrix's required hop count, because the full 4 x 4 matrix requires 32 admissions and cannot fit the default cap of 30. It does not alter a running service or its ledger. Caller rows are processed in sequence; diagonal cells remain in the fixture.

`configs/agents.example.toml` holds neutral echo/noisy agents. `configs/faults.example.toml` is a separate registry of slow and process-tree command alternatives; it is not merged into the default registry. To select it, set `COORD_REGISTRY=configs/faults.example.toml` before starting a server. Assign usable loopback ports first. The process-tree prompt must be a marker-file path in an isolated directory. The timeout test invokes the stub directly, waits past its delay and requires the marker to remain absent.

## Optional real loopback SDK smoke

The optional route requires the packages declared in `pyproject.toml` already present. That file pins `a2a-sdk==1.1.2` and `mcp==2.0.0` to the recorded versions; the other dependency ranges preserve the supplied project requirements rather than claiming exact measured versions. The standard-library suite needs none of these packages. Dependency setup is separate from these offline checks.

```sh
python3 -B scripts/sdk_smoke.py
```

The runner refuses with `UNEXECUTED` and exit 2 if its required imports are absent. It never downloads or installs anything. With dependencies present it writes a temporary registry, assigns loopback ports, starts synthetic servers, checks public-card and unauthorized-request behaviour, calls and nests a token round trip, fans out, reaches a loop refusal, then kills its own servers and cleans up.

This transport check was not executed successfully while preparing this public copy: the available environment lacked the SDK and web-server dependencies. The official SDK API compatibility and live socket path remain unverified here. The stdlib mocks do not remove that limitation. MCP registry/router code is optional in the source plan and is not included.

For a separately started, configured set of stub servers, `scripts/matrix_test.py --sdk --by-row` selects real SDK calls. Assign usable loopback ports first. Pace a full matrix beyond the breaker window or use an explicitly isolated test cap; the script does not silently relax a live cap.

## Stop file and service generation

The optional server checks `COORD_STATE_DIR/disabled` before importing the SDK. `COORD_STATE_DIR` defaults to `./state`. Tests create the stop file in an isolated directory and require a clean exit. Nothing is loaded into launchd.

To print a plist, supply paths from your own environment at invocation time:

```sh
python3 -B scripts/generate_services.py --root "$PWD" --python "$(command -v python3)" --agent agent-a
```

The generator reads every registry entry rather than maintaining a second hand-written roster. The selected definition uses `KeepAlive.SuccessfulExit=false` and throttle 10 s. A printed definition is not service installation evidence. The repository contains no generated machine-specific plist.

## Chat gates and the baseline reader

```sh
python3 -B scripts/baseline_loops.py fixtures/chat-loop.jsonl
python3 -B scripts/bridge_layers.py
python3 -B -m unittest tests.test_chat -v
```

The baseline reader accepts JSONL or CSV with `session,sender,text,timestamp`; input is already scoped to inbound messages and to the desired window. It strips timestamp-shaped text, collapses whitespace, truncates the normalised sentence to 120 characters, and groups by session. The public fixture matches three historical aggregates: 90 messages, a 74-minute span and a maximum of 11 normalised repeats. Its sentences, exact cadence and remaining repeat distribution are synthetic; it is not a replay of the private event.

The bridge example uses an explicitly uniform cadence of 0.6 messages per minute per sender to demonstrate why a 3-in-60 s burst limit is the wrong shape for that fixture. This does not establish the interarrival times of the historical event.

The neutral registry comes from an injected name-to-id dictionary, with fixtures `bot-a`/`bot-b` and obviously synthetic numeric identifiers. `CHAT_GATES_ENABLED` is the live kill switch; `CHAT_AUDIT_PATH` selects the hash-only audit. `gate_keep_silence(..., extra_cores=...)` is the English-core extension point. Callers adapting additional languages must define and test those cores themselves.

The stream example buffers the final text, calls the stateful gate exactly once, and then sends or suppresses. A named bug reproducer deliberately evaluates twice and observes self-suppression; the stream regression requires one gate call and a delivered reply. An in-memory double-evaluation mutation must fail that delivery assertion. A positive suppression case and a deliberately ineffective-gate mutation prevent a swallowed wiring error from looking green. It is a neutral integration, not the runtime's native streaming implementation. The richer runtime redactor and tool-guard sections are not shipped; only synthetic credential shapes are used.

## Root versus profile configuration

```sh
mkdir -p state/tmp
TMPDIR="$PWD/state/tmp" python3 -B scripts/toy_profile_trap.py
```

Expected output from the supplied toy:

```text
default-home block(needs review) block(needs review)
profile-home allow(exempt) block(needs review)
```

The toy is copied unchanged. Python's `tempfile.TemporaryDirectory()` reads `TMPDIR`; the command creates that directory first so the temporary fixture stays under the repository. `APP_HOME` separately selects which fixture configuration each child reads. The broader board example reads JSON for dependency-free operation; the equivalent YAML example contains only the reviewer map, completion switch, observer switch and dispatcher interval.

```sh
python3 -B scripts/reviewer_map_consistency.py configs/board.example.json fixtures/reviewer-table.json fixtures/profiles.json
python3 -B -m unittest tests.test_board -v
```

Reconciliation injects a profile-existence predicate. The CLI's provider is a synthetic JSON list. Missing providers or unreadable inputs exit 2; differences, one-sided entries, self-review or nonexistent profiles exit 1. It does not inspect a real runtime's profile directories.

Board tests set both `WORKER_TASK` and `WORKER_RUN`. They force the nine historical gate-review paths, the observer's positive bypass, candidate-range negative controls, watermark rewind and off/on catch-up. The scan uses first non-zero-duration runs and the child's original creation payload. Current assignee and synthetic zero-length runs cannot satisfy its evidence test.

The board toy does not spawn workers or implement a full task scheduler. It provides the completion/review tools and a tick entry point with the scan before a next-step callback. Gate exceptions allow; scan exceptions do not stop the callback. A done card remains done after a flag. Same-user database writes are still outside the tool-level boundary.

## Single-writer JSON-board pass

```sh
mkdir -p state
cp fixtures/board.json state/board.json
python3 -B scripts/board_pass.py state/board.json
python3 -B scripts/board_pass.py state/board.json
```

The success card writes and verifies `out.txt`. The unsatisfiable regex predicate fails, feeds its evidence into the next packet, then blocks at the attempt limit. The dirty-workdir case is an explicit `dirty_fixture` preflight mock, remains ready, and counts no attempt. It does not inspect Git state or reproduce the historical local executor's worktree handling.

This demo intentionally changes `state/board.json` and leaves generated files in `state/success` and `state/unsatisfiable`. Copy `fixtures/board.json` again to reset card status and attempt history before another two-pass run. Relative `workdir:` paths resolve from the repository root, not from the board file's directory. For an isolated run, copy the board into a fresh directory under the repository and rewrite all three `workdir:` entries to directories inside it, as the end-to-end test does; moving only the board file does not isolate the workdirs.

To check predicates independently:

```sh
python3 -B scripts/board_pass.py --verify path/to/predicates.json --workdir path/to/workdir
```

The entry point exits 0 only on a passed verdict. It rejects an empty acceptance list, unknown predicates and errors. `cmd_succeeds` takes an argv list, executes locally in the workdir, and uses its exit code. Supply commands you intend to run. The evaluator is a small teaching implementation; the original verdict source was [axiom](https://github.com/ryangu00/axiom).

The JSON board is read and written under the pass's non-blocking lock. File replacement makes each snapshot complete; claim, comment and transition remain sequential operations with a crash window. Claims carry TTL 3600 s and are reclaimed on a later pass. Each exception-cleanup step is isolated. A comment-write failure blocks rather than enabling uncounted retry.

The exact exit/status success contract is tested even though the local harness executor branch is removed. No merger, worktree manager, external board CLI or hosted agent is included.

## Publication assets

The repository includes `docs/assets/banner.png` and its source, `docs/make_banner.py`. Regeneration requires Pillow (`PIL`), which is not needed for the offline suite. The image, generator and LICENSE are unchanged by this review update; the generator was not run. No runtime configuration, real audit log, real ledger, private board, original integration test or real chat identifier is shipped.
