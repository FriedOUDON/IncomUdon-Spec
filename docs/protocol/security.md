# Security

## Crypto mode registry

| Name | Status | `key_id` |
|---|---|---:|
| `no-crypto` | Compatibility/testing only | 0 |
| `legacy-xor` | Deprecated compatibility mode | 1 |
| `aes-gcm` | Legacy AES-GCM | 1 |
| `aes-gcm-v2` | Default for new clients | 2 |

## Password normalization

Let `P` be the configured password string.

1. If `P` is `sha256:` followed by 64 hexadecimal characters, use those 32
   decoded bytes.
2. If `P` is exactly 64 hexadecimal characters, use those 32 decoded bytes.
3. Otherwise use `SHA-256(UTF-8(P))`.
4. If `P` is empty after trimming, use 32 zero bytes.

The channel password key is:

```text
password_key = SHA-256(normalized_password_hash || U32BE(channel_id))
```

## AES-GCM keys

Use HKDF-SHA-256 with empty salt:

```text
aes-gcm:    HKDF(password_key, "incomudon-session-aesgcm", 32)
aes-gcm-v2: HKDF(password_key, "incomudon-session-aesgcm-v2", 32)
```

## Control Authentication key

Control Authentication v1 derives a separate channel control key:

```text
control-auth-v1: HKDF(password_key, "incomudon-control-auth-v1", 32)
```

This key is distinct from the media key. It is used for HMAC-authenticated
control packets and is documented in `control-auth.md`. The normalized password
input and `password_key` derivation above are unchanged; normal text passwords
are first SHA-256 normalized, while 64-hex and `sha256:` inputs supply the
normalized 32 bytes before channel binding.

AES-256-GCM uses a 12-byte nonce:

```text
nonce_bytes = 0x00000000 || U64BE(packet_nonce)
```

A sender MUST use a cryptographically random 64-bit nonce base and increment
it for every encrypted packet. A nonce MUST NOT repeat with the same key.

## AES-GCM v2

AES-GCM v2 sets flag `0x0001`, uses `key_id = 2`, and authenticates the exact
28-byte packet prefix as AAD. The encrypted payload and 16-byte GCM tag do not
increase packet size compared with AES-GCM v1.

AES-GCM v1 uses no AAD. A receiver configured for v2 MUST reject a packet that
lacks the v2 flag, and a legacy receiver MUST reject a packet carrying it.

## Legacy XOR

`legacy-xor` XORs the payload with a 32-byte HKDF output using info
`incomudon-session`. Its tag is the first 16 bytes of:

```text
SHA-256(key || aad || ciphertext || U64LE(packet_nonce))
```

It is retained only to decode legacy deployments and MUST NOT be selected by a
new profile.

## Deterministic vector

See `../../test-vectors/aes-gcm-v2.json`. Test keys and passwords in that file
are synthetic and MUST NOT be deployed.
