# Directory UDP Protocol

The directory service is an optional UDP control-plane protocol. It distributes
channel names, speaker names, and current participant metadata. It never
carries channel passwords, audio keys, or endpoint addresses.

## Limits and defaults

- PSK: 32 base64url-decoded bytes.
- Epoch: 16 random bytes.
- Maximum Relay datagram: 1200 bytes.
- Maximum channels/speakers/participants/clients: 256/4096/128/64.
- Default publish interval: 30 seconds.
- Default snapshot and dynamic-client TTL: 90 seconds.
- Requests and registrations may be valid for at most 30 seconds.

## JSON envelope

Each UDP datagram is UTF-8 JSON conforming to
`schemas/directory-v1.schema.json`.

```json
{
  "v": 1,
  "type": "snapshot",
  "keyId": "pwa-1",
  "epoch": "base64url-no-padding",
  "sequence": 1,
  "expiresAt": 1700000010,
  "ciphertext": "base64url-no-padding"
}
```

Allowed types are `snapshot`, `participants`, `request`, `register`, and
`heartbeat`. Sequence must be nonzero and monotonically increase per
`keyId:epoch` replay domain.

## Key derivation and AEAD

```text
directory_key = HMAC-SHA-256(psk,
  "IncomUdon directory PSK v1 relay-to-pwa" || epoch)
nonce = "IDP1" || U64BE(sequence)
```

AES-256-GCM encrypts the JSON payload. AAD is the concatenation of:

```text
"IncomUdon Directory Envelope AAD v1\0"
U8(v) || U8(len(type)) || type || U8(len(keyId)) || keyId || epoch ||
U64BE(sequence) || U64BE(expiresAt)
```

Receivers MUST validate envelope type, key ID, epoch size, expiration,
authentication tag, and replay sequence before accepting a payload.

## Payloads

`snapshot` plaintext:

```json
{"version":1,"revision":"sha256 hex","issuedAt":0,"expiresAt":0,
 "channels":[{"channelId":111,"name":"Operations"}],
 "speakers":[{"channelId":111,"senderId":1002,"name":"Unit A"}]}
```

A speaker row with `channelId` set to the string `all` in the source CSV is
resolved by the Relay into per-channel metadata; a channel-specific row wins.

`participants` plaintext contains `participants`, each with `channelId`,
`senderId`, `lastSeenAt`, and `talking`. It intentionally contains no address.

`request` plaintext contains `version`, `issuedAt`, and `expiresAt`.
`register` and `heartbeat` additionally contain a base64url 16-byte
`instanceId`. The Relay derives a client's target address from the observed
UDP source address, never from the payload.

See `../../test-vectors/directory-psk-v1.json` for a deterministic request.
