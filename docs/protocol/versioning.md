# Versioning and Compatibility

## Protocol and specification versions

The UDP field `version = 1` identifies the deployed wire protocol. This
repository uses semantic tags for specification releases. `v0.1.0-draft`
documents current behavior for the Rust migration.

## Change process

1. Change this repository first.
2. Add deterministic vectors for every new encoding or security rule.
3. Update Relay and at least one client.
4. Run Relay/PWA/Qt/Rust interoperability tests.
5. Tag the specification release and declare that tag in every consumer.

## Compatibility requirements

- Never reinterpret an existing packet type, flag, or payload byte silently.
- Add optional behavior through a new packet type, flag, or explicitly
  versioned payload.
- Preserve raw AES-GCM v2 media packets while relaying.
- Keep legacy decoding only where a documented compatibility mode requires it.
- New clients MUST default to AES-GCM v2 and MUST NOT default to legacy XOR.
