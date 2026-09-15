# Test Vectors

All vectors use synthetic secrets and identifiers. They are safe to commit but
MUST NOT be used in production.

| File | Purpose |
|---|---|
| `packet-envelope-v1.json` | Plain packet encoding and control payloads |
| `password-kdf-v1.json` | Argon2id-v1 and raw-secret-v1 root-key derivation |
| `aes-gcm-v2.json` | Channel credential derivation, AES-GCM v2 base/counter AAD, ciphertext, and tag |
| `media-replay-v1.json` | AES-GCM v2 authenticated media replay-window acceptance and rejection cases |
| `control-auth-v1.json` | Password/control-key derivation, authenticated control tag, pre-JOIN counter sequences, and Relay counter-rollover boundaries |
| `relay-reauthenticated-codec-config-v1.json` | Relay reconstruction of authenticated `CODEC_CONFIG` with a fresh Relay nonce, sequence, and tag |
| `fec-rs-6-2.json` | Historical fixed-size six-frame two-parity FEC case |
| `fec-v2-variable-6-2.json` | FEC v2 variable-size and short-final-block parity/recovery cases |
| `fec-fault-cases.json` | Machine-readable index of common FEC fault-injection cases |
| `directory-psk-v1.json` | Legacy shared-PSK Directory v1 request envelope |
| `directory-channel-v2.json` | Primary channel-password-derived Directory v2 request envelope |
| `diagnostics-v1.json` | Redacted local debug-metrics snapshot |
| `ptt-timeout-v1.json` | `TALK_RELEASE` reason payloads and timeout timelines |
| `membership-lease-v1.json` | Membership lease timing, keepalive cadence, and Control Authentication policy refresh cases |
| `floor-interrupt-v1.json` | Admission-required interrupt request, preemption release, and priority-selection cases |
| `identity-admission-v1.json` | Ed25519 JWS ticket, proof-of-possession, denial payloads, and membership-expiry tie-break cases |
| `management/service-admission-v1.json` | Managed Service Admission Ed25519 JWS grant, proof-of-possession, and denial payloads |
| `management/service-admission-control-auth-v1.json` | Managed Service Admission pre-JOIN Control Authentication counter sequence |
| `management/event-stream-resume-v1.json` | SSE cursor precedence and role-aware `410 Gone` recovery |
| `configuration/relay-csv-v1.json` | Relay Directory, Control Authentication, and Management Plane CSV parser fixture |
| `mtu-v1.json` | MTU-safe AUDIO and FEC v2 datagram budget cases |
| `multi-talker-mixing-v1.json` | Concurrent-talker gain, limiter, transition, and source-limit cases |

A compatible implementation MUST compare raw bytes, not only decoded fields.
