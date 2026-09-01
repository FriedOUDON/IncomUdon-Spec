# Test Vectors

This directory will contain deterministic interoperability data for every
stable protocol feature.

Required vector groups before `v1.0.0`:

- packet envelope serialization and parsing;
- AES-GCM legacy and AES-GCM v2 success/failure cases;
- join, PTT, codec configuration, and server configuration payloads;
- PCM, Codec2, and Opus packet examples;
- FEC recovery examples; and
- directory PSK authentication examples.

Vectors must state the specification version, input values, expected binary
hex, and expected decoded output. Secret material in vectors must be synthetic
and must never be reused in deployed environments.
