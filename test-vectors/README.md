# Test Vectors

All vectors use synthetic secrets and identifiers. They are safe to commit but
MUST NOT be used in production.

| File | Purpose |
|---|---|
| `packet-envelope-v1.json` | Independently re-encoded Version 1 envelopes and control/media payloads |
| `password-kdf-v1.json` | Independently re-derived Argon2id-v1 and raw-secret-v1 root keys |
| `aes-gcm-v2.json` | Independently re-encrypted AES-GCM v2 media key, nonce/AAD, ciphertext, and tag |
| `media-replay-v1.json` | Independently evaluated AES-GCM v2 authenticated media replay-window transitions |
| `control-auth-v1.json` | Independently re-derived Control Authentication HMAC tag/cookie and counter boundaries |
| `relay-reauthenticated-codec-config-v1.json` | Relay reconstruction of authenticated `CODEC_CONFIG` with a fresh Relay nonce, sequence, and tag |
| `fec-rs-6-2.json` | Independently recomputed historical fixed-size six-frame P/Q parity and recovery case |
| `fec-v2-variable-6-2.json` | Independently recomputed FEC v2 variable-size, short-final-block, and wrap-boundary parity/recovery cases |
| `fec-fault-cases.json` | Machine-readable index of common FEC fault-injection cases |
| `directory-v3.json` | Independently re-encrypted Directory UDP v3 AEAD, fragmentation, replay, media-port carrier, lifecycle, type/payload, and identifier cases |
| `diagnostics-v1.json` | Test-vector metadata plus a redacted local debug-metrics `snapshot` |
| `ptt-timeout-v1.json` | Independently evaluated `TALK_RELEASE` reason payloads and server-managed timeout transitions |
| `membership-lease-v1.json` | Independently evaluated membership timing, keepalive cadence, and Control Authentication refresh transitions |
| `floor-interrupt-v1.json` | Independently evaluated authenticated interrupt request, preemption, and priority-selection transitions |
| `identity-admission-v1.json` | Ed25519 admission fixtures and independently evaluated membership-expiry tie-breaks |
| `management/service-admission-v1.json` | Ed25519 service-admission fixtures and independently evaluated expiry/grace transitions |
| `management/service-admission-control-auth-v1.json` | Managed Service Admission pre-JOIN Control Authentication counter sequence |
| `management/management-event-v1.json` | Channel-scoped and global Management SSE event envelopes |
| `management/audit-retrieval-v1.json` | Audit retrieval query scenario and canonical response page |
| `management/event-stream-resume-v1.json` | SSE cursor precedence and role-aware `410 Gone` recovery |
| `management/authorization-scopes-v1.json` | Management API channel, resource, list, SSE global-event, and global-permission authorization cases |
| `configuration/relay-csv-v1.json` | Relay Directory, Control Authentication, and Management Plane CSV parser fixture |
| `mtu-v1.json` | MTU-safe AUDIO and FEC v2 datagram budget cases |
| `multi-talker-mixing-v1.json` | Concurrent-talker gain, limiter, transition, and source-limit cases |

A compatible implementation MUST compare raw bytes, not only decoded fields.
