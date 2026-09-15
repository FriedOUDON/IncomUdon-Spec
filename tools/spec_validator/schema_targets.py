"""Schema-target manifest and OpenAPI structural validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, SchemaError

from .loader import VectorValidationError, load_json, repository_path, resolve_json_pointer


MANIFEST_PATH = "tools/vector-schema-targets.json"
MANIFEST_SCHEMA_PATH = "tools/vector-schema-targets.schema.json"


def _validation_summary(errors: list[Any]) -> str:
    first = errors[0]
    location = "/".join(str(part) for part in first.absolute_path) or "<root>"
    return f"{location}: {first.message}"


def validate_schema_documents(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted((root / "schemas").rglob("*.json")):
        relative = path.relative_to(root).as_posix()
        try:
            schema = load_json(path)
            Draft202012Validator.check_schema(schema)
        except (VectorValidationError, SchemaError) as exc:
            errors.append(f"{relative}: invalid JSON Schema: {exc}")
    return errors


def validate_openapi_document(root: Path) -> list[str]:
    path = root / "docs/extensions/management/openapi-v1.yaml"
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return [f"{path.relative_to(root).as_posix()}: invalid OpenAPI YAML: {exc}"]

    if not isinstance(document, dict):
        return [f"{path.relative_to(root).as_posix()}: OpenAPI document must be an object"]
    if document.get("openapi") != "3.1.0":
        return [f"{path.relative_to(root).as_posix()}: expected openapi 3.1.0"]
    if not isinstance(document.get("paths"), dict):
        return [f"{path.relative_to(root).as_posix()}: paths must be an object"]
    return []


def _load_manifest(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    try:
        manifest = load_json(repository_path(root, MANIFEST_PATH))
        manifest_schema = load_json(repository_path(root, MANIFEST_SCHEMA_PATH))
        validation_errors = list(Draft202012Validator(manifest_schema).iter_errors(manifest))
        if validation_errors:
            errors.append(f"{MANIFEST_PATH}: {_validation_summary(validation_errors)}")
    except (VectorValidationError, SchemaError) as exc:
        errors.append(f"{MANIFEST_PATH}: invalid manifest: {exc}")
        return None, errors
    return manifest, errors


def _decode_target(value: Any, encoding: str, label: str) -> Any:
    if encoding == "object":
        return value
    if encoding != "json-string":
        raise VectorValidationError(f"{label}: unsupported encoding {encoding!r}")
    if not isinstance(value, str):
        raise VectorValidationError(f"{label}: json-string target is not a string")
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise VectorValidationError(f"{label}: target contains invalid JSON: {exc}") from exc


def validate_schema_targets(root: Path) -> list[str]:
    manifest, errors = _load_manifest(root)
    if manifest is None:
        return errors

    vector_cache: dict[str, Any] = {}
    schema_cache: dict[str, Draft202012Validator] = {}
    declared_schemas: set[str] = set()

    for target in manifest["targets"]:
        name = target["name"]
        vector_relative = target["vector"]
        schema_relative = target["schema"]
        declared_schemas.add(schema_relative)
        try:
            if vector_relative not in vector_cache:
                vector_cache[vector_relative] = load_json(repository_path(root, vector_relative))
            if schema_relative not in schema_cache:
                schema_value = load_json(repository_path(root, schema_relative))
                schema_cache[schema_relative] = Draft202012Validator(schema_value)

            selection = resolve_json_pointer(vector_cache[vector_relative], target["pointer"])
            candidates: list[tuple[str, Any]]
            if target.get("each", False):
                if not isinstance(selection, list):
                    raise VectorValidationError(f"{name}: each target is not an array")
                item_pointer = target.get("itemPointer", "")
                candidates = [
                    (f"{target['pointer']}/{index}{item_pointer}", resolve_json_pointer(item, item_pointer))
                    for index, item in enumerate(selection)
                ]
            else:
                candidates = [(target["pointer"], selection)]

            expected = target.get("expected", "valid")
            encoding = target.get("encoding", "object")
            for pointer, candidate in candidates:
                instance = _decode_target(candidate, encoding, name)
                validation_errors = list(schema_cache[schema_relative].iter_errors(instance))
                is_valid = not validation_errors
                if expected == "valid" and not is_valid:
                    errors.append(
                        f"{name} ({vector_relative}{pointer}) does not validate against "
                        f"{schema_relative}: {_validation_summary(validation_errors)}"
                    )
                elif expected == "invalid" and is_valid:
                    errors.append(
                        f"{name} ({vector_relative}{pointer}) unexpectedly validates against "
                        f"{schema_relative}"
                    )
        except (VectorValidationError, SchemaError) as exc:
            errors.append(f"{name}: {exc}")

    all_schemas = {
        path.relative_to(root).as_posix()
        for path in (root / "schemas").rglob("*.json")
    }
    missing = sorted(all_schemas - declared_schemas)
    if missing:
        errors.append("schema target manifest has no runtime target for: " + ", ".join(missing))
    return errors
