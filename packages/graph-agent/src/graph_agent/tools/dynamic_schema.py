"""Schema-by-Example runtime support.

SKILL authors declare expected output shape with a markdown
``<output_example>`` block. This module parses that block into a small runtime
schema and validates ``finish_task(business_data_md=...)`` items without any
Pydantic BaseModel.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DynamicFieldDef:
    """One field parsed from an ``<output_example>`` bullet."""

    name: str
    type_hint: str
    required: bool = True
    default: str | None = None
    description: str = ""
    coerce_fn: Callable[[Any], Any] | None = field(default=None, repr=False)
    enum_values: list[str] | None = None


@dataclass
class DynamicSchemaDef:
    """Runtime schema parsed from one ``<output_example>`` block."""

    name: str
    item_header: str
    fields: list[DynamicFieldDef]


@dataclass
class DynamicBlockMeta:
    """Framework metadata for one parsed markdown block."""

    id: str


@dataclass
class DynamicParsedBlock:
    """One markdown block split into framework metadata and raw item data."""

    meta: DynamicBlockMeta
    data: dict[str, Any]


class OutputExampleParseError(ValueError):
    """Raised when an ``<output_example>`` block fails strict parsing."""


_OUTPUT_EXAMPLE_BLOCK_RE = re.compile(
    r'^\s*<output_example\s+name="([^"]+)">\s*(.*?)\s*</output_example>\s*$',
    re.DOTALL,
)
_FIELD_LINE_RE = re.compile(r"^\s*-\s+(\w+)\s+\(([^)]+)\)\s*:\s*(.*)$")
_SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_]\w*$")
_ITEM_HEADER_RE = re.compile(r"^##\s+(.+)$")
_FLAT_FIELD_RE = re.compile(r"^[-*•]\s+(\w+):\s*(.*)$")


def parse_output_example(block_text: str) -> DynamicSchemaDef:
    """Parse one strict ``<output_example>`` block into a dynamic schema."""

    match = _OUTPUT_EXAMPLE_BLOCK_RE.match(block_text or "")
    if not match:
        raise OutputExampleParseError(
            'Cannot find a standalone <output_example name="...">...</output_example> block'
        )

    schema_name = match.group(1).strip()
    if not _SCHEMA_NAME_RE.match(schema_name):
        raise OutputExampleParseError(
            f"Invalid output_example schema name {schema_name!r}. Use a Python-style identifier."
        )

    body = match.group(2)
    item_header: str | None = None
    fields: list[DynamicFieldDef] = []

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("##"):
            header_match = _ITEM_HEADER_RE.match(stripped)
            if not header_match:
                raise OutputExampleParseError(
                    f"Invalid item header in schema {schema_name}: {line!r}"
                )
            if item_header is not None:
                raise OutputExampleParseError(
                    f"Schema {schema_name} declares multiple ## item headers"
                )
            item_header = header_match.group(1).strip()
            continue
        if not stripped.startswith("-"):
            raise OutputExampleParseError(
                f"Unsupported non-bullet line in schema {schema_name}: {line!r}"
            )

        field_match = _FIELD_LINE_RE.match(line)
        if not field_match:
            raise OutputExampleParseError(
                "Bullet does not match strict pattern "
                "'- name (type[, required|optional[, default=X]]): desc'\n"
                f"Got: {line!r}\n"
                f"Schema: {schema_name}"
            )

        field_name = field_match.group(1)
        type_part = field_match.group(2).strip()
        description = field_match.group(3).strip()
        fields.append(_parse_field(field_name, type_part, description, schema_name))

    if item_header is None:
        raise OutputExampleParseError(
            f"Schema {schema_name} must include exactly one '## <header>' line"
        )
    if not fields:
        raise OutputExampleParseError(f"Schema {schema_name} must declare at least one field")

    return DynamicSchemaDef(name=schema_name, item_header=item_header, fields=fields)


def parse_md_simple(md_text: str) -> list[DynamicParsedBlock]:
    """Parse ``##`` markdown blocks into raw field dictionaries.

    This intentionally does no schema-aware coercion. DynamicSchemaDef performs
    coercion and validation in a separate deterministic pass.
    """

    blocks: list[DynamicParsedBlock] = []
    current_id: str | None = None
    current_data: dict[str, Any] = {}

    def flush() -> None:
        nonlocal current_id, current_data
        if current_id is not None:
            blocks.append(
                DynamicParsedBlock(
                    meta=DynamicBlockMeta(id=current_id),
                    data=current_data,
                )
            )
        current_id = None
        current_data = {}

    for raw_line in (md_text or "").splitlines():
        stripped = raw_line.strip()
        header_match = _ITEM_HEADER_RE.match(stripped)
        if header_match:
            flush()
            current_id = header_match.group(1).strip()
            current_data = {}
            continue
        if current_id is None or not stripped or stripped.startswith("```"):
            continue
        field_match = _FLAT_FIELD_RE.match(stripped)
        if field_match:
            current_data[field_match.group(1)] = field_match.group(2).strip()
        elif stripped.startswith(("-", "*", "•")):
            logger.warning("parse_md_simple: unrecognised bullet, skipping: %r", raw_line)

    flush()
    return blocks


def coerce_item_against_dynamic_schema(
    item_data: dict[str, Any],
    schema: DynamicSchemaDef,
) -> tuple[dict[str, Any], list[str]]:
    """Validate and coerce one item against a dynamic schema."""

    field_map = {field.name: field for field in schema.fields}
    coerced: dict[str, Any] = {}
    errors: list[str] = []

    for key, value in item_data.items():
        field_def = field_map.get(key)
        if field_def is None:
            errors.append(f"Unknown field '{key}' (not in <output_example>)")
            continue
        try:
            coerced[key] = _coerce_value(value, field_def)
        except (TypeError, ValueError) as exc:
            errors.append(
                f"Field '{key}' value {value!r} cannot coerce to {field_def.type_hint}: {exc}"
            )

    for field_def in schema.fields:
        if field_def.name in coerced:
            continue
        if field_def.name in item_data:
            continue
        if field_def.required:
            errors.append(f"Missing required field '{field_def.name}'")
        elif field_def.default is not None:
            try:
                coerced[field_def.name] = _coerce_value(field_def.default, field_def)
            except (TypeError, ValueError) as exc:
                errors.append(
                    f"Default for field '{field_def.name}' cannot coerce to "
                    f"{field_def.type_hint}: {exc}"
                )

    return coerced, errors


def validate_against_dynamic_schema(
    item_data: dict[str, Any],
    schema: DynamicSchemaDef,
) -> list[str]:
    """Return validation errors for one item. Empty list means valid."""

    _, errors = coerce_item_against_dynamic_schema(item_data, schema)
    return errors


def render_dynamic_schema_output_format(schema: DynamicSchemaDef) -> str:
    """Render a dynamic schema as the prompt-side ``<output_format>`` block."""

    template_lines = [
        "请按以下结构输出 business_data_md（一个或多个 `##` 块，每块对应一个 "
        f"{schema.name} 实例）：",
        "",
        "```markdown",
        f"## {schema.item_header}",
    ]
    for field_def in schema.fields:
        template_lines.append(f"- {field_def.name}: <值>")
    template_lines.append("```")

    reference_lines = ["", "字段说明："]
    for field_def in schema.fields:
        required_marker = "（必填）" if field_def.required else "（可选）"
        default = f"，默认值 `{field_def.default}`" if field_def.default is not None else ""
        reference_lines.append(
            f"- **{field_def.name}** {required_marker}: "
            f"`{field_def.type_hint}`{default} — {field_def.description or '（无描述）'}"
        )

    return "\n".join(template_lines + reference_lines)


def _parse_field(
    name: str,
    type_part: str,
    description: str,
    schema_name: str,
) -> DynamicFieldDef:
    parts = _split_top_level_commas(type_part)
    if not parts:
        raise OutputExampleParseError(f"Field {name} in schema {schema_name} lacks a type")

    type_hint = parts[0]
    coerce_fn, enum_values = _build_type_runtime(type_hint, name)
    required = True
    default: str | None = None

    for qualifier in parts[1:]:
        if qualifier == "required":
            required = True
        elif qualifier == "optional":
            required = False
        elif qualifier.startswith("default="):
            default = qualifier[len("default=") :]
        else:
            raise OutputExampleParseError(
                f"Unknown qualifier {qualifier!r} in field {name}. "
                "Allowed: required / optional / default=X"
            )

    return DynamicFieldDef(
        name=name,
        type_hint=type_hint,
        required=required,
        default=default,
        description=description,
        coerce_fn=coerce_fn,
        enum_values=enum_values,
    )


def _split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth < 0:
                raise OutputExampleParseError(f"Unbalanced brackets in type declaration {text!r}")
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if depth != 0:
        raise OutputExampleParseError(f"Unbalanced brackets in type declaration {text!r}")
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _build_type_runtime(
    type_hint: str,
    field_name: str,
) -> tuple[Callable[[Any], Any], list[str] | None]:
    if type_hint == "int":
        return _coerce_int, None
    if type_hint == "float":
        return _coerce_float, None
    if type_hint == "str":
        return lambda value: "" if value is None else str(value), None
    if type_hint == "bool":
        return _coerce_bool, None
    if type_hint.startswith("Literal[") and type_hint.endswith("]"):
        enum_values = [
            value.strip().strip("'\"")
            for value in type_hint[len("Literal[") : -1].split(",")
            if value.strip()
        ]
        if not enum_values:
            raise OutputExampleParseError(
                f"Literal type for field {field_name} must list at least one value"
            )
        return str, enum_values
    if type_hint.startswith("list[") and type_hint.endswith("]"):
        inner_hint = type_hint[len("list[") : -1].strip()
        inner_coerce, inner_enum = _build_type_runtime(inner_hint, field_name)

        def coerce_list(value: Any) -> list[Any]:
            raw_values = value if isinstance(value, list) else str(value).split(",")
            items = [inner_coerce(v.strip() if isinstance(v, str) else v) for v in raw_values]
            if inner_enum is not None:
                for item in items:
                    if str(item) not in inner_enum:
                        raise ValueError(f"{item!r} not in {inner_enum}")
            return items

        return coerce_list, None
    raise OutputExampleParseError(
        f"Unsupported type {type_hint!r} for field {field_name}. "
        "Allowed: int / float / str / bool / Literal[...] / list[X]"
    )


def _coerce_value(value: Any, field_def: DynamicFieldDef) -> Any:
    coerced = value if field_def.coerce_fn is None else field_def.coerce_fn(value)
    if field_def.enum_values is not None and str(coerced) not in field_def.enum_values:
        raise ValueError(f"{coerced!r} not in {field_def.enum_values}")
    return coerced


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("bool is not accepted as int")
    return int(value)


def _coerce_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("bool is not accepted as float")
    return float(value)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    raise ValueError("expected one of true/false/1/0/yes/no")


__all__ = [
    "DynamicFieldDef",
    "DynamicSchemaDef",
    "OutputExampleParseError",
    "coerce_item_against_dynamic_schema",
    "parse_md_simple",
    "parse_output_example",
    "render_dynamic_schema_output_format",
    "validate_against_dynamic_schema",
]
