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
| `IDENTITY_BEGIN` | Admission Ticket and Ed25519 public key | Starts optional OIDC-derived Relay identity admission |
| `IDENTITY_CHALLENGE` | Relay expiry and random challenge | Sent after a valid ticket is presented |
| `IDENTITY_PROOF` | Ed25519 challenge signature | Completes proof-of-possession before JOIN |
| `IDENTITY_DENY` | Relay admission denial reason | Indicates required/invalid/expired/unauthorized admission |

Control Authentication v1 requirements, authenticated JOIN payload, and
replay behavior are defined in `control-auth.md`. Optional OIDC-derived Relay
admission, ticket/proof payloads, and authorization policy are defined in
`identity-admission.md`.

## Talk packets

`TALK_GRANT` and `TALK_DENY` have a 4-byte payload:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | `talker_id` (`u32`) |

`TALK_RELEASE` has a five-byte payload: `talker_id:u32 || release_reason:u8`.
Release reason values and authoritative Relay timeout behavior are defined in
`ptt-timeout.md`.

`TALK_DENY` identifies the current lowest sender ID among active talkers, or
zero when none can be selected. A client MUST stop pending transmission after
a deny and MUST discard stale queued frames.

A duplicate `PTT_ON` from an already granted sender causes a grant to be sent
to that sender only. It does not rebroadcast a grant because that would reset
other receivers' playout state or extend the server-managed talk deadline.

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
| 0 | 2 | `maximum_talk_seconds` in whole seconds; zero disables the server-managed limit |
| 2 | 1 | flags; bit 0 is `multi_talk_enabled`; bits 1-7 are reserved and MUST be zero |
| 3 | 1 | maximum active talkers; minimum effective value is one |

The timeout is a Relay-enforced monotonic talk lease. Its complete semantics,
release reasons, configuration-update handling, and client obligations are
specified in `ptt-timeout.md`.

## Security note

Control Authentication v1 authenticates control packets when its flag is set
and required by Relay policy; see `control-auth.md`. The legacy zero-tag
control framing is permitted only when Control Authentication v1 is not in
use. A receiver MUST NOT treat a legacy zero tag as authentication.
