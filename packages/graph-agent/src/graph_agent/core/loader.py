"""V2.1 graph skill loader: route GRAPH.md + phase node documents."""

from __future__ import annotations

import logging
import json
import re
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal

from jsonschema.exceptions import SchemaError
from jsonschema.validators import Draft202012Validator
from pydantic import ValidationError

from graph_agent.core.exceptions import SkillLoadError
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


class SkillLoader:
    """Thin V2.1 parser/route orchestrator."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def compile_skill(self, skill_root: str | Path) -> CompiledSkill:
        root = Path(skill_root)
        _guard_v21_root(root)

        graph_path = root / "GRAPH.md"
        graph_frontmatter, graph_body, _ = parse_markdown_parts(graph_path)
        manifest = _parse_graph_manifest(graph_path, graph_frontmatter, graph_body)
        io_inputs = _validate_io_schema(root, manifest.io_inputs_ref, "input")
        io_outputs = _validate_io_schema(root, manifest.io_outputs_ref, "output")

        phase_docs: list[PhaseDocument] = []
        for phase_name, phase_file, mode in _discover_phase_files(root):
            frontmatter, body, _ = parse_markdown_parts(phase_file)
            yaml_mode = str(frontmatter.get("mode") or "").strip()
            _validate_mode_matches_filename(phase_file, yaml_mode)
            scan_forbidden_topology_tags(phase_file, body)
            phase_docs.append(_build_phase_document(phase_name, phase_file, mode, frontmatter, body))

        raw = {
            "graph": {"frontmatter": graph_frontmatter, "body": graph_body},
            "io": {"inputs": io_inputs, "outputs": io_outputs},
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
        return CompiledSkill(raw=raw, manifest=manifest, nodes=phase_docs)


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
    SkillLoader().compile_skill(root)
    raise SkillLoadError(
        "[F-v21-route] "
        f"{root}:1 V2.1 runtime harness assembly is not implemented until T1.5"
    )


def _fatal(path: Path, line: int, message: str) -> None:
    raise SkillLoadError(f"[F-v21-route] {path}:{line} {message}")


def _io_fatal(path: Path, line: int, message: str) -> None:
    raise SkillLoadError(f"[F-v21-io] {path}:{line} {message}")


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


def _parse_graph_manifest(path: Path, frontmatter: dict[str, Any], body: str) -> GraphManifest:
    data = dict(frontmatter)
    data.setdefault("schema_version", "2.1")

    input_ref = _first_src(body, "input")
    output_ref = _first_src(body, "output")
    if input_ref:
        data["io_inputs_ref"] = input_ref
    if output_ref:
        data["io_outputs_ref"] = output_ref

    phases = []
    for attrs in _iter_self_closing_tag_attrs(body, "phase"):
        if "id" not in attrs or "src" not in attrs:
            continue
        phases.append(
            GraphPhaseRef(
                id=attrs["id"],
                src=attrs["src"],
                depends_on=_split_depends_on(attrs.get("depends_on", "")),
            )
        )
    data["phases"] = phases

    try:
        return GraphManifest.model_validate(data)
    except ValidationError as exc:
        _fatal(path, 1, f"GRAPH.md manifest validation failed: {exc}")


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
    "_guard_v21_root",
    "_resolve_io_ref",
    "_route_document",
    "_validate_io_schema",
    "_validate_mode_matches_filename",
    "load_workflow_from_md",
]
