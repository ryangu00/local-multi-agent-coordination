# Chapter 2: Loop bounds that hold

### Problem

Agents that can call agents can call each other forever. Each hop is a full CLI session, so a cycle costs tokens and mutates state. Which bound actually holds when an adversarial reviewer is allowed to try to get around it?

### What we built or changed

Every adapter appends one row per request to a shared local ledger keyed by the protocol's `context_id`. The same file is the audit log and the input to loop detection. Adapters and call helpers carry chain provenance, but clearing the inherited environment can still reset a sub-call's context and depth. The fleet-wide count remains the backstop because it ignores both context and identity.

**Three bounds** (constants as shipped; chosen by reasoning, not measurement):

| Bound | Rule | Constant |
|---|---|---|
| depth | refuse a hop when the chain already has 6 references | `MAX_DEPTH = 6` ("a hop is a full CLI session, so a chain this long is minutes of work") |
| repeat | refuse the same agent being given the same question a third time in one context | `MAX_REPEAT = 2`; fingerprint = first 16 hex of sha256 over the whitespace-normalised prompt |
| breaker | refuse an agent past 12 sessions in 300 s, and refuse everything past 30 sessions fleet-wide in 300 s, whatever context anyone claims | `BREAKER_MAX = 12`, `BREAKER_FLEET_MAX = 30`, `BREAKER_WINDOW_S = 300` |

`A -> B -> A` stays legal: calling back whoever called you is ordinary delegation; it becomes a cycle only when the question comes back too (the same agent asked the same question a third time).

**Admission is decide-and-record in one critical section.** `admit()` takes an exclusive `flock` on a sidecar lock file, reads the ledger, applies the verdict, and appends the hop row before releasing. After taking the lock it compares the lock file's inode with the path's inode and retries (up to 5 times) because `flock` guards an inode, not a path; if it cannot hold the lock it refuses rather than running unlocked. A ledger that cannot be written is a refusal ("with no ledger there is no bound at all"). A torn line in the ledger is skipped so one bad write cannot disable the gate.

**Refusals are agent text with a marker** (a fixed string prefix), not transport errors: a transport error would hide which agent stopped and why, and without a marker an aggregator counts "I refused" as a reply. Outcomes are separate append-only rows (`ok`, milliseconds, result length) so the file stays append-only and two adapters can never interleave a rewrite.

**Process-tree kill.** The child is started in its own session; on timeout or cancellation the whole group gets SIGKILL and is reaped. `proc.kill()` alone signalled only the direct child, and grandchildren kept spending tokens while the caller had been told "child killed": a report that was true and useless.

### Procedure as actually run

1. Build depth + repeat + breaker with a "deliberately constructed cycle" test and a "legal callback" test.
2. Send the batch to agent B (other vendor) over the hub's own path; first verdict was "redo".
3. For every reviewer claim, write a reproduction before fixing; keep each reproduction as a permanent test.
4. Second review round with two targeted attacks (name rotation, lock-file replacement); final verdict GO.
5. Re-run on 2026-10-03: the original chain suite passed 17 of 17 (Python 3.13.13, a2a-sdk 1.1.2); the denoise tests also passed.

### Results

**Seven first-round findings, all upheld** (3 BLOCKER, 4 MAJOR) and two second-round attacks:

| # | Bypass or flaw | How it was shown | Fix |
|---|---|---|---|
| 1 | Prompt fingerprint evaded by appending a counter to each hop | reproduced | breaker as a wall-clock backstop |
| 2 | Check and record were separate steps: 10 concurrent identical hops, 10 admitted | reproduced, 10 for 10 | one critical section |
| 3 | Timeout killed only the direct child; a grandchild still wrote its marker file | reproduced (marker appeared) | process group kill |
| 4 | Reference list joined with commas misaligned when an id contained a comma | upheld | JSON list |
| 5 | Explicit references replaced inherited ones, breaking the chain | upheld | merge, never replace |
| 6 | Clearing the inherited environment broke the chain link and reset depth to zero | upheld | the breaker does not depend on inherited context |
| 7 | Refusal counted as success by the fan-out aggregator | upheld | refusal marker checked |
| 8 (round 2) | Rotating agent names (A, B, C, A ...) multiplies the per-agent cap by roster size | targeted test | fleet-wide cap added |
| 9 (round 2) | `flock` held on an inode; replacing the lock file runs two critical sections at once | targeted test | inode re-check, refuse if unstable |

**Original test suite (17 checks)** and what each guards:

| Group | Checks | Guards |
|---|---|---|
| Constructed cycle | first two hops pass (second is a callback); third identical ask refused as "cycle" | cycle detection |
| Legal callback | A to B to A with a different question passes | no false refusal |
| Depth boundary | refused at 6; one short still passes | boundary not early |
| Context isolation and whitespace | another context unaffected; original context still blocked; re-wrapped whitespace is the same question | fingerprint semantics |
| Paraphrase plus new context each hop | still stopped by the breaker | bypass 1 |
| 10 concurrent identical hops | at most 2 admitted | bypass 2 |
| Grandchild after timeout | timeout reported honestly; marker file never appears | bypass 3 |
| Name rotation | stopped by the fleet-wide cap | bypass 8 |
| Lock file swapped repeatedly | refuses instead of running unlocked | bypass 9 |
| Refusal marker | marked refusals are recognisable; normal text is not | bypass 7 |
| Corrupt ledger line | torn line skipped, rest still judged | gate not disabled by one bad write |

The cycle-only half of a test suite would pass a gate that refuses everything; the callback and boundary cases are what keep it honest.

**Ledger in use** (read-only count, 2026-10-03): 96 rows written 2026-08-03 to 2026-08-15: 26 hop rows (to agent B 16, agent D 4, agent A 4, agent C 2; 24 single, 2 chained), 26 outcome rows (24 ok, 2 not ok), 44 rows in the earlier format. Test traffic and real use are mixed in these rows.

### What did not work

| Layer | Why it failed as a bound |
|---|---|
| Depth | An agent that spawns its sub-call with a cleaned environment loses the inherited context, so depth restarts at zero. |
| Repeat | Fingerprints normalise whitespace but not paraphrase; appending a counter makes every hop a new question. |
| Per-agent quota alone | Only as strong as the number of agent names; rotation multiplies the ceiling by the roster size. |
| "Child killed" reporting | True and useless when grandchildren survive. |

Only the fleet-wide wall-clock count of sessions in a window, which reads neither content nor identity, was not bypassed. (Precisely: the per-agent count is keyed by identity and was beaten by rotation; the fleet-wide count is the one that ignores identity as well.)

### Pitfalls (symptom -> root cause -> fix)

- **Found while preparing this book: the original documented fleet cap of 30 was really 15.** Symptom: a rotation test refuses at hop 15 with the message "the fleet started 30 sessions". Root cause: the window filter counts every ledger row with an epoch, and since the ledger gained separate outcome rows each completed hop writes two rows. Reproduction (scratch ledger, 4 rotating agent names, distinct questions): with an outcome row after every hop, 15 hops admitted then refusal; without outcome rows, 30 admitted. The per-agent count is unaffected because outcome rows carry no agent name. Fix for the shipped version: count only hop rows (`kind == "hop"`, treating rows without a kind as hops) and add a test that completes 20 hops and expects 20 admitted, then test the full 30-hop limit and refusal of the next hop. The original installation was not changed. The shipped copy corrects the count; `scripts/repro_fleet_cap_double_count.py` also runs an in-memory mutation of the original rule.
- A full 4 x 4 matrix cannot run through the cap: 16 cells x 2 hops = 32 hop rows (64 rows with outcomes) against a cap of 30 per 300 s. The breaker landed one day after the matrix run, and the record does not say the matrix was re-run afterwards; run by row with pauses, or raise the cap for test runs.
- A restart or a state-directory move that resets the ledger makes the breaker forget everything while the service looks healthy. The design notes therefore require "ledger row count continues to grow after a migration" as an explicit acceptance check; the state directory was deliberately never renamed.
- Check-then-act on a shared file under concurrency admits everyone ("every one reads a pre-limit ledger") -> one critical section and an inode re-check.
- A fallback path that was never tested is a time bomb: the registry fallback raised `AttributeError` the one time it ran (in mcp 2.x a tool-decorated function is not unwrapped), and it should not have existed at all because the router's point is to hold no roster -> delete it; make "discovery down" a distinct, fatal error.
- A degraded output that looks like a normal answer is worse than an error: a malformed registry reply read as "no matches" answered "no agent has this skill" -> validate the payload and raise a separate protocol error; an empty `matches` list is still a legitimate answer.
- Thresholds are guesses until measured: 6, 2, 12, 30 and 300 s were chosen by reasoning (a hop is minutes of work), not from a false-refusal rate. Treat them as starting values and log refusals.

### The rule

Bound loops with a wall-clock count of sessions that neither reads the prompt nor trusts a name, take the decision and the record in one critical section, and when a counter's documented limit and its observed limit might differ, test the observed one.

## Shipped reproduction

Use `python3 -B scripts/repro_fleet_cap_double_count.py` for the original-versus-corrected count and `python3 -B -m unittest tests.test_hub -v` for concurrency, process-tree, boundary and denoise checks. The source mutation stays in memory.
