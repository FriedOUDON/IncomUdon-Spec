# Control Packets

Unless otherwise stated, a client control request uses its own `sender_id` in
the common header. Relay-generated `TALK_*` packets set both the header
`sender_id` and the payload talker ID to the resolved talker.

| Type | Client payload | Relay behavior |
|---|---|---|
| `JOIN` | empty normally; `expiry:u32 || cookie[16]` when Control Authentication v1 is required | Register authenticated endpoint, send server config and active talker sync |
| `LEAVE` | empty | Remove endpoint and release its talk state |
| `KEEPALIVE` | empty | Refresh endpoint membership |
| `PTT_ON` | empty | Ordinary grant or deny according to floor policy |
| `PTT_REQUEST` | `0x01` (`INTERRUPT_REQUESTED`) | Admission-required authorized higher-priority preemption request |
| `PTT_OFF` | empty | Release the requesting sender if active |
| `KEY_EXCHANGE` | ASCII `LEGACY` | Legacy compatibility marker |
| `AUTH_HELLO` | empty, Control Authentication v1 tag required | Relay returns `AUTH_CHALLENGE`; no membership state change |
| `AUTH_CHALLENGE` | Relay payload: expiry and cookie | Sent only to the requesting endpoint |
| `IDENTITY_BEGIN` | Admission Ticket and Ed25519 public key | Starts optional OIDC-derived Relay identity admission |
| `IDENTITY_CHALLENGE` | Relay expiry and random challenge | Sent after a valid ticket is presented |
| `IDENTITY_PROOF` | Ed25519 challenge signature | Completes proof-of-possession before JOIN |
| `IDENTITY_DENY` | Relay admission denial reason | Indicates required/invalid/expired/unauthorized admission |
| `SERVICE_ADMISSION_BEGIN` | Service Admission Grant and Ed25519 public key | Starts optional Management-Plane-derived service admission |
| `SERVICE_ADMISSION_CHALLENGE` | Relay expiry and random challenge | Sent after a valid service grant is presented |
| `SERVICE_ADMISSION_PROOF` | Ed25519 challenge signature | Completes service proof-of-possession before JOIN |
| `SERVICE_ADMISSION_DENY` | Relay service-admission denial reason | Indicates disabled/invalid/expired/revoked service admission |

Control Authentication v1 requirements, authenticated JOIN payload, and
replay behavior are defined in `control-auth.md`. Optional OIDC-derived Relay
admission, ticket/proof payloads, and authorization policy are defined in
`identity-admission.md`. Optional mTLS-Management-Plane-derived service
admission is defined in `../extensions/management/service-admission.md`.

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

`PTT_REQUEST` payload and Relay preemption rules are defined in
`floor-interrupt.md`. Floor Interrupt uses a new packet type so legacy empty
`PTT_ON` behavior remains unchanged.

A duplicate `PTT_ON` from an already granted sender causes a grant to be sent
to that sender only. It does not rebroadcast a grant because that would reset
other receivers' playout state or extend the server-managed talk deadline.

## Codec configuration

The first coordinated client release uses this 19-byte payload:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 1 | flags; bit 0 is `pcm_only` |
| 1 | 1 | codec transport ID |
| 2 | 4 | codec mode/bitrate in bps (`u32`, big-endian) |
| 6 | 1 | FEC options |
| 7 | 12 | `media_nonce_base_96` |

The codec mode/bitrate field carries the exact codec-specific bitrate in bps.
A sender MUST encode a listed bitrate without unit conversion, clamping, or
truncation. A receiver MUST reject a non-PCM `CODEC_CONFIG` whose codec ID or
bitrate is unsupported locally. For PCM, receivers MUST ignore this field.

For `aes-gcm-v2`, `media_nonce_base_96` MUST be a newly CSPRNG-generated,
non-zero media session base and MUST match every subsequent encrypted `AUDIO`
and `FEC` header for this sender until the next configuration. A sender MUST
create a fresh base whenever it changes the codec transport, mode, or FEC
options and emits a replacement configuration. The packet MUST use Control
Authentication v1. A receiver MUST authenticate this configuration before
creating or replacing the sender's media replay domain. When the Relay forwards
or replays a verified configuration, it reauthenticates the original talker's
19-byte payload as Relay-originated control under `control-auth.md`; the
receiver uses the Relay nonce domain for control replay protection while still
using the original talker `sender_id` and payload for media state.
`CODEC_CONFIG` does not carry a `media_key_id`: an AES-GCM v2 receiver MUST use
the `media_key_id` selected by its media security mode (`2` for AES-GCM v2).
The `control_key_id` in the Control Authentication header authenticates this
configuration but MUST NOT be used as its media replay-domain key ID.

For `no-crypto`, `legacy-xor`, and legacy `aes-gcm`, the 12-byte
`media_nonce_base_96` field (bytes 7 through 18) MUST be all zero and
receivers MUST ignore it. It remains present so the payload length is
unambiguous across the coordinated release.

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

The historical three-, four-, and five-byte `CODEC_CONFIG` forms are not
required for the first coordinated release because all clients are migrated
together. Implementations may retain historical decoding as a local
compatibility option, but MUST transmit the 19-byte form described above.

## Server configuration

`SERVER_CONFIG` has an eight-byte payload:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 2 | `maximum_talk_seconds` in whole seconds; zero disables the server-managed talk limit |
| 2 | 1 | flags; bit 0 is `multi_talk_enabled`; bits 1-7 are reserved and MUST be zero |
| 3 | 1 | maximum active talkers; value MUST be in the range 1 through 16 |
| 4 | 2 | `membership_lease_seconds` (`u16`, big-endian); 15 through 300 |
| 6 | 2 | `keepalive_interval_seconds` (`u16`, big-endian); 1 through `floor(membership_lease_seconds / 3)` |

The standard default membership values are a 30-second lease and a 10-second
idle keepalive interval. A Relay MUST send the eight-byte form and MUST NOT
send the predecessor four-byte form. A client MUST reject an invalid payload
length or invalid membership timing relationship rather than silently
normalizing it. The membership lease and refresh rules are defined in
`membership-lease.md`. The maximum talk timeout is a separate Relay-enforced
monotonic talk lease; its release reasons, configuration-update handling, and
client obligations are specified in `ptt-timeout.md`.

## Security note

Control Authentication v1 authenticates control packets when its flag is set
and required by Relay policy; see `control-auth.md`. The legacy zero-tag
control framing is permitted only when Control Authentication v1 is not in
use. A receiver MUST NOT treat a legacy zero tag as authentication.
