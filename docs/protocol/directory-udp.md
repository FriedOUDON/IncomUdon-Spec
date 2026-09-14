# Directory UDP Protocol

The Directory service is an optional UDP control-plane protocol. It distributes
channel names, speaker names, and current participant metadata. It never
carries channel passwords, media keys, OIDC tokens, or endpoint addresses.

Directory is disabled by default. When enabled, **Directory UDP v2 with
channel-password-derived keys is the primary mode**. It exposes metadata only
for a channel whose password is already configured locally. Directory UDP v1
with a separately provisioned shared PSK remains an explicit compatibility and
administrative mode; it is not the default for new deployments.

## Limits and defaults

- Maximum Directory datagram: 1200 bytes, including its JSON envelope.
- Maximum channels/speakers/participants/clients: 256/4096/128/64.
- Default publish interval: 30 seconds.
- Default snapshot and dynamic-client TTL: 90 seconds.
- Requests and registrations may be valid for at most 30 seconds.
- Directory MUST be explicitly enabled. An enabled implementation SHOULD use
  `channel-password` mode unless it has an administrative requirement for a
  shared cross-channel directory.

## Authentication modes

| Mode | Version | Status | Scope |
|---|---:|---|---|
| `off` | - | Default | Directory traffic is not processed. |
| `channel-password` | 2 | Primary | One configured channel per request, authenticated with the existing channel password derivation. |
| `shared-psk` | 1 | Explicit compatibility/administrative mode | One separately provisioned directory PSK may expose configured cross-channel metadata. |

A Relay MUST NOT silently fall back from `channel-password` to `shared-psk`.
A client MUST select the same mode as its Relay deployment. The two modes use
different envelopes, keys, nonces, and replay domains.

## Directory UDP v2: channel-password mode

### Envelope

Each UDP datagram is UTF-8 JSON conforming to
`schemas/directory-v2.schema.json`.

```json
{
  "v": 2,
  "type": "request",
  "channelId": 111,
  "epoch": "base64url-no-padding",
  "sequence": 1,
  "expiresAt": 1700000010,
  "ciphertext": "base64url-no-padding"
}
```

Allowed types are `snapshot`, `participants`, `request`, `register`, and
`heartbeat`. `channelId` is an unsigned 32-bit channel identifier. It is
plaintext only so the receiver can select the candidate key; it is included in
AAD and is therefore authenticated. Sequence MUST be nonzero and monotonically
increase in the replay domain below.

### Key derivation and AEAD

The channel credential and `password_key` derivation in `security.md` are
normative. A Relay and client MUST derive Directory keys from `password_key`,
never from the raw credential text. `argon2id-v1` passphrase derivation or the
explicit `raw-secret-v1` input form MUST be completed before Directory key
derivation begins.

```text
directory_channel_key = HKDF-SHA-256(
  password_key, empty_salt,
  "incomudon-directory-channel-v2", 32)

directory_c2r_key = HKDF-SHA-256(
  directory_channel_key, empty_salt,
  "incomudon-directory-channel-v2 client-to-relay", 32)

directory_r2c_key = HKDF-SHA-256(
  directory_channel_key, empty_salt,
  "incomudon-directory-channel-v2 relay-to-client", 32)

directory_epoch_key = HKDF-SHA-256(
  directional_key, epoch,
  "incomudon-directory-envelope-v2", 32)
```

`directional_key` is `directory_c2r_key` for `request`, `register`, and
`heartbeat`; it is `directory_r2c_key` for `snapshot` and `participants`.
Directional keys prevent nonce collisions between client and Relay traffic.
Each sender MUST choose a fresh random 16-byte epoch before its first message
and whenever its sequence state is reset. Sequence increases monotonically per
`direction, channelId, epoch` replay domain.

AES-256-GCM encrypts the JSON payload. The nonce is:

```text
nonce = "IDP2" || U64BE(sequence)
```

AAD is the concatenation of:

```text
"IncomUdon Directory Envelope AAD v2\0"
U8(v) || U8(len(type)) || type || U32BE(channelId) || epoch ||
U64BE(sequence) || U64BE(expiresAt)
```

Receivers MUST enforce the exact envelope schema, channel ID range, epoch
size, expiration, allowed direction/type combination, AEAD authentication tag,
and replay sequence before accepting a payload. A Relay MUST bind dynamic
registrations to the observed UDP source address, never to an address in a
payload.

### Payload scope

The v2 payload forms are unchanged from v1, except that every accepted payload
is scoped to the authenticated envelope `channelId`.

- `snapshot` contains at most the corresponding channel row and its resolved
  speaker rows:

  ```json
  {"version":2,"revision":"sha256 hex","issuedAt":0,"expiresAt":0,
   "channels":[{"channelId":111,"name":"Operations"}],
   "speakers":[{"channelId":111,"senderId":1002,"name":"Unit A"}]}
  ```

  A speaker row with `channelId` set to the string `all` in source CSV input
  is resolved by the Relay into the requested channel; a channel-specific row
  wins. Source CSV field definitions and validation rules are in
  `../configuration/relay-csv.md`.
- `participants` contains only participants for the corresponding channel,
  each with `channelId`, `senderId`, `lastSeenAt`, and `talking`.
- `request` contains `version`, `issuedAt`, and `expiresAt`.
- `register` and `heartbeat` additionally contain a base64url 16-byte
  `instanceId`.

A Relay MUST NOT return directory data for another channel in a v2 response.
A receiver MUST reject a decrypted record whose `channelId`, when present,
differs from the envelope channel ID.

This design means that a client cannot obtain a channel name, speaker mapping,
or participant list without knowing that channel's password. A multi-channel
client sends independent Directory requests for each configured channel.

### Password strength

Directory v2 does not increase the credential trust boundary: anyone who
knows a channel credential can already derive the corresponding media and
authenticated control keys. Encrypted JSON has predictable structure, so weak
passphrases MUST NOT be treated as confidential even with Argon2id. Empty
credentials are rejected for Directory v2 as required by `security.md`.

See `../../test-vectors/directory-channel-v2.json` for a deterministic v2
request envelope.

## Directory UDP v1: shared-PSK compatibility mode

Directory v1 is retained for deployments that deliberately provision a
separate 32-byte base64url Directory PSK and need a cross-channel
administrative directory. Its envelope conforms to
`schemas/directory-v1.schema.json` and includes `keyId`. It is selected only
by explicit `shared-psk` configuration.

```text
directory_key = HMAC-SHA-256(psk,
  "IncomUdon directory PSK v1 relay-to-pwa" || epoch)
nonce = "IDP1" || U64BE(sequence)
```

Its AAD is the concatenation of:

```text
"IncomUdon Directory Envelope AAD v1\0"
U8(v) || U8(len(type)) || type || U8(len(keyId)) || keyId || epoch ||
U64BE(sequence) || U64BE(expiresAt)
```

The v1 `snapshot` may contain configured data across channels. Its use is
therefore appropriate only when that visibility is intended. See
`../../test-vectors/directory-psk-v1.json` for a deterministic v1 request.
