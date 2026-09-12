# Test Vectors

All vectors use synthetic secrets and identifiers. They are safe to commit but
MUST NOT be used in production.

| File | Purpose |
|---|---|
| `packet-envelope-v1.json` | Plain packet encoding and control payloads |
| `password-kdf-v1.json` | Argon2id-v1 and raw-secret-v1 root-key derivation |
| `aes-gcm-v2.json` | Channel credential derivation, AES-GCM v2 AAD, ciphertext, and tag |
| `control-auth-v1.json` | Password/control-key derivation and authenticated control tag |
| `fec-rs-6-2.json` | Historical fixed-size six-frame two-parity FEC case |
| `fec-v2-variable-6-2.json` | FEC v2 variable-size and short-final-block parity/recovery cases |
| `fec-fault-cases.json` | Machine-readable index of common FEC fault-injection cases |
| `directory-psk-v1.json` | Legacy shared-PSK Directory v1 request envelope |
| `directory-channel-v2.json` | Primary channel-password-derived Directory v2 request envelope |
| `diagnostics-v1.json` | Redacted local debug-metrics snapshot |
| `ptt-timeout-v1.json` | `TALK_RELEASE` reason payloads and timeout timelines |
| `identity-admission-v1.json` | Ed25519 JWS ticket, proof-of-possession, and denial payloads |
| `mtu-v1.json` | MTU-safe AUDIO and FEC v2 datagram budget cases |
| `multi-talker-mixing-v1.json` | Concurrent-talker gain, limiter, transition, and source-limit cases |

A compatible implementation MUST compare raw bytes, not only decoded fields.
