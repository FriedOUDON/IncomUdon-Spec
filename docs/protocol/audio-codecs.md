# Audio Codecs and Timing

## Audio transport IDs

| ID | Codec |
|---:|---|
| `0x00` | PCM |
| `0x01` | Codec2 |
| `0x02` | Opus |

`CODEC_CONFIG` establishes the sender codec before an audio payload is
interpreted. Receivers MUST retain independent decoder state per sender.

## Real-time behavior

- Audio is transported in approximately 20 ms media frames unless a codec
  profile explicitly defines another frame duration.
- Clients SHOULD capture and play at the best practical device sample rate,
  then resample at the codec boundary.
- Jitter buffers MUST be bounded.
- When latency exceeds the configured bound, receivers SHOULD discard stale
  frames and resynchronize near the live edge.
- Transmit queues MUST be bounded. A sender MUST drop stale audio rather than
  deliver it seconds later.

## Codec-specific requirements

- PCM payload format, channel count, and sample rate are defined by the
  negotiated codec configuration.
- Codec2 mode selection MUST match the negotiated Codec2 mode and bitrate.
- Opus encoder and decoder settings MUST be compatible with the declared
  media frame duration.

Exact payload bodies and reference encode/decode samples will be published in
`test-vectors/` before the Rust client is declared protocol-compatible.
