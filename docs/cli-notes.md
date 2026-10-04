# CLI adapter notes

Agent A was a terminal coding agent; agent B was a second coding agent from another vendor. The public registry contains only synthetic agents. No credential variable names, permission settings or production routing configuration are included.

## Permission sources

The recorded test found `--allowedTools` additive. A scoped shell pattern did not remove broad permission inherited from user settings: an arbitrary `date` command still ran. The successful narrowing used `--settings <file>` plus `--setting-sources ''`. An attempted push in dry-run mode was then denied. These are historical observations, not current-client compatibility tests.

Dropping user settings also dropped routing environment and the key helper. The child therefore needed explicit routing configuration. The public example does not supply that configuration; its values are deployment-specific prerequisites and are not known here.

## Sandbox and working directory

Agent B's read-only sandbox also blocked loopback networking. A read-only agent could receive work but could not call peers. The recorded combination was `--sandbox workspace-write -c sandbox_workspace_write.network_access=true`, with a scratch working directory. The network setting only took effect in workspace-write mode. Source hashes were unchanged after the audit.

This scoped direct writes. It did not prevent a request to an unsandboxed peer that could write the audited source. No stronger isolation claim follows.

## Non-interactive process setup

Agent A used `-p`; agent B used `exec`. Under launchd, an interactive alias or shell function is not an executable. The source record required absolute executable paths in installed command templates. The public fixtures use `python3` from the test environment; the print-only service generator requires an explicit interpreter path. Before using its output with launchd, resolve the fixture command's interpreter as well.

The adapter passes `/dev/null` for stdin, merges stderr into stdout, starts a process group, and kills the group on timeout or coroutine cancellation. Explicit protocol cancellation remains unsupported in the supplied adapter. The semaphore bounds spawned children. The example uses `max_concurrency = 6`; the recorded setting of 2 could starve a self-call holding an inbound and child slot.

## Output is part of the contract

A generic bracket-tag noise pattern removed errors along with startup banners. The corrected rule keeps error-looking lines even when they match the noise pattern, and retains the raw output if filtering would remove everything. The public test replays the three recorded error shapes with synthetic surrounding text.

The registry files use port 0 as a placeholder, not an advertised usable endpoint. The optional SDK smoke runner assigns ephemeral loopback ports in its own temporary registry. The process-tree fixture's prompt is a marker-file path; its test supplies one inside an isolated test directory.

## Optional registry as MCP

The original MCP registry used SSE and generated cards on every read. Skill matching inspected skill identifiers and names, not descriptions; the router logged candidates, matched skills and registry-order tie breaks. Discovery failure was fatal. Malformed payloads were protocol errors, while a valid empty `matches` list meant no match.

The optional MCP registry/router implementation is not shipped. Generated official SDK cards remain in `scripts/cards.py`; private capability counters and roster readers were removed. The original registry's bearer-free boundary and its rot test are explained in [Chapter 1](hub.md), rather than represented by a simulated network service here.
