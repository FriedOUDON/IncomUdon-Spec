# Control Packets

Control packets are used for membership, talk state, codec negotiation, and
server policy. Their payload layouts are versioned independently from the
common envelope only when the Relay explicitly advertises support.

## Required lifecycle

1. A client sends `JOIN` for its channel and sender ID.
2. The Relay accepts or rejects membership according to its policy.
3. The client sends `CODEC_CONFIG` before transmitting an audio payload.
4. The client sends `PTT_ON` before a talk burst and `PTT_OFF` after it.
5. The client sends `LEAVE` when disconnecting cleanly.

## Floor control

When the Relay has multi-talk disabled, clients MUST honor `TALK_GRANT`,
`TALK_RELEASE`, and `TALK_DENY`. A denied sender MUST immediately stop any
pending audio transmission and must not drain stale frames later.

When multi-talk is enabled, receivers MUST maintain a decode/jitter state per
active sender. A client MAY locally mute selected sender IDs without affecting
Relay membership.

## Payload status

The byte-level payload layouts for `JOIN`, `LEAVE`, `PTT_*`, `CODEC_CONFIG`,
and `SERVER_CONFIG` are provisional until captured Relay/PWA/Qt interoperability
vectors are checked into this repository. They MUST be documented here before
Protocol v1.0.0 is tagged.
