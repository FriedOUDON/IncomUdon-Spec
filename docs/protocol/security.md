# Security

## Crypto mode registry

| Name | Status | Media Key ID (wire `key_id`) |
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
channel-password key. Managed Service Admission v1 uses the same authenticated
control path for its signed grant and proof exchange. It likewise does not
derive, disclose, or replace any channel-password key.

### Key ID namespaces

The fixed wire field name `key_id` has separate meanings in the two security
headers:

- `control_key_id` is the wire `key_id` in the 28-byte Control Authentication
  v1 header. It selects the HMAC `control_key` used to authenticate control
  packets.
- `media_key_id` is the wire `key_id` in the 36-byte AES-GCM v2 media header.
  It selects the media-crypto key/profile namespace and is part of the media
  replay domain.

These identifiers are independent. An authenticated `CODEC_CONFIG` carries a
`control_key_id` in its Control Authentication header but does not carry a
`media_key_id`. For AES-GCM v2, receivers obtain the expected `media_key_id`
from the selected media mode; it is fixed at `2`. A `control_key_id` MUST NOT
be substituted for a `media_key_id` when selecting or creating media replay
state.

## AES-GCM nonce lifecycle and media anti-replay

AES-256-GCM v2 identifies every encrypted-media session with a 12-byte
`media_nonce_base_96`. At session initialization, a sender MUST obtain this
base from a cryptographically secure random number generator (CSPRNG), set
`media_counter = 0`, announce the base in authenticated `CODEC_CONFIG`, and
allocate one counter for every encrypted `AUDIO` and `FEC` packet. This shared
namespace includes both P and Q parity packets.

The on-wire header carries both the base and the allocated `media_counter`:

```text
nonce_96 = U96BE((U96BE(media_nonce_base_96) + U32BE(media_counter)) mod 2^96)
```

The sender MUST allocate the counter before encryption. A failed encryption or
send consumes that counter; an implementation MUST NOT roll it back, reuse it,
or emit it twice. `media_counter` ranges from `0` through `2^32 - 1`; a sender
MUST start a fresh media session with a newly generated base before it would
wrap, whenever counter state is lost, or whenever a local session is reset
while retaining the media key. A fresh session MUST send a new authenticated
`CODEC_CONFIG` before its first encrypted media packet.

The media key is shared by channel participants. Sequential, timestamp-based,
or sender-ID-derived bases are prohibited. A CSPRNG-generated 96-bit base per
sender/session makes accidental overlap of the at-most-`2^32` counter ranges
cryptographically negligible. As with all AES-GCM use, a `(media_key,
nonce_96)` pair MUST NOT be reused.

### Receiver replay window

AES-GCM authentication alone does not identify a previously valid packet that
has been replayed. Each receiver MUST therefore maintain a 64-counter sliding
replay window for every media replay domain:

```text
(channel_id, sender_id, media_key_id, media_nonce_base_96)
```

A receiver creates a domain only after accepting the matching authenticated
19-byte `CODEC_CONFIG`; the configuration's `media_nonce_base_96` binds the
sender's announced session to its codec state. For AES-GCM v2, the domain uses
the mode-selected `media_key_id` (`2`), never the `control_key_id` that
authenticated `CODEC_CONFIG`. It MUST reject encrypted media whose base or
`media_key_id` does not match that sender/media-key/codec configuration.
When a newly accepted configuration changes the base, the receiver MUST discard
the old replay window, jitter/FEC state, and codec ordering state for that
sender before accepting the new domain.

For a packet in an announced domain, the receiver MUST:

1. reject a counter more than 63 below the highest authenticated counter as
   stale;
2. authenticate the AES-GCM tag using the derived `nonce_96` and exact header
   AAD;
3. after successful authentication, reject a counter already marked in the
   64-counter window as replayed;
4. accept an unseen counter within the window to tolerate UDP reordering; and
5. advance and prune the window when a newly authenticated counter is newer
   than the recorded high-water counter.

Authentication failure MUST NOT advance the high-water counter or mark a
counter as seen. Implementations processing media concurrently MUST make the
post-authenticate check-and-mark operation atomic for a replay domain. A
receiver MUST drop rejected replay or stale packets before codec, FEC, jitter,
or playout processing.

`audio_seq` remains a codec/FEC and playout sequence only. It MUST NOT replace
this cryptographic replay check and MAY wrap independently. The Relay MAY keep
an equivalent bounded per-sender replay cache to discard obvious duplicates
before forwarding, but this is an optional bandwidth/DoS optimization; every
receiver MUST perform the final replay check itself.

Control Authentication v1 is REQUIRED with AES-GCM v2 so `CODEC_CONFIG` is
integrity-protected before it establishes an accepted media replay domain. It
protects active-session configuration replay through its own authenticated
control-session window. This group-key construction cannot make replay
protection survive an attacker who can reproduce an old authenticated session
across a full receiver-state loss; deployments requiring that stronger property
need a future Relay-issued epoch, persistent state, or per-sender credential
extension.

## AES-GCM v2

AES-GCM v2 sets flag `0x0001`, uses `media_key_id = 2` in its wire `key_id`
field, requires `header_len = 36` for encrypted `AUDIO` and `FEC` packets, and
authenticates the exact 36-byte packet prefix as AAD. The header carries
`media_nonce_base_96`, `media_counter`, and `media_key_id`; the final 16 bytes
of every encrypted payload are the GCM authentication tag.

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
