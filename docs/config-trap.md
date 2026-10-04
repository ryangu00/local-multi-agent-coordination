# Chapter 6: The config-reading trap

### Problem

The default-reviewer map from Chapter 5 shipped on 2026-09-08 with unit tests and an end-to-end check, and did nothing for any worker. Why?

### What we built or changed

Workers are fresh child processes started by the dispatcher with the runtime's home variable set to the worker's profile directory (`<root>/profiles/<name>`). The generic configuration loader reads the file in the current home, that is the profile's own `config.yaml`. The fleet-wide table (default reviewer map, routing, quotas, master switches) existed only in the root `config.yaml`, which no worker reads. Reading a missing key does not raise: the loader returns an empty mapping, the lookup returns `None`, and `None` is the gate's exemption E2 ("no reviewer configured, fail open"). Failure looks exactly like "not configured".

Fix: a root-aware reader. Resolve the fleet root with the runtime's own helper (which returns the root even inside a profile environment), read the root file with the raw profile-config reader, and fall back to the generic loader if the root file cannot be read (in a single-profile deployment the two are the same file). Both the reviewer lookup and the master switch use it. Later the lookup was moved down into the database module so that the tool-layer gate and the dispatcher scan (Chapter 7) share the configuration lookup but keep their own criteria.

### Procedure as actually run

1. The first acceptance card (a body that never mentions review) completed with one run and zero review events: the gate did not fire.
2. Layer-by-layer investigation ended at the lookup, not the gate.
3. Measured the same function in two homes, then in four profile homes after the fix; after moving the code a third check ran in three homes (default, one worker profile, the reviewer's own profile) and the two layers' lookups agreed.
4. Explained the earlier "success": one card on 2026-09-08 appeared to prove the map worked, but its body named the reviewer explicitly, so it was the prompt path, not the table (a false positive).

### Results

| Environment (home set to) | Before fix | After fix |
|---|---|---|
| worker profile A | `None` | reviewer from the root table |
| default home | reviewer | reviewer |
| worker profile B | not measured | reviewer from the root table |
| worker profile C | not measured | reviewer from the root table |
| the reviewer's own profile | not measured | an implementer profile of another family (so it does not review itself) |

Consequence of the root cause: the map was inert in every non-default profile from the day it landed (2026-09-08), that is until the same-day acceptance failed; the tool-layer default and the new completion gate both depended on the lookup and failed together. The first acceptance run failed and the cause was found within the day.

Verification of the fix: four worker-profile homes resolved correctly; after the lookup moved, agreement in three homes. Because worker processes load the patched module fresh, no gateway restart was needed; calls made inside the long-lived gateway process pick the change up at its next restart.

### What did not work

| Attempt | Result |
|---|---|
| Unit test in the default home only | Passed; wrong environment. |
| End-to-end card whose body already named the reviewer | Passed through the prompt path and hid the fault. |
| Reading config through the generic loader in a worker | Empty mapping, `None`, silent exemption. |

### Pitfalls (symptom -> root cause -> fix)

- A gate passes everything in workers but blocks in your shell -> profile-dependent config loading returned `None` for a fleet-level key -> resolve fleet-level keys from the root, test in a profile environment.
- "Not configured" and "could not read configuration" are indistinguishable -> the loader returns an empty mapping on a miss -> make fleet-level readers return a distinguishable "unreadable" state or raise when the root file is expected but missing; keep fail-open only for the configured-but-absent case, and log which one happened.
- Every new gate that reads a table needs the same acceptance: run it once with the home variable set to a worker profile.

**A toy that reproduces the trap** (verified on 2026-10-03, stdlib only; included under `scripts/` of the shipped files): a root `config.json` holding `{"reviewer_map": {"worker-a": "reviewer-b"}}`, a profile `config.json` of `{}`, a child process started with `APP_HOME` set to each. Expected output:

| Home | Buggy lookup gate | Root-aware gate |
|---|---|---|
| default home | block (needs review) | block (needs review) |
| profile home | **allow (exempt)** | block (needs review) |

### The rule

A policy table read through a profile-relative loader is read from the wrong place and fails silent; resolve fleet-level policy from the fleet root, and never accept a gate until it has been run once in a worker's own home environment with its own exemptions disarmed.

## Shipped reproduction

Run `scripts/toy_profile_trap.py` with `TMPDIR` set to a scratch directory inside the repository. The supplied toy is copied unchanged. The board reader separately uses `APP_HOME` and the root/profile fallback. Unreadable policy remains fail-open in this re-creation; distinguishing unreadable from absent is the documented improvement, not a silently claimed production fix.

The [shorter field guide](https://github.com/ryangu00/agent-guards-that-fail-silently) covers this story briefly; this chapter adds mechanism, exemptions and the dispatcher scan without reproducing its tables.

