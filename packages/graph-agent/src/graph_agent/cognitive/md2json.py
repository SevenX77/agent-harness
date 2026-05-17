"""V2.1 finish_task Markdown-to-dict facade."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class Md2JsonResult:
    """md2json parsing result for V2.1 finish_task."""

    data: dict[str, Any]
    validation_errors: list[dict[str, Any]]
    repaired: bool


_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^[-*]\s+([A-Za-z_][\w-]*):\s*(.*)$")


def parse_finish_markdown(
    markdown: str,
    output_schema: dict[str, Any] | None = None,
) -> Md2JsonResult:
    """Parse V2.1 finish_task Markdown into a dict and optionally validate it."""

    data = _parse_markdown_to_dict(markdown, output_schema)
    if output_schema is None:
        return Md2JsonResult(data=data, validation_errors=[], repaired=False)

    validator = Draft202012Validator(output_schema)
    errors = [_jsonschema_error(err) for err in sorted(validator.iter_errors(data), key=str)]
    return Md2JsonResult(data=data, validation_errors=errors, repaired=False)


def _parse_markdown_to_dict(
    markdown: str,
    output_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    properties = _schema_properties(output_schema)
    data: dict[str, Any] = {}

    for key, body in _split_heading_sections(markdown).items():
        bullet_data = _parse_bullets(body, properties)
        if bullet_data:
            data.update(bullet_data)

        normalized_key = _normalize_key(key)
        if normalized_key in properties or not bullet_data:
            schema = properties.get(normalized_key)
            data[normalized_key] = _coerce_value(_strip_outer_fence(body), schema)

    return data


def _split_heading_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_key: str | None = None

    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            current_key = _normalize_key(match.group(1))
            sections.setdefault(current_key, [])
            continue
        if current_key is not None:
            sections[current_key].append(line)

    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def _parse_bullets(body: str, properties: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for line in body.splitlines():
        match = _BULLET_RE.match(line.strip())
        if not match:
            continue
        key = _normalize_key(match.group(1))
        parsed[key] = _coerce_value(match.group(2).strip(), properties.get(key))
    return parsed


def _coerce_value(raw: str, schema: dict[str, Any] | None) -> Any:
    value = raw.strip()
    schema_type = schema.get("type") if isinstance(schema, dict) else None

    if _looks_like_json(value):
        try:
            return json.loads(_strip_outer_fence(value))
        except json.JSONDecodeError:
            return value

    if schema_type == "integer":
        try:
            return int(value)
        except ValueError:
            return value
    if schema_type == "number":
        try:
            return float(value)
        except ValueError:
            return value
    if schema_type == "boolean":
        lowered = value.lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    if schema_type == "array" and "," in value:
        return [item.strip() for item in value.split(",") if item.strip()]

    return value


def _strip_outer_fence(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _looks_like_json(value: str) -> bool:
    stripped = _strip_outer_fence(value)
    return (stripped.startswith("{") and stripped.endswith("}")) or (
        stripped.startswith("[") and stripped.endswith("]")
    )


def _schema_properties(output_schema: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(output_schema, dict):
        return {}
    properties = output_schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def _normalize_key(key: str) -> str:
    return key.strip().strip("#").strip().replace("-", "_")


def _jsonschema_error(error: Any) -> dict[str, Any]:
    return {
        "path": [str(part) for part in error.path],
        "schema_path": [str(part) for part in error.schema_path],
        "message": error.message,
        "validator": error.validator,
    }


__all__ = ["Md2JsonResult", "parse_finish_markdown"]
