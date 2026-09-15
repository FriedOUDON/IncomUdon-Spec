# UDP Wire Format

All multibyte integers use network byte order (big endian).

## Version 1 fixed header

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 1 | `version` (`1`) |
| 1 | 1 | `type` |
| 2 | 2 | `header_len` |
| 4 | 4 | `channel_id` |
| 8 | 4 | `sender_id` |
| 12 | 2 | `seq` |
| 14 | 2 | `flags` |

The fixed header is 16 bytes. `seq` increments for every packet sent by a
client and wraps modulo 65536. A Relay MUST likewise assign `seq` from its own
outbound counter to every Relay-originated or Relay-reauthenticated downstream
control packet; this counter is independent of client sequence spaces and MAY
be shared across original talker sender IDs. Receivers MUST tolerate wrapping
and MUST NOT assume that the sequence field alone is a cryptographic nonce or
replay identifier.

## AES-GCM v2 media security header

An AES-GCM v2 encrypted `AUDIO` or `FEC` packet MUST set `header_len = 36` and
carry this header immediately after the fixed header:

| Offset | Bytes | Field |
|---:|---:|---|
| 16 | 12 | `media_nonce_base_96` |
| 28 | 4 | `media_counter` (`u32`) |
| 32 | 4 | wire `key_id` (`media_key_id`) |

In this 36-byte header, the wire `key_id` is the `media_key_id`. It belongs
to the media-crypto namespace and is distinct from the Control Authentication
`control_key_id` carried by the 28-byte header below.

Ciphertext follows offset 36 and the final 16 bytes are the AES-GCM
authentication tag. The AES-GCM nonce is
`U96BE(U96BE(media_nonce_base_96) + U32BE(media_counter))`; the exact 36-byte
packet prefix is authenticated as AAD. The base/counter fields also define the
receiver media anti-replay domain and sliding replay window; see `security.md`.

## Control and legacy security header

A packet with `header_len = 28` carries this separate header immediately after
the fixed header:

| Offset | Bytes | Field |
|---:|---:|---|
| 16 | 8 | `nonce` |
| 24 | 4 | wire `key_id` (`control_key_id`) |

In this 28-byte header, the wire `key_id` is the `control_key_id`. It
selects Control Authentication key material and MUST NOT be interpreted as a
`media_key_id`.

This form is used by Control Authentication v1 and documented in
`control-auth.md`. It MUST NOT be used for AES-GCM v2 encrypted media. Legacy
plain control packets in encrypted modes may carry a 28-byte zero nonce/key-ID
header, their plaintext payload, and a 16-byte zero tag for compatibility.

## Datagram size

The complete UDP payload, including this envelope and any authentication tag,
MUST NOT exceed `MAX_UDP_DATAGRAM_BYTES = 1200`. See `mtu.md` for the
normative media/FEC budgets and Path MTU handling rules.

## Legacy header

A legacy 14-byte header omits `flags`. Existing native clients may parse it
for backwards compatibility. New implementations MUST transmit the 16-byte
Version 1 fixed header and MUST NOT generate the 14-byte form.

## Flags

| Value | Name | Meaning |
|---:|---|---|
| `0x0001` | `AES_GCM_V2_HEADER_AAD` | AES-GCM v2 media: `header_len = 36`; authenticate the first 36 bytes as AAD |
| `0x0002` | `CONTROL_AUTH_V1` | Authenticate plaintext control with HMAC-SHA-256 |

Unknown flag bits MUST be zero when sending and ignored when receiving.

## Packet types

| Value | Name |
|---:|---|
| `0x01` | `AUDIO` |
| `0x02` | `PTT_ON` |
| `0x03` | `PTT_OFF` |
| `0x04` | `KEEPALIVE` |
| `0x05` | `JOIN` |
| `0x06` | `LEAVE` |
| `0x07` | `TALK_GRANT` |
| `0x08` | `TALK_RELEASE` |
| `0x09` | `TALK_DENY` |
| `0x0A` | `KEY_EXCHANGE` |
| `0x0B` | `CODEC_CONFIG` |
| `0x0C` | `FEC` |
| `0x0D` | `SERVER_CONFIG` |
| `0x0E` | `PING` |
| `0x0F` | `PONG` |
| `0x10` | `AUTH_HELLO` |
| `0x11` | `AUTH_CHALLENGE` |
| `0x12` | `IDENTITY_BEGIN` |
| `0x13` | `IDENTITY_CHALLENGE` |
| `0x14` | `IDENTITY_PROOF` |
| `0x15` | `IDENTITY_DENY` |
| `0x16` | `SERVICE_ADMISSION_BEGIN` |
| `0x17` | `SERVICE_ADMISSION_CHALLENGE` |
| `0x18` | `SERVICE_ADMISSION_PROOF` |
| `0x19` | `SERVICE_ADMISSION_DENY` |
| `0x1A` | `PTT_REQUEST` |

See `../test-vectors/packet-envelope-v1.json` for canonical byte examples.

Control Authentication v1 packet construction is defined in `control-auth.md`.
