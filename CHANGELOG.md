# Changelog

## Unreleased

- Clarifies that Directory UDP v2 HKDF and AAD use decoded 16-byte
  `epoch_raw`, not the base64url JSON text.

- Adds canonical paginated `GET /audit-records` retrieval for redacted
  Management Plane audit records.

- Defines `PREEMPTED` `TALK_RELEASE` as immediate discard, rather than drain,
  for queued media and FEC state.

- Introduces `SPEC_VERSION` as the single source of the current specification
  snapshot, normalizes all vector `specVersion` values, and adds CI validation
  for development snapshots and tagged releases.

- Adds the registered Opus `24000` bps mode, aligns the 24 kbps FEC
  recommendation, and adds a canonical `CODEC_CONFIG` packet vector.

- Limits Directory UDP v1 and v2 JSON-number `sequence` and `expiresAt`
  values to positive JavaScript-safe integers, preserving exact cross-language
  `U64BE` nonce and AAD encoding without lossless JSON extensions.

- Clarifies Multi-Talker Mixing receiver conformance: 16 concurrent sources
  define the full-mix-capable profile, while resource-constrained receivers
  may enforce a lower deterministic local limit with visible diagnostics.

- Generalizes Server-Managed PTT Timeout `grant_time` to every newly
  created `TALK_GRANT`, including Floor Interrupt requests that use an
  available slot or preempt an active talker.

- Separates Control Authentication `control_key_id` terminology from AES-GCM
  v2 `media_key_id` terminology. Clarifies that authenticated
  `CODEC_CONFIG` establishes media replay state with the mode-selected Media
  Key ID, never its Control Key ID.

- Clarifies that Managed Service Admission receive-only grace remains a
  bounded existing-membership exception when Identity Admission is `required`,
  without authorizing JOIN, PTT, endpoint changes, or ordinary endpoint access.

- Defines Managed Service Admission v1 natural expiry: effective membership
  deadlines, receive-only grace limits, `SERVICE_ADMISSION_EXPIRED` release
  reason `0x08`, renewal races, and deterministic expiry cases.

- Defines FEC v2 final-block termination ordering: final AUDIO and P/Q parity
  are sent before `PTT_OFF`; a Relay releases immediately on `PTT_OFF` and
  treats reordered final parity as ordinary loss. Adds ordering and reorder
  fault-injection cases.

- Clarifies Control Authentication v1 Relay key provisioning: Relay CSV
  keys are the credential-derived `control_key` values used by standard clients,
  not independently provisioned random secrets. Documents that `key_id` alone
  does not rotate key material and defines coordinated credential rotation.

- Fixes Floor Interrupt v1 canonical vectors to carry the required 28-byte
  Control Authentication header and HMAC tag for both `PTT_REQUEST` and the
  Relay-generated `PREEMPTED` `TALK_RELEASE`; adds authentication rejection
  cases.

- Fixes Control Authentication v1 client nonce-counter allocation: all
  authenticated pre-JOIN exchanges consume the next counter, JOIN no longer
  assumes counter one after admission, and Relays retain a provisional replay
  window through JOIN. Adds Identity and Managed Service Admission counter
  sequences and replay-window interoperability requirements.

- Expands the coordinated-release `CODEC_CONFIG` codec mode/bitrate field to
  a 32-bit big-endian bps value. The authenticated configuration payload is
  now 19 bytes, so Opus 96 kbps and 128 kbps are represented without
  truncation; packet vectors cover 128 kbps explicitly.

- Defines Relay Operational CSV Configuration v1: UTF-8/RFC 4180 parsing,
  Directory channel/speaker metadata, Control Authentication key rows, and
  optional Management Plane service and channel ACL inputs with atomic reload,
  revocation, redaction, and parser fixtures.

- Defines optional Floor Interrupt v1: an Admission-required, Control-
  Authentication-protected `PTT_REQUEST` path for Relay-authorized higher-
  priority preemption, bounded per-talker replacement, `PREEMPTED` release,
  immediate old-audio cleanup, and deterministic authorization/packet vectors.
- Defines optional Management Plane v1: an administratively isolated HTTPS/mTLS
  API, channel-scoped roles and ACLs, redacted SSE event delivery, private
  Relay integration, and Recorder Worker orchestration without media/key proxying.
- Defines Managed Service Admission v1: mTLS-gated, Ed25519-signed,
  proof-of-possession Relay grants for non-interactive services, bounded
  renewable/grace behavior, revocation, an API contract, schemas, and a
  deterministic admission vector. Existing Directory UDP behavior is unchanged.
- Defines Multi-Talker Mixing: independent per-talker decoding and playout,
  16-talker Relay/receiver interoperability limit, common-rate mixing,
  20 ms gain ramps, final peak protection, mixer diagnostics, and canonical
  concurrent-source test cases.
- Promotes channel-password-derived Directory UDP v2 as the primary optional
  directory mode. Defines per-channel directional AES-GCM keys, authenticated
  channel scoping, schema, and a deterministic vector; retains shared-PSK
  Directory v1 only as an explicit compatibility/administrative mode.
- Defines optional Identity Admission v1: OIDC Access Service integration,
  Ed25519 proof-of-possession Relay Admission Tickets, per-channel listen/talk
  permissions, and default-off Relay policy modes.

- Defines AES-GCM v2 media anti-replay protection: an authenticated
  `CODEC_CONFIG` announces a CSPRNG 96-bit media-session base; every AUDIO/FEC
  packet carries that base plus a shared 32-bit counter; and receivers enforce
  a 64-counter post-authentication replay window per sender/session/key.
  AES-GCM v2 now requires Control Authentication v1, uses a 36-byte AAD header,
  and rejects media from an unannounced session.
- Defines an MTU-safe 1200-byte UDP datagram limit, a 1131-byte transmit media
  frame limit, FEC v2 size budgets, oversize Relay-drop behavior, and
  diagnostics for local MTU/oversize failures.
- Replaces the fast SHA-256 channel-password normalization with `argon2id-v1`
  for passphrases, adds the explicit `raw-secret-v1` 256-bit secret form, and
  removes the draft-era `sha256:` and implicit bare-64-hex inputs.

- Defines Server-Managed PTT Timeout: monotonic Relay-enforced talk leases,
  five-byte `TALK_RELEASE` reason signaling, deadline handling, client stop
  behavior, and required timeout interoperability cases.

- Defines Diagnostics and Debug Metrics v1: redacted per-session, transmit,
  per-talker receive/playout, FEC, authentication, and QoS metrics.
- Defines Control Authentication v1: password-key separation, HMAC control
  tags, Relay key provisioning, cookie-authenticated JOIN, and replay
  protection for first-release secure clients.
- Adds a real-time playout specification with an 80 ms target delay,
  120 ms hard delay bound, fixed frame deadlines, and stale-audio
  resynchronization behavior.
- Defines the first-release coordinated migration to FEC v2, including
  variable-size codec-frame parity through length metadata and zero padding.
- Defines Opus in-band FEC as an Opus profile mode and specifies its sender
  advertisement and one-frame receive recovery behavior.
- Defines five-byte `CODEC_CONFIG` FEC option signaling.
- Specifies that external parity FEC and Opus in-band FEC may be combined only
  by explicit user choice, with the combination disabled by default.
- Adds bitrate-specific FEC operation recommendations and sets the Opus
  in-band FEC expected packet-loss default to 10 percent with normal UI
  choices of 0, 3, 5, 10, and 15 percent.
- Defines `MAX_MEDIA_FRAME_BYTES` as 4096 bytes for both codec frames and
  FEC v2 parity data.
- Requires P/Q parity for short final FEC blocks and adds common FEC
  fault-injection requirements and FEC v2 deterministic vectors.

## v0.1.0-draft - 2026-09-01

- Documents the observed Version 1 UDP envelope and packet registry.
- Documents PCM, Codec2, Opus, FEC, floor-control, and Ping/Pong behavior.
- Documents AES-GCM v2 key derivation, nonce construction, and header AAD.
- Documents the optional PSK-protected directory UDP protocol.
- Adds deterministic packet, crypto, FEC, and directory test vectors.

This is a draft release. It is suitable as the compatibility target for the
first Rust protocol implementation, but it is not a promise that future
protocol revisions will be backward compatible.
