from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError, make_error_payload
from graph_agent.core.graph_assembler import assemble_graph
from langchain_core.messages import AIMessage


class CapturePromptChatModel:
    def __init__(self) -> None:
        self.system_prompts: list[str] = []

    def bind_tools(self, tools: list[Any]) -> "CapturePromptChatModel":
        del tools
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.system_prompts.append(str(messages[0].content))
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {"markdown": "## answer\n\nok"},
                    "id": "finish-1",
                }
            ],
        )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent_skill(root: Path, *, reference_path: str = "references/guide.md") -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: reference-reader
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
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
phase_config:
  tools:
    - finish_task
  references:
    - id: Guide
      path: {reference_path}
      summary: Guide reference
---
<role>
Reader.
</role>
<goal>
Use @reference:Guide.
</goal>
""",
    )


def test_reader_failure_warns_and_fallback_markdown_enters_knowledge_base(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FailingReaderRuntime:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def initial_state(self) -> dict[str, Any]:
            raise TimeoutError("reader timed out")

    monkeypatch.setattr(
        "graph_agent.core.graph_assembler.ReferenceReaderRuntime",
        FailingReaderRuntime,
    )
    _agent_skill(tmp_path)
    _write(tmp_path / "references" / "guide.md", "fallback source text " * 50)
    chat = CapturePromptChatModel()

    graph = assemble_graph(compile_skill(tmp_path, cache=False), chat_model=chat).graph
    graph.invoke({"data": {"inputs": {"topic": "T"}}, "flow": {}, "messages": [], "run_id": "r1"})

    prompt = chat.system_prompts[0]
    knowledge_base = prompt[prompt.index("<knowledge_base>") : prompt.index("</knowledge_base>")]
    assert "[F-v3-reference-reader-failed]" in knowledge_base
    assert "fallback source text" in knowledge_base


def test_invalid_reference_path_is_compile_fatal_not_reader_fallback(tmp_path: Path) -> None:
    _agent_skill(tmp_path, reference_path="../outside.md")

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(tmp_path, cache=False)
    assert exc_info.value.payload.code == "[F-v3-resource-reference-path-invalid]"


def test_reference_path_escape_to_existing_file_is_compile_fatal(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    _write(outside, "external reference")
    _agent_skill(tmp_path, reference_path=f"../{outside.name}")

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(tmp_path, cache=False)
    assert exc_info.value.payload.code == "[F-v3-resource-reference-path-invalid]"


def test_reference_reader_path_invalid_fatal_propagates_from_assembly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class PathInvalidReaderRuntime:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def initial_state(self) -> dict[str, Any]:
            raise GraphAgentFatalError(
                "escaped",
                payload=make_error_payload("[F-v3-resource-reference-path-invalid]", "escaped"),
            )

    monkeypatch.setattr(
        "graph_agent.core.graph_assembler.ReferenceReaderRuntime",
        PathInvalidReaderRuntime,
    )
    _agent_skill(tmp_path)
    _write(tmp_path / "references" / "guide.md", "reference body")

    with pytest.raises(GraphAgentFatalError) as exc_info:
        assemble_graph(compile_skill(tmp_path, cache=False), chat_model=CapturePromptChatModel())
    assert exc_info.value.payload.code == "[F-v3-resource-reference-path-invalid]"


def test_reference_reader_runs_once_during_assembly_not_each_agent_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class CountingReaderRuntime:
        def __init__(self, **kwargs: Any) -> None:
            self.phase_id = kwargs["phase_id"]

        def initial_state(self) -> dict[str, Any]:
            calls.append(self.phase_id)
            return {
                "data": {"inputs": {}, "phase_outputs": {}, "scratch": {}},
                "flow": {},
                "messages": [],
                "run_id": None,
            }

    monkeypatch.setattr(
        "graph_agent.core.graph_assembler.ReferenceReaderRuntime",
        CountingReaderRuntime,
    )
    _agent_skill(tmp_path)
    _write(tmp_path / "references" / "guide.md", "reference body")
    chat = CapturePromptChatModel()

    assemble_graph(compile_skill(tmp_path, cache=False), chat_model=chat)

    assert calls == ["main"]


# The real 60s timeout wrapper and 3000-token truncation limit are intentionally
# left to implementation review/e2e verification; these unit tests lock the
# fallback contract without sleeping or manufacturing token-counter assumptions.
def test_reader_output_invalid_falls_back_without_blocking_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class InvalidReaderRuntime:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def initial_state(self) -> dict[str, Any]:
            raise GraphAgentFatalError("[F-v3-reference-reader-output-invalid] missing markdown")

    monkeypatch.setattr(
        "graph_agent.core.graph_assembler.ReferenceReaderRuntime",
        InvalidReaderRuntime,
    )
    _agent_skill(tmp_path)
    _write(tmp_path / "references" / "guide.md", "raw reference for fallback")
    chat = CapturePromptChatModel()

    graph = assemble_graph(compile_skill(tmp_path, cache=False), chat_model=chat).graph
    result = graph.invoke(
        {"data": {"inputs": {"topic": "T"}}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert result["data"]["phase_outputs"]["main"] == {"answer": "ok"}
    assert "[F-v3-reference-reader-failed]" in chat.system_prompts[0]
