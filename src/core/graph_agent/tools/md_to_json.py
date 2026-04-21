"""MD Parser — structured Markdown → Pydantic model list.

Converts LLM-generated Markdown (## item boundaries, bullet fields) into validated
Pydantic model instances, with optional LLM surgical patching for the ~5-10% of
items that fail validation.

Public API:
    parse_md(md_text, schema) → list[dict]  # raw field extraction
    diagnose(items, schema) → DiagnosticReport  # per-item Pydantic check
    md_to_json(md_text, schema) → list[T]  # unified: parse + diagnose + patch
"""
from __future__ import annotations

import importlib
import logging
import re
import sys
import types
import typing
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from ..core.runner import run_skill

logger = logging.getLogger(__name__)


def _resolve_schema_from_path(path: str) -> type[BaseModel]:
    """Resolve a dotted path like 'a.b.Class' to the BaseModel subclass.

    The skill loader registers dynamically loaded modules in sys.modules under
    a namespaced key (``_graph_agent_skill_.<hash>.<module>``); classes defined
    in those modules carry the namespaced ``__module__``. Looking up via
    ``sys.modules`` first avoids importlib re-import attempts that fail on
    namespaced dotted paths.
    """
    module_str, _, cls_name = path.rpartition(".")
    if not module_str or not cls_name:
        raise ValueError(f"invalid schema path: {path!r}")
    module = sys.modules.get(module_str)
    if module is None:
        module = importlib.import_module(module_str)
    cls = getattr(module, cls_name, None)
    if cls is None:
        raise ValueError(f"schema path {path!r} resolved module has no attribute {cls_name!r}")
    if not (isinstance(cls, type) and issubclass(cls, BaseModel)):
        got = type(cls).__name__
        raise ValueError(f"schema path {path!r} is not a BaseModel subclass (got {got})")
    return cls

# Path to Patch Agent SKILL.md — resolved once at module load
_PATCH_SKILL_MD: Path = (
    Path(__file__).resolve().parent.parent / "skills" / "builtin" / "md-patch" / "SKILL.md"
)


# ─── Diagnostic data structures ──────────────────────────────────────────────

@dataclass
class FieldError:
    """One validation error for a single field within an item."""

    field: str  # Pydantic loc path, e.g. "climax_intensity" or "lines.0.speaker"
    error: str  # Human-readable error message
    error_kind: Literal["structural", "semantic"] = "semantic"


@dataclass
class ItemError:
    """All validation errors for one parsed item."""

    index: int  # position in the items list
    item_id: str | None  # ## header text stored as _md_id, may be None
    fields: list[FieldError] = dc_field(default_factory=list)


@dataclass
class DiagnosticReport:
    """Result of per-item Pydantic validation."""

    valid_items: list[BaseModel]
    errors: list[ItemError]

    @property
    def all_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def has_structural_errors(self) -> bool:
        return any(
            fe.error_kind == "structural"
            for ie in self.errors
            for fe in ie.fields
        )

    @property
    def has_semantic_errors(self) -> bool:
        return any(
            fe.error_kind == "semantic"
            for ie in self.errors
            for fe in ie.fields
        )

    @property
    def semantic_only(self) -> bool:
        """True when all errors are semantic (md-patch cannot help)."""
        return len(self.errors) > 0 and not self.has_structural_errors

    def to_prompt_string(self) -> str:
        """Render a human-readable diagnostic report for the Patch Agent prompt."""
        if self.all_valid:
            return "所有 item 验证通过，无错误。"
        lines: list[str] = [
            f"验证结果：{len(self.valid_items)} 个通过，{len(self.errors)} 个有错误。",
            "",
        ]
        for item_err in self.errors:
            id_label = (
                f"_md_id={item_err.item_id!r}"
                if item_err.item_id
                else f"index={item_err.index}"
            )
            lines.append(f"【错误 Item {item_err.index}】{id_label}")
            structural = [fe for fe in item_err.fields if fe.error_kind == "structural"]
            semantic = [fe for fe in item_err.fields if fe.error_kind == "semantic"]
            if structural:
                lines.append(" ┌─ 格式错误（md-patch 可修复）")
                for fe in structural:
                    lines.append(f" │ 字段 `{fe.field}`: {fe.error}")
            if semantic:
                lines.append(" ┌─ 语义错误（需重新生成）")
                for fe in semantic:
                    lines.append(f" │ 字段 `{fe.field}`: {fe.error}")
            lines.append("")
        return "\n".join(lines)


class SemanticValidationError(ValueError):
    """Raised by md_to_json() when all validation errors are semantic.

    md-patch cannot fix semantic errors (e.g. '极高' where int expected).
    The calling tool should catch this and return the diagnostic report to the
    Agent loop for re-generation.
    """

    def __init__(self, report: DiagnosticReport) -> None:
        self.report = report
        super().__init__(report.to_prompt_string())


# ─── Type annotation helpers ──────────────────────────────────────────────────

def _unwrap_optional(annotation: Any) -> Any:
    """For T | None or Optional[T], return T. Otherwise return annotation."""
    # typing.Optional[T] is typing.Union[T, None]
    if typing.get_origin(annotation) is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    # Python 3.10+ union syntax: X | Y
    if isinstance(annotation, types.UnionType):
        args = [a for a in annotation.__args__ if a is not type(None)]  # type: ignore[union-attr]
        if len(args) == 1:
            return args[0]
    return annotation


def _is_list_annotation(annotation: Any) -> bool:
    """Return True if annotation resolves to list[...] (after unwrapping Optional)."""
    return typing.get_origin(_unwrap_optional(annotation)) is list


def _get_list_inner_type(annotation: Any) -> Any:
    """Return the element type from list[T] annotations."""
    inner = _unwrap_optional(annotation)
    args = typing.get_args(inner)
    return args[0] if args else str


def _get_numeric_cast(annotation: Any) -> type[int] | type[float] | None:
    """Return int or float constructor if the annotation expects a numeric type."""
    inner = _unwrap_optional(annotation)
    if inner is int:
        return int
    if inner is float:
        return float
    return None


def _get_field_annotations(schema: type[BaseModel]) -> dict[str, Any]:
    """Extract {field_name: annotation} from a Pydantic model's field definitions."""
    return {name: info.annotation for name, info in schema.model_fields.items()}


# ─── @key sub-object parser ───────────────────────────────────────────────────

def _parse_at_key_lines(raw_lines: list[str]) -> list[dict[str, str]]:
    """Parse ``@key: val`` indented lines into a list of dicts.

    A repeated key signals the start of a new sub-object.
    Non-@key lines are skipped (they should not appear in an @key block; a warning is logged).

    Example input:
        ["@speaker: 旁白", "@text: 她回头", "@speaker: 主角", "@text: 来了"]

    Example output:
        [{"speaker": "旁白", "text": "她回头"}, {"speaker": "主角", "text": "来了"}]
    """
    objects: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw in raw_lines:
        m = re.match(r"@(\w+):\s*(.*)", raw.strip())
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key in current:
                # Repeated key → close current object, start new one
                objects.append(current)
                current = {}
            current[key] = val
        else:
            stripped = raw.strip()
            if stripped:
                logger.warning(
                    "parse_md: non-@key line in nested sub-object context, skipping: %r",
                    stripped,
                )
    if current:
        objects.append(current)
    return objects


# ─── Regex constants ──────────────────────────────────────────────────────────

_RE_ITEM_HEADER = re.compile(r"^##\s+(.+)$")

# Flat field: "- key: value" (supports -, *, • bullets)
_RE_FLAT_FIELD = re.compile(r"^[-*•]\s+(\w+):\s+(.+)$")

# Nested field start: "- key:" (empty value — children follow as indented lines)
_RE_NESTED_FIELD = re.compile(r"^[-*•]\s+(\w+):\s*$")

# Indented child: " - some content" (2+ leading spaces + any bullet)
_RE_INDENTED_CHILD = re.compile(r"^\s{2,}[-*•]\s+(.+)$")


# ─── parse_md ─────────────────────────────────────────────────────────────────

def parse_md(md_text: str, schema: type[BaseModel]) -> list[dict[str, Any]]:
    """Parse structured Markdown text into raw item dicts.

    Phase 1 — split md_text on ``## `` headers; each header becomes one item.
    Phase 2 — extract fields from each block's bullet lines.
    Phase 3 — coerce scalar values to schema-declared types (int/float/list).

    Each output dict contains ``_md_id`` (the ``##`` header text) with an underscore
    prefix that guarantees no collision with schema field names.

    Unrecognised lines are logged at WARNING level and skipped — never raised.
    """
    annotations = _get_field_annotations(schema)
    blocks = _split_into_blocks(md_text)
    logger.debug("parse_md: schema=%s raw_blocks=%d", schema.__name__, len(blocks))

    items: list[dict[str, Any]] = []
    for item_id, block_lines in blocks:
        item = _parse_block(item_id, block_lines, annotations)
        items.append(item)

    logger.info("parse_md: schema=%s parsed=%d items", schema.__name__, len(items))
    return items


def _split_into_blocks(md_text: str) -> list[tuple[str, list[str]]]:
    """Split MD text on ``## `` markers → [(item_id, body_lines), ...]."""
    blocks: list[tuple[str, list[str]]] = []
    current_id: str | None = None
    current_lines: list[str] = []

    for raw_line in md_text.splitlines():
        m = _RE_ITEM_HEADER.match(raw_line)
        if m:
            if current_id is not None:
                blocks.append((current_id, current_lines))
            current_id = m.group(1).strip()
            current_lines = []
        elif current_id is not None:
            current_lines.append(raw_line)

    if current_id is not None:
        blocks.append((current_id, current_lines))

    return blocks


def _parse_block(
    item_id: str,
    lines: list[str],
    annotations: dict[str, Any],
) -> dict[str, Any]:
    """Parse the body lines of one ## block into a flat field dict."""
    item: dict[str, Any] = {"_md_id": item_id}
    current_nested_key: str | None = None
    nested_children: list[str] = []

    def _flush_nested() -> None:
        """Apply accumulated children to current_nested_key."""
        nonlocal current_nested_key, nested_children
        if current_nested_key is None:
            return
        ann = annotations.get(current_nested_key)
        if _is_list_annotation(ann):
            inner_type = _get_list_inner_type(ann)
            # Check if inner_type is a BaseModel subclass → @key format
            if isinstance(inner_type, type) and issubclass(inner_type, BaseModel):
                item[current_nested_key] = _parse_at_key_lines(nested_children)
            elif any(c.strip().startswith("@") for c in nested_children):
                # Annotation says list[str] but children look like @key lines →
                # still parse as sub-objects (LLM sometimes uses @key for dict lists)
                item[current_nested_key] = _parse_at_key_lines(nested_children)
            else:
                # Plain list[str]
                item[current_nested_key] = [c.strip() for c in nested_children if c.strip()]
        else:
            # Non-list nested field — join children (unlikely, but handle gracefully)
            item[current_nested_key] = ", ".join(c.strip() for c in nested_children if c.strip())
        current_nested_key = None
        nested_children = []

    for line in lines:
        if not line.strip():
            continue  # skip blank lines

        # Indented child — must be checked FIRST (before flat/nested patterns)
        child_m = _RE_INDENTED_CHILD.match(line)
        if child_m:
            if current_nested_key is not None:
                nested_children.append(child_m.group(1))
            else:
                logger.warning(
                    "parse_md: indented child outside nested field, skipping: %r",
                    line,
                )
            continue

        # New top-level bullet → flush any pending nested field
        _flush_nested()

        # Flat field: "- key: value"
        flat_m = _RE_FLAT_FIELD.match(line)
        if flat_m:
            key, raw_val = flat_m.group(1), flat_m.group(2).strip()
            item[key] = _coerce_scalar(key, raw_val, annotations)
            continue

        # Nested field start: "- key:"
        nested_m = _RE_NESTED_FIELD.match(line)
        if nested_m:
            current_nested_key = nested_m.group(1)
            nested_children = []
            continue

        logger.warning("parse_md: unrecognised line, skipping: %r", line)

    # Flush the last pending nested field
    _flush_nested()
    return item


def _coerce_scalar(key: str, raw_val: str, annotations: dict[str, Any]) -> Any:
    """Coerce a raw string value to the type expected by the schema for ``key``."""
    ann = annotations.get(key)
    if ann is None:
        return raw_val

    # list[str] via inline comma notation (flat field format)
    if _is_list_annotation(ann):
        return [v.strip() for v in raw_val.split(",") if v.strip()]

    # int / float — try conversion; keep str on failure (diagnose will report)
    cast = _get_numeric_cast(ann)
    if cast is not None:
        try:
            return cast(raw_val)
        except (ValueError, TypeError):
            logger.debug(
                "parse_md: cannot cast %r to %s for key=%r, keeping str",
                raw_val,
                cast.__name__,
                key,
            )
            return raw_val

    return raw_val


# ─── diagnose ─────────────────────────────────────────────────────────────────

def _classify_error_kind(pydantic_error_type: str) -> Literal["structural", "semantic"]:
    """Classify a Pydantic validation error as structural or semantic."""
    if pydantic_error_type == "missing":
        return "structural"
    return "semantic"


_T = TypeVar("_T", bound=BaseModel)


def diagnose(
    items: list[dict[str, Any]], schema: type[_T]
) -> DiagnosticReport:
    """Validate each item dict against ``schema`` independently.

    One item failing validation does NOT affect any other item.
    Valid items are collected in ``DiagnosticReport.valid_items``;
    failures become ``DiagnosticReport.errors`` entries with per-field error details.
    """
    valid_items: list[BaseModel] = []
    errors: list[ItemError] = []

    for i, item in enumerate(items):
        try:
            valid_items.append(schema.model_validate(item))
        except PydanticValidationError as exc:
            field_errors = [
                FieldError(
                    field=".".join(str(loc) for loc in err["loc"]),
                    error=err["msg"],
                    error_kind=_classify_error_kind(err["type"]),
                )
                for err in exc.errors()
            ]
            errors.append(
                ItemError(
                    index=i,
                    item_id=item.get("_md_id"),  # type: ignore[arg-type]
                    fields=field_errors,
                )
            )

    logger.info(
        "diagnose: schema=%s total=%d valid=%d errors=%d",
        schema.__name__,
        len(items),
        len(valid_items),
        len(errors),
    )
    return DiagnosticReport(valid_items=valid_items, errors=errors)


# ─── md_to_json ───────────────────────────────────────────────────────────────

def _extract_md_excerpt(md_text: str, error_indices: set[int]) -> str:
    """Extract only the ## blocks at ``error_indices`` from ``md_text``.

    Implementation:
      1. Split md_text on lines that start a new ## block (keeping the delimiter).
      2. Filter to only item blocks (skip any pre-header preamble).
      3. Select the sub-list at error_indices.
      4. Rejoin for the Patch Agent prompt.
    """
    # Split on lines that start a new ## block; re.split with lookahead keeps delimiters
    raw_parts = re.split(r"(?m)^(?=##\s)", md_text)
    # Keep only parts that begin with '## ' (i.e. actual item blocks).
    # Use simple prefix check because p is a multi-line chunk, not a single line.
    item_parts = [p for p in raw_parts if p.lstrip().startswith("## ")]
    selected = [item_parts[i] for i in sorted(error_indices) if i < len(item_parts)]
    return "\n".join(selected)


def md_to_json(
    md_text: str,
    schema: type[_T] | None = None,
    *,
    ctx: dict[str, object] | None = None
) -> list[_T]:
    """Parse MD text and return validated Pydantic model instances.

    Happy path (all valid, ~90-95% of calls): parse → diagnose → return immediately.
    Zero extra LLM tokens.

    Error path (~5-10% of calls): Extract MD excerpt for error items only → call Patch Agent
    → merge valid_items + patched_items → return.

    Args:
        md_text: Raw Markdown text from LLM output.
        schema: Pydantic model class to validate against. If None, resolves from
            ctx — preferring ctx["_md_schema"] (direct class) and falling back
            to ctx["_md_schema_path"] (dotted path resolved via sys.modules).
        ctx: Optional context dict containing schema info. The graph_agent
            harness injects the path form to keep ctx msgpack-serializable
            across LangGraph checkpoints.

    Returns:
        list[schema]: All items as validated model instances.
    """
    # Schema resolution: explicit arg > ctx["_md_schema"] (class) > ctx["_md_schema_path"] (string)
    _missing_schema_msg = (
        'md_to_json requires either schema= or ctx["_md_schema"]/["_md_schema_path"]'
    )
    if schema is None:
        if ctx is None:
            raise ValueError(_missing_schema_msg)
        direct = ctx.get("_md_schema")
        if direct is not None:
            schema = direct  # type: ignore[assignment]
        else:
            path = ctx.get("_md_schema_path")
            if not isinstance(path, str) or not path:
                raise ValueError(_missing_schema_msg)
            schema = _resolve_schema_from_path(path)  # type: ignore[assignment]
    items = parse_md(md_text, schema)
    logger.info("md_to_json: schema=%s parsed=%d items", schema.__name__, len(items))

    report = diagnose(items, schema)
    logger.info(
        "md_to_json: valid=%d errors=%d",
        len(report.valid_items),
        len(report.errors),
    )

    if report.all_valid:
        return list(report.valid_items)  # type: ignore[return-value]

    # Check if all errors are semantic (md-patch cannot help)
    if report.semantic_only:
        logger.warning(
            "md_to_json: all %d errors are semantic, skipping md-patch, raising SemanticValidationError",
            len(report.errors),
        )
        raise SemanticValidationError(report)

    # Error path: extract only the failing MD blocks, run Patch Agent
    error_indices = {e.index for e in report.errors}
    md_excerpt = _extract_md_excerpt(md_text, error_indices)
    logger.info(
        "md_to_json: triggering Patch Agent for %d error items (schema=%s)",
        len(report.errors),
        schema.__name__,
    )

    result = run_skill(
        _PATCH_SKILL_MD,
        original_md_excerpt=md_excerpt,
        diagnostic_report=report.to_prompt_string(),
        valid_results=[item.model_dump() for item in report.valid_items],
        error_items=[items[e.index] for e in report.errors],
        schema=schema,  # Python class object — safe inside graph_agent context dict
    )

    patched: list[dict[str, Any]] = result["context"]["final_results"]
    logger.info(
        "md_to_json: patch completed, %d patched items merged",
        len(patched),
    )
    return list(report.valid_items) + [  # type: ignore[return-value]
        schema.model_validate(p) for p in patched
    ]


# ─── Schema to Type Dict ─────────────────────────────────────────────────────


def _type_to_constraint(annotation: Any, field_info: Any = None) -> str:
    """Convert a Python type annotation to a human-readable constraint string."""
    import typing
    from pydantic import BaseModel

    # Handle Optional[T] - both typing.Union and Python 3.10+ UnionType (X | Y)
    import types
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # Check for Optional/Union types (typing.Union or types.UnionType for X | Y syntax)
    is_union = False
    if origin is typing.Union:
        is_union = True
    elif isinstance(annotation, types.UnionType):
        is_union = True
        origin = types.UnionType

    if is_union:
        # Optional[T] is Union[T, None]
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            return _type_to_constraint(non_none_args[0], field_info)

    # Handle Literal[...]
    if origin is typing.Literal:
        values = [f"{v!r}" for v in args]
        return f"[字符串，限 {', '.join(values)}]"

    # Handle List[T]
    if origin is list:
        inner = args[0] if args else str
        if inner is str:
            return "[列表，缩进子行或逗号分隔]"
        return f"[列表，元素为 {_type_to_constraint(inner)}]"

    # Handle primitive types
    if annotation is str:
        return "[文本]"

    if annotation is int:
        constraint = "[整数"
        # Extract ge/le from field_info metadata (contains Ge/Le objects)
        ge_val = None
        le_val = None
        if field_info and hasattr(field_info, 'metadata'):
            for m in field_info.metadata:
                if hasattr(m, 'ge'):
                    ge_val = m.ge
                elif m.__class__.__name__ == 'Ge' and hasattr(m, 'ge'):
                    ge_val = m.ge
                if hasattr(m, 'le'):
                    le_val = m.le
                elif m.__class__.__name__ == 'Le' and hasattr(m, 'le'):
                    le_val = m.le
        if ge_val is not None:
            constraint += f", >={ge_val}"
        if le_val is not None:
            constraint += f", <={le_val}"
        constraint += "]"
        return constraint

    if annotation is float:
        constraint = "[小数"
        ge_val = None
        le_val = None
        if field_info and hasattr(field_info, 'metadata'):
            for m in field_info.metadata:
                if hasattr(m, 'ge'):
                    ge_val = m.ge
                elif m.__class__.__name__ == 'Ge' and hasattr(m, 'ge'):
                    ge_val = m.ge
                if hasattr(m, 'le'):
                    le_val = m.le
                elif m.__class__.__name__ == 'Le' and hasattr(m, 'le'):
                    le_val = m.le
        if ge_val is not None:
            constraint += f", >={ge_val}"
        if le_val is not None:
            constraint += f", <={le_val}"
        constraint += "]"
        return constraint

    # Handle BaseModel subclasses (nested)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return "[嵌套对象]"

    return "[未知]"


def schema_to_type_dict(schema: type[BaseModel]) -> str:
    """Generate a type constraint dictionary from a Pydantic schema.

    Each line follows format: "- field_name: [constraint]"
    """
    lines: list[str] = []
    for name, info in schema.model_fields.items():
        constraint = _type_to_constraint(info.annotation, info)
        lines.append(f"- {name}: {constraint}")
    return "\n".join(lines)
