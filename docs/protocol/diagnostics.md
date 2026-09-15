# Diagnostics and Debug Metrics v1

## Scope

Diagnostics and Debug Metrics v1 defines a local, per-session debug snapshot
for PWA, Qt, and Rust clients. It is intended for an explicit debug UI, a
support export, or developer tooling. It is not a Relay packet format and MUST
NOT alter real-time media scheduling.

A client exposes one snapshot per active profile or PWA slot. Multi-slot UIs
MUST NOT merge sender-specific counters into an unrelated slot.

## Privacy and performance requirements

Diagnostics are disabled by default and require an explicit local debug option.
A normal UI MUST NOT show them. When enabled, clients SHOULD refresh display
snapshots at most once per second, plus significant state transitions.

Implementations MUST collect counters without blocking audio capture, codec,
network receive, or playback callbacks. Atomic increments or bounded
single-producer event queues are preferred. They MUST NOT emit a console line
for every audio packet while normal diagnostics are enabled.

A snapshot, debug export, or normal log MUST NOT contain:

- channel passwords or password hashes;
- media keys, control keys, HMAC tags, AES-GCM tags, nonces, or cookies;
- raw audio/FEC payloads;
- Relay IP addresses, endpoint addresses, or local public addresses.

Sender IDs, codec IDs, codec modes, local durations, aggregate byte counts,
and Relay RTT are permitted.

## Snapshot format

The canonical JSON shape is defined by
`../../schemas/diagnostics-v1.schema.json`. `snapshot_monotonic_ms` uses a
process-local monotonic clock and MUST NOT be interpreted as wall-clock time.
Counters are non-negative and reset when the local session is recreated.

Platform-dependent fields that are optional and nullable in the canonical
schema MAY be omitted or set to `null` when unavailable; they MUST NOT be
fabricated. They are `tx.send_errors_mtu`,
`rx.talkers[*].output_underruns`, `rx.mixer.output_underruns`, and
`network.qos_applied`. For those fields, a reported zero means the client
observed zero events or a negative result, not that the metric was unavailable.
Values shown as `*_per_second` are calculated over the most recent completed
one-second interval. Counter values remain cumulative for the current session.

## Connection metrics

| Field | Meaning |
|---|---|
| `connection.state` | `disconnected`, `connecting`, `authenticating`, `connected`, `reconnecting`, or `failed` |
| `connection.control_auth_policy` | `required`, `optional`, `off`, or `unknown` |
| `connection.control_auth_state` | `disabled`, `hello_sent`, `challenge_received`, `joined`, or `failed` |
| `connection.relay_rtt_ms` | Last successful PING/PONG round-trip time; null if unavailable |
| `connection.last_relay_rx_age_ms` | Monotonic age since the latest Relay packet |
| `connection.reconnect_attempts` | Current session reconnect attempts |

No connection metric may expose the resolved Relay address.

## Transmit metrics

`tx` reports local microphone and source-file transmission processing.

| Field | Meaning |
|---|---|
| `ptt_state` | `idle`, `requesting`, `granted`, `denied`, or `releasing` |
| `frames_captured` | PCM frames captured from the microphone/source pipeline |
| `frames_encoded` | Frames successfully encoded for the configured uplink codec |
| `audio_packets_sent` / `audio_bytes_sent` | AUDIO packet totals |
| `frames_dropped_stale` | Frames dropped to keep real-time latency bounded |
| `frames_dropped_backpressure` | Frames dropped because send queue/socket backpressure was excessive |
| `frames_dropped_oversize` | Encoded/source frames rejected before packetization because they exceed the transmit media limit |
| `datagrams_dropped_oversize` | Fully built datagrams rejected because they exceed the UDP datagram limit |
| `send_errors_mtu` | Local UDP send failures that indicate an MTU/path-MTU error, when distinguishable; omit or null when the platform cannot classify the error |
| `send_errors` | All UDP send errors, including `send_errors_mtu` |
| `tx_queue_frames` / `tx_queue_age_ms` | Current queued-frame count and oldest-frame age |
| `audio_packets_per_second` / `audio_bytes_per_second` | Latest one-second transmit rates |

The `tx.fec` object records `enabled`, `blocks_emitted`,
`short_final_blocks_emitted`, `parity_p_packets_sent`,
`parity_q_packets_sent`, and `parity_bytes_sent`.

The `tx.opus_inband_fec` object records `enabled`, `expected_loss_percent`,
and `supported_bitrate`. `supported_bitrate` is true only for 12 or 16 kbps.

## Per-talker receive and playout metrics

`rx.talkers` contains a separate entry for each recently active sender ID. A
client MAY retain a released talker for up to 30 seconds for diagnosis, then
remove it. To prevent unbounded memory use, clients MUST cap retained entries;
the standard cap is 16. Additional talkers are aggregated in
`rx.overflow_talkers` without sender IDs.

| Field | Meaning |
|---|---|
| `sender_id` | Remote talker sender ID |
| `active` | Whether the Relay currently reports the sender as talking |
| `codec_id` / `codec_mode` | Last authenticated codec configuration; `codec_mode` is the exact `u32` codec mode/bitrate value |
| `last_packet_age_ms` | Monotonic age of the latest media packet |
| `audio_packets_received` / `audio_bytes_received` | AUDIO packet totals |
| `sequence_gaps` | Detected missing audio-sequence intervals |
| `packets_duplicate` / `packets_reordered` | Duplicate and reordering observations |
| `packets_late_dropped` | Media received after its playout deadline |
| `media_auth_failures` | AES-GCM authentication failures before media processing |
| `media_replay_rejections` | Authenticated media counters already seen in the replay window |
| `media_stale_counter_drops` | Media counters older than the 64-counter replay window |
| `media_unannounced_session_rejections` | AES-GCM v2 media whose nonce base lacks matching authenticated `CODEC_CONFIG` |
| `frames_rendered` | Frames accepted by the playback pipeline |
| `frames_plc` / `frames_silence` | Packet-loss concealment and explicit-silence intervals |
| `decode_errors` | Codec decode failures |
| `playout_target_ms` / `playout_effective_ms` | Configured target and current effective playout delay |
| `playout_queue_frames` | Current eligible playout queue depth |
| `playout_resyncs` | Stale-audio resynchronizations |
| `output_underruns` | Audio output stream underruns, when observable; omit or null when unavailable |

## Multi-Talker Mixer Metrics

`rx.mixer` describes the final local mix for the current channel session. It
contains no PCM samples, channel password material, endpoint address, or
speaker name. Locally muted sources are excluded from `active_sources`.

| Field | Meaning |
|---|---|
| `active_sources` | Current number of contributing sources after local mute policy, 0 through 16 |
| `maximum_sources` | Currently enforced local concurrent mix capacity, 1 through 16; it may be a fixed resource-constrained limit or a temporary runtime-degradation limit. |
| `mix_intervals_rendered` | Count of 20 ms source-mix intervals rendered |
| `gain_transition_ms` | Configured source-gain transition duration; standard value is 20 |
| `limiter_activations` | Final peak-limiter activation count |
| `source_limit_drops` | Talker intervals omitted because the local source limit was reached |
| `output_underruns` | Aggregate final-output stream underruns, when observable; omit or null when unavailable |

`rx.talkers[*].output_underruns`, when a platform can attribute it, remains a
per-talker observation. `rx.mixer.output_underruns` is the authoritative
aggregate output-device measure.

`external_fec` records `enabled`, `parity_packets_received`,
`blocks_completed`, `frames_recovered`, `blocks_unrecoverable`,
`invalid_packets`, `deadline_misses`, and `late_results_discarded`.

`opus_inband_fec` records `advertised_enabled`, `recovery_attempts`,
`frames_recovered`, `not_eligible_gaps`, and `late_results_discarded`.

A recovered frame increments exactly one recovery counter. A frame rendered
through PLC after failed recovery MUST NOT also increment `frames_recovered`.

## Control authentication metrics

`control_auth` aggregates local verification and Relay admission outcomes that
the client can observe.

| Field | Meaning |
|---|---|
| `authenticated_joins` | Successful local authenticated JOIN completions |
| `control_packets_accepted` | Valid authenticated control packets accepted locally |
| `invalid_tag_rejections` | Packets rejected for HMAC mismatch |
| `unknown_key_rejections` | Packets rejected for unknown Control Key ID |
| `cookie_rejections` | Challenge/Join failures attributable to cookie expiry or mismatch |
| `replay_rejections` | Packets rejected as replayed or outside the replay window |
| `authentication_failures` | Aggregate handshake/authentication failures |

The exact Relay rejection reason may be unavailable to a client. In that case,
clients MUST increment only the locally observable aggregate failure counter.

## Identity admission metrics

`identity_admission` records only local admission state and aggregate outcomes.
It MUST NOT contain a compact JWS, OIDC credential, ticket ID, issuer URL,
subject, public key, challenge, or channel authorization list.

| Field | Meaning |
|---|---|
| `mode` | `off`, `optional`, `required`, or `unknown` Relay identity-admission policy |
| `state` | `disabled`, `pending`, `admitted`, `denied`, `expired`, or `unknown` |
| `listen_permitted` / `talk_permitted` | Locally effective permissions; false when unavailable or denied |
| `ticket_lifetime_remaining_ms` | Remaining local ticket lifetime, or null when unavailable/disabled |
| `tickets_accepted` / `tickets_denied` | Admission result totals |
| `proof_failures` | Locally observed identity proof failures |
| `renewals` | Successful admission renewals |
| `admission_expirations` | Local admissions that expired during the session |

In `off` mode, `state` MUST be `disabled`, permission values MUST be false,
and all counters MUST be zero.

## Network and QoS metrics

The `network` object records `udp_packets_sent`, `udp_packets_received`,
`udp_bytes_sent`, `udp_bytes_received`, and their latest one-second rates. It
also records `rx_datagrams_rejected_oversize`: locally received datagrams
rejected before packet processing because they exceed the protocol MTU limit.
It records `qos_requested` and `qos_applied` when the platform exposes the
result of DSCP EF socket configuration. `qos_applied` is omitted or null when
the result cannot be observed.

## UI presentation

Debug UIs SHOULD show the following groups in this order:

1. connection and control authentication;
2. transmit;
3. receive/playout per talker;
4. FEC recovery;
5. network and QoS.

Normal values use the default text color. Warnings such as stale-frame drops,
PLC, decode failures, failed authentication, and output underruns SHOULD be
visually distinct. A diagnostic color alone MUST NOT be the only indication of
an error state.

## Validation requirements

Implementations MUST validate the sample
`../../test-vectors/diagnostics-v1.json`. Tests MUST cover counter increments,
per-talker separation, released-talker expiry, 16-talker retention cap,
missing-platform fields, and redaction of prohibited values.
