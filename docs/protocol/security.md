# Security

## Crypto mode registry

| Name | Status | `key_id` |
|---|---|---:|
| `no-crypto` | Compatibility/testing only | 0 |
| `legacy-xor` | Deprecated compatibility mode | 1 |
| `aes-gcm` | Legacy AES-GCM | 1 |
| `aes-gcm-v2` | Default for new clients | 2 |

## Channel credential and root-key derivation

A secure channel credential is either a human-entered passphrase or an
explicitly marked 256-bit random secret. Its only purpose at this stage is to
produce the 32-byte `password_key`; media, control, and Directory keys remain
separately derived from that root key.

The configured credential is interpreted as follows:

| Form | Credential kind | Rule |
|---|---|---|
| `secret:` followed by exactly 64 hexadecimal characters | `raw-secret-v1` | Decode the 32 bytes after `secret:`. |
| Any other non-empty string | `argon2id-v1` | Normalize to Unicode NFC and encode as UTF-8 passphrase bytes. |

The `secret:` prefix is ASCII and case-sensitive. Implementations MUST NOT
automatically recognize a bare 64-hex string as a raw secret; it is a
passphrase unless it has the explicit prefix. A credential beginning with
`sha256:` MUST be rejected. The draft-era `sha256:` and bare-64-hex
normalization forms are removed in the first coordinated migration.

For every secure channel, derive the public 16-byte channel salt:

```text
channel_salt = SHA-256(
  "incomudon-channel-password-salt-v1\0" || U32BE(channel_id)
)[0:16]
```

`channel_salt` is not secret and need not be transmitted. It prevents a single
precomputation from applying to every channel ID while avoiding an additional
per-channel provisioning field. A future random provisioned channel salt MUST
use a new credential-KDF version.

For `argon2id-v1`, derive:

```text
password_key = Argon2id(
  password = UTF8(NFC(P)),
  salt = channel_salt,
  version = 0x13,
  memory_kib = 65536,
  iterations = 3,
  parallelism = 4,
  output_length = 32
)
```

`argon2id-v1` follows the memory-constrained Argon2id recommendation in
[RFC 9106, Section 4](https://www.rfc-editor.org/rfc/rfc9106.html#section-4).
Parameters are protocol constants and MUST NOT be silently reduced after a
derivation failure.

For `raw-secret-v1`, derive:

```text
password_key = HKDF-SHA-256(
  IKM = decoded_secret_32,
  salt = channel_salt,
  info = "incomudon-raw-secret-v1",
  length = 32
)
```

Secure modes MUST reject an empty credential. `no-crypto` ignores the
credential and is the only mode that may be used without one. Implementations
MUST select the credential kind from the configured input before attempting
packet authentication and MUST NOT silently fall back to the removed SHA-256
scheme or try multiple credential kinds for an incoming packet. The credential
kind is local channel configuration, not UDP packet metadata.

Argon2id is performed only while establishing or reconfiguring a local channel
session, never once per packet. Implementations SHOULD retain only the derived
keys needed by the active session and SHOULD clear temporary passphrase and KDF
memory where the platform permits it. A 256-bit `secret:` credential is
recommended for unattended or high-security deployments; Argon2id raises the
cost of offline guessing but cannot make a weak passphrase strong.

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
Authentication keys. See `directory-udp.md`. When configured, Identity
Admission v1 additionally uses this authenticated control path for its
OIDC-derived Relay ticket and proof exchange; it does not derive a new
channel-password key.

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

See `../../test-vectors/password-kdf-v1.json` for root-key derivation and
`../../test-vectors/aes-gcm-v2.json` for AEAD construction. Test credentials
and keys in those files are synthetic and MUST NOT be deployed.
