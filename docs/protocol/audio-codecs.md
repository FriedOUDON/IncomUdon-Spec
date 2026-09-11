# Audio Codecs and Timing

## Transport IDs

| ID | Codec | Mode field |
|---:|---|---|
| `0x00` | PCM | ignored; clients display no bitrate |
| `0x01` | Codec2 | one of 450, 700, 1600, 2400, 3200 bps |
| `0x02` | Opus | one of 6000, 8000, 12000, 16000, 20000, 64000, 96000, 128000 bps |

Unsupported mode values are normalized to the nearest supported value by the
current PWA implementation. New clients SHOULD transmit only listed values.

`Opus (in-band FEC)` is a profile/UI mode, not a new transport codec ID. It
uses transport ID `0x02` and advertises its FEC behavior through
`CODEC_CONFIG`. See `fec.md` and `control-packets.md`.

## AUDIO payload

The modern media payload is:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 2 | `audio_seq` (`u16`) |
| 2 | variable | Codec frame |

`audio_seq` increments per media frame and is independent of envelope `seq`.
It drives loss detection and external-FEC grouping. Media frames are normally
20 ms.

`MAX_MEDIA_FRAME_BYTES` is `4096`. It is a receiver-side codec and FEC
validation ceiling: a codec frame excludes the two-byte `audio_seq` prefix and
receivers MUST discard frames over this value before codec decoding. FEC v2
uses the same ceiling for every advertised frame length and padded parity data.

It is not a transmit size. Senders MUST cap every outbound codec frame at
`MAX_TRANSMIT_MEDIA_FRAME_BYTES = 1139` and every complete UDP datagram at
`MAX_UDP_DATAGRAM_BYTES = 1200`. These MTU-safe limits, including exact
AES-GCM v2 and FEC v2 budgets, are defined in `mtu.md`.

PCM is signed 16-bit little-endian mono at 8000 Hz, 160 samples per frame
(320 bytes). A legacy PCM payload of exactly 320 bytes has no `audio_seq` and
MUST be accepted as an unsequenced PCM frame. Modern PCM carries 322 bytes:
two sequence bytes followed by the 320-byte PCM frame.

Codec2 and Opus frames use the negotiated codec configuration. Receivers MUST
maintain codec state by sender ID, not merely by channel ID.

## Real-time rules

The normative receiver playout timeline, latency bounds, and FEC
deadlines are defined in `playout.md`.

- Capture, network, external-FEC, and playback queues MUST be bounded.
- Senders SHOULD drop stale frames instead of creating delayed speech.
- Receivers SHOULD resynchronize near the live edge when jitter-buffer delay
  exceeds their configured limit.
- A `TALK_RELEASE` flushes decodable queued media and then discards remaining
  incomplete FEC state.
- Opus in-band FEC receivers retain one 20 ms playout interval to allow
  reconstruction from the following packet.

The Relay forwards authorized media byte-for-byte. In particular, it MUST NOT
rewrite AES-GCM v2 headers because they are authenticated.
