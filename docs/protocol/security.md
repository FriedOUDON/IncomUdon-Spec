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
directory-channel-v2: HKDF(password_key, "incomudon-directory-channel-v2", 32)
```

The `control-auth-v1` key is distinct from the media key. It is used for
HMAC-authenticated control packets and is documented in `control-auth.md`.
Directory UDP v2 derives additional direction and epoch keys from
`directory-channel-v2`; these are distinct from both media and Control
Authentication keys. See `directory-udp.md`. When configured, Identity Admission v1 additionally uses this authenticated control path for
its OIDC-derived Relay ticket and proof exchange; it does not derive a new
channel-password key. The normalized password
input and `password_key` derivation above are unchanged; normal text passwords
are first SHA-256 normalized, while 64-hex and `sha256:` inputs supply the
normalized 32 bytes before channel binding.

## AES-GCM nonce lifecycle

AES-256-GCM v2 uses the 12-byte `nonce_96` carried directly in the media
security header as its AEAD nonce/IV. It MUST NOT prepend a fixed zero prefix
or otherwise transform this value before AES-GCM processing.

At encrypted-media session initialization, a sender MUST obtain a fresh
96-bit `nonce_base` from a cryptographically secure random number generator
(CSPRNG), initialize `nonce_counter = 0`, and allocate nonces as:

```text
nonce_96 = U96BE((U96BE(nonce_base) + nonce_counter) mod 2^96)
nonce_counter = nonce_counter + 1
```

The sender MUST allocate the next nonce before attempting encryption. A failed
send or encryption operation consumes the allocation; implementations MUST
never roll the counter back or reuse that nonce. The same nonce-counter
namespace covers every AES-GCM v2 encrypted `AUDIO` and `FEC` packet produced
with the media key, including both P and Q parity packets.

A sender MUST NOT wrap the 96-bit counter space. To retain a conservative
lifetime bound, an encrypted-media session MUST contain no more than `2^32`
nonce allocations. Before reaching that limit, or whenever the counter state
is lost or reset while retaining the media key, the sender MUST begin a fresh
session with a newly generated 96-bit `nonce_base`. A receiver uses the
on-wire `nonce_96` directly and does not need the base or counter state.

The media key is shared by channel participants, so implementations MUST use a
CSPRNG for every sender/session base; sequential, timestamp-derived, or
sender-ID-derived bases are prohibited. This gives each sender/session a
96-bit random nonce starting point and makes accidental cross-sender range
collisions cryptographically negligible for the intended deployment. As with
all AES-GCM use, a `(media_key, nonce_96)` pair MUST NOT be reused.

## AES-GCM v2

AES-GCM v2 sets flag `0x0001`, uses `key_id = 2`, requires `header_len = 32`
for encrypted `AUDIO` and `FEC` packets, and authenticates the exact 32-byte
packet prefix as AAD. The final 16 bytes of every encrypted payload are the
GCM authentication tag.

The 28-byte Control Authentication v1 header is a separate HMAC construction;
it is not an AES-GCM v2 nonce format and MUST NOT be used for encrypted media.

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
