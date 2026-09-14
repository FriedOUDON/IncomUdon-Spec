# Versioning and Compatibility

## Protocol and specification versions

The UDP field `version = 1` identifies the deployed wire protocol. This
repository uses semantic tags for specification releases. `v0.1.0-draft`
documents current behavior and the first coordinated Rust migration target.

## Change process

1. Change this repository first.
2. Add deterministic vectors for every new encoding or security rule.
3. Update Relay and all supported clients.
4. Run Relay/PWA/Qt/Rust interoperability tests.
5. Tag the specification release and declare that tag in every consumer.

## Compatibility requirements

- Never reinterpret an existing packet type, flag, or payload byte silently
  after the first production release.
- Add optional behavior through a new packet type, flag, or explicitly
  versioned payload.
- Preserve raw AES-GCM v2 media packets while relaying.
- Keep legacy decoding only where a documented compatibility mode requires it.
- New clients MUST default to AES-GCM v2 and MUST NOT default to legacy XOR.

## First-release coordinated migration

The PWA, Qt, and Rust clients covered by `v0.1.0-draft` have not yet reached a
formal production release. They therefore MUST migrate together to the
19-byte `CODEC_CONFIG` with a media nonce base, five-byte `TALK_RELEASE`
with release reason, FEC v2, Control Authentication v1, optional Identity
Admission v1, the 1200-byte UDP datagram limit, the AES-GCM v2 36-byte media
header with an explicit 96-bit session base and 32-bit anti-replay counter,
and the `argon2id-v1`/`raw-secret-v1` channel credential KDF defined in this
draft. First-release clients MUST NOT transmit or require support for the
predecessor draft AES-GCM v2 28-byte media header with its zero-prefixed 64-bit
nonce, the predecessor 32-byte direct-nonce header, old `CODEC_CONFIG` payload
forms, or the removed `sha256:` and implicit bare-64-hex password normalization
forms. Supporting FEC v1 or unauthenticated secure controls in first-release
clients is optional, not required; AES-GCM v2 itself always requires Control
Authentication v1.

Once a production release is declared, future incompatible changes MUST follow
the compatibility requirements above and use explicit version negotiation or a
new protocol version.
