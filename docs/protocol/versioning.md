# Versioning and Compatibility

## Version namespaces

IncomUdon uses independent version namespaces. Implementations MUST NOT treat
one namespace as an implicit value for another.

| Namespace | Meaning | Example |
|---|---|---|
| UDP envelope | On-wire protocol format | `version = 1` |
| Specification snapshot | Complete documentation/schema/vector revision | `unreleased` or `v0.7.0-draft` |
| Extension or scheme | Individually versioned optional protocol feature | `control-auth-v1` |
| Development state | A non-tagged work-in-progress snapshot | `unreleased` |

## Specification snapshot source

The repository-root `SPEC_VERSION` file is the single source of truth for the
specification snapshot represented by the current checkout. Its content MUST be
exactly one non-empty line and MUST be either `unreleased` or a semantic Git tag
name such as `v0.7.0-draft`.

Every JSON file beneath `test-vectors/` MUST contain a top-level `specVersion`
string equal to `SPEC_VERSION`. A vector's `specVersion` describes the complete
specification snapshot to which that file currently belongs; it does not record
when the vector or feature was first introduced.

An optional `introducedIn` field MAY record introduction history only after the
referenced release tag exists. It MUST NOT be used as a substitute for the
current `specVersion`.

## Development change process

1. Keep `SPEC_VERSION` and every test-vector `specVersion` set to `unreleased`
   on normal development commits.
2. Change this repository before implementation code.
3. Add or update deterministic vectors for every new encoding or security rule.
4. Run the specification checks and Relay/PWA/Qt/Rust interoperability tests.
5. Update supported consumers to declare the exact tagged specification release
   only after that release has been created.

## Release procedure

1. Select a new semantic specification tag, such as `v0.7.0-draft`.
2. Complete normative documentation, schemas, vectors, and implementation
   interoperability validation.
3. In the release commit, set `SPEC_VERSION` and every vector `specVersion` to
   the selected tag.
4. Run `tools/check_spec_version.py --expected-version TAG` and all applicable
   validation tests.
5. Create an annotated Git tag with the same name on that exact commit and push
   the commit and tag.
6. Start the next development cycle in a follow-up commit by restoring
   `SPEC_VERSION` and all vector `specVersion` values to `unreleased`.

A GitHub Actions tag build MUST reject a tag whose name differs from
`SPEC_VERSION`. Tagged release compatibility MUST always be evaluated from the
schemas and vectors contained in that exact tag, never from a later `main`
checkout.

## Compatibility requirements

- Never reinterpret an existing packet type, flag, or payload byte silently
  after the first production release.
- Add optional behavior through a new packet type, flag, or explicitly
  versioned payload.
- Preserve raw AES-GCM v2 media packets while relaying.
- Keep legacy decoding only where a documented compatibility mode requires it.
- New clients MUST default to AES-GCM v2 and MUST NOT default to legacy XOR.

## First-release coordinated migration

The PWA, Qt, and Rust clients covered by the current coordinated draft have not
yet reached a formal production release. They therefore MUST migrate together
to the 19-byte `CODEC_CONFIG` with a media nonce base, five-byte
`TALK_RELEASE` with release reason, FEC v2, Control Authentication v1, optional
Identity Admission v1, the 1200-byte UDP datagram limit, the AES-GCM v2
36-byte media header with an explicit 96-bit session base and 32-bit
anti-replay counter, and the `argon2id-v1`/`raw-secret-v1` channel credential
KDF defined in this draft. First-release clients MUST NOT transmit or require
support for the predecessor draft AES-GCM v2 28-byte media header with its
zero-prefixed 64-bit nonce, the predecessor 32-byte direct-nonce header, old
`CODEC_CONFIG` payload forms, or the removed `sha256:` and implicit bare-64-hex
password normalization forms. Supporting FEC v1 or unauthenticated secure
controls in first-release clients is optional, not required; AES-GCM v2 itself
always requires Control Authentication v1.

Once a production release is declared, future incompatible changes MUST follow
the compatibility requirements above and use explicit version negotiation or a
new protocol version.
