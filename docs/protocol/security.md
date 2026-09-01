# Security

## Supported modes

Implementations support the legacy AES-GCM mode and AES-GCM v2. New clients
MUST default to AES-GCM v2. A client MUST only use a mode accepted by the
Relay and shared by the selected channel.

## AES-GCM v2

AES-GCM v2 encrypts the packet payload and authenticates the complete common
and security headers as Additional Authenticated Data (AAD).

- The `AES_GCM_V2_HEADER_AAD` envelope flag MUST be set.
- `header_len` MUST be 28.
- AAD is exactly the first 28 bytes of the datagram.
- Ciphertext follows the 28-byte header.
- The final 16 bytes are the GCM authentication tag.
- Any AAD, ciphertext, or tag verification failure MUST discard the packet.

The nonce source, key derivation, and key rotation behavior are verified by
the versioned crypto test vectors. Implementations MUST use cryptographically
secure random nonces and MUST NOT reuse a nonce with the same key.

## Legacy mode

Legacy AES-GCM is retained only for backwards compatibility. Its header is
not protected as AAD. New features MUST NOT extend legacy mode.

## Key material

Channel passwords, derived keys, and private key material MUST NOT appear in
logs, telemetry, ordinary settings exports, or packet-debug displays. Platform
credential stores SHOULD be used for persisted secrets.
