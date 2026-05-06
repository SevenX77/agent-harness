"""Phase 3 SKILL manifest to PhaseNode builder."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from graph_agent.tools.dynamic_schema import (
    DynamicSchemaDef,
    OutputExampleParseError,
    parse_output_example,
    render_dynamic_schema_output_format,
)
from graph_agent.core.exceptions import SkillCompilationError, SkillLoadError
from graph_agent.core.personas import resolve_persona
from graph_agent.core.schema_engine import SchemaEngine
from graph_agent.core.types import Phase

if TYPE_CHECKING:
    from graph_agent.core.manifest import AgentSkillDef, LLMPhase, LogicPhase, PersonaSkillDef
    from graph_agent.core.manifest import SkillManifest as SkillManifestType
    from graph_agent.core.module_sandbox import ModuleSandbox
    from graph_agent.core.phase_node import PhaseNode
    from graph_agent.core.state import BusinessData, WorkflowState

logger = logging.getLogger(__name__)
_SCHEMA_ENGINE: SchemaEngine = SchemaEngine()
_LOCAL_MODULE_CACHE: dict[str, Any] = {}


def get_schema_engine() -> SchemaEngine:
    """Return the SchemaEngine shared across compile + runtime consumers."""
    return _SCHEMA_ENGINE


def build_graph_nodes(
    manifest: SkillManifestType,
    schema_engine: SchemaEngine,
    module_sandbox: ModuleSandbox,
) -> list[PhaseNode]:
    """Phase 3: typed manifest to executable PhaseNode facades."""

    from graph_agent.core.manifest import (
        AgentSkillDef,
        GraphSkillDef,
        LLMPhase,
        LogicPhase,
        PersonaSkillDef,
    )
    from graph_agent.core.phase_node import PhaseNode

    if isinstance(manifest, PersonaSkillDef):
        raise SkillLoadError(
            "Persona skills are not runnable on their own — they are injected via adopted_persona."
        )

    business_data_cls = _build_business_data_for_manifest(manifest, schema_engine)
    initial_state_factory = _initial_state_factory(business_data_cls)
    skill_base_dir = _skill_base_dir_from_sandbox(module_sandbox)

    if isinstance(manifest, AgentSkillDef):
        phase = _phase_from_agent_manifest_for_nodes(
            manifest,
            module_sandbox,
            skill_base_dir=skill_base_dir,
        )
        return [
            PhaseNode(
                name=phase.name,
                execute_fn=_phase_node_execute_fn(phase.name),
                metadata={"type": manifest.type, "mode": "agent"},
                phase=phase,
                business_data_cls=business_data_cls,
                initial_state_factory=initial_state_factory,
            )
        ]

    if not isinstance(manifest, GraphSkillDef):
        raise SkillLoadError(f"Unsupported manifest type: {type(manifest).__name__}")

    nodes: list[PhaseNode] = []
    for phase_def in manifest.phases:
        if isinstance(phase_def, LLMPhase):
            phase, output_schema_cls = _llm_phase_for_node(
                phase_def,
                module_sandbox,
                skill_base_dir=skill_base_dir,
            )
            compiled_schema = manifest.compiled_schemas.get(phase_def.name)
            nodes.append(
                PhaseNode(
                    name=phase_def.name,
                    execute_fn=_phase_node_execute_fn(phase_def.name),
                    metadata={"type": manifest.type, "mode": phase_def.mode},
                    phase=phase,
                    business_data_cls=business_data_cls,
                    initial_state_factory=initial_state_factory,
                    compiled_schema=compiled_schema,
                    output_schema_cls=output_schema_cls,
                    validator=phase.validator,
                )
            )
            continue

        if isinstance(phase_def, LogicPhase):
            phase = _logic_phase_for_node(
                phase_def,
                module_sandbox,
                skill_base_dir=skill_base_dir,
            )
            nodes.append(
                PhaseNode(
                    name=phase_def.name,
                    execute_fn=_phase_node_execute_fn(phase_def.name),
                    metadata={"type": manifest.type, "mode": phase_def.mode},
                    phase=phase,
                    business_data_cls=business_data_cls,
                    initial_state_factory=initial_state_factory,
                    validator=phase.validator,
                )
            )
            continue

        raise SkillLoadError(
            f"Unsupported phase type for {getattr(phase_def, 'name', '?')!r}: "
            f"{type(phase_def).__name__}"
        )

    return nodes


def _skill_base_dir_from_sandbox(module_sandbox: ModuleSandbox) -> Path | None:
    search_paths = module_sandbox.search_paths
    return search_paths[-1] if search_paths else None


def _build_business_data_for_manifest(
    manifest: SkillManifestType,
    schema_engine: SchemaEngine,
) -> type[BusinessData]:
    from graph_agent.core import state as state_module

    factory = getattr(state_module, "build_business_data_for_skill", None)
    if callable(factory):
        typed_factory = cast(
            Callable[[SkillManifestType, SchemaEngine], type[BusinessData]],
            factory,
        )
        return typed_factory(manifest, schema_engine)
    return _fallback_build_business_data_for_skill(manifest, schema_engine)


def _fallback_build_business_data_for_skill(
    manifest: SkillManifestType,
    schema_engine: SchemaEngine,
) -> type[BusinessData]:
    from pydantic import create_model

    from graph_agent.core.manifest import GraphSkillDef, LLMPhase
    from graph_agent.core.state import BusinessData

    fields: dict[str, Any] = {}
    if isinstance(manifest, GraphSkillDef):
        for input_def in manifest.io.inputs:
            fields[input_def.name] = (Any, None)
        for output_def in manifest.io.outputs:
            fields[output_def.name] = (Any, None)
        for phase in manifest.phases:
            if isinstance(phase, LLMPhase) and phase.hoist_to:
                fields[phase.hoist_to] = (Any, None)
        for schema in manifest.compiled_schemas.values():
            schema_engine.get_pydantic_model(schema)

    model_name = "BusinessData_" + re.sub(r"\W+", "_", manifest.name).strip("_")
    return cast(
        type[BusinessData],
        create_model(model_name or "BusinessData_Skill", __base__=BusinessData, **fields),
    )


def _initial_state_factory(
    business_data_cls: type[BusinessData],
) -> Callable[[dict[str, Any] | None], WorkflowState]:
    from graph_agent.core.state import FrameworkState, WorkflowState

    def build(initial_data: dict[str, Any] | None = None) -> WorkflowState:
        return WorkflowState(
            data=business_data_cls.model_validate(initial_data or {}),
            flow=FrameworkState(),
            messages=[],
        )

    return build


def _phase_node_execute_fn(phase_name: str) -> Callable[[WorkflowState], WorkflowState]:
    from graph_agent.core.state import StateManager

    def execute(state: WorkflowState) -> WorkflowState:
        return StateManager.update_framework(state, current_phase=phase_name)

    return execute


def _phase_from_agent_manifest_for_nodes(
    manifest: AgentSkillDef,
    module_sandbox: ModuleSandbox,
    *,
    skill_base_dir: Path | None,
) -> Phase:
    tools = [
        cast(Callable[..., str], module_sandbox.import_callable(ref))
        for ref in manifest.agent_tools
    ]
    system_prompt = _compose_agent_system_prompt(
        manifest,
        skill_base_dir=skill_base_dir,
    )
    if manifest.adopted_persona is not None:
        if skill_base_dir is None:
            raise SkillLoadError(
                f"Cannot resolve adopted_persona {manifest.adopted_persona!r} without skill base dir"
            )
        persona_manifest = resolve_persona(
            manifest.adopted_persona,
            base_dir=skill_base_dir,
        )
        system_prompt = _inject_persona(persona_manifest, system_prompt)
    return Phase(
        name=manifest.name,
        system_prompt=system_prompt,
        user_prompt_template=manifest.user_prompt_template,
        tools=tools,
        tier=manifest.agent_profile.llm_role or "balanced",
        llm_role=manifest.agent_profile.llm_role,
        model_override=manifest.model_override,
        references=[
            _resolve_reference_resource(skill_base_dir, reference)
            if skill_base_dir is not None
            else reference
            for reference in manifest.agent_profile.references
        ],
        skill_base_dir=skill_base_dir,
        context_access=list(manifest.agent_profile.context_access),
        requires_llm=True,
    )


def _llm_phase_for_node(
    phase_def: LLMPhase,
    module_sandbox: ModuleSandbox,
    *,
    skill_base_dir: Path | None,
) -> tuple[Phase, type[Any] | None]:
    output_schema_cls: type[Any] | None = None
    if phase_def.output_example and phase_def.output_schema:
        raise SkillCompilationError(
            f"[F-output-example-conflict] SKILL.md:phases.{phase_def.name}: "
            "output_example and output_schema are mutually exclusive"
        )
    dynamic_schema = (
        _parse_output_example_or_raise(
            phase_def.output_example,
            location=f"SKILL.md:phases.{phase_def.name}.output_example",
        )
        if phase_def.output_example
        else None
    )
    if dynamic_schema is not None:
        dynamic_schema.hoist_to = phase_def.hoist_to  # type: ignore[attr-defined]

    system_prompt = phase_def.prompt
    if phase_def.output_schema and dynamic_schema is None:
        output_schema_cls = module_sandbox.import_class(phase_def.output_schema)
        format_md = _render_output_format_markdown_for_model(
            output_schema_cls,
            phase_def.output_schema,
        )
        if format_md:
            system_prompt = (
                f"{system_prompt}\n\n<output_format>\n{format_md}\n</output_format>"
                if system_prompt
                else f"<output_format>\n{format_md}\n</output_format>"
            )
    else:
        xml_tags = _render_skill_section_xml_tags(
            phase_def,
            skill_base_dir=skill_base_dir,
        )
        if xml_tags:
            system_prompt = f"{system_prompt}\n\n{xml_tags}" if system_prompt else xml_tags

    if phase_def.steps:
        system_prompt = _append_steps_to_prompt(system_prompt or "", phase_def.steps)
    if phase_def.adopted_persona is not None:
        if skill_base_dir is None:
            raise SkillLoadError(
                f"Cannot resolve adopted_persona {phase_def.adopted_persona!r} without skill base dir"
            )
        persona_manifest = resolve_persona(
            phase_def.adopted_persona,
            base_dir=skill_base_dir,
        )
        system_prompt = _inject_persona(persona_manifest, system_prompt)

    validator = cast(
        Callable[..., tuple[bool, list[str]]] | None,
        (module_sandbox.import_callable(phase_def.validator) if phase_def.validator else None),
    )
    if validator is not None and phase_def.hoist_to:
        validator.hoist_to = phase_def.hoist_to  # type: ignore[attr-defined]

    phase = Phase(
        name=phase_def.name,
        system_prompt=system_prompt,
        user_prompt_template=phase_def.user_prompt_template,
        tools=[
            cast(Callable[..., str], module_sandbox.import_callable(ref))
            for ref in phase_def.agent_tools
        ],
        max_iterations=phase_def.max_iterations if phase_def.max_iterations is not None else 20,
        tier=phase_def.llm_role or "balanced",
        llm_role=phase_def.llm_role,
        model_override=phase_def.model_override,
        validator=validator,
        retry_target=phase_def.retry_target,
        max_retries=phase_def.max_retries if phase_def.max_retries is not None else 3,
        max_nudges=phase_def.max_nudges if phase_def.max_nudges is not None else 1,
        dead_end_threshold=(
            phase_def.dead_end_threshold if phase_def.dead_end_threshold is not None else 3
        ),
        references=[
            _resolve_reference_resource(skill_base_dir, reference)
            if skill_base_dir is not None
            else reference
            for reference in phase_def.references
        ],
        skill_base_dir=skill_base_dir,
        context_access=list(phase_def.context_access),
        output_schema=cast(Any, output_schema_cls or dynamic_schema),
        output_schema_path=phase_def.output_schema if output_schema_cls is not None else None,
        requires_llm=True,
    )
    phase.hoist_to = phase_def.hoist_to  # type: ignore[attr-defined]
    return phase, output_schema_cls


def _logic_phase_for_node(
    phase_def: LogicPhase,
    module_sandbox: ModuleSandbox,
    *,
    skill_base_dir: Path | None,
) -> Phase:
    return Phase(
        name=phase_def.name,
        system_prompt=None,
        tools=[
            cast(Callable[..., str], module_sandbox.import_callable(ref))
            for ref in phase_def.execute_steps
        ],
        model_override=phase_def.model_override,
        validator=cast(
            Callable[..., tuple[bool, list[str]]] | None,
            (module_sandbox.import_callable(phase_def.validator) if phase_def.validator else None),
        ),
        skill_base_dir=skill_base_dir,
        requires_llm=False,
    )


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

    if kind == "schema":
        module_path_str = resource_path
        attr_name = ""
    else:
        parts = resource_path.rsplit(".", 1)
        if len(parts) != 2:
            raise SkillLoadError(
                f"Invalid {kind} reference '{resource_path}'. Expected format: module.path.name"
            )
        module_path_str, attr_name = parts

    if kind == "tool" and not attr_name:
        raise SkillLoadError(
            f"Invalid {kind} reference '{resource_path}'. Expected format: module.path.name"
        )

    if kind == "tool" and (module_path_str == "builtin" or module_path_str.startswith("builtin.")):
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

    resolved_module: Any = _LOCAL_MODULE_CACHE.get(
        f"_graph_agent_skill_.{_skill_namespace(base_dir)}.{module_path_str}"
    )
    if resolved_module is None:
        resolved_module = _load_skill_local_module(module_path_str, base_dir)
    if resolved_module is None:
        try:
            resolved_module = importlib.import_module(module_path_str)
        except ImportError as exc:
            raise SkillLoadError(
                f"Cannot import {kind} module '{module_path_str}' for '{resource_path}': {exc}"
            ) from exc

    if kind == "schema":
        return resolved_module

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
    """Append numbered prompt-structure steps as a ``<steps>`` XML tag.

    Round 8 §C blueprint: discrete schema fields render as XML tags so
    the LLM can attend to structure deterministically.
    """
    if not steps:
        return prompt
    lines = ["<steps>"]
    lines.extend(f"  {i}. {step}" for i, step in enumerate(steps, start=1))
    lines.append("</steps>")
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


def _compose_agent_system_prompt(
    manifest: AgentSkillDef,
    *,
    skill_base_dir: Path | None = None,
) -> str:
    """Assemble an agent skill's System Prompt using Round 8 §C XML tags.

    Wraps role/goal/constraints in dedicated XML tags so the LLM attends
    to structure deterministically. PM still writes natural-language
    field values; the compiler is responsible for the wrapping.

    Persona injection (when ``adopted_persona`` is set) is layered on
    top by the caller.
    """
    profile = manifest.agent_profile
    sections: list[str] = [
        f"<domain_expertise>\n  {profile.role}\n</domain_expertise>",
        f"<task_objective>\n  {profile.goal}\n</task_objective>",
    ]
    xml_tags = _render_skill_section_xml_tags(profile, skill_base_dir=skill_base_dir)
    if xml_tags:
        sections.append(xml_tags)
    if profile.steps:
        steps_lines = ["<steps>"]
        steps_lines.extend(f"  {i}. {step}" for i, step in enumerate(profile.steps, start=1))
        steps_lines.append("</steps>")
        sections.append("\n".join(steps_lines))
    if profile.constraints:
        constraints_lines = ["<constraints>"]
        constraints_lines.extend(f"  - {c}" for c in profile.constraints)
        constraints_lines.append("</constraints>")
        sections.append("\n".join(constraints_lines))
    return "\n\n".join(sections)


def _inject_persona(
    persona: PersonaSkillDef,
    system_prompt: str | None,
) -> str:
    """Combine a PersonaSkillDef with a phase's system prompt.

    Persona's ``role_profile`` establishes the LLM's identity and is layered
    *before* the phase-specific instructions. ``evaluation_rubrics`` (when
    present) sit between the two as a self-evaluation lens the LLM should
    apply. ``few_shot_examples`` are rendered into the same ``<examples>``
    tag used by AgentProfile / LLMPhase prompt-schema fields.
    """
    parts: list[str] = [persona.role_profile]
    if persona.evaluation_rubrics:
        parts.append("---")
        parts.append("## 评估标准")
        parts.append(persona.evaluation_rubrics)
    xml_tags = _render_skill_section_xml_tags(persona)
    if xml_tags:
        parts.append(xml_tags)
    parts.append("---")
    parts.append(system_prompt or "")
    return "\n\n".join(parts)


def _phase_from_agent_skill(
    manifest: AgentSkillDef,
    base_dir: Path,
    callbacks: list[Any] | None,
    loading_stack: set[str],
) -> Phase:
    """Build the single runtime Phase for a ``type: agent`` manifest.

    Dispatched from ``load_workflow_from_md`` for ``type: agent``; the
    DeerFlow agent loop receives the composed system prompt and the
    resolved tool callables.
    """
    del callbacks, loading_stack  # unused in agent path; reserved for persona resolution
    system_prompt = _compose_agent_system_prompt(manifest, skill_base_dir=base_dir)
    if manifest.adopted_persona is not None:
        persona_manifest = resolve_persona(
            manifest.adopted_persona,
            base_dir=base_dir,
        )
        system_prompt = _inject_persona(persona_manifest, system_prompt)
    tools = [_resolve_tool_reference(ref, base_dir) for ref in manifest.agent_tools]
    phase = Phase(
        name=manifest.name,
        system_prompt=system_prompt,
        user_prompt_template=manifest.user_prompt_template,
        tools=tools,
        tier=manifest.agent_profile.llm_role or "balanced",
        llm_role=manifest.agent_profile.llm_role,
        model_override=manifest.model_override,
        references=[
            resolve_skill_resource(base_dir, reference, kind="reference")
            for reference in manifest.agent_profile.references
        ],
        skill_base_dir=base_dir,
        context_access=list(manifest.agent_profile.context_access),
        requires_llm=True,
    )
    return phase


def _phase_from_graph_phase(
    phase_def: Any,  # PhaseDef (Annotated Union); runtime-typed to avoid pyright noise
    base_dir: Path,
    callbacks: list[Any] | None,
    loading_stack: set[str],
) -> Phase:
    """Dispatch on ``mode`` to build one runtime Phase from a GraphSkillDef.phases entry.

    Two branches matching the manifest's two phase modes:
    ``llm`` (ReAct loop) and ``logic`` (deterministic Python steps).
    The 1.x ``delegate`` / ``parallel_delegate`` modes were removed in
    MVP-0 B1 (2026-04-28).
    """
    del callbacks, loading_stack  # reserved for future cross-skill composition
    from graph_agent.core.manifest import LLMPhase as _LLMPhase
    from graph_agent.core.manifest import LogicPhase as _LogicPhase

    if isinstance(phase_def, _LLMPhase):
        tools = [_resolve_tool_reference(ref, base_dir) for ref in phase_def.agent_tools]
        if phase_def.output_example and phase_def.output_schema:
            raise SkillCompilationError(
                f"[F-output-example-conflict] SKILL.md:phases.{phase_def.name}: "
                "output_example and output_schema are mutually exclusive"
            )
        dynamic_schema = (
            _parse_output_example_or_raise(
                phase_def.output_example,
                location=f"SKILL.md:phases.{phase_def.name}.output_example",
            )
            if phase_def.output_example
            else None
        )
        if dynamic_schema is not None:
            dynamic_schema.hoist_to = phase_def.hoist_to  # type: ignore[attr-defined]
        output_schema_cls = (
            _resolve_output_schema_class(
                phase_def.output_schema,
                skill_base_dir=base_dir,
            )
            if phase_def.output_schema and dynamic_schema is None
            else None
        )
        system_prompt = phase_def.prompt
        xml_tags = _render_skill_section_xml_tags(phase_def, skill_base_dir=base_dir)
        if xml_tags:
            system_prompt = f"{system_prompt}\n\n{xml_tags}" if system_prompt else xml_tags
        if phase_def.steps:
            system_prompt = _append_steps_to_prompt(system_prompt or "", phase_def.steps)
        if phase_def.adopted_persona is not None:
            persona_manifest = resolve_persona(
                phase_def.adopted_persona,
                base_dir=base_dir,
            )
            system_prompt = _inject_persona(persona_manifest, system_prompt)
        validator = cast(
            Callable[..., tuple[bool, list[str]]] | None,
            (
                _resolve_tool_reference(phase_def.validator, base_dir)
                if phase_def.validator
                else None
            ),
        )
        if validator is not None and phase_def.hoist_to:
            validator.hoist_to = phase_def.hoist_to  # type: ignore[attr-defined]
        phase = Phase(
            name=phase_def.name,
            system_prompt=system_prompt,
            user_prompt_template=phase_def.user_prompt_template,
            tools=tools,
            max_iterations=phase_def.max_iterations if phase_def.max_iterations is not None else 20,
            tier=phase_def.llm_role or "balanced",
            llm_role=phase_def.llm_role,
            model_override=phase_def.model_override,
            validator=validator,
            retry_target=phase_def.retry_target,
            max_retries=phase_def.max_retries if phase_def.max_retries is not None else 3,
            max_nudges=phase_def.max_nudges if phase_def.max_nudges is not None else 1,
            dead_end_threshold=(
                phase_def.dead_end_threshold if phase_def.dead_end_threshold is not None else 3
            ),
            references=[
                resolve_skill_resource(base_dir, reference, kind="reference")
                for reference in phase_def.references
            ],
            skill_base_dir=base_dir,
            context_access=list(phase_def.context_access),
            # T5 keeps the resolved class on Phase for validation while
            # retaining the dotted path as metadata for diagnostics.
            output_schema=cast(Any, dynamic_schema or output_schema_cls),
            output_schema_path=None if dynamic_schema is not None else phase_def.output_schema,
            requires_llm=True,
        )
        phase.hoist_to = phase_def.hoist_to  # type: ignore[attr-defined]
        return phase

    if isinstance(phase_def, _LogicPhase):
        tools = [_resolve_tool_reference(ref, base_dir) for ref in phase_def.execute_steps]
        return Phase(
            name=phase_def.name,
            system_prompt=None,
            tools=tools,
            model_override=phase_def.model_override,
            validator=cast(
                Callable[..., tuple[bool, list[str]]] | None,
                (
                    _resolve_tool_reference(phase_def.validator, base_dir)
                    if phase_def.validator
                    else None
                ),
            ),
            requires_llm=False,
        )

    raise SkillLoadError(
        f"Unknown phase type for '{getattr(phase_def, 'name', '?')}': {type(phase_def).__name__}"
    )
