"""Safe local-file loading and RFC 6901 JSON Pointer resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class VectorValidationError(ValueError):
    """Raised when a validator input is malformed or escapes the repository."""


def repository_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise VectorValidationError(f"path must be repository-relative: {relative}")

    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise VectorValidationError(f"path escapes repository root: {relative}") from exc
    return resolved


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise VectorValidationError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise VectorValidationError(f"invalid JSON in {path}: {exc}") from exc


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON Pointer, with the empty pointer selecting root."""
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise VectorValidationError(f"JSON Pointer must be empty or begin with '/': {pointer}")

    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise VectorValidationError(f"JSON Pointer does not exist: {pointer}")
            current = current[token]
            continue
        if isinstance(current, list):
            if not token.isdecimal():
                raise VectorValidationError(f"JSON Pointer array token is not an index: {pointer}")
            index = int(token)
            if index >= len(current):
                raise VectorValidationError(f"JSON Pointer index is out of range: {pointer}")
            current = current[index]
            continue
        raise VectorValidationError(f"JSON Pointer traverses a scalar value: {pointer}")
    return current
