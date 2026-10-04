# Complete result and mechanism tables

These are the supplied historical records. They are not measurements made by the shipped synthetic fixtures. Dates, conditions and qualifiers remain attached. No raw production state is published.

## Recorded setting

Conditions: one M4 Max Mac, 64 GiB, macOS and launchd; original August and September 2026 work, with the identified 2026-10-03 package re-run.

| Component | Recorded version or form | Condition |
|---|---|---|
| Hub Python | 3.13.x; 3.13.13 in the 2026-10-03 re-run | Project requires >= 3.13; package manager `uv`. |
| `a2a-sdk` | 1.1.2 | Protobuf types, snake_case fields; Apache-2.0. |
| `mcp` | 2.0.0 in the re-run; registry written against 2.x | `MCPServer`, SSE transport. |
| Reference sample | `a2aproject/a2a-samples`, `samples/python/agents/a2a_mcp` | Its lock pinned the withdrawn `a2a-sdk` 0.3.0 wheel; fetch returned 404. |
| Agent A | a terminal coding agent, 2.1.158 at the August 2026 handshake probe | Non-interactive `-p`. |
| Agent B | a second coding agent from another vendor, around 0.144 in August 2026 | Non-interactive `exec`. |
| Task board | SQLite board and 60-second dispatcher tick, release tag 2026.8.31, local patches | MIT upstream; runtime intentionally unnamed. |
| Board storage | `journal_mode=DELETE`; embedded SQLite 3.50.4 | The original hit the WAL-reset corruption bug; relevant to timing, not gate logic. |
| Chat | A Discord-style server with bot accounts | Numeric mention syntax; only synthetic identifiers ship here. |

## Chapter 1: hub

Original hub work: 2026-08-02 on one M4 Max Mac, 64 GiB; one run per matrix cell unless a row says otherwise. These are historical records, not the offline fixture results.

### Rejected routes (each with the evidence that rejected it).

| Route | Why rejected |
|---|---|
| Own unified dispatch layer | Re-invents MCP plus A2A v1.0. |
| Chain in MCP `_meta` | Probe server captured the coding-agent A client's handshake: `protocolVersion: 2025-11-25`, and `_meta` was null in all three handshake frames; agent B's CLI marked the probe server `Unsupported`. The MCP spec revision was already published; client implementations had not followed. |
| Upgrade the client to unlock `_meta` | The changelog of a newer client (2.1.220) listed no MCP protocol upgrade entry. |
| Chain in tool arguments | A public issue in the coding-agent A repository (a public client issue, a feature request later marked "not planned") documents the same shape failing: an `is_subagent` argument cannot work because a sub-agent does not know it is one. Verified by reading the issue on 2026-10-03. |

### Call matrix, 2026-08-02 (one machine, one run per cell, token must come back verbatim):

| Stage | Cells passing | Condition |
|---|---|---|
| After first four adapters | 2 of 4 agents verified | Two agents recorded as blocked. |
| After fixing the three non-transport faults and the two wrong diagnoses | **16 of 16** | Including 4 self-call cells; a cell is a two-hop round trip. |

**Fan-out and chain** (same week):

| Measure | Value |
|---|---|
| Four-way concurrent fan-out wall time | 14.3 s (sum of single calls: more than 40 s) |
| Fan-out with a 6 s per-target deadline | 2 of 4 answered, 2 of 4 timed out, call still returned, missing agents named |
| Three-hop chain | one `context_id`, `reference_task_ids` accumulated per hop, no agent self-reported anything |
| Auth | no token: 401; card endpoint without token: 200; with token: full chain works |
| Router decision log | 21 rows in total (read-only count 2026-10-03); a skill nobody advertises returned "no match" rather than a guess |

**Review rounds on the hub** (reviewer: agent B via the hub; counts as recorded):

| Batch | Findings | Outcome |
|---|---|---|
| First adapter batch | round 1: 1 BLOCKER (timeout did not kill the child), 4 MAJOR (no concurrency cap; loopback is not auth; MCP count off by one; only one exception type caught) plus an unimplemented placeholder; round 2: six verified fixed, 3 new; round 3: all fixed | GO after 3 rounds; no command injection |
| Matrix batch | 2 BLOCKER + 1 MAJOR | all upheld and fixed |
| Registry/router batch | round 1: 1 BLOCKER + 2 MAJOR + 2 MINOR; round 2: NO-GO with 2 more | all upheld; GO after round 2 |
| Loop-prevention batch | 3 BLOCKER + 4 MAJOR, then 2 specific attacks (see Chapter 2) | GO after 2 rounds |

### What did not work

| Attempt | Result |
|---|---|
| MCP `_meta` baggage for the chain | Absent on the wire (`_meta` null in all handshake frames). |
| Tool-argument self-identification | Public issue shows the same design failing. |
| Following the official sample as-is | Its lock pinned a withdrawn wheel; the sample itself had rotted. Fix: remove the lock and upgrade to 1.1.2. "Official reference" still has to be run to count. |
| `max_concurrency = 2` | A self-call holds the inbound slot and a child slot; one more outbound call starves the pair. The symptom is not a fast failure but a hang until the client timeout, which reads as a network problem. Raised to 6. |
| Matrix token `OK-caller-target` | Models "helpfully" shortened it to `OK`, which was logged as a transport failure. Use a token with no separator. |
| Agent C without an identity | About 1 call in 3 returned an onboarding greeting instead of working. Fixed with an identity block plus a workspace instructions file that is always injected; four consecutive runs stable. |
| Output noise filter that dropped any bracket-tagged line | It also dropped `[error]` and `[fatal]` lines, leaving only plain prose, so a failed call read as a success. Replaced by a named list of noise tags, with error-looking lines always outranking the drop pattern; a regression test replays the three reviewer-supplied reproductions and was also run against the old pattern to prove it discriminates. |
| 16 cells at once | About 30 concurrent CLI sessions on one machine fail from congestion, not from real faults. Run by row. |
| Two router-served agents calling each other | Two sessions share one router; one transient network error seen, retry passed. Read a single failed cell with that in mind. |

Full procedure, non-tabular observations and limitations: [hub](hub.md).

## Chapter 2: loop bounds

Original bounds: reasoned defaults, not calibrated measurements; review reproductions as recorded, with the dated re-run on 2026-10-03 distinguished below.

Every adapter appends one row per request to a shared local ledger keyed by the protocol's `context_id`. The same file is the audit log and the input to loop detection. Adapters and call helpers carry chain provenance, but clearing the inherited environment can still reset a sub-call's context and depth. The fleet-wide count remains the backstop because it ignores both context and identity.

**Three bounds** (constants as shipped; chosen by reasoning, not measurement):

| Bound | Rule | Constant |
|---|---|---|
| depth | refuse a hop when the chain already has 6 references | `MAX_DEPTH = 6` ("a hop is a full CLI session, so a chain this long is minutes of work") |
| repeat | refuse the same agent being given the same question a third time in one context | `MAX_REPEAT = 2`; fingerprint = first 16 hex of sha256 over the whitespace-normalised prompt |
| breaker | refuse an agent past 12 sessions in 300 s, and refuse everything past 30 sessions fleet-wide in 300 s, whatever context anyone claims | `BREAKER_MAX = 12`, `BREAKER_FLEET_MAX = 30`, `BREAKER_WINDOW_S = 300` |

### Seven first-round findings, all upheld (3 BLOCKER, 4 MAJOR) and two second-round attacks:

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

**Ledger in use** (read-only count, 2026-10-03): 96 rows written 2026-08-03 to 2026-08-15: 26 hop rows (to agent B 16, agent D 4, agent A 4, agent C 2; 24 single, 2 chained), 26 outcome rows (24 ok, 2 not ok), 44 rows in the earlier format. Test traffic and real use are mixed in these rows.

### What did not work

| Layer | Why it failed as a bound |
|---|---|
| Depth | An agent that spawns its sub-call with a cleaned environment loses the inherited context, so depth restarts at zero. |
| Repeat | Fingerprints normalise whitespace but not paraphrase; appending a counter makes every hop a new question. |
| Per-agent quota alone | Only as strong as the number of agent names; rotation multiplies the ceiling by the roster size. |
| "Child killed" reporting | True and useless when grandchildren survive. |

Full procedure, non-tabular observations and limitations: [loop-bounds](loop-bounds.md).

## Chapter 3: stopping services

Operational decision: 2026-08-02 to 2026-08-16; usage is the owner's account, with a separate read-only ledger and stop-file check on 2026-10-03.

Stopping the system-level copy needs administrator rights, which were deliberately not obtained (typing a password into a shell leaves it in history, the process table and session records), so the kill switch was added instead. The commands for a clean removal were written down for the owner to run later.

### Results

| Fact | Value | Source type |
|---|---|---|
| Real uses in the 14 days after build (2026-08-02 to 08-16) | 2 calls, both to agent B, both with a shorter direct route available | owner's decision record |
| Ledger rows in the same period | 26 hop rows (mixed with matrix and test traffic) | read-only count, 2026-10-03 |
| Resident cost | 4 adapter processes plus registry, 5 services, ports reserved | decision record |
| State on 2026-10-03 | stop file present (created 2026-08-16); the file's presence was read, ports were not probed | file check |
| Externally cited context | the A2A foundation reports 150-plus member organisations; an independent assessment says "supported by" is not "deeply used" and that adoption is mostly cross-organisation and cross-cloud | secondary context in the source record; original URLs not supplied |

A follow-up design note ("context is the workspace": make `context_id` the key of a per-run directory holding artifacts, transcript and manifest) was written and never built. It also listed things deliberately not done because there is exactly one user: no container isolation, no second memory database, no DAG engine, no inbound screener, no multi-tenant concepts.

### What did not work

| Attempt | Result |
|---|---|
| Disable the user-level services | Services reappeared three times. |
| Rename the entry file to mute the service | KeepAlive would crash-loop and flood the logs; abandoned. |
| Ask for administrator rights | Declined on purpose; kill switch gave the same effect. |

Full procedure, non-tabular observations and limitations: [stopping-services](stopping-services.md).

## Chapter 4: chat loops

Chat baseline: a 30-day window in September 2026; audit: 2026-06-21 to 2026-09-16. The later dispatch figures are not a controlled chat-versus-board comparison.

A reaction protocol tells senders what happened (working, done, error, input filtered, loop-muted); sender contract: if the only response is a reaction, stop mentioning. Blocking all bot messages was rejected because it destroys deliberate cross-bot delegation.

**Gate net, June 2026: a dependency-free module** (646 lines in the original module, stdlib only, YAML optional there) that any bridge or gateway can call before posting.

| Gate | Stage | Rule | Constant |
|---|---|---|---|
| ack window | inbound | a bot-authored message starting with `[ACK]` (after stripping leading mentions) opens a per-channel silence window; a human `[ACK ...]` does not | 8 s |
| block secrets | outbound | suppress a reply matching credential shapes (a union of a 3-pattern base and, in a gateway process, a richer redactor) | n/a |
| enforce silence | outbound | suppress anything posted inside the silence window | 8 s |
| keep silence | outbound | suppress pure placeholder silence (trivial words, bracketed "silent" shells, a language-agnostic core list); never inspect text longer than 30 characters | 30 chars |
| fix mention | outbound | rewrite plain-text bot names to numeric mentions so the peer is actually triggered | n/a |
| loop cooldown | outbound | suppress a reply that mentions the same bot again within a window, per (me, target) | 60 s |

### What the baseline measured (30-day window, September 2026):

| Event | Span | Mention-bearing inbound messages | Max repeats of one normalised sentence | Notes |
|---|---|---|---|---|
| A | 2026-09-04 02:00 to 03:14 (74 min) | 90 | 11 | a scheduled job at 02:00 made one bot report; the second bot answered; they exchanged short receipt acknowledgements; 31 distinct contents after timestamp removal (working notes) |
| B | 2026-08-07 | 7 | 1 | same peer |
| Window total | 30 days | 97 | n/a | (the working notes quote "97 messages in 74 minutes" for event A; 97 is the 30-day total of both events, 90 is event A by the script) |

The failure shape is a scheduler-triggered periodic exchange of short sentences, not a long chain. A definition of "six consecutive messages with no human interruption" counted zero events and was discarded.

**Gate-net audit trail, 2026-06-21 to 2026-09-16 (376 rows):**

| Gate or act | Rows |
|---|---|
| secret redaction in outbound or streamed text | 131 |
| mention rewrite (chained) | 127 |
| re-mention within 60 s suppressed | 67 |
| inbound ack window opened | 17 |
| outbound suppressed inside the ack window | 6 |
| reply containing a credential suppressed (base 6, richer redactor 2) | 8 |
| tool guard blocked a credential-exfiltration tool name | 6 |
| empty or trivial reply suppressed (empty 8, `ok` 1, ack pattern 1, emoji 1, `[SILENT]` shell 2) | 13 |
| tool-output redaction | 1 |

The working notes also explained the event as "the loop protection was inert". That is not supported: the directory hook that had been inert was activated and the gates wired on 2026-06-20 and 2026-06-21, months before event A, and the audit file shows the gate firing during it. That explanation is dropped from the book.

**Why a board instead of chat** (background paragraph only; there is no controlled chat-versus-board comparison):

| Measure | Chat baseline | Five real tasks dispatched through the runtime's bot-messaging mode (3 hosted-room, 2 direct-message) |
|---|---|---|
| Bot-to-bot messages per task | event A: 90 | max 2 |
| Max sentence repeat | 11 | 1 |
| Pick-up rate | historic board baseline 4 of 9 (44%) | 5 of 5 |
| Pick-up latency | n/a | 14.4, 19.5, 31.4, 79.6, 185.8 s; median 31.4 s |
| Delivered work that was fabricated | not measured | 2 of 5 (after a silent fall-back to a weak model; caught by an independent reviewer or a re-check) |

The five-card test measured a bot-messaging mode, and the board baseline is a weak one (the board had had no new cards for three months). Pre-registered pass rules were absolute: per card at most 10 bot-to-bot messages and repeat at most 2; at least 4 of 5 picked up with median latency at most 70 s. After the dispatcher went live, five days of use (2026-09-06, 08, 09, 10, 14) gave up to 14 cards a day, pick-up 100% and median dispatch latency 38 s.

### What did not work

| Attempt | Result |
|---|---|
| Blocking bot-authored messages | Rejected: kills legitimate delegation. |
| Per-message re-mention suppression as the only loop control | Fired 24 times in event A; event still lasted 74 minutes. |
| Definition "six consecutive bot messages without a human" | Counted zero events in a window that contained a 90-message loop. |
| Treating a prompt instruction as a control | The prompt prefix is layer 3, not a bound. |

Full procedure, non-tabular observations and limitations: [chat-loops](chat-loops.md).

## Chapter 5: review gate

One board, 2026-09-06 to 2026-09-08; gate findings re-verified as described. Historical acceptance results are distinct from the rebuilt toy tests.

**Why not a hook:** the lifecycle hooks had claimed, completed and blocked events and worker-start/stop events, but no review-requested event and no pre-complete event; the completed event fires after the write transaction commits.

**Exemptions of the completion gate** (any one allows the call; short-circuit in order):

| # | Condition | Why it must be exempt |
|---|---|---|
| E1 | kill-switch setting false (default: on) | one config change closes it without a code change |
| (retry) | card already done or archived | completion retries are an idempotent branch in the database; blocking them reports a committed completion as "please request review" |
| E2 | no default reviewer resolves for the assignee | external or unregistered lanes would otherwise deadlock (fail open) |
| E3 | the latest `review_requested` event is not an explicit self-handover (normalised, case-insensitive); malformed evidence is lenient here | the caller is the reviewer approving, or rework after rejection; without this review could never be closed. Evidence is the event, not a run: the event is written unconditionally, a run only sometimes |
| E4 | a child card pre-created before this card's first run | the board guidance says a parent with pre-created review/QA/release children should complete directly; completion is what releases them |
| E5 | this call is not a worker call | manual or orchestrator back-fills have no worker context; "has any run" is the wrong test because the database synthesises a zero-length run for manual transitions |

### Default behaviour and the prompt control (one board, 2026-09-06 to 09-08):

| Date | Control | Cards | Who reviewed |
|---|---|---|---|
| 2026-09-06 | none (smoke test) | 3 (two itemised) | implementer reviewed itself |
| 2026-09-06 | prompt names reviewer | card 1 | named reviewer, correct |
| 2026-09-06 | prompt names reviewer | card 2 | named reviewer, correct |
| 2026-09-08 | prompt names reviewer, body equally clear | card 3 | `reviewer = None`, implementer reviewed itself |
| | **Prompt compliance** | **2 of 3** | |

**Completion-gate acceptance (2026-09-08):** A card with no review mention in its body was refused on its first run with "the producer cannot be the acceptor"; the worker obeyed; the review event carried implementer and reviewer; the reviewer completed it. A parent with a genuinely pre-created child completed in one run with zero review events; the child was released and reviewed.

**Review of the gate: 12 findings, 0 false positives** (reconciliation table, each re-verified):

| Finding | Verdict | Disposition |
|---|---|---|
| legitimate reviewer blocked (event but no run) | upheld | fixed (evidence is the event) |
| independent QA child is itself blocked | upheld | not fixed: telling a review card from an ordinary card needs parent/title, which a worker can forge; workaround in the card convention |
| any child exempts, two tool calls to bypass | upheld, most serious | fixed: child must predate the card's first run |
| worker names itself reviewer to get a pass | upheld | fixed: equal normalised names are not a handover |
| reviewer profile in the map may not exist | upheld | not fixed in the gate; reconciliation script gained the existence assertion |
| child check and commit not atomic | upheld | not fixable at tool layer; recorded |
| synthetic run mistaken for a worker | upheld | fixed |
| completion retry mis-reported | upheld | fixed |
| same-machine CLI completion and direct DB writes skip the gate | upheld | claim downgraded |
| `blocked` escapes; the refusal text only asks | upheld | recorded; not mechanically blocked because blocked is for real escalation |
| refusal text omitted ids and metadata | upheld | fixed |
| E3 is a permanent history exemption, not "current version reviewed" | upheld | recorded; intended |

**The claim, downgraded.** The first decision text said a worker could not bypass cross-family review. It was withdrawn. Three hard facts: the command-line completion path goes straight to the database write after the goal judge and never calls the gate (a worker has its own valid task, run and claim variables); any process with write access to the database file can update it; and after a refusal a worker can mark the card blocked, which mechanically ends the run. The gate's honest capability is: when a worker completes through the tool layer, it mechanically stops the two most common failures (forgot to request review; reviewing itself) and gives a copy-paste next step. It is not a permission boundary.

### What did not work

| Attempt | Result |
|---|---|
| Prompt only | 2 of 3 compliance; the miss had an equally clear body. |
| A lifecycle hook | No suitable event exists (no pre-complete; completed fires after commit). |
| An external watchdog that reassigns self-reviewed cards | Races the dispatcher tick; the dispatcher may already have claimed the card for self-review. |
| Making `reviewer` required | Breaks every path that needs no review; larger divergence from upstream. |
| "Any child card" as exemption | Two legitimate tool calls bypass it. |
| "Block is forbidden" in the refusal text | Text only; the call still succeeds. |

Full procedure, non-tabular observations and limitations: [review-gate](review-gate.md).

## Chapter 6: config trap

Config trap found and fixed on 2026-09-08; profile measurements and the separate toy re-run on 2026-10-03 are identified below.

The earlier "success" was misleading: one card on 2026-09-08 appeared to prove the map worked, but its body named the reviewer explicitly, so it was the prompt path, not the table (a false positive).

### Results

| Environment (home set to) | Before fix | After fix |
|---|---|---|
| worker profile A | `None` | reviewer from the root table |
| default home | reviewer | reviewer |
| worker profile B | not measured | reviewer from the root table |
| worker profile C | not measured | reviewer from the root table |
| the reviewer's own profile | not measured | an implementer profile of another family (so it does not review itself) |

Verification of the fix: four worker-profile homes resolved correctly; after the lookup moved, agreement in three homes. Because worker processes load the patched module fresh, no gateway restart was needed; calls made inside the long-lived gateway process pick the change up at its next restart.

### What did not work

| Attempt | Result |
|---|---|
| Unit test in the default home only | Passed; wrong environment. |
| End-to-end card whose body already named the reviewer | Passed through the prompt path and hid the fault. |
| Reading config through the generic loader in a worker | Empty mapping, `None`, silent exemption. |

- Every new gate that reads a table needs the same acceptance: run it once with the home variable set to a worker profile.

**A toy that reproduces the trap** (verified on 2026-10-03, stdlib only; included under `scripts/` of the shipped files): a root `config.json` holding `{"reviewer_map": {"worker-a": "reviewer-b"}}`, a profile `config.json` of `{}`, a child process started with `APP_HOME` set to each. Expected output:

| Home | Buggy lookup gate | Root-aware gate |
|---|---|---|
| default home | block (needs review) | block (needs review) |
| profile home | **allow (exempt)** | block (needs review) |

Full procedure, non-tabular observations and limitations: [config-trap](config-trap.md).

## Chapter 7: dispatcher evidence

Dispatcher first-day acceptance: 2026-09-09; review and operating records are as stated, not a new production re-run.

| Layer | Cost of a false positive | Therefore |
|---|---|---|
| tool-layer gate | blocks real work; the implementer is stuck | lenient, fail open |
| dispatcher scan | one extra log line and event | strict |

### Spec errors found by the implementer (all three were "read what the function does, not what it requires of the caller"):

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

Full procedure, non-tabular observations and limitations: [dispatcher-evidence](dispatcher-evidence.md).

## Chapter 8: predicate pass

Predicate live branches: 2026-08-04; later executor diff: 2026-09-04. The shipped JSON-board tests are synthetic and do not reproduce the live timings.

### The four blockers and why they vanish:

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

Full procedure, non-tabular observations and limitations: [predicate-pass](predicate-pass.md).

## Non-tabular observations retained with their conditions

Conditions: read-only hub ledger count on 2026-10-03, covering 2026-08-03 to 2026-08-15; real and test traffic are mixed.

| Measure | Recorded value |
|---|---|
| Total ledger rows | 96 |
| Hop rows | 26: to B 16, D 4, A 4, C 2; 24 single and 2 chained |
| Outcome rows | 26: 24 ok and 2 not ok |
| Earlier-format rows | 44 |

Conditions: event A audit selection, one channel, 2026-09-04 01:30 to 04:00; these are gate events, not message totals.

| Measure | Recorded value |
|---|---|
| Selected audit rows | 64 |
| Re-mention suppressions | 24; first 02:22:09, last 03:12:39 |
| Empty-reply suppressions | 8 |
| Mention rewrites | 32 |
| Event span despite suppression | 74 minutes |
| Aggregate cadence, computed inference | about 1.2 messages/minute total; about 0.6 per sender |

Conditions: five real tasks in bot-messaging mode, not a controlled board-versus-chat trial; the historic board baseline had no new cards for three months.

| Pre-registered criterion | Required value |
|---|---|
| Bot-to-bot messages per card | at most 10 |
| Maximum repeat | at most 2 |
| Pick-up | at least 4 of 5 |
| Median latency | at most 70 s |

Conditions: an explicit-reviewer end-to-end run in the 2026-09-08 gate work; one recorded run.

| Phase | Recorded observation |
|---|---|
| Execution | 228 s |
| Review after reassignment | 79 s; 41 tool calls; probes re-run and one nit found |
| Gate review reconciliation | 12 findings, 0 false positives; 6 fixed, 3 not fixed, 3 recorded limits |
| Decision narrative discrepancy | 11 itemised findings, five named fixes; the reconciliation also includes the missing-refusal-metadata fix |
| Temporary-database acceptance after fixes | 9 of 9; original temporary tests no longer available |

Conditions: five days of dispatcher operation, 2026-09-06, 08, 09, 10 and 14; aggregate record, no post-deployment flag count supplied.

| Measure | Recorded value |
|---|---|
| Daily cards | up to 14 |
| Pick-up | 100% |
| Median dispatch latency | 38 s |

Conditions: later executor integration after 2026-09-04; original live and mocked tests, not the public toy's elapsed times.

| Check | Recorded result |
|---|---|
| Packet compilation tests | 5 |
| Mocked state-machine tests | 13 |
| Board end-to-end success | 16 to 17 s |
| Unsatisfiable predicate | blocked after two attempts in 38 to 50 s |
| Dirty working directory | refused in 1 s; no attempt counted |

The public offline results are reported separately in [validation](validation.md). Their counts are new test observations, not replacements for any historical table.
