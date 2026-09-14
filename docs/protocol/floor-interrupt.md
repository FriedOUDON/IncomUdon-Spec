# Floor Interrupt v1

## Scope

Floor Interrupt v1 is an optional Relay floor-control extension for an
admitted, higher-priority talker to preempt a lower-priority active talker. It
is intended for managed operational channels, not as a general client-selected
priority mechanism.

Floor Interrupt v1 is disabled by default. It MUST be enabled independently
per Relay policy and MUST NOT be available unless all of the following are
true:

1. Identity Admission v1 policy is `required`;
2. Control Authentication v1 is required for the channel; and
3. the requester has a current Identity Admission or Managed Service Admission
   state with `talk` and `interrupt` permission.

A Relay MUST fail closed at startup if Floor Interrupt v1 is enabled while
Identity Admission is not `required` or Control Authentication v1 is not
required. It MUST NOT grant an interrupt request using only a channel password,
Control Authentication group key, sender ID, source endpoint, or a client-
supplied priority. This requirement prevents a shared channel credential from
becoming an implicit preemption authority.

## Admission-derived authority

Admission tickets and Service Admission Grants use the following permission
bits:

| Bit | Name | Meaning |
|---:|---|---|
| 0 | `listen` | Join and receive channel traffic. |
| 1 | `talk` | Request ordinary floor access with `PTT_ON`. |
| 2 | `interrupt` | Request Floor Interrupt with `PTT_REQUEST`. Requires `talk`. |

An admission with `interrupt` MUST carry `pri`, an unsigned interrupt priority
from 1 through 255. A Relay derives the requester's effective priority only
from the currently verified admission claim. It MUST treat an absent `pri` as
zero and MUST reject an admission that sets `interrupt` without both `talk` and
a valid non-zero `pri`.

The Access Service determines `interrupt` and `pri` for Identity Admission.
The Management Service determines them from the mTLS service ACL for Managed
Service Admission. A client UI MAY expose an interrupt PTT control only after
it learns that the current admission authorizes it, but displaying that control
does not confer authority.

`recorder` and `observer` Managed Service roles MUST NOT receive `interrupt`.
A deployment MUST restrict interrupt grants to explicitly authorized identities
or automation services and SHOULD audit issuance, renewal, use, denial, and
revocation.

## PTT request packet

Floor Interrupt introduces `PTT_REQUEST` with packet type `0x1A`. It uses the
normal Version 1 28-byte Control Authentication header and has exactly one
payload byte:

| Bit | Name | Requirement |
|---:|---|---|
| 0 | `INTERRUPT_REQUESTED` | MUST be set. |
| 1-7 | reserved | MUST be zero on transmit and ignored on receive. |

A client requests ordinary floor access with the existing empty-payload
`PTT_ON`. It sends `PTT_REQUEST` only when it deliberately requests an
interrupt. A Relay MUST reject a `PTT_REQUEST` payload that is not exactly
`0x01`; it MUST NOT silently treat it as ordinary `PTT_ON`.

A requester waits for `TALK_GRANT` before sending media, exactly as for
ordinary PTT. `TALK_DENY` remains the denial response and does not disclose
whether denial resulted from disabled policy, missing permission, equal/higher
priority, no selectable victim, or another local policy condition.

## Relay preemption algorithm

For every `PTT_REQUEST`, the Relay MUST first validate ordinary membership,
Control Authentication, current admission, `talk`, `interrupt`, and non-zero
`pri`. It then applies this algorithm atomically with floor-state updates:

1. If an active-talker slot is available, grant the requester without releasing
   another talker.
2. If no slot is available, choose exactly one active talker with the lowest
   effective admission priority.
3. Grant preemption only when the requester priority is strictly greater than
   the selected talker's priority.
4. If no lower-priority active talker exists, send `TALK_DENY` and change no
   active talk state.
5. If preemption is allowed, immediately stop forwarding AUDIO and FEC from the
   selected talker, broadcast `TALK_RELEASE` with reason `PREEMPTED`, then
   grant the requester and begin its ordinary server-managed PTT lease.

With single-talk policy, the selected active talker is the sole current talker.
With multi-talk policy, the Relay MUST preempt only one lowest-priority active
talker to create one slot; it MUST NOT clear all talkers for one request.
For equal lowest priorities, the Relay MUST use a deterministic tie-breaker,
with lower numeric `sender_id` selected first.

The Relay MUST serialize release and grant processing. It SHOULD send the
`PREEMPTED` release before the replacement `TALK_GRANT`; UDP reordering remains
possible, so receivers must handle either ordering without retaining obsolete
media. The new talker receives a fresh normal PTT lease; it does not inherit
any remaining duration from the preempted talker.

A successful `PTT_REQUEST` creates a new normal talk grant. Its
`grant_time` and server-managed deadline are defined by `ptt-timeout.md`,
whether the grant used an available slot or replaced another talker. An already
granted talker that retransmits `PTT_REQUEST` receives an ordinary unicast
`TALK_GRANT` only when it remains active. Such a retransmission MUST NOT
preempt another talker, reset the talk lease, or change active priorities.

## Release and playout behavior

`TALK_RELEASE` reason `PREEMPTED` has value `0x07`. A preempted local sender
MUST immediately end its PTT grant, stop capture/encoding, discard queued
media/FEC/source-file frames, and require a new physical or UI press edge
before it may request the floor again.

Unlike an ordinary remote release, a receiver handling `PREEMPTED` MUST remove
the preempted talker from the output mix with a fade of no more than 20 ms,
discard all unrendered jitter-buffer, FEC, and decode-ordering state for that
talker, and suppress that talker's end-of-talk cue. It MUST NOT wait for old
speech to drain before rendering the replacement talker. This cleanup applies
only to the preempted sender and MUST NOT reset another active talker's state.

## Management and diagnostics

Management Plane v1 ACLs MAY grant `interrupt` and a priority only to an
explicit service/channel assignment. The grant-issuance API MUST derive the
claim from that ACL; it MUST NOT accept a caller-selected priority value.

A Relay SHOULD expose redacted diagnostics counters for interrupt requests,
grants, denials, preemptions, and rejected unauthorized requests. Audit records
MUST contain the requesting admitted identity/service, channel ID, replaced
sender ID when applicable, effective priorities, result, and timestamp. They
MUST NOT contain channel credentials, keys, full tickets, full grants, or
source network addresses.

## Required interoperability cases

1. A Relay with Floor Interrupt disabled rejects `PTT_REQUEST` and leaves an
   active talker unchanged.
2. A Relay with Identity Admission other than `required` does not enable Floor
   Interrupt.
3. A requester with only `listen` or only `talk` is denied and cannot preempt.
4. An interrupt admission without valid non-zero `pri` is denied.
5. A higher-priority requester preempts one lower-priority talker, emits
   `PREEMPTED`, stops old media forwarding, and grants a fresh lease.
6. Equal or lower priority requests are denied without ending any active talk.
7. A full multi-talk channel replaces exactly one deterministically selected
   lowest-priority talker.
8. Receivers discard only the preempted talker's unrendered audio and do not
   play an end-of-talk cue for it.
9. A duplicate request from an already granted talker does not preempt another
   talker or extend its current talk deadline.
10. `PTT_REQUEST` is rejected when its Control Authentication header, tag, or
    client nonce replay state is invalid.
11. A `PREEMPTED` `TALK_RELEASE` uses an authenticated 28-byte Control
    Authentication header and is rejected when its Relay-generated tag is
    invalid.

## Deterministic vector

`../../test-vectors/floor-interrupt-v1.json` contains byte-for-byte authenticated
`PTT_REQUEST` and `PREEMPTED` `TALK_RELEASE` envelopes, including their
28-byte Control Authentication headers, nonces, Control Key ID, and HMAC tags,
plus authorization and selection cases.