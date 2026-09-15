# IncomUdon Specification

**Wire protocol version:** `1`
**Specification snapshot:** [`SPEC_VERSION`](SPEC_VERSION) (currently `unreleased`)
**Latest tagged specification:** `v0.6.0-draft`

This repository is the canonical interoperability specification for the
IncomUdon Relay, PWA client, Qt native client, and future Rust native client.
It describes Version 1 behavior and provides deterministic vectors for new
implementations.

## Normative language

The terms MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as
requirements for compatible implementations.

## Contents

- `docs/protocol/overview.md`: scope and transport lifecycle.
- `docs/protocol/wire-format.md`: Version 1 packet envelope.
- `docs/protocol/control-packets.md`: control payload layouts and relay rules.
- `docs/protocol/membership-lease.md`: Relay-advertised membership lease and keepalive cadence.
- `docs/protocol/ptt-timeout.md`: Relay-enforced maximum talk duration and release behavior.
- `docs/protocol/floor-interrupt.md`: admission-required authorized floor preemption.
- `docs/protocol/audio-codecs.md`: media payloads and codec negotiation.
- `docs/protocol/playout.md`: real-time playout, jitter buffering, and resynchronization.
- `docs/protocol/mtu.md`: MTU-safe UDP datagram limits and fragmentation policy.
- `docs/protocol/security.md`: password derivation and crypto modes.
- `docs/protocol/control-auth.md`: group-authenticated Relay control traffic.
- `docs/protocol/identity-admission.md`: optional OIDC-derived per-user Relay admission.
- `docs/configuration/relay-csv.md`: Relay Directory, control-key, and Management Plane CSV provisioning formats.
- `docs/extensions/management/overview.md`: optional, mTLS-protected Management Plane boundary and roles.
- `docs/extensions/management/service-admission.md`: signed Managed Service Admission for non-interactive services.
- `docs/extensions/management/recording-integration.md`: receive-only recording-worker integration boundary.
- `docs/extensions/management/openapi-v1.yaml`: Management Plane HTTPS and SSE API contract.
- `docs/protocol/fec.md`: external parity FEC and Opus in-band FEC.
- `docs/protocol/fec-testing.md`: common FEC fault-injection cases.
- `docs/protocol/directory-udp.md`: optional Directory UDP v3 protocol; channel-password scoped with bounded fragmentation and an optional media-port carrier.
- `docs/protocol/ping.md`: liveness and RTT measurement.
- `docs/protocol/diagnostics.md`: local debug metrics and redaction rules.
- `docs/protocol/versioning.md`: compatibility and release procedure.
- `schemas/`: JSON Schemas for directory, management events, and service grants.
- `test-vectors/`: deterministic packet, cryptographic, service-admission, and Relay CSV parser test data.

## Compatibility rule

An implementation may claim compatibility with a tagged IncomUdon specification
only when it uses the documentation, schemas, and applicable test vectors from
that exact Git tag, parses every applicable vector, and produces byte-identical
output for all deterministic encode vectors.

The `main` branch normally has `SPEC_VERSION` set to `unreleased`. Its vectors
describe the current development specification and MUST NOT be used to claim
compatibility with an older tagged release.

## License

The specification text, schemas, and test vectors are licensed under MIT.
