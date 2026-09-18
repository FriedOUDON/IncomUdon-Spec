# Recording Integration v1

## Scope

Recording Integration v1 defines how an organization-operated recorder uses
Management Plane v1 without turning the Relay into a media decryptor or a
recording-data proxy. It is designed for continuous, receive-only recording of
an allowed channel.

## Components

- `Management Service`: exposes the mTLS Management API, applies ACLs, issues
  Managed Service Admission Grants, controls jobs, and optionally retains audit
  records.
- `Recorder Worker`: an ordinary receive-only Relay participant operated by the
  organization. It validates, decrypts, decodes, timestamps, and stores media.
- `Relay`: continues to forward authorized encrypted media; it does not decode
  or persist media for this integration.

The Recorder Worker MUST be a separate service identity from the Management
Service. It SHOULD use a dedicated OS account/container, certificate, storage
location, and channel ACL.

## Start and stop lifecycle

1. An mTLS-authenticated caller with `recorder` permission requests a
   recording job for one allowed channel.
2. The Management Service creates a job with an opaque `job_id`. When Audit
   Retrieval is enabled, the corresponding action is auditable.
3. The Recorder Worker obtains a receive-only Service Admission Grant and joins
   the channel using the normal authenticated UDP protocol.
4. The Recorder Worker emits `recording_state_changed` events such as
   `starting`, `recording`, `degraded`, `stopping`, `stopped`, or `failed`.
5. On stop, revocation, grant failure, or Relay membership loss, the worker
   closes the current recording segment and reports the result.

A Management API request MUST NOT cause Relay media to be sent through the
Management HTTPS connection. Media stays on the existing Relay UDP path.

## Channel credentials and key material

The Recorder Worker needs the same local channel credential configuration as a
normal receiver to authenticate and decrypt protected media. Management Plane
v1 does not define channel-secret distribution.

A deployment MAY inject recorder credentials through an operating-system secret
store, container secret, hardware-backed key store, or separate organization
vault. It MUST NOT return channel passwords, derived keys, AES-GCM keys, or
Control Authentication keys from the ordinary Management API or SSE event
stream. Grant issuance and channel-secret provisioning are deliberately
separate controls.

## Receive-only constraints

A recorder grant MUST have `role = recorder` and `perm = 1`. The Relay MUST
reject PTT, AUDIO, and FEC transmitted by that endpoint. The Recorder Worker
MUST NOT request PTT as a liveness mechanism; it uses JOIN/KEEPALIVE and grant
renewal instead.

The worker SHOULD keep per-sender codec, FEC, AES-GCM v2 replay, jitter, and
playout/decode state independent, as required for ordinary multi-talker
receivers. Recording timestamps SHOULD record the local capture/segment time
and relevant sender/channel metadata without exposing credentials.

## Availability and backpressure

Recording is an external consumer. Its storage, encoder, or uploader backlogs
MUST NOT delay the Relay forwarding loop. A Recorder Worker MUST use bounded
queues. On persistent storage failure it SHOULD close the segment, report
`degraded` or `failed`, and preserve real-time Relay participation where doing
so does not exhaust local resources.

For uninterrupted operation, the worker renews its short-lived Service
Admission Grant before expiry and uses the optional bounded grace described in
`service-admission.md` only when the deployment permits it. It MUST reconnect
after Relay restart, membership expiration, source endpoint change, or
revocation; it MUST NOT attempt to reuse an expired grant for a new JOIN.

## Audit and privacy

When the Management Service advertises `audit_retrieval: true`, it MUST audit
job creation, start, stop, failure, grant issuance, renewal, and revocation
using the canonical Management Plane v1 `AuditRecord`. The corresponding
actions are `recording_create`, `recording_start`, `recording_stop`,
`recording_failure`, `recording_grant_issued`, `recording_grant_renewed`, and
`recording_grant_revoked`. Each such record MUST contain `recording_job` details
with the opaque `job_id` and the assigned Recorder Worker
`recorder_service_id`, in addition to channel ID, timestamp, actor, and result.
`actor_type` and `actor_id` identify the principal that caused the operation;
the separate `recorder_service_id` identifies the Worker associated with the
job even when it did not initiate that operation. When Audit Retrieval is not
enabled, the protocol does not require recording audit records. Events and
ordinary logs MUST NOT include media content, channel credentials, keys, full
grants, or certificate private keys.

Retention, consent, export format, access to recorded media, legal hold, and
regional privacy requirements are deployment policy. They are intentionally
outside the UDP and Management Plane wire specifications.
