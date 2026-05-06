"""Three-stage SKILL.md loader pipeline."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .exceptions import SkillLoadError
from .harness import GraphAgentHarness, Phase
from .schema_engine import SchemaEngine
from .skill_builder import (
    _SCHEMA_ENGINE,
    _compose_agent_system_prompt,
    _phase_from_agent_skill,
    _phase_from_graph_phase,
    _render_skill_section_xml_tags,
    build_graph_nodes,
)
from .skill_parser import parse_skill_md
from .skill_validator import validate_manifest

if TYPE_CHECKING:
    from .io_manager import IODef, IOManager
    from .manifest import SkillManifest as SkillManifestType
    from .module_sandbox import ModuleSandbox
    from .phase_node import PhaseNode

logger = logging.getLogger(__name__)

__all__ = [
    "CompiledSkill",
    "SkillLoader",
    "_compose_agent_system_prompt",
    "_phase_from_agent_skill",
    "_phase_from_graph_phase",
    "_render_skill_section_xml_tags",
    "_SCHEMA_ENGINE",
    "build_graph_nodes",
    "get_schema_engine",
    "load_workflow_from_md",
    "parse_skill_md",
    "validate_manifest",
]


@dataclass(frozen=True)
class CompiledSkill:
    """Phase 1-3 pipeline result emitted by SkillLoader."""

    raw: dict[str, Any]
    manifest: SkillManifestType
    nodes: list[PhaseNode] = field(default_factory=list)


def get_schema_engine() -> SchemaEngine:
    """Return the SchemaEngine shared across compile + runtime consumers."""
    return _SCHEMA_ENGINE


class SkillLoader:
    """Thin orchestrator over parse -> validate -> build."""

    def __init__(
        self,
        schema_engine: SchemaEngine | None = None,
        io_manager_factory: Callable[[list[IODef]], IOManager] | None = None,
        module_sandbox: ModuleSandbox | None = None,
    ) -> None:
        self._schema_engine = schema_engine or get_schema_engine()
        if module_sandbox is None:
            from .module_sandbox import ModuleSandbox

            module_sandbox = ModuleSandbox()
        self._module_sandbox = module_sandbox
        if io_manager_factory is None:
            from .io_manager import IOManager

            def io_manager_factory(specs: list[IODef]) -> IOManager:
                return IOManager(specs)

        self._io_manager_factory = io_manager_factory

    def compile_skill(self, skill_path: str | Path) -> CompiledSkill:
        path = Path(skill_path)
        _guard_skill_file(path)
        raw = parse_skill_md(path.read_text(encoding="utf-8"))
        _guard_schema_version(raw, path)
        manifest = validate_manifest(raw, self._schema_engine, self._io_manager_factory)
        nodes = build_graph_nodes(
            manifest,
            self._schema_engine,
            self._module_sandbox.with_search_paths([path.parent]),
        )
        return CompiledSkill(raw=raw, manifest=manifest, nodes=nodes)


def load_workflow_from_md(
    md_path: str | Path,
    callbacks: list[Any] | None = None,
    _loading_stack: set[str] | None = None,
) -> GraphAgentHarness:
    """Compile a SKILL.md file into a GraphAgentHarness via the three stages."""
    del _loading_stack
    path = Path(md_path)
    compiled = SkillLoader().compile_skill(path)
    phases = _phases_from_nodes(compiled.nodes)
    return GraphAgentHarness(
        phases=phases,
        callbacks=callbacks,
        io_config=_raw_io_config(compiled.manifest),
        context_mapping=_raw_context_mapping(compiled.manifest),
        skill_dir=path.parent,
    )


def _guard_skill_file(path: Path) -> None:
    if not path.exists():
        raise SkillLoadError(f"SKILL.md not found: {path}")
    if not path.read_text(encoding="utf-8").strip():
        raise SkillLoadError(f"SKILL.md is empty: {path}")


def _guard_schema_version(raw: dict[str, Any], path: Path) -> None:
    if "schema_version" not in raw:
        raise SkillLoadError(
            f"Missing schema_version in {path}. Only schema_version: '2.0' is supported."
        )
    schema_version = str(raw.get("schema_version") or "").strip()
    if schema_version != "2.0":
        raise SkillLoadError(
            f"Unsupported schema_version: {schema_version!r} in {path}. "
            'Only schema_version: "2.0" is supported.'
        )


def _phases_from_nodes(nodes: list[PhaseNode]) -> list[Phase]:
    phases: list[Phase] = []
    for node in nodes:
        if node.phase is None:
            raise SkillLoadError(f"PhaseNode {node.name!r} has no runtime Phase")
        phases.append(node.phase)
    return phases


def _raw_io_config(manifest: SkillManifestType) -> dict[str, Any] | None:
    from .manifest import GraphSkillDef

    return manifest.io.model_dump() if isinstance(manifest, GraphSkillDef) else None


def _raw_context_mapping(manifest: SkillManifestType) -> dict[str, str] | None:
    from .manifest import GraphSkillDef

    if isinstance(manifest, GraphSkillDef) and manifest.context_mapping:
        return dict(manifest.context_mapping)
    return None
