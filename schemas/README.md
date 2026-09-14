# Schemas

`directory-v2.schema.json` validates the primary channel-password-derived
Directory UDP v2 outer envelope. `directory-v1.schema.json` validates the
legacy explicit shared-PSK envelope. Neither schema validates ciphertext
plaintext; that must happen only after AES-GCM authentication succeeds.

- `directory-v1.schema.json`: shared-PSK Directory UDP v1 compatibility envelope.
- `directory-v2.schema.json`: primary channel-password-derived Directory UDP v2 envelope.
- `diagnostics-v1.schema.json`: local client debug-metrics snapshot.
- `management/service-admission-grant-v1.schema.json`: signed Managed Service Admission claim set after JWS verification.
- `management/management-event-v1.schema.json`: redacted Management Plane SSE event envelope.
