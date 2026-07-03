"""Graph topology projection helpers owned by graph-agent core."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from graph_agent.core.exceptions import GraphAgentError
from graph_agent.core.loader import _extract_body_phase_refs
from graph_agent.core.parser import parse_markdown_parts, parse_markdown_parts_best_effort

_PHASE_FILE_TO_MODE = {
    "LOGIC.md": "logic",
    "SUBGRAPH.md": "subgraph",
    "SKILL.md": "agent",
}


@dataclass(frozen=True)
class GraphTopologyProjection:
    phases: list[str]
    graph_topology: list[dict[str, object]]


@dataclass(frozen=True)
class ChildGraphTopologyProjection(GraphTopologyProjection):
    path: str
    name: str
    description: str


class SubgraphTopologyProjectionError(ValueError):
    def __init__(self, code: str, reason: str, path: str) -> None:
        self.code = code
        self.reason = reason
        self.path = path
        super().__init__(reason)


def load_graph_topology_projection(skill_dir: Path) -> GraphTopologyProjection:
    graph_path = skill_dir / "GRAPH.md"
    if not graph_path.exists():
        return GraphTopologyProjection(phases=[], graph_topology=[])

    try:
        frontmatter, body, _line_meta = parse_markdown_parts(graph_path)
    except GraphAgentError:
        # The strict compile-path parser (`parse_markdown_parts`) treats the
        # whole frontmatter as one atomic YAML document, so a defect
        # anywhere in it (most often a duplicate key hand-authored under
        # `io.inputs`/`io.outputs`) blanks out `phases` too, even though
        # `phases` itself is syntactically fine. This projection's entire
        # purpose is showing phases/DAG in Studio's repair view WHILE the
        # skill is broken, so losing recoverable data to a field this
        # projection never reads defeats it — fall back to a tolerant parse.
        # If the frontmatter is malformed beyond just a duplicate key, this
        # re-raises and the caller's own catch-all degrades to ([], []).
        frontmatter, body, _line_meta = parse_markdown_parts_best_effort(graph_path)
    phases_raw = frontmatter.get("phases", [])
    phases = [str(phase) for phase in phases_raw] if isinstance(phases_raw, list) else []
    refs = _extract_body_phase_refs(graph_path, body)

    topology: list[dict[str, object]] = []
    for ref in refs:
        mode = phase_mode_for(skill_dir, ref.name)
        row: dict[str, object] = {
            "id": ref.name,
            "src": f"phases/{ref.name}",
            "depends_on": list(ref.depends_on),
            "mode": mode,
        }
        if mode == "subgraph":
            row["path"] = read_subgraph_path(skill_dir, ref.name)
        if ref.output:
            row["output"] = True
        topology.append(row)

    return GraphTopologyProjection(phases=phases, graph_topology=topology)


def phase_mode_for(skill_dir: Path, phase_name: str) -> str:
    phase_dir = skill_dir / "phases" / phase_name
    for filename, mode in _PHASE_FILE_TO_MODE.items():
        if (phase_dir / filename).exists():
            return mode
    return ""


def read_subgraph_path(skill_dir: Path, phase_name: str) -> str | None:
    phase_path = skill_dir / "phases" / phase_name / "SUBGRAPH.md"
    if not phase_path.is_file():
        return None
    frontmatter, _body, _line_meta = parse_markdown_parts(phase_path)
    path_value = frontmatter.get("path")
    if isinstance(path_value, str) and path_value.strip():
        value = path_value.strip()
        candidate = Path(value)
        # Surface a RESOLVED ABSOLUTE child path so consumers (Studio Subgraph
        # Library + inline drill-down) get a usable location regardless of whether
        # the author wrote the recommended relative-to-skill-root form or an
        # absolute path. Relative paths resolve against the skill root, matching
        # the compile/assembly resolvers (loader._resolve_subgraph_path_root).
        if candidate.is_absolute():
            return str(candidate)
        return str((skill_dir.resolve() / candidate).resolve())
    return None


def load_child_graph_topology_projection(
    *,
    parent_skill_dir: Path,
    child_path: str,
    allowed_roots: list[Path],
) -> ChildGraphTopologyProjection:
    resolved_child = resolve_subgraph_child_root(
        parent_skill_dir=parent_skill_dir,
        child_path=child_path,
        allowed_roots=allowed_roots,
    )
    graph_md = resolved_child / "GRAPH.md"
    frontmatter, _body, _line_meta = parse_markdown_parts(graph_md)
    projection = load_graph_topology_projection(resolved_child)
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    return ChildGraphTopologyProjection(
        path=str(resolved_child),
        name=name if isinstance(name, str) and name else resolved_child.name,
        description=description if isinstance(description, str) else "",
        phases=projection.phases,
        graph_topology=projection.graph_topology,
    )


def resolve_subgraph_child_root(
    *,
    parent_skill_dir: Path,
    child_path: str,
    allowed_roots: list[Path],
) -> Path:
    if not child_path or not child_path.strip():
        raise SubgraphTopologyProjectionError("SUBGRAPH_PATH_INVALID", "path is empty", child_path)
    if "\x00" in child_path:
        raise SubgraphTopologyProjectionError("SUBGRAPH_PATH_INVALID", "path contains null byte", child_path)

    candidate = Path(child_path)
    if not candidate.is_absolute():
        raise SubgraphTopologyProjectionError("SUBGRAPH_PATH_INVALID", "path must be absolute", child_path)

    roots = _resolved_allowed_roots(parent_skill_dir, allowed_roots)
    resolved_child = candidate.resolve(strict=False)
    if not any(_is_within(resolved_child, root) for root in roots):
        raise SubgraphTopologyProjectionError(
            "SUBGRAPH_PATH_INVALID",
            "path is outside the workspace boundary",
            child_path,
        )

    if not (resolved_child / "GRAPH.md").is_file():
        raise SubgraphTopologyProjectionError("SUBGRAPH_PATH_NOT_FOUND", "GRAPH.md not found", child_path)
    return resolved_child


def _resolved_allowed_roots(parent_skill_dir: Path, allowed_roots: list[Path]) -> list[Path]:
    roots = [parent_skill_dir, *allowed_roots]
    resolved: list[Path] = []
    for root in roots:
        try:
            resolved.append(root.resolve(strict=False))
        except OSError:
            continue
    return resolved


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True
