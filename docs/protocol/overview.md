# Protocol Overview

## Scope

IncomUdon is a real-time push-to-talk protocol transported over UDP. The
Relay forwards authenticated traffic between members of a channel. Clients
may use PCM, Codec2, or Opus audio payloads and may negotiate codec settings
at runtime.

This specification defines the common UDP envelope, packet type registry,
security requirements, timing expectations, and compatibility process. The
Relay does not decode audio payloads in the normal forwarding path.

## Transport requirements

- UDP is the primary transport for relay audio and control traffic.
- Numeric fields in the common UDP envelope use network byte order.
- Clients MUST treat packet loss, duplication, reordering, and endpoint
  changes as normal network conditions.
- Real-time traffic MUST prefer dropping stale frames over replaying delayed
  frames.
- A client MUST NOT transmit an audio payload before completing the channel
  join and codec configuration flow.

## Packet classes

| Class | Packet types | Purpose |
|---|---|---|
| Audio | `AUDIO`, `FEC` | Encoded voice and forward-error-correction data |
| PTT | `PTT_ON`, `PTT_OFF` | Sender talk-state transitions |
| Membership | `JOIN`, `LEAVE` | Channel membership lifecycle |
| Floor control | `TALK_GRANT`, `TALK_RELEASE`, `TALK_DENY` | Optional single-talker control |
| Codec | `CODEC_CONFIG` | Codec and bitrate capability negotiation |
| Liveness | `KEEPALIVE`, `PING`, `PONG` | Membership and round-trip measurement |
| Security | `KEY_EXCHANGE` | Legacy/key-exchange compatibility flow |
| Server | `SERVER_CONFIG` | Server-provided policy/configuration |

## Compatibility

The protocol version currently carried in packets is `1`. New behavior that
changes the meaning or byte layout of an existing packet MUST be introduced
with an explicit feature flag or a new protocol version. Implementations MUST
continue to parse supported legacy headers as described in `wire-format.md`.
