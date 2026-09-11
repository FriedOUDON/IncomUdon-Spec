# Control Packets

Unless otherwise stated, a client control request uses its own `sender_id` in
the common header. Relay-generated `TALK_*` packets set both the header
`sender_id` and the payload talker ID to the resolved talker.

| Type | Client payload | Relay behavior |
|---|---|---|
| `JOIN` | empty normally; `expiry:u32 || cookie[16]` when Control Authentication v1 is required | Register authenticated endpoint, send server config and active talker sync |
| `LEAVE` | empty | Remove endpoint and release its talk state |
| `KEEPALIVE` | empty | Refresh endpoint membership |
| `PTT_ON` | empty | Grant or deny according to floor policy |
| `PTT_OFF` | empty | Release the requesting sender if active |
| `KEY_EXCHANGE` | ASCII `LEGACY` | Legacy compatibility marker |
| `AUTH_HELLO` | empty, Control Authentication v1 tag required | Relay returns `AUTH_CHALLENGE`; no membership state change |
| `AUTH_CHALLENGE` | Relay payload: expiry and cookie | Sent only to the requesting endpoint |

Control Authentication v1 requirements, authenticated JOIN payload, and
replay behavior are defined in `control-auth.md`.

## Talk packets

`TALK_GRANT`, `TALK_RELEASE`, and `TALK_DENY` have a 4-byte payload:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | `talker_id` (`u32`) |

`TALK_DENY` identifies the current lowest sender ID among active talkers, or
zero when none can be selected. A client MUST stop pending transmission after
a deny and MUST discard stale queued frames.

A duplicate `PTT_ON` from an already granted sender causes a grant to be sent
to that sender only. It does not rebroadcast a grant because that would reset
other receivers' playout state.

## Codec configuration

The first coordinated client release uses this five-byte payload:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 1 | flags; bit 0 is `pcm_only` |
| 1 | 1 | codec transport ID |
| 2 | 2 | codec mode/bitrate (`u16`, big-endian) |
| 4 | 1 | FEC options |

FEC option bits are:

| Bit | Name | Meaning |
|---:|---|---|
| 0 | `external_parity_fec` | Sender may emit external parity FEC packets |
| 1 | `opus_inband_fec` | Sender enables Opus in-band FEC; valid only for Opus |
| 2 | `external_fec_v2` | External parity packets use the FEC v2 payload format |
| 3-7 | reserved | MUST be zero on transmit and ignored on receive |

`external_fec_v2` MUST be set when `external_parity_fec` is set. A receiver
MUST ignore inconsistent FEC options and continue to decode ordinary audio.
It MUST apply FEC state separately for each sender ID.

The historical four-byte and three-byte `CODEC_CONFIG` forms are not required
for the first coordinated release because all clients are migrated together.
Implementations may retain historical decoding as a local compatibility option,
but MUST transmit the five-byte form described above.

## Server configuration

`SERVER_CONFIG` has a four-byte payload:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 2 | maximum talk duration in whole seconds; zero disables it |
| 2 | 1 | flags; bit 0 is `multi_talk_enabled` |
| 3 | 1 | maximum active talkers; minimum effective value is one |

## Security note

In the currently deployed protocol, control packets are sent as plain packets
even when a media crypto mode is selected. Their zero GCM tag is a framing
placeholder, not authentication. New applications MUST preserve this behavior
for Version 1 compatibility and MUST NOT treat it as authenticated control.
A future protocol version should define authenticated control traffic.
