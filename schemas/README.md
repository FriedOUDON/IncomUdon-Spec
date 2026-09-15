# Schemas

`directory-v3.schema.json` validates the only current Directory UDP outer
envelope. `directory-v3-client-payload.schema.json`,
`directory-v3-response-fragment.schema.json`, and
`directory-v3-error-payload.schema.json` validate decrypted Directory payloads
after AES-GCM authentication succeeds. The encrypted envelope and decrypted
payload are separate JSON documents; the normative `envelope.type` to payload
variant mapping is defined in `../docs/protocol/directory-udp.md`.
Neither schema validates unauthenticated ciphertext.

- `directory-v3.schema.json`: channel-password-derived Directory UDP v3 envelope.
- `directory-v3-client-payload.schema.json`: decrypted v3 request, registration, or heartbeat.
- `directory-v3-response-fragment.schema.json`: decrypted v3 participants or snapshot-page fragment.
- `directory-v3-error-payload.schema.json`: decrypted v3 request error response.
- `diagnostics-v1.schema.json`: local client debug-metrics snapshot.
- `management/service-admission-grant-v1.schema.json`: signed Managed Service Admission claim set after JWS verification.
- `management/management-event-v1.schema.json`: redacted Management Plane SSE event envelope.
