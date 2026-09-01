# Ping and Liveness

`PING` (`0x0E`) and `PONG` (`0x0F`) measure Relay UDP endpoint liveness.
Their payload is exactly eight opaque bytes.

The Relay replies with `PONG` only when the source address is already
registered by `JOIN` for the same channel and sender ID. It echoes the eight
payload bytes to that same endpoint and MUST NOT broadcast or reflect a ping
from an unknown endpoint.

Recommended client intervals:

- idle: every 10 seconds;
- active send or receive: every 5 seconds;
- no response: back off beyond the normal interval.

RTT MUST use a local monotonic clock. Normal client UI logs MUST NOT expose
Relay IP addresses merely because address fallback occurred.
