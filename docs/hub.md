# Chapter 1: Four local CLI agents behind an official A2A adapter

### Problem

The owner wanted any of four local CLI agents to be able to hand work to any other: single hop, chain A to B to C, and fan-out to several at once. A first design used a home-made dispatch layer and a second used MCP `_meta` fields to carry the chain; both were rejected by evidence (below). Selection rule written at the top of the work: official first, community second, hand-built last; no invented protocol fields; every "custom" piece must say why neither official nor community code covers it.

### What we built or changed

**Rejected routes (each with the evidence that rejected it).**

| Route | Why rejected |
|---|---|
| Own unified dispatch layer | Re-invents MCP plus A2A v1.0. |
| Chain in MCP `_meta` | Probe server captured the coding-agent A client's handshake: `protocolVersion: 2025-11-25`, and `_meta` was null in all three handshake frames; agent B's CLI marked the probe server `Unsupported`. The MCP spec revision was already published; client implementations had not followed. |
| Upgrade the client to unlock `_meta` | The changelog of a newer client (2.1.220) listed no MCP protocol upgrade entry. |
| Chain in tool arguments | A public issue in the coding-agent A repository (a public client issue, a feature request later marked "not planned") documents the same shape failing: an `is_subagent` argument cannot work because a sub-agent does not know it is one. Verified by reading the issue on 2026-10-03. |

**Chosen design: A2A trunk, MCP as registry.**

- Protocol layer is the official `a2a-sdk` only. Chain provenance rides on three first-class protocol fields, so no agent has to report anything about itself: `context_id` (groups one conversation), `task_id` (one unit of work), `reference_task_ids` (the tasks this one refers to, which is the chain). Reflected from the installed SDK on 2026-08-02: `Message` has `message_id, context_id, task_id, role, parts, metadata, extensions, reference_task_ids`; `Task` has `id, context_id, status, artifacts, history, metadata`.
- **Adapter** (`CliAgentExecutor`): one A2A request becomes one non-interactive CLI invocation. The command is a shell-style template with `{prompt}` and `{session}` placeholders; each is substituted as a single argv element and executed with `create_subprocess_exec`, so there is no shell and no re-parsing (a review confirmed no command-injection path). stdin is `/dev/null` (these CLIs block on a pipe nobody writes), stderr is merged into stdout, the child runs in its own session/process group, concurrency is capped per adapter by a semaphore, and any CLI-side failure comes back as agent text rather than a transport error, so a crashed tool is distinguishable from an unreachable agent.
- **Per-agent registry entry** (`agents.toml`): `port`, `max_concurrency`, `timeout_s`, `command`, optional `cwd`, `env_set`, `env_unset`, `drop_line_regex`, `skills`, `description`, `status` (`verified` or `blocked`, with a `note`). A blocked agent is recorded as blocked; the matrix was not allowed to pretend.
- **Agent cards are generated, never written.** Cards are built with the SDK's own types from live state (count of MCP servers, skills, routable models, roster size) and serialised with protobuf's JSON converter; a count that cannot be established is shown as absent, not zero. Card endpoint is the 1.0 well-known path `/.well-known/agent-card.json`.
- **Registry** is an MCP server (SSE, loopback) exposing a `resource://agent_cards/list` resource and `find_agents` / `list_agents` tools. One deliberate departure from the official sample: the sample loads cards from a directory of checked-in JSON; this registry builds cards from the generator on every read, because a registry that answers from a stale copy is worse than none. The sample's embedding-based matching was not adopted (four known agents; needs an external API key); matching is substring over skill id and name only.
- **Router** (`route.py`) holds no roster. It asks the registry at call time, picks the agent with the most matched skills, and writes the basis (all candidates, matched skills, whether a tie was broken by registry order) to a decision log. No match answers "no agent advertises this skill" instead of guessing.
- **Fan-out** (`fanout.py`): every target gets its own deadline and failure slot; the result lists who answered and who did not; refusals carry a marker so an aggregator does not count "I declined to run" as an answer; exit code is non-zero when nobody answered.
- **Auth**: servers bind to loopback only and require a bearer token; the card endpoint is public. The token file is created with mode 0600 atomically (`O_EXCL`), and reading it refuses a symlink, a different owner, or group/world access; comparison uses `secrets.compare_digest`. Loopback alone is not authentication (any local process, including a browser page, can reach a loopback port, and these endpoints spawn real agents). Recorded boundary: the registry has no bearer.
- **Chain inheritance through the environment**: an adapter exports `context`, `task` and `refs` (a JSON list, not a comma-joined string, because an id containing the separator split into two ancestors) into the child it spawns; the call helper inherits them, and merges explicit references with inherited ones instead of replacing them (replacing had silently shortened the chain). Before this, an agent's sub-call opened a fresh context and a real multi-hop chain was logged as N unrelated single hops.
- **Caller identity from the ledger, not from the environment**: the variable an adapter exports lives in the child it spawns and never crosses the wire, so reading it on the receiving side returns the callee's own name. The caller is resolved from the ledger by looking up the parent task (last reference).

### Procedure as actually run

1. **Preconditions first.** Official sample run attempted; the SDK on the machine reflected to confirm the four chain fields exist as protocol fields. The sample needed a hosted-model API key that was not available, so "run the sample end to end" was recorded as unverifiable, and its purpose (the SDK works here) was satisfied by the running hub.
2. **Single adapter, then more.** Agent B first (non-interactive `exec`), then agent D; a 3-hop chain D to B to D confirmed one `context_id` across hops with `reference_task_ids` accumulating.
3. **Four-agent adapters, status honest.** After the first pass 2 of 4 agents were verified; the other two were recorded as blocked, with the reasons found later to be wrong (below).
4. **Matrix.** `matrix_test.py`: for each caller A and callee B, ask A (through its adapter) to run the call helper against B with a token, and require B's token verbatim in the reply. Every cell is two real hops. The four self-call cells were kept on purpose as the deadlock check.
5. **Adversarial review through the hub itself.** Each batch of code was reviewed by agent B (a different vendor) reached over the hub's own A2A path, so the new channel reviewed the new code.
6. **Self-audit against the plan.** The initial implementer claimed all ten completion criteria met, then re-checked against the plan and found at least four short; the source record does not supply an itemised table of those criteria.

### Results

**Call matrix, 2026-08-02** (one machine, one run per cell, token must come back verbatim):

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

### Pitfalls (symptom -> root cause -> fix)

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

### The rule

Put chain provenance in protocol fields filled by the adapter, not in anything the model is asked to report, and count a multi-agent system as working only when a verbatim token has made the full round trip and every "blocked" label has been re-diagnosed from the real error, not the printed one.

## Shipped reproduction

The official SDK remains responsible for protocol types. `scripts/process_runner.py` is extracted from the adapter for stdlib tests. `scripts/matrix_test.py --by-row` defaults to a local subprocess mock and is explicitly not a new A2A result. See [reproduction](reproduction.md) and [CLI notes](cli-notes.md).

