# Protocol Overview

## Scope

IncomUdon Version 1 is a UDP push-to-talk protocol. A Relay keeps a short-lived
membership table per `channel_id`, grants one or more active talkers according
to Relay policy, and forwards packets without decoding encrypted media.

Clients use a single channel ID and sender ID per session. A receiver that
supports multiple concurrent talkers MUST keep decoder, FEC, and playout state
separate for each sender ID.

## Transport lifecycle

1. Send `JOIN` to register the observed UDP source endpoint.
2. Send `CODEC_CONFIG` before the first media frame for a sender.
3. Send `PTT_ON`; wait for `TALK_GRANT` before treating media as authorized.
4. Send `AUDIO` and optional `FEC` while granted.
5. Send `PTT_OFF`; the Relay broadcasts `TALK_RELEASE`.
6. Send `KEEPALIVE` while idle and `LEAVE` during a clean disconnect.

A joining client receives `SERVER_CONFIG`. If talkers are already active, the
Relay sends each active talker's `CODEC_CONFIG` before its `TALK_GRANT`.

## Relay policy

With multi-talk disabled, the Relay grants one active talker. With multi-talk
enabled, it grants up to its configured active-talker limit. Unauthorized
`AUDIO` and `FEC` packets are not forwarded. The Relay may release a talker
when its configured maximum talk duration or membership timeout expires.

## Packet classes

| Class | Types | Purpose |
|---|---|---|
| Membership | `JOIN`, `LEAVE`, `KEEPALIVE` | Endpoint registration and liveness |
| Floor control | `PTT_ON`, `PTT_OFF`, `TALK_*` | Talk request and Relay decision |
| Media | `AUDIO`, `FEC`, `CODEC_CONFIG` | Voice frames and decoder configuration |
| Server | `SERVER_CONFIG` | Talk timeout and multi-talk policy |
| Diagnostics | `PING`, `PONG` | Endpoint liveness and RTT |
| Compatibility | `KEY_EXCHANGE` | Legacy handshake marker |

The Relay recognizes protocol version `1` only.
