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

## Multi-Talker Mixing

When `SERVER_CONFIG.multi_talk_enabled` is true, a receiver MUST be able to
render every Relay-authorized active talker concurrently. A talker is identified
by the tuple `(channel_id, sender_id)`. Decoder, jitter-buffer, FEC, playout,
and resampler state MUST remain independent for that tuple.

A receiver MUST NOT wait for one talker to reach a playout deadline before
rendering another talker. Each talker enters and leaves the output mix only at
its own scheduled playout intervals. A `TALK_RELEASE`, source-limit drop, or
playout resynchronization for one talker MUST NOT flush, reset, delay, or
otherwise interrupt another talker's state.

### Source selection and limits

The standard `MAX_MIX_TALKERS` is 16. Relays in an interoperable Version 1
deployment MUST advertise no more than 16 active talkers, and receivers MUST
support mixing at least 16 concurrent non-muted talkers. A receiver MAY impose
a lower local limit only when resource constrained, but it MUST expose the
resulting source-limit drops in diagnostics and SHOULD make that limitation
visible to the user.

A source contributes to the mix when it has a renderable scheduled interval:
ordinary media, timely FEC recovery, or PLC output. Locally muted sources,
including self-ID mute, MUST NOT contribute. The current contributing-source
count is `N`. A receiver renders silence when `N = 0`.

### Common render clock and resampling

A receiver MUST convert every contributing mono decoder output to one local
common mix sample rate before summation. A stateful resampler, when needed,
MUST be maintained per talker and MUST NOT be shared between talkers. Device
output-rate conversion occurs after the common-rate mix. Implementations MAY
duplicate the final mono mix to device output channels; spatial placement is
outside this protocol.

The common render clock is local. Receivers MUST NOT attempt to synchronize
talker timelines with one another or add delay beyond the per-talker bounds in
order to align their starts. This preserves the 80 ms target and 120 ms maximum
playout delay defined above.

### Gain and limiter

For every common-rate output sample, a receiver computes the per-source target
gain as:

```text
gain(N) = 1 / sqrt(N)
```

The mixed normalized sample is the sum of every contributing source sample
multiplied by its current gain. When `N` changes, all affected source gains
MUST transition linearly from their previous value to the new target over
`MIX_GAIN_TRANSITION_MS = 20 ms`. A newly contributing source starts at zero
and ramps to its target; a source leaving the mix ramps to zero when enough
local samples remain. A receiver MAY complete an unavoidable final release
immediately rather than retain stale speech solely for a gain ramp.

The mixer MUST use an accumulator that cannot wrap for the supported source
limit. Before conversion to a device sample format, it MUST apply a final peak
limiter. The baseline interoperable limiter is:

```text
limited(x) = clamp(x, -1.0, +1.0)
```

An implementation MAY use a soft limiter instead, provided that its output
never exceeds the normalized range and that it remains linear for
`abs(x) <= 0.95`. User-configured master speaker gain is applied after the
protocol mix and before the final device conversion; it MUST also be covered by
peak protection.

See `../../test-vectors/multi-talker-mixing-v1.json` for canonical gain,
limiting, and source-limit cases.

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

On `TALK_RELEASE` with reason `PREEMPTED`, a receiver MUST fade the preempted
talker from the mix in no more than 20 ms, discard all unrendered jitter-buffer,
FEC, and decoder ordering state immediately, and suppress that talker's
end-of-talk cue. It MUST NOT delay the replacement talker to drain preempted
speech.

On any other `TALK_RELEASE`, a receiver MUST render only frames that remain
eligible under their scheduled deadlines. It MUST then discard residual
jitter-buffer, FEC, and decoder ordering state for that talker. It MUST NOT
keep a released
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
