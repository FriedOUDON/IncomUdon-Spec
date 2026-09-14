# IncomUdon Specification

**Specification release:** `v0.1.0-draft`

This repository is the canonical interoperability specification for the
IncomUdon Relay, PWA client, Qt native client, and future Rust native client.
It describes observed Version 1 behavior and provides deterministic vectors
for new implementations.

## Normative language

The terms MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as
requirements for compatible implementations.

## Contents

- `docs/protocol/overview.md`: scope and transport lifecycle.
- `docs/protocol/wire-format.md`: Version 1 packet envelope.
- `docs/protocol/control-packets.md`: control payload layouts and relay rules.
- `docs/protocol/ptt-timeout.md`: Relay-enforced maximum talk duration and release behavior.
- `docs/protocol/floor-interrupt.md`: admission-required authorized floor preemption.
- `docs/protocol/audio-codecs.md`: media payloads and codec negotiation.
- `docs/protocol/playout.md`: real-time playout, jitter buffering, and resynchronization.
- `docs/protocol/mtu.md`: MTU-safe UDP datagram limits and fragmentation policy.
- `docs/protocol/security.md`: password derivation and crypto modes.
- `docs/protocol/control-auth.md`: group-authenticated Relay control traffic.
- `docs/protocol/identity-admission.md`: optional OIDC-derived per-user Relay admission.
- `docs/extensions/management/overview.md`: optional, mTLS-protected Management Plane boundary and roles.
- `docs/extensions/management/service-admission.md`: signed Managed Service Admission for non-interactive services.
- `docs/extensions/management/recording-integration.md`: receive-only recording-worker integration boundary.
- `docs/extensions/management/openapi-v1.yaml`: Management Plane HTTPS and SSE API contract.
- `docs/protocol/fec.md`: external parity FEC and Opus in-band FEC.
- `docs/protocol/fec-testing.md`: common FEC fault-injection cases.
- `docs/protocol/directory-udp.md`: optional Directory protocol; channel-password-derived v2 is primary and shared-PSK v1 is compatibility-only.
- `docs/protocol/ping.md`: liveness and RTT measurement.
- `docs/protocol/diagnostics.md`: local debug metrics and redaction rules.
- `docs/protocol/versioning.md`: compatibility and release procedure.
- `schemas/`: JSON Schemas for directory, management events, and service grants.
- `test-vectors/`: deterministic packet and cryptographic test data, including service admission.

## Compatibility rule

An implementation may claim `IncomUdon-Spec v0.1.0-draft` compatibility only
when it parses every applicable vector and produces byte-identical output for
all deterministic encode vectors.

## License

The specification text, schemas, and test vectors are licensed under MIT.
