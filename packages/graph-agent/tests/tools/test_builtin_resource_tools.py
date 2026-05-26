from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError
from graph_agent.core.graph_assembler import assemble_graph
from langchain_core.messages import AIMessage


class CaptureToolsChatModel:
    def __init__(self) -> None:
        self.tools_by_name: dict[str, Any] = {}

    def bind_tools(self, tools: list[Any]) -> "CaptureToolsChatModel":
        self.tools_by_name = {tool.name: tool for tool in tools}
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
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


def _resource_skill(
    root: Path,
    *,
    reference_path: str = "references/r1.md",
    example_path: str = "examples/e2.md",
) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: resource-tools
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
    - id: R1
      path: {reference_path}
      summary: Primary reference
  examples:
    - id: E2
      path: {example_path}
      summary: Example document
---
<role>
Resource reader.
</role>
<goal>
Use @reference:R1 and @example:E2.
</goal>
<example id="E1">
Inline example.
</example>
""",
    )


def _bound_tools(root: Path, skill_resolver: object) -> dict[str, Any]:
    chat = CaptureToolsChatModel()
    compiled = compile_skill(root, cache=False, skill_resolver=skill_resolver)
    graph = assemble_graph(compiled, chat_model=chat, skill_resolver=skill_resolver).graph
    graph.invoke({"data": {"inputs": {"topic": "T"}}, "flow": {}, "messages": [], "run_id": "r1"})
    return chat.tools_by_name


def test_read_reference_returns_declared_current_phase_markdown(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _resource_skill(tmp_path)
    _write(tmp_path / "references" / "r1.md", "# Reference\n\nAllowed content.")
    _write(tmp_path / "examples" / "e2.md", "# Example\n\nAllowed example.")

    tools = _bound_tools(tmp_path, mock_skill_resolver)

    assert tools["read_reference"].invoke({"reference_id": "R1"}) == "# Reference\n\nAllowed content."


def test_read_example_returns_declared_document_example_markdown(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _resource_skill(tmp_path)
    _write(tmp_path / "references" / "r1.md", "# Reference\n")
    _write(tmp_path / "examples" / "e2.md", "# Example\n\nAllowed example.")

    tools = _bound_tools(tmp_path, mock_skill_resolver)

    assert tools["read_example"].invoke({"example_id": "E2"}) == "# Example\n\nAllowed example."


def test_read_reference_unknown_id_uses_runtime_not_found_code(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _resource_skill(tmp_path)
    _write(tmp_path / "references" / "r1.md", "# Reference\n")
    _write(tmp_path / "examples" / "e2.md", "# Example\n")
    tools = _bound_tools(tmp_path, mock_skill_resolver)

    with pytest.raises(GraphAgentFatalError) as exc_info:
        tools["read_reference"].invoke({"reference_id": "missing"})
    assert exc_info.value.payload.code == "[F-v3-resource-reference-not-found]"


def test_read_reference_unknown_id_does_not_touch_matching_external_file(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    outside = tmp_path.parent / "missing"
    outside.write_text("SHOULD_NOT_LEAK", encoding="utf-8")
    _resource_skill(tmp_path)
    _write(tmp_path / "references" / "r1.md", "# Reference\n")
    _write(tmp_path / "examples" / "e2.md", "# Example\n")
    tools = _bound_tools(tmp_path, mock_skill_resolver)

    with pytest.raises(GraphAgentFatalError) as exc:
        tools["read_reference"].invoke({"reference_id": "missing"})

    assert "SHOULD_NOT_LEAK" not in str(exc.value)
    assert exc.value.payload.code == "[F-v3-resource-reference-not-found]"


def test_read_example_unknown_id_uses_runtime_not_found_code(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _resource_skill(tmp_path)
    _write(tmp_path / "references" / "r1.md", "# Reference\n")
    _write(tmp_path / "examples" / "e2.md", "# Example\n")
    tools = _bound_tools(tmp_path, mock_skill_resolver)

    with pytest.raises(GraphAgentFatalError) as exc_info:
        tools["read_example"].invoke({"example_id": "missing"})
    assert exc_info.value.payload.code == "[F-v3-resource-example-not-found]"


def test_read_reference_path_escape_is_blocked_without_leaking_external_file(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    outside = tmp_path.parent / "secret-reference.md"
    outside.write_text("SHOULD_NOT_LEAK", encoding="utf-8")
    _resource_skill(tmp_path, reference_path="../secret-reference.md")
    _write(tmp_path / "examples" / "e2.md", "# Example\n")

    with pytest.raises(SkillLoadError) as exc:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    assert exc.value.payload.code == "[F-v3-resource-reference-path-invalid]"

    assert "SHOULD_NOT_LEAK" not in str(exc.value)


def test_read_reference_invalid_arguments_use_tool_argument_code(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _resource_skill(tmp_path)
    _write(tmp_path / "references" / "r1.md", "# Reference\n")
    _write(tmp_path / "examples" / "e2.md", "# Example\n")
    tools = _bound_tools(tmp_path, mock_skill_resolver)

    with pytest.raises(GraphAgentFatalError) as exc_info:
        tools["read_reference"].invoke({"reference_id": 123})
    assert exc_info.value.payload.code == "[F-v3-tool-argument-invalid]"


def test_example_path_escape_is_blocked_without_leaking_external_file(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    outside = tmp_path.parent / "secret-example.md"
    outside.write_text("SHOULD_NOT_LEAK", encoding="utf-8")
    _resource_skill(tmp_path, example_path="../secret-example.md")
    _write(tmp_path / "references" / "r1.md", "# Reference\n")
    tools = _bound_tools(tmp_path, mock_skill_resolver)

    with pytest.raises(GraphAgentFatalError) as exc:
        tools["read_example"].invoke({"example_id": "E2"})
    assert exc.value.payload.code == "[F-v3-resource-example-path-invalid]"

    assert "SHOULD_NOT_LEAK" not in str(exc.value)
