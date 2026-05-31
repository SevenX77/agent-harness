"""Phase 3 SKILL manifest to PhaseNode builder."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast

from graph_agent.core.exceptions import SkillCompilationError, SkillLoadError
from graph_agent.core.schema_engine import SchemaEngine
from graph_agent.tools.dynamic_schema import (
    DynamicSchemaDef,
    OutputExampleParseError,
    parse_output_example,
    render_dynamic_schema_output_format,
)

logger = logging.getLogger(__name__)
_SCHEMA_ENGINE: SchemaEngine = SchemaEngine()
_LOCAL_MODULE_CACHE: dict[str, Any] = {}


def get_schema_engine() -> SchemaEngine:
    """Return the SchemaEngine shared across compile + runtime consumers."""
    return _SCHEMA_ENGINE


def _render_output_format_markdown_for_model(
    model_cls: type[Any],
    output_schema_path: str,
) -> str:
    if not hasattr(model_cls, "model_fields"):
        raise SkillLoadError(f"output_schema {output_schema_path!r} is not a Pydantic BaseModel")

    class_name = model_cls.__name__
    template_lines = [
        "请按以下结构输出 business_data_md（一个或多个 `##` 块，每块对应一个 "
        f"{class_name} 实例）：",
        "",
        "```markdown",
        "## <item_id 标识符>",
    ]
    for field_name in model_cls.model_fields:
        template_lines.append(f"- {field_name}: <值>")
    template_lines.append("```")

    reference_lines = ["", "字段说明："]
    for field_name, field_info in model_cls.model_fields.items():
        field_type = getattr(
            field_info.annotation,
            "__name__",
            str(field_info.annotation),
        )
        description = field_info.description or "（无描述）"
        required_marker = "（必填）" if field_info.is_required() else "（可选）"
        reference_lines.append(
            f"- **{field_name}** {required_marker}: `{field_type}` — {description}"
        )

    return "\n".join(template_lines + reference_lines)


def _parse_output_example_or_raise(
    output_example: str,
    *,
    location: str,
) -> DynamicSchemaDef:
    """Parse ``output_example`` or surface a compile-fatal loader error.

    Side-effect: warms the shared SchemaEngine cache so finish.py
    validation and IOManager hoist hit the cache later. A SchemaEngine
    disagreement on input that ``parse_output_example`` already accepted
    is logged as a warning — the canonical ``DynamicSchemaDef`` is the
    source of truth for compile success.
    """
    try:
        dynamic = parse_output_example(output_example)
    except OutputExampleParseError as exc:
        raise SkillCompilationError(f"[F-output-example-invalid] {location}: {exc}") from exc

    try:
        _SCHEMA_ENGINE.parse_from_md(output_example)
    except Exception as exc:  # noqa: BLE001 — broad SchemaParseError surface
        logger.warning(
            "loader: SchemaEngine.parse_from_md disagreed with "
            "parse_output_example at %s: %s; cache will be cold for this fragment",
            location,
            exc,
        )
    return dynamic


# ---------------------------------------------------------------------------
# Dynamic import (adapted from DeerFlow reflection/resolvers.py)
# ---------------------------------------------------------------------------


def _skill_namespace(base_dir: Path) -> str:
    """Return the stable module namespace for one skill directory."""
    return hashlib.sha256(str(base_dir.resolve()).encode("utf-8")).hexdigest()[:20]


def _load_skill_local_module(module_path_str: str, base_dir: Path) -> Any | None:
    """Load a SKILL-local module under the same namespace used for tools."""
    module_file = base_dir / module_path_str.replace(".", "/")
    py_file = module_file.with_suffix(".py")
    if not py_file.exists():
        init_file = module_file / "__init__.py"
        if init_file.exists():
            py_file = init_file
        else:
            return None

    if not py_file.resolve().is_relative_to(base_dir.resolve()):
        raise SkillLoadError(
            f"Module reference '{module_path_str}' resolves outside skill directory: {py_file}"
        )

    module_name = f"_graph_agent_skill_.{_skill_namespace(base_dir)}.{module_path_str}"
    cached = _LOCAL_MODULE_CACHE.get(module_name)
    if cached is not None:
        return cached

    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        raise SkillLoadError(f"Cannot load module spec for {py_file}")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        _LOCAL_MODULE_CACHE.pop(module_name, None)
        raise
    _LOCAL_MODULE_CACHE[module_name] = module
    return module


def resolve_skill_resource(
    base_dir: Path,
    resource_path: str,
    *,
    kind: Literal["tool", "reference", "schema"] = "tool",
) -> Any:
    """Resolve a SKILL-local resource through one sandboxed code path.

    ``tool`` returns a callable, ``schema`` returns a module for legacy
    Pydantic output_schema rendering, and ``reference`` returns a normalized
    path relative to ``base_dir``. File-backed resources must stay under the
    skill directory.
    """
    if kind == "reference":
        return _resolve_reference_resource(base_dir, resource_path)

    module_path_str, attr_name = _split_resource_reference(resource_path, kind)

    if kind == "tool" and (module_path_str == "builtin" or module_path_str.startswith("builtin.")):
        return _resolve_builtin_tool(module_path_str, attr_name, resource_path)

    resolved_module = _resolve_resource_module(base_dir, module_path_str, kind, resource_path)

    if kind == "schema":
        return resolved_module

    return _get_callable_resource(resolved_module, attr_name, resource_path)


def _split_resource_reference(
    resource_path: str,
    kind: Literal["tool", "reference", "schema"],
) -> tuple[str, str]:
    if kind == "schema":
        return resource_path, ""
    parts = resource_path.rsplit(".", 1)
    if len(parts) != 2:
        raise SkillLoadError(
            f"Invalid {kind} reference '{resource_path}'. Expected format: module.path.name"
        )
    return parts[0], parts[1]


def _resolve_builtin_tool(
    module_path_str: str,
    attr_name: str,
    resource_path: str,
) -> Callable[..., str]:
    try:
        from graph_agent.tools import builtin as _builtin_pkg  # noqa: F401

        submod_name = module_path_str[len("builtin") :].lstrip(".")
        full_module = "graph_agent.tools.builtin"
        if submod_name:
            full_module = f"{full_module}.{submod_name}"
        module = importlib.import_module(full_module)
    except ImportError as exc:
        raise SkillLoadError(f"Cannot import builtin tool '{resource_path}': {exc}") from exc

    try:
        func = getattr(module, attr_name)
    except AttributeError as exc:
        raise SkillLoadError(
            f"Builtin module '{full_module}' does not define '{attr_name}'"
        ) from exc

    if not callable(func):
        raise SkillLoadError(f"'{resource_path}' is not callable (got {type(func).__name__})")
    return cast(Callable[..., str], func)


def _resolve_resource_module(
    base_dir: Path,
    module_path_str: str,
    kind: Literal["tool", "reference", "schema"],
    resource_path: str,
) -> Any:
    cached_name = f"_graph_agent_skill_.{_skill_namespace(base_dir)}.{module_path_str}"
    resolved_module: Any = _LOCAL_MODULE_CACHE.get(cached_name)
    if resolved_module is not None:
        return resolved_module
    resolved_module = _load_skill_local_module(module_path_str, base_dir)
    if resolved_module is not None:
        return resolved_module
    try:
        return importlib.import_module(module_path_str)
    except ImportError as exc:
        raise SkillLoadError(
            f"Cannot import {kind} module '{module_path_str}' for '{resource_path}': {exc}"
        ) from exc


def _get_callable_resource(
    resolved_module: Any,
    attr_name: str,
    resource_path: str,
) -> Callable[..., str]:
    try:
        func = getattr(resolved_module, attr_name)
    except AttributeError as exc:
        raise SkillLoadError(f"Module for '{resource_path}' does not define '{attr_name}'") from exc

    if not callable(func):
        raise SkillLoadError(f"'{resource_path}' is not callable (got {type(func).__name__})")

    return cast(Callable[..., str], func)


def _resolve_reference_resource(base_dir: Path, reference_path: str) -> str:
    """Resolve and normalize one declared reference file path."""
    clean = str(reference_path or "").strip().replace("\\", "/")
    while clean.startswith("./"):
        clean = clean[2:]
    if not clean:
        raise SkillLoadError("Reference path is empty")
    if Path(clean).is_absolute():
        raise SkillLoadError(f"Reference path must be relative: {reference_path!r}")

    base_resolved = base_dir.resolve()
    references_root = (base_resolved / "references").resolve()
    candidates = [(base_resolved / clean).resolve()]
    if not clean.startswith("references/"):
        candidates.append((references_root / clean).resolve())
    for candidate in candidates:
        try:
            candidate.relative_to(base_resolved)
        except ValueError as exc:
            raise SkillLoadError(
                f"Reference '{reference_path}' resolves outside skill directory: {candidate}"
            ) from exc
        if candidate.is_file():
            return candidate.relative_to(base_resolved).as_posix()

    # Existence is checked by the read_file tool at runtime so tests and
    # generated skills can declare references before materializing files.
    return clean


def _resolve_tool_reference(
    ref_path: str,
    base_dir: Path,
) -> Callable[..., str]:
    """Resolve a dot-path tool reference to a Python callable."""
    return cast(Callable[..., str], resolve_skill_resource(base_dir, ref_path, kind="tool"))


def _append_steps_to_prompt(prompt: str, steps: list[str]) -> str:
    """Append prompt-structure steps as plain V0.3.0 step lines."""
    if not steps:
        return prompt
    lines = ["Suggested steps:"]
    lines.extend(f"  {i}. {step}" for i, step in enumerate(steps, start=1))
    block = "\n".join(lines)
    if not prompt:
        return block
    return f"{prompt}\n\n{block}"


def _render_skill_section_xml_tags(
    phase_or_profile: Any,
    *,
    skill_base_dir: Path | None = None,
) -> str:
    """Render optional prompt-schema fields as XML-ish skill-section tags."""
    sections: list[str] = []

    domain_protocols = list(getattr(phase_or_profile, "domain_protocols", []) or [])
    if domain_protocols:
        lines = ["<domain_protocols>"]
        lines.extend(
            f"  [protocol:P{i}] {protocol}" for i, protocol in enumerate(domain_protocols, start=1)
        )
        lines.append("</domain_protocols>")
        sections.append("\n".join(lines))

    few_shot_examples = list(getattr(phase_or_profile, "few_shot_examples", []) or [])
    if few_shot_examples:
        lines = ["<examples>"]
        lines.extend(
            f'  <example id="{i}">{example}</example>'
            for i, example in enumerate(few_shot_examples, start=1)
        )
        lines.append("</examples>")
        sections.append("\n".join(lines))

    references = list(getattr(phase_or_profile, "references", []) or [])
    if references:
        if skill_base_dir is not None:
            references = [
                resolve_skill_resource(skill_base_dir, reference, kind="reference")
                for reference in references
            ]
        lines = [
            "<knowledge_base>",
            "  本地有以下参考文件，请在需要时调用 read_file 查阅：",
        ]
        lines.extend(f"  - {reference}" for reference in references)
        lines.append("</knowledge_base>")
        sections.append("\n".join(lines))

    context_access = list(getattr(phase_or_profile, "context_access", []) or [])
    if context_access:
        tool_names = {
            "artifact": "read_artifact",
            "working_memory": "read_working_memory",
        }
        lines = [
            "<context_access>",
            "  如果在当前输入中发现信息缺失，你被授权使用以下工具追溯前序上下文：",
        ]
        lines.extend(f"  - {tool_names[item]}" for item in context_access)
        lines.append("</context_access>")
        sections.append("\n".join(lines))

    output_example = getattr(phase_or_profile, "output_example", None)
    if output_example:
        phase_name = getattr(phase_or_profile, "name", "unknown")
        schema = _parse_output_example_or_raise(
            output_example,
            location=f"SKILL.md:phases.{phase_name}.output_example",
        )
        sections.append(
            f"<output_format>\n{render_dynamic_schema_output_format(schema)}\n</output_format>"
        )
    else:
        output_schema = getattr(phase_or_profile, "output_schema", None)
        if output_schema:
            base_dir = skill_base_dir or getattr(phase_or_profile, "skill_base_dir", None)
            format_md = _render_output_format_markdown(
                output_schema,
                skill_base_dir=base_dir,
            )
            if format_md:
                sections.append(f"<output_format>\n{format_md}\n</output_format>")

    return "\n\n".join(sections)


def _render_output_format_markdown(
    output_schema_path: str,
    *,
    skill_base_dir: Path | None = None,
) -> str:
    """Render output schema as Markdown template + field reference.

    The template explicitly shows the ``##`` block + bullet structure
    that md_to_json expects, so the LLM doesn't have to infer it from
    field metadata alone. Falls back to empty string + log warning when
    the schema can't be resolved (graceful degradation).

    Args:
        output_schema_path: Dotted path to a Pydantic BaseModel class.

    Returns:
        Markdown string with two sections:
          1. Template skeleton showing ``## <id>`` + bullet fields with
             placeholders.
          2. Field reference listing required/optional + type + description.
        Empty string on resolution failure.

    """
    model_cls = _resolve_output_schema_class(
        output_schema_path,
        skill_base_dir=skill_base_dir,
    )
    if model_cls is None:
        return ""
    return _render_output_format_markdown_for_model(model_cls, output_schema_path)


def _resolve_output_schema_class(
    output_schema_path: str,
    *,
    skill_base_dir: Path | None = None,
) -> type[Any] | None:
    """Resolve a dotted output schema path to a Pydantic model class."""
    try:
        module_path, class_name = output_schema_path.rsplit(".", 1)
        if skill_base_dir is not None:
            module = resolve_skill_resource(
                skill_base_dir,
                module_path,
                kind="schema",
            )
        else:
            module = importlib.import_module(module_path)

        model_cls = getattr(module, class_name)

        if not hasattr(model_cls, "model_fields"):
            logger.warning(
                "loader: output_schema %s is not a Pydantic BaseModel; skipping <output_format>",
                output_schema_path,
            )
            return None

        return cast(type[Any], model_cls)

    except (ImportError, AttributeError, SkillLoadError, ValueError) as exc:
        logger.warning(
            "loader: failed to resolve output_schema %s: %s; skipping <output_format>",
            output_schema_path,
            exc,
        )
        return None
