# Server-Managed PTT Timeout

## Scope

This document defines the authoritative Relay-side maximum talk duration for a
single granted talker. It applies independently to every active `sender_id`,
including when multi-talk is enabled. It does not change the membership lease
or client-side microphone safety timers.

The maximum duration is advertised by `SERVER_CONFIG` as `maximum_talk_seconds`.
It is an absolute talk lease: audio activity, `KEEPALIVE`, duplicate `PTT_ON`,
and FEC traffic MUST NOT extend it.

## Relay time base and grant snapshot

The Relay MUST measure every active talk lease with a monotonic clock. The
lease starts when the Relay accepts `PTT_ON` and emits `TALK_GRANT`; call this
instant `grant_time`.

For a nonzero configured duration `T`, the deadline is:

```text
deadline = grant_time + T seconds
```

The Relay MUST NOT forward `AUDIO` or `FEC` for that talker once its monotonic
clock reaches the deadline. It MUST release the talker and broadcast exactly
one `TALK_RELEASE` with reason `SERVER_TALK_TIMEOUT` as promptly as its event
loop permits. Packets received before the deadline but still queued at the
Relay MUST be discarded rather than forwarded late.

A value of zero disables the server-managed maximum duration. A disabled
maximum duration MUST NOT be interpreted as a client-side default limit.

The Relay snapshots the maximum duration when it grants a talker. A later
configuration reload or `SERVER_CONFIG` update applies to subsequent grants;
it MUST NOT silently alter the deadline of an already granted talker. An
operator that must terminate an active talker early MUST send `TALK_RELEASE`
with reason `SERVER_POLICY`.

## Release reasons

`TALK_RELEASE` has the following five-byte payload:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | `talker_id` (`u32`) |
| 4 | 1 | `release_reason` |

| Value | Name | Meaning |
|---:|---|---|
| `0x00` | `CLIENT_PTT_OFF` | Relay accepted the talker's `PTT_OFF`. |
| `0x01` | `SERVER_TALK_TIMEOUT` | The granted maximum talk duration elapsed. |
| `0x02` | `MEMBERSHIP_TIMEOUT` | The talker's membership lease expired. |
| `0x03` | `CLIENT_LEAVE` | Relay accepted the talker's `LEAVE`. |
| `0x04` | `SERVER_POLICY` | Relay or administrator ended the active talk for policy reasons. |
| `0x05-0xff` | reserved | A receiver MUST treat an unknown value as a release. |

Relay-generated `TALK_RELEASE` packets MUST use the resolved talker ID in both
the common header `sender_id` and payload `talker_id`.

A Relay MUST emit only one release for a grant. If `PTT_OFF`, `LEAVE`, a
membership timeout, or a server timeout race, the Relay uses the first event
processed for that grant and ignores later termination events. A duplicate
`PTT_OFF` or `LEAVE` after release MUST be harmless and MUST NOT generate a
second release broadcast.

## Floor-control interaction

A `PTT_ON` received from an already granted sender remains idempotent: the
Relay sends a unicast `TALK_GRANT` but MUST NOT reset or extend that sender's
deadline. This rule prevents retrying clients from bypassing the timeout.

When multi-talk is enabled, each granted talker has its own deadline. Expiring
or releasing one talker MUST NOT release other active talkers or reset their
deadlines. The released slot becomes available to a pending/new floor request
according to normal Relay policy.

The Relay remains authoritative even if a client did not receive
`SERVER_CONFIG`, has an inaccurate local timer, or maliciously continues to
send media. It MUST reject media outside an active grant window.

## Client behavior

A client MAY show the advertised maximum duration as a local countdown, but
that countdown is informational only. The Relay release is authoritative.

On `TALK_RELEASE` for the local sender, a client MUST immediately:

1. mark the current PTT grant as ended;
2. stop capture/encoding for the grant;
3. discard queued uplink media and parity frames for that grant; and
4. stop any source-file transmission associated with that grant.

A client MUST NOT automatically issue another `PTT_ON` merely because the
physical/button input remains held after a `SERVER_TALK_TIMEOUT` release. A
new press edge is required before requesting the floor again. This avoids an
unintended immediate re-grant loop at the maximum-duration boundary.

On a remote `TALK_RELEASE`, receivers MUST retain already accepted media in
their bounded per-talker playout buffer and drain it under `playout.md`.
They MUST NOT delay the release indefinitely waiting for missing packets, and
MUST start an end-of-talk cue only after that accepted media has drained.

## SERVER_CONFIG delivery

The Relay MUST send `SERVER_CONFIG` after each successful `JOIN` before it
sends a `TALK_GRANT` for that endpoint. It MAY send a new `SERVER_CONFIG` to
joined endpoints after a policy reload. Clients MUST use the most recently
received configuration only for user feedback and for future floor requests;
they MUST NOT assume it changes a currently granted lease.

## Required interoperability cases

Implementations MUST test at least the following cases:

1. `maximum_talk_seconds = 0` permits an active talk until ordinary release.
2. A single talk expires at the monotonic deadline, emits reason `0x01`, and
   forwards no post-deadline audio/FEC.
3. Duplicate `PTT_ON` does not move the deadline.
4. In multi-talk mode, one expiring talker does not interrupt another.
5. A client receives `SERVER_TALK_TIMEOUT`, stops local uplink, and requires a
   new press edge before another floor request.
6. A receiver drains already buffered remote audio before playing its
   end-of-talk cue.
