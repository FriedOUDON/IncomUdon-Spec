# Membership Lease and Keepalive

## Scope

This document defines Version 1 endpoint membership lifetime after a successful
`JOIN`. It is distinct from the server-managed maximum talk lease in
`ptt-timeout.md` and from diagnostic `PING`/`PONG` liveness measurement in
`ping.md`.

A membership lease is a Relay-side monotonic deadline. On expiry, the Relay
MUST remove the endpoint membership. If that endpoint has an active talk grant,
the Relay MUST immediately stop forwarding its `AUDIO` and `FEC` and broadcast
exactly one `TALK_RELEASE` with reason `MEMBERSHIP_TIMEOUT` (`0x02`). For a
Managed Service Admission endpoint, this rule applies when the normal
membership deadline is earlier than or equal to the service admission deadline;
the strictly earlier service-admission deadline uses
`SERVICE_ADMISSION_EXPIRED` (`0x08`) as defined in
`../extensions/management/service-admission.md`. For an Identity Admission
endpoint, this rule likewise applies when the normal membership deadline is
earlier than or equal to ticket `exp`; only a strictly earlier ticket expiry
uses `IDENTITY_EXPIRED` (`0x05`) as defined in `identity-admission.md`.

## Advertised timing

`SERVER_CONFIG` advertises these values as defined in `control-packets.md`:

| Field | Requirement |
|---|---|
| `membership_lease_seconds` (`L`) | `u16` in the inclusive range 15 through 300 seconds. |
| `keepalive_interval_seconds` (`K`) | `u16` in the inclusive range 1 through `floor(L / 3)` seconds. |

The Version 1 defaults are `L = 30` and `K = 10`. The `K <= floor(L / 3)`
constraint reserves time for normal packet loss and scheduler jitter; it does
not guarantee membership survival through arbitrary UDP loss or process
suspension.

The Relay MUST select one valid `(L, K)` pair when accepting `JOIN`, start the
membership deadline at that acceptance time, and send the matching
`SERVER_CONFIG` before any `TALK_GRANT` to that endpoint. The selected pair is
a membership snapshot: a Relay MUST NOT change it for that endpoint until the
endpoint leaves or completes another successful `JOIN`. A later configuration
reload MAY use a different pair for new memberships. If it sends an updated
`SERVER_CONFIG` to existing endpoints for another policy change, it MUST retain
their membership snapshot values.

Before receiving a valid `SERVER_CONFIG` for each JOIN attempt, a joining
client MUST use a bootstrap `KEEPALIVE` interval of 5 seconds, measured from
its most recent JOIN or refresh-eligible transmission. The lower bound `L >= 15` makes this bootstrap
cadence safe for every conforming Relay. A client that receives an invalid
`SERVER_CONFIG` MUST NOT replace its existing timing values; if it has no
existing valid configuration, it MUST treat the JOIN as incomplete and restart
its normal JOIN procedure.

## Refresh rules

When the Relay accepts a refresh-eligible packet from the registered endpoint,
it MUST set:

```text
deadline = receive_monotonic_time + L
```

Only these incoming packet classes refresh an established membership:

1. `KEEPALIVE` from the registered endpoint.
2. An authenticated, valid `CODEC_CONFIG` from the registered endpoint.
3. An authenticated, valid `PTT_ON`, `PTT_REQUEST`, or `PTT_OFF` from the
   registered endpoint, whether the floor decision is grant or deny.
4. `AUDIO` or `FEC` accepted from the registered endpoint while it holds the
   corresponding current talk grant and, where applicable, matches the
   announced media nonce base.

A successful `JOIN` establishes the first deadline rather than refreshing a
pre-existing membership. `AUTH_*`, `IDENTITY_*`, `SERVICE_ADMISSION_*`,
`KEY_EXCHANGE`, malformed or unauthorized packets, `PING`, and `PONG` MUST NOT
refresh membership unless a future extension explicitly updates this list.

## Client cadence

While a client considers its membership established, it MUST transmit at least
one refresh-eligible packet in every interval `K`. When it has not transmitted
another refresh-eligible packet during that interval, it MUST transmit an empty
`KEEPALIVE`. A client MAY suppress a redundant `KEEPALIVE` while it is already
sending valid `AUDIO`, `FEC`, codec configuration, or PTT control at that
cadence. `PING` does not satisfy this requirement.

Clients SHOULD use a monotonic local scheduler and SHOULD send before the end
of each interval rather than scheduling exactly at its boundary. They MUST NOT
infer continued membership merely because a local `KEEPALIVE` was transmitted;
the Relay remains authoritative and may expire the membership when no eligible
packet arrives before its deadline.

## PING/PONG separation

`PING`/`PONG` measure reachability and RTT only. Their recommended cadence may
be shorter or longer than `K`, and backoff after missing `PONG` responses does
not alter the required membership refresh cadence. Conversely, a recent
`KEEPALIVE` does not constitute a successful RTT measurement.

## Required interoperability cases

Implementations MUST test at least the following cases:

1. The default `SERVER_CONFIG` encodes `L = 30` and `K = 10` in the eight-byte
   payload.
2. A newly joined client uses the 5-second bootstrap cadence until valid server
   configuration arrives.
3. Idle `KEEPALIVE` at or below `K` refreshes the Relay deadline.
4. Accepted active-talk `AUDIO`/`FEC` refreshes the deadline without redundant
   keepalive traffic.
5. `PING`/`PONG` alone does not refresh membership, so the endpoint expires at
   `L` and an active talk receives `MEMBERSHIP_TIMEOUT`.
6. A Relay rejects `SERVER_CONFIG` timing values outside the specified ranges
   or with `K > floor(L / 3)`.
7. A policy reload does not silently shorten the membership snapshot of an
   already joined endpoint.
