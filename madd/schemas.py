"""JSON Schema loading and a small structural validator.

The validator intentionally supports only the subset used by the schemas
in madd/schemas/: type (including a list of types), required, properties,
items, and enum. It does not claim full JSON Schema compliance. It returns
structured errors and never raises on the first problem.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).parent / "schemas"
SCHEMA_NAMES = ["frame", "claim", "dossier", "consensus_spec", "candidate",
                "gate_report", "run_manifest"]


def load_schema(name: str) -> dict:
    path = SCHEMA_DIR / (name + ".json")
    if not path.exists():
        raise ValueError("unknown schema name: " + name)
    return json.loads(path.read_text(encoding="utf-8"))


def _type_ok(value, expected) -> bool:
    types = expected if isinstance(expected, list) else [expected]
    for t in types:
        if t == "object" and isinstance(value, dict):
            return True
        if t == "array" and isinstance(value, list):
            return True
        if t == "string" and isinstance(value, str):
            return True
        if t == "boolean" and isinstance(value, bool):
            return True
        if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if t == "null" and value is None:
            return True
    return False


def validate(instance, schema: dict, path: str = "$") -> list:
    """Validate instance against the supported schema subset. Returns errors."""
    errors = []
    expected_type = schema.get("type")
    if expected_type is not None and not _type_ok(instance, expected_type):
        errors.append({"path": path, "code": "type_mismatch",
                       "message": "expected type " + str(expected_type)})
        return errors
    if "enum" in schema and instance not in schema["enum"]:
        errors.append({"path": path, "code": "enum_mismatch",
                       "message": "value not in enum " + str(schema["enum"])})
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append({"path": path + "." + req, "code": "missing_required",
                               "message": "required field missing: " + req})
        props = schema.get("properties", {})
        for key, subschema in props.items():
            if key in instance:
                errors.extend(validate(instance[key], subschema, path + "." + key))
    if isinstance(instance, list) and "items" in schema:
        for idx, item in enumerate(instance):
            errors.extend(validate(item, schema["items"], path + "[" + str(idx) + "]"))
    return errors


def validate_artifact(schema_name: str, artifact: dict) -> list:
    return validate(artifact, load_schema(schema_name))
