"""SKILL.md loader for GraphAgentHarness.

The loader turns a Markdown skill file into executable ``Phase`` objects and a
ready-to-run ``GraphAgentHarness``. It is the only place that understands the
full SKILL authoring surface:

- YAML frontmatter: ``name`` / ``description`` / ``type`` / ``io`` / ``context_mapping``
- body tags: ``<phase_config>``, ``<system_prompt>``, ``<user_prompt>``,
  ``<user_prompt_builder>``, ``<data_architecture>``, ``<node>``, ``<ref>``
- phase options: ``tier``, ``tools``, ``validator``, ``retry_target``,
  ``max_iterations``, ``max_tool_calls``, ``max_retries``, ``max_nudges``,
  ``dead_end_threshold``, ``subagent_enabled``, ``subgraph``, ``context_bridge``
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

from .parser import (
    _NODE_PATTERN,
    _extract_tags,
    _normalise_phase_tags,
    _parse_frontmatter,
    _resolve_refs,
    _split_by_phase_headers,
    _strip_frontmatter,
    _validate_frontmatter,
)
from .exceptions import SkillCompilationError, SkillLoadError
from .harness import ContextBridge, GraphAgentHarness, Phase

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

    Supports two modes based on frontmatter ``type``:
    - ``simple`` (default): single agent loop with at most one phase
    - ``graph``: ``<node>`` + ``<ref>`` driven multi-node topology

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

        # Step 2: Validate frontmatter
        valid, msg, skill_name = _validate_frontmatter(frontmatter)
        if not valid:
            raise SkillLoadError(f"Frontmatter validation failed: {msg}")

        logger.info("Loading skill '%s' from %s", skill_name, md_path)

        # Step 2.5: Static compilation check (fail-fast)
        from .compiler import compile_skill as _compile_check

        compile_result = _compile_check(md_path)
        for w in compile_result.warnings:
            logger.warning(
                "[Compiler] %s @ %s — %s", w.rule_id, w.location, w.message,
            )
        if not compile_result.passed:
            detail = "\n".join(
                f"  [{f.rule_id}] {f.location}: {f.message}"
                for f in compile_result.fatals
            )
            raise SkillCompilationError(
                f"Skill '{skill_name}' has {len(compile_result.fatals)} FATAL error(s):\n{detail}",
                compile_result=compile_result,
            )

        # Step 3: Parse phases based on skill type
        skill_type = frontmatter.get("type", "simple")

        if skill_type == "simple":
            phases = _parse_simple_mode(
                content=content,
                base_dir=base_dir,
                callbacks=callbacks,
                loading_stack=loading_stack,
            )
        elif skill_type == "graph":
            phases = _parse_graph_mode(
                content=content,
                base_dir=base_dir,
                callbacks=callbacks,
                loading_stack=loading_stack,
            )
        else:
            raise SkillLoadError(
                f"Unknown skill type '{skill_type}'. Supported: simple, graph"
            )

        # Step 4: Build harness (no longer needs LLMGateway — uses Model Resolver)
        raw_io = frontmatter.get("io")
        if raw_io is not None and not isinstance(raw_io, dict):
            logger.warning("[Loader] 'io' frontmatter is not a dict (got %s), ignoring", type(raw_io).__name__)
            raw_io = None
        raw_context_mapping = frontmatter.get("context_mapping")
        if raw_context_mapping is not None and not isinstance(raw_context_mapping, dict):
            logger.warning("[Loader] 'context_mapping' frontmatter is not a dict (got %s), ignoring", type(raw_context_mapping).__name__)
            raw_context_mapping = None
        return GraphAgentHarness(
            phases=phases,
            callbacks=callbacks,
            io_config=raw_io,
            context_mapping=raw_context_mapping,
            skill_dir=base_dir,
        )
    finally:
        loading_stack.discard(md_resolved)


# ---------------------------------------------------------------------------
# Simple mode: single agent loop (at most one phase)
# ---------------------------------------------------------------------------


def _parse_simple_mode(
    content: str,
    base_dir: Path,
    callbacks: list[Any] | None,
    loading_stack: set[str],
) -> list[Phase]:
    """Parse SKILL.md in simple mode — single agent loop, at most one phase.

    Simple mode creates exactly ONE Phase for a single agent execution loop.
    Three accepted formats (checked in order):

    1. No ``## Phase N:`` headers → extract XML tags directly from body.
    2. Exactly one ``## Phase N:`` header → parse that section.
    3. Multiple ``## Phase N:`` headers → error (use ``type: graph`` instead).

    If no ``<phase_config>`` tag is found in format 1, a sensible default is
    generated so that minimal simple skills only need ``<system_prompt>``.
    """
    phase_sections = _split_by_phase_headers(content)

    if len(phase_sections) > 1:
        raise SkillLoadError(
            f"Simple mode supports at most one phase, found {len(phase_sections)}. "
            "Use type: graph for multi-phase workflows."
        )

    if len(phase_sections) == 1:
        title, section_text = phase_sections[0]
        tags = _extract_tags(section_text)
    else:
        body = _strip_frontmatter(content)
        tags = _extract_tags(body)
        title = "main"

        if not tags.get("phase_config"):
            tags["phase_config"] = ["name: main\ntier: balanced\nmax_iterations: 20"]

    phase, errors = _build_phase_from_tags(
        label=title,
        tags=tags,
        base_dir=base_dir,
        callbacks=callbacks,
        loading_stack=loading_stack,
    )

    if errors:
        raise SkillLoadError(
            f"Failed to resolve {len(errors)} tool reference(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return [phase] if phase else []


# ---------------------------------------------------------------------------
# Graph mode: <node> + <ref> topology
# ---------------------------------------------------------------------------

def _parse_graph_mode(
    content: str,
    base_dir: Path,
    callbacks: list[Any] | None,
    loading_stack: set[str],
) -> list[Phase]:
    """Parse SKILL.md in graph mode — ``<node>`` tags with optional ``<ref>``."""
    # Task 5.3: accept <phase> as a synonym for <node> so authors can migrate
    # without breaking existing skills that still use <node>.
    content = _normalise_phase_tags(content)
    nodes = list(_NODE_PATTERN.finditer(content))
    if not nodes:
        raise SkillLoadError("No '<phase>' or '<node>' tags found (graph mode)")

    phases: list[Phase] = []
    import_errors: list[str] = []

    for match in nodes:
        node_id = match.group(1)
        # depends_on = match.group(2)  # Reserved for future DAG execution
        node_content = match.group(3).strip()

        # Resolve <ref> tags within node content
        resolved_content = _resolve_refs(node_content, base_dir)

        # Extract XML tags from resolved content
        tags = _extract_tags(resolved_content)

        phase, errors = _build_phase_from_tags(
            label=node_id,
            tags=tags,
            base_dir=base_dir,
            callbacks=callbacks,
            loading_stack=loading_stack,
        )
        if errors:
            import_errors.extend(errors)
        if phase:
            phases.append(phase)

    if import_errors:
        raise SkillLoadError(
            f"Failed to resolve {len(import_errors)} tool reference(s):\n"
            + "\n".join(f"  - {e}" for e in import_errors)
        )

    return phases


# ---------------------------------------------------------------------------
# Shared: build Phase from extracted XML tags
# ---------------------------------------------------------------------------


def _parse_sub_skill_decl(decl: dict[str, Any], *, base_dir: Path) -> "SubSkillSpec":
    """Parse and validate a single sub_skill declaration dict."""
    from .skill_tool_factory import SubSkillSpec

    required = ("name", "description", "skill_path", "input_schema")
    for key in required:
        if key not in decl:
            raise ValueError(f"sub_skill declaration missing required field: '{key}'")

    return SubSkillSpec(
        name=decl["name"],
        description=decl["description"],
        skill_path=decl["skill_path"],
        input_schema=decl["input_schema"],
        _parent_skill_dir=base_dir,
    )


def _build_phase_from_tags(
    label: str,
    tags: dict[str, list[str]],
    base_dir: Path,
    callbacks: list[Any] | None,
    loading_stack: set[str],
) -> tuple[Phase | None, list[str]]:
    """Build a Phase from extracted XML tags.

    Args:
        label: Phase title (simple mode) or node id (graph mode).
        tags: Extracted XML tags from the section/node content.
        base_dir: Base directory for resolving tool references.
        callbacks: Callback list passed to nested subgraphs.
        loading_stack: Recursion guard for nested ``subgraph`` loading.

    Returns:
        (Phase, []) on success, or (None, [error_messages]) on failure.

    The resulting Phase may be populated from multiple sources:

    - ``<phase_config>``: name, tier, tools, validator, retry_target,
      max_iterations, max_tool_calls, max_retries, max_nudges,
      dead_end_threshold, subagent_enabled, subgraph, context_bridge
    - ``<system_prompt>``: ``Phase.system_prompt``
    - ``<user_prompt>`` / ``<user_prompt_builder>``: ``Phase.user_prompt_template``
    - ``<data_architecture>``: ``Phase.data_architecture``

    """
    import_errors: list[str] = []

    # Parse phase_config
    phase_config_texts = tags.get("phase_config", [])
    if not phase_config_texts:
        raise SkillLoadError(f"Phase '{label}' missing <phase_config> tag")

    try:
        phase_cfg = yaml.safe_load(phase_config_texts[0])
    except yaml.YAMLError as exc:
        raise SkillLoadError(
            f"Invalid YAML in <phase_config> of '{label}': {exc}"
        ) from exc

    if not isinstance(phase_cfg, dict):
        raise SkillLoadError(f"<phase_config> in '{label}' must be a YAML dict")

    default_phase_name = label.lower().replace(" ", "_")
    phase_name = _phase_string(
        phase_cfg,
        "name",
        label,
        default=default_phase_name,
    ) or default_phase_name

    # Parse subgraph config first (mutually exclusive with LLM prompt/tool config).
    subgraph_harness: GraphAgentHarness | None = None
    context_bridge: ContextBridge | None = None
    subgraph_path = phase_cfg.get("subgraph")
    if subgraph_path is not None:
        if not isinstance(subgraph_path, str) or not subgraph_path.strip():
            raise SkillLoadError(
                f"Phase '{label}' has invalid 'subgraph' value. Expected non-empty string path."
            )

        child_skill_path = (base_dir / subgraph_path).resolve()
        if not child_skill_path.exists():
            raise SkillLoadError(
                f"Phase '{label}' subgraph not found: {child_skill_path}"
            )

        subgraph_harness = load_workflow_from_md(
            md_path=child_skill_path,
            callbacks=callbacks,
            _loading_stack=loading_stack,
        )

        bridge_cfg = phase_cfg.get("context_bridge") or {}
        if not isinstance(bridge_cfg, dict):
            raise SkillLoadError(
                f"Phase '{label}' context_bridge must be a YAML dict"
            )
        bridge_inputs = bridge_cfg.get("inputs") or {}
        bridge_outputs = bridge_cfg.get("outputs") or {}
        if not isinstance(bridge_inputs, dict) or not isinstance(bridge_outputs, dict):
            raise SkillLoadError(
                f"Phase '{label}' context_bridge.inputs/outputs must be YAML dicts"
            )
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in bridge_inputs.items()):
            raise SkillLoadError(
                f"Phase '{label}' context_bridge.inputs must map string->string"
            )
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in bridge_outputs.items()):
            raise SkillLoadError(
                f"Phase '{label}' context_bridge.outputs must map string->string"
            )
        context_bridge = ContextBridge(inputs=bridge_inputs, outputs=bridge_outputs)

    # Parse system_prompt
    system_prompts = tags.get("system_prompt", [])
    system_prompt = system_prompts[0] if system_prompts else None
    requires_llm = (system_prompt is not None) and (subgraph_harness is None)

    # Parse user_prompt_builder (also accept user_prompt as alias)
    user_prompts = tags.get("user_prompt_builder", []) or tags.get("user_prompt", [])
    user_prompt_template = user_prompts[0] if user_prompts else None

    # Parse optional data_architecture section
    data_architectures = tags.get("data_architecture", [])
    data_architecture = data_architectures[0] if data_architectures else None

    # Resolve tool references
    tool_refs = _phase_string_list(phase_cfg, "tools", label)
    tools: list[Callable[..., str]] = []
    if subgraph_harness is None:
        for ref in tool_refs:
            try:
                fn = _resolve_tool_reference(ref, base_dir)
                tools.append(fn)
            except SkillLoadError as exc:
                import_errors.append(str(exc))

    # Resolve sub_skill declarations (zero-Python cross-skill calling)
    if subgraph_harness is None:
        sub_skill_decls = phase_cfg.get("sub_skills", []) or []
        for decl in sub_skill_decls:
            try:
                spec = _parse_sub_skill_decl(decl, base_dir=base_dir)
                from .skill_tool_factory import build_skill_tool
                tool = build_skill_tool(spec)
                tools.append(tool)
            except (KeyError, ValueError) as exc:
                import_errors.append(f"sub_skill '{decl.get('name', '?')}': {exc}")

    # Resolve validator reference
    validator: Callable[..., tuple[bool, list[str]]] | None = None
    validator_ref = _phase_string(phase_cfg, "validator", label)
    if validator_ref:
        try:
            validator = _resolve_tool_reference(validator_ref, base_dir)  # type: ignore[assignment]
        except SkillLoadError as exc:
            import_errors.append(str(exc))

    # Resolve optional schema tag for md_to_json type dict injection
    output_schema: type[BaseModel] | None = None
    output_schema_path: str | None = None
    md_type_dict: str | None = None
    schema_ref = _phase_string(phase_cfg, "schema", label)
    if schema_ref:
        try:
            schema_cls = _resolve_tool_reference(schema_ref, base_dir)
            from ..tools.md_to_json import schema_to_type_dict
            from pydantic import BaseModel as _BaseModel
            if isinstance(schema_cls, type) and issubclass(schema_cls, _BaseModel):
                output_schema = schema_cls
                # Fully-qualified path for checkpointer-safe ctx injection.
                # _resolve_tool_reference registers the module in sys.modules under a
                # namespaced name; __module__ on the class reflects that, making this
                # path resolvable later via sys.modules lookup.
                output_schema_path = f"{schema_cls.__module__}.{schema_cls.__name__}"
                type_dict_str = schema_to_type_dict(schema_cls)
                md_type_dict = type_dict_str
                if system_prompt and "{md_type_dict}" in system_prompt:
                    system_prompt = system_prompt.replace("{md_type_dict}", type_dict_str)
                elif system_prompt:
                    system_prompt = system_prompt + "\n\n" + type_dict_str
            else:
                logger.warning("schema tag %s is not a BaseModel subclass, skipping", schema_ref)
        except SkillLoadError:
            logger.warning("schema tag 解析失败: %s, 跳过 type dict 注入", schema_ref)

    tier = _phase_string(phase_cfg, "tier", label, default="balanced") or "balanced"
    retry_target = _phase_string(phase_cfg, "retry_target", label)
    phase = Phase(
        name=phase_name,
        system_prompt=system_prompt if subgraph_harness is None else None,
        tools=tools,
        max_iterations=_phase_int(phase_cfg, "max_iterations", label, default=20),
        max_tool_calls=_phase_int(phase_cfg, "max_tool_calls", label, default=0),
        tier=tier,
        # Task 6.1: model_override is an optional per-phase pin into
        # llm_roles.yaml's models: section. None = use tier → role → model
        # resolution as before.
        model_override=_phase_string(phase_cfg, "model_override", label),
        validator=validator,
        retry_target=retry_target,
        max_retries=_phase_int(phase_cfg, "max_retries", label, default=3),
        user_prompt_template=user_prompt_template,
        requires_llm=requires_llm,
        # Task 6.5: default budget drops from 3 to 1. Explicit phase_config
        # values still win.
        max_nudges=_phase_int(phase_cfg, "max_nudges", label, default=1),
        dead_end_threshold=_phase_int(phase_cfg, "dead_end_threshold", label, default=3),
        data_architecture=data_architecture,
        subagent_enabled=_phase_bool(phase_cfg, "subagent_enabled", label, default=False),
        subgraph=subgraph_harness,
        context_bridge=context_bridge,
        output_schema=output_schema,
        output_schema_path=output_schema_path,
        md_type_dict=md_type_dict,
    )

    return phase, import_errors
