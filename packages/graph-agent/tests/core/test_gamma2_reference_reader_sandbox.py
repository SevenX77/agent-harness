from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.runtime.state import BlackboardState
from langchain_core.messages import AIMessage


class FakeToolChatModel:
    def __init__(self, calls: list[list[dict[str, Any]]]) -> None:
        self.calls = calls
        self.tool_results: list[str] = []

    def bind_tools(self, tools: list[Any]) -> FakeToolChatModel:
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        for message in messages:
            if getattr(message, "name", None) == "read_reference":
                self.tool_results.append(str(message.content))
        tool_calls = self.calls.pop(0) if self.calls else []
        return AIMessage(content="", tool_calls=tool_calls)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base(root: Path, phases: str, outputs: dict[str, object] | None = None) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "2.1"
name: gamma2-reference
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
"""
        + phases,
    )
    _write(root / "io" / "inputs.json", "{}\n")
    _write(root / "io" / "outputs.json", json.dumps(outputs or {}, ensure_ascii=False))


def _agent_with_reference(root: Path) -> None:
    _write(
        root / "phases" / "main" / "SKILL.md",
        """---
mode: agent
role: reader
goal: read reference
references:
  - id: Guide
    path: references/guide.md
    summary: Guide text
---
<role>
reader
</role>
<goal>
read reference
</goal>
""",
    )
    _write(root / "references" / "guide.md", "sandboxed guide")


def test_reference_reader_runtime_is_invoked_with_sandbox(monkeypatch, tmp_path: Path) -> None:
    seen: list[BlackboardState] = []

    class SpyReferenceReaderRuntime:
        def __init__(
            self,
            *,
            skill_id: str,
            phase_id: str,
            root: Path,
            timeout_s: int = 60,
        ) -> None:
            self.skill_id = skill_id
            self.phase_id = phase_id
            self.root = root
            self.timeout_s = timeout_s

        def initial_state(self) -> BlackboardState:
            state: BlackboardState = {
                "data": {
                    "inputs": {"skill_id": self.skill_id, "phase_id": self.phase_id},
                    "phase_outputs": {},
                    "scratch": {},
                },
                "flow": {"timeout_s": self.timeout_s},
                "messages": [],
                "run_id": None,
            }
            seen.append(state)
            return state

    monkeypatch.setattr(
        "graph_agent.core.graph_assembler.ReferenceReaderRuntime",
        SpyReferenceReaderRuntime,
    )
    _base(
        tmp_path,
        '<phase id="main" src="phases/main" depends_on="" />\n',
        {"type": "object", "properties": {"answer": {"type": "string"}}},
    )
    _agent_with_reference(tmp_path)
    chat = FakeToolChatModel(
        [
            [{"name": "read_reference", "args": {"reference_id": "Guide"}, "id": "read-1"}],
            [{"name": "finish_task", "args": {"markdown": "## answer\n\nok"}, "id": "done"}],
        ]
    )

    result = assemble_graph(compile_skill(tmp_path, cache=False), chat_model=chat).graph.invoke(
        {
            "data": {
                "inputs": {"topic": "visible"},
                "phase_outputs": {"parent": {"secret": "no"}},
                "scratch": {"secret": "no"},
            },
            "flow": {"timeout_s": 5},
            "messages": ["parent-message"],
            "run_id": "parent-run",
        }
    )

    assert result["data"]["phase_outputs"]["main"] == {"answer": "ok"}
    assert seen == [
        {
            "data": {
                "inputs": {"skill_id": "gamma2-reference", "phase_id": "main"},
                "phase_outputs": {},
                "scratch": {},
            },
            "flow": {"timeout_s": 60},
            "messages": [],
            "run_id": None,
        }
    ]
    assert "sandboxed guide" in chat.tool_results[0]
