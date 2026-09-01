# IncomUdon Specification

This repository is the canonical specification for the IncomUdon relay
protocol and interoperability requirements. It is shared by the Relay,
PWA client, Qt native client, and the future Rust native client.

## Status

The current wire protocol is version 1. This repository starts as a
normative baseline for its common packet envelope and security behavior.
Payload layouts that are not yet covered by golden test vectors are marked
as provisional. A new implementation MUST NOT claim compatibility until it
passes the test vectors published with the matching specification release.

## Repository layout

- `docs/protocol/`: transport, security, audio, and control specifications.
- `schemas/`: machine-readable schemas for non-audio messages.
- `test-vectors/`: binary packet, crypto, FEC, and codec interoperability vectors.

## Consumers

Each implementation repository MUST declare the exact specification tag it
implements, for example: `IncomUdon-Spec v1.0.0`.

## License

The specification text, schemas, and test vectors are licensed under MIT.
