"""SKILL.md loader for GraphAgentHarness.

The loader turns a schema-2.0 SKILL.md file into a ready-to-run
``GraphAgentHarness``. The authoring surface is the YAML frontmatter
described by ``manifest.SkillManifest``:

- top-level: ``schema_version`` / ``name`` / ``description`` / ``type``
- artifact-specific: ``agent_profile`` (agent), ``io`` + ``phases``
  (graph), ``role_profile`` (persona)
- phase modes: ``llm`` (prompt + agent_tools + retry/output_schema),
  ``logic`` (deterministic execute_steps + validator)

The 1.x ``delegate`` / ``parallel_delegate`` phase modes (subgraph
composition + fan-out) were removed in MVP-0 B1 (2026-04-28). Static
cross-skill composition will return in V2 via LangGraph Send API.

The manifest carries runtime fields structurally. The markdown body is
purely human documentation and is not parsed for execution semantics.
"""

from __future__ import annotations

import importlib
import importlib.util
import hashlib
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from .parser import _parse_frontmatter

if TYPE_CHECKING:
    from .manifest import AgentSkillDef, PersonaSkillDef
from .exceptions import SkillCompilationError, SkillLoadError
from .harness import GraphAgentHarness, Phase
from .personas import resolve_persona
from ..tools.dynamic_schema import (
    DynamicSchemaDef,
    OutputExampleParseError,
    parse_output_example,
    render_dynamic_schema_output_format,
)

logger = logging.getLogger(__name__)


def _parse_output_example_or_raise(
    output_example: str,
    *,
    location: str,
) -> DynamicSchemaDef:
    """Parse ``output_example`` or surface a compile-fatal loader error."""
    try:
        return parse_output_example(output_example)
    except OutputExampleParseError as exc:
        raise SkillCompilationError(
            f"[F-output-example-invalid] {location}: {exc}"
        ) from exc


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
    if module_name in sys.modules:
        return sys.modules[module_name]

    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        raise SkillLoadError(f"Cannot load module spec for {py_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
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
                f"Invalid {kind} reference '{resource_path}'. "
                "Expected format: module.path.name"
            )
        module_path_str, attr_name = parts

    if kind == "tool" and not attr_name:
        raise SkillLoadError(
            f"Invalid {kind} reference '{resource_path}'. "
            "Expected format: module.path.name"
        )

    if kind == "tool" and (
        module_path_str == "builtin" or module_path_str.startswith("builtin.")
    ):
        try:
            from ..tools import builtin as _builtin_pkg  # noqa: F401

            submod_name = module_path_str[len("builtin"):].lstrip(".")
            full_module = "graph_agent.tools.builtin"
            if submod_name:
                full_module = f"{full_module}.{submod_name}"
            module = importlib.import_module(full_module)
        except ImportError as exc:
            raise SkillLoadError(
                f"Cannot import builtin tool '{resource_path}': {exc}"
            ) from exc

        try:
            func = getattr(module, attr_name)
        except AttributeError as exc:
            raise SkillLoadError(
                f"Builtin module '{full_module}' does not define '{attr_name}'"
            ) from exc

        if not callable(func):
            raise SkillLoadError(
                f"'{resource_path}' is not callable (got {type(func).__name__})"
            )
        return func  # type: ignore[return-value]

    module = sys.modules.get(
        f"_graph_agent_skill_.{_skill_namespace(base_dir)}.{module_path_str}"
    )
    if module is None:
        module = _load_skill_local_module(module_path_str, base_dir)
    if module is None:
        try:
            module = importlib.import_module(module_path_str)
        except ImportError as exc:
            raise SkillLoadError(
                f"Cannot import {kind} module '{module_path_str}' "
                f"for '{resource_path}': {exc}"
            ) from exc

    if kind == "schema":
        return module

    try:
        func = getattr(module, attr_name)
    except AttributeError as exc:
        raise SkillLoadError(
            f"Module for '{resource_path}' does not define '{attr_name}'"
        ) from exc

    if not callable(func):
        raise SkillLoadError(
            f"'{resource_path}' is not callable (got {type(func).__name__})"
        )

    return func  # type: ignore[return-value]


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
                f"Reference '{reference_path}' resolves outside skill directory: "
                f"{candidate}"
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
    return resolve_skill_resource(base_dir, ref_path, kind="tool")


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------


def load_workflow_from_md(
    md_path: str | Path,
    callbacks: list[Any] | None = None,
    _loading_stack: set[str] | None = None,
) -> GraphAgentHarness:
    """Load a SKILL.md file and compile it into a GraphAgentHarness.

    Supports schema-2.0 frontmatter ``type`` values:
    - ``agent``: single DeerFlow agent loop built from ``agent_profile``
    - ``graph``: ordered ``phases`` using ``llm`` / ``logic`` phase modes
    - ``persona``: not runnable directly; injected through
      ``adopted_persona``

    Args:
        md_path: Path to the SKILL.md file.
        callbacks: Optional callback list injected into the resulting harness.
        _loading_stack: Reserved for future cross-skill composition; the
            1.x subgraph-recursion consumer was removed in MVP-0 B1
            (2026-04-28). Callers should leave this as None.

    Returns:
        A compiled GraphAgentHarness ready for .run().

    Raises:
        SkillLoadError: On any parsing or validation failure.

    """
    md_path = Path(md_path)
    if not md_path.exists():
        raise SkillLoadError(f"SKILL.md not found: {md_path}")

    md_resolved = str(md_path.resolve())
    loading_stack = _loading_stack or set()
    if md_resolved in loading_stack:
        chain = " -> ".join([*sorted(loading_stack), md_resolved])
        raise SkillLoadError(f"Cyclic skill reference detected: {chain}")

    loading_stack.add(md_resolved)
    try:
        content = md_path.read_text(encoding="utf-8")
        base_dir = md_path.parent
        if not content.strip():
            raise SkillLoadError(f"SKILL.md is empty: {md_path}")

        # Step 1: Parse YAML frontmatter
        frontmatter = _parse_frontmatter(content)
        # Schema 2.0 is the only supported version. Cohesion plan 方针 2.3
        # (2026-04-26): the loader used to fall off the end of this
        # function for any other ``schema_version``, returning ``None`` —
        # callers then crashed with ``NoneType has no attribute 'run'``
        # far away from the real cause. Reuse the compiler's
        # ``F-schema-version`` wording so authors see one consistent
        # message regardless of which entry point fires first.
        # 方针 3.3: coerce via str() so unquoted YAML literals like
        # ``schema_version: 2.0`` (parsed as float) don't crash with
        # AttributeError before reaching the version check. Normalise
        # back to the canonical string so downstream Pydantic
        # ``Literal["2.0"]`` validation sees the right type.
        schema_version = str(frontmatter.get("schema_version") or "").strip()
        if schema_version != "2.0":
            raise SkillLoadError(
                f"Unsupported schema_version: {schema_version!r} in {md_path}. "
                'Only schema_version: "2.0" is supported.'
            )

        from pydantic import TypeAdapter
        from .compiler import compile_skill as _compile_check
        from .manifest import (
            AgentSkillDef,
            GraphSkillDef,
            PersonaSkillDef,
            SkillManifest,
        )
        from .parser import parse_skill_file as _parse_skill_file

        compile_result = _compile_check(md_path)
        for w in compile_result.warnings:
            logger.warning(
                "[Compiler] %s @ %s — %s",
                w.rule_id,
                w.location,
                w.message,
            )
        if not compile_result.passed:
            detail = "\n".join(
                f" [{f.rule_id}] {f.location}: {f.message}"
                for f in compile_result.fatals
            )
            raise SkillCompilationError(
                f"Skill has {len(compile_result.fatals)} FATAL error(s):\n{detail}",
                compile_result=compile_result,
            )
        parsed = _parse_skill_file(md_path)
        manifest = TypeAdapter(SkillManifest).validate_python(
            parsed["frontmatter"]
        )
        logger.info(
            "Loading schema-2.0 skill '%s' (%s) from %s",
            manifest.name,
            type(manifest).__name__,
            md_path,
        )
        if isinstance(manifest, PersonaSkillDef):
            raise SkillLoadError(
                "Persona skills are not runnable on their own — they "
                "are injected via adopted_persona."
            )
        if isinstance(manifest, AgentSkillDef):
            phases = [
                _phase_from_agent_skill(manifest, base_dir, callbacks, loading_stack)
            ]
        else:  # GraphSkillDef
            phases = [
                _phase_from_graph_phase(p, base_dir, callbacks, loading_stack)
                for p in manifest.phases
            ]
        raw_io = (
            manifest.io.model_dump() if isinstance(manifest, GraphSkillDef) else None
        )
        raw_context_mapping = (
            dict(manifest.context_mapping)
            if isinstance(manifest, GraphSkillDef) and manifest.context_mapping
            else None
        )
        return GraphAgentHarness(
            phases=phases,
            callbacks=callbacks,
            io_config=raw_io,
            context_mapping=raw_context_mapping,
            skill_dir=base_dir,
        )

    finally:
        loading_stack.discard(md_resolved)



def _append_steps_to_prompt(prompt: str, steps: list[str]) -> str:
    """Append numbered prompt-structure steps as a ``<steps>`` XML tag.

    Round 8 §C blueprint: discrete schema fields render as XML tags so
    the LLM can attend to structure deterministically.
    """
    if not steps:
        return prompt
    lines = ["<steps>"]
    lines.extend(
        f"  {i}. {step}" for i, step in enumerate(steps, start=1)
    )
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
            f"  [protocol:P{i}] {protocol}"
            for i, protocol in enumerate(domain_protocols, start=1)
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
        schema = _parse_output_example_or_raise(
            output_example,
            location=f"SKILL.md:phases.{getattr(phase_or_profile, 'name', 'unknown')}.output_example",
        )
        sections.append(
            "<output_format>\n"
            f"{render_dynamic_schema_output_format(schema)}\n"
            "</output_format>"
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
                "loader: output_schema %s is not a Pydantic BaseModel; "
                "skipping <output_format>",
                output_schema_path,
            )
            return ""

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

        reference_lines = [
            "",
            "字段说明：",
        ]
        for field_name, field_info in model_cls.model_fields.items():
            field_type = getattr(
                field_info.annotation,
                "__name__",
                str(field_info.annotation),
            )
            description = field_info.description or "（无描述）"
            required_marker = "（必填）" if field_info.is_required() else "（可选）"
            reference_lines.append(
                f"- **{field_name}** {required_marker}: "
                f"`{field_type}` — {description}"
            )

        return "\n".join(template_lines + reference_lines)

    except (ImportError, AttributeError, SkillLoadError, ValueError) as exc:
        logger.warning(
            "loader: failed to resolve output_schema %s: %s; "
            "skipping <output_format>",
            output_schema_path,
            exc,
        )
        return ""


def _compose_agent_system_prompt(
    manifest: "AgentSkillDef",
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
        steps_lines.extend(
            f"  {i}. {step}" for i, step in enumerate(profile.steps, start=1)
        )
        steps_lines.append("</steps>")
        sections.append("\n".join(steps_lines))
    if profile.constraints:
        constraints_lines = ["<constraints>"]
        constraints_lines.extend(f"  - {c}" for c in profile.constraints)
        constraints_lines.append("</constraints>")
        sections.append("\n".join(constraints_lines))
    return "\n\n".join(sections)


def _inject_persona(
    persona: "PersonaSkillDef",
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
    manifest: "AgentSkillDef",
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
            manifest.adopted_persona, base_dir=base_dir,
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
        subagent_enabled=manifest.subagent_enabled,
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
    from .manifest import LLMPhase as _LLMPhase
    from .manifest import LogicPhase as _LogicPhase

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
            setattr(dynamic_schema, "hoist_to", phase_def.hoist_to)
        system_prompt = phase_def.prompt
        xml_tags = _render_skill_section_xml_tags(phase_def, skill_base_dir=base_dir)
        if xml_tags:
            system_prompt = f"{system_prompt}\n\n{xml_tags}" if system_prompt else xml_tags
        if phase_def.steps:
            system_prompt = _append_steps_to_prompt(system_prompt or "", phase_def.steps)
        if phase_def.adopted_persona is not None:
            persona_manifest = resolve_persona(
                phase_def.adopted_persona, base_dir=base_dir,
            )
            system_prompt = _inject_persona(persona_manifest, system_prompt)
        validator = (
            _resolve_tool_reference(phase_def.validator, base_dir)
            if phase_def.validator
            else None
        )
        if validator is not None and phase_def.hoist_to:
            setattr(validator, "hoist_to", phase_def.hoist_to)
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
                phase_def.dead_end_threshold
                if phase_def.dead_end_threshold is not None
                else 3
            ),
            subagent_enabled=phase_def.subagent_enabled,
            references=[
                resolve_skill_resource(base_dir, reference, kind="reference")
                for reference in phase_def.references
            ],
            skill_base_dir=base_dir,
            context_access=list(phase_def.context_access),
            # 方针 1.3: thread output_schema dotted path so PhaseExecutor
            # can hand it to md_to_json. The runtime stores the path, not
            # the resolved class, because LangGraph's msgpack checkpointer
            # cannot serialise ModelMetaclass.
            output_schema=dynamic_schema,
            output_schema_path=None if dynamic_schema is not None else phase_def.output_schema,
            requires_llm=True,
        )
        setattr(phase, "hoist_to", phase_def.hoist_to)
        return phase

    if isinstance(phase_def, _LogicPhase):
        tools = [_resolve_tool_reference(ref, base_dir) for ref in phase_def.execute_steps]
        return Phase(
            name=phase_def.name,
            system_prompt=None,
            tools=tools,
            model_override=phase_def.model_override,
            validator=(
                _resolve_tool_reference(phase_def.validator, base_dir)
                if phase_def.validator
                else None
            ),
            requires_llm=False,
        )

    raise SkillLoadError(
        f"Unknown phase type for '{getattr(phase_def, 'name', '?')}': "
        f"{type(phase_def).__name__}"
    )
