# Identity Admission v1

## Scope

Identity Admission v1 is an optional per-user authorization layer for Relay
membership and floor control. It uses an OpenID Connect (OIDC) identity
provider through an IncomUdon Access Service, then presents a short-lived
Relay Admission Ticket over the existing UDP control path.

It is separate from channel passwords, AES-GCM v2 media encryption, and
Control Authentication v1:

- OIDC authenticates a person or organization-managed account to the Access
  Service.
- Identity Admission authorizes that account for one channel, sender ID, and
  permission set at the Relay.
- The channel password continues to derive the media and Control Authentication
  keys. Identity Admission does not replace or disclose it.

Identity Admission does not provide per-packet speaker signatures. It prevents
an unauthorized account from joining a protected Relay channel, but a member
who knows the shared channel secret remains within the group-authentication
trust boundary described in `control-auth.md`.

## Deployment modes

Relay identity-admission policy has these modes:

| Mode | Behavior |
|---|---|
| `off` | Default. No OIDC hook, Access Service, ticket processing, or identity admission state is initialized. Existing JOIN behavior is unchanged. |
| `optional` | Legacy authenticated JOIN is permitted. A client that presents an identity ticket must complete the identity flow successfully; a valid ticket adds its per-channel permissions. |
| `required` | A client must complete Identity Admission before JOIN. JOIN, media receive membership, and PTT are denied without a valid, unexpired admission. |

The deployment configuration default is:

```text
identity_admission.mode = off
```

`required` mode MUST also require Control Authentication v1. A Relay MUST fail
closed at startup if `required` is configured without the channel Control Key
material needed to authenticate the identity control messages. Deployments
SHOULD also use AES-GCM v2 media, but Identity Admission does not itself alter
the selected media crypto mode.

`optional` is intended for rollout and mixed deployments. It is not sufficient
to restrict a channel to named users, because a legacy client can still join.
An organization that needs an allow-list MUST use `required`.

## OIDC and Access Service

The Access Service is the OIDC relying party. It validates the configured
issuer, redirect URI, client ID, issuer signature, audience, expiration, and
other normal OIDC requirements before it applies local authorization policy.
It maps a stable OIDC subject and optional IdP groups to an IncomUdon channel
permission set.

Browser clients MUST use Authorization Code Flow with PKCE. A PWA deployment
MUST retain its OIDC session in `Secure`, `HttpOnly`, appropriately `SameSite`
server-session cookies; it MUST NOT put OIDC access or refresh tokens in
`localStorage`, URLs, WebSocket query parameters, diagnostics, or normal logs.

Native clients MUST use the platform system browser and Authorization Code Flow
with PKCE, not an embedded credential web view. The Access Service returns a
Relay Admission Ticket after successful OIDC authentication and authorization.

The Relay never receives an IdP access token or refresh token. It trusts only
Access Service ticket-signing keys configured by key ID.

## Relay Admission Ticket

A Relay Admission Ticket is a compact JWS using `alg = EdDSA` and an Ed25519
Access Service signing key. It MUST use Compact Serialization, ASCII
base64url segments without padding, and be no longer than 768 ASCII bytes.
The JWS protected header MUST contain `alg`, `kid`, and
`typ = "incomudon-admission+jwt"`.

The signed payload MUST contain these claims:

| Claim | Requirement |
|---|---|
| `iss` | Configured Access Service issuer identifier. |
| `aud` | Exact configured Relay audience. |
| `sub` | Stable, Access-Service-scoped pseudonymous user identifier; no email address or display name. |
| `jti` | Cryptographically random ticket ID. |
| `iat` / `exp` | Numeric Unix seconds. `exp - iat` MUST NOT exceed 300 seconds. |
| `ch` | Authorized `channel_id` (`u32`). |
| `sid` | Authorized `sender_id` (`u32`). |
| `perm` | Permission bitset: bit 0 `listen`, bit 1 `talk`. Bit 0 MUST be set. |
| `cnf.jkt` | Base64url SHA-256 digest of the raw 32-byte Ed25519 client public key. |

The Access Service MUST apply group/user/channel policy before ticket issuance.
It MUST omit IdP access tokens, refresh tokens, email addresses, display names,
channel passwords, keys, and arbitrary group claims from the ticket.

The Relay verifies the JWS against a locally configured active or previous
Ed25519 public key selected by `kid`. It MUST validate `iss`, `aud`, `iat`,
`exp`, maximum lifetime, `ch`, `sid`, permissions, and `cnf.jkt` before marking
a peer admitted. A Relay MAY allow at most 30 seconds of clock skew. Ticket
keys MUST support overlap during signing-key rotation.

## UDP admission flow

Identity admission uses the following packet types. Every packet in this flow
MUST use Control Authentication v1 and its normal replay protection.

| Type | Direction | Payload |
|---|---|---|
| `IDENTITY_BEGIN` (`0x12`) | Client to Relay | `ticket_length:u16 || compact_jws || client_public_key[32]` |
| `IDENTITY_CHALLENGE` (`0x13`) | Relay to client | `expiry:u32 || challenge[32]` |
| `IDENTITY_PROOF` (`0x14`) | Client to Relay | `signature[64]` |
| `IDENTITY_DENY` (`0x15`) | Relay to client | `reason:u8` |

The ticket length MUST be from 1 through 768. The Relay MUST reject malformed
base64url/JWS data, unsupported algorithms, ticket/public-key binding errors,
and messages exceeding the datagram limit in `mtu.md` before creating durable
membership state.

A client first completes the Control Authentication cookie challenge described
in `control-auth.md`, but does not send JOIN yet. It then sends
`IDENTITY_BEGIN`. The Relay validates the ticket and confirms that:

1. the common-header channel ID and sender ID equal `ch` and `sid`;
2. the SHA-256 digest of `client_public_key` equals `cnf.jkt`; and
3. the ticket grants `listen` permission.

If valid, the Relay creates a short-lived pending record bound to the observed
source IP, source port, channel ID, sender ID, ticket hash, and challenge. It
returns `IDENTITY_CHALLENGE` with an expiry no more than 30 seconds ahead.

The client signs the following exact byte sequence with its ticket-bound
Ed25519 private key and sends the raw 64-byte Ed25519 signature in
`IDENTITY_PROOF`:

```text
SHA-256(
  "incomudon-identity-admission-v1\0" ||
  challenge ||
  U32BE(channel_id) || U32BE(sender_id) ||
  SHA-256(ASCII(compact_jws))
)
```

The Relay verifies the proof from the same observed source endpoint, consumes
the pending challenge once, and marks the endpoint identity-admitted until the
ticket expiry. The client then sends the ordinary authenticated JOIN cookie
payload. In `required` mode the Relay MUST reject JOIN unless this admission
state is valid for the same endpoint, channel ID, and sender ID.

A client renews admission before ticket expiry by repeating `IDENTITY_BEGIN`
and `IDENTITY_PROOF` from its current endpoint. Renewal does not require a
second JOIN and MUST NOT reset an active server-managed PTT deadline.

## Authorization and expiry

An admitted peer with `listen` may JOIN and receive channel traffic. It may
send `PTT_ON` only when its ticket also grants `talk`. A Relay MUST reject PTT
from a listen-only ticket and MUST NOT forward that peer's media or FEC.

Relay membership expiration is the earlier of the normal membership deadline
and the ticket `exp`. On ticket expiry, the Relay MUST remove membership. If
that peer is actively talking, it MUST stop forwarding media/FEC and broadcast
`TALK_RELEASE` with reason `IDENTITY_EXPIRED`.

A Relay MUST NOT automatically renew a ticket. If an Access Service revokes an
account, the normal bounded response is ticket expiry. Immediate revocation
requires a separately distributed Relay deny-list or online introspection
extension and is outside Identity Admission v1.

## Denial reasons

| Value | Name | Meaning |
|---:|---|---|
| `0x00` | `ADMISSION_REQUIRED` | JOIN was attempted without current admission in required mode. |
| `0x01` | `INVALID_TICKET` | Invalid JWS format, signature, algorithm, or key ID. |
| `0x02` | `TICKET_EXPIRED` | Ticket is expired, not yet valid, or exceeds the allowed lifetime. |
| `0x03` | `TICKET_SCOPE_MISMATCH` | Issuer, audience, channel ID, sender ID, or key binding mismatch. |
| `0x04` | `PERMISSION_DENIED` | Required `listen` or `talk` permission is absent. |
| `0x05` | `INVALID_PROOF` | Challenge, endpoint binding, or Ed25519 proof verification failed. |
| `0x06-0xff` | reserved | Client MUST display a generic admission failure. |

The Relay MAY rate-limit identity failures. It MUST log only a reason class and
a privacy-preserving ticket ID hash prefix; it MUST NOT log the compact JWS,
OIDC token, public-key material, or challenge bytes.

## Security properties and limitations

The Admission Ticket is not an OIDC bearer token and is not sufficient by
itself for Relay access. It is bound to an Ed25519 proof of possession, the
UDP endpoint during the challenge, and Control Authentication v1. The ticket
is transmitted as plaintext control data, so it MUST contain no personal data
or reusable IdP credentials. Its short lifetime and proof-of-possession binding
prevent a passive observer from replaying it as another client.

Identity Admission does not prevent UDP jamming, traffic analysis, a user with
both a valid ticket and the channel secret from abusing group credentials, or
compromise of the Access Service signing key. Operators MUST protect signing
keys, use HTTPS/WSS for OIDC and Access Service traffic, restrict redirect
URIs, and rotate signing keys through overlapping `kid` entries.

## Required interoperability cases

1. `off` mode performs no ticket processing and accepts existing authenticated
   JOIN behavior unchanged.
2. `required` mode rejects JOIN without current identity admission.
3. A valid listen-only ticket permits JOIN but rejects PTT.
4. A valid talk ticket completes the cookie, ticket, proof, and JOIN flow.
5. An altered ticket, wrong `kid`, expired ticket, wrong channel/sender ID,
   wrong public key, replayed challenge, and invalid signature are rejected.
6. Ticket renewal preserves membership without resetting an active PTT lease.
7. Ticket expiry removes membership and releases an active talker with
   `IDENTITY_EXPIRED`.
8. No normal log, diagnostics snapshot, or UI export contains a JWS, OIDC
   credential, challenge, public key, or full pseudonymous subject value.

## Deterministic vector

`../../test-vectors/identity-admission-v1.json` contains synthetic RFC 8032
Ed25519 keys, a signed compact JWS, an `IDENTITY_BEGIN` payload, an identity
challenge, and a proof-of-possession signature. Implementations that support
Identity Admission v1 MUST verify the JWS and proof byte-for-byte before
claiming compatibility.
