# Changelog

## Unreleased

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

- Defines an MTU-safe 1200-byte UDP datagram limit, a 1135-byte transmit media
  frame limit, FEC v2 size budgets, oversize Relay-drop behavior, and
  diagnostics for local MTU/oversize failures.
- Revises AES-GCM v2 media nonces to a direct CSPRNG-generated 96-bit
  sender/session base plus monotonic allocation, increases its authenticated
  media header to 32 bytes, and adds the coordinated first-release migration
  requirement.
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
