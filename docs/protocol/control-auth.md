# Control Authentication v1

## Scope and trust model

Control Authentication v1 protects Version 1 Relay control traffic against
network parties that do not know the channel password. It authenticates
client-to-Relay control requests and Relay-originated control packets. A
Relay re-authenticates verified `CODEC_CONFIG` payloads before sending them
downstream; it never forwards the client-authenticated datagram byte-for-byte.
Control Authentication is separate from AES-GCM v2 media encryption.

This is **group authentication**. Every client that knows a channel password
can derive the same control key. Consequently, it does not identify individual
members and cannot prevent an authorized group member from impersonating
another sender ID or forging a Relay-looking control packet. Deployments that
require per-user identity or cryptographic proof of Relay origin require
separate per-client credentials and a Relay signing-key extension; those are
outside Control Authentication v1.

Control Authentication v1 prevents off-channel spoofing, control-packet
modification, and replay within an authenticated session. It does not prevent
UDP jamming, packet dropping, bandwidth exhaustion, or actions by an
authorized group member.

## Password and key derivation

Derive `password_key` from the configured channel credential exactly as
specified in `security.md`. `argon2id-v1` is the default for a passphrase;
`raw-secret-v1` is available only through the explicit `secret:` input form.
The removed `sha256:` and bare-64-hex normalization forms MUST NOT be accepted.
The credential kind is selected from local configuration before control traffic
is processed and is not conveyed in a control packet.

Derive separate keys from the same `password_key`:

```text
media_key = HKDF-SHA-256(password_key, empty_salt,
                         "incomudon-session-aesgcm-v2", 32)

control_key = HKDF-SHA-256(password_key, empty_salt,
                           "incomudon-control-auth-v1", 32)
```

`media_key` remains the AES-GCM v2 media key. `control_key` is used only for
HMAC control authentication. Derived keys MUST NOT be included in packets,
configuration exports, diagnostics, or logs. Clients may store the configured
password according to their local profile-security policy, but MUST derive keys
only in process memory when establishing a session.

Key separation means possession of a stored `control_key` does not directly
provide `media_key`. `argon2id-v1` increases the cost of offline passphrase
guessing if an authenticated packet is disclosed, but does not eliminate the
risk of weak passwords. Secure deployments SHOULD use a randomly generated
256-bit channel secret represented as `secret:` followed by 64 hexadecimal
characters.

## Packet authentication format

A Control Authentication v1 packet uses the normal 28-byte security header:

| Header field | Requirement |
|---|---|
| `header_len` | `28` |
| `flags` | `CONTROL_AUTH_V1` (`0x0002`) set; AES-GCM v2 media AAD flag is clear |
| `nonce` | control-session nonce defined below |
| wire `key_id` (`control_key_id`) | non-zero Control Key ID |
| payload | plaintext control payload |
| trailing tag | first 16 bytes of the HMAC-SHA-256 result |

The tag is:

```text
HMAC-SHA-256(
  control_key,
  "incomudon-control-auth-v1\0" || packet_bytes[0:28] || payload
)[0:16]
```

The fixed header and security header are authenticated exactly as encoded. Tag
comparison MUST be constant-time. A receiver MUST reject a packet with an
unknown Control Key ID, missing flag, invalid header length, zero nonce, or
invalid tag before changing membership, floor-control, codec, or liveness
state.

`CONTROL_AUTH_V1` is not media encryption. Audio and FEC keep their existing
AES-GCM v2 packet construction, `media_key_id`, and tag rules. The
`control_key_id` in this packet authenticates control only; it neither selects
a media key nor forms part of an AES-GCM v2 media replay domain.

## Authenticated join and replay protection

A client MUST complete the following handshake before the Relay registers it
or forwards its media:

1. Send authenticated `AUTH_HELLO` (`0x10`) with an empty payload.
2. Receive authenticated `AUTH_CHALLENGE` (`0x11`) from the Relay.
3. When Identity Admission is enabled, complete `IDENTITY_BEGIN`,
   `IDENTITY_CHALLENGE`, and `IDENTITY_PROOF` before JOIN. When Managed Service
   Admission is enabled for a service endpoint, complete
   `SERVICE_ADMISSION_BEGIN`, `SERVICE_ADMISSION_CHALLENGE`, and
   `SERVICE_ADMISSION_PROOF` instead.
4. Send authenticated `JOIN` containing the challenge expiry and cookie.
5. Receive normal authenticated Relay state/configuration packets.

Identity Admission is fully optional and defaults to off. Its additional
admission flow is defined in `identity-admission.md`. Managed Service Admission
is optional and defined in `../extensions/management/service-admission.md`.

A client chooses a cryptographically random, non-zero 32-bit
`client_session_id`. It MUST regenerate the value if its CSPRNG returns zero.
The high 32 bits of every client-originated Control Authentication v1 nonce are
this session ID; the low 32 bits are its control counter. This nonce is an
authenticated replay identifier, not an AES-GCM media nonce. In particular,
the `AUTH_HELLO` counter zero then cannot form the prohibited all-zero nonce.

For one `client_session_id`, `AUTH_HELLO` MUST use counter zero. Every
subsequent client-originated Control Authentication v1 packet MUST consume the
next previously unused counter value. The counter MUST increase by exactly one
when the client constructs another authenticated control packet, including
pre-JOIN admission packets and post-JOIN traffic, and MUST NOT be reset or
reused within that session. A dropped packet still consumes its counter.

`JOIN` uses counter one only when no authenticated pre-JOIN exchange occurs.
When Identity Admission, Managed Service Admission, or a future authenticated
pre-JOIN extension is used, `JOIN` MUST use the next unused counter. Thus a
fresh Identity or Managed Service Admission flow uses client-to-Relay counters
zero for `AUTH_HELLO`, one for its `*_BEGIN`, two for its `*_PROOF`, and three
for `JOIN`.

A client MUST start a new authenticated handshake with a fresh random
`client_session_id` before allocating counter `2^32`, after abandoning an
incomplete pre-JOIN attempt, or when retrying `AUTH_HELLO`. It MUST NOT restart
at counter zero under an existing session ID.

`AUTH_CHALLENGE` has this payload:

| Offset | Bytes | Field |
|---:|---:|---|
| 0 | 4 | expiry, Unix seconds (`u32`, big-endian) |
| 4 | 16 | opaque Relay cookie |

The authenticated `JOIN` payload is byte-identical to the received challenge
payload. The Relay cookie is the first 16 bytes of:

```text
HMAC-SHA-256(
  relay_cookie_secret,
  "incomudon-control-cookie-v1\0" ||
  source_ip_16 || U16BE(source_port) ||
  U32BE(channel_id) || U32BE(sender_id) || U32BE(control_key_id) ||
  U32BE(client_session_id) || U32BE(expiry)
)[0:16]
```

`source_ip_16` is the 16-byte IPv6 address. IPv4 source addresses MUST be
represented as IPv4-mapped IPv6 addresses. Cookies MUST expire within 30
seconds, be single-use, and be checked against the received source IP and
port. The Relay cookie secret is Relay-local random key material and MUST NOT
be exposed to clients.

After verifying `AUTH_HELLO` with counter zero, the Relay MUST create a
provisional bounded 64-counter replay window keyed by the observed source IP
and port, channel ID, sender ID, Control Key ID, and `client_session_id`. It
MUST record counter zero and apply that same window to every authenticated
client-to-Relay packet before JOIN. The provisional state MUST expire no later
than the associated cookie expiry and MUST be bounded against unauthenticated
state exhaustion.

On successful JOIN, the Relay MUST promote the exact provisional replay window
to the authenticated peer session without clearing it. It accepts a counter at
most once, tolerates limited UDP reordering within the 64-counter window, and
rejects a different session ID or counters outside the window. This preserves
replay protection for `AUTH_HELLO`, any admission packets, and JOIN itself. A
source-address change requires a new authenticated handshake.

The Relay uses its own cryptographically random, non-zero 32-bit instance ID
in the high 32 bits of nonce values for Relay-originated control packets. It
MUST regenerate the instance ID if its CSPRNG returns zero. Relay-originated
nonces use a monotonically increasing low 32-bit counter. Clients maintain a
bounded replay window for each Relay instance ID.

A Relay MUST NOT allow its low 32-bit control counter to wrap. Counter
`0xffffffff` is the final value that MAY be allocated in one Relay nonce
domain. Before allocating another Relay-originated authenticated control
packet, the Relay MUST atomically begin a new Relay nonce domain: it selects a
fresh CSPRNG-generated non-zero `relay_instance_id` different from the active
one, resets the low counter to zero, and allocates the next nonce from that new
domain. It MUST NOT allocate another nonce under the retired instance ID. An
in-process rollover MUST NOT reuse an earlier Relay instance ID. If the Relay
cannot obtain a new usable instance ID, it MUST fail closed for
Relay-originated authenticated control rather than reuse or wrap a nonce.

The rollover is self-describing in the high 32 bits of the authenticated
control nonce and does not require client reauthentication, membership changes,
or a Relay process restart. A Relay process start or restart likewise begins a
new Relay nonce domain with a fresh non-zero CSPRNG-generated instance ID and
low counter zero. On a valid Relay-originated authenticated control packet with
a previously unseen `relay_instance_id`, a client MUST initialize a separate
bounded replay window for that instance ID; it MUST NOT merge counters or replay
state with another Relay instance ID. A client MAY evict inactive Relay domains
to maintain its bounded state. After accepting a new Relay instance ID as
active, a client MUST mark the previously active domain retired and MUST NOT let
a later packet from that retired instance ID replace its active Relay nonce
domain or roll back control-derived state.

## Relay-reauthenticated CODEC_CONFIG

After verifying a client-originated authenticated `CODEC_CONFIG`, the Relay
MUST cache its exact verified 19-byte payload, original `channel_id` and
`sender_id`, and verified `control_key_id`. When forwarding that configuration
to a receiver, including active-talker synchronization after a new JOIN, the
Relay MUST construct a new Relay-originated Control Authentication v1 packet.
It MUST NOT forward the client datagram, client control nonce, fixed-header
`seq`, or client HMAC tag byte-for-byte.

The reauthenticated downstream packet MUST use the original `channel_id`,
original talker `sender_id`, packet type `CODEC_CONFIG`, the exact cached
payload, the verified `control_key_id`, `header_len = 28`, and
`CONTROL_AUTH_V1`. It MUST use a fresh unused Relay control nonce and a newly
computed HMAC tag over the reconstructed fixed and security headers plus the
cached payload. The Relay MUST assign a fresh downstream fixed-header `seq`
as defined in `wire-format.md`. A cached configuration re-emitted to another
receiver or at a later time MUST consume another Relay counter and produce a
new tag even when its payload is unchanged.

A receiver MUST process the downstream configuration as Relay-originated
control: verify its HMAC and enforce replay protection only in the Relay
instance-ID nonce domain. It MUST NOT create a replay window for the original
client session ID. After successful verification, the receiver applies the
original talker `sender_id` and payload to codec and media-replay state as
specified in `control-packets.md`, `audio-codecs.md`, and `security.md`.
Reauthentication standardizes replay handling and cached delivery; because the
control key is group-shared, it does not provide cryptographic proof that only
the Relay could have created the packet.

## Authenticated packet classes

The following client-to-Relay packets MUST use Control Authentication v1 when
it is required for the channel:

- `AUTH_HELLO`
- `JOIN`
- `LEAVE`
- `KEEPALIVE`
- `PTT_ON`
- `PTT_REQUEST`
- `PTT_OFF`
- `CODEC_CONFIG`
- `PING`
- `IDENTITY_BEGIN`
- `IDENTITY_PROOF`
- `SERVICE_ADMISSION_BEGIN`
- `SERVICE_ADMISSION_PROOF`

The Relay MUST apply Control Authentication v1 to its generated `AUTH_CHALLENGE`,
`IDENTITY_CHALLENGE`, `IDENTITY_DENY`, `SERVICE_ADMISSION_CHALLENGE`,
`SERVICE_ADMISSION_DENY`, `TALK_GRANT`, `TALK_RELEASE`, `TALK_DENY`,
`SERVER_CONFIG`, `PONG`, and Relay-reauthenticated `CODEC_CONFIG` packets.
Before caching a CodecConfig, granting or releasing talk, registering a peer,
refreshing membership, or constructing downstream state from a client control
packet, the Relay MUST apply the current channel policy. When that policy
requires Control Authentication, it MUST verify authentication before taking any
of those actions. A packet rejected by the current policy MUST NOT refresh
membership. Membership refresh eligibility for accepted `KEEPALIVE`,
`CODEC_CONFIG`, and PTT control is defined in `membership-lease.md`; this also
includes valid unauthenticated control accepted for an `optional` unconfigured
legacy channel or an `off` channel.

For AES-GCM v2, the Relay
MUST cache the verified CodecConfig and reauthenticate it before forwarding the
configuration, including before forwarding `AUDIO` or `FEC` with that sender's
announced `media_nonce_base_96`; it MUST NOT forward media for an unconfigured
base. Audio and FEC packets are accepted only from an
authenticated peer session that currently holds a valid membership.

## Relay key provisioning and policy

The Relay reads channel-specific control keys from a protected key file. Each
entry has this CSV form:

```text
channel_id,key_id,control_key_base64
100,1,Base64Encoded32ByteControlKey
```

For a channel used by standard Control Authentication v1 clients, every
`control_key_base64` value MUST be the exact 32-byte `control_key` that those
clients derive from the configured channel credential and `channel_id` according
to [Password and key derivation](#password-and-key-derivation). The CSV
`key_id` field is the `control_key_id`: it selects the provisioned row, but is
not an input to the credential KDF or the Control Authentication HKDF. It is
distinct from the AES-GCM v2 `media_key_id`.

A trusted provisioning step MUST derive this value before it is placed in the
Relay key file. The Relay key file MUST contain only `control_key`, never the
channel credential, `password_key`, `media_key`, or another derived channel key.
Control Authentication v1 does not define an explicit independently provisioned
Control Authentication secret. An unrelated random 32-byte key is incompatible
with standard clients and MUST NOT be configured for such a channel. This
purpose-limited derived key is the Control Authentication dedicated key.

The Relay MUST protect this file with owner-only read access. Multiple entries for
a channel with distinct Key IDs support coordinated credential rotation.

Relay policy has three modes:

| Mode | Behavior |
|---|---|
| `required` | Reject channels without a configured Control Key and reject all unauthenticated controls. |
| `optional` | Require authentication for configured channels; permit legacy behavior for unconfigured channels. |
| `off` | Disable Control Authentication v1; development/compatibility only. |

Production deployments SHOULD use `required`. First-release secure clients
MUST use AES-GCM v2 media with Control Authentication v1. `no-crypto`,
`legacy-xor`, and legacy AES-GCM are weak compatibility modes and MUST NOT be
accepted by a Relay in `required` mode.

## Key rotation

A Relay MAY hold an old and new `control_key_id` simultaneously. Clients select
the configured Control Key ID and its matching channel credential in their
profile; the default `control_key_id` is `1`. Because `control_key_id` is not a
KDF input, changing only it while retaining a credential does not rotate
cryptographic key material.

A cryptographic Control Authentication key rotation MUST use a distinct channel
credential and a new Relay row containing the resulting derived `control_key`
under a new Key ID. The client MUST update both its credential and Key ID before
its new authenticated JOIN. This also rotates the credential-derived media and
Directory keys; Control Authentication v1 does not define a control-only
cryptographic rotation. The Relay SHOULD accept the old derived key only for a
bounded coordinated migration period.

## Diagnostics and test requirements

The common local snapshot format and redaction requirements are defined in
`diagnostics.md`.

Normal UI logs MUST NOT contain passwords, normalized hashes, derived keys,
control tags, cookies, or Relay cookie secrets. Debug logs MAY identify a
rejection reason class such as `invalid_tag`, `expired_cookie`, or
`replayed_nonce`, but MUST NOT include secret material.

Implementations MUST verify the deterministic `control-auth-v1.json` and
`relay-reauthenticated-codec-config-v1.json` vectors and run tests for valid
tags, tampering, wrong key IDs, incorrect channel or
sender IDs, expired/reused cookies, source-address cookie mismatch, replayed
nonces, provisional-window expiry, window promotion at JOIN, direct,
Identity Admission, and Managed Service Admission counter sequences, and
Relay-reauthenticated `CODEC_CONFIG` delivery with a fresh Relay nonce and tag,
and Relay counter exhaustion rollover without nonce reuse or counter wrap.
