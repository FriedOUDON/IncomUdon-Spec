# Forward Error Correction

## Scope and deployment

Forward error correction (FEC) is an optional media feature. The draft FEC v2
format below is the required format for the first coordinated release of the
PWA, Qt, and Rust clients. These clients are not yet formally released, so the
migration is intentionally a one-shot deployment: FEC v1 decoding and
negotiation are not required in compliant first-release clients.

After the first release, an incompatible FEC format change MUST use a new
explicitly negotiated format version or a new protocol version.

Two independent FEC mechanisms are defined:

- **External parity FEC** protects PCM, Codec2, and Opus codec frames with
  Reed-Solomon-style P and Q parity over GF(256).
- **Opus in-band FEC** is the Opus encoder/decoder feature and is available
  only for Opus media.

They may be enabled together only through an explicit user choice. The
combination is disabled by default and is not recommended for low-bitrate
Opus because it applies two sources of redundancy.

## External parity FEC v2

The encoder groups up to six consecutive codec frames by their `audio_seq`.
For each complete group, it emits two parity packets after the final audio
frame. When a talker releases PTT, an incomplete final group MUST also be
emitted using its actual `block_size`, from 1 through 6. Both P and Q parity
packets MUST be emitted for every complete and short final block.

Unlike FEC v1, FEC v2 supports variable-size frames. Each codec frame is
zero-padded to the greatest frame length in the block before parity is formed.
The original frame lengths are carried in every parity packet.

### FEC v2 payload

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 1 | `format_version`; fixed to `2` |
| 1 | 2 | `block_start` (`u16`, big-endian) |
| 3 | 1 | `block_size`; 1 through 6 |
| 4 | 1 | `parity_index`; 0 for P, 1 for Q |
| 5 | `block_size * 2` | `frame_lengths`; `u16` big-endian for each frame |
| variable | variable | parity data, exactly `max(frame_lengths)` bytes |

Both parity packets for a block carry identical length metadata. A receiver
MUST reject a block with an invalid version, block size, zero frame length,
frame length greater than `MAX_MEDIA_FRAME_BYTES`, or parity payload length
inconsistent with the advertised maximum frame length. `MAX_MEDIA_FRAME_BYTES`
is defined in `audio-codecs.md` and applies equally to raw audio codec frames
and FEC parity data. A sender MUST additionally cap every outbound source
frame and parity data length at `MAX_TRANSMIT_MEDIA_FRAME_BYTES` so the entire
FEC datagram satisfies the MTU policy in `mtu.md`.

The FEC packet uses the same crypto mode as media and is forwarded only while
the sender holds the talk grant. When media encryption is active, all fields in
the FEC payload, including lengths, are encrypted and authenticated by the
existing media envelope.

### Coding equations

For padded frame bytes `D[i]`, i = 0 through `block_size - 1`, over GF(256)
with primitive polynomial `0x11d`:

```text
P = D[0] XOR D[1] XOR ... XOR D[block_size - 1]
Q = sum(GF_MUL(D[i], 2^i))
```

One missing frame can be recovered with P or Q. Two missing frames require
both P and Q. More than two missing frames are not recoverable. After
recovery, a receiver MUST truncate each recovered padded frame to its advertised
original length before passing it to the codec decoder.

Receivers MUST key external FEC state by sender ID, codec configuration, and
AES-GCM v2 `media_nonce_base_96` when encryption is active.
They MUST bound FEC state and discard stale blocks rather than increasing
playout latency without limit. On `TALK_RELEASE`, receivers MUST flush any
available original or recovered media in sequence order and discard the
remaining incomplete FEC state.

## Opus in-band FEC

`Opus (in-band FEC)` is a UI and profile codec mode; its media transport codec
ID remains `Opus`. When selected, the encoder MUST enable the Opus in-band FEC
encoder control and set an explicit expected packet-loss percentage.

The standard expected packet-loss default is **10 percent**. It is persisted
per transmit profile. Normal settings UI MUST present the fixed choices `0`,
`3`, `5`, `10`, and `15` percent, with `10` selected by default.

Opus in-band FEC is formally supported at 12 and 16 kbps. Clients MAY expose
it at other Opus bitrates, but MUST describe recovery effectiveness at those
bitrates as not guaranteed.

A receiver that has been told that a sender uses Opus in-band FEC MUST:

1. track the sender's `audio_seq` values;
2. hold one 20 ms Opus playout interval;
3. when exactly one frame is missing and the following Opus packet arrives,
   decode that following packet once with Opus FEC enabled to reconstruct the
   missing frame; and
4. decode the same following packet normally for its own audio interval.

If two or more consecutive Opus frames are missing, the receiver MUST use its
normal packet-loss concealment or real-time drop policy. It MUST NOT wait
indefinitely for late media.

## Combined FEC behavior

A user may explicitly enable external parity FEC together with Opus in-band
FEC. When `Opus (in-band FEC)` is selected, the external-FEC control MUST
default to off. Enabling it MUST show a warning that the combination increases
bandwidth use and may increase playout latency.

Receivers MUST never replay an interval that has already been rendered. For a
missing interval, a complete external-FEC recovery is preferred when it is
available before the receiver's bounded playout deadline; otherwise an
available Opus in-band FEC reconstruction may be rendered. This mode is
non-default and intended only for loss-prone links with sufficient bitrate and
latency budget.

## Recommended operation

| Codec / bitrate | Recommended FEC mode |
|---|---|
| Opus 12 or 16 kbps | Opus in-band FEC |
| Opus 24 kbps or higher | No FEC by default; consider external parity FEC on measured loss-prone links |
| PCM / Codec2 | External parity FEC when loss protection is required |

External parity FEC adds two parity packets for each block of up to six audio
frames. Opus in-band FEC trades part of the configured Opus bitrate for
redundancy. Implementations SHOULD expose these trade-offs to users.

The normative FEC recovery deadline and bounded-delay behavior are defined
in `playout.md`.

## Test vectors and fault injection

`../../test-vectors/fec-v2-variable-6-2.json` is the deterministic
interoperability vector for FEC v2. It covers variable-size frames, one-frame
recovery, two-frame recovery, and a short final PTT block.

All supported clients MUST run the common fault-injection cases defined in
`fec-testing.md` before declaring FEC v2 interoperability.
