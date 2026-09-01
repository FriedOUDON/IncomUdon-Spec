# Changelog

## v0.1.0-draft - 2026-09-01

- Documents the observed Version 1 UDP envelope and packet registry.
- Documents PCM, Codec2, Opus, FEC, floor-control, and Ping/Pong behavior.
- Documents AES-GCM v2 key derivation, nonce construction, and header AAD.
- Documents the optional PSK-protected directory UDP protocol.
- Adds deterministic packet, crypto, FEC, and directory test vectors.

This is a draft release. It is suitable as the compatibility target for the
first Rust protocol implementation, but it is not a promise that future
protocol revisions will be backward compatible.
