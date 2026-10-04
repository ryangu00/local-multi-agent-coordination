# Chapter 4: Chat loops between bots

### Problem

Several bots share a channel and are allowed to mention each other. The failure expected from early experience was a polite acknowledgement answered by a polite acknowledgement forever. The failure actually measured was different.

### What we built or changed

**Early design, May 2026: four cheap layers for a bridge process** (the process that turns a bot mention into an agent run).

1. Input filter: if the message body after stripping mentions matches a low-content pattern (ack, `...`, ok, thanks, a lone emoji) do not call the model; add a reaction. This is the cheapest layer.
2. Pair rate limit: per (sender, channel), if 3 triggers arrive within 60 s, mute that pair for 300 s.
3. Bot-aware prompt prefix: when the sender is a bot, prepend etiquette (be terse; reply `[ACK]` only when nothing new; do not reply to an incoming ack; end the discussion).
4. Output filter: if the generated reply is itself low-content (under 5 characters, all punctuation or emoji, matches the pattern), do not post, add a reaction.

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

Order is fixed (secrets, silence window, placeholder silence, mention rewrite, cooldown). Any internal error returns ALLOW with the original text ("never drop a message because of a gate error"); an environment variable is a live kill switch. State (silence windows, last-mention times) is per process and, since a restart was an escape hatch out of the cooldown, persisted atomically to a per-profile file and pruned of expired entries on load. Every suppress/block/rewrite appends one JSON line with a timestamp, gate name, channel, length and the first 12 hex of a sha256 of the content, never the content, so a suppressed secret is provable without being exposed. A health summary (enabled flag, registry loaded, bot count, audit path) is called at gateway start and logs a loud error if the net is switched off or the registry is empty, because "we thought the net was up but it was inert" had been the shape of earlier incidents.

### Procedure as actually run

1. **Baseline** (September 2026): a read-only script groups mention-bearing inbound messages per chat session over a 30-day window and prints, per event, message count and the maximum number of times one normalised sentence repeats (timestamps replaced by a placeholder, whitespace collapsed, first 120 characters).
2. **Audit trail** counted read-only on 2026-10-03.
3. **Reconstruction** of what the gates did during the one large event, from the audit file's timestamps.
4. **Tests**: 24 gate tests (silence window, expiry, trivial words, secret suppression with synthetic fixtures such as `sk-FAKE...`, name rewrite not doubled, cooldown, fail-open on missing state, kill switch, idempotent init) plus 6 integration tests that import a bridge and call the gates, plus five small gateway test files (loop dedup hook, persistence round trip with pruning, human-ack carve-out, startup alarm, streaming gate).

### Results

**What the baseline measured (30-day window, September 2026):**

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

**What the gates did during event A** (rows between 01:30 and 04:00 on 2026-09-04, one channel): 64 rows, of which 24 were "re-mention within 60 s" suppressions (first at 02:22:09, last at 03:12:39), 8 were empty-reply suppressions and 32 were mention rewrites. The loop ran for the full 74 minutes regardless.

Interpretation, flagged as inference from the numbers above, not a tested claim: the cooldown suppresses one outbound message at a time and never latches, so each suppression removed a post but the next scheduled-looking exchange continued; the per-sender burst rule from the early bridge design was 3 in 60 s, while 90 messages in 74 minutes is about 1.2 per minute in total, about 0.6 per minute per sender, so the aggregate cadence suggests that the burst rule missed it. This remains an inference; the averages alone do not establish every interarrival interval. A rate rule has to be sized from the loop you have actually observed.

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

### Pitfalls (symptom -> root cause -> fix)

- The safety net is "wired" but nothing is committed: an audit read only the committed tree and declared the net inert; the working tree had the wiring, and one file sync would have erased it -> audit the working tree and the effective runtime, not only the committed state; commit the wiring.
- Streamed replies bypass the outbound gate: the gate sat after an early return taken whenever a reply had already been streamed (the default path), so streamed output had zero suppression -> evaluate the gate at the single finalize point of the stream, exactly once.
- A stateful gate evaluated twice suppresses the bot's own reply: the cooldown records the mention it just allowed, so a second evaluation sees it and suppresses -> gate once per message, never per frame; add a test that fails if it is evaluated twice.
- A test that cannot fail: the streaming helper imported the gate module through a package path that did not exist; the import error was swallowed by the fail-open rule, so every test passed with no gate at all -> assert the suppress case actually drops the message.
- A human typing "[ACK] please do X" silenced the bot for the window -> only bot-authored acks open the window; keep the legacy default for older callers.
- A restart resets the cooldown and the silence window -> persist and prune on load.
- A gate net that is silently off -> startup health summary with a loud log line.
- Residual noted after a later upgrade: a new native-streaming branch in the runtime does not pass the gate (the chat platform's edit stream is unaffected). Record it as an open item.

### The rule

Size a chat loop bound from the loop you measured (cadence, content variety, who triggers it), make it latch rather than suppress one message at a time, and give the net an audit trail and a startup alarm so "off" is never silent.

## Shipped reproduction

Use `scripts/chat_gates.py`, `scripts/chat_stream.py`, `scripts/bridge_layers.py` and `scripts/baseline_loops.py`. The registry is explicitly injected. English silence cores have an extension argument. The neutral module does not include the runtime's richer redactor or tool guards. The synthetic log matches 90 messages, a 74-minute span and a maximum of 11 normalised repeats. Its sentences, exact cadence and remaining repeat distribution are synthetic. No latching fix is claimed.
