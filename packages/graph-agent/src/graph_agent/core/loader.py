"""V2.1 graph skill loader: route GRAPH.md + phase node documents."""

from __future__ import annotations

import ast
import logging
import json
import importlib.util
import inspect
import re
import traceback
from dataclasses import dataclass, field
from json import JSONDecodeError
from types import ModuleType
from pathlib import Path
from typing import Any, Callable, Literal

from jsonschema.exceptions import SchemaError
from jsonschema.validators import Draft202012Validator
from pydantic import ValidationError

from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError
from graph_agent.core.actions import ActionDef, ActionRegistry, ToolDef, ToolRegistry
from graph_agent.core.manifest import (
    GraphManifest,
    GraphPhaseRef,
    LogicNodeAST,
    SkillNodeAST,
    SubgraphNodeAST,
)
from graph_agent.core.parser import (
    extract_raw_blocks,
    parse_markdown_parts,
    scan_forbidden_topology_tags,
)
from graph_agent.core.purity import scan_python_purity, scan_tool_imports_context
from graph_agent.cognitive.context_facade import Context

logger = logging.getLogger(__name__)

RouteKind = Literal["graph", "logic", "subgraph", "skill"]
PhaseAST = LogicNodeAST | SubgraphNodeAST | SkillNodeAST

_PHASE_FILE_TO_MODE: dict[str, str] = {
    "LOGIC.md": "logic",
    "SUBGRAPH.md": "subgraph",
    "SKILL.md": "skill",
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


@dataclass(frozen=True)
class _RawPhaseAttrs:
    id: str | None
    src: str | None
    depends_on_raw: str | None
    depends_on: list[str]
    line: int


class SkillLoader:
    """Thin V2.1 parser/route orchestrator."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def compile_skill(self, skill_root: str | Path) -> CompiledSkill:
        root = Path(skill_root)
        _guard_v21_root(root)

        graph_path = root / "GRAPH.md"
        graph_frontmatter, graph_body, line_meta = parse_markdown_parts(graph_path)
        raw_attrs = _extract_phase_attrs(graph_body, line_meta["body_start"])
        manifest = _build_graph_manifest(graph_path, graph_frontmatter, graph_body, raw_attrs)
        _validate_graph_topology(graph_path, raw_attrs, root)
        io_inputs = _validate_io_schema(root, manifest.io_inputs_ref, "input")
        io_outputs = _validate_io_schema(root, manifest.io_outputs_ref, "output")
        output_schema_keys = _extract_output_schema_keys(io_outputs)

        discovered = _discover_phase_files(root)
        phase_docs: list[PhaseDocument] = []
        for phase_name, phase_file, mode in discovered:
            frontmatter, body, _ = parse_markdown_parts(phase_file)
            yaml_mode = str(frontmatter.get("mode") or "").strip()
            _validate_mode_matches_filename(phase_file, yaml_mode)
            scan_forbidden_topology_tags(phase_file, body)
            phase_docs.append(_build_phase_document(phase_name, phase_file, mode, frontmatter, body))
        actions, tools = _discover_actions_and_tools(root, discovered)
        _validate_logic_action_return_keys(phase_docs, actions, output_schema_keys)

        raw = {
            "graph": {"frontmatter": graph_frontmatter, "body": graph_body},
            "io": {
                "inputs": io_inputs,
                "outputs": io_outputs,
                "output_schema_keys": sorted(output_schema_keys) if output_schema_keys is not None else None,
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
        logger.info("Compiled V2.1 graph skill root=%s phases=%d", root, len(phase_docs))
        return CompiledSkill(raw=raw, manifest=manifest, nodes=phase_docs, actions=actions, tools=tools)


def load_workflow_from_md(
    md_path: str | Path,
    callbacks: list[Any] | None = None,
    _loading_stack: set[str] | None = None,
) -> Any:
    """V2.1 temporary runtime wrapper.

    T0.1 owns document routing only.  Runtime LangGraph assembly lands in
    T1.5, so this wrapper rejects file paths and then fails explicitly after
    proving the V2.1 root can compile.
    """
    del callbacks, _loading_stack
    root = Path(md_path)
    if root.is_file():
        _fatal(root, 1, "load_workflow_from_md now accepts a V2.1 skill root directory")
    from graph_agent.core.compiler import compile_skill
    from graph_agent.core.graph_assembler import assemble_graph

    return assemble_graph(compile_skill(root)).graph


def _fatal(path: Path, line: int, message: str) -> None:
    raise SkillLoadError(f"[F-v21-route] {path}:{line} {message}")


def _io_fatal(path: Path, line: int, message: str) -> None:
    raise SkillLoadError(f"[F-v21-io] {path}:{line} {message}")


def _graph_fatal(path: Path, line: int, message: str) -> None:
    raise SkillLoadError(f"[F-v21-graph] {path}:{line} {message}")


def _actions_fatal(path: Path, line: int, message: str) -> None:
    raise SkillLoadError(f"[F-v21-actions] {path}:{line} {message}")


def _actions_keys_fatal(path: Path, line: int, message: str) -> None:
    raise GraphAgentFatalError(f"[F-v21-actions-keys] {path}:{line} {message}")


def _purity_fatal(path: Path, line: int, message: str) -> None:
    raise SkillLoadError(f"[F-v21-purity] {path}:{line} {message}")


def _guard_v21_root(skill_root: Path) -> None:
    if not skill_root.exists():
        _fatal(skill_root / "GRAPH.md", 1, "missing required GRAPH.md")
    if not skill_root.is_dir():
        _fatal(skill_root, 1, "V2.1 compile_skill expects a skill root directory")

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

        phase_files = [phase_dir / name for name in _PHASE_FILE_TO_MODE if (phase_dir / name).exists()]
        if len(phase_files) > 1:
            names = ", ".join(path.name for path in phase_files)
            _fatal(phase_files[1], 1, f"phase directory contains multiple node files: {names}")
        if not phase_files:
            _fatal(phase_dir, 1, "phase directory must contain LOGIC.md, SUBGRAPH.md, or SKILL.md")

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
    root_tools = _load_tool_dir(skill_root / "tools", phase_id=None) if (skill_root / "tools").exists() else []

    for phase_id, phase_file, mode in discovered:
        phase_dir = phase_file.parent
        actions_dir = phase_dir / "actions"
        tools_dir = phase_dir / "tools"

        if mode == "logic":
            if tools_dir.exists():
                _actions_fatal(tools_dir, 1, "tools/ is only allowed for SKILL phases")
            if actions_dir.exists():
                actions_by_phase[phase_id] = _load_action_dir(actions_dir, phase_id)
        elif mode == "skill":
            if actions_dir.exists():
                _actions_fatal(actions_dir, 1, "actions/ is only allowed for LOGIC phases")
            if tools_dir.exists():
                tools_by_phase[phase_id] = _load_tool_dir(tools_dir, phase_id=phase_id)
        else:
            if actions_dir.exists():
                _actions_fatal(actions_dir, 1, "actions/ is not allowed for SUBGRAPH phases")
            if tools_dir.exists():
                _actions_fatal(tools_dir, 1, "tools/ is not allowed for SUBGRAPH phases")

    return ActionRegistry(actions_by_phase), ToolRegistry(root_tools=root_tools, by_phase=tools_by_phase)


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
        _actions_fatal(path, 1, f"action {func.__name__!r} must accept context/ctx as first parameter")
    annotation = params[0].annotation
    if annotation is inspect.Parameter.empty:
        return
    if annotation is Context:
        return
    if isinstance(annotation, str) and annotation in {"Context", "graph_agent.cognitive.context_facade.Context"}:
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
    _fatal(file_path, 1, "unsupported V2.1 document filename")


def _validate_mode_matches_filename(path: Path, yaml_mode: str) -> None:
    expected = _PHASE_FILE_TO_MODE.get(path.name)
    if expected is None:
        _route_document(path)
        return
    if yaml_mode != expected:
        line = _frontmatter_key_line(path, "mode")
        _fatal(path, line, f"mode {yaml_mode!r} does not match {path.name} filename")


def _build_graph_manifest(
    path: Path,
    frontmatter: dict[str, Any],
    body: str,
    raw_attrs: list[_RawPhaseAttrs],
) -> GraphManifest:
    data = dict(frontmatter)
    data.setdefault("schema_version", "2.1")

    input_ref = _first_src(body, "input")
    output_ref = _first_src(body, "output")
    if input_ref:
        data["io_inputs_ref"] = input_ref
    if output_ref:
        data["io_outputs_ref"] = output_ref

    phases: list[GraphPhaseRef] = []
    for attrs in raw_attrs:
        if attrs.id is None or attrs.src is None:
            continue
        phases.append(
            GraphPhaseRef(
                id=attrs.id,
                src=attrs.src,
                depends_on=attrs.depends_on,
            )
        )
    data["phases"] = phases

    try:
        return GraphManifest.model_validate(data)
    except ValidationError as exc:
        _fatal(path, 1, f"GRAPH.md manifest validation failed: {exc}")


def _extract_phase_attrs(body: str, body_start_line: int) -> list[_RawPhaseAttrs]:
    pattern = re.compile(r"<phase\b([^>]*)/>", re.IGNORECASE | re.DOTALL)
    raw_attrs: list[_RawPhaseAttrs] = []
    for match in pattern.finditer(body):
        attrs = _parse_attrs(match.group(1))
        line = body_start_line + body[: match.start()].count("\n")
        depends_on_raw = attrs.get("depends_on")
        raw_attrs.append(
            _RawPhaseAttrs(
                id=attrs.get("id"),
                src=attrs.get("src"),
                depends_on_raw=depends_on_raw,
                depends_on=_split_depends_on(depends_on_raw or ""),
                line=line,
            )
        )
    return raw_attrs


def _validate_graph_topology(
    graph_path: Path,
    raw_attrs: list[_RawPhaseAttrs],
    skill_root: Path,
) -> None:
    for attrs in raw_attrs:
        if attrs.id is None:
            _graph_fatal(graph_path, attrs.line, "phase tag missing required id")
        if attrs.src is None:
            _graph_fatal(graph_path, attrs.line, f"phase {attrs.id!r} missing required src")

    phase_by_id: dict[str, _RawPhaseAttrs] = {}
    for index, attrs in enumerate(raw_attrs):
        assert attrs.id is not None
        if attrs.id in phase_by_id:
            _graph_fatal(graph_path, attrs.line, f"duplicate phase id {attrs.id!r}")
        phase_by_id[attrs.id] = attrs
        if attrs.depends_on_raw is None:
            _graph_fatal(
                graph_path,
                attrs.line,
                f"phase {attrs.id!r} missing required depends_on; "
                'use depends_on="" for entry phases',
            )

    for attrs in raw_attrs:
        assert attrs.id is not None
        for dep in attrs.depends_on:
            if dep not in phase_by_id:
                _graph_fatal(
                    graph_path,
                    attrs.line,
                    f"phase {attrs.id!r} depends_on unknown phase {dep!r}",
                )
            if dep == attrs.id:
                _graph_fatal(graph_path, attrs.line, f"phase {attrs.id!r} cannot depend on itself")

    _validate_acyclic_graph(graph_path, raw_attrs)
    _validate_no_orphans(graph_path, raw_attrs)
    for attrs in raw_attrs:
        assert attrs.id is not None and attrs.src is not None
        _validate_phase_src(graph_path, attrs, skill_root)


def _validate_acyclic_graph(graph_path: Path, raw_attrs: list[_RawPhaseAttrs]) -> None:
    adjacency: dict[str, list[str]] = {attrs.id or "": [] for attrs in raw_attrs}
    line_by_id: dict[str, int] = {attrs.id or "": attrs.line for attrs in raw_attrs}
    for attrs in raw_attrs:
        assert attrs.id is not None
        for dep in attrs.depends_on:
            adjacency[dep].append(attrs.id)

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
                    line_by_id.get(nxt, 1),
                    "cycle detected: " + " -> ".join(cycle),
                )
            if state.get(nxt) is None:
                visit(nxt)
        stack.pop()
        state[node] = "black"

    for node in adjacency:
        if state.get(node) is None:
            visit(node)


def _validate_no_orphans(graph_path: Path, raw_attrs: list[_RawPhaseAttrs]) -> None:
    if len(raw_attrs) <= 1:
        return
    adjacency: dict[str, set[str]] = {attrs.id or "": set() for attrs in raw_attrs}
    by_id = {attrs.id or "": attrs for attrs in raw_attrs}
    for attrs in raw_attrs:
        assert attrs.id is not None
        for dep in attrs.depends_on:
            adjacency[attrs.id].add(dep)
            adjacency[dep].add(attrs.id)

    start = raw_attrs[0].id
    assert start is not None
    visited: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(sorted(adjacency[node] - visited))

    for phase_id in adjacency:
        if phase_id not in visited:
            attrs = by_id[phase_id]
            _graph_fatal(
                graph_path,
                attrs.line,
                f"orphan phase {phase_id!r} is disconnected from the main graph",
            )


def _validate_phase_src(graph_path: Path, attrs: _RawPhaseAttrs, skill_root: Path) -> None:
    assert attrs.id is not None and attrs.src is not None
    src_path = Path(attrs.src)
    if src_path.is_absolute():
        _graph_fatal(graph_path, attrs.line, f"phase {attrs.id!r} src must stay inside skill root")
    root_resolved = skill_root.resolve()
    candidate = (skill_root / src_path).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        _graph_fatal(graph_path, attrs.line, f"phase {attrs.id!r} src must stay inside skill root")

    if not candidate.is_dir() or not any((candidate / name).is_file() for name in _PHASE_FILE_TO_MODE):
        _graph_fatal(
            graph_path,
            attrs.line,
            f"phase {attrs.id!r} src {attrs.src!r} has no LOGIC.md/SUBGRAPH.md/SKILL.md",
        )


def _resolve_io_ref(skill_root: Path, ref: str) -> Path:
    display_path = skill_root / ref
    if Path(ref).is_absolute():
        _io_fatal(display_path, 1, "IO schema ref must stay inside skill root")
    root_resolved = skill_root.resolve()
    candidate = (skill_root / ref).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        _io_fatal(display_path, 1, "IO schema ref must stay inside skill root")
    return candidate


def _validate_io_schema(
    skill_root: Path,
    ref: str,
    kind: Literal["input", "output"],
) -> dict[str, Any]:
    path = _resolve_io_ref(skill_root, ref)
    display_path = skill_root / ref
    if path.suffix != ".json":
        _io_fatal(display_path, 1, "IO schema refs must point to .json files")
    if not path.is_file():
        _io_fatal(display_path, 1, f"missing IO schema referenced by GRAPH.md {kind}")

    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        _io_fatal(display_path, exc.lineno, f"invalid JSON: {exc.msg}")
    except OSError as exc:
        _io_fatal(display_path, 1, f"failed to read IO schema: {exc}")

    if not isinstance(schema, dict):
        _io_fatal(display_path, 1, "JSON Schema document must be an object")

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        _io_fatal(display_path, 1, f"invalid JSON Schema: {exc.message}")
    return schema


def _extract_output_schema_keys(schema: dict[str, Any]) -> set[str] | None:
    properties = schema.get("properties")
    if properties is None:
        return None
    if not isinstance(properties, dict):
        return set()
    return {key for key in properties if isinstance(key, str)}


class _ActionReturnKeyVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, allowed_keys: set[str]) -> None:
        self.path = path
        self.allowed_keys = allowed_keys

    def visit_Return(self, node: ast.Return) -> None:  # noqa: N802
        value = node.value
        if isinstance(value, ast.Dict):
            for key_node in value.keys:
                if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                    continue
                if key_node.value not in self.allowed_keys:
                    line = getattr(key_node, "lineno", node.lineno)
                    _actions_keys_fatal(
                        self.path,
                        line,
                        f"action returns undeclared output key {key_node.value!r}",
                    )
        self.generic_visit(node)


def _validate_logic_action_return_keys(
    phase_docs: list[PhaseDocument],
    actions: ActionRegistry,
    output_schema_keys: set[str] | None,
) -> None:
    if output_schema_keys is None:
        return
    for doc in phase_docs:
        if not isinstance(doc.ast, LogicNodeAST):
            continue
        action_def = actions.for_phase(doc.phase_name).get(doc.ast.python_callable)
        if action_def is None:
            continue
        _validate_action_return_keys(action_def.path, output_schema_keys)


def _validate_action_return_keys(path: Path, output_schema_keys: set[str]) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        _actions_keys_fatal(path, exc.lineno or 1, f"could not parse action source: {exc.msg}")
    except OSError as exc:
        _actions_keys_fatal(path, 1, f"could not read action source: {exc}")
    _ActionReturnKeyVisitor(path, output_schema_keys).visit(tree)


def _build_phase_document(
    phase_name: str,
    path: Path,
    mode: str,
    frontmatter: dict[str, Any],
    body: str,
) -> PhaseDocument:
    allowed = ["role", "system_prompt", "exit_contract", "python_callable", "sub_skill_ref"]
    blocks = extract_raw_blocks(body, allowed)
    data = dict(frontmatter)
    data["raw_blocks"] = blocks
    data.setdefault("name", phase_name)

    try:
        if mode == "logic":
            data.setdefault("python_callable", blocks.get("python_callable"))
            ast: PhaseAST = LogicNodeAST.model_validate(data)
        elif mode == "subgraph":
            data.setdefault("sub_skill_ref", blocks.get("sub_skill_ref"))
            ast = SubgraphNodeAST.model_validate(data)
        else:
            data.setdefault("system_prompt", blocks.get("system_prompt"))
            data.setdefault("exit_contract", blocks.get("exit_contract"))
            ast = SkillNodeAST.model_validate(data)
    except ValidationError as exc:
        _fatal(path, 1, f"{path.name} AST validation failed: {exc}")

    return PhaseDocument(
        phase_name=phase_name,
        path=path,
        mode=mode,
        frontmatter=frontmatter,
        raw_blocks=blocks,
        ast=ast,
    )


_ATTR_RE = re.compile(r"([A-Za-z_][\w:-]*)\s*=\s*(['\"])(.*?)\2", re.DOTALL)


def _iter_self_closing_tag_attrs(body: str, tag: str) -> list[dict[str, str]]:
    pattern = re.compile(rf"<{re.escape(tag)}\b([^>]*)/>", re.IGNORECASE | re.DOTALL)
    return [_parse_attrs(match.group(1)) for match in pattern.finditer(body)]


def _first_src(body: str, tag: str) -> str | None:
    attrs = _iter_self_closing_tag_attrs(body, tag)
    if not attrs:
        return None
    return attrs[0].get("src")


def _parse_attrs(raw: str) -> dict[str, str]:
    return {match.group(1): match.group(3) for match in _ATTR_RE.finditer(raw)}


def _split_depends_on(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [part for part in re.split(r"[\s,]+", raw.strip()) if part]


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
    "PhaseDocument",
    "SkillLoader",
    "_discover_phase_files",
    "_extract_phase_attrs",
    "_guard_v21_root",
    "_resolve_io_ref",
    "_route_document",
    "_validate_graph_topology",
    "_validate_io_schema",
    "_validate_mode_matches_filename",
    "load_workflow_from_md",
]
