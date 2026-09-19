# IncomUdon Specification Contributing

1. Update normative Markdown before implementation code.
2. Add or update a deterministic vector for every wire-format or crypto change.
3. Use synthetic credentials only.
4. Preserve backwards-compatible text unless a specification version change is
   explicitly proposed.
5. Do not copy implementation-specific UI or deployment documentation here.
6. Keep every `test-vectors/**/*.json` top-level `specVersion` equal to the
   repository-root `SPEC_VERSION` value.
7. Run `py tools/check_spec_version.py` and install then run all independent
   reference validation suites before submitting a change:

   ```powershell
   py -m pip install -r tools/requirements-ci.txt
   py tools/validate_vectors.py --suite all
   ```

   Use `--suite structural` when only metadata, JSON Schema, and Management
   OpenAPI 3.1 contract validation is needed during iteration.

   A release commit must also pass `--expected-version` with its planned tag name.
   Normal development commits must pass `--require-unreleased-unless-tagged`.
