# Chapter 5: Self-review is the default on a task board

### Problem

An agent runtime with a SQLite task board has a review step that is on by default: when a card enters the review state, the dispatcher claims it and starts a reviewer using the card's current assignee. The tool a worker calls to request review takes an optional `reviewer`. A worker that omits it is therefore reviewed by itself. This is the upstream default, not a misconfiguration; the upstream guidance text only says `reviewer=<optional-profile>`.

### What we built or changed

Three successive controls, each found insufficient by measurement.

1. **Prompt** (2026-09-06): a card convention document and a closing instruction written into every card body naming the reviewer.
2. **Tool-layer default reviewer** (2026-09-08): a flat table in configuration, `kanban.default_reviewer_map: {implementer profile: reviewer profile}`, consulted by the review-request tool when `reviewer` is empty. Rules: ordered by model family, same family never reviews itself (two implementers shared a family, so one reviewer from a third family covers all of them; the reviewer's own cards go to an implementer of another family); an unknown assignee, or a table entry that maps a profile to itself, returns `None` so upstream behaviour is kept rather than inventing a wrong reviewer. Because the reviewer parameter is applied before dispatch, the reassignment has no race with the dispatcher (an external watchdog that rewrites after the fact would race with the 60-second tick).
3. **Completion gate** (2026-09-08): a check at the top of the completion tool, before the database write, because a worker could also skip review entirely by completing the card.

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

The refusal text has four parts: why it was refused, the reviewer to use, a copy-paste call to the review tool (with the summary and metadata to carry over), and an explicit "do not escape by marking the card blocked". Any exception inside the gate returns "allow": a gate that errors must never freeze a card.

**Reconciliation script** (stdlib plus YAML): compares the configuration table with the table in the convention document, exits 1 on any difference, any one-sided entry, any self-review entry, and (added later) any profile named in either table that the runtime does not recognise; it names the profile, the side (implementer or reviewer), the mapping and the source. It uses the runtime's own profile-exists function rather than listing a directory, and tests inject a fake existence function; if the runtime cannot be loaded it exits 2 rather than reporting green.

### Procedure as actually run

1. 2026-09-06: smoke test of the dispatcher with two real cards; the verdict write-up records every smoke-test card as self-reviewed (it names two itemised, one more counted).
2. 2026-09-06 and 09-08: three cards under the prompt control, checked for who reviewed (table below).
3. 2026-09-08: tool-layer map; unit checks for the lookup (known implementers resolve, the reviewer's own profile resolves to an implementer, unknown, `None` and empty return `None`); end-to-end with a card whose body deliberately has no reviewer instruction.
4. 2026-09-08: completion gate; acceptance used a card whose body never mentions review and a parent with a pre-created child.
5. Adversarial review of the gate by agent B (static, attacker posture), 12 findings, each re-verified by the orchestrator in source or a temporary database.

### Results

**Default behaviour and the prompt control** (one board, 2026-09-06 to 09-08):

| Date | Control | Cards | Who reviewed |
|---|---|---|---|
| 2026-09-06 | none (smoke test) | 3 (two itemised) | implementer reviewed itself |
| 2026-09-06 | prompt names reviewer | card 1 | named reviewer, correct |
| 2026-09-06 | prompt names reviewer | card 2 | named reviewer, correct |
| 2026-09-08 | prompt names reviewer, body equally clear | card 3 | `reviewer = None`, implementer reviewed itself |
| | **Prompt compliance** | **2 of 3** | |

**First end-to-end with an explicit reviewer:** execution 228 s, reviewer started after reassignment and took 79 s, 41 tool calls (it re-ran the probes itself, read the routing file, and found one nit the implementer had not mentioned): independent review, not stamping.

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

So 6 fixed, 3 upheld and not fixed, 3 recorded as limits. (The decision record itemises 11 of the 12, naming five fixes; the reconciliation table also lists the fix for refusal text that omitted ids and metadata.) After fixes, 9 of 9 cases passed on a temporary database: 3 bypass cases blocked (post-hoc child, self-named reviewer, case-variant self-review) and 4 legitimate paths allowed (genuine pre-created child, genuine handover to another family, event without a run, completion retry on a done card), plus the baseline (no review, no child: blocked) and a non-worker call (allowed).

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

### Pitfalls (symptom -> root cause -> fix)

- Review "on" yet implementers review themselves -> default dispatch uses the current assignee and the reviewer argument is optional -> resolve the reviewer mechanically before dispatch.
- Changing an implementer's model silently re-creates same-family review -> the map is ordered by family and drifts with model changes -> recompute the table whenever any profile's primary model changes and run the reconciliation script from cron.
- An assignee written as a nickname instead of the runtime's profile name -> the dispatcher classifies the card non-spawnable and it sits ready forever, no error -> assignee must be a profile name; two cards with a nickname assignee had not been picked up in three months.
- A reviewer profile that does not exist -> the card is moved to review and the dispatcher skips it every tick -> existence assertion in the reconciliation script.
- A retired poller aimed at the same cards -> after the new flow the review cards' assignee became the poller's pick-up condition, so keeping it would have created a double-claim race; its log held 13 lines in 70 days, all "starting" -> retire stale pollers when you change the flow that feeds them.
- Verifying a gate whose exemptions eat the harness: after the worker-context fix, the worker test reads two environment variables; without them every check shows "allowed" and looks like "no false blocks" -> before testing a gate, test that the harness is not eaten by the gate's own exemptions (set the worker variables explicitly).

### The rule

If an unmentioned parameter lets an agent judge its own work, resolve it in code before dispatch, give the code an explicit list of exemptions that you can name and test, and write down in the same document what the gate cannot stop.

## Shipped reproduction

The rebuilt `scripts/toy_board.py` uses `tasks`, `task_runs`, `task_events` and `task_links`. `tests/test_board.py` supplies both `WORKER_TASK` and `WORKER_RUN`; without them E5 would swallow the worker tests. The toy uses JSON configuration to remain dependency-free; `configs/board.example.yaml` shows only the relevant policy keys.

The [shorter field guide](https://github.com/ryangu00/agent-guards-that-fail-silently) covers this story briefly; this chapter adds mechanism, exemptions and the dispatcher scan without reproducing its tables.
