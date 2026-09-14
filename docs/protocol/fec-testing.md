# FEC Fault-Injection Test Cases

## Purpose

These cases define the minimum common behavior required from the PWA, Qt, and
Rust clients for external FEC v2 and Opus in-band FEC. They test transport and
playout decisions, not subjective speech quality. Use deterministic synthetic
frames where byte-exact recovery is expected, and use a fixed speech sample
where codec output is evaluated.

All tests use 20 ms media frames. Test harnesses MUST bound queues and MUST
fail a case if recovery requires replaying a media interval already rendered.

## External FEC v2 cases

| ID | Injection | Required result |
|---|---|---|
| `fec-v2-clean` | Deliver six audio frames and both parity packets. | Render audio in sequence; do not emit duplicate recovered frames. |
| `fec-v2-one-loss-p` | Drop one audio frame; deliver P parity. | Recover the dropped original frame byte-identically. |
| `fec-v2-one-loss-q` | Drop one audio frame; deliver Q parity only. | Recover the dropped original frame byte-identically. |
| `fec-v2-two-loss` | Drop two audio frames; deliver P and Q. | Recover both original frames byte-identically and in sequence. |
| `fec-v2-three-loss` | Drop three audio frames; deliver P and Q. | Do not generate incorrect audio; use normal loss handling for unrecoverable intervals. |
| `fec-v2-parity-loss` | Drop one parity packet and one audio frame. | Recover only when the remaining parity equation is sufficient. |
| `fec-v2-both-parity-loss` | Drop both parity packets and one audio frame. | Do not claim recovery; use normal loss handling. |
| `fec-v2-reorder` | Deliver one or both parity packets before delayed audio frames. | Preserve sequence order, recover when possible, and keep bounded state. |
| `fec-v2-late-original` | Recover a missing frame, then deliver its original late. | Do not render the interval twice. |
| `fec-v2-short-final` | Send a PTT-final block of 1 through 5 frames with P and Q. | Parse its actual block size and recover up to two losses when mathematically possible. |
| `fec-v2-final-order` | Locally release PTT with an incomplete final block. | Submit final AUDIO, P, Q, then `PTT_OFF` in that order; the Relay forwards the accepted final parity before release. |
| `fec-v2-final-reorder` | Deliver final P, then `PTT_OFF`, then final Q to the Relay. | Process release without delay; discard Q as post-release parity and do not reopen or extend the grant. |
| `fec-v2-release-incomplete` | Release talk before parity is received for a non-final incomplete block. | Flush available original audio and discard stale FEC state without unbounded delay. |
| `fec-v2-oversize` | Advertise a frame length greater than `MAX_MEDIA_FRAME_BYTES`. | Reject the FEC block without allocating an over-limit buffer. |

## Opus in-band FEC cases

| ID | Injection | Required result |
|---|---|---|
| `opus-fec-clean` | Deliver consecutive 12 or 16 kbps Opus packets. | Normal playout with one 20 ms retained interval. |
| `opus-fec-one-loss` | Drop exactly one Opus packet and deliver its successor. | Decode the missing interval using in-band FEC, then decode the successor normally. |
| `opus-fec-two-loss` | Drop two consecutive Opus packets. | Do not attempt false in-band recovery; use PLC or real-time loss handling. |
| `opus-fec-final-loss` | Drop the final packet before `TALK_RELEASE`. | Do not wait indefinitely for a nonexistent successor; use normal loss handling. |
| `opus-fec-unsupported-rate` | Enable in-band FEC above 16 kbps. | Connection and decoding remain valid; UI indicates recovery effectiveness is not guaranteed. |

## Combined-mode cases

| ID | Injection | Required result |
|---|---|---|
| `combined-one-loss` | Enable both mechanisms and drop one frame. | Render at most one reconstruction for the missing interval. |
| `combined-deadline` | Delay external parity past playout deadline while in-band FEC is available. | Render in-band reconstruction; do not replay after late parity arrives. |
| `combined-two-loss` | Enable both mechanisms and drop two frames with timely P/Q. | Use external recovery when it completes before the bounded playout deadline. |

## Execution requirements

- Run all cases with plain media and AES-GCM v2 media envelopes.
- Run external-FEC cases with PCM, Codec2, and variable-size Opus frames.
- Use the deterministic FEC v2 vector for byte-level tests.
- Record frame generation, arrival, recovery, render, discard, and queue-depth
  events in debug mode.
- A client MAY choose its own finite playout deadline, but MUST document that
  value and use it consistently in combined-mode tests.
