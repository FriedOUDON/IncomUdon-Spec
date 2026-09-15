# Datagram Size and MTU Policy

## Scope

This policy prevents IP fragmentation for real-time IncomUdon UDP traffic. It
applies to every Version 1 UDP datagram emitted by clients and Relays,
including media, FEC, floor control, authentication, and diagnostics packets.

`MAX_UDP_DATAGRAM_BYTES` is the size of the complete UDP payload: the
IncomUdon fixed/security headers, encrypted or plaintext payload, and any
authentication tag. It excludes the UDP and IP headers.

## Normative limits

| Constant | Value | Meaning |
|---|---:|---|
| `MAX_UDP_DATAGRAM_BYTES` | 1200 bytes | Maximum complete UDP payload emitted or forwarded by a Version 1 implementation. |
| `MAX_MEDIA_FRAME_BYTES` | 4096 bytes | Receiver-side codec/FEC validation ceiling. It is not a permitted transmit size. |
| `MAX_TRANSMIT_MEDIA_FRAME_BYTES` | 1131 bytes | Maximum codec-frame size a sender may place into AUDIO or FEC v2. |

The 1200-byte datagram limit leaves room for IPv6 and UDP headers below the
IPv6 minimum link MTU of 1280 bytes. It is deliberately lower than a typical
1500-byte Ethernet MTU so it remains practical across IPv4, IPv6, VPN, mobile,
and tunneled paths.

A sender MUST NOT create a datagram larger than
`MAX_UDP_DATAGRAM_BYTES`. A Relay MUST discard and MUST NOT forward an
incoming datagram larger than this limit. Implementations MAY count and
locally report such drops, but MUST NOT log media content or secret material.

Directory UDP v3 uses this same 1200-byte ceiling. Its dedicated transport is
raw JSON; its media-port transport includes a five-byte carrier, so the inner
JSON is limited to 1195 bytes. Directory fragmentation is an application-level
mechanism and MUST NOT rely on IP fragmentation.

## Media and FEC budget

For AES-GCM v2 AUDIO, the largest relevant envelope is:

```text
36-byte IncomUdon AES-GCM v2 media security header
+ 2-byte AUDIO sequence
+ 1131-byte codec frame
+ 16-byte AES-GCM tag
= 1185 bytes
```

For an AES-GCM v2 FEC v2 parity packet with the maximum block size of six, the
largest envelope is:

```text
36-byte IncomUdon AES-GCM v2 media security header
+ 17-byte FEC v2 metadata (5-byte prefix + six u16 lengths)
+ 1131-byte parity data
+ 16-byte AES-GCM tag
= 1200 bytes
```

Therefore a sender using FEC v2 MUST cap every source codec frame at
`MAX_TRANSMIT_MEDIA_FRAME_BYTES`; the parity data then fits without IP
fragmentation. The receiver-side `MAX_MEDIA_FRAME_BYTES` ceiling remains
larger only to bound decoder input and compatibility parsing. It MUST NOT be
used as an outbound allocation or transmission target.

## Fragmentation and path-MTU behavior

Application-layer media fragmentation and reassembly are not part of Version
1. A sender MUST drop an over-limit frame rather than split it into multiple
UDP datagrams. It MUST NOT retain an over-limit frame for later transmission.

When platform APIs expose a Path MTU Discovery or Don't Fragment option, an
implementation SHOULD request it. A local send failure that indicates an MTU
problem, including `EMSGSIZE` or its platform equivalent, MUST be treated as a
real-time drop: the implementation MUST increment diagnostics, discard the
current datagram, and continue with subsequent live frames. It MUST NOT retry
or queue that stale media indefinitely.

The 1200-byte limit reduces fragmentation risk but cannot guarantee delivery:
encapsulation overhead, broken ICMP delivery, OS policies, congestion, and
normal UDP loss remain possible. Implementations MUST continue to use bounded
queues and the playout resynchronization rules in `playout.md`.

## FEC pacing

FEC v2 emits P and Q after a source block. The two parity datagrams MAY be
sent consecutively, but they count toward the normal bounded outbound queue
and stale-frame policy. A sender MUST NOT delay newer speech merely to retain
old parity, and MUST NOT exceed the datagram limit for either parity packet.

## Required interoperability cases

1. An AES-GCM v2 AUDIO frame of 1131 bytes produces a datagram no larger than
   1185 bytes.
2. A six-frame AES-GCM v2 FEC v2 parity datagram with 1131-byte parity data is
   exactly 1200 bytes and is accepted for transmission.
3. A 1132-byte codec frame or FEC parity source is rejected before network
   transmission.
4. A Relay receives a datagram larger than 1200 bytes and does not forward it.
5. An MTU-related local send error increments diagnostics and does not cause
   delayed retransmission of that media frame.
