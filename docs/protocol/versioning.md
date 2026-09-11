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
five-byte `CODEC_CONFIG`, FEC v2, and Control Authentication v1 formats
defined in this draft. Supporting FEC v1 or unauthenticated secure controls
in first-release clients is optional, not required.

Once a production release is declared, future incompatible changes MUST follow
the compatibility requirements above and use explicit version negotiation or a
new protocol version.
