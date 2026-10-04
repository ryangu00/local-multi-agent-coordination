# Chapter 7: Evidence in a loop the agent cannot call

### Problem

Chapter 5 ends with a gate that is a reminder. A worker could still finish a card from the command line without review. Enforcement has to live in a process the worker cannot call. What should that process do, and by which criteria?

### What we built or changed

A scan in the dispatcher's tick, step 0, run under the board's single-writer lock before reclaiming, promoting or spawning anything. The dispatcher interval is 60 s. The scan is observation only:

- It records one `review_enforcement_flagged` event on the card (payload: implementer, expected reviewer, a fixed reason string, board name) and one WARNING log line. It never changes card status, never dispatches, never messages.
- It fails open: any exception is swallowed and dispatch continues.
- A per-board watermark (highest event id seen) is kept in one global JSON file; the read-modify-write happens inside one `flock`. The first run only builds the watermark and scans nothing (otherwise the first tick would flag all history). Candidates are cards with a `completed` event whose id is above the watermark. Idempotence: a card that already has the flag event is not flagged again. A master switch (default on) is read from the fleet root (Chapter 6); when it is off the scan returns before reading the watermark, so completions during the off period are scanned after it is switched on again, which makes "turn it off" a safe emergency action.
- If the lock cannot be taken, the watermark is still written (best effort, one warning): writing only when locked left the previous value at 0 and, combined with the first-run branch, would have made the scan return silently forever.

**The verdict function** (a done card is flagged when all of these hold):

1. status is done;
2. there is at least one non-zero-duration run (`ended_at IS NULL OR started_at < ended_at`), which is also how manual book-keeping cards are excluded;
3. a reviewer resolves for the implementer, where the implementer is the profile of the first non-zero-duration run;
4. no other profile has a non-zero-duration run on the card (this also covers rework after rejection);
5. no genuinely pre-created child: a child whose creation time is earlier than the card's first run and whose own `created` event lists the card among its parents.

**Three decisions that the record argues for.**

*Detect only, never reopen.* The helper that cascades a reopen only downgrades descendants to todo; flipping the parent's status is the caller's responsibility and the contract for it (target state, assignee, run and claim fields, what to do with running descendants) does not exist in that release; the command line deliberately has no done-reopen verb. Calling the helper alone yields the worst state: parent still done, every finished descendant invalidated. The decision is "do not build", not "build and default off". The value is that anyone who bypasses the tool-layer gate leaves an event the tool layer will not let them remove: an upgrade from a reminder to evidence, not to enforcement.

*Two layers deliberately differ.* A first spec demanded that the scan reuse the gate's logic. The implementer refused and gave counter-examples in both directions: with a single event whose payload is `{}` the gate exempts and the scan flags; with a handover to a reviewer followed by a self-handover the gate rejects the latest and the scan, seeing the earlier non-zero-duration reviewer run, does not flag. Failure costs are opposite:

| Layer | Cost of a false positive | Therefore |
|---|---|---|
| tool-layer gate | blocks real work; the implementer is stuck | lenient, fail open |
| dispatcher scan | one extra log line and event | strict |

Only the configuration lookup is shared; each layer's code comment names the other and says why they differ. "Gate allows, scan warns" is not a contradiction; it is the point of an observing layer.

*Who did the work comes from the runs, not the assignee.* The review-request call rewrites the card's assignee to the reviewer and inserts two zero-length synthetic runs for that profile. The first scan version derived the implementer from the assignee, so a worker that "handed over" to a name missing from the map made the reviewer lookup (condition 3) find nothing, and the whole verdict allowed at once; it also reported the wrong person. Using the first non-zero-duration run fixes both; a worker cannot create someone else's non-zero-length run through the tools. Same-user database writes remain outside this boundary.

### Procedure as actually run

1. The orchestrator wrote a specification; an outsourced implementer (agent B) refused to implement it and cited three conflicts with the code's own documentation; each was re-checked in source and upheld.
2. A second outsourced draft (a cheaper model lane) produced a patch with a self-check table that was all green and described as a path walk-through, not an execution; the orchestrator read it line by line and changed five things (below) before production.
3. Applied to production with timestamped backups; kill switch tested.
4. Two-leg adversarial review: one reviewer agent from the board's reviewer lane (5 findings) and one from a cheap-model lane (4 findings), every claim re-verified.
5. Five-criterion live acceptance on the first day, then five days of real cards.

### Results

**Spec errors found by the implementer** (all three were "read what the function does, not what it requires of the caller"):

| Claim in the specification | What the code's own documentation said |
|---|---|
| calling the descendant-invalidation helper reopens the card | it only downgrades descendants; the caller must flip the parent in the same transaction |
| "has at least one run" excludes manual back-fills | manual completion synthesises a zero-length run, so "has a run" includes them |
| the scan must reuse the gate's logic | the layers' failure costs are opposite (above) |

**Defects in the outsourced draft** (five; the first is the dangerous one):

| # | Defect | Severity | Effect if shipped |
|---|---|---|---|
| 1 | "first run only builds the line" return placed after the candidate query | high | first tick flags all history; one board had about 20,100 events (20,094 and 20,145 at two moments) |
| 2 | event-append helper called without an open transaction (its docstring says it must be inside one) | high | broken write |
| 3 | `kind LIKE '%completed%'` guess | medium | over-wide; the real kind is exactly `completed` (one of 15 kinds in that database) |
| 4 | watermark written only when the lock was acquired | medium | lock failure leaves it at 0 and the scan permanently blind after the first-run fix |
| 5 | module-level import where the file's convention is lazy in-function import | low | new import-time dependency edge |

**Review legs** (reviewer's raw findings; all re-verified by the orchestrator):

| Leg | Findings | Real | False positive | Suggested fix usable as written |
|---|---|---|---|---|
| reviewer lane | 5 | 4 | 1 (claimed full table scan; query plan shows a primary-key range scan, 20 narrow lookups 0.1 ms total, worst case 1.4 ms) | 0 of 2 |
| cheap-model lane | 4 | 4 | 0 | 0 of 2 |
| total | 9 raw, 8 distinct (two legs found the same hole) | 7 | 1 | none |

The two legs converging on the same hole was read as a strong signal. None of the four suggested fixes could be adopted as written: two did not close the hole, one would have excused the mechanism's core use case, one was an accepted trade-off. External review is valuable for finding where; deciding how remains the orchestrator's job.

**Two bypasses reproduced by the reviewers and then closed:**

| Bypass | Why the first fix failed or was replaced |
|---|---|
| after being refused, link any older card as a child of your own card, then complete from the command line (the "pre-created child" exemption was satisfied by creation time alone; the link tool is open to workers and has no ownership check) | adding an ownership check does not close it: the attacker links their own card as parent and an old card as child; replaced by "the child's own `created` event must list this card as a parent" (post-hoc links only write a different event, `linked`; at the time the whole database held 4 links and 0 such events, so nobody had used post-hoc links) |
| claim to hand over to a reviewer that never appears, then complete from the command line | first fix ("the named reviewer must have a run") failed: the review call itself synthesises two zero-length runs for that name; the real defect was deriving the implementer from the assignee (above) |

One more suggestion was declined on purpose: adding "outcome is completed" to condition 2 would exclude a card whose first run crashed and was reclaimed, but that is the mechanism's core case (the acceptance card's runs were a crashed 121 s run and a zero-second completion), and flagging a card that someone actually ran, that crashed, and was then marked done with no review is a true statement.

**First-day acceptance (2026-09-09, all measured):**

| Criterion | Result | Evidence |
|---|---|---|
| first run builds the line silently | pass | ten boards got a watermark; 0 flags on existing history; no warnings |
| command-line bypass is flagged | pass | worker ran 121 s with no review and no children; completed from a terminal (proving the tool gate does not stop that path); next tick wrote 1 flag with the four payload fields correct; card status unchanged; WARNING logged |
| no false flag | pass | a parent satisfying four of the five conditions and exempt only through a genuinely pre-created child (child created 17 s before the parent's first run) was not flagged; a QA review child was not flagged; both confirmed to have entered the scan range |
| flagged once | pass | watermark rewound by hand to force a rescan; watermark advanced again, flag count stayed 1, no duplicate warning |
| switch | pass | switch off: the same kind of card across two ticks was not flagged and the watermark did not advance (370 stayed 370); switch on: flagged at once with correct payload |

Two weak greens were caught and strengthened: the "flagged once" check initially never exercised the idempotence guard because the watermark made every card a candidate only once, and the harness's own "was this card scanned" guard had its direction reversed. Rule applied: a negative assertion about a card that was never in the scan range is an empty assertion; use cards created after the first-run baseline.

**Operating data:** five days (2026-09-06, 08, 09, 10, 14), at most 14 cards on a day, pick-up 100%, median dispatch latency 38 s. No post-deployment flag counts were recorded in the source record; none is claimed here.

### What did not work

| Attempt | Result |
|---|---|
| Auto-reopen of flagged cards | Not built: no parent-transition contract in that release. |
| One shared criterion for both layers | Each shared form moves one layer to the wrong side of its failure-cost curve. |
| Implementer from the assignee | Rewritten by handover; both a bypass and a wrong name. |
| Ownership check on the link tool | Does not close the post-hoc link bypass. |
| Adding "completed" outcome to condition 2 | Hides the mechanism's central case. |
| Trusting a green self-check from an outsourced draft | It was a path walk-through; the first-run defect only shows in a real first run. |

### Pitfalls (symptom -> root cause -> fix)

- Watching for bypass inside the agent's own tool -> the worker has a terminal and a valid claim -> observe from the dispatcher.
- Flag count of zero after deploy -> may mean the guard is blind, not that nobody bypassed (watermark never written, switch off, wrong board) -> deploy with a deliberate positive control (a card completed from a terminal) and a rewind test.
- An observing layer that silently stops (lock unavailable, first-run branch) -> permanent silent blindness -> best-effort write plus one warning is better than perfect-but-silent.
- A write to the board from a new component outside a transaction -> write helper expected an open transaction -> read the helper's docstring first line.

### Limits to state in the book

- Detection, not prevention; a flagged card stays done.
- The flag event is tamper-evident only against actors who work through the tools. A process of the same operating-system user with write access to the database file can edit or delete events; real separation needs another operating-system identity or file permissions the worker lacks (not built).
- The strict scan flags a card whose worker crashed after a run and was later marked done, by design.
- The runtime patches were uncommitted working-tree changes (about 464 inserted lines across two files) when the source record was prepared, with the temporary-database tests of the 9-of-9 run no longer on disk; this repository ships a rebuilt toy with its own tests, not the patch.

### The rule

Put the enforcement and the evidence where the constrained agent cannot call, let the blocking layer be lenient and the observing layer strict, derive "who did the work" from facts the actor cannot forge, and prove the observer is alive with a positive control.

## Shipped reproduction

The toy tick calls the scan under its board lock before the next-step callback. A global JSON watermark is locked across read/modify/write. Tests force candidate-range entry, an actual terminal-style completion, a rewind, and off/on catch-up. They also reproduce both criteria counter-examples and the post-hoc-link and zero-length-run bypasses. Initially empty toy boards use key presence, rather than a positive watermark value, to recognise an established baseline.

The [shorter field guide](https://github.com/ryangu00/agent-guards-that-fail-silently) covers this story briefly; this chapter adds mechanism, exemptions and the dispatcher scan without reproducing its tables.

