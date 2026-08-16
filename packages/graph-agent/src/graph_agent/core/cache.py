"""AST cache for V0.3.0 skill compilation."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from graph_agent.core.loader import CompiledSkill, PhaseDocument
from graph_agent.core.manifest import GraphManifest, PhaseAST

logger = logging.getLogger(__name__)


def get_cache_dir() -> Path:
    return Path.home() / ".cache" / "graph-agent-v030"


def compute_cache_key(root: Path) -> str:
    root = root.resolve()
    payload = {
        "format": "v2",
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
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("[Cache] Failed to load cached compiled skill %s: %s", key, exc)
        return None


def save_to_cache(key: str, compiled: CompiledSkill) -> None:
    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{key}.json"
    cache_file.write_text(
        json.dumps(_dehydrate_compiled_skill(compiled), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


#: File types a compile reads: the markdown documents it parses and the Python
#: modules it imports (validators, logic actions, tools).
_COMPILE_INPUT_SUFFIXES = frozenset({".md", ".py"})


def _is_skipped_dir(name: str) -> bool:
    """Directories a compile never reads, pruned before descending into them.

    Not tidiness — each one is actively harmful in the key. ``.workspace`` holds
    run/predict output that every execution rewrites, so keying on it would
    invalidate the cache after each run. ``.git`` is large enough to make the walk
    itself the dominant cost. ``__pycache__`` mirrors sources the key already
    covers, with mtimes that move on import rather than on edit.
    """
    return name.startswith(".") or name == "__pycache__"


def _collect_skill_files(root: Path) -> list[Path]:
    """Every compile input under the skill root.

    Deliberately over-approximate. An input the key MISSES makes ``compile_skill``
    answer for a tree that is not the one on disk — a wrong answer. An extra file
    in the key only costs a recompile. Build caches that get this right (ccache's
    depfiles, Bazel's declared inputs) all treat an unsound dependency set as a
    correctness bug rather than a tuning knob, and this follows that side.

    Known remaining hole: a subgraph resolved OUTSIDE this root (a linked skill)
    is still not covered, because the resolved set is only known after compiling.
    Closing that needs the loader to report its read-set and the cache snapshot to
    carry it — a separate change. This one shrinks the hole from "everything below
    the root except GRAPH.md and phases/" to "only out-of-root links".
    """
    files: list[Path] = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if not _is_skipped_dir(name)]
        base = Path(directory)
        files.extend(
            base / filename
            for filename in filenames
            if Path(filename).suffix in _COMPILE_INPUT_SUFFIXES
        )
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
        "subagents_by_phase": {
            phase_id: [
                {
                    "parent_phase_id": subagent.parent_phase_id,
                    "name": subagent.name,
                    "target_skill": subagent.target_skill,
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
                    attr_name: {
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
                    for attr_name, span in token.attr_spans.items()
                },
            }
            for phase_id, token in compiled.phase_tokens.items()
        },
    }


def _rehydrate_compiled_skill(snapshot: dict[str, Any], root: Path) -> CompiledSkill:
    from graph_agent.core.loader import (
        CompiledSubagent,
        PhaseAttributeSpan,
        PhaseTokenInfo,
        _discover_actions_and_tools,
        _inject_subagent_tools,
        _subagent_input_model_name,
    )
    from graph_agent.core.subagents import build_subagent_input_model

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
    subagents_by_phase: dict[str, list[CompiledSubagent]] = {}
    for phase_id, subagents in dict(snapshot["subagents_by_phase"]).items():
        hydrated_subagents: list[CompiledSubagent] = []
        for item in subagents:
            input_schema = dict(item["input_schema"])
            input_model = build_subagent_input_model(
                _subagent_input_model_name(str(item["parent_phase_id"]), str(item["name"])),
                input_schema,
            )
            hydrated_subagents.append(
                CompiledSubagent(
                    parent_phase_id=str(item["parent_phase_id"]),
                    name=str(item["name"]),
                    target_skill=str(item["target_skill"]),
                    description=str(item["description"]),
                    root=Path(item["root"]),
                    input_schema=input_schema,
                    input_model=input_model,
                    expected_schema=dict(item["expected_schema"]),
                )
            )
        subagents_by_phase[str(phase_id)] = hydrated_subagents
    phase_tokens: dict[str, PhaseTokenInfo] = {}
    for phase_id, token in dict(snapshot["phase_tokens"]).items():
        attr_spans = {
            str(attr_name): PhaseAttributeSpan(**span)
            for attr_name, span in dict(token["attr_spans"]).items()
        }
        phase_tokens[str(phase_id)] = PhaseTokenInfo(
            phase_id=str(token["phase_id"]),
            raw_text=str(token["raw_text"]),
            start_offset=int(token["start_offset"]),
            end_offset=int(token["end_offset"]),
            line_start=int(token["line_start"]),
            line_end=int(token["line_end"]),
            attrs=dict(token["attrs"]),
            attr_spans=attr_spans,
        )
    tools = _inject_subagent_tools(tools, subagents_by_phase)
    return CompiledSkill(
        raw=dict(snapshot["raw"]),
        manifest=manifest,
        nodes=nodes,
        actions=actions,
        tools=tools,
        subagents_by_phase=subagents_by_phase,
        phase_tokens=phase_tokens,
    )


__all__ = ["compute_cache_key", "get_cache_dir", "load_from_cache", "save_to_cache"]
