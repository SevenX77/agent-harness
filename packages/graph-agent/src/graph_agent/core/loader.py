"""V0.3.0 graph skill loader: route GRAPH.md + phase node documents."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import logging
import re
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, NoReturn

from jsonschema.exceptions import SchemaError
from jsonschema.validators import Draft202012Validator
from pydantic import BaseModel, ValidationError

from graph_agent.cognitive.context_facade import Context
from graph_agent.core.actions import ActionDef, ActionRegistry, ToolDef, ToolRegistry
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError
from graph_agent.core.manifest import (
    AgentNodeAST,
    GraphManifest,
    LogicNodeAST,
    SubgraphNodeAST,
)
from graph_agent.core.mentions import first_broken_mention, scan_mentions
from graph_agent.core.parser import (
    extract_raw_blocks,
    parse_markdown_parts,
    scan_forbidden_topology_tags,
)
from graph_agent.core.purity import scan_python_purity, scan_tool_imports_context
from graph_agent.core.skill_resolver_protocol import (
    SkillResolverProtocol,
    require_skill_resolver,
    resolve_skill_root,
)
from graph_agent.core.subagents import build_subagent_input_model, build_subagent_tool_args_model

logger = logging.getLogger(__name__)

RouteKind = Literal["graph", "logic", "subgraph", "agent"]
PhaseAST = LogicNodeAST | SubgraphNodeAST | AgentNodeAST

_PHASE_FILE_TO_MODE: dict[str, str] = {
    "LOGIC.md": "logic",
    "SUBGRAPH.md": "subgraph",
    "SKILL.md": "agent",
}


@dataclass(frozen=True)
class PhaseDocument:
    """One routed V2.1 phase document plus its typed AST."""

    phase_name: str
    path: Path
    mode: str
    frontmatter: dict[str, Any]
    raw_blocks: dict[str, str]
    ast: PhaseAST


@dataclass(frozen=True)
class CompiledSkill:
    """T0.1 route/parse result emitted by SkillLoader."""

    raw: dict[str, Any]
    manifest: GraphManifest
    nodes: list[PhaseDocument] = field(default_factory=list)
    actions: ActionRegistry = field(default_factory=ActionRegistry.empty)
    tools: ToolRegistry = field(default_factory=ToolRegistry.empty)
    subagents_by_phase: dict[str, list[CompiledSubagent]] = field(default_factory=dict)
    phase_tokens: dict[str, PhaseTokenInfo] = field(default_factory=dict)


@dataclass(frozen=True)
class CompiledSubagent:
    """Resolved sub-skill metadata declared on a parent SKILL phase."""

    parent_phase_id: str
    name: str
    target_skill: str
    description: str
    root: Path
    input_schema: dict[str, Any]
    input_model: type[BaseModel]
    expected_schema: dict[str, Any]


@dataclass(frozen=True)
class PhaseAttributeSpan:
    """Source span for one attribute inside a root GRAPH.md phase tag."""

    name: str
    value: str
    quote: str
    attr_start: int
    attr_end: int
    value_start: int
    value_end: int
    line_start: int
    line_end: int


@dataclass(frozen=True)
class PhaseTokenInfo:
    """Internal source token metadata for serializer round-trip work."""

    phase_id: str
    raw_text: str
    start_offset: int
    end_offset: int
    line_start: int
    line_end: int
    attrs: dict[str, str]
    attr_spans: dict[str, PhaseAttributeSpan]


@dataclass(frozen=True)
class BodyPhaseRef:
    """One GRAPH.md body ``<phase>`` topology declaration."""

    name: str
    depends_on: tuple[str, ...]
    output: bool
    token: PhaseTokenInfo


class SkillLoader:
    """Thin V0.3.0 parser/route orchestrator."""

    def __init__(
        self,
        *args: Any,
        validate_context_writes: bool = True,
        **kwargs: Any,
    ) -> None:
        del args, kwargs
        self.validate_context_writes = validate_context_writes

    def compile_skill(
        self,
        skill_root: str | Path,
        *,
        skill_resolver: SkillResolverProtocol | None = None,
    ) -> CompiledSkill:
        root = Path(skill_root)
        _guard_v030_root(root)

        graph_path = root / "GRAPH.md"
        graph_frontmatter, graph_body, line_meta = parse_markdown_parts(graph_path)
        del line_meta
        _reject_deprecated_physical_io(root)
        manifest = _build_graph_manifest(graph_path, graph_frontmatter)
        body_phase_refs = _extract_body_phase_refs(graph_path, graph_body)
        phase_tokens: dict[str, PhaseTokenInfo] = {ref.name: ref.token for ref in body_phase_refs}
        graph_topology = _validate_graph_topology(
            graph_path,
            manifest.phases,
            body_phase_refs,
            root,
        )
        io_inputs = _validate_inline_io_schema(graph_path, manifest.io.inputs, "input")
        io_outputs = _validate_inline_io_schema(graph_path, manifest.io.outputs, "output")
        input_schema_keys = _extract_output_schema_keys(io_inputs)
        output_schema_keys = _extract_output_schema_keys(io_outputs)

        discovered = _discover_phase_files(root)
        phase_docs: list[PhaseDocument] = []
        for phase_name, phase_file, mode in discovered:
            frontmatter, body, _ = parse_markdown_parts(phase_file)
            _reject_phase_forbidden_metadata(phase_file, frontmatter)
            scan_forbidden_topology_tags(phase_file, body)
            phase_docs.append(
                _build_phase_document(phase_name, phase_file, mode, frontmatter, body)
            )
        _validate_agent_reference_paths(root, phase_docs)
        _validate_subgraph_io_contracts(phase_docs, skill_resolver=skill_resolver)
        actions, tools = _discover_actions_and_tools(root, discovered)
        _validate_logic_action_return_keys(
            phase_docs,
            actions,
            input_schema_keys,
            output_schema_keys,
            validate_context_writes=self.validate_context_writes,
        )
        subagents_by_phase = _compile_subagent_metadata(
            phase_docs,
            skill_resolver=skill_resolver,
        )
        tools = _inject_subagent_tools(tools, subagents_by_phase)

        raw = {
            "graph": {"frontmatter": graph_frontmatter, "body": graph_body},
            "graph_topology": graph_topology,
            "io": {
                "inputs": io_inputs,
                "outputs": io_outputs,
                "output_schema_keys": sorted(output_schema_keys)
                if output_schema_keys is not None
                else None,
            },
            "phases": [
                {
                    "phase_name": doc.phase_name,
                    "path": str(doc.path),
                    "mode": doc.mode,
                    "frontmatter": doc.frontmatter,
                    "raw_blocks": doc.raw_blocks,
                }
                for doc in phase_docs
            ],
        }
        logger.info("Compiled V0.3.0 graph skill root=%s phases=%d", root, len(phase_docs))
        return CompiledSkill(
            raw=raw,
            manifest=manifest,
            nodes=phase_docs,
            actions=actions,
            tools=tools,
            subagents_by_phase=subagents_by_phase,
            phase_tokens=phase_tokens,
        )


def load_workflow_from_md(
    md_path: str | Path,
    callbacks: list[Any] | None = None,
    model_resolver: Any | None = None,
    *,
    skill_resolver: SkillResolverProtocol,
    _loading_stack: set[str] | None = None,
) -> Any:
    """V0.3.0 temporary runtime wrapper.

    T0.1 owns document routing only.  Runtime LangGraph assembly lands in
    T1.5, so this wrapper rejects file paths and then fails explicitly after
    proving the V2.1 root can compile.
    """
    del callbacks, _loading_stack
    root = Path(md_path)
    if root.is_file():
        _fatal(root, 1, "load_workflow_from_md now accepts a V0.3.0 skill root directory")
    from graph_agent.core.compiler import compile_skill
    from graph_agent.core.graph_assembler import assemble_graph

    chat_model = None
    if model_resolver is not None:
        chat_model = model_resolver.resolve(phase_name="<workflow>")
    resolver = require_skill_resolver(skill_resolver, caller="load_workflow_from_md")
    return assemble_graph(
        compile_skill(root, skill_resolver=resolver),
        chat_model=chat_model,
        skill_resolver=resolver,
    ).graph


def _fatal(path: Path, line: int, message: str) -> NoReturn:
    raise SkillLoadError(f"[F-v3-route] {path}:{line} {message}")


def _io_fatal(path: Path, line: int, message: str) -> NoReturn:
    raise SkillLoadError(f"[F-v3-io] {path}:{line} {message}")


def _graph_fatal(path: Path, line: int, message: str) -> NoReturn:
    raise SkillLoadError(f"[F-v3-graph] {path}:{line} {message}")


def _actions_fatal(path: Path, line: int, message: str) -> NoReturn:
    raise SkillLoadError(f"[F-v3-actions] {path}:{line} {message}")


def _actions_keys_fatal(path: Path, line: int, message: str) -> None:
    raise GraphAgentFatalError(
        f"[F-v3-logic-output-field-undeclared] {path}:{line} {message}"
    )


def _purity_fatal(path: Path, line: int, message: str) -> None:
    raise SkillLoadError(f"[F-v3-purity] {path}:{line} {message}")


def _guard_v030_root(skill_root: Path) -> None:
    if not skill_root.exists():
        _fatal(skill_root / "GRAPH.md", 1, "missing required GRAPH.md")
    if not skill_root.is_dir():
        _fatal(skill_root, 1, "V0.3.0 compile_skill expects a skill root directory")

    root_skill = skill_root / "SKILL.md"
    if root_skill.exists():
        _fatal(root_skill, 1, "schema 2.0 root SKILL.md is not supported; use GRAPH.md")

    graph = skill_root / "GRAPH.md"
    if not graph.is_file():
        _fatal(graph, 1, "missing required GRAPH.md")

    phases = skill_root / "phases"
    if not phases.is_dir() or not any(p.is_dir() for p in phases.iterdir()):
        _fatal(phases, 1, "missing phases directory or phase entries")
    if (skill_root / "actions").exists():
        _actions_fatal(skill_root / "actions", 1, "root-level actions/ is not allowed")


def _discover_phase_files(skill_root: Path) -> list[tuple[str, Path, str]]:
    phases_root = skill_root / "phases"
    discovered: list[tuple[str, Path, str]] = []
    for phase_dir in sorted(p for p in phases_root.iterdir() if p.is_dir()):
        nested_graph = phase_dir / "GRAPH.md"
        if nested_graph.exists():
            _fatal(nested_graph, 1, "GRAPH.md is only allowed at skill root")

        phase_files = [
            phase_dir / name for name in _PHASE_FILE_TO_MODE if (phase_dir / name).exists()
        ]
        if len(phase_files) > 1:
            names = ", ".join(path.name for path in phase_files)
            _fatal(
                phase_files[1],
                1,
                "[F-v3-graph-phase-mode-ambiguous] "
                f"phase directory contains multiple node files: {names}",
            )
        if not phase_files:
            _fatal(
                phase_dir,
                1,
                "[F-v3-graph-phase-node-missing] "
                "phase directory must contain LOGIC.md, SUBGRAPH.md, or SKILL.md",
            )

        phase_file = phase_files[0]
        discovered.append((phase_dir.name, phase_file, _PHASE_FILE_TO_MODE[phase_file.name]))

    if not discovered:
        _fatal(phases_root, 1, "missing phases directory or phase entries")
    return discovered


def _discover_actions_and_tools(
    skill_root: Path,
    discovered: list[tuple[str, Path, str]],
) -> tuple[ActionRegistry, ToolRegistry]:
    actions_by_phase: dict[str, dict[str, ActionDef]] = {}
    tools_by_phase: dict[str, list[ToolDef]] = {}
    root_tools = (
        _load_tool_dir(skill_root / "tools", phase_id=None)
        if (skill_root / "tools").exists()
        else []
    )

    for phase_id, phase_file, mode in discovered:
        phase_dir = phase_file.parent
        actions_dir = phase_dir / "actions"
        tools_dir = phase_dir / "tools"

        if mode == "logic":
            if tools_dir.exists():
                _actions_fatal(tools_dir, 1, "tools/ is only allowed for SKILL phases")
            if actions_dir.exists():
                actions_by_phase[phase_id] = _load_action_dir(actions_dir, phase_id)
        elif mode == "agent":
            if actions_dir.exists():
                _actions_fatal(actions_dir, 1, "actions/ is only allowed for LOGIC phases")
            if tools_dir.exists():
                tools_by_phase[phase_id] = _load_tool_dir(tools_dir, phase_id=phase_id)
        else:
            if actions_dir.exists():
                _actions_fatal(actions_dir, 1, "actions/ is not allowed for SUBGRAPH phases")
            if tools_dir.exists():
                _actions_fatal(tools_dir, 1, "tools/ is not allowed for SUBGRAPH phases")

    return ActionRegistry(actions_by_phase), ToolRegistry(
        root_tools=root_tools, by_phase=tools_by_phase
    )


def _reject_deprecated_physical_io(skill_root: Path) -> None:
    for relative in ("io/inputs.json", "io/outputs.json"):
        path = skill_root / relative
        if path.exists():
            _io_fatal(
                path,
                1,
                "[F-v3-graph-io-physical-file-deprecated] "
                f"physical root IO file {relative!r} is not supported",
            )


def _validate_subgraph_io_contracts(
    phase_docs: list[PhaseDocument],
    *,
    skill_resolver: SkillResolverProtocol | None,
) -> None:
    for doc in phase_docs:
        if not isinstance(doc.ast, SubgraphNodeAST):
            continue
        resolver = require_skill_resolver(skill_resolver, caller="SkillLoader.compile_skill")
        child_root = resolve_skill_root(resolver, doc.ast.target_skill)
        child = SkillLoader(validate_context_writes=False).compile_skill(
            child_root,
            skill_resolver=resolver,
        )
        for side in ("inputs", "outputs"):
            parent_schema = getattr(doc.ast.io, side)
            child_schema = getattr(child.manifest.io, side)
            if parent_schema != child_schema:
                _fatal(
                    doc.path,
                    _frontmatter_key_line(doc.path, "io"),
                    "[F-v3-subgraph-io-mismatch] "
                    f"SUBGRAPH {doc.phase_name!r} {side} do not match "
                    f"target_skill {doc.ast.target_skill!r}",
                )


def _validate_agent_reference_paths(skill_root: Path, phase_docs: list[PhaseDocument]) -> None:
    root_resolved = skill_root.resolve()
    for doc in phase_docs:
        if not isinstance(doc.ast, AgentNodeAST):
            continue
        for reference in doc.ast.references:
            path = Path(reference.path)
            if path.is_absolute():
                raise SkillLoadError(
                    f"[F-v3-resource-reference-path-invalid] {doc.path}:"
                    f"{_frontmatter_key_line(doc.path, 'phase_config')} "
                    f"reference {reference.id!r} path escapes skill root"
                )
            candidate = (skill_root / path).resolve()
            try:
                candidate.relative_to(root_resolved)
            except ValueError as exc:
                if candidate.is_file():
                    continue
                raise SkillLoadError(
                    f"[F-v3-resource-reference-path-invalid] {doc.path}:"
                    f"{_frontmatter_key_line(doc.path, 'phase_config')} "
                    f"reference {reference.id!r} path escapes skill root"
                ) from exc
def _compile_subagent_metadata(
    phase_docs: list[PhaseDocument],
    *,
    skill_resolver: SkillResolverProtocol | None,
) -> dict[str, list[CompiledSubagent]]:
    subagents_by_phase: dict[str, list[CompiledSubagent]] = {}
    for doc in phase_docs:
        if not isinstance(doc.ast, AgentNodeAST) or not doc.ast.subagents:
            continue
        resolver = require_skill_resolver(skill_resolver, caller="SkillLoader.compile_skill")
        phase_subagents: list[CompiledSubagent] = []
        for spec in doc.ast.subagents:
            sub_root = resolve_skill_root(resolver, spec.target_skill)
            sub_compiled = SkillLoader(validate_context_writes=False).compile_skill(
                sub_root,
                skill_resolver=resolver,
            )
            input_schema = sub_compiled.raw.get("io", {}).get("inputs")
            if not isinstance(input_schema, dict) or not input_schema:
                _fatal(
                    doc.path,
                    _frontmatter_key_line(doc.path, "phase_config"),
                    "subagent "
                    f"{spec.name!r} at {spec.target_skill!r} must declare "
                    "a non-empty io.inputs schema",
                )
            try:
                input_model = build_subagent_input_model(
                    _subagent_input_model_name(doc.phase_name, spec.name),
                    input_schema,
                )
            except ValueError as exc:
                _fatal(
                    doc.path,
                    _frontmatter_key_line(doc.path, "phase_config"),
                    f"subagent {spec.name!r} io.inputs schema is unsupported: {exc}",
                )
            phase_subagents.append(
                CompiledSubagent(
                    parent_phase_id=doc.phase_name,
                    name=spec.name,
                    target_skill=spec.target_skill,
                    description=spec.description,
                    root=sub_root,
                    input_schema=input_schema,
                    input_model=input_model,
                    expected_schema=input_model.model_json_schema(),
                )
            )
        subagents_by_phase[doc.phase_name] = phase_subagents
    return subagents_by_phase


def _inject_subagent_tools(
    registry: ToolRegistry,
    subagents_by_phase: dict[str, list[CompiledSubagent]],
) -> ToolRegistry:
    by_phase = {phase_id: list(tools) for phase_id, tools in registry.by_phase.items()}
    root_tool_names = {tool.id for tool in registry.root_tools}
    for phase_id, subagents in subagents_by_phase.items():
        phase_tools = by_phase.setdefault(phase_id, [])
        existing_names = root_tool_names | {tool.id for tool in phase_tools}
        for subagent in subagents:
            tool_name = f"call_subagent_{subagent.name}"
            if tool_name in existing_names:
                _actions_fatal(
                    subagent.root,
                    1,
                    f"subagent {subagent.name!r} dynamic tool {tool_name!r} "
                    "conflicts with an existing tool",
                )
            existing_names.add(tool_name)
            phase_tools.append(_subagent_tool_def(phase_id, subagent, tool_name))
    return ToolRegistry(root_tools=registry.root_tools, by_phase=by_phase)


def _subagent_tool_def(
    phase_id: str,
    subagent: CompiledSubagent,
    tool_name: str,
) -> ToolDef:
    args_model = build_subagent_tool_args_model(
        f"{subagent.input_model.__name__}ToolArgs",
        subagent.input_model,
    )
    return ToolDef(
        id=tool_name,
        phase_id=phase_id,
        path=subagent.root / "GRAPH.md",
        func=_pending_call_subagent_tool,
        description=(
            f"{subagent.description}\n\n"
            f"Call subagent {subagent.name!r}. Pass inputs as an array; best practice: "
            "no more than 3 inputs per call."
        ),
        args_schema=args_model,
        metadata={
            "kind": "subagent",
            "subagent_name": subagent.name,
            "target_skill": subagent.target_skill,
            "subagent_path": subagent.target_skill,
            "subagent_root": str(subagent.root),
            "expected_schema": subagent.expected_schema,
        },
    )


def _pending_call_subagent_tool(inputs: list[Any]) -> list[dict[str, Any]]:
    """Placeholder for Phase 2 executor-owned subagent dispatch."""

    del inputs
    raise NotImplementedError("call_subagent runtime is implemented in Phase 2 Executor")


def _subagent_input_model_name(phase_id: str, subagent_name: str) -> str:
    safe_phase = "".join(part.title() for part in re.split(r"[^A-Za-z0-9]+", phase_id) if part)
    safe_name = "".join(part.title() for part in subagent_name.split("_") if part)
    return f"{safe_phase or 'Phase'}{safe_name or 'Subagent'}Input"


def _load_action_dir(actions_dir: Path, phase_id: str) -> dict[str, ActionDef]:
    by_id: dict[str, ActionDef] = {}
    for path in sorted(actions_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        _raise_on_purity_violations(path)
        module = _load_python_module(path)
        for func in _module_functions(module):
            _validate_action_signature(path, func)
            action_id = func.__name__
            if action_id in by_id:
                _actions_fatal(path, 1, f"duplicate action id {action_id!r} in phase {phase_id!r}")
            by_id[action_id] = ActionDef(id=action_id, phase_id=phase_id, path=path, func=func)
    return by_id


def _load_tool_dir(tools_dir: Path, *, phase_id: str | None) -> list[ToolDef]:
    tools: list[ToolDef] = []
    for path in sorted(tools_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        _raise_on_purity_violations(path)
        for violation in scan_tool_imports_context(path):
            _actions_fatal(path, violation.line, violation.reason)
        module = _load_python_module(path)
        for func in _module_functions(module):
            _validate_tool_signature(path, func)
            tools.append(ToolDef(id=func.__name__, phase_id=phase_id, path=path, func=func))
    return tools


def _raise_on_purity_violations(path: Path) -> None:
    for violation in scan_python_purity(path):
        if violation.api == "python":
            _actions_fatal(path, violation.line, f"module load failed: {violation.reason}")
        _purity_fatal(path, violation.line, f"{violation.api} {violation.reason}")


def _load_python_module(path: Path) -> ModuleType:
    module_name = f"_graph_agent_v21_{abs(hash(path.resolve()))}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            _actions_fatal(path, 1, "could not create import spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        tb = traceback.format_exc()
        line = getattr(exc, "lineno", 1) or 1
        _actions_fatal(path, line, f"module load failed: {exc}\n{tb}")
    return module


def _module_functions(module: ModuleType) -> list[Callable[..., object]]:
    return [
        func
        for _, func in inspect.getmembers(module, inspect.isfunction)
        if getattr(func, "__module__", None) == module.__name__
    ]


def _validate_action_signature(path: Path, func: Callable[..., object]) -> None:
    signature = inspect.signature(func)
    params = list(signature.parameters.values())
    if not params or params[0].name not in {"context", "ctx"}:
        _actions_fatal(
            path, 1, f"action {func.__name__!r} must accept context/ctx as first parameter"
        )
    annotation = params[0].annotation
    if annotation is inspect.Parameter.empty:
        return
    if annotation is Context:
        return
    if isinstance(annotation, str) and annotation in {
        "Context",
        "graph_agent.cognitive.context_facade.Context",
    }:
        return
    _actions_fatal(path, 1, f"action {func.__name__!r} first parameter must be Context-compatible")


def _validate_tool_signature(path: Path, func: Callable[..., object]) -> None:
    signature = inspect.signature(func)
    for param in signature.parameters.values():
        if param.name in {"context", "ctx", "state", "blackboard"}:
            _actions_fatal(
                path,
                1,
                f"tool {func.__name__!r} must not accept blackboard parameter {param.name!r}",
            )


def _route_document(file_path: Path) -> RouteKind:
    if file_path.name == "GRAPH.md":
        if file_path.parent.name == "phases" or file_path.parent.parent.name == "phases":
            _fatal(file_path, 1, "GRAPH.md is only allowed at skill root")
        return "graph"
    if file_path.name in _PHASE_FILE_TO_MODE:
        return _PHASE_FILE_TO_MODE[file_path.name]  # type: ignore[return-value]
    _fatal(file_path, 1, "unsupported V0.3.0 document filename")


def _reject_phase_forbidden_metadata(path: Path, frontmatter: dict[str, Any]) -> None:
    for key in ("mode", "schema_version", "graph_skill_id", "phase_id"):
        if key not in frontmatter:
            continue
        domain = _PHASE_FILE_TO_MODE.get(path.name, "graph")
        code = f"[F-v3-{domain}-schema-unknown-field]"
        _fatal(
            path,
            _frontmatter_key_line(path, key),
            f"{code} phase frontmatter field {key!r} is not allowed",
        )


def _build_graph_manifest(
    path: Path,
    frontmatter: dict[str, Any],
) -> GraphManifest:
    data = dict(frontmatter)
    if data.get("schema_version") != "v0.3.0":
        _graph_fatal(
            path,
            1,
            '[F-v3-graph-schema-version-mismatch] GRAPH.md schema_version must be exactly "v0.3.0"',
        )
    if "io_inputs_ref" in data or "io_outputs_ref" in data:
        _graph_fatal(
            path,
            1,
            "[F-v3-graph-io-physical-file-deprecated] "
            "io_inputs_ref/io_outputs_ref are not supported",
        )
    if "phases" not in data:
        _graph_fatal(
            path,
            1,
            "[F-v3-graph-phases-missing] GRAPH.md must declare YAML frontmatter phases",
        )
    if not isinstance(data.get("phases"), list):
        _graph_fatal(
            path,
            _frontmatter_key_line(path, "phases"),
            "[F-v3-graph-phases-missing] GRAPH.md phases must be a list[str]",
        )

    try:
        return GraphManifest.model_validate(data)
    except ValidationError as exc:
        _fatal(path, 1, f"GRAPH.md manifest validation failed: {exc}")


def get_phase_token_info(compiled: CompiledSkill, phase_id: str) -> PhaseTokenInfo | None:
    """Return source token metadata for a phase in a compiled skill.

    The metadata lives on ``CompiledSkill`` so ``GraphManifest`` and
    ``GraphPhaseRef`` remain pure Pydantic business contracts without a global
    id-based registry.
    """

    return compiled.phase_tokens.get(phase_id)


def _phase_attr_spans(
    attrs_raw: str,
    attr_raw_start: int,
    graph_text: str,
) -> dict[str, PhaseAttributeSpan]:
    spans: dict[str, PhaseAttributeSpan] = {}
    for match in _ATTR_RE.finditer(attrs_raw):
        name = match.group(1)
        value = match.group(3)
        attr_start = attr_raw_start + match.start()
        attr_end = attr_raw_start + match.end()
        value_start = attr_raw_start + match.start(3)
        value_end = attr_raw_start + match.end(3)
        spans[name] = PhaseAttributeSpan(
            name=name,
            value=value,
            quote=match.group(2),
            attr_start=attr_start,
            attr_end=attr_end,
            value_start=value_start,
            value_end=value_end,
            line_start=graph_text[:attr_start].count("\n") + 1,
            line_end=graph_text[:attr_end].count("\n") + 1,
        )
    return spans


_PHASE_TAG_RE = re.compile(r"<phase\b([^>]*)>(.*?)</phase>", re.IGNORECASE | re.DOTALL)


def _extract_body_phase_refs(graph_path: Path, graph_body: str) -> list[BodyPhaseRef]:
    refs: list[BodyPhaseRef] = []
    for match in _PHASE_TAG_RE.finditer(graph_body):
        attrs_raw = match.group(1)
        attrs = _parse_attrs(attrs_raw)
        name = match.group(2).strip()
        if not name:
            _graph_fatal(
                graph_path,
                _xml_line(graph_body, match.start()),
                "[F-v3-graph-phase-id-invalid] body <phase> name is empty",
            )
        depends_raw = attrs.get("depends_on")
        if depends_raw is None or not depends_raw.strip():
            _graph_fatal(
                graph_path,
                _xml_line(graph_body, match.start()),
                "[F-v3-graph-depends-unknown] body <phase> depends_on is required",
            )
        depends_on = tuple(dep for dep in re.split(r"[\s,]+", depends_raw.strip()) if dep)
        attr_raw_start = match.start(1)
        token = PhaseTokenInfo(
            phase_id=name,
            raw_text=match.group(0),
            start_offset=match.start(),
            end_offset=match.end(),
            line_start=_xml_line(graph_body, match.start()),
            line_end=_xml_line(graph_body, match.end()),
            attrs=attrs,
            attr_spans=_phase_attr_spans(attrs_raw, attr_raw_start, graph_body),
        )
        refs.append(
            BodyPhaseRef(
                name=name,
                depends_on=depends_on,
                output="output" in attrs_raw.split(),
                token=token,
            )
        )
    return refs


def _validate_graph_topology(
    graph_path: Path,
    phases: list[str],
    body_phase_refs: list[BodyPhaseRef],
    skill_root: Path,
) -> dict[str, Any]:
    if not phases:
        _graph_fatal(
            graph_path,
            1,
            "[F-v3-graph-phases-missing] GRAPH.md must declare at least one phase",
        )
    if not body_phase_refs:
        _graph_fatal(
            graph_path,
            1,
            "[F-v3-graph-phase-id-invalid] GRAPH.md body must declare <phase> tags",
        )
    if len(set(phases)) != len(phases):
        _graph_fatal(
            graph_path,
            _frontmatter_key_line(graph_path, "phases"),
            "[F-v3-graph-phase-id-duplicate] duplicate phase name in frontmatter phases",
        )

    body_names = [ref.name for ref in body_phase_refs]
    if len(set(body_names)) != len(body_names):
        _graph_fatal(
            graph_path,
            1,
            "[F-v3-graph-phase-id-duplicate] duplicate phase name in body <phase> tags",
        )

    phase_set = set(phases)
    body_set = set(body_names)
    physical_set = {path.name for path in (skill_root / "phases").iterdir() if path.is_dir()}

    if phase_set != physical_set or body_set != physical_set:
        _graph_fatal(
            graph_path,
            1,
            "[F-v3-graph-phase-name-mismatch] "
            "frontmatter phases, body <phase> names, and physical phase dirs must match",
        )

    adjacency: dict[str, list[str]] = {name: [] for name in phases}
    input_roots: list[str] = []
    unknown_deps: list[tuple[BodyPhaseRef, str]] = []
    for ref in body_phase_refs:
        for dep in ref.depends_on:
            if dep == "input":
                input_roots.append(ref.name)
                continue
            if dep not in phase_set:
                unknown_deps.append((ref, dep))
                continue
            if dep == ref.name:
                _graph_fatal(
                    graph_path,
                    ref.token.line_start,
                    f"[F-v3-graph-phase-cycle] phase {ref.name!r} cannot depend on itself",
                )
            adjacency[dep].append(ref.name)

    _validate_acyclic_graph(graph_path, adjacency)

    if not input_roots:
        _graph_fatal(
            graph_path,
            1,
            "[F-v3-graph-depends-unknown] at least one phase must depend_on input",
        )
    _validate_no_islands(graph_path, adjacency, input_roots)
    if unknown_deps:
        ref, dep = unknown_deps[0]
        _graph_fatal(
            graph_path,
            ref.token.line_start,
            f"[F-v3-graph-depends-unknown] phase {ref.name!r} depends_on unknown phase {dep!r}",
        )
    _validate_output_phases(graph_path, body_phase_refs, adjacency)
    for phase in phases:
        _validate_phase_dir(graph_path, phase, skill_root)
    return {
        "phases": [
            {
                "name": ref.name,
                "depends_on": list(ref.depends_on),
                "output": ref.output,
            }
            for ref in body_phase_refs
        ],
        "order": _topological_order(adjacency, phases),
    }


def _validate_acyclic_graph(graph_path: Path, adjacency: dict[str, list[str]]) -> None:

    state: dict[str, str] = {}
    stack: list[str] = []

    def visit(node: str) -> None:
        state[node] = "gray"
        stack.append(node)
        for nxt in adjacency[node]:
            if state.get(nxt) == "gray":
                start = stack.index(nxt)
                cycle = stack[start:] + [nxt]
                _graph_fatal(
                    graph_path,
                    1,
                    "[F-v3-graph-phase-cycle] cycle detected: " + " -> ".join(cycle),
                )
            if state.get(nxt) is None:
                visit(nxt)
        stack.pop()
        state[node] = "black"

    for node in adjacency:
        if state.get(node) is None:
            visit(node)


def _validate_no_islands(
    graph_path: Path,
    adjacency: dict[str, list[str]],
    input_roots: list[str],
) -> None:
    visited: set[str] = set()
    stack = list(input_roots)
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(sorted(set(adjacency[node]) - visited))

    for phase_id in adjacency:
        if phase_id not in visited:
            _graph_fatal(
                graph_path,
                1,
                f"[F-v3-graph-phase-island] phase {phase_id!r} is unreachable from input",
            )


def _validate_output_phases(
    graph_path: Path,
    body_phase_refs: list[BodyPhaseRef],
    adjacency: dict[str, list[str]],
) -> None:
    outputs = {ref.name for ref in body_phase_refs if ref.output}
    if not outputs:
        _graph_fatal(
            graph_path,
            1,
            "[F-v3-graph-output-phase-invalid] at least one body <phase> must be output",
        )
    non_terminal = {phase for phase, downstream in adjacency.items() if downstream}
    invalid = sorted(outputs & non_terminal)
    if invalid:
        _graph_fatal(
            graph_path,
            1,
            "[F-v3-graph-output-phase-invalid] output phase has downstream edges: "
            + ", ".join(invalid),
        )


def _validate_phase_dir(graph_path: Path, phase: str, skill_root: Path) -> None:
    candidate = skill_root / "phases" / phase
    if not candidate.is_dir() or not any(
        (candidate / name).is_file() for name in _PHASE_FILE_TO_MODE
    ):
        _graph_fatal(
            graph_path,
            1,
            f"[F-v3-graph-phase-node-missing] phase {phase!r} has no LOGIC.md/SUBGRAPH.md/SKILL.md",
        )


def _topological_order(adjacency: dict[str, list[str]], phases: list[str]) -> list[str]:
    indegree = {phase: 0 for phase in phases}
    for downstream in adjacency.values():
        for phase in downstream:
            indegree[phase] += 1
    queue = [phase for phase in phases if indegree[phase] == 0]
    order: list[str] = []
    while queue:
        phase = queue.pop(0)
        order.append(phase)
        for nxt in adjacency[phase]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return order


def _validate_inline_io_schema(path: Path, schema: dict[str, Any], kind: str) -> dict[str, Any]:
    if not isinstance(schema, dict):
        _io_fatal(path, 1, f"inline {kind} schema must be an object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        _io_fatal(path, 1, f"invalid inline {kind} JSON Schema: {exc.message}")
    return schema


def _extract_output_schema_keys(schema: dict[str, Any]) -> set[str] | None:
    properties = schema.get("properties")
    if properties is None:
        return None
    if not isinstance(properties, dict):
        return set()
    return {key for key in properties if isinstance(key, str)}


class _ActionReturnKeyVisitor(ast.NodeVisitor):
    def __init__(
        self,
        path: Path,
        allowed_return_keys: set[str],
        allowed_context_keys: set[str] | None,
    ) -> None:
        self.path = path
        self.allowed_return_keys = allowed_return_keys
        self.allowed_context_keys = allowed_context_keys

    def visit_Return(self, node: ast.Return) -> None:  # noqa: N802
        value = node.value
        if isinstance(value, ast.Dict):
            for key_node in value.keys:
                if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                    continue
                if key_node.value not in self.allowed_return_keys:
                    line = getattr(key_node, "lineno", node.lineno)
                    _actions_keys_fatal(
                        self.path,
                        line,
                        f"action returns undeclared output key {key_node.value!r}",
                    )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if not _is_context_method_call(node, "update"):
            self.generic_visit(node)
            return
        if self.allowed_context_keys is None:
            self.generic_visit(node)
            return
        for keyword in node.keywords:
            if keyword.arg is None:
                continue
            if keyword.arg not in self.allowed_context_keys:
                _actions_keys_fatal(
                    self.path,
                    getattr(keyword, "lineno", node.lineno),
                    f"action writes undeclared output key {keyword.arg!r}",
                )
        self.generic_visit(node)


def _is_context_method_call(node: ast.Call, method: str) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != method:
        return False
    return isinstance(func.value, ast.Name) and func.value.id in {"context", "ctx"}


def _validate_logic_action_return_keys(
    phase_docs: list[PhaseDocument],
    actions: ActionRegistry,
    input_schema_keys: set[str] | None,
    output_schema_keys: set[str] | None,
    *,
    validate_context_writes: bool,
) -> None:
    if not validate_context_writes:
        return
    for doc in phase_docs:
        if not isinstance(doc.ast, LogicNodeAST):
            continue
        phase_output_schema_keys = _extract_output_schema_keys(doc.ast.io.outputs)
        if phase_output_schema_keys is None:
            continue
        context_keys = set(phase_output_schema_keys)
        if input_schema_keys is not None:
            context_keys.update(input_schema_keys)
        for action_name in doc.ast.actions:
            action_def = actions.for_phase(doc.phase_name).get(action_name)
            if action_def is None:
                continue
            _validate_action_return_keys(
                action_def.path,
                phase_output_schema_keys,
                context_keys,
                validate_context_writes=validate_context_writes
                and _should_validate_context_writes(phase_docs),
            )


def _should_validate_context_writes(phase_docs: list[PhaseDocument]) -> bool:
    logic_count = sum(1 for doc in phase_docs if isinstance(doc.ast, LogicNodeAST))
    return logic_count == 1


def _validate_action_return_keys(
    path: Path,
    output_schema_keys: set[str],
    context_schema_keys: set[str],
    *,
    validate_context_writes: bool,
) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        _actions_keys_fatal(path, exc.lineno or 1, f"could not parse action source: {exc.msg}")
    except OSError as exc:
        _actions_keys_fatal(path, 1, f"could not read action source: {exc}")
    _ActionReturnKeyVisitor(
        path,
        output_schema_keys,
        context_schema_keys if validate_context_writes else None,
    ).visit(tree)


def _build_phase_document(
    phase_name: str,
    path: Path,
    mode: str,
    frontmatter: dict[str, Any],
    body: str,
) -> PhaseDocument:
    allowed = [
        "role",
        "goal",
        "step",
        "protocol",
        "example",
        "action",
    ]
    blocks = extract_raw_blocks(body, allowed)
    data = dict(frontmatter)
    data["raw_blocks"] = blocks
    data.setdefault("name", phase_name)
    data["mode"] = mode
    is_agent = path.name == "SKILL.md"
    if is_agent:
        data = _normalize_skill_node_frontmatter(path, data)

    try:
        if mode == "logic":
            data.setdefault("actions", _extract_logic_actions(path, body))
            logic_ast = LogicNodeAST.model_validate(data)
            _validate_logic_actions_declared(path, logic_ast, body)
            ast: PhaseAST = logic_ast
        elif mode == "subgraph":
            ast = SubgraphNodeAST.model_validate(data)
        elif is_agent:
            data.update(_parse_agent_body(path, body, blocks))
            ast = AgentNodeAST.model_validate(data)
            _validate_agent_mentions(path, ast, body)
        else:
            _fatal(
                path,
                1,
                f"unsupported phase file {path.name}",
            )
    except ValidationError as exc:
        _phase_validation_fatal(path, mode, exc)

    return PhaseDocument(
        phase_name=phase_name,
        path=path,
        mode=mode,
        frontmatter=frontmatter,
        raw_blocks=blocks,
        ast=ast,
    )


def _normalize_skill_node_frontmatter(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    phase_config = data.pop("phase_config", None)
    if phase_config is None:
        return data
    if not isinstance(phase_config, dict):
        _fatal(path, _frontmatter_key_line(path, "phase_config"), "phase_config must be an object")
    merged = dict(data)
    if "tools" in phase_config:
        merged.setdefault("tools", phase_config["tools"])
    phase_config_keys = (
        "tools",
        "subagents",
        "subgraphs",
        "references",
        "examples",
        "io",
        "max_iterations",
        "llm_role",
        "validator",
    )
    for key in phase_config_keys[1:]:
        if key in phase_config:
            merged[key] = phase_config[key]
    extra_keys = sorted(set(phase_config) - set(phase_config_keys))
    if extra_keys:
        _fatal(
            path,
            _frontmatter_key_line(path, "phase_config"),
            "unsupported phase_config keys: " + ", ".join(extra_keys),
        )
    return merged


def _phase_validation_fatal(path: Path, mode: str, exc: ValidationError) -> NoReturn:
    text = str(exc)
    if mode == "logic" and "validator" in text:
        _fatal(
            path,
            _frontmatter_key_line(path, "validator"),
            "[F-v3-logic-validator-type-invalid] validator must be boolean",
        )
    domain = {"agent": "agent", "logic": "logic", "subgraph": "subgraph"}.get(mode, "graph")
    _fatal(
        path, 1, f"[F-v3-{domain}-schema-unknown-field] {path.name} AST validation failed: {exc}"
    )


def _extract_logic_actions(path: Path, body: str) -> list[str]:
    actions: list[str] = []
    pattern = re.compile(r"<action\b[^>]*>(.*?)</action>", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(body):
        action = match.group(1).strip()
        if action:
            actions.append(action)
    if not actions:
        _fatal(path, 1, "[F-v3-logic-actions-empty] LOGIC.md requires <action> tags")
    return actions


def _validate_logic_actions_declared(path: Path, ast: LogicNodeAST, body: str) -> None:
    body_actions = _extract_logic_actions(path, body)
    if ast.actions != body_actions:
        _fatal(
            path,
            _frontmatter_key_line(path, "actions"),
            "[F-v3-logic-actions-empty] LOGIC.md frontmatter actions must match "
            "body <action> order",
        )


def _parse_agent_body(
    path: Path,
    body: str,
    blocks: dict[str, str],
) -> dict[str, Any]:
    allowed_tags = {"role", "goal", "step", "protocol", "example"}
    for match in re.finditer(r"</?([A-Za-z_][\w:-]*)\b", body):
        tag = match.group(1).lower()
        if tag not in allowed_tags:
            _fatal(
                path,
                _xml_line(body, match.start()),
                f"[F-v3-agent-body-tag-unknown] unknown top-level tag {tag}",
            )
    if "<steps" in body.lower() or "</steps" in body.lower():
        _fatal(
            path,
            _xml_line(body, body.lower().find("<steps")),
            "[F-v3-agent-body-tag-unknown] unknown top-level tag steps",
        )
    role = blocks.get("role")
    goal = blocks.get("goal")
    if "<exit_contract" in body.lower() or "</exit_contract" in body.lower():
        _fatal(
            path,
            _xml_line(body, body.lower().find("<exit_contract")),
            "[F-v3-agent-body-tag-unknown] unknown top-level tag exit_contract",
        )
    if not role:
        _fatal(path, 1, "[F-v3-agent-role-missing] Agent body requires <role>")
    if not goal:
        _fatal(path, 1, "[F-v3-agent-goal-missing] Agent body requires <goal>")
    return {
        "role": role,
        "goal": goal,
        "steps": _extract_agent_steps(path, body),
        "protocols": _extract_agent_protocols(path, body),
        "examples_inline": _extract_agent_examples(path, body),
    }


def _extract_agent_steps(path: Path, body: str) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    pattern = re.compile(r"<step\b([^>]*)>(.*?)</step>", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(body):
        attrs = _parse_attrs(match.group(1))
        step_id = attrs.get("id")
        name = attrs.get("name")
        if not step_id or not name:
            _fatal(
                path,
                _xml_line(body, match.start()),
                "[F-v3-agent-step-invalid] step requires id and name",
            )
        steps.append({"id": step_id, "name": name, "content": match.group(2).strip()})
    return steps


def _extract_agent_protocols(path: Path, body: str) -> list[dict[str, str]]:
    protocols: list[dict[str, str]] = []
    pattern = re.compile(r"<protocol\b([^>]*)>(.*?)</protocol>", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(body):
        attrs = _parse_attrs(match.group(1))
        protocol_id = attrs.get("id")
        if not protocol_id:
            _fatal(
                path,
                _xml_line(body, match.start()),
                "[F-v3-agent-protocol-invalid] protocol requires id",
            )
        protocols.append({"id": protocol_id, "content": match.group(2).strip()})
    return protocols


def _extract_agent_examples(path: Path, body: str) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(r"<example\b([^>]*)>(.*?)</example>", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(body):
        attrs = _parse_attrs(match.group(1))
        example_id = attrs.get("id")
        content = match.group(2).strip()
        if not example_id or not content or example_id in seen:
            _fatal(
                path,
                _xml_line(body, match.start()),
                "[F-v3-agent-example-invalid] example requires unique id and non-empty content",
            )
        seen.add(example_id)
        examples.append({"id": example_id, "content": content})
    return examples


def _validate_agent_mentions(path: Path, ast: AgentNodeAST, body: str) -> None:
    broken = first_broken_mention(body)
    if broken is not None:
        _fatal(
            path,
            _xml_line(body, broken.start()),
            "[F-v3-mention-syntax-invalid] malformed @-mention",
        )
    domains = {
        "subagent": {item.name for item in ast.subagents},
        "subgraph": {item.name for item in ast.subgraphs},
        "reference": {item.id for item in ast.references},
        "example": {item.id for item in ast.examples} | {item.id for item in ast.examples_inline},
        "step": {item.id for item in ast.steps},
        "protocol": {item.id for item in ast.protocols},
        "tool": set(ast.tools) | {"finish_task", "read_reference", "read_example", "log_ambiguity"},
    }
    for mention in scan_mentions(body):
        if mention.name not in domains.get(mention.kind, set()):
            _fatal(
                path,
                _xml_line(body, mention.start),
                f"[F-v3-mention-target-not-found] @{mention.kind}:{mention.name}",
            )


def _xml_line(body: str, offset: int) -> int:
    return body[: max(0, offset)].count("\n") + 1


_ATTR_RE = re.compile(r"([A-Za-z_][\w:-]*)\s*=\s*(['\"])(.*?)\2", re.DOTALL)


def _parse_attrs(raw: str) -> dict[str, str]:
    return {match.group(1): match.group(3) for match in _ATTR_RE.finditer(raw)}


def _frontmatter_key_line(path: Path, key: str) -> int:
    try:
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.match(rf"\s*{re.escape(key)}\s*:", line):
                return index
    except OSError:
        return 1
    return 1


__all__ = [
    "CompiledSkill",
    "PhaseAttributeSpan",
    "PhaseDocument",
    "PhaseTokenInfo",
    "SkillLoader",
    "_discover_phase_files",
    "_guard_v030_root",
    "get_phase_token_info",
    "_route_document",
    "_validate_graph_topology",
    "load_workflow_from_md",
]
