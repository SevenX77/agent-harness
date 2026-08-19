"""SchemaEngine — unified parsing and validation for SKILL output schemas."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import textwrap
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from types import GenericAlias
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic import ValidationError as PydanticValidationError

from graph_agent.core.exceptions import SkillCompilationError
from graph_agent.tools.dynamic_schema import OutputExampleParseError, parse_output_example

logger = logging.getLogger(__name__)


class SchemaParseError(SkillCompilationError):
    """Raised when a SKILL output schema fragment cannot be parsed."""


@dataclass(frozen=True)
class ListType:
    """Internal marker for a list item type before Pydantic model creation."""

    item_type: Any


@dataclass(frozen=True)
class SchemaObject:
    """Hashable intermediate schema representation used by SchemaEngine.

    ``fields`` stores ``(field_name, type_descriptor)`` pairs. A descriptor may
    be a Python type, another ``SchemaObject`` for nested objects, or ``ListType``
    for list fields. The mutable raw schema dict is deliberately excluded from
    equality/hash so the object remains safe as an ``lru_cache`` key.
    """

    fields: tuple[tuple[str, Any], ...] = ()
    required_fields: frozenset[str] = frozenset()
    output_example_md: str | None = None
    raw_schema_dict: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)
    field_descriptions: tuple[tuple[str, str], ...] = ()
    field_defaults: tuple[tuple[str, Any], ...] = ()
    schema_name: str = "BusinessSchema"
    item_header: str | None = None

    @property
    def raw(self) -> dict[str, Any]:
        """Backward-compatible raw schema view."""

        return self.raw_schema_dict

    @property
    def field_map(self) -> dict[str, Any]:
        """Return fields as a dict for tests and callers that need lookup."""

        return dict(self.fields)

    @property
    def description_map(self) -> dict[str, str]:
        """Return field descriptions as a dict."""

        return dict(self.field_descriptions)

    @property
    def default_map(self) -> dict[str, Any]:
        """Return optional defaults as a dict."""

        return dict(self.field_defaults)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating data against a SchemaObject."""

    ok: bool
    errors: tuple[str, ...] = ()
    field_errors: dict[str, str] = field(default_factory=dict)
    parsed: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """Backward-compatible alias used by older T1 tests/callers."""

        return self.ok


@dataclass(frozen=True)
class _SchemaLine:
    indent: int
    text: str
    line_no: int


_OUTPUT_EXAMPLE_BLOCK_RE = re.compile(
    r'<output_example\s+name="[^"]+">\s*.*?\s*</output_example>',
    re.DOTALL,
)
_NAMED_BLOCK_RE = re.compile(r"^(\s*)(output_schema|output_example):\s*(.*)$")
_FIELD_RE = re.compile(r"^(?:-\s*)?([A-Za-z_]\w*)(\?)?\s*:\s*(.*)$")
_SCHEMA_NAME_RE = re.compile(r"^[A-Za-z_]\w*$")

_PRIMITIVE_TYPES: dict[str, Any] = {
    "Any": Any,
    "any": Any,
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "float": float,
    "number": float,
    "bool": bool,
    "boolean": bool,
    "dict": dict[str, Any],
    "object": dict[str, Any],
}


@dataclass(frozen=True)
class UnionType:
    """JSON Schema type-array member union ('null' arrives as ``type(None)``).

    A marker like ``ListType`` rather than an eager ``X | Y`` annotation:
    members may be ``ListType``/``SchemaObject`` descriptors that only become
    annotations inside ``_descriptor_to_annotation``, and building models
    eagerly here would bypass the cached-model path.
    """

    members: tuple[Any, ...]


class SchemaEngine:
    """Parse schema fragments, generate Pydantic models, and validate data."""

    def parse_from_md(self, md_content: str) -> SchemaObject:
        """Parse ``output_schema`` or ``output_example`` Markdown/YAML text."""

        fragment = _extract_schema_fragment(md_content)
        if not fragment.strip():
            return SchemaObject(raw_schema_dict={})

        output_example = _extract_output_example(fragment)
        if output_example is not None:
            return _parse_output_example_to_schema(output_example)

        json_schema = _try_parse_json_schema(fragment)
        if json_schema is not None:
            return _schema_from_mapping(json_schema)

        lines = _normalise_schema_lines(fragment)
        if not lines:
            return SchemaObject(raw_schema_dict={})
        return _parse_schema_object(lines, schema_name="BusinessSchema")

    def get_pydantic_model(self, schema: SchemaObject) -> type[BaseModel]:
        """Return an ``lru_cache``-backed dynamic Pydantic model class."""

        return _get_pydantic_model_cached(schema)

    def validate(self, data: Any, schema: SchemaObject) -> ValidationResult:
        """Validate arbitrary data against ``schema`` using Pydantic."""

        model = self.get_pydantic_model(schema)
        try:
            parsed_model = model.model_validate(data)
        except PydanticValidationError as exc:
            errors: list[str] = []
            field_errors: dict[str, str] = {}
            for detail in exc.errors():
                loc = ".".join(str(part) for part in detail.get("loc", ())) or "__root__"
                msg = str(detail.get("msg", "validation error"))
                errors.append(f"{loc}: {msg}")
                field_errors[loc] = msg
            return ValidationResult(
                ok=False,
                errors=tuple(errors),
                field_errors=field_errors,
            )

        return ValidationResult(
            ok=True,
            parsed=dump_without_invented_nones(parsed_model),
        )

    def get_json_schema(self, schema: SchemaObject) -> dict[str, Any]:
        """Return JSON Schema generated from the dynamic Pydantic model."""

        model = self.get_pydantic_model(schema)
        return model.model_json_schema()


def dump_without_invented_nones(parsed_model: BaseModel) -> dict[str, Any]:
    """Dump a validated model without inventing fields the submitter omitted.

    Declared defaults must materialise (they are real values), but an optional
    field with no default dumps as None — and downstream jsonschema validation
    rejects null where the schema declares object/array. Only keys that were
    NOT submitted AND resolved to None are dropped, at every nesting depth
    (a parent's ``model_dump`` materialises nested optionals too).
    """
    dumped = _prune_invented_nones(parsed_model)
    return dumped if isinstance(dumped, dict) else {}


def _prune_invented_nones(value: Any) -> Any:
    if isinstance(value, BaseModel):
        submitted = value.model_fields_set
        return {
            key: _prune_invented_nones(getattr(value, key))
            for key in type(value).model_fields
            if not (getattr(value, key) is None and key not in submitted)
        }
    if isinstance(value, dict):
        return {key: _prune_invented_nones(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_prune_invented_nones(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_prune_invented_nones(item) for item in value)
    return value


@lru_cache(maxsize=128)
def _get_pydantic_model_cached(schema: SchemaObject) -> type[BaseModel]:
    field_definitions: dict[str, Any] = {}
    descriptions = schema.description_map
    defaults = schema.default_map

    for field_name, type_descriptor in schema.fields:
        annotation = _descriptor_to_annotation(type_descriptor)
        default: Any
        if field_name in schema.required_fields:
            default = Field(..., description=descriptions.get(field_name))
        else:
            default = Field(defaults.get(field_name), description=descriptions.get(field_name))
            annotation = _optional_annotation(annotation)
        field_definitions[field_name] = (annotation, default)

    model_name = _model_name_for_schema(schema)
    return cast(
        type[BaseModel],
        create_model(
            model_name,
            __config__=ConfigDict(extra="forbid", validate_default=True),
            **field_definitions,
        ),
    )


def _extract_schema_fragment(md_content: str) -> str:
    text = md_content or ""
    output_example = _extract_output_example(text)
    if output_example is not None:
        return output_example

    named = _extract_named_yaml_block(text, "output_example")
    if named is not None:
        return named
    named = _extract_named_yaml_block(text, "output_schema")
    if named is not None:
        return named
    return text


def _extract_output_example(text: str) -> str | None:
    match = _OUTPUT_EXAMPLE_BLOCK_RE.search(text or "")
    if match is None:
        return None
    return textwrap.dedent(match.group(0)).strip()


def _extract_named_yaml_block(text: str, key: str) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = _NAMED_BLOCK_RE.match(line)
        if match is None or match.group(2) != key:
            continue

        base_indent = len(match.group(1))
        tail = match.group(3).strip()
        if tail and tail != "|":
            return tail.strip("'\"")

        block_lines: list[str] = []
        for raw_child in lines[index + 1 :]:
            if not raw_child.strip():
                block_lines.append(raw_child)
                continue
            child_indent = len(raw_child) - len(raw_child.lstrip(" "))
            if child_indent <= base_indent:
                break
            block_lines.append(raw_child)
        return textwrap.dedent("\n".join(block_lines)).strip()
    return None


def _try_parse_json_schema(fragment: str) -> dict[str, Any] | None:
    stripped = fragment.strip()
    if not stripped.startswith("{"):
        return None
    try:
        loaded = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise SchemaParseError(f"Invalid JSON output schema: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SchemaParseError("JSON output schema must be an object")
    return cast(dict[str, Any], loaded)


def _parse_output_example_to_schema(block_text: str) -> SchemaObject:
    try:
        dynamic_schema = parse_output_example(block_text)
    except OutputExampleParseError as exc:
        raise SchemaParseError(f"Invalid output_example schema: {exc}") from exc

    fields: list[tuple[str, Any]] = []
    required: set[str] = set()
    descriptions: list[tuple[str, str]] = []
    defaults: list[tuple[str, Any]] = []
    seen: set[str] = set()

    for field_def in dynamic_schema.fields:
        if field_def.name in seen:
            raise SchemaParseError(f"Duplicate field {field_def.name!r} in output_example")
        seen.add(field_def.name)
        descriptor = _parse_type_expr(field_def.type_hint)
        fields.append((field_def.name, descriptor))
        descriptions.append((field_def.name, field_def.description))
        if field_def.required:
            required.add(field_def.name)
        elif field_def.default is not None:
            defaults.append((field_def.name, _coerce_output_example_default(field_def)))

    return SchemaObject(
        fields=tuple(fields),
        required_fields=frozenset(required),
        output_example_md=block_text,
        raw_schema_dict=_raw_schema_dict(fields, required, descriptions),
        field_descriptions=tuple(descriptions),
        field_defaults=tuple(defaults),
        schema_name=dynamic_schema.name,
        item_header=dynamic_schema.item_header,
    )


def _schema_from_mapping(
    mapping: dict[str, Any], *, schema_name: str = "BusinessSchema"
) -> SchemaObject:
    fields: list[tuple[str, Any]] = []
    required: set[str] = set()

    properties = mapping.get("properties")
    if isinstance(properties, dict):
        required_values = mapping.get("required", [])
        if not isinstance(required_values, list):
            raise SchemaParseError("JSON Schema 'required' must be a list")
        required = {str(value) for value in required_values}
        for name, prop_schema in properties.items():
            fields.append((str(name), _descriptor_from_json_value(prop_schema)))
        return SchemaObject(
            fields=tuple(fields),
            required_fields=frozenset(required),
            raw_schema_dict=dict(mapping),
            schema_name=schema_name,
        )

    for name, value in mapping.items():
        fields.append((str(name), _descriptor_from_json_value(value)))
        required.add(str(name))

    if not fields:
        raise SchemaParseError("Schema must declare at least one field")
    return SchemaObject(
        fields=tuple(fields),
        required_fields=frozenset(required),
        raw_schema_dict=dict(mapping),
        schema_name=schema_name,
    )


def _coerce_output_example_default(field_def: Any) -> Any:
    if field_def.coerce_fn is None:
        return field_def.default
    try:
        return field_def.coerce_fn(field_def.default)
    except (TypeError, ValueError) as exc:
        raise SchemaParseError(
            f"Default for field {field_def.name!r} cannot coerce to {field_def.type_hint}: {exc}"
        ) from exc


def _descriptor_from_json_value(value: Any) -> Any:
    if isinstance(value, str):
        descriptor, _ = _parse_declared_type(value)
        return descriptor
    if isinstance(value, dict):
        return _descriptor_from_json_mapping(cast(dict[str, Any], value))
    if isinstance(value, list):
        return _descriptor_from_json_list(value)
    raise SchemaParseError(f"Unsupported schema value {value!r}")


def _descriptor_from_json_mapping(value: dict[str, Any]) -> Any:
    if "enum" in value:
        enum_values = value["enum"]
        if not isinstance(enum_values, list):
            raise SchemaParseError("JSON Schema 'enum' must be a list")
        return _literal_from_json_enum(enum_values)
    schema_type = value.get("type")
    if isinstance(schema_type, list):
        return _descriptor_from_json_type_array(value, schema_type)
    if schema_type == "array":
        items = value.get("items", {})
        item_descriptor = Any if items == {} else _descriptor_from_json_value(items)
        return ListType(item_descriptor)
    if schema_type == "object":
        if isinstance(value.get("properties"), dict):
            return _schema_from_mapping(value)
        return dict[str, Any]
    if isinstance(schema_type, str) and set(value).issubset({"type", "description"}):
        descriptor, _ = _parse_declared_type(schema_type)
        return descriptor
    if isinstance(value.get("properties"), dict):
        return _schema_from_mapping(value)
    return _schema_from_mapping(value)


def _descriptor_from_json_type_array(value: dict[str, Any], types: list[Any]) -> Any:
    """JSON Schema 'type' as an ARRAY = a union of the named types.

    The standard way to declare nullability (`type: [string, "null"]`).
    Previously this fell through to the list-shorthand branch and died with a
    message about item counts (field evidence: predict
    2026-08-19T05-40-31_498a3bfe on story-deconstruction-v3-lab).
    """
    names = [t for t in types if isinstance(t, str)]
    if not names or len(names) != len(types):
        raise SchemaParseError("JSON Schema 'type' array must contain type names")
    members: list[Any] = []
    for name in names:
        if name == "null":
            members.append(type(None))
            continue
        members.append(_descriptor_from_json_mapping({**value, "type": name}))
    if len(members) == 1:
        return members[0]
    return UnionType(tuple(members))


def _descriptor_from_json_list(value: list[Any]) -> Any:
    if len(value) != 1:
        raise SchemaParseError("List schema shorthand must contain exactly one item type")
    return ListType(_descriptor_from_json_value(value[0]))


def _literal_from_json_enum(values: list[Any]) -> Any:
    if not values:
        raise SchemaParseError("JSON Schema 'enum' must contain at least one value")
    for value in values:
        if not isinstance(value, str | int | float | bool) and value is not None:
            raise SchemaParseError("JSON Schema 'enum' only supports scalar values")
    return cast(Any, Literal).__getitem__(tuple(values))


def _normalise_schema_lines(fragment: str) -> list[_SchemaLine]:
    dedented = textwrap.dedent(fragment).strip("\n")
    lines: list[_SchemaLine] = []
    for line_no, raw_line in enumerate(dedented.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped in {"---", "```", "```markdown", "```yaml"}:
            continue
        if stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append(_SchemaLine(indent=indent, text=stripped, line_no=line_no))
    return lines


def _parse_schema_object(lines: list[_SchemaLine], *, schema_name: str) -> SchemaObject:
    fields, required, descriptions = _parse_field_block(lines, start=0, base_indent=lines[0].indent)
    if not fields:
        raise SchemaParseError("Schema must declare at least one field")
    return SchemaObject(
        fields=tuple(fields),
        required_fields=frozenset(required),
        raw_schema_dict=_raw_schema_dict(fields, required, descriptions),
        field_descriptions=tuple(descriptions),
        schema_name=schema_name,
    )


def _parse_field_block(
    lines: list[_SchemaLine],
    *,
    start: int,
    base_indent: int,
) -> tuple[list[tuple[str, Any]], set[str], list[tuple[str, str]]]:
    fields: list[tuple[str, Any]] = []
    required: set[str] = set()
    descriptions: list[tuple[str, str]] = []
    seen: set[str] = set()
    index = start

    while index < len(lines):
        line = lines[index]
        if line.indent < base_indent:
            break
        if line.indent > base_indent:
            raise SchemaParseError(f"Unexpected indentation at line {line.line_no}: {line.text!r}")

        match = _FIELD_RE.match(line.text)
        if match is None:
            raise SchemaParseError(f"Invalid schema line {line.line_no}: {line.text!r}")

        name = match.group(1)
        optional_marker = bool(match.group(2))
        type_text = _strip_inline_comment(match.group(3).strip())
        if name in seen:
            raise SchemaParseError(f"Duplicate field {name!r}")
        seen.add(name)

        child_start = index + 1
        child_end = _find_child_end(lines, child_start, line.indent)
        if type_text:
            descriptor, type_optional = _parse_declared_type(type_text)
            index += 1
        elif child_start < child_end:
            descriptor = _parse_child_descriptor(lines[child_start:child_end], name)
            type_optional = False
            index = child_end
        else:
            raise SchemaParseError(f"Field {name!r} is missing a type declaration")

        fields.append((name, descriptor))
        if not (optional_marker or type_optional):
            required.add(name)
        descriptions.append((name, ""))

    return fields, required, descriptions


def _strip_inline_comment(text: str) -> str:
    return text.split(" #", 1)[0].strip()


def _find_child_end(lines: list[_SchemaLine], start: int, parent_indent: int) -> int:
    index = start
    while index < len(lines) and lines[index].indent > parent_indent:
        index += 1
    return index


def _parse_child_descriptor(child_lines: list[_SchemaLine], field_name: str) -> Any:
    first = child_lines[0]
    if first.text.startswith("- "):
        return _parse_list_child_descriptor(child_lines, field_name)
    return _parse_schema_object(child_lines, schema_name=_schema_name_from_field(field_name))


def _parse_list_child_descriptor(child_lines: list[_SchemaLine], field_name: str) -> ListType:
    first_text = child_lines[0].text[2:].strip()
    if first_text and ":" not in first_text:
        descriptor, _ = _parse_declared_type(first_text)
        return ListType(descriptor)

    normalised: list[_SchemaLine] = []
    first_indent = child_lines[0].indent
    for index, line in enumerate(child_lines):
        text = line.text
        if index == 0 and text.startswith("- "):
            text = text[2:].strip()
            indent = 0
        else:
            indent = max(0, line.indent - first_indent - 2)
        normalised.append(_SchemaLine(indent=indent, text=text, line_no=line.line_no))
    item_schema = _parse_schema_object(
        normalised,
        schema_name=f"{_schema_name_from_field(field_name)}Item",
    )
    return ListType(item_schema)


def _parse_declared_type(type_text: str) -> tuple[Any, bool]:
    cleaned = type_text.strip()
    optional = False
    if cleaned.endswith("?"):
        optional = True
        cleaned = cleaned[:-1].strip()
    if cleaned.startswith("Optional[") and cleaned.endswith("]"):
        optional = True
        cleaned = cleaned[len("Optional[") : -1].strip()
    if " | None" in cleaned:
        optional = True
        cleaned = cleaned.replace(" | None", "").strip()
    if "None | " in cleaned:
        optional = True
        cleaned = cleaned.replace("None | ", "").strip()
    return _parse_type_expr(cleaned), optional


def _parse_type_expr(type_text: str) -> Any:
    type_hint = type_text.strip()
    if not type_hint:
        raise SchemaParseError("Empty type declaration")
    if type_hint in _PRIMITIVE_TYPES:
        return _PRIMITIVE_TYPES[type_hint]
    if type_hint.startswith("list[") and type_hint.endswith("]"):
        return ListType(_parse_type_expr(type_hint[len("list[") : -1].strip()))
    if type_hint.startswith("List[") and type_hint.endswith("]"):
        return ListType(_parse_type_expr(type_hint[len("List[") : -1].strip()))
    if type_hint.startswith("Literal[") and type_hint.endswith("]"):
        values = [
            part.strip().strip("'\"")
            for part in type_hint[len("Literal[") : -1].split(",")
            if part.strip()
        ]
        if not values:
            raise SchemaParseError("Literal[...] must contain at least one value")
        return cast(Any, Literal).__getitem__(tuple(values))
    raise SchemaParseError(
        f"Unsupported schema type {type_hint!r}. "
        "Allowed: str/int/float/bool/Any/dict/list[T]/Literal[...]"
    )


def _descriptor_to_annotation(descriptor: Any) -> Any:
    if isinstance(descriptor, SchemaObject):
        return _get_pydantic_model_cached(descriptor)
    if isinstance(descriptor, ListType):
        return GenericAlias(list, (_descriptor_to_annotation(descriptor.item_type),))
    if isinstance(descriptor, UnionType):
        annotation = _descriptor_to_annotation(descriptor.members[0])
        for member in descriptor.members[1:]:
            annotation = annotation | _descriptor_to_annotation(member)
        return annotation
    return descriptor


def _optional_annotation(annotation: Any) -> Any:
    if annotation is Any:
        return Any
    return annotation | None


def _raw_schema_dict(
    fields: list[tuple[str, Any]],
    required: set[str],
    descriptions: list[tuple[str, str]],
) -> dict[str, Any]:
    description_map = dict(descriptions)
    properties: dict[str, Any] = {}
    for name, descriptor in fields:
        properties[name] = _descriptor_to_raw(descriptor, description_map.get(name, ""))
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(required),
    }


def _descriptor_to_raw(descriptor: Any, description: str = "") -> dict[str, Any]:
    if isinstance(descriptor, SchemaObject):
        raw = dict(descriptor.raw_schema_dict)
    elif isinstance(descriptor, ListType):
        raw = {"type": "array", "items": _descriptor_to_raw(descriptor.item_type)}
    elif descriptor is str:
        raw = {"type": "string"}
    elif descriptor is int:
        raw = {"type": "integer"}
    elif descriptor is float:
        raw = {"type": "number"}
    elif descriptor is bool:
        raw = {"type": "boolean"}
    elif descriptor is Any:
        raw = {}
    else:
        raw = {"type": "string"}
    if description:
        raw["description"] = description
    return raw


def _canonical_key(value: Any) -> str:
    """A string that is equal for equal values, in every process.

    `repr()` is not that string. Two things it pulls in break the property this
    function exists to give `_model_name_for_schema`:

    * **Unordered containers.** `SchemaObject.required_fields` is a `frozenset`,
      and a frozenset's iteration order follows the hashes of its elements. Str
      hashing is randomised per interpreter (`PYTHONHASHSEED`), so the same
      schema reprs differently in different processes.
    * **Fields excluded from equality.** `raw_schema_dict` is `compare=False`,
      yet a dataclass repr still prints it -- so two `SchemaObject`s that are
      `==` could repr differently.

    So the key is built explicitly: unordered containers are sorted, mappings
    are emitted by sorted key, and only the fields that define equality are
    read. Types are named by module and qualname rather than repr, which is
    stable but says `<class 'str'>`.

    Borrowed from JSON Canonicalization Scheme (RFC 8785): fix an order for
    members, then serialise through JSON so the encoding itself is injective --
    a digest over an unordered or ambiguously delimited rendering addresses
    nothing. Not borrowed: its number and Unicode rules, and its promise of
    interoperability. This key is never parsed back, never stored, and never
    compared across versions of this module; it only has to be injective and
    stable within one build.
    """

    if isinstance(value, SchemaObject):
        return _canonical_schema_key(value)
    if isinstance(value, ListType):
        return f"list[{_canonical_key(value.item_type)}]"
    if isinstance(value, UnionType):
        return "union[" + ",".join(_canonical_key(member) for member in value.members) + "]"
    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"
    if isinstance(value, Mapping):
        items = sorted((str(key), _canonical_key(item)) for key, item in value.items())
        return "{" + ",".join(f"{key}:{item}" for key, item in items) + "}"
    if isinstance(value, (set, frozenset)):
        return "{" + ",".join(sorted(_canonical_key(item) for item in value)) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_key(item) for item in value) + "]"
    return repr(value)


def _canonical_schema_key(schema: SchemaObject) -> str:
    return json.dumps(
        [
            schema.schema_name,
            [[name, _canonical_key(descriptor)] for name, descriptor in schema.fields],
            sorted(schema.required_fields),
            [[name, text] for name, text in schema.field_descriptions],
            [[name, _canonical_key(value)] for name, value in schema.field_defaults],
            schema.item_header,
            schema.output_example_md,
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _model_name_for_schema(schema: SchemaObject) -> str:
    base = schema.schema_name if _SCHEMA_NAME_RE.match(schema.schema_name) else "BusinessSchema"
    digest = hashlib.sha256(_canonical_schema_key(schema).encode("utf-8")).hexdigest()[:8]
    return f"{base}_{digest}"


def _schema_name_from_field(field_name: str) -> str:
    parts = [part.capitalize() for part in field_name.split("_") if part]
    return "".join(parts) or "Nested"


__all__ = [
    "SchemaEngine",
    "SchemaObject",
    "SchemaParseError",
    "ValidationResult",
]
