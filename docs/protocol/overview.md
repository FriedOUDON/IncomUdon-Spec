# Protocol Overview

## Scope

IncomUdon Version 1 is a UDP push-to-talk protocol. A Relay keeps a short-lived
membership table per `channel_id`, grants one or more active talkers according
to Relay policy, and forwards packets without decoding encrypted media.

Clients use a single channel ID and sender ID per session. A receiver that
supports multiple concurrent talkers MUST keep decoder, FEC, playout, and
resampler state separate for each sender ID, then mix eligible output under
`playout.md`.

## Transport lifecycle

1. When Control Authentication v1 is required, complete `AUTH_HELLO` and
   `AUTH_CHALLENGE`. When optional Identity Admission is required, complete
   `IDENTITY_BEGIN`, `IDENTITY_CHALLENGE`, and `IDENTITY_PROOF`; an authorized
   non-interactive service may instead complete `SERVICE_ADMISSION_BEGIN`,
   `SERVICE_ADMISSION_CHALLENGE`, and `SERVICE_ADMISSION_PROOF` when Managed
   Service Admission is enabled. Then send authenticated `JOIN` to register
   the observed UDP source endpoint. Otherwise send `JOIN`.
2. Send a 19-byte `CODEC_CONFIG` before the first media frame for a sender.
   It MUST use Control Authentication v1 when required by the channel policy,
   and always for AES-GCM v2. A policy-permitted unauthenticated configuration
   is limited to `no-crypto` and `legacy-xor`. For AES-GCM v2 the configuration
   announces the fresh media nonce base and establishes the receiver replay
   domain.
3. Send ordinary `PTT_ON`, or authorized `PTT_REQUEST` for Floor Interrupt;
   wait for `TALK_GRANT` before treating media as authorized.
4. Send `AUDIO` and optional `FEC` while granted and before any Relay-enforced
   talk deadline. On local PTT release, submit any final AUDIO and final FEC P/Q
   block before `PTT_OFF`, as defined in `fec.md`.
5. Send `PTT_OFF`; the Relay broadcasts `TALK_RELEASE` without waiting for
   reordered final parity. The Relay may instead release the talk at its
   server-managed deadline or on membership expiry.
6. Maintain the advertised membership lease by sending `KEEPALIVE` while
   idle and `LEAVE` during a clean disconnect, as defined in
   `membership-lease.md`.

A joining client receives `SERVER_CONFIG`. If talkers are already active, the
Relay sends each active talker's `CODEC_CONFIG` before its `TALK_GRANT`.

## Relay policy

With multi-talk disabled, the Relay grants one active talker. With multi-talk
enabled, it grants up to its configured active-talker limit. Unauthorized
`AUDIO` and `FEC` packets are not forwarded. The Relay MUST NOT forward a UDP
datagram larger than the MTU-safe protocol limit defined in `mtu.md`. The
Relay enforces each granted talker's configured maximum duration with a
monotonic deadline and releases
that talker when the deadline or membership lease expires. See
`ptt-timeout.md` for the authoritative timeout rules.

## Packet classes

| Class | Types | Purpose |
|---|---|---|
| Membership | `JOIN`, `LEAVE`, `KEEPALIVE` | Endpoint registration, lease refresh, and expiry |
| Floor control | `PTT_ON`, `PTT_REQUEST`, `PTT_OFF`, `TALK_*` | Talk request and Relay decision |
| Media | `AUDIO`, `FEC`, `CODEC_CONFIG` | Voice frames and decoder configuration |
| Server | `SERVER_CONFIG` | Talk, multi-talk, and membership timing policy |
| Diagnostics | `PING`, `PONG` | RTT/liveness measurement; independent of membership refresh |
| Compatibility | `KEY_EXCHANGE` | Legacy handshake marker |
| Authentication | `AUTH_HELLO`, `AUTH_CHALLENGE` | Relay cookie challenge for authenticated membership |
| Identity admission | `IDENTITY_*` | Optional OIDC-derived per-user Relay authorization |
| Service admission | `SERVICE_ADMISSION_*` | Optional mTLS-Management-Plane-derived Relay authorization for services |
| Directory | Separate JSON envelope | Optional channel-password-scoped metadata and participant discovery; v3 supports bounded fragmentation |

The Relay recognizes protocol version `1` only.
