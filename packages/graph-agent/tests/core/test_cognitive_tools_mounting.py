"""Cognitive tool mounting on the live create_agent path.

Migration decision 2026-08-15 (docs/design/2026-08-15-legacy-cognitive-features-
migration-decision.md):

* §3.1-§3.3 — ask_clarification / update_working_memory / log_ambiguity are
  mounted unconditionally (P1-5 escape-hatch ruling for clarification).
* §3.4 — query_working_memory / read_artifact stay opt-in behind the phase's
  ``context_access`` declaration (Round 8 strong-isolation ruling), carried
  loader → AgentNodeAST → graph_assembler.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

import graph_agent.core.graph_assembler as graph_assembler
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import AgentNodeAST


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _skill(root: Path, *, context_access: list[str] | None = None) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: cognitive-tools-mount-probe
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - main
---
<phase depends_on="input" output>main</phase>
""",
    )
    access_block = (
        "context_access:\n" + "".join(f"  - {name}\n" for name in context_access)
        if context_access
        else ""
    )
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
max_iterations: 2
llm_role: graph_agent
{access_block}---
<role>
Mount probe.
</role>
<goal>
Produce the declared output.
</goal>
""",
    )


class _ChatModel:
    def bind_tools(self, tools: list[Any], **kwargs: Any) -> _ChatModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> Any:
        del messages
        raise AssertionError("model must not be invoked by mounting tests")


class _Resolver:
    def __init__(self, model: Any) -> None:
        self._model = model

    def resolve(
        self,
        llm_role: str,
        *,
        callbacks: tuple[Any, ...],
        phase_name: str,
        predict_context: Any = None,
    ) -> Any:
        del llm_role, callbacks, phase_name, predict_context
        return self._model


def _mounted_tool_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: object,
    *,
    context_access: list[str] | None = None,
) -> set[str]:
    _skill(tmp_path, context_access=context_access)
    captured: dict[str, Any] = {}

    class _Agent:
        def invoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
            del config, kwargs
            return input

    def fake_create_agent(**kwargs: Any) -> _Agent:
        captured["create_agent_kwargs"] = kwargs
        return _Agent()

    monkeypatch.setattr(graph_assembler, "create_agent", fake_create_agent, raising=False)

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = graph_assembler.assemble_graph(
        compiled,
        model_resolver=_Resolver(_ChatModel()),
        skill_resolver=mock_skill_resolver,
        checkpointer=InMemorySaver(),
    ).graph
    graph.invoke(
        {"data": {"topic": "probe"}, "flow": {"thread_id": "mount-thread"}, "messages": []},
        config={"configurable": {"thread_id": "mount-thread"}},
    )

    assert "create_agent_kwargs" in captured
    return {str(getattr(tool, "name", "")) for tool in captured["create_agent_kwargs"]["tools"]}


def test_cognitive_tools_mounted_unconditionally(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mock_skill_resolver: object
) -> None:
    tool_names = _mounted_tool_names(monkeypatch, tmp_path, mock_skill_resolver)

    assert {"ask_clarification", "update_working_memory", "log_ambiguity"} <= tool_names
    assert "query_working_memory" not in tool_names
    assert "read_artifact" not in tool_names


def test_context_access_working_memory_mounts_only_query_tool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mock_skill_resolver: object
) -> None:
    tool_names = _mounted_tool_names(
        monkeypatch, tmp_path, mock_skill_resolver, context_access=["working_memory"]
    )

    assert "query_working_memory" in tool_names
    assert "read_artifact" not in tool_names


def test_context_access_artifact_mounts_only_read_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mock_skill_resolver: object
) -> None:
    tool_names = _mounted_tool_names(
        monkeypatch, tmp_path, mock_skill_resolver, context_access=["artifact"]
    )

    assert "read_artifact" in tool_names
    assert "query_working_memory" not in tool_names


def test_context_access_both_mounts_both_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mock_skill_resolver: object
) -> None:
    tool_names = _mounted_tool_names(
        monkeypatch,
        tmp_path,
        mock_skill_resolver,
        context_access=["working_memory", "artifact"],
    )

    assert {"query_working_memory", "read_artifact"} <= tool_names


def test_loader_carries_context_access_into_agent_ast(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _skill(tmp_path, context_access=["working_memory", "artifact"])

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    agent_asts = [doc.ast for doc in compiled.nodes if isinstance(doc.ast, AgentNodeAST)]
    assert len(agent_asts) == 1
    assert agent_asts[0].context_access == ["working_memory", "artifact"]


def test_loader_defaults_context_access_to_empty(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _skill(tmp_path)

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    agent_asts = [doc.ast for doc in compiled.nodes if isinstance(doc.ast, AgentNodeAST)]
    assert agent_asts[0].context_access == []


def test_loader_rejects_unknown_context_access_value(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _skill(tmp_path, context_access=["everything"])

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    payload = exc_info.value.payload
    assert payload is not None
    assert str(payload.field_path or "").startswith("context_access")
    assert "working_memory" in str(exc_info.value)
