"""SKILL.md loader for GraphAgentHarness.

The loader turns a schema-2.0 SKILL.md file into a ready-to-run
``GraphAgentHarness``. The authoring surface is the YAML frontmatter
described by ``manifest.SkillManifest``:

- top-level: ``schema_version`` / ``name`` / ``description`` / ``type``
- artifact-specific: ``agent_profile`` (agent), ``io`` + ``phases``
  (graph), ``role_profile`` (persona)
- phase modes: ``llm`` (prompt + agent_tools + retry/output_schema),
  ``logic`` (deterministic execute_steps + validator), ``delegate``
  (subgraph + context_bridge)

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
from typing import Any

import yaml

from .parser import _parse_frontmatter
from .exceptions import SkillCompilationError, SkillLoadError
from .harness import ContextBridge, GraphAgentHarness, Phase
from .personas import resolve_persona

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dynamic import (adapted from DeerFlow reflection/resolvers.py)
# ---------------------------------------------------------------------------


def _resolve_tool_reference(
    ref_path: str,
    base_dir: Path,
) -> Callable[..., str]:
    """Resolve a dot-path tool reference to a Python callable.

    The reference format is: module.submodule.function_name
    The last dot separates the module path from the function name.
    Modules are resolved relative to base_dir, with one special case:
    references that start with ``builtin.`` are resolved against the
    framework-owned ``graph_agent.tools.builtin`` package so any SKILL.md
    can write ``tools: [builtin.parallel_map]`` without copying the file
    into the skill directory.

    Adapted from DeerFlow reflection/resolvers.py L25-70, with separator
    changed from ':' to '.' (last dot = function separator).

    Args:
        ref_path: Dot-separated path like 'tools.analysis_tools.inspect_entity'
            or 'builtin.parallel_map' for framework-owned tools.
        base_dir: Base directory for relative imports (SKILL.md parent dir)

    Returns:
        The resolved Python callable.

    Raises:
        SkillLoadError: If the import fails.

    """
    parts = ref_path.rsplit(".", 1)
    if len(parts) != 2:
        raise SkillLoadError(
            f"Invalid tool reference '{ref_path}'. Expected format: module.path.function_name"
        )

    module_path_str, func_name = parts

    # Framework builtins live inside the graph_agent package itself so they
    # can't live under the caller's skill directory. We import them via
    # normal Python import path resolution instead of file-path loading.
    if module_path_str == "builtin" or module_path_str.startswith("builtin."):
        try:
            import importlib as _importlib
            from ..tools import builtin as _builtin_pkg  # noqa: F401
            submod_name = module_path_str[len("builtin"):].lstrip(".")
            full_module = "graph_agent.tools.builtin"
            if submod_name:
                full_module = f"{full_module}.{submod_name}"
            module = _importlib.import_module(full_module)
        except ImportError as exc:
            raise SkillLoadError(
                f"Cannot import builtin tool '{ref_path}': {exc}"
            ) from exc

        try:
            func = getattr(module, func_name)
        except AttributeError as exc:
            raise SkillLoadError(
                f"Builtin module '{full_module}' does not define '{func_name}'"
            ) from exc

        if not callable(func):
            raise SkillLoadError(
                f"'{ref_path}' is not callable (got {type(func).__name__})"
            )
        return func  # type: ignore[return-value]

    # Convert dot path to file path relative to base_dir
    module_file = base_dir / module_path_str.replace(".", "/")
    # Try as .py file
    py_file = module_file.with_suffix(".py")
    if not py_file.exists():
        # Try as package __init__.py
        init_file = module_file / "__init__.py"
        if init_file.exists():
            py_file = init_file
        else:
            raise SkillLoadError(
                f"Cannot find module for '{ref_path}': tried {py_file} and {init_file}"
            )

    # Validate resolved path stays within skill directory
    if not py_file.resolve().is_relative_to(base_dir.resolve()):
        raise SkillLoadError(
            f"Tool reference '{ref_path}' resolves outside skill directory: {py_file}"
        )

    # Dynamic import using importlib
    skill_namespace = hashlib.sha256(
        str(base_dir.resolve()).encode("utf-8")
    ).hexdigest()[:20]
    module_name = f"_graph_agent_skill_.{skill_namespace}.{module_path_str}"
    try:
        importlib.invalidate_caches()
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            raise SkillLoadError(f"Cannot load module spec for {py_file}")

        module = importlib.util.module_from_spec(spec)
        # Register in sys.modules before exec (needed for `from __future__` + dataclass)
        sys.modules[module_name] = module
        source = py_file.read_text(encoding="utf-8")
        code = compile(source, str(py_file), "exec")
        try:
            exec(code, module.__dict__)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
    except SkillLoadError:
        raise
    except Exception as exc:
        raise SkillLoadError(f"Error importing '{ref_path}' from {py_file}: {exc}") from exc

    try:
        func = getattr(module, func_name)
    except AttributeError as exc:
        raise SkillLoadError(f"Module {py_file} does not define '{func_name}'") from exc

    if not callable(func):
        raise SkillLoadError(f"'{ref_path}' is not callable (got {type(func).__name__})")

    return func  # type: ignore[return-value]


def _phase_string(
    phase_cfg: dict[str, Any],
    key: str,
    label: str,
    *,
    default: str | None = None,
    allow_empty: bool = False,
) -> str | None:
    """Read a string phase_config field with runtime type validation."""
    raw = phase_cfg.get(key, default)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise SkillLoadError(
            f"Phase '{label}' key '{key}' must be a string, got {type(raw).__name__}"
        )
    value = raw.strip()
    if value or allow_empty:
        return value
    if default is None:
        return None
    raise SkillLoadError(f"Phase '{label}' key '{key}' must be a non-empty string")


def _phase_int(
    phase_cfg: dict[str, Any],
    key: str,
    label: str,
    *,
    default: int,
) -> int:
    """Read an integer phase_config field and reject bool/float drift."""
    raw = phase_cfg.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise SkillLoadError(
            f"Phase '{label}' key '{key}' must be an integer, got {type(raw).__name__}"
        )
    return raw


def _phase_bool(
    phase_cfg: dict[str, Any],
    key: str,
    label: str,
    *,
    default: bool,
) -> bool:
    """Read a boolean phase_config field with strict typing."""
    raw = phase_cfg.get(key, default)
    if not isinstance(raw, bool):
        raise SkillLoadError(
            f"Phase '{label}' key '{key}' must be a boolean, got {type(raw).__name__}"
        )
    return raw


def _phase_string_list(
    phase_cfg: dict[str, Any],
    key: str,
    label: str,
) -> list[str]:
    """Read a list[str] phase_config field."""
    raw = phase_cfg.get(key, [])
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SkillLoadError(
            f"Phase '{label}' key '{key}' must be a YAML list, got {type(raw).__name__}"
        )

    normalized: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise SkillLoadError(
                f"Phase '{label}' key '{key}' must contain non-empty strings only"
            )
        normalized.append(item.strip())
    return normalized


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
    - ``graph``: ordered ``phases`` using ``llm`` / ``logic`` /
      ``delegate`` phase modes
    - ``persona``: not runnable directly; injected through
      ``adopted_persona``

    Args:
        md_path: Path to the SKILL.md file.
        callbacks: Optional callback list injected into the resulting harness.
        _loading_stack: Internal recursion guard used when skills reference
            sub-skills via ``subgraph``. Callers should leave this as None.

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



def _compose_agent_system_prompt(manifest: "AgentSkillDef") -> str:
    """Assemble an agent skill's System Prompt from its agent_profile.

    Joins ``role`` + ``goal`` + ``steps`` + ``constraints`` into the prose
    form the DeerFlow agent loop expects. Persona injection is layered
    on top by the caller when ``adopted_persona`` is set.
    """
    profile = manifest.agent_profile
    parts: list[str] = [f"你是{profile.role}。", f"你的目标:{profile.goal}"]
    if profile.steps:
        parts.append("## 工作流")
        parts.extend(f"{i}. {step}" for i, step in enumerate(profile.steps, start=1))
    if profile.constraints:
        parts.append("## 约束")
        parts.extend(f"- {c}" for c in profile.constraints)
    return "\n\n".join(parts)


def _inject_persona(
    persona: "PersonaSkillDef",
    system_prompt: str | None,
) -> str:
    """Combine a PersonaSkillDef with a phase's system prompt.

    Persona's ``role_profile`` establishes the LLM's identity and is layered
    *before* the phase-specific instructions. ``evaluation_rubrics`` (when
    present) sit between the two as a self-evaluation lens the LLM should
    apply. ``few_shot_examples`` would need a messages-history surface that
    Phase doesn't yet expose; raising rather than silently dropping the field
    forces authors to either remove it or wait for the runtime to land.

    Future work: wire ``few_shot_examples`` through the LLM client as
    pre-filled assistant/user pairs, then drop the NotImplementedError.
    """
    if persona.few_shot_examples:
        raise NotImplementedError(
            f"Persona '{persona.name}' declares few_shot_examples, but the "
            "runtime does not yet materialise them as pre-filled message "
            "history. Leave the list empty until the wiring lands."
        )
    parts: list[str] = [persona.role_profile]
    if persona.evaluation_rubrics:
        parts.append("---")
        parts.append("## 评估标准")
        parts.append(persona.evaluation_rubrics)
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
    system_prompt = _compose_agent_system_prompt(manifest)
    if manifest.adopted_persona is not None:
        persona_manifest = resolve_persona(
            manifest.adopted_persona, base_dir=base_dir,
        )
        system_prompt = _inject_persona(persona_manifest, system_prompt)
    tools = [_resolve_tool_reference(ref, base_dir) for ref in manifest.agent_tools]
    return Phase(
        name=manifest.name,
        system_prompt=system_prompt,
        user_prompt_template=manifest.user_prompt_template,
        tools=tools,
        tier=manifest.tier or "balanced",
        model_override=manifest.model_override,
        subagent_enabled=manifest.subagent_enabled,
        requires_llm=True,
    )


def _phase_from_graph_phase(
    phase_def: Any,  # PhaseDef (Annotated Union); runtime-typed to avoid pyright noise
    base_dir: Path,
    callbacks: list[Any] | None,
    loading_stack: set[str],
) -> Phase:
    """Dispatch on ``mode`` to build one runtime Phase from a GraphSkillDef.phases entry.

    Three branches matching the manifest's three phase modes:
    ``llm`` (ReAct loop), ``logic`` (deterministic Python steps),
    ``delegate`` (recursive load of a child SKILL.md).
    """
    # Imported inside the function to keep the dead-code block self-contained
    # until the Commit-2 switch; avoids polluting module-level imports.
    from .manifest import DelegatePhase as _DelegatePhase
    from .manifest import LLMPhase as _LLMPhase
    from .manifest import LogicPhase as _LogicPhase

    if isinstance(phase_def, _LLMPhase):
        tools = [_resolve_tool_reference(ref, base_dir) for ref in phase_def.agent_tools]
        system_prompt = phase_def.prompt
        if phase_def.adopted_persona is not None:
            persona_manifest = resolve_persona(
                phase_def.adopted_persona, base_dir=base_dir,
            )
            system_prompt = _inject_persona(persona_manifest, system_prompt)
        return Phase(
            name=phase_def.name,
            system_prompt=system_prompt,
            user_prompt_template=phase_def.user_prompt_template,
            tools=tools,
            max_iterations=phase_def.max_iterations if phase_def.max_iterations is not None else 20,
            tier=phase_def.tier or "balanced",
            model_override=phase_def.model_override,
            validator=(
                _resolve_tool_reference(phase_def.validator, base_dir)
                if phase_def.validator
                else None
            ),
            retry_target=phase_def.retry_target,
            max_retries=phase_def.max_retries if phase_def.max_retries is not None else 3,
            max_nudges=phase_def.max_nudges if phase_def.max_nudges is not None else 1,
            dead_end_threshold=(
                phase_def.dead_end_threshold
                if phase_def.dead_end_threshold is not None
                else 3
            ),
            subagent_enabled=phase_def.subagent_enabled,
            # 方针 1.3: thread output_schema dotted path so PhaseExecutor
            # can hand it to md_to_json. The runtime stores the path, not
            # the resolved class, because LangGraph's msgpack checkpointer
            # cannot serialise ModelMetaclass.
            output_schema_path=phase_def.output_schema,
            requires_llm=True,
        )

    if isinstance(phase_def, _LogicPhase):
        tools = [_resolve_tool_reference(ref, base_dir) for ref in phase_def.execute_steps]
        return Phase(
            name=phase_def.name,
            system_prompt=None,
            tools=tools,
            tier=phase_def.tier or "balanced",
            model_override=phase_def.model_override,
            validator=(
                _resolve_tool_reference(phase_def.validator, base_dir)
                if phase_def.validator
                else None
            ),
            # 方针 1.1: thread retry fields into runtime Phase so a
            # logic-phase validator failure routes through RetryRouter the
            # same way an LLM-phase validator failure does.
            retry_target=phase_def.retry_target,
            max_retries=phase_def.max_retries if phase_def.max_retries is not None else 3,
            requires_llm=False,
        )

    if isinstance(phase_def, _DelegatePhase):
        child_path = (base_dir / phase_def.subgraph).resolve()
        # Cohesion plan 方针 4.4 (2026-04-26): a path that exists but is
        # a directory used to slip past ``exists()`` and crash later in
        # ``read_text`` with ``IsADirectoryError`` — far away from the
        # author's typo. Match the compile-time validator's contract:
        # the subgraph reference must point at a regular file.
        if not child_path.is_file():
            raise SkillLoadError(
                f"Delegate phase '{phase_def.name}' subgraph not found "
                f"(or not a file): {child_path}"
            )
        child_harness = load_workflow_from_md(
            md_path=child_path,
            callbacks=callbacks,
            _loading_stack=loading_stack,
        )
        return Phase(
            name=phase_def.name,
            system_prompt=None,
            tools=[],
            tier=phase_def.tier or "balanced",
            model_override=phase_def.model_override,
            subgraph=child_harness,
            context_bridge=ContextBridge(
                inputs=dict(phase_def.context_bridge.inputs),
                outputs=dict(phase_def.context_bridge.outputs),
            ),
            requires_llm=False,
        )

    raise SkillLoadError(
        f"Unknown phase type for '{getattr(phase_def, 'name', '?')}': "
        f"{type(phase_def).__name__}"
    )
