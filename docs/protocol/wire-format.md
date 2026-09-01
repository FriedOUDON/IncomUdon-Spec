# UDP Wire Format

## Common envelope

All multibyte integer fields are unsigned and encoded in network byte order
(big endian).

### Version 1 fixed header

| Offset | Size | Field | Description |
|---:|---:|---|---|
| 0 | 1 | `version` | Protocol version; currently `1` |
| 1 | 1 | `type` | Packet type |
| 2 | 2 | `header_len` | Number of bytes before payload |
| 4 | 4 | `channel_id` | Relay channel identifier |
| 8 | 4 | `sender_id` | Sender identifier |
| 12 | 2 | `seq` | Per-sender sequence number, wrapping at 65535 |
| 14 | 2 | `flags` | Envelope feature flags |

The Version 1 fixed header is 16 bytes.

### Security header

When `header_len` is 28, the fixed header is followed by this 12-byte
security header:

| Offset from security header | Size | Field | Description |
|---:|---:|---|---|
| 0 | 8 | `nonce` | Packet nonce |
| 8 | 4 | `key_id` | Key identifier |

A secured packet then carries ciphertext followed by a 16-byte GCM tag.

### Legacy header

A legacy fixed header is 14 bytes and omits `flags`. Legacy packets use a
zero flag value when exposed through the Version 1 API. Implementations MUST
accept this header only for explicitly supported legacy compatibility modes.

## Envelope flags

| Bit | Name | Meaning |
|---:|---|---|
| 0 | `AES_GCM_V2_HEADER_AAD` | The complete 28-byte header is AES-GCM additional authenticated data |

Undefined flag bits MUST be ignored when receiving and MUST be zero when
transmitting.

## Packet type registry

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

## Plain control packets

Existing Version 1 plain control packets use `header_len = 28`, a zero nonce,
a zero key ID, and an all-zero 16-byte tag. They are identified by packet type
and are not authenticated by that zero tag. Future secure control extensions
MUST use the AES-GCM v2 construction rather than treating the zero tag as
security.
