"""AST cache for V2.1 skill compilation."""

from __future__ import annotations

import hashlib
import json
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from graph_agent.core.loader import CompiledSkill, PhaseDocument
from graph_agent.core.manifest import GraphManifest, PhaseAST


def get_cache_dir() -> Path:
    return Path.home() / ".cache" / "graph-agent-v21"


def compute_cache_key(root: Path) -> str:
    root = root.resolve()
    payload = {
        "root": str(root),
        "python": list(sys.version_info[:3]),
        "package": _get_graph_agent_version(),
        "files": _skill_file_metadata(root),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_from_cache(key: str, root: Path) -> CompiledSkill | None:
    cache_file = get_cache_dir() / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        snapshot = json.loads(cache_file.read_text(encoding="utf-8"))
        return _rehydrate_compiled_skill(snapshot, root)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_to_cache(key: str, compiled: CompiledSkill) -> None:
    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{key}.json"
    cache_file.write_text(
        json.dumps(_dehydrate_compiled_skill(compiled), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _collect_skill_files(root: Path) -> list[Path]:
    files: list[Path] = []
    graph = root / "GRAPH.md"
    if graph.exists():
        files.append(graph)
    io_dir = root / "io"
    if io_dir.exists():
        files.extend(path for path in io_dir.glob("*.json") if path.is_file())
    phases_dir = root / "phases"
    if phases_dir.exists():
        files.extend(path for path in phases_dir.rglob("*.md") if path.is_file())
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _skill_file_metadata(root: Path) -> list[tuple[str, int, int]]:
    metadata_rows: list[tuple[str, int, int]] = []
    for path in _collect_skill_files(root):
        stat = path.stat()
        metadata_rows.append((path.relative_to(root).as_posix(), stat.st_mtime_ns, stat.st_size))
    return metadata_rows


def _get_graph_agent_version() -> str:
    try:
        return metadata.version("graph-agent")
    except metadata.PackageNotFoundError:
        return "0+local"


def _dehydrate_compiled_skill(compiled: CompiledSkill) -> dict[str, Any]:
    return {
        "raw": compiled.raw,
        "manifest": compiled.manifest.model_dump(mode="json"),
        "nodes": [
            {
                "phase_name": node.phase_name,
                "path": str(node.path),
                "mode": node.mode,
                "frontmatter": node.frontmatter,
                "raw_blocks": node.raw_blocks,
                "ast": node.ast.model_dump(mode="json"),
            }
            for node in compiled.nodes
        ],
    }


def _rehydrate_compiled_skill(snapshot: dict[str, Any], root: Path) -> CompiledSkill:
    from graph_agent.core.loader import _discover_actions_and_tools

    manifest = GraphManifest.model_validate(snapshot["manifest"])
    adapter: TypeAdapter[PhaseAST] = TypeAdapter(PhaseAST)
    nodes = [
        PhaseDocument(
            phase_name=str(node["phase_name"]),
            path=Path(node["path"]),
            mode=str(node["mode"]),
            frontmatter=dict(node["frontmatter"]),
            raw_blocks=dict(node["raw_blocks"]),
            ast=adapter.validate_python(node["ast"]),
        )
        for node in snapshot["nodes"]
    ]
    discovered = [(node.phase_name, node.path, node.mode) for node in nodes]
    actions, tools = _discover_actions_and_tools(root.resolve(), discovered)
    return CompiledSkill(
        raw=dict(snapshot["raw"]),
        manifest=manifest,
        nodes=nodes,
        actions=actions,
        tools=tools,
    )


__all__ = ["compute_cache_key", "get_cache_dir", "load_from_cache", "save_to_cache"]
