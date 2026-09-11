# Real-Time Playout

## Scope

This document defines receiver playout timing, jitter buffering, late-media
discard, packet-loss concealment (PLC), and the deadline for external and
Opus in-band FEC recovery. It applies independently to every active sender ID
in a channel.

The objective is push-to-talk real-time behavior: clients prioritize current
speech over complete delivery of stale speech.

## Standard timing

| Parameter | Standard value |
|---|---:|
| `TARGET_PLAYOUT_DELAY_MS` | 80 ms |
| `MAX_PLAYOUT_DELAY_MS` | 120 ms |
| Nominal media interval | 20 ms |

`TARGET_PLAYOUT_DELAY_MS` is the receiver's intended total playout delay. It
is not an additional FEC wait period. A receiver normally starts a sender's
playout timeline after accumulating approximately 80 ms of usable media or
an equivalent bounded startup interval.

`MAX_PLAYOUT_DELAY_MS` is the hard bound for accumulated receiver delay. It
allows short network variation but does not permit old speech to build up.

## Per-sender playout timeline

A receiver MUST maintain independent decoder, jitter-buffer, FEC, and playout
state for every sender ID. For each 20 ms media sequence interval, it MUST
assign a fixed scheduled playout time.

The scheduled playout time is the frame's recovery deadline:

1. If ordinary media is available by the deadline, render it.
2. Otherwise, if a complete external-FEC recovery is available by the
   deadline, render the recovered frame.
3. Otherwise, if an eligible one-frame Opus in-band FEC recovery is available
   by the deadline, render that reconstruction.
4. Otherwise, apply the codec's PLC behavior or render silence, then continue
   with the next scheduled interval.

A receiver MUST NOT postpone later scheduled intervals to wait for a missing
or late frame. It MUST NOT render a frame after its deadline, and MUST NOT
render an interval twice when an original or FEC-recovered copy arrives late.

## Bounded delay and resynchronization

If queued media or scheduled playout would cause effective playout delay to
exceed `MAX_PLAYOUT_DELAY_MS`, a receiver MUST discard enough oldest unrendered
media to return near `TARGET_PLAYOUT_DELAY_MS`. It MUST preserve ordering among
frames that remain eligible for playback.

This resynchronization rule applies after normal jitter, packet loss, delayed
FEC parity, page/UI stalls, audio-device stalls, and any other source of
receiver backlog. A client MUST favor discarding stale audio over expanding
playout delay without bound.

## FEC deadline behavior

Opus in-band FEC requires the following Opus packet. A receiver therefore
retains one nominal 20 ms interval within the normal 80 ms playout target; it
MUST NOT add a separate 20 ms delay beyond that target solely for in-band FEC.

External parity FEC may require later packets from a six-frame block. It is
opportunistic under the standard low-delay policy: a receiver MAY use an
external-FEC result only if the required data and parity arrive before the
missing frame's scheduled playout deadline. It MUST NOT extend the delay past
that deadline merely to wait for parity.

When both FEC mechanisms are enabled, a complete external recovery available
by the deadline takes priority. Otherwise, an eligible Opus in-band recovery
may be rendered. A later external result MUST be discarded if that interval
was already rendered.

## Release and state cleanup

On `TALK_RELEASE`, a receiver MUST render only frames that remain eligible
under their scheduled deadlines. It MUST then discard residual jitter-buffer,
FEC, and decoder ordering state for that talker. It MUST NOT keep a released
talker alive merely to await late parity.

## Diagnostics

Debug instrumentation requirements and the common snapshot schema are defined
in `diagnostics.md`. Implementations SHOULD expose, per sender ID:

- target and effective playout delay;
- current jitter-buffer depth;
- late-frame and stale-frame discard counts;
- PLC count;
- external-FEC and Opus in-band FEC recovery counts;
- FEC results discarded after their playout deadline; and
- resynchronization count and most recent reason.
