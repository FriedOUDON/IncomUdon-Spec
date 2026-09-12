# Control Authentication v1

## Scope and trust model

Control Authentication v1 protects Version 1 Relay control traffic against
network parties that do not know the channel password. It authenticates
client-to-Relay control requests and Relay-forwarded or Relay-generated
control packets. It is separate from AES-GCM v2 media encryption.

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
| `key_id` | non-zero Control Key ID |
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
AES-GCM v2 packet construction, key ID, and tag rules.

## Authenticated join and replay protection

A client MUST complete the following handshake before the Relay registers it
or forwards its media:

1. Send authenticated `AUTH_HELLO` (`0x10`) with an empty payload.
2. Receive authenticated `AUTH_CHALLENGE` (`0x11`) from the Relay.
3. When Identity Admission is enabled, complete `IDENTITY_BEGIN`,
   `IDENTITY_CHALLENGE`, and `IDENTITY_PROOF` before JOIN.
4. Send authenticated `JOIN` containing the challenge expiry and cookie.
5. Receive normal authenticated Relay state/configuration packets.

Identity Admission is fully optional and defaults to off. Its additional
admission flow is defined in `identity-admission.md`.

A client chooses a cryptographically random 32-bit `client_session_id`. The
high 32 bits of every client-originated control nonce are this session ID; the
low 32 bits are a monotonically increasing counter. `AUTH_HELLO` uses counter
zero and the authenticated `JOIN` uses counter one.

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
  U32BE(channel_id) || U32BE(sender_id) || U32BE(key_id) ||
  U32BE(client_session_id) || U32BE(expiry)
)[0:16]
```

`source_ip_16` is the 16-byte IPv6 address. IPv4 source addresses MUST be
represented as IPv4-mapped IPv6 addresses. Cookies MUST expire within 30
seconds, be single-use, and be checked against the received source IP and
port. The Relay cookie secret is Relay-local random key material and MUST NOT
be exposed to clients.

After successful JOIN, the Relay maintains a bounded 64-counter replay window
per authenticated peer session. It accepts a counter at most once, tolerates
limited UDP reordering within that window, and rejects packets from a different
session ID or counters outside the window. A source-address change requires a
new authenticated handshake.

The Relay uses its own cryptographically random 32-bit instance ID in the high
32 bits of nonce values for Relay-originated control packets, with a
monotonically increasing low 32-bit counter. Clients maintain a bounded replay
window for each Relay instance ID.

## Authenticated packet classes

The following client-to-Relay packets MUST use Control Authentication v1 when
it is required for the channel:

- `AUTH_HELLO`
- `JOIN`
- `LEAVE`
- `KEEPALIVE`
- `PTT_ON`
- `PTT_OFF`
- `CODEC_CONFIG`
- `PING`
- `IDENTITY_BEGIN`
- `IDENTITY_PROOF`

The Relay MUST apply Control Authentication v1 to its generated `AUTH_CHALLENGE`,
`IDENTITY_CHALLENGE`, `IDENTITY_DENY`, `TALK_GRANT`, `TALK_RELEASE`,
`TALK_DENY`, `SERVER_CONFIG`, and `PONG` packets.
It MUST verify authentication before caching a CodecConfig, granting/releasing
talk, registering a peer, refreshing membership, or forwarding an authenticated
client control packet. Audio and FEC packets are accepted only from an
authenticated peer session that currently holds a valid membership.

## Relay key provisioning and policy

The Relay reads channel-specific control keys from a protected key file. Each
entry has this CSV form:

```text
channel_id,key_id,control_key_base64
100,1,Base64Encoded32ByteControlKey
```

The Relay MUST protect this file with owner-only read access. It stores only
`control_key`, not the channel password or `media_key`. Multiple entries for a
channel with distinct Key IDs permit key rotation.

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

A Relay MAY hold an old and new Control Key ID simultaneously. Clients select
the configured Key ID in their profile; the default is `1`. The Relay SHOULD
accept the old key only for a bounded migration period. Changing a client's
Control Key ID requires a new authenticated JOIN.

## Diagnostics and test requirements

The common local snapshot format and redaction requirements are defined in
`diagnostics.md`.

Normal UI logs MUST NOT contain passwords, normalized hashes, derived keys,
control tags, cookies, or Relay cookie secrets. Debug logs MAY identify a
rejection reason class such as `invalid_tag`, `expired_cookie`, or
`replayed_nonce`, but MUST NOT include secret material.

Implementations MUST verify the deterministic `control-auth-v1.json` vector
and run tests for valid tags, tampering, wrong key IDs, incorrect channel or
sender IDs, expired/reused cookies, source-address cookie mismatch, replayed
nonces, and each Relay policy mode.
