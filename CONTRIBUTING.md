# IncomUdon Specification Contributing

1. Update normative Markdown before implementation code.
2. Add or update a deterministic vector for every wire-format or crypto change.
3. Use synthetic credentials only.
4. Preserve backwards-compatible text unless a specification version change is
   explicitly proposed.
5. Do not copy implementation-specific UI or deployment documentation here.
6. Keep every `test-vectors/**/*.json` top-level `specVersion` equal to the
   repository-root `SPEC_VERSION` value.
7. Run `py tools/check_spec_version.py` before submitting a change. A release
   commit must also pass `--expected-version` with its planned tag name.
