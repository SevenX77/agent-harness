"""AST cache for V2.1 skill compilation."""

from __future__ import annotations

import hashlib
import json
import sys
import warnings
from importlib import metadata
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from graph_agent.core.loader import (
    CompiledSkill,
    CompiledSubagent,
    PhaseAttributeSpan,
    PhaseDocument,
    PhaseTokenInfo,
)
from graph_agent.core.manifest import GraphManifest, PhaseAST
from graph_agent.core.subagents import build_subagent_input_model

_CACHE_SCHEMA_VERSION = 2


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
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{key}.json"
        cache_file.write_text(
            json.dumps(_dehydrate_compiled_skill(compiled), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    except OSError as exc:
        warnings.warn(f"Graph-agent cache write failed: {exc}", RuntimeWarning, stacklevel=2)


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
        "schema_version": _CACHE_SCHEMA_VERSION,
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
        "subagents_by_phase": {
            phase_id: [
                {
                    "parent_phase_id": subagent.parent_phase_id,
                    "name": subagent.name,
                    "path": subagent.path,
                    "description": subagent.description,
                    "root": str(subagent.root),
                    "input_schema": subagent.input_schema,
                    "expected_schema": subagent.expected_schema,
                }
                for subagent in subagents
            ]
            for phase_id, subagents in compiled.subagents_by_phase.items()
        },
        "phase_tokens": {
            phase_id: {
                "phase_id": token.phase_id,
                "raw_text": token.raw_text,
                "start_offset": token.start_offset,
                "end_offset": token.end_offset,
                "line_start": token.line_start,
                "line_end": token.line_end,
                "attrs": token.attrs,
                "attr_spans": {
                    name: {
                        "name": span.name,
                        "value": span.value,
                        "quote": span.quote,
                        "attr_start": span.attr_start,
                        "attr_end": span.attr_end,
                        "value_start": span.value_start,
                        "value_end": span.value_end,
                        "line_start": span.line_start,
                        "line_end": span.line_end,
                    }
                    for name, span in token.attr_spans.items()
                },
            }
            for phase_id, token in compiled.phase_tokens.items()
        },
    }


def _rehydrate_compiled_skill(snapshot: dict[str, Any], root: Path) -> CompiledSkill:
    from graph_agent.core.loader import (
        _discover_actions_and_tools,
        _inject_subagent_tools,
        _subagent_input_model_name,
    )

    if snapshot["schema_version"] != _CACHE_SCHEMA_VERSION:
        raise ValueError("unsupported cache schema version")
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
    subagents_by_phase = _rehydrate_subagents_by_phase(
        snapshot["subagents_by_phase"], _subagent_input_model_name
    )
    tools = _inject_subagent_tools(tools, subagents_by_phase)
    phase_tokens = _rehydrate_phase_tokens(snapshot["phase_tokens"])
    return CompiledSkill(
        raw=dict(snapshot["raw"]),
        manifest=manifest,
        nodes=nodes,
        actions=actions,
        tools=tools,
        subagents_by_phase=subagents_by_phase,
        phase_tokens=phase_tokens,
    )


def _rehydrate_subagents_by_phase(
    snapshot: dict[str, Any],
    input_model_name: Any,
) -> dict[str, list[CompiledSubagent]]:
    subagents_by_phase: dict[str, list[CompiledSubagent]] = {}
    for phase_id, subagents in snapshot.items():
        phase_subagents: list[CompiledSubagent] = []
        for subagent in subagents:
            expected_schema = dict(subagent["expected_schema"])
            name = str(subagent["name"])
            parent_phase_id = str(subagent["parent_phase_id"])
            input_model = build_subagent_input_model(
                input_model_name(parent_phase_id, name),
                expected_schema,
            )
            phase_subagents.append(
                CompiledSubagent(
                    parent_phase_id=parent_phase_id,
                    name=name,
                    path=str(subagent["path"]),
                    description=str(subagent["description"]),
                    root=Path(subagent["root"]),
                    input_schema=dict(subagent["input_schema"]),
                    input_model=input_model,
                    expected_schema=expected_schema,
                )
            )
        subagents_by_phase[str(phase_id)] = phase_subagents
    return subagents_by_phase


def _rehydrate_phase_tokens(snapshot: dict[str, Any]) -> dict[str, PhaseTokenInfo]:
    tokens: dict[str, PhaseTokenInfo] = {}
    for phase_id, token in snapshot.items():
        attr_spans = {
            str(name): PhaseAttributeSpan(
                name=str(span["name"]),
                value=str(span["value"]),
                quote=str(span["quote"]),
                attr_start=int(span["attr_start"]),
                attr_end=int(span["attr_end"]),
                value_start=int(span["value_start"]),
                value_end=int(span["value_end"]),
                line_start=int(span["line_start"]),
                line_end=int(span["line_end"]),
            )
            for name, span in token["attr_spans"].items()
        }
        tokens[str(phase_id)] = PhaseTokenInfo(
            phase_id=str(token["phase_id"]),
            raw_text=str(token["raw_text"]),
            start_offset=int(token["start_offset"]),
            end_offset=int(token["end_offset"]),
            line_start=int(token["line_start"]),
            line_end=int(token["line_end"]),
            attrs=dict(token["attrs"]),
            attr_spans=attr_spans,
        )
    return tokens


__all__ = ["compute_cache_key", "get_cache_dir", "load_from_cache", "save_to_cache"]
