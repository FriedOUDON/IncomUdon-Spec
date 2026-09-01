# Versioning and Compatibility

## Specification releases

Specification tags use semantic versioning.

- Patch releases clarify text or add test vectors without changing behavior.
- Minor releases add backward-compatible packet types, flags, or optional
  features.
- Major releases change mandatory interoperability behavior.

## Implementation declaration

Each client and Relay release MUST document:

- supported protocol versions;
- supported encryption modes;
- supported codecs and FEC modes; and
- the exact `IncomUdon-Spec` tag used for validation.

## Change process

1. Update this repository first.
2. Add or update binary test vectors.
3. Implement the change in Relay and at least one client.
4. Run cross-implementation interoperability tests.
5. Tag the specification and then release consumers.

No implementation repository may silently redefine an existing field or
packet type.
