# Test Vectors

All vectors use synthetic secrets and identifiers. They are safe to commit but
MUST NOT be used in production.

| File | Purpose |
|---|---|
| `packet-envelope-v1.json` | Plain packet encoding and control payloads |
| `aes-gcm-v2.json` | Password derivation, AES-GCM v2 AAD, ciphertext, and tag |
| `control-auth-v1.json` | Password/control-key derivation and authenticated control tag |
| `fec-rs-6-2.json` | Historical fixed-size six-frame two-parity FEC case |
| `fec-v2-variable-6-2.json` | FEC v2 variable-size and short-final-block parity/recovery cases |
| `fec-fault-cases.json` | Machine-readable index of common FEC fault-injection cases |
| `directory-psk-v1.json` | Authenticated directory request envelope |
| `diagnostics-v1.json` | Redacted local debug-metrics snapshot |
| `ptt-timeout-v1.json` | `TALK_RELEASE` reason payloads and timeout timelines |
| `identity-admission-v1.json` | Ed25519 JWS ticket, proof-of-possession, and denial payloads |
| `mtu-v1.json` | MTU-safe AUDIO and FEC v2 datagram budget cases |

A compatible implementation MUST compare raw bytes, not only decoded fields.
