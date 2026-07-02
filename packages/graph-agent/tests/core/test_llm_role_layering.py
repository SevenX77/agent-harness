"""llm_role layering: graph-level default + per-node use_graph_llm_role switch.

Design source: docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md — GRAPH.md
``llm_role`` is the whole-graph default role; SKILL.md ``llm_role`` overrides
it; ``use_graph_llm_role: true`` inverts the priority so the graph default
wins while the node's own value stays untouched in the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent.core.graph_assembler import _resolve_phase_chat_model
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import AgentNodeAST, GraphManifest, effective_llm_role


def _write_minimal_agent_skill(
    root: Path,
    *,
    graph_extra: str = "",
    skill_extra: str = "",
) -> None:
    (root / "phases" / "seg").mkdir(parents=True)
    graph_extra_block = f"{graph_extra}\n" if graph_extra else ""
    skill_extra_block = f"{skill_extra}\n" if skill_extra else ""
    (root / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: llm-role-layering-test
{graph_extra_block}io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - seg
---
<phase depends_on="input" output>seg</phase>
""",
        encoding="utf-8",
    )
    (root / "phases" / "seg" / "SKILL.md").write_text(
        f"""---
{skill_extra_block}io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties:
      answer:
        type: string
---
<role>Segmenter</role>
<goal>Answer.</goal>
""",
        encoding="utf-8",
    )


class _RecordingResolver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def resolve(self, role_name: str, **kwargs: Any) -> object:
        self.calls.append(role_name)
        return object()


def _agent_ast(compiled_skill: Any, phase_id: str) -> AgentNodeAST:
    for node in compiled_skill.nodes:
        if node.phase_name == phase_id:
            ast = node.ast
            assert isinstance(ast, AgentNodeAST)
            return ast
    raise AssertionError(f"phase {phase_id!r} not found")


# --- compile-level: the fields exist and round-trip through the loader ---


def test_graph_manifest_accepts_graph_level_llm_role(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_agent_skill(tmp_path, graph_extra="llm_role: fast")
    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)
    assert compiled.manifest.llm_role == "fast"


def test_graph_manifest_llm_role_defaults_to_none(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_agent_skill(tmp_path)
    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)
    assert compiled.manifest.llm_role is None


def test_agent_node_accepts_use_graph_llm_role(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_agent_skill(
        tmp_path,
        graph_extra="llm_role: fast",
        skill_extra="llm_role: analyst\nuse_graph_llm_role: true",
    )
    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)
    ast = _agent_ast(compiled, "seg")
    assert ast.use_graph_llm_role is True
    # The node's own value is preserved untouched next to the switch.
    assert ast.llm_role == "analyst"


def test_agent_node_use_graph_llm_role_defaults_to_false(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _write_minimal_agent_skill(tmp_path, skill_extra="llm_role: analyst")
    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)
    assert _agent_ast(compiled, "seg").use_graph_llm_role is False


# --- the effective-role chain (pure) ---


def test_effective_role_switch_on_graph_wins() -> None:
    ast = AgentNodeAST(
        mode="agent", role="r", goal="g", llm_role="analyst", use_graph_llm_role=True
    )
    assert effective_llm_role(ast, "fast") == "fast"


def test_effective_role_switch_on_without_graph_default_falls_back() -> None:
    ast = AgentNodeAST(
        mode="agent", role="r", goal="g", llm_role="analyst", use_graph_llm_role=True
    )
    assert effective_llm_role(ast, None) == "graph_agent"


def test_effective_role_switch_off_node_wins() -> None:
    ast = AgentNodeAST(mode="agent", role="r", goal="g", llm_role="analyst")
    assert effective_llm_role(ast, "fast") == "analyst"


def test_effective_role_switch_off_without_node_inherits_graph() -> None:
    ast = AgentNodeAST(mode="agent", role="r", goal="g")
    assert effective_llm_role(ast, "fast") == "fast"


def test_effective_role_both_unset_uses_conventional_default() -> None:
    ast = AgentNodeAST(mode="agent", role="r", goal="g")
    assert effective_llm_role(ast, None) == "graph_agent"


# --- the resolver receives the effective role, not the raw node value ---


def test_resolver_receives_effective_role() -> None:
    resolver = _RecordingResolver()
    model = _resolve_phase_chat_model(
        "seg",
        "fast",
        chat_model=None,
        model_resolver=resolver,
        llm_provider=None,
        callbacks=(),
    )
    assert model is not None
    assert resolver.calls == ["fast"]


# --- graph manifest still rejects genuinely unknown fields ---


def test_graph_manifest_still_rejects_unknown_fields() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GraphManifest.model_validate(
            {
                "schema_version": "v0.3.0",
                "name": "x",
                "made_up_field": 1,
                "io": {
                    "inputs": {"type": "object", "properties": {}},
                    "outputs": {"type": "object", "properties": {}},
                },
                "phases": ["seg"],
            }
        )
