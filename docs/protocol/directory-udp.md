# Directory UDP v3

## Scope

Directory UDP v3 is the only current IncomUdon Directory wire protocol. It is
an optional UDP metadata plane for channel names, speaker names, and current
participant metadata. It never carries channel credentials, media keys, OIDC
material, endpoint addresses, or media payloads.

Directory is disabled by default. When enabled, it uses channel-password-derived
keys and the media-port transport by default. A Relay MAY instead use a
dedicated Directory UDP listener when operational policy requires network and
traffic separation.

Directory UDP v1 shared-PSK and Directory UDP v2 are removed from the current
specification. They are historical draft formats available only through prior
specification tags. A current implementation MUST transmit and accept only v3;
it MUST NOT fall back to or negotiate v1 or v2.

## Limits and defaults

| Constant | Value | Requirement |
|---|---:|---|
| `MAX_DIRECTORY_UDP_PAYLOAD_BYTES` | 1200 bytes | Complete UDP payload, including an optional media-port carrier. |
| Maximum channels/speakers/participants/clients | 256/4096/128/64 | Directory logical-object limits. |
| `MAX_DIRECTORY_FRAGMENT_COUNT` | 32 | Maximum fragments in one data response or snapshot page. |
| `DIRECTORY_REPLAY_WINDOW_SIZE` | 64 | Per-domain authenticated sequence window. |
| `MAX_DIRECTORY_REASSEMBLY_SETS` | 2 | Incomplete sets retained per replay domain. |
| `MAX_DIRECTORY_REASSEMBLED_PLAINTEXT_BYTES` | 32768 bytes | Total retained decrypted plaintext per replay domain. |
| `DIRECTORY_REASSEMBLY_TIMEOUT_SECONDS` | 5 seconds | Maximum time to wait for a complete fragment set. |
| `MAX_DIRECTORY_PAGE_COUNT` | 256 | Maximum pages in one revision-pinned snapshot retrieval. |
| Default publish interval | 30 seconds | Relay dynamic participant publication interval. |
| Default snapshot/client TTL | 90 seconds | Maximum freshness lifetime for published metadata. |
| Request and registration lifetime | 30 seconds | Maximum accepted `expiresAt - issuedAt`. |

The 1200-byte limit applies after UTF-8 JSON serialization, AES-GCM encryption,
base64url encoding, envelope serialization, and, for media-port transport, the
carrier prefix. Senders MUST NOT rely on IP fragmentation.

## Transport binding

Directory v3 has two mutually exclusive configured transports:

| Transport | Default | Datagram form |
|---|---:|---|
| `media-port` | Yes, when Directory is enabled | `"IDP3" || U8(1) || directory_v3_json` |
| `dedicated-udp` | No | Raw UTF-8 `directory_v3_json` |

`"IDP3"` is the four ASCII bytes `49 44 50 33`; the carrier version is one
byte with value `0x01`. The carrier has no length field because the UDP
datagram boundary supplies it. A carrier occupies five bytes, so its inner JSON
MUST be no larger than 1195 bytes.

On a media port, a Relay MUST first enforce the 1200-byte cap, carrier length,
magic, and pre-authentication source rate limit. It MUST dispatch a valid
carrier only to the Directory parser and MUST NOT also pass it to the binary
media/control parser. A non-carrier is processed only as a binary media/control
datagram. A disabled Directory service or a Relay configured for
`dedicated-udp` MUST discard media-port carriers without response.

A Directory request is processed locally by the Relay. It MUST NOT be forwarded
to channel members as media or control traffic. A response is sent through the
same configured transport to the observed source endpoint bound to the request
or registration. `media-port` clients derive that endpoint from the active
Relay host and port. `dedicated-udp` clients require an explicitly configured
Directory host and port; endpoint provisioning is outside this wire protocol.

The selected transport is cryptographically bound as `transport_binding`:

```text
0x00 = dedicated-udp
0x01 = media-port carrier
```

A receiver obtains the binding from the local listener/carrier, never from the
JSON payload. A datagram replayed between transports therefore fails AES-GCM
authentication.

### Media-port scheduling

Media-port Directory traffic is best effort. A Relay and client MUST give media
and ordinary Relay control traffic strict priority over Directory processing and
transmission. They MUST maintain Directory-specific bounded receive and
transmit budgets; dropping Directory traffic is permitted, while delaying,
queueing behind, or dropping `AUDIO`, `FEC`, or ordinary control to preserve a
Directory response is prohibited.

Implementations MUST apply a pre-authentication source rate limit before JSON
parsing and a separate authenticated Directory response budget before sending
fragments. They MUST pace multi-fragment responses and MUST NOT apply voice
DSCP EF treatment to Directory traffic. Implementations SHOULD expose the
resulting drops and reassembly failures through local diagnostics.

## Envelope

After removing the optional carrier, every Directory datagram is UTF-8 JSON
conforming to `../../schemas/directory-v3.schema.json`:

```json
{
  "v": 3,
  "type": "request",
  "channelId": 111,
  "epoch": "base64url-no-padding",
  "sequence": 1,
  "expiresAt": 1700000010,
  "ciphertext": "base64url-no-padding"
}
```

Allowed types and directions are:

| Direction | Types |
|---|---|
| client to Relay | `request`, `register`, `heartbeat` |
| Relay to client | `snapshot`, `participants`, `error` |

`channelId` is plaintext only so a receiver can select the channel credential.
It is included in AAD and is authenticated. A Relay MUST NOT return data for a
different channel. A receiver MUST reject a decrypted record whose `channelId`,
when present, differs from envelope `channelId`.

The JSON `epoch` is canonical unpadded base64url encoding of exactly 16 random
bytes. Let `epoch_raw = BASE64URL-DECODE(envelope.epoch)`. A receiver MUST
reject decode failure, a value other than 16 bytes, or an encoding for which
`BASE64URL-ENCODE(epoch_raw)` differs from `envelope.epoch`. All cryptographic
uses of `epoch` use `epoch_raw`, never the textual JSON representation.

`sequence` and `expiresAt` MUST be positive JavaScript-safe integers in the
inclusive range 1 through 9007199254740991. Implementations MUST preserve
these values exactly through JSON parsing and encode them as zero-extended
`U64BE` inputs. `expiresAt`, `issuedAt`, and `lastSeenAt` are Unix time seconds.
Senders choose a fresh CSPRNG-generated `epoch_raw` before first use and
whenever local sequence state resets.

## Key derivation and AEAD

Channel credentials are normalized to `password_key` by `security.md` before
Directory derivation. Empty credentials are invalid. Directory v3 derives no
key from raw credential text and defines no shared-PSK mode.

```text
directory_channel_key = HKDF-SHA-256(
  password_key, empty_salt,
  "incomudon-directory-channel-v3", 32)

directory_c2r_key = HKDF-SHA-256(
  directory_channel_key, empty_salt,
  "incomudon-directory-channel-v3 client-to-relay", 32)

directory_r2c_key = HKDF-SHA-256(
  directory_channel_key, empty_salt,
  "incomudon-directory-channel-v3 relay-to-client", 32)

directory_epoch_key = HKDF-SHA-256(
  directional_key, epoch_raw,
  "incomudon-directory-envelope-v3", 32)
```

`directional_key` is `directory_c2r_key` for `request`, `register`, and
`heartbeat`; it is `directory_r2c_key` for `snapshot`, `participants`, and
`error`. Directional keys prevent client-to-Relay and Relay-to-client nonce
collisions.

AES-256-GCM encrypts each complete plaintext fragment independently:

```text
nonce = "IDP3" || U64BE(sequence)
```

AAD is exactly:

```text
"IncomUdon Directory Envelope AAD v3\0" ||
U8(v) || U8(transport_binding) || U8(len(type)) || type ||
U32BE(channelId) || epoch_raw || U64BE(sequence) || U64BE(expiresAt)
```

A receiver MUST validate the datagram size, carrier, envelope schema,
direction/type, canonical epoch, and AES-GCM tag before marking a sequence
accepted. It MUST reject an envelope whose `expiresAt` is not in the future
according to its local Unix clock. It MUST NOT advance replay state for an
unauthenticated or otherwise rejected datagram.

## Replay window

Replay state is scoped to `(direction, channelId, epoch_raw)`. A receiver MUST
maintain a 64-entry sliding window of authenticated accepted `sequence` values:

- a sequence newer than the current high watermark advances the window;
- an unseen sequence within the window is accepted to tolerate UDP reordering;
- a duplicate sequence or a sequence older than the window is rejected.

A sender MUST use each sequence at most once in its replay domain. All fragments
of one data response use the same epoch, distinct sequences, common
`issuedAt`/`expiresAt`, and ascending fragment indexes. The sender MUST NOT
interleave a different data response into the same replay domain until it has
emitted the complete current fragment set.

## Encrypted payloads

Every encrypted payload has `version = 3`, `issuedAt`, and `expiresAt`.
`issuedAt` MUST be earlier than `expiresAt`, and the plaintext `expiresAt` MUST
exactly equal the authenticated envelope value. Client-originated payloads MUST
conform to `../../schemas/directory-v3-client-payload.schema.json`; `request`,
`register`, and `heartbeat` payloads MUST have a lifetime no greater than 30
seconds. Relay-originated `snapshot`, `participants`, and `error` payloads MUST
have a lifetime no greater than 90 seconds.

A `request` has a CSPRNG-generated 16-byte canonical base64url `requestId` and
a `resource` value of `participants` or `snapshot`. A snapshot request may
include an opaque `cursor` received from a prior page. The Relay MUST echo
`requestId` in every response to that request, including an `error`. Periodic
Relay publication without a request MAY omit `requestId`.

`register` and `heartbeat` additionally carry a canonical base64url 16-byte
`instanceId`. The Relay MUST bind dynamic registrations to the observed UDP
source endpoint, never to an address in a payload.

An `error` payload is always a single Relay-originated datagram conforming to
`../../schemas/directory-v3-error-payload.schema.json`. It has `version`,
`issuedAt`, `expiresAt`, `requestId`, and `code`; it MUST NOT contain
`fragment`.

Data responses (`participants` and `snapshot`) MUST conform after decryption to
`../../schemas/directory-v3-response-fragment.schema.json`. Every data response
contains:

```json
{
  "fragment": {
    "responseId": "base64url-encoded-16-byte-random-value",
    "index": 0,
    "count": 3
  }
}
```

`responseId` is fresh 128-bit CSPRNG output for each logical response or
snapshot page. `index` is zero based and MUST satisfy `0 <= index < count`.
`count` is in the inclusive range 1 through 32. A single-datagram data response
still MUST use `index = 0` and `count = 1`.

`participants` contains at most 128 rows for envelope `channelId`; each row has
`channelId`, non-zero `senderId`, `lastSeenAt`, and `talking`. Every logical row
MUST appear in exactly one fragment.

A `snapshot` carries the static channel row and resolved speaker rows. A speaker
`senderId` MUST be non-zero. Large snapshots use revision-pinned pages:

```json
{
  "revision": "lowercase-sha256-hex",
  "page": {
    "index": 0,
    "count": 3,
    "nextCursor": "opaque-cursor-or-null"
  },
  "channels": [],
  "speakers": []
}
```

Every fragment of a page repeats `revision` and `page`. `channels` contains the
single channel row only in fragment zero and is empty in other fragments. A
completed page contributes its speaker rows exactly once. `page.count` is in
the inclusive range 1 through 256 and `0 <= page.index < page.count`; the final
page has `nextCursor = null`, while every non-final page has a non-null opaque
cursor. The Relay MUST retain a stable source revision for a cursor lifetime of
at least 30 seconds. A client MUST stage all pages of one revision and
atomically replace its static snapshot only after every page is complete. It
MUST keep its prior snapshot if any page is missing, expires, or belongs to
another revision.

When a Relay cannot represent a requested resource within fragment, page, or
single-record limits, it MUST return an `error` payload rather than truncate
metadata silently. Defined `error.code` values are `RESPONSE_TOO_LARGE`,
`INVALID_CURSOR`, and `PAGING_SESSION_EXPIRED`. Error payloads are always
single datagrams and do not contain `fragment`.

## Fragment construction and reassembly

A sender MUST first partition logical rows, assign the final `responseId` and
`count`, then serialize, encrypt, base64url-encode, envelope, and (if selected)
carrier-wrap each fragment. It MUST repeat packing as needed until every final
UDP payload is no larger than 1200 bytes. Fixed row counts alone are not a
valid sizing rule. A sender MUST reject an individual record that cannot fit
within these limits and return `RESPONSE_TOO_LARGE`.

A receiver buffers authenticated fragments by:

```text
(direction, channelId, epoch_raw, type, responseId)
```

It MUST permit any arrival order. The first authenticated fragment for an
`index` is retained. If another authenticated fragment with the same set and
index conflicts in common metadata or content, the receiver MUST discard the
entire set and count a reassembly conflict. Fragment sets with different
`responseId` values MUST NOT be combined.

A receiver MUST enforce the configured fragment-count, set-count, and plaintext
limits before retaining data. It MUST discard an incomplete set at the earlier
of `expiresAt` and five seconds after its first accepted fragment. It MUST NOT
treat an incomplete set as a complete snapshot or remove records absent only
because their fragment has not arrived.

After all indexes are present, the receiver MUST validate common metadata,
record uniqueness, channel scope, snapshot page metadata, and logical object
limits. It then applies participants or a completed snapshot revision
atomically. A completed response whose highest fragment sequence is older than
or equal to the highest sequence of an already applied response in the same
replay domain MUST NOT overwrite that newer state.

## Credential security

Directory v3 does not extend the channel credential trust boundary: anyone who
knows a channel credential can already derive the corresponding media and
Control Authentication keys. Encrypted Directory JSON has predictable
structure, so weak passphrases MUST NOT be treated as confidential even when
the `password_key` was derived with Argon2id. Empty credentials are invalid as
required by `security.md`.

## Diagnostics and test requirements

Directory diagnostics are optional because Directory is optional. When exposed,
they use the `directory` object in `diagnostics-v1.schema.json` and MUST NOT
include Directory endpoints, channel credentials, keys, epochs, request IDs,
response IDs, cursors, or metadata names.

Implementations MUST validate `../../test-vectors/directory-v3.json` and test:

1. dedicated and media-port carrier AEAD binding;
2. a single fragment and a three-fragment response;
3. out-of-order, duplicate, conflicting, and missing fragments;
4. replay-window acceptance within 64 sequences and stale/duplicate rejection;
5. expiration and five-second incomplete-set discard;
6. 1200-byte boundary enforcement including the carrier;
7. revision-pinned snapshot pagination and atomic replacement;
8. media-port rate-limit, pacing, and Directory drop behavior without media
   scheduling regression.
