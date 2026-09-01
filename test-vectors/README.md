# Test Vectors

All vectors use synthetic secrets and identifiers. They are safe to commit but
MUST NOT be used in production.

| File | Purpose |
|---|---|
| `packet-envelope-v1.json` | Plain packet encoding and control payloads |
| `aes-gcm-v2.json` | Password derivation, AES-GCM v2 AAD, ciphertext, and tag |
| `fec-rs-6-2.json` | Six-frame two-parity FEC encode/recovery case |
| `directory-psk-v1.json` | Authenticated directory request envelope |

A compatible implementation MUST compare raw bytes, not only decoded fields.
