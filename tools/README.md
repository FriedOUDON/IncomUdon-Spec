# Specification Validators

`validate_vectors.py` is an independent reference validator. It MUST NOT import
Relay, PWA, Qt, or Rust implementation code.

## Structural suite

Run the first-stage suite with:

```powershell
python -m pip install -r tools/requirements-ci.txt
python tools/validate_vectors.py --suite all
```

The structural suite validates vector `specVersion` metadata, every repository
JSON Schema, the Management OpenAPI YAML document, and runtime JSON targets
listed in `vector-schema-targets.json`.

The manifest maps a test vector and RFC 6901 JSON Pointer to its canonical
schema. A vector root is metadata or a scenario container, not automatically a
runtime protocol object. `each: true` validates every item in an array;
`encoding: "json-string"` parses a JSON string before schema validation.

## Deterministic packet suite

The `packet` suite independently re-encodes the Version 1 fixed header and
payloads with semantic fixture fields in `packet-envelope-v1.json`. It checks
the resulting payload and complete datagram against their canonical hexadecimal
values. The current coverage includes the 19-byte `CODEC_CONFIG`, talk
packets, the eight-byte `SERVER_CONFIG`, `PING`, and sequenced AUDIO payloads.

Run only this suite with:

```powershell
python tools/validate_vectors.py --suite packet
```

## Crypto golden suite

The `crypto` suite recomputes canonical values without importing product code.
It covers `argon2id-v1` and `raw-secret-v1` credential normalization, HKDF key
separation, Control Authentication HMAC tags and cookies, AES-256-GCM media
and Directory UDP v3 AEAD values, and Ed25519 JWS/admission proof signatures.
The suite verifies both dedicated-UDP and media-port Directory AEAD bindings.

Run only this suite with:

```powershell
python tools/validate_vectors.py --suite crypto
```

`argon2id-v1` intentionally uses its normative 64 MiB memory cost. The
validator caches identical fixture derivations within one process, but CI
workers must have enough memory for the full protocol parameters.

## FEC suite

The `fec` suite implements GF(256) with primitive polynomial `0x11d` and
recomputes external FEC P/Q parity without using a client or Relay codec
library. It validates the historical fixed-size fixture and FEC v2 variable
frame padding, payload encoding, one- and two-frame recovery, short final PTT
blocks, and `audio_seq` wrap-boundary membership.

Run only this suite with:

```powershell
python tools/validate_vectors.py --suite fec
```

## Lifecycle semantic suite

The `lifecycle` suite evaluates state-transition fixtures from the protocol
rules rather than accepting their expected labels as data. It covers
server-managed PTT deadlines and release payloads, membership timing and
Control Authentication acceptance, Identity and Managed Service admission
expiry attribution, Directory v3 replay/reassembly/pagination/registration,
AES-GCM media replay windows, and Floor Interrupt authorization, deterministic
victim selection, preempted playout cleanup, and authenticated control packets.

Run only this suite with:

```powershell
python tools/validate_vectors.py --suite lifecycle
```

## Planned suites

The suite entry point is intentionally extensible for future protocol features.
Every suite continues to avoid product implementation code.
