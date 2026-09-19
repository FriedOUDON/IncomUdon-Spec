#!/usr/bin/env python3
"""Validate that every test vector belongs to the current specification snapshot."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

VERSION_PATTERN = re.compile(
    r"^(?:unreleased|v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?)$"
)


def read_spec_version(root: Path) -> str:
    path = root / "SPEC_VERSION"
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if len(lines) != 1 or not lines[0]:
        raise ValueError("SPEC_VERSION must contain exactly one non-empty line")
    version = lines[0]
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"unsupported SPEC_VERSION value: {version!r}")
    return version


def head_tags(root: Path) -> set[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "tag", "--points-at", "HEAD"],
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"cannot list tags pointing at HEAD: {exc}") from exc
    return {tag for tag in completed.stdout.splitlines() if tag}


def validate_vectors(root: Path, expected: str) -> list[str]:
    errors: list[str] = []
    vector_root = root / "test-vectors"
    paths = sorted(vector_root.rglob("*.json"))
    if not paths:
        return [f"no JSON vectors found under {vector_root}"]

    for path in paths:
        relative = path.relative_to(root)
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{relative}: invalid JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{relative}: root must be a JSON object")
            continue
        actual = value.get("specVersion")
        if actual != expected:
            errors.append(
                f"{relative}: specVersion={actual!r}, expected {expected!r}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--expected-version",
        help="require SPEC_VERSION to equal this release tag",
    )
    parser.add_argument(
        "--require-unreleased-unless-tagged",
        action="store_true",
        help="require unreleased unless a matching tag points at HEAD",
    )
    args = parser.parse_args()

    try:
        version = read_spec_version(args.root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.expected_version is not None and version != args.expected_version:
        print(
            "error: SPEC_VERSION=%r, expected release tag %r"
            % (version, args.expected_version),
            file=sys.stderr,
        )
        return 1

    if args.require_unreleased_unless_tagged and version != "unreleased":
        try:
            tags = head_tags(args.root)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if version not in tags:
            print(
                "error: non-tag build requires SPEC_VERSION='unreleased' unless "
                "a matching tag points at HEAD; found %r" % version,
                file=sys.stderr,
            )
            return 1

    errors = validate_vectors(args.root, version)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"validated {version}: all test-vector specVersion values match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
