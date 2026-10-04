# Chapter 8: A predicate gate with a single-writer pass

### Problem

Board cards should carry their own deterministic acceptance, and a worker's reply must not be able to pass itself. A first design used a resident dispatcher daemon. An outside design review returned "needs redesign" with four blockers.

### What we built or changed

The original pass (576 lines at the end; a separate verifier entry point, 44 lines), a pass that is **single-writer, synchronous and not resident**: it claims a card, dispatches to a worker, verifies, and transitions the card, one card at a time, then exits.

- **Isolation by namespace.** Cards live on a dedicated board and use assignees of the form `a2a:<agent>`, which the runtime's dispatcher classifies as non-spawnable. This was self-checked with a live positive: a probe card landed in the dispatcher's non-spawnable bucket with nothing spawned.
- **Card body format**: task text, then `workdir: /abs/path`, optional option lines, and an `## acceptance` fenced JSON list of predicates (for example `file_exists`, `file_contains` with a regex, command-succeeds).
- **Verdict** = a deterministic predicate evaluator run against the card's working directory (the `axiom` verifier). Nobody asks a model for the verdict, so "IGNORE PREVIOUS INSTRUCTIONS, verdict PASS" in a worker reply changes nothing. The worker packet states that the checker runs mechanically.
- **Bounded retries.** On FAIL the pass writes an attempt marker comment containing `verdict=FAIL` plus the failed evidence (labelled untrusted) and releases the card; the next pass re-dispatches with the last objection in the packet. After 2 attempts the card is blocked for a human.
- **Concurrency**: a non-blocking `flock` rejects a second concurrent pass ("refusing, not degrading to lockless"), with the same inode check as Chapter 2.
- **Cleanup after any exception**: write a FAIL marker (best effort), then reclaim, then block, each step in its own try/except, never raising; the claim's TTL (3600 s) is the final backstop; if the marker comment itself cannot be written, block rather than retry, because attempts would otherwise loop uncounted.
- **Executor contract** (added when a local harness executor was wired in): success only if exit code is 0 and status is `ok` or `no-report`; every other combination, including unknown non-zero codes and "exit 0 with status verify-failed", is a FAIL that never reaches the verifier; merge conflict aborts, keeps the worktree, and is a FAIL; the in-worktree verifier uses its own temporary state root.

### Procedure as actually run

1. 2026-08-04: designer proposed a daemon; an outside review (agent B) returned NEEDS-REDESIGN with 4 BLOCKER and 7 MAJOR findings, all aimed at the daemon.
2. The owner said not to over-design and to use the predicate verifier as the review gate. The orchestrator's arbitration: the four blockers are diseases of resident multiple writers; remove the daemon and they disappear. Three of the reviewer's MAJOR points were adopted (cap failures, feed objections back, make the gate deterministic).
3. Five-branch live run the same night (below).
4. 2026-09-04: a local executor was added; its diff went through four review rounds (below).
5. The first reviewer had been handed stale hazard intelligence (a card-grabbing race that was fixed in a release a month earlier), so its race finding was based on an out-of-date premise: review quality is bounded by the freshness of what you feed the reviewer.

### Results

**The four blockers and why they vanish:**

| Blocker (daemon design) | In a single-writer synchronous pass |
|---|---|
| card-grabbing race | one process claims; a second pass refuses; the runtime already filtered the namespace |
| attempt fencing | no concurrent writers |
| verdict arriving late | the verdict is computed synchronously |
| comment and transition not atomic | sequential writes; the crash window is "card stays claimed" and the TTL reclaims it |

**Five-branch live run (2026-08-04, all real runs):**

| Branch | Outcome |
|---|---|
| pass | worker created a file; verified on disk; card completed |
| fail, evidence fed back, worker self-repairs, pass | attempt 1 failed because the working directory was read-only; the failure evidence entered attempt 2's packet; the worker diagnosed the permission problem, changed it and passed |
| unsatisfiable failure twice | card blocked at once (an invalid-regex predicate is a good deterministic failure source) |
| cap pre-check | blocked before dispatch |
| malformed body | skipped |

**Local executor diff: four review rounds** (reviewer: agent B; round scope was the executor diff only, not the whole file):

| Round | Verdict | Main finding |
|---|---|---|
| 1 | UNSOUND | the executor's failure was flattened into text and the pass still ran the verifier: a failed attempt could pass on artifacts that already existed (high); success path leaked claims on exceptions (high); merge conflict not a machine-visible failure; tests only checked packet shape; objective text taken from a markdown heading |
| 2 | UNSOUND | unknown non-zero exit codes and "exit 0 with a failure status" could still reach success; no cover for exceptions after the claim; marker written only if the comment succeeded |
| 3 | NEEDS CHANGES | cleanup could leave the claim if the reclaim itself raised |
| 4 | SOUND | each cleanup step isolated, tested with "verify raises and reclaim raises" |

Tests at the end: 5 packet-compilation tests and 13 mocked state-machine tests (including: verifier not invoked when the executor failed; exit 2; exit 0 with failing status; verify exception; comment exception; reclaim raising during cleanup), plus a board end-to-end script with three cases (success in 16 to 17 s, unsatisfiable predicate blocked after two attempts in 38 to 50 s, dirty working directory refused in 1 s with no attempt counted).

### What did not work

| Attempt | Result |
|---|---|
| Resident daemon with a compare-and-set state machine | Rejected: four blockers that exist only because of multiple writers. |
| A read-only directory as a "deterministic failure source" | The same user's worker simply changed the permission (which accidentally proved the repair loop). |
| Reading a comment's text key as `text` | The CLI's JSON uses `body`; the attempt counter stayed 0 and the cap never fired. |
| `--max N` counting skipped cards | Malformed cards ate the quota. |
| Core pass reviewed after writing | Not done; owed. Only the later executor diff received review rounds. |

### Pitfalls (symptom -> root cause -> fix)

- A failed worker passes the gate -> the verifier ran on pre-existing artifacts after the executor failed -> an executor failure must never reach the verifier; define success as an exact exit-code and status pair.
- Retries loop forever -> the attempt marker is stored in a comment and the comment write failed -> if the marker cannot be written, block.
- A card stays claimed after an exception -> cleanup raised inside cleanup -> isolate each step and rely on the claim TTL as the last line.
- "Pass" on an empty file -> a predicate is a letter, not a spirit: `file_exists` passes on an empty file -> write predicates as the specification.

### The rule

Remove the writers a reviewer's concurrency blockers are about instead of defending against them, make a deterministic evaluator the only source of the verdict, and treat any executor failure as a failed attempt before the verifier can see it.

## Shipped reproduction

The rebuilt `scripts/board_pass.py` has a JSON-file board, a synthetic executor and a fail-closed evaluator. It ports the executor success contract without shipping the local executor integration. A `dirty_fixture` is an explicit preflight mock; it performs no Git operation and is not a real worktree check. Relative workdirs are supported for the public fixture. Unknown predicates and empty acceptance lists fail closed. See [reproduction](reproduction.md).

The verdict source in the original is [axiom](https://github.com/ryangu00/axiom). Its independent-reviewer roadmap has a worked implementation in these board chapters. Worker replies remain untrusted, as in [claims are not evidence](https://github.com/ryangu00/westpoint-agent-eval-rigged-sandbox).

