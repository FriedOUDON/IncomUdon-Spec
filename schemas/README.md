# Schemas

`directory-v1.schema.json` validates the authenticated outer directory
envelope. It does not validate ciphertext plaintext; that must happen only
after AES-GCM authentication succeeds.

- `diagnostics-v1.schema.json`: local client debug-metrics snapshot.
