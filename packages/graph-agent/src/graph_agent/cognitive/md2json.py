"""V2.1 finish_task Markdown-to-dict facade."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from graph_agent.tools.md_value import (
    looks_like_json_literal,
    parse_list_value,
    strip_outer_fence,
)


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
            data[normalized_key] = _coerce_value(strip_outer_fence(body), schema)

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

    # A declared array is read by the one authority on list-shaped Markdown
    # values, so this parser and ``tools/md_to_json.parse_md`` — both of which
    # run over the same ``business_data_md`` — cannot disagree about it.
    if schema_type == "array":
        return parse_list_value(value)

    if looks_like_json_literal(value):
        return _coerce_json_like(value)

    scalar = _coerce_schema_scalar(value, schema_type)
    if scalar is not _UNCOERCED:
        return scalar

    return value


_UNCOERCED = object()


def _coerce_json_like(value: str) -> Any:
    try:
        return json.loads(strip_outer_fence(value))
    except json.JSONDecodeError:
        return value


def _coerce_schema_scalar(value: str, schema_type: Any) -> Any:
    if schema_type == "integer":
        return _coerce_int_or_original(value)
    if schema_type == "number":
        return _coerce_float_or_original(value)
    if schema_type == "boolean":
        return _coerce_bool_or_uncoerced(value)
    return _UNCOERCED


def _coerce_int_or_original(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def _coerce_float_or_original(value: str) -> float | str:
    try:
        return float(value)
    except ValueError:
        return value


def _coerce_bool_or_uncoerced(value: str) -> bool | object:
    lowered = value.lower()
    if lowered in {"true", "yes", "1"}:
        return True
    if lowered in {"false", "no", "0"}:
        return False
    return _UNCOERCED


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
