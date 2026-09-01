# Forward Error Correction

IncomUdon supports optional forward error correction (FEC) for media traffic.
FEC packets are associated with a sender and media sequence range and are
identified by packet type `0x0C`.

## Requirements

- FEC is optional and policy-controlled.
- FEC data MUST be bounded; a receiver must not wait indefinitely for parity.
- Recovered frames are useful only while still inside the receiver jitter
  window. Late recovery MUST be discarded.
- A FEC implementation MUST preserve the original media ordering and MUST NOT
  expand latency without a configured jitter-buffer limit.

The Reed-Solomon parameters, parity payload layout, and reference recovery
vectors are pending extraction from the Relay implementation and will be
published before a stable specification tag.
