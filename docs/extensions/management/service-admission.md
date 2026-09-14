# Managed Service Admission v1

## Scope

Managed Service Admission v1 authorizes an organization-operated non-
interactive service, such as a Recorder Worker, to join one Relay channel
without an interactive OIDC login. It is an optional companion to Identity
Admission v1 and is available only when Management Plane v1 and the Relay
managed-service admission policy are enabled.

It does not grant anonymous Relay access. The service first authenticates to
the Management API with mTLS, receives a narrow signed grant through a
channel-scoped ACL, then proves possession of its bound Ed25519 key to the
Relay over authenticated UDP control packets.

## Policy modes

| Mode | Behavior |
|---|---|
| `off` | Default. The Relay does not parse service admission packets or accept service grants. |
| `enabled` | The Relay accepts a valid Managed Service Admission in addition to normal JOIN behavior. |

If Identity Admission is `required`, a Relay in `enabled` mode MAY accept
exactly one current admission state for a joining endpoint: either Identity
Admission v1 or Managed Service Admission v1. It MUST NOT accept an endpoint
with neither state. If Identity Admission is `off` or `optional`, a service
grant remains an additional constrained authorization mechanism but does not
change ordinary-client behavior.

Managed Service Admission MUST require Control Authentication v1. A Relay
MUST fail closed at startup when managed-service admission is enabled but its
Service Admission Grant verification keys are unavailable.

## Service Admission Grant

A Service Admission Grant is a compact JWS using `alg = EdDSA` and a
Management Service Ed25519 signing key. It MUST use Compact Serialization,
ASCII base64url segments without padding, and be no longer than 768 ASCII
bytes. Its protected header MUST contain `alg`, `kid`, and
`typ = "incomudon-service-admission+jwt"`.

The JWS payload MUST validate against
`../../../schemas/management/service-admission-grant-v1.schema.json` after signature
verification. It contains the following claims:

| Claim | Requirement |
|---|---|
| `iss` | Configured Management Service issuer identifier. |
| `aud` | Exact configured Relay audience. |
| `svc` | Stable Management-Service-scoped pseudonymous service ID. |
| `jti` | Cryptographically random grant ID. |
| `iat` / `exp` | Numeric Unix seconds; `exp - iat` MUST be from 60 through 3600 seconds. |
| `ch` | Authorized `channel_id` (`u32`). |
| `sid` | Authorized `sender_id` (`u32`). |
| `role` | `recorder`, `observer`, or `automation`. |
| `perm` | Permission bitset: bit 0 `listen`, bit 1 `talk`, bit 2 `interrupt`; bit 0 MUST be set and bit 2 requires bit 1. |
| `pri` | Interrupt priority (`u8`), required and non-zero only when bit 2 is set. |
| `cnf.jkt` | Base64url SHA-256 digest of the raw 32-byte Ed25519 service public key. |
| `grace_seconds` | Optional bounded uninterrupted-membership grace; 0 through 1800. |

`recorder` and `observer` grants MUST have `perm = 1`. A Management Service
MUST issue `perm` bit 1 only to an ACL that explicitly grants `talk`, and bit
2 with a non-zero `pri` only to an ACL that explicitly grants Floor Interrupt;
role names alone are insufficient. The grant MUST omit channel credentials,
derived keys, OIDC credentials, personal data, certificate material, and
arbitrary organization claims.

The Relay selects a configured active or previous Management Service public key
by `kid`, verifies the JWS signature, then validates all claims, clock skew,
maximum lifetime, role/permission consistency, and `cnf.jkt`. A Relay MAY
allow at most 30 seconds of clock skew. Signing-key rotation MUST permit an
intentional overlap of active and previous verification keys.

## UDP admission flow

All packets in this flow MUST use Control Authentication v1, the ordinary
control replay window, and the Version 1 28-byte control header. They use the
following packet types:

| Type | Direction | Payload |
|---|---|---|
| `SERVICE_ADMISSION_BEGIN` (`0x16`) | Service to Relay | `grant_length:u16 || compact_jws || service_public_key[32]` |
| `SERVICE_ADMISSION_CHALLENGE` (`0x17`) | Relay to service | `expiry:u32 || challenge[32]` |
| `SERVICE_ADMISSION_PROOF` (`0x18`) | Service to Relay | `signature[64]` |
| `SERVICE_ADMISSION_DENY` (`0x19`) | Relay to service | `reason:u8` |

`grant_length` MUST be from 1 through 768. The Relay MUST reject malformed
JWS data, an unsupported algorithm, incorrect protected-header type, invalid
key binding, and a datagram that exceeds the UDP MTU limit before creating
durable membership state.

A service completes the Control Authentication cookie challenge but does not
send JOIN yet. It sends `SERVICE_ADMISSION_BEGIN`; the Relay verifies that the
common-header channel ID and sender ID equal `ch` and `sid`, the grant permits
`listen`, and the public-key digest equals `cnf.jkt`. The Relay then creates a
pending record bound to the observed source IP, source port, channel ID,
sender ID, grant hash, and random challenge. It returns a challenge with an
expiry no more than 30 seconds ahead.

The service signs this exact byte sequence with the Ed25519 private key bound
by `cnf.jkt` and returns the raw 64-byte signature:

```text
SHA-256(
  "incomudon-managed-service-admission-v1\0" ||
  challenge ||
  U32BE(channel_id) || U32BE(sender_id) ||
  SHA-256(ASCII(compact_jws))
)
```

The Relay verifies the proof from the same source endpoint, consumes the
pending challenge once, and marks the endpoint service-admitted until grant
expiry. The service then sends the ordinary authenticated JOIN cookie payload.
A valid service-admitted state is bound to the endpoint, channel ID, sender ID,
permission set, grant ID, and proof key.

## Permission enforcement and renewal

A service with `listen` may JOIN and receive channel traffic. It may send ordinary `PTT_ON` only when `talk` is set. It may send
`PTT_REQUEST` only when `talk`, `interrupt`, and a valid non-zero `pri` are
present and Floor Interrupt v1 is enabled. A Relay MUST reject a PTT request
whose required permission is absent and MUST NOT forward AUDIO or FEC from a
listen-only service. It MUST enforce all ordinary floor,
membership, PTT timeout, MTU, media authentication, and media replay rules.

The service renews before expiry by completing a new begin/challenge/proof
flow from its current endpoint. Renewal MUST NOT reset an active PTT deadline.
A Recorder Worker SHOULD renew at no later than half the granted lifetime. A
Relay MUST NOT obtain or renew a grant itself.

An existing receive-only service membership MAY remain until
`exp + grace_seconds` only when all of the following hold:

1. `grace_seconds` is present and non-zero;
2. it does not exceed 1800;
3. membership and source endpoint remained continuous from before `exp`;
4. the Relay has not restarted and membership did not expire; and
5. the grant was not revoked.

An expired grant MUST NOT authorize a new JOIN, source-endpoint change,
privilege increase, or fresh service-admission flow. A Relay MUST NOT extend
grace beyond the grant claim or local configured maximum. Deployments SHOULD
set grace to zero unless a recorder availability requirement justifies it.

## Revocation

The Management Service sends a private authenticated revocation event to the
Relay containing the affected grant ID and/or service ID, channel ID, and
reason. The Relay MUST invalidate matching current service-admitted state,
remove membership, stop media forwarding, and release an active talker with
`TALK_RELEASE` reason `SERVICE_ADMISSION_REVOKED`. A Relay SHOULD complete
revocation within five seconds of receiving the private event.

Relay-side grant deny lists MAY be retained across Management Service outages.
They MUST be bounded, expire no later than the revoked grant's maximum possible
grace deadline, and contain only a privacy-preserving grant ID hash or an
opaque grant ID.

## Denial reasons

| Value | Name | Meaning |
|---:|---|---|
| `0x00` | `SERVICE_ADMISSION_REQUIRED` | Admission required but no current service admission exists. |
| `0x01` | `INVALID_SERVICE_GRANT` | JWS format, type, signature, algorithm, or key ID is invalid. |
| `0x02` | `SERVICE_GRANT_EXPIRED` | Grant is expired, not yet valid, or exceeds allowed lifetime. |
| `0x03` | `SERVICE_SCOPE_MISMATCH` | Issuer, audience, channel ID, sender ID, or key binding mismatch. |
| `0x04` | `SERVICE_PERMISSION_DENIED` | Required `listen`, `talk`, or `interrupt` permission is absent. |
| `0x05` | `INVALID_SERVICE_PROOF` | Challenge, endpoint binding, or proof verification failed. |
| `0x06` | `SERVICE_ADMISSION_DISABLED` | Relay managed-service policy is disabled. |
| `0x07` | `SERVICE_ADMISSION_REVOKED` | Grant or service was revoked. |
| `0x08-0xff` | reserved | Client MUST show a generic service-admission failure. |

The Relay MAY rate-limit failures. It MUST log only reason classes and a
privacy-preserving grant-ID hash prefix; it MUST NOT log grants, public keys,
challenge bytes, certificates, or channel credentials.

## Security properties

A Service Admission Grant is not a channel credential and cannot decrypt
media. A valid grant is insufficient without a matching Ed25519
proof-of-possession key, authenticated control traffic, an authorized source
endpoint, and the channel's ordinary credential-derived security state.

The service admission JWS travels through UDP control data and therefore MUST
contain no secret or personal data. Short lifetimes, mTLS-gated issuance,
proof-of-possession binding, Relay audience binding, channel scoping, replay
protection, and revocation limit its use. This protocol does not protect
against UDP jamming, traffic analysis, compromise of the Management Service
signing key, or compromise of a Recorder Worker's channel credential.

## Deterministic vector

`../../../test-vectors/management/service-admission-v1.json` contains synthetic Ed25519 keys,
a signed grant, a begin payload, a challenge, and a proof. Implementations
that support Managed Service Admission v1 MUST verify the grant and proof
byte-for-byte before claiming compatibility.