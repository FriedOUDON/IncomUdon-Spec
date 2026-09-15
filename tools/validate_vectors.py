#!/usr/bin/env python3
"""Run independent structural validation for IncomUdon specification vectors."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from check_spec_version import read_spec_version, validate_vectors
from spec_validator.crypto_vectors import validate_crypto_vectors
from spec_validator.fec_vectors import validate_fec_vectors
from spec_validator.lifecycle_vectors import validate_lifecycle_vectors
from spec_validator.packet_encoder import validate_packet_envelope_vectors
from spec_validator.schema_targets import (
    validate_openapi_document,
    validate_schema_documents,
    validate_schema_targets,
)


def validate_metadata(root: Path) -> list[str]:
    try:
        version = read_spec_version(root)
    except ValueError as exc:
        return [str(exc)]
    return validate_vectors(root, version)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--suite", choices=("structural", "packet", "crypto", "fec", "lifecycle", "all"), default="structural"
    )
    args = parser.parse_args()
    root = args.root.resolve()

    errors = []
    completed: list[str] = []
    if args.suite in {"structural", "all"}:
        errors.extend(validate_metadata(root))
        errors.extend(validate_schema_documents(root))
        errors.extend(validate_openapi_document(root))
        errors.extend(validate_schema_targets(root))
        completed.append("structural")
    if args.suite in {"packet", "all"}:
        errors.extend(validate_packet_envelope_vectors(root))
        completed.append("packet")
    if args.suite in {"crypto", "all"}:
        errors.extend(validate_crypto_vectors(root))
        completed.append("crypto")
    if args.suite in {"fec", "all"}:
        errors.extend(validate_fec_vectors(root))
        completed.append("fec")
    if args.suite in {"lifecycle", "all"}:
        errors.extend(validate_lifecycle_vectors(root))
        completed.append("lifecycle")

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    print("validated " + ", ".join(completed) + " test-vector suite(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
