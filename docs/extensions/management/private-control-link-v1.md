# Private Control Link v1

## Scope

Private Control Link v1 is an optional Management Plane v1 extension for the
trusted control connection between one Management Service and one Relay. It is
not an HTTP API, a Directory protocol, or a client-facing transport. It carries
narrow Relay-control commands and optional redacted Relay lifecycle and audit
inputs.

A deployment that does not enable this extension MUST retain normal Relay and
Management API behavior. It MAY enable Managed Service Admission without this
extension: that profile supports grant issuance and natural expiry, but has no
standards-defined remote administrative revocation path. After an ACL removal,
service disablement, or grant revocation, the Management Service MUST NOT issue
new affected grants, but the action does not alter a grant issued before the
change, whether or not it has previously been presented to or accepted by the
Relay. Such a grant remains eligible for Relay acceptance until its normal
expiry or another already-defined Relay-local invalidation condition. A
deployment MUST NOT claim prompt Relay-side administrative revocation without
this extension. A deployment that needs prompt ACL, service, or grant
revocation of an already-issued grant MUST enable this extension.

This extension does not carry media, channel credentials, derived keys,
admission grants, OIDC material, client certificate private keys, source IP
addresses, or UDP ports.

## Separate listener and transport

The Relay Control Endpoint and the Management Service form the two roles of a
Private Control Link. The Management Service initiates the connection to the
Relay Control Endpoint. The endpoint MUST use a listener distinct from the
externally reachable Management API HTTPS listener. It MUST NOT share a TCP
port, HTTP route, certificate authorization policy, or network exposure with
that API.

A deployment MUST use exactly one of these transports for a link instance:

- On one host, an OS local socket with peer-credential checks is RECOMMENDED.
  Unix Domain Sockets are the standard local-socket binding. The socket path
  MUST be owned and permissioned so that only the Relay and the explicitly
  authorized Management Service OS identities can connect.
- Across hosts, the endpoint MUST listen on a dedicated internal TCP port using
  TLS 1.3 or later with mutual TLS. The port MUST be reachable only from the
  Management Service network boundary and MUST NOT be exposed to ordinary
  client or Directory networks.

For mTLS, the Relay MUST map the verified Management Service client certificate
to one configured `management_service_id`. A certificate that is accepted by
the external Management API MUST NOT gain Private Control Link access merely
by that fact. The control link MUST have an explicit authorization mapping;
using a separate private CA or separate certificate profile is RECOMMENDED.

For a local socket, the Relay MUST derive the authorized service identity from
verified OS peer credentials and its local mapping. If the operating system
cannot provide peer credentials for the selected local-socket mechanism, the
deployment MUST use mTLS instead. The `management_service_id` in `hello` is a
consistency check and MUST exactly equal the identity derived by the Relay. It
MUST NOT be trusted as authentication input. It uses the Managed Service ID
lexical grammar defined in `overview.md`, but identifies the Management Service
control peer and is not required to equal an admitted service's `svc` value.

## Framing and messages

The link is a bidirectional byte stream. Each message is one frame:

```text
U32BE(json_length) || UTF8(JSON message)
```

`json_length` MUST be from 2 through 65536. Senders MUST NOT compress frames.
Receivers MUST reject a zero-length, oversized, malformed UTF-8, malformed JSON,
or schema-invalid frame before dispatching it, and MUST close the connection for
a framing violation. A receiver MUST NOT allocate an unbounded buffer from an
untrusted length prefix.

Every message validates against
`../../../schemas/management/private-control-link-v1.schema.json`. The
`schema_version` is always `"private-control-link-v1"`. Every `message_id` and
`session_id` is the canonical unpadded Base64URL encoding of exactly 16 random
bytes: receivers MUST decode, require exactly 16 bytes, re-encode using
unpadded Base64URL, and compare the result byte-for-byte with the received
string.

All integer fields are JSON integers in the IEEE-754 safe range. Channel and
sender identifiers use their ordinary unsigned 32-bit values. A peer MUST
reject duplicate object member names and any field not permitted by the message
variant.

## Session establishment

The Management Service MUST send `hello` as its first frame within five
seconds of connecting. It contains its `management_service_id` and booleans
that request optional Relay lifecycle events, audit inputs, and diagnostic
snapshots. The Relay MUST verify the transport identity and the
`management_service_id`, then reply with `hello_ack` containing a fresh
`session_id`, its opaque `relay_id`, and the accepted optional inputs.

Before a valid `hello`/`hello_ack` exchange, neither peer may send a command or
notification. The Relay MUST allow no more than one active session for the
same authorized Management Service identity; it MUST close an older session
before accepting a replacement. `ping` and `pong` are optional keepalives and
do not change command or membership state.

A Management Service MUST reconnect after transport loss. Reconnection does
not replay Relay notifications and does not reset Relay admission state.

## Service-admission revocation command

After establishment, the Management Service may send
`revoke_service_admission`. It contains:

- `channel_id`: the affected channel.
- At least one target: `service_id` and/or `grant_id_hash`. A `service_id` is
  the exact canonical Managed Service ID from the admitted grant's `svc` claim.
- `reason`: `acl_removed`, `service_disabled`, or `grant_revoked`.
- `deny_until`: an absolute UTC Unix timestamp in seconds.

`grant_id_hash` is the canonical unpadded Base64URL encoding of
`SHA-256(ASCII(jti))`, where `jti` is the exact string value of the `jti` claim
from the signature-verified Service Admission JWS payload. The hash input is
only those ASCII claim bytes: it MUST NOT contain JSON quotation marks, JSON
escaping, whitespace, a prefix or suffix, or any compact-JWS bytes. The Relay
MUST derive the same value from the verified grant before evaluating a
grant-scoped deny rule. The compact-JWS hash used by the proof-of-possession
flow is a distinct construction and MUST NOT be used as `grant_id_hash`. The
Relay MUST model each accepted command as one channel-bound deny rule with the
following selector scope:

- `service_id` only creates a service-scoped rule. It matches every current and
  future Service Admission Grant for that service in the specified channel.
- `grant_id_hash` only creates a grant-scoped rule. It matches that grant in the
  specified channel.
- Both fields create a conjunctive rule. Both selectors MUST match; the command
  MUST NOT widen into an OR match.

`deny_until` defines a fixed deadline, not a duration relative to any Relay
acceptance or retry time. The Management Service and Relay MUST use sufficiently
synchronized UTC clocks to evaluate it. At command processing, the Relay MUST
return `error` with code `invalid_revocation_deadline` when `deny_until` is more
than 5400 seconds after its current UTC time. If `deny_until` is at or before
the Relay's current UTC time, the Relay MUST NOT install or reactivate a rule;
it MUST return an `ack` with outcome `already_expired`, the supplied
`deny_until`, and zero effect counts.

For a non-expired command, the Relay MUST retain the rule while its current UTC
time is strictly before `deny_until` and remove it at that deadline. A
Management Service revoking a service or grant MUST choose a deadline that
covers every still-valid affected grant, including any permitted receive-only
grace. For a rule containing `grant_id_hash`, `deny_until` MUST NOT be later
than the targeted grant's maximum possible grace deadline. A service-scoped
rule is not tied to any individual grant deadline; it may be extended only by a
new command with a fresh `message_id` and a later `deny_until`.

On accepting a non-expired valid command, the Relay MUST durably commit the
bounded deny rule before replying. The durable state MUST include the selector,
`deny_until`, `message_id`, sufficient command identity to recognize an
identical retry, and the original acknowledgement. The Relay MUST restore every
unexpired rule before accepting Managed Service Admission after a restart. It
MUST reject matching future Managed Service Admission flows, invalidate matching
current service-admitted state, remove matching memberships, stop their media
forwarding, and send `TALK_RELEASE` with `SERVICE_ADMISSION_REVOKED` for every
matching active talker. It MUST return an `ack` only after these effects are
committed. An applied `ack` MUST echo `deny_until`; its
`affected_membership_count` and `talk_release_count` report the effects for the
command and may both be zero when the deny rule was installed before the
targeted service joined.

The Relay SHOULD complete these effects within five seconds of receiving the
command. An unauthorized sender or an unsupported command MUST produce `error`,
not `ack`. A malformed JSON or schema-invalid command is a framing violation
and closes the connection as defined above.

`revoke_service_admission` is idempotent. The Management Service MUST retry an
unacknowledged command after reconnecting with the identical `message_id` and
identical command body. The Relay MUST retain a bounded idempotency entry for
at least ten minutes after sending an `ack`; a duplicate MUST resend the cached
acknowledgement and MUST NOT emit another `TALK_RELEASE`. Reusing a
`message_id` with a different body is a protocol error. Cache eviction or a
Relay restart MUST NOT change an active rule's `deny_until`: an identical retry
for an unexpired durable rule MUST return its original acknowledgement and MUST
NOT emit another `TALK_RELEASE`. After `deny_until`, a retry MUST NOT recreate
or extend the rule and returns `already_expired` if no cached acknowledgement is
available.

The Management Service MUST keep a revocation pending until it receives an
`ack` or the bounded denial period no longer matters. It MUST NOT treat a lost
connection as a successful revocation. The Relay MUST continue to fail closed
for a matching deny rule when the Management Service is unavailable.

Version 1 defines no arbitrary Relay configuration, key-management, channel
credential, or media-control command. Such commands require a future extension
with their own authorization and idempotency rules.

## Relay notifications

A Relay may send `relay_lifecycle_event` only when the Management Service
requested and the Relay accepted lifecycle input in `hello`/`hello_ack`. It may
send `relay_audit_input` only when audit input was similarly negotiated.
Diagnostics use the request/response exchange defined below and are not a
notification stream. A Management Service that advertises `event_delivery`
other than `disabled` SHOULD request lifecycle inputs. One that advertises
`audit_retrieval: true` SHOULD request audit inputs and MUST NOT treat rejected
or disconnected input as complete audit coverage. The allowed event names and
redaction requirements are those in `overview.md#relay-event-integration`.

Private-link notifications have no replay cursor and no persistence
requirement. The Relay MUST use bounded notification queues and MUST NOT let a
slow or unavailable Management Service delay media forwarding. It MAY coalesce
state-change lifecycle events and may drop notifications when the link is
unavailable or a bounded queue is full. The Management Service MUST treat a
link disconnect as a possible notification gap.

A `relay_lifecycle_event` is input to the Management Service, not an external
SSE event. It deliberately has no `event_id`. If the Management Service exposes
it through `GET /events`, the Management Service assigns the external
per-service `event_id` and applies the normal channel/global authorization and
capability rules.

A `relay_audit_input` similarly has no `record_id`. When Audit Retrieval is
enabled, the Management Service may convert received input into the canonical
`AuditRecord`, assign its `record_id`, and retain the record before exposing
it. The Relay is not an audit store, and a private-link outage does not permit
the Management Service to claim that the resulting retained record set is a
complete Relay event history.

## Relay state snapshots

A Management Service that needs canonical current channel and participant state
MAY send `get_relay_state_snapshot` after session establishment. The request
contains only the common `schema_version`, `type`, and `message_id` fields. A
Relay that does not implement this optional read-only command returns `error`
with code `unsupported_message`; it MUST NOT alter Relay state.

For an accepted request, the Relay captures one point-in-time view of every
current channel and responds with one or more `relay_state_snapshot` messages.
Every response has a fresh `message_id`, the request `message_id` in
`in_reply_to`, a common fresh `snapshot_id`, a zero-based `chunk_index`, and a
common `chunk_count` from one through 64. A chunk contains channel entries with
`channel_id` and the current participant `sender_id`/`state` pairs. A channel
may occur in more than one chunk when its participant list crosses a frame
boundary. Each response is independently framed and MUST remain within the
normal 65536-byte Private Control Link frame limit.

The Relay MUST send all chunks for one snapshot before any lifecycle event
whose underlying Relay state changed after the snapshot was captured. A
lifecycle event sent before the chunks may be represented already in the
snapshot. The Management Service MUST collect every index from zero through
`chunk_count - 1` for the same `snapshot_id` and `in_reply_to`, reject duplicate
or inconsistent chunks, and atomically replace its current state projection
only after the complete set is received. It MUST discard an incomplete set on
link loss and request a fresh snapshot after reconnecting. A Management Service
that exposes current-state API resources MUST NOT present a prior connection's
projection as current; it returns the documented unavailable response until the
new complete snapshot is applied. Snapshot messages are read-only, have no
replay cursor, and do not imply durable Relay history.

The Relay MUST bound snapshot work to 64 chunks. If the current state cannot be
encoded within that bound, it MUST return `error` with code `overloaded` rather
than drop or truncate participants. Snapshot collection and delivery MUST NOT
delay media forwarding.

## Relay diagnostics

A Management Service that requests `want_diagnostics: true` in `hello` MAY use
diagnostics only when the Relay returns `diagnostics_accepted: true` in
`hello_ack`. A Relay MUST set `diagnostics_accepted` to `false` when
`want_diagnostics` is `false`, and it MUST set the field to `true` only when it
can serve the diagnostics exchange for the established session. A requester
that has not negotiated diagnostics MUST NOT send `get_relay_diagnostics`; the
Relay MUST return `unsupported_message` without changing Relay state.

The request contains only the common `schema_version`, `type`, and
`message_id` fields. A Management Service MUST send the read-only
`get_relay_diagnostics` request no more frequently than once every ten seconds.
The Relay MUST enforce the same minimum interval per established Private
Control Link session using a monotonic clock. It MUST reply to an earlier
request with `error` code `overloaded`, whose `in_reply_to` identifies that
request, and MUST NOT send a snapshot or alter Relay state. A rate-limited
request does not restart the interval measured from the preceding accepted
diagnostic request. For an accepted request, the Relay replies with one
`relay_diagnostics_snapshot` whose `in_reply_to` equals the request
`message_id`.

A snapshot contains the following common fields:

- `relay_id`: the opaque identifier from `hello_ack`.
- `counter_epoch`: a canonical unpadded Base64URL encoding of 16 random bytes.
  The Relay MUST create it when the Relay process starts and MUST create a new
  value whenever it resets its diagnostic counters.
- `observed_at`: the Relay wall-clock observation time as an RFC 3339 UTC
  timestamp.
- `floor_interrupt`: the redacted Floor Interrupt counter object below.

The pair `(relay_id, counter_epoch)` identifies one continuous counter domain.
Counters are process-local, non-negative, monotonically increasing JSON
integers. For snapshots received in order within one counter domain, every
named counter in a later snapshot MUST be greater than or equal to the same
counter in the preceding snapshot. Counters are not durable and reset after a
Relay restart; a Management Service MUST treat a new `counter_epoch` as a new
time-series domain rather than infer a counter decrease. A Relay MUST reset
all diagnostic counters to zero and create a new `counter_epoch` before any
counter would exceed `9007199254740991`. A counter MUST NOT wrap or decrease
while `counter_epoch` is unchanged.

The `floor_interrupt` object contains:

- `ptt_requests_total`: well-formed `PTT_REQUEST` packets that passed Control
  Authentication and reached Floor Interrupt decision processing.
- `grants_total`: requests for which the Relay sent `TALK_GRANT`, including an
  idempotent grant repair for an already-active requester.
- `denials_total`: authorized requests denied because no eligible grant or
  preemption was available.
- `preemptions_total`: active talkers released with `PREEMPTED`; this is a
  subset of `grants_total`.
- `unauthorized_rejections_total`: authenticated requests rejected because the
  requester lacked a current membership, valid required admission, or interrupt
  permission.

Packets that fail framing, Control Authentication, or replay checks MUST NOT
increment the Floor Interrupt counters. A Relay with Floor Interrupt disabled
MUST report all Floor Interrupt counters as zero. In every snapshot,
`preemptions_total` MUST be less than or equal to `grants_total`. The counters
MUST NOT contain channel IDs, sender IDs, endpoint addresses, actor or service
identifiers, priorities, ticket data, grant data, channel credentials, derived
keys, admission secrets, bearer tokens, raw control credentials, or other
per-request labels. The exhaustive snapshot schema is an enforceable redaction
boundary: a receiver MUST reject a snapshot containing an unrecognized or
sensitive field.

A snapshot is not an audit input and MUST NOT be reconstructed from
`relay_audit_input` messages. The Relay MUST retain no snapshot history and
MUST NOT delay media forwarding to produce or deliver one. A Management Service
may retry a failed read with a new `message_id`; diagnostic reads have no
idempotency cache or side effects. The Management Service is responsible for
polling, retaining, and exporting snapshots through its own metrics system.

## Error handling and limits

An `error` contains the triggering `in_reply_to` message ID when one exists and
one of the schema-defined error codes. `overloaded` means the peer MUST retry
with exponential backoff; it does not imply that a revocation was applied.
`unauthorized`, `identity_mismatch`, `handshake_required`, and
`invalid_revocation_target` MUST NOT be retried without correcting the request.

Implementations MUST rate-limit handshake and malformed-frame failures, bound
all command, notification, and idempotency queues, and log only message type,
reason class, opaque message-ID prefix, and aggregate counts. They MUST NOT log
full service IDs, grant ID hashes, certificates, or message bodies unless an
operator has explicitly configured a protected diagnostic sink.

## Interoperability vector

`../../../test-vectors/management/private-control-link-v1.json` defines framed
message examples, optional-PCL admission lifecycle, canonical identifier
validation, cross-surface Managed Service ID grammar, `jti`-derived
`grant_id_hash` cross-vector validation, revocation idempotency, and Relay
diagnostics cases. Implementations that support this extension MUST validate
the schema, framing limits, target intersection, absolute deny deadlines,
duplicate command behavior, diagnostics negotiation, redaction, and
counter-epoch handling before claiming Private Control Link v1 compatibility.
