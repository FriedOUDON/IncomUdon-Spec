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
client and wraps modulo 65536. Receivers MUST tolerate wrapping and MUST NOT
assume that the sequence field alone is a cryptographic nonce.

## Security header

A packet with `header_len = 28` carries this header immediately after the
fixed header:

| Offset | Bytes | Field |
|---:|---:|---|
| 16 | 8 | `nonce` |
| 24 | 4 | `key_id` |

For encrypted media, ciphertext follows offset 28 and the final 16 bytes are
the authentication tag. Plain control packets in encrypted modes also use a
28-byte header, zero nonce/key ID, their plaintext payload, and 16 zero tag
bytes; see `security.md`.

## Legacy header

A legacy 14-byte header omits `flags`. Existing native clients may parse it
for backwards compatibility. New implementations MUST transmit the 16-byte
Version 1 fixed header and MUST NOT generate the 14-byte form.

## Flags

| Value | Name | Meaning |
|---:|---|---|
| `0x0001` | `AES_GCM_V2_HEADER_AAD` | Authenticate the first 28 bytes as AES-GCM AAD |
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

See `../test-vectors/packet-envelope-v1.json` for canonical byte examples.

Control Authentication v1 packet construction is defined in `control-auth.md`.
