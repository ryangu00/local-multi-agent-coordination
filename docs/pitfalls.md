# Pitfalls and discriminating checks

Each entry preserves the observed symptom, diagnosed cause and recorded fix. Historical results and reconstructed test coverage are distinct.

## Chapter 1: hub

- Agent A returns `401 OAuth access token has been revoked`, yet logging in does not help -> an inherited base-URL variable overrode the CLI's own settings and pushed it onto a path that never consults subscription credentials; the error text is about a token, the fault is not -> set routing variables explicitly for the child (placeholder key when a router holds the real one) instead of relying on inheritance.
- Agent C replies a provider-prefix rejection -> default model written with a vendor prefix its harness does not accept, and an empty credentials directory (never onboarded) -> fix the prefix and onboard; two faults stacked.
- Asking the model which model it is returns a confident wrong name -> self-report is a hallucination; the router's own audit table showed the real model -> use ground-truth logs, never the model's mouth.
- Agent B in a read-only sandbox can be called but can never call anyone -> read-only sandbox also blocks loopback networking -> use workspace-write plus the explicit network flag (which only takes effect in workspace-write mode) and point the working directory at a scratch directory; sha256 of the audited source was unchanged afterwards. State the limit honestly: this stops the agent editing the code directly, not asking an unsandboxed peer to do it.
- Agent A's `--allowedTools` "narrowing" ran an arbitrary shell command (`date` passed) -> that flag only adds to the permission rules merged from user settings -> narrow with `--settings <file>` plus `--setting-sources ''` (empty), and supply the routing environment explicitly because dropping the user scope also drops the route env and the key helper; `git push --dry-run` was then denied.
- A service that works in the terminal fails under launchd -> a bare command name is, on an interactive shell, an alias that activates a virtualenv first (agent D) or a wrapper function that injects `--resume` (agent A), not a binary -> use absolute paths in the command template. The adapter reported `FileNotFoundError` as text, as designed.
- Test "routing tiers" all passed -> every case carried a comma in the model name, which the router treats as pinned and skips tier logic, so nothing was tested -> read the router's own decision audit rows and unit-test the decision function.
- "Twenty-turn agentic test passed" proved nothing -> it ran through an alternative provider, but the original failure lived on the direct path -> test the path that failed.
- A self-audit `grep model` reported "models scanned" -> it matched a comment -> verify a capability by whether it is called, not whether the word appears.
- Upgrading a router in a shadow instance still rewrote another tool's configuration (a managed block pointing agent B at the shadow, new token, a stale catalogue path) and broke agent B when the shadow stopped -> isolating the router's own directory did not isolate its side effects -> back up every downstream tool's config, run the downstream agents before and after, and read the new ledger's `ok` column (it caught this; a ledger that only records "allowed to start" would not have).

For the procedure and its limits, read [hub](hub.md).

## Chapter 2: loop bounds

- **Found while preparing this book: the original documented fleet cap of 30 was really 15.** Symptom: a rotation test refuses at hop 15 with the message "the fleet started 30 sessions". Root cause: the window filter counts every ledger row with an epoch, and since the ledger gained separate outcome rows each completed hop writes two rows. Reproduction (scratch ledger, 4 rotating agent names, distinct questions): with an outcome row after every hop, 15 hops admitted then refusal; without outcome rows, 30 admitted. The per-agent count is unaffected because outcome rows carry no agent name. Fix for the shipped version: count only hop rows (`kind == "hop"`, treating rows without a kind as hops) and add a test that completes 20 hops and expects 20 admitted, then test the full 30-hop limit and refusal of the next hop. The original installation was not changed. The shipped copy corrects the count; `scripts/repro_fleet_cap_double_count.py` also runs an in-memory mutation of the original rule.
- A full 4 x 4 matrix cannot run through the cap: 16 cells x 2 hops = 32 hop rows (64 rows with outcomes) against a cap of 30 per 300 s. The breaker landed one day after the matrix run, and the record does not say the matrix was re-run afterwards; run by row with pauses, or raise the cap for test runs.
- A restart or a state-directory move that resets the ledger makes the breaker forget everything while the service looks healthy. The design notes therefore require "ledger row count continues to grow after a migration" as an explicit acceptance check; the state directory was deliberately never renamed.
- Check-then-act on a shared file under concurrency admits everyone ("every one reads a pre-limit ledger") -> one critical section and an inode re-check.
- A fallback path that was never tested is a time bomb: the registry fallback raised `AttributeError` the one time it ran (in mcp 2.x a tool-decorated function is not unwrapped), and it should not have existed at all because the router's point is to hold no roster -> delete it; make "discovery down" a distinct, fatal error.
- A degraded output that looks like a normal answer is worse than an error: a malformed registry reply read as "no matches" answered "no agent has this skill" -> validate the payload and raise a separate protocol error; an empty `matches` list is still a legitimate answer.
- Thresholds are guesses until measured: 6, 2, 12, 30 and 300 s were chosen by reasoning (a hop is minutes of work), not from a false-refusal rate. Treat them as starting values and log refusals.

For the procedure and its limits, read [loop-bounds](loop-bounds.md).

## Chapter 3: stopping services

- A stopped service keeps coming back -> a second install of the same thing at another launchd level -> before guessing layer by layer, ask whether a second thing is doing the same job (`launchctl print` at every domain, not only the user's).
- A kill switch that returns non-zero or crashes gets restarted -> exit 0 with `SuccessfulExit=false` -> do not re-launch.
- A state directory renamed for tidiness resets the breaker ledger and the system still looks healthy -> do not rename live state; if you must, add a row-count continuity check.
- The original installer script installed services for only two of the four agents although four were verified -> a shipped installer must be generated from the registry, not hand-listed.

For the procedure and its limits, read [stopping-services](stopping-services.md).

## Chapter 4: chat loops

- The safety net is "wired" but nothing is committed: an audit read only the committed tree and declared the net inert; the working tree had the wiring, and one file sync would have erased it -> audit the working tree and the effective runtime, not only the committed state; commit the wiring.
- Streamed replies bypass the outbound gate: the gate sat after an early return taken whenever a reply had already been streamed (the default path), so streamed output had zero suppression -> evaluate the gate at the single finalize point of the stream, exactly once.
- A stateful gate evaluated twice suppresses the bot's own reply: the cooldown records the mention it just allowed, so a second evaluation sees it and suppresses -> gate once per message, never per frame; add a test that fails if it is evaluated twice.
- A test that cannot fail: the streaming helper imported the gate module through a package path that did not exist; the import error was swallowed by the fail-open rule, so every test passed with no gate at all -> assert the suppress case actually drops the message.
- A human typing "[ACK] please do X" silenced the bot for the window -> only bot-authored acks open the window; keep the legacy default for older callers.
- A restart resets the cooldown and the silence window -> persist and prune on load.
- A gate net that is silently off -> startup health summary with a loud log line.
- Residual noted after a later upgrade: a new native-streaming branch in the runtime does not pass the gate (the chat platform's edit stream is unaffected). Record it as an open item.

For the procedure and its limits, read [chat-loops](chat-loops.md).

## Chapter 5: review gate

- Review "on" yet implementers review themselves -> default dispatch uses the current assignee and the reviewer argument is optional -> resolve the reviewer mechanically before dispatch.
- Changing an implementer's model silently re-creates same-family review -> the map is ordered by family and drifts with model changes -> recompute the table whenever any profile's primary model changes and run the reconciliation script from cron.
- An assignee written as a nickname instead of the runtime's profile name -> the dispatcher classifies the card non-spawnable and it sits ready forever, no error -> assignee must be a profile name; two cards with a nickname assignee had not been picked up in three months.
- A reviewer profile that does not exist -> the card is moved to review and the dispatcher skips it every tick -> existence assertion in the reconciliation script.
- A retired poller aimed at the same cards -> after the new flow the review cards' assignee became the poller's pick-up condition, so keeping it would have created a double-claim race; its log held 13 lines in 70 days, all "starting" -> retire stale pollers when you change the flow that feeds them.
- Verifying a gate whose exemptions eat the harness: after the worker-context fix, the worker test reads two environment variables; without them every check shows "allowed" and looks like "no false blocks" -> before testing a gate, test that the harness is not eaten by the gate's own exemptions (set the worker variables explicitly).

For the procedure and its limits, read [review-gate](review-gate.md).

## Chapter 6: config trap

- A gate passes everything in workers but blocks in your shell -> profile-dependent config loading returned `None` for a fleet-level key -> resolve fleet-level keys from the root, test in a profile environment.
- "Not configured" and "could not read configuration" are indistinguishable -> the loader returns an empty mapping on a miss -> make fleet-level readers return a distinguishable "unreadable" state or raise when the root file is expected but missing; keep fail-open only for the configured-but-absent case, and log which one happened.
- Every new gate that reads a table needs the same acceptance: run it once with the home variable set to a worker profile.

**A toy that reproduces the trap** (verified on 2026-10-03, stdlib only; included under `scripts/` of the shipped files): a root `config.json` holding `{"reviewer_map": {"worker-a": "reviewer-b"}}`, a profile `config.json` of `{}`, a child process started with `APP_HOME` set to each. Expected output:

| Home | Buggy lookup gate | Root-aware gate |
|---|---|---|
| default home | block (needs review) | block (needs review) |
| profile home | **allow (exempt)** | block (needs review) |

For the procedure and its limits, read [config-trap](config-trap.md).

## Chapter 7: dispatcher evidence

- Watching for bypass inside the agent's own tool -> the worker has a terminal and a valid claim -> observe from the dispatcher.
- Flag count of zero after deploy -> may mean the guard is blind, not that nobody bypassed (watermark never written, switch off, wrong board) -> deploy with a deliberate positive control (a card completed from a terminal) and a rewind test.
- An observing layer that silently stops (lock unavailable, first-run branch) -> permanent silent blindness -> best-effort write plus one warning is better than perfect-but-silent.
- A write to the board from a new component outside a transaction -> write helper expected an open transaction -> read the helper's docstring first line.

For the procedure and its limits, read [dispatcher-evidence](dispatcher-evidence.md).

## Chapter 8: predicate pass

- A failed worker passes the gate -> the verifier ran on pre-existing artifacts after the executor failed -> an executor failure must never reach the verifier; define success as an exact exit-code and status pair.
- Retries loop forever -> the attempt marker is stored in a comment and the comment write failed -> if the marker cannot be written, block.
- A card stays claimed after an exception -> cleanup raised inside cleanup -> isolate each step and rely on the claim TTL as the last line.
- "Pass" on an empty file -> a predicate is a letter, not a spirit: `file_exists` passes on an empty file -> write predicates as the specification.

For the procedure and its limits, read [predicate-pass](predicate-pass.md).
