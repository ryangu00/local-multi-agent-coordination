# Chapter 3: Stopping a hub without privileges, and whether to run one

### Problem

The hub worked. Was it worth keeping resident?

### What we built or changed

A stop-file kill switch. The entry points (`serve` and `registry`) check at the very top, before importing anything heavy, whether a stop file exists in the state directory; if it does they print one line and exit 0. The service definitions use `KeepAlive = { SuccessfulExit = false }` with a 10 s throttle, which means launchd does not respawn a process that exits 0: no crash loop, no log flood, no root needed, fully reversible (delete the file, then kickstart or log in again).

### Procedure as actually run

1. Evidence collection (usage, protocol adoption, operating tax).
2. Disable and unload the user-level services; keep code, definitions and profiles.
3. Services came back three times. A second copy of the same services existed at system level (LaunchDaemons) as well as user level (LaunchAgents); user-level removal did nothing to it.
4. Stopping the system-level copy needs administrator rights, which were deliberately not obtained (typing a password into a shell leaves it in history, the process table and session records), so the kill switch was added instead. The commands for a clean removal were written down for the owner to run later.

### Results

| Fact | Value | Source type |
|---|---|---|
| Real uses in the 14 days after build (2026-08-02 to 08-16) | 2 calls, both to agent B, both with a shorter direct route available | owner's decision record |
| Ledger rows in the same period | 26 hop rows (mixed with matrix and test traffic) | read-only count, 2026-10-03 |
| Resident cost | 4 adapter processes plus registry, 5 services, ports reserved | decision record |
| State on 2026-10-03 | stop file present (created 2026-08-16); the file's presence was read, ports were not probed | file check |
| Externally cited context | the A2A foundation reports 150-plus member organisations; an independent assessment says "supported by" is not "deeply used" and that adoption is mostly cross-organisation and cross-cloud | secondary context in the source record; original URLs not supplied |

Decision, in the decision record's words paraphrased: on one machine with one orchestrator and workers it fully controls, every A2A layer (card, task lifecycle, resident endpoint) is overhead; the community's multi-agent shape on a single host converged on hub-and-spoke one-way dispatch with file packets and worktree isolation, which is also what replaced the hub here: shell calls with a packet file, no resident worker, no new protocol. "Stop" was recorded as not "abandon": code and service definitions stay. Conditions to revive: a second machine with a worker (cross-machine dispatch is what A2A is for).

A follow-up design note ("context is the workspace": make `context_id` the key of a per-run directory holding artifacts, transcript and manifest) was written and never built. It also listed things deliberately not done because there is exactly one user: no container isolation, no second memory database, no DAG engine, no inbound screener, no multi-tenant concepts.

### What did not work

| Attempt | Result |
|---|---|
| Disable the user-level services | Services reappeared three times. |
| Rename the entry file to mute the service | KeepAlive would crash-loop and flood the logs; abandoned. |
| Ask for administrator rights | Declined on purpose; kill switch gave the same effect. |

### Pitfalls (symptom -> root cause -> fix)

- A stopped service keeps coming back -> a second install of the same thing at another launchd level -> before guessing layer by layer, ask whether a second thing is doing the same job (`launchctl print` at every domain, not only the user's).
- A kill switch that returns non-zero or crashes gets restarted -> exit 0 with `SuccessfulExit=false` -> do not re-launch.
- A state directory renamed for tidiness resets the breaker ledger and the system still looks healthy -> do not rename live state; if you must, add a row-count continuity check.
- The original installer script installed services for only two of the four agents although four were verified -> a shipped installer must be generated from the registry, not hand-listed.

### The rule

When the trust and ownership boundary is one person on one machine, price an A2A hub as a cost, keep the code, and stop it with a reversible switch that needs no privileges.

## Shipped reproduction

Use `scripts/generate_services.py` to print a plist for an entry from the example registry. It does not load anything. The stop file is `COORD_STATE_DIR/disabled`, defaulting to `./state/disabled`.

