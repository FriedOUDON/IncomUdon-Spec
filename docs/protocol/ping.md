# Ping and Liveness

`PING` (`0x0E`) and `PONG` (`0x0F`) provide endpoint liveness and round-trip
measurement over the Relay audio UDP port.

## Payload

The payload is an opaque eight-byte nonce. The Relay returns the same nonce
only to the registered source endpoint.

## Timing

- Idle clients SHOULD ping every 10 seconds.
- A client that is sending or receiving media SHOULD ping every 5 seconds.
- After a timeout, retry intervals SHOULD increase to avoid unnecessary load.
- Ping does not substitute for `KEEPALIVE`, which maintains membership.

A client MUST calculate round-trip time from a monotonic local clock and MUST
not expose remote endpoint addresses in normal user-facing logs.
