# Relay Operational CSV Configuration v1

## Scope

This document defines the interoperable CSV file formats used to provision
Relay-side operational metadata and keys. It covers the optional Directory
publisher, Control Authentication key store, and the optional Management Plane
service and channel ACL inputs.

These files are local administration data. They are not UDP protocol payloads,
are never distributed to clients, and do not define container paths, environment
variable names, reload intervals, or file-permission commands. Implementations
MUST document those deployment-specific settings separately.

Directory CSV files provide display metadata only. They MUST NOT authorize
channel membership. Management CSV files authorize Management Plane services;
they MUST NOT contain channel credentials, derived keys, media plaintext, or
private keys.

## Common CSV rules

All files use RFC 4180 CSV with these additional requirements:

- Encoding MUST be UTF-8 without a BOM. Parsers MUST accept LF and CRLF line
  endings.
- A row MUST contain the exact number of fields defined for its file after CSV
  unescaping. Unknown or missing fields are errors.
- Numeric IDs are unsigned decimal integers in the inclusive range
  `0` through `4294967295`, without signs, hexadecimal notation, or grouping
  separators. A field with a narrower range states that range explicitly.
- Boolean fields are the lowercase ASCII literals `true` or `false`.
- Parsers MUST reject a file with duplicate semantic keys. They MUST NOT use
  last-row-wins behavior for authorization or key material.
- An implementation that reloads files MUST parse and validate the complete
  candidate file set before applying any part of it. On failure, it MUST retain
  the previous valid generation and emit a redacted configuration error.
- Names are non-empty valid UTF-8 text of at most 128 Unicode code points.
  Deployments SHOULD avoid control characters and leading or trailing
  whitespace in names.

Directory CSV files permit a first-row header and whole-line comments beginning
with `#`; blank rows are ignored. The legacy Control Authentication key file
permits an optional first-row header and blank rows, but does not permit comment
rows. Management CSV v1 files require a header row and do not permit comments
or blank data rows.

## Directory metadata files

Directory UDP is optional. When enabled, the Relay consumes the following two
files as one metadata generation. Their data is published only through the
Directory protocol; see `../protocol/directory-udp.md`.

### `channels.csv`

Columns:

```text
channel_id,name
```

`channel_id` is a unique `u32`. `name` is the display name for that channel.
At least one channel row is required when Directory publishing is enabled.

```csv
channel_id,name
111,Security A
222,Maintenance
```

### `speakers.csv`

Columns:

```text
channel_id,sender_id,name
```

`sender_id` is a `u32`; `name` is the display name. A numeric `channel_id`
MUST name an existing row in `channels.csv`. The exact pair
`(channel_id, sender_id)` MUST be unique.

The special case-insensitive value `all` is permitted only in the
`channel_id` column. It defines a fallback name for that `sender_id` across all
configured channels. A concrete numeric channel row for the same sender takes
precedence. Each `(all, sender_id)` pair MUST be unique.

```csv
channel_id,sender_id,name
all,1002,Dispatch
111,1002,Security Dispatch
222,2001,Maintenance Lead
```

The example resolves sender `1002` as `Security Dispatch` in channel `111`
and as `Dispatch` in channel `222`. `all` is display-metadata fallback only;
it MUST NOT be accepted in a control-key or Management Plane authorization
file.

## Control Authentication key file

The optional Control Authentication key store has this format:

```text
channel_id,key_id,control_key_base64
```

`channel_id` is a `u32`. The CSV column `key_id` is the non-zero
`control_key_id`, unique within its channel. `control_key_base64` is standard
padded Base64 that decodes to exactly 32 bytes. The semantic key
`(channel_id, control_key_id)` MUST be unique. This Control Authentication
identifier is distinct from the AES-GCM v2 `media_key_id` and does not select
media key material.

```csv
channel_id,key_id,control_key_base64
111,1,AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
```

For a channel used by standard Control Authentication v1 clients,
`control_key_base64` MUST be the exact 32-byte `control_key` derived from the
same channel credential and `channel_id` according to
`../protocol/control-auth.md`. Operators MUST perform the credential-to-
`password_key` derivation from `../protocol/security.md`, then the Control
Authentication HKDF, before Base64-encoding the result for this file.

This file contains the purpose-limited Control Authentication key, not an
independently provisioned Control Authentication secret. It MUST NOT contain an
unrelated random key that standard clients cannot derive. It MUST be stored
outside source control, readable only by the Relay process identity, and excluded
from normal configuration exports, diagnostics, and logs. The Relay key file
MUST NOT contain channel credentials, `password_key`, `media_key`, or Directory
keys. The control key itself is used according to
`../protocol/control-auth.md`.

## Management Plane files

Management Plane v1 is optional and disabled by default. These files are
consulted only when a deployment enables that plane. They define local mapping
and authorization data for the mTLS-authenticated Management Service described
in `../extensions/management/overview.md`; they do not replace the signed
Managed Service Admission grant protocol.

### `management-services.csv`

Columns:

```text
service_id,certificate_sha256,api_role,enabled
```

| Column | Requirement |
|---|---|
| `service_id` | Stable ASCII identifier matching `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`. |
| `certificate_sha256` | Lowercase 64-hex-character SHA-256 digest of the DER-encoded mTLS client certificate. |
| `api_role` | One of `viewer`, `recorder`, `operator`, `auditor`, or `admin`. |
| `enabled` | `true` permits the mapped service to authenticate; `false` denies it. |

`service_id` and `certificate_sha256` MUST each be unique. A certificate maps
to exactly one service. Replacing a certificate therefore requires an explicit
new row or an atomic generation update; sharing a certificate across services
is prohibited.

```csv
service_id,certificate_sha256,api_role,enabled
recorder-east,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,recorder,true
dispatch-console,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,operator,true
```

The certificate digest identifies a public certificate and is not secret, but
it SHOULD still be treated as administration metadata. The matching private
key, CA material, Management Service signing keys, and channel credentials
MUST NOT appear in this CSV.

### `management-channel-acl.csv`

Columns:

```text
service_id,channel_id,sender_id,admission_role,allow_listen,allow_talk,allow_interrupt,interrupt_priority,enabled
```

| Column | Requirement |
|---|---|
| `service_id` | Existing enabled `management-services.csv` service ID. |
| `channel_id` | Exact authorized `u32` channel ID. Wildcards and `all` are forbidden. |
| `sender_id` | Exact `u32` sender ID bound into a Managed Service Admission grant. |
| `admission_role` | `recorder`, `observer`, or `automation`. |
| `allow_listen` | Must be `true` for an issuable Managed Service Admission grant. |
| `allow_talk` | Permits ordinary `PTT_ON` only when `true`. |
| `allow_interrupt` | Permits `PTT_REQUEST` only when `true`; requires `allow_talk=true`. |
| `interrupt_priority` | Decimal `0` through `255`; it MUST be `1` through `255` exactly when `allow_interrupt=true`, otherwise `0`. |
| `enabled` | `false` prevents issuance from this row without deleting its audit history. |

The tuple `(service_id, channel_id, sender_id)` MUST be unique. An
`admission_role` of `recorder` or `observer` MUST have
`allow_listen=true`, `allow_talk=false`, `allow_interrupt=false`, and
`interrupt_priority=0`. `automation` may have talk or interrupt permission
only through the explicit fields above. A role name alone MUST NOT imply talk
or interrupt permission.

```csv
service_id,channel_id,sender_id,admission_role,allow_listen,allow_talk,allow_interrupt,interrupt_priority,enabled
recorder-east,111,9001,recorder,true,false,false,0,true
dispatch-console,111,9002,automation,true,true,true,200,true
```

A Management Service derives grant claims `ch`, `sid`, `role`, `perm`, and
`pri` only from an enabled valid row. It MUST NOT accept a caller-supplied
priority or channel scope. See
`../extensions/management/service-admission.md` and
`../protocol/floor-interrupt.md`.

## Reload, revocation, and logging

Changes to Directory files may update published display metadata on the next
Directory publication. Changes to the Control Authentication key file MUST
follow the key-rotation behavior in `control-auth.md`. An implementation MAY
reload Management CSV files, but when it does it MUST evaluate
`management-services.csv` and `management-channel-acl.csv` atomically.

Disabling or removing a mapped Management service or channel ACL row MUST be
processed as an authorization change. Existing Managed Service Admission
memberships are subject to the revocation behavior in
`../extensions/management/overview.md`; a reload MUST NOT leave an obsolete
service with indefinitely renewable privileges.

Logs MAY identify a file name, a row number, a non-secret `service_id`, and a
channel ID. Logs MUST NOT contain `control_key_base64`, channel passwords,
derived keys, private keys, admission grants, or complete certificate material.

## Interoperability fixture

`../../test-vectors/configuration/relay-csv-v1.json` provides canonical valid
CSV text and normalized expected values for parser tests. Implementations MUST
reject each listed invalid semantic condition rather than silently choosing a
row.