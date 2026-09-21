# Management Plane v1

## Scope and default state

Management Plane v1 is an optional, administratively isolated TCP/TLS plane
for organization-operated participant management, recording orchestration,
health monitoring, optional event delivery and audit retrieval, Managed Service
Admission, and an optional private Relay control transport. It is not a
replacement for the Version 1 UDP Relay, the optional Directory UDP protocol,
or client media transport.

Management Plane v1 is disabled by default. A deployment that does not enable
it MUST retain the existing Relay, Directory, and client behavior without
requiring certificates, management credentials, or a management listener.

The Management Plane MUST NOT be implemented by adding privileged operations
to Directory UDP. Directory UDP remains an optional channel metadata and
participant-discovery protocol with its existing authentication and encryption
rules.

## Deployment boundary

A conforming deployment SHOULD run the externally reachable Management API as
a separate `Management Service` process or container. The Management Service
MUST expose HTTPS over TCP only on an administration network, management VLAN,
VPN, dedicated interface, or equivalent firewall-restricted boundary. It MUST
NOT be publicly reachable merely because the normal Relay UDP port is public.

When Private Control Link v1 is enabled, the Relay and Management Service
communicate through a separate authenticated private control link.
`private-control-link-v1.md` defines its dedicated listener, local-socket or
mTLS transport, framing, authentication, revocation command, and bounded
notification behavior:

- On one host, a Unix Domain Socket is RECOMMENDED.
- Across hosts, TCP protected by a distinct internal mTLS deployment is
  RECOMMENDED.
- The private control link MUST use a listener distinct from the external
  Management API port and MUST NOT be reachable from ordinary client or
  Directory networks.

A single-process implementation MAY expose the Management API directly, but
MUST preserve the same listener, authentication, authorization, audit, and
network-separation requirements. A separate process/container is the
recommended deployment because it provides a clear OS and network privilege
boundary.

## Transport and API model

The external Management API uses HTTPS over TCP. It provides:

- REST resources for health, channel/participant state, ACL-backed admission
  grant issuance, and recording-job control.
- Optional SSE event delivery, either live-only or replay-capable.
- Optional audit retrieval.
- JSON request and response bodies encoded as UTF-8.

`docs/extensions/management/openapi-v1.yaml` defines the initial HTTP contract.
`GET /audit-records`, when enabled, is the canonical paginated read API for
retained audit records; it is distinct from the redacted SSE `/events` stream.
`schemas/management/management-event-v1.schema.json` defines the common event
envelope. `schemas/management/audit-retrieval-v1.schema.json` defines the audit
retrieval page. Every enabled `GET /audit-records` response MUST include
`schema_version: "audit-retrieval-v1"`; the OpenAPI `AuditRecordPage` schema
and JSON Schema define the same canonical response object.

### Event and audit capabilities

Event delivery and Audit Retrieval are independently optional. `GET /health`
MUST advertise both capabilities in its `capabilities` object:

- `event_delivery` is `disabled`, `live`, or `replay`.
- `audit_retrieval` is a boolean.

With `event_delivery: "disabled"`, the Management Service MUST return `404 Not
Found` for `GET /events`. With `event_delivery: "live"`, `GET /events` MAY
stream only events emitted after the new live subscription is established. It
MUST NOT claim replay support. A request containing `since`, including an empty
or non-cursor value, MUST return `400 Bad Request` because the parameter is not
supported in live mode. A `Last-Event-ID` header MAY be
present because a standard SSE client reconnects automatically; the Management
Service MUST accept it, MUST NOT validate or use its value as a replay cursor,
and MUST begin delivery only with events emitted after the new subscription is
established. A live-only event stream does not require durable event retention,
and a reconnect may miss events.

Every live SSE event still carries its `event_id` in the SSE `id` field. In
live mode that field does not provide replay or continuity guarantees. Channel
and global authorization filtering may create normal gaps in the visible event
IDs, so a client MUST NOT infer an event-loss gap solely from a discontinuity.

With `event_delivery: "replay"`, the Management Service MUST durably retain
redacted events for its documented retention period before exposing them to an
external subscriber. It MUST implement the cursor and recovery rules below.
A Relay is never required to retain SSE history; the Management Service owns
that durable state.

With `audit_retrieval: false`, the Management Service MUST return `404 Not
Found` for `GET /audit-records` and MUST NOT claim to provide retained audit
records. With `audit_retrieval: true`, it MUST durably retain the audit records
that it exposes for its documented retention period. A deployment without Audit
Retrieval has no protocol requirement to create, retain, or export audit
records.
`test-vectors/management/management-event-v1.json` contains canonical event
instances under its `events` scenario array. Its root `specVersion` is test
metadata, not part of an SSE event. `test-vectors/management/audit-retrieval-v1.json`
likewise keeps query scenario inputs at its root and places the canonical API
response object under `response`.
Management APIs MUST use explicit `/v1/` versioning and MUST NOT return channel
passwords, derived keys, media plaintext, OIDC credentials, or client certificate private keys. The grant-issuance endpoint is the only API response permitted to return a Service Admission Grant; it MUST use `Cache-Control: no-store`, and grants MUST NOT appear in logs, audit records, or event streams.

Management API methods MUST use TLS. HTTP/2 MAY be used, but HTTP/1.1
compatibility is REQUIRED. Every SSE event, when event delivery is enabled,
MUST carry its monotonic `event_id` as the SSE `id` field. Event IDs are opaque
decimal cursors scoped to one Management Service instance. Their decimal
serialization does not imply contiguous values, and clients MUST NOT derive a
next event ID by arithmetic or infer event loss from an ID gap.

The following cursor and recovery rules apply only when `event_delivery` is
`"replay"`. `since` is an optional query parameter for an initial connection
or an explicit historical replay. `Last-Event-ID` is the authoritative resume
cursor for SSE reconnection. Both cursors are exclusive: when either is
selected, the first replay candidate is the first retained event ordered after
that cursor that the caller is authorized to receive. Authorization filtering
may therefore create normal gaps in replayed event IDs. A request with neither
cursor starts a live stream and MUST NOT imply historical replay. Clients SHOULD
omit `since` when reconnecting an established stream.

If both `Last-Event-ID` and `since` are present, the Management Service MUST
use `Last-Event-ID` and MUST ignore `since` without validating its value. A
malformed selected cursor MUST return `400 Bad Request`. A syntactically valid
selected cursor that is unknown, belongs to a
different Management Service instance, or is no longer retained MUST return
`410 Gone`; the service MUST NOT silently start from the newest event. A caller
that receives `410 Gone` MUST discard the expired cursor before opening a new
stream. It MUST then resynchronize according to its authorized scope:

- For every channel where the caller has `viewer` scope, it MUST fetch a fresh
  participant snapshot before opening a cursor-free live stream.
- For a channel visible only through `auditor` scope, a participant snapshot is
  neither required nor authorized. The caller MUST record that the SSE history
  is discontinuous for that channel and, when Audit Retrieval is enabled, MAY
  retrieve retained authorized audit records through `GET /audit-records`; audit
  retrieval does not reconstruct omitted redacted events.
- An auditor-only caller MUST NOT be required to call a viewer-only state
  resource to recover. It records the discontinuity and opens a new stream
  without `Last-Event-ID` or `since`, receiving only subsequently emitted
  authorized events.

This recovery rule preserves the viewer/auditor information boundary while
making the loss of a retained SSE cursor explicit.

## mTLS and service identity

The Management API MUST authenticate callers with mutual TLS by default. Each
organization-operated integration, including a recorder, participant manager,
or automation worker, MUST have a distinct client certificate and private key.
A deployment SHOULD use a private Management CA separate from the certificate
used for public Web UI HTTPS.

The Management Service maps the verified client certificate Subject Alternative
Name or SHA-256 certificate fingerprint to one `service_id` and a channel-scoped
ACL. Certificate sharing between services is prohibited. The mapping and role
assignment are local administration data and are not propagated through the
UDP protocol. `../../configuration/relay-csv.md` defines the canonical CSV
format when a Relay deployment uses file-backed certificate and channel ACLs.

Administrators are responsible for:

1. creating and protecting the Management CA;
2. issuing a Management API server certificate;
3. issuing a separate client certificate for each integration;
4. configuring channel-scoped ACLs and permitted roles;
5. limiting the HTTPS listener to the management network; and
6. rotating or revoking certificates and ACL entries when a service is retired.

The API MUST reject a missing, untrusted, expired, or ACL-unmapped client
certificate. Bearer tokens, OIDC, and other authentication mechanisms MAY be
specified by a future Management API version, but MUST NOT weaken the mTLS
requirement in Management Plane v1.

## Managed Service ID grammar

A Managed Service ID is a case-sensitive ASCII identifier matching the
following grammar:

```text
^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$
```

It is one through 128 characters long, begins with an ASCII letter or digit,
and thereafter contains only ASCII letters, digits, `.`, `_`, or `-`. The
`service_id` columns in `management-services.csv` and
`management-channel-acl.csv`, the Managed Service Admission `svc` claim, and
the Private Control Link `revoke_service_admission.service_id` and lifecycle
event `service_id` fields use this same Managed Service ID namespace. Whenever
two of those fields identify the same service, their values MUST be exactly
equal. Comparisons are byte-for-byte and case-sensitive.

Private Control Link `management_service_id` identifies the Management Service
control peer rather than an admitted managed service. It uses this same lexical
grammar for operational consistency, but is a separate namespace and is not
required to equal a Managed Service ID used by an admission grant or revocation
target.

## Roles and channel ACLs

Authorization is evaluated for every request using the authenticated
`service_id`, requested operation, and that operation's effective
authorization scope. Roles are channel-scoped unless an administrator explicitly
configures a global permission; an implementation MUST NOT infer all-channel or
global access from possession of a certificate or channel-scoped role.

1. A channel-scoped operation, including participant lookup, grant issuance,
   and recording-job creation, MUST authorize `service_id`, target `channel_id`,
   and operation.
2. An operation on an existing channel-owned resource, including recording-job
   stop, MUST resolve that resource's authoritative stored `channel_id` before
   authorization. A caller-supplied channel ID MUST NOT override the stored
   scope.
3. A multi-channel list operation MUST filter every returned resource to channels
   for which the authenticated service has the required channel-scoped operation.
   A service with no matching channel scope MUST receive `403`, not an unfiltered
   or implicitly global result.
4. A multi-channel event stream MUST filter each channel-scoped event with a
   non-null `channel_id` to channels for which the authenticated service has the
   required event role. A caller with neither a matching event channel scope nor
   an explicit global event permission MUST receive `403` for the stream.
5. A global operation or global event has no channel ID and MUST require an
   explicitly configured global permission. A channel-scoped role MUST NOT imply
   that permission.

| Role | Permitted operations |
|---|---|
| `viewer` | Read channel state, participant state, and redacted events for allowed channels. |
| `recorder` | `viewer` operations plus recording-job lifecycle and Managed Service Admission with receive-only permissions. |
| `operator` | `viewer` operations plus explicitly configured channel operations. |
| `auditor` | Read redacted events for explicitly authorized channels and, when Audit Retrieval is enabled, retained audit records; unscoped records require an explicit global audit permission. |
| `admin` | Manage Management Plane ACLs and signing-key configuration. |

For the initial HTTP contract, `GET /channels` filters its channel summaries
to the caller's `viewer` scope. `GET /events` filters every channel-scoped
event to the caller's `viewer` or `auditor` scope, while global event delivery
uses the explicit event-type permissions defined in
[Global event authorization](#global-event-authorization). `GET /health`
requires the explicit global `health.read` permission. `GET /audit-records`
follows the additional `auditor` and global-audit rules below. The
`POST /recording-jobs/{job_id}/stop` endpoint resolves the stored job channel
before applying the recorder or operator permission; it never trusts an
inferred or client-supplied replacement channel scope.

The initial `recorder` role MUST NOT grant PTT, media transmission, ordinary
profile changes, or Relay policy changes. A future automation extension may permit talk only through an explicit `talk`
ACL and Managed Service Admission permission; Floor Interrupt additionally
requires an explicit `interrupt` ACL and Relay-assigned priority. Neither
permission is implied by `operator` or `recorder`.

## Managed Service Admission

Managed Service Admission v1 is a separate Relay membership admission path for
non-interactive organization-operated services. It is intended for 24-hour
recording and monitoring workers that cannot use an interactive OIDC browser
flow. It is not anonymous access and it does not disclose or replace a channel
credential.

A Management Service authenticated service may request a short-lived,
Ed25519-signed Service Admission Grant. The service presents that grant and a
proof of possession over the existing authenticated UDP control path. A Relay
that validates the grant admits the service according to its channel-scoped
permissions. The complete protocol is in `service-admission.md`.

Private Control Link v1 is optional for grant issuance and natural expiry. A
Managed Service Admission deployment without it can issue and verify grants,
but cannot perform standards-defined prompt Relay-side administrative
revocation of a grant issued before the administrative change, whether or not
it has previously been presented to or accepted by the Relay. A deployment that
requires that capability MUST enable Private Control Link v1; its authenticated
`revoke_service_admission` command is defined in
`private-control-link-v1.md`.

When Identity Admission is `required`, a valid Managed Service Admission MAY
satisfy the admission prerequisite only when the Relay's managed-service policy
is enabled. Ordinary clients remain subject to Identity Admission; a managed
service grant never makes OIDC optional for other endpoints.

Managed Service Admission bypasses only the interactive OIDC admission path.
It MUST NOT bypass the channel credential, AES-GCM v2 media authentication,
Control Authentication v1, MTU limits, membership lease, or floor-control
policy.

## Relay event integration

A Relay MAY emit only minimally necessary, redacted lifecycle events and audit
inputs over Private Control Link v1. A deployment that enables event delivery
or Audit Retrieval MUST make the required lifecycle input available to its
Management Service without making the Relay retain event or audit history. The
initial lifecycle event set is:

- `participant_joined`
- `participant_left`
- `talk_started`
- `talk_ended`
- `relay_health_changed`
- `recording_state_changed`
- `service_admission_issued`
- `service_admission_revoked`

A Private Control Link lifecycle input includes an RFC 3339 UTC timestamp, an
event type, and a channel ID or explicit `null` for a global event. It MAY
include a sender ID, service ID, reason code, or recording job ID. It has no
external SSE `event_id`; the Management Service assigns that per-service
cursor only when it publishes the input through `GET /events`. Audit inputs
likewise have no `record_id`; the Management Service assigns it only when it
creates a canonical retained `AuditRecord`. Private-link inputs and resulting
Management events MUST NOT include IP addresses, UDP ports, media payloads,
channel passwords, derived keys, OIDC material, admission grants, certificate
contents, or private keys. Private-link notification delivery is bounded and
non-persistent; a Management Service MUST treat a control-link outage as a
possible input gap and MUST NOT represent a recovered stream as complete
history.

### Global event authorization

A channel-scoped event MUST carry a non-null `channel_id`; delivery requires the
caller's `viewer` or `auditor` scope for that exact channel and uses the normal
redacted event representation. A global event MUST carry `channel_id: null`.
It is never authorized merely because the caller has a role for one or more
channels.

Every global event type MUST define an explicit global permission before it is
emitted or delivered. A global event with no specified permission mapping MUST
NOT be emitted or delivered. Version 1 defines this mapping:

| Global event type | Required global permission |
|---|---|
| `relay_health_changed` | `health.read` |

`relay_health_changed` is always a global event. It MUST carry
`channel_id: null` and a `state` of `healthy`, `degraded`, or `unhealthy`.
It has the same authorization boundary as `GET /health`: a caller without
explicit `health.read` MUST NOT receive it, including through an otherwise
permitted `GET /events` stream. Conversely, `health.read` authorizes delivery
only of this mapped global event; it grants no channel-scoped event, participant,
or channel-state access.

When event delivery is enabled, a caller MAY open `GET /events` when it has
at least one authorized channel-scoped event role or an explicit global event
permission. On every delivery, the Management Service MUST independently apply
the channel scope for a non-null `channel_id` or the event-type-specific global
permission for a null `channel_id`. This rule applies equally to `viewer` and
`auditor` callers.

Implementations MUST bound private-link and subscriber queues and MAY coalesce
state-change events under backpressure. They MUST NOT let an unavailable
Management Service or subscriber delay Relay media forwarding.

## Revocation and availability

Prompt Relay-side administrative revocation is an optional capability provided
by Private Control Link v1. In a Managed Service Admission deployment without
Private Control Link, an ACL removal, service disablement, or grant revocation
MUST stop future issuance of affected grants but does not immediately alter a
grant issued before the change, whether or not it has previously been presented
to or accepted by the Relay. A later presentation of that grant remains
eligible for Relay acceptance until its normal expiry or another Relay-local
invalidation condition applies. The Management Service MUST NOT represent the
administrative action as a Relay-applied revocation.

A deployment that requires prompt revocation of existing Service Admission
state MUST enable Private Control Link v1. In that profile, a Management
Service MUST send `revoke_service_admission` when an ACL is removed, a service
is disabled, or a grant is revoked. The Relay MUST stop forwarding media for a
revoked service, remove its membership promptly, and use
`SERVICE_ADMISSION_REVOKED` only when it applies that command. The command is
authenticated, bounded by its fixed `deny_until` deadline, durable across Relay
restart, and idempotent; a target propagation time of five seconds is
RECOMMENDED.

Service Admission Grants are intentionally short-lived. A service renews them
through its mTLS-authenticated Management API session before expiry. To support
long-running receive-only recording during a temporary Management Service
outage, a Relay MAY preserve an uninterrupted existing recorder membership
until `expires_at + grace_seconds`; `grace_seconds` is grant-bounded and MUST
NOT exceed 1800 seconds. During this grace period the Relay MUST NOT accept a
new JOIN, changed source endpoint, or renewed privilege from the expired grant.
A Relay restart or membership expiry ends the grace period. New Managed Service
Admission MUST fail closed when the Management Service cannot issue a valid
grant.

A 24-hour recorder therefore uses renewable grants and normal authenticated
KEEPALIVE traffic. It MUST treat Relay restart, grant rejection, membership
loss, and recording-worker restart as recoverable conditions and reconnect
without using an unbounded local audio queue.

## Recording boundary

The Relay forwards encrypted media and MUST NOT decrypt it for recording.
A Recorder Worker joins as a receive-only Relay participant, validates media,
and decrypts/decodes it using separately provisioned channel credentials. The
Management API controls recording jobs and reports their state; it MUST NOT
place channel credentials or media keys in ordinary API responses. See
`recording-integration.md`.

## Optional audit retrieval

When `audit_retrieval` is `true`, `GET /audit-records` is a canonical,
read-only Management Plane v1 resource. It MUST require the `auditor`
operation in the authenticated mTLS ACL. For a channel-scoped record, the
service MUST also be authorized for that channel. For a record with
`channel_id = null`, the service MUST have an explicitly configured global
audit permission; a certificate MUST NOT gain global audit access implicitly.

The Management Service MUST durably retain redacted audit records for its
documented deployment retention period before exposing them through the v1 API.
Records are append-only through the v1 API: no endpoint may modify or delete
them. Each returned record MUST
contain an opaque `record_id`, RFC 3339 UTC `timestamp`, `actor_type`,
privacy-preserving `actor_id`, nullable `channel_id`, `action`, and `result`.
`actor_type` is `identity`, `service`, or `relay`. An `identity` actor uses the
stable admitted identity identifier; a `service` actor uses the authenticated
Management Service `service_id`; and a `relay` actor uses a deployment-local,
opaque Relay identifier. An audit record MUST NOT contain channel passwords,
derived keys, admission grants, certificate contents, source addresses, media
payloads, unredacted request bodies, or raw OIDC claims beyond the configured
privacy-preserving identity identifier.

`action: "floor_interrupt"` records MUST include `floor_interrupt` details:
the requester's effective priority, nullable replaced sender ID, and nullable
replaced effective priority. Both replaced fields MUST be non-null for a
preemption and MUST be null when the request did not actually preempt an
active talker.

`recording_create`, `recording_start`, `recording_stop`, `recording_failure`,
`recording_grant_issued`, `recording_grant_renewed`, and
`recording_grant_revoked` records MUST include `recording_job` details. Those
details contain the opaque `job_id` and `recorder_service_id` for the Recorder
Worker assigned to that job. `actor_type` and `actor_id` identify the principal
that caused the recorded operation; they MUST NOT be treated as the Recorder
Worker identity unless they actually identify that worker.
This canonical record format applies when Audit Retrieval is enabled. The
Management Service, rather than the Relay, retains and exposes the records
through `GET /audit-records` subject to the caller's audit ACL. A Relay that
does not provide a Management Service is not required to maintain an audit
sink.

The endpoint returns records newest first, using `record_id` as a stable
tie-breaker. It accepts optional `channel_id`, inclusive `since`, exclusive
`until`, `action`, `result`, `limit`, and opaque `cursor` query parameters.
`limit` defaults to 100 and MUST NOT exceed 1000. A cursor MUST be bound to
the authenticated service and query filters. A changed filter or invalid time
range MUST return `400`; a cursor outside the retained window MUST return
`410 Gone`; an unauthorized requested channel MUST return `403`.

`/events` remains an SSE lifecycle feed and MUST NOT be used as an audit
record substitute. When enabled, Audit Retrieval is pull-based and paginated so
it can safely support long-lived organization-operated audit consumers.

## Audit and non-goals

When `audit_retrieval` is `true`, grant issuance, grant renewal, revocation,
recording start/stop, ACL changes, and administrative requests MUST produce an
auditable, redacted record that identifies the authenticated actor, requested
channel, action, result, and timestamp. Management-originated records use
`actor_type: "service"` and the authenticated `service_id` as `actor_id`.
When `audit_retrieval` is `false`, the protocol does not require a Relay or
Management Service to create, retain, or export an audit record; deployments
MAY still maintain local logs under their own policy.

Management Plane v1 does not define media upload, media proxying, centralized
key escrow, general user login, browser client replacement, or a Directory UDP
management extension. Those functions require separate versioned proposals.

## Required interoperability cases

1. Disabled Management Plane leaves existing UDP Relay and Directory behavior
   unchanged.
2. An untrusted, expired, or ACL-unmapped mTLS client cannot access the API.
3. A channel-scoped role does not authorize `GET /health` unless the service
   also has explicit global `health.read` permission.
4. A caller with channel-scoped `viewer` or `auditor` access but no
   `health.read` does not receive a global `relay_health_changed` SSE event.
5. A caller with explicit `health.read` receives `relay_health_changed` with
   `channel_id: null`, but receives no channel-scoped event without the matching
   channel role.
6. A `recorder` ACL can issue only a receive-only grant for an allowed channel.
7. A service grant cannot join a different channel, use another sender ID, or
   be used by a different proof-of-possession key.
8. A valid Managed Service Admission can satisfy a required identity policy
   only for that service endpoint while managed-service admission is enabled.
9. Without Private Control Link, an administrative change denies future affected
   grants but does not claim prompt Relay-side revocation of an already-issued
   grant.
10. With Private Control Link enabled for prompt revocation, revocation removes
    the affected membership without affecting unrelated channel members.
11. A Management API outage denies new grants while an uninterrupted existing
    receive-only membership follows the bounded grace rule.
12. API responses, SSE events, audit records, and normal Relay logs contain no
    channel password, derived key, admission grant, certificate private key,
    or media payload.
13. When `audit_retrieval` is `true`, an `auditor` retrieves only records for
    explicitly authorized channels; a request for another channel is rejected.
14. When `event_delivery` is `replay`, an SSE cursor outside the retained
    window returns `410 Gone` rather than silently skipping history.
15. With `event_delivery` set to `live`, `GET /events` accepts a cursor-free
    connection and a standard SSE reconnect carrying `Last-Event-ID`, ignores
    that header, and rejects `since` with `400 Bad Request`.
16. With `event_delivery` set to `disabled`, `GET /events` returns `404 Not
    Found`.
17. With `audit_retrieval` set to `false`, `GET /audit-records` returns `404
    Not Found` and no audit retention is required.
18. When `audit_retrieval` is `true`, audit pagination is stable, and an audit
    cursor outside the retained window returns `410 Gone` rather than silently
    skipping history.
