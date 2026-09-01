# Control Packets

Unless otherwise stated, a client control request uses its own `sender_id` in
the common header. Relay-generated `TALK_*` packets set both the header
`sender_id` and the payload talker ID to the resolved talker.

| Type | Client payload | Relay behavior |
|---|---|---|
| `JOIN` | empty | Register endpoint, echo to joiner, send server config and active talker sync |
| `LEAVE` | empty | Remove endpoint and release its talk state |
| `KEEPALIVE` | empty | Refresh endpoint membership |
| `PTT_ON` | empty | Grant or deny according to floor policy |
| `PTT_OFF` | empty | Release the requesting sender if active |
| `KEY_EXCHANGE` | ASCII `LEGACY` | Legacy compatibility marker |

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

The current payload is four bytes:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 1 | flags; bit 0 is `pcm_only` |
| 1 | 1 | codec transport ID |
| 2 | 2 | codec mode/bitrate (`u16`) |

A legacy three-byte form omits the codec transport ID: `[flags][mode:u16]`.
Receivers interpret that form as Codec2. When `pcm_only` is set, receivers MUST
interpret the transport as PCM regardless of byte 1.

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
