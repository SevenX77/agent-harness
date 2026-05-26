from __future__ import annotations

import json
import re
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
    phase_entries = []
    for match in re.finditer(r'<phase id="([^"]+)" src="([^"]+)" depends_on="([^"]*)"', phases):
        deps = [dep for dep in re.split(r"[\s,]+", match.group(3).strip()) if dep]
        phase_entries.append((match.group(1), deps))
    phase_yaml = "\n".join(f"  - {phase_id}" for phase_id, _ in phase_entries)
    depended_on = {dep for _, deps in phase_entries for dep in deps}
    phase_body = "\n".join(
        '<phase depends_on="{deps}"{output}>{phase_id}</phase>'.format(
            deps=", ".join(deps) if deps else "input",
            output=" output" if phase_id not in depended_on else "",
            phase_id=phase_id,
        )
        for phase_id, deps in phase_entries
    )
    output_schema = outputs or {"type": "object", "properties": {}}
    output_yaml = json.dumps(output_schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: gamma2-reference
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    {output_yaml}
phases:
{phase_yaml}
---
{phase_body}
""",
    )


def _agent_with_reference(root: Path) -> None:
    _write(
        root / "phases" / "main" / "SKILL.md",
        """---
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


def test_reference_reader_runtime_is_invoked_with_sandbox(
    monkeypatch, tmp_path: Path, mock_skill_resolver: object
) -> None:
    seen: list[BlackboardState] = []

    class SpyReferenceReaderRuntime:
        def __init__(
            self,
            *,
            skill_id: str,
            phase_id: str,
            root: Path,
            references: list[dict[str, Any]] | None = None,
            max_output_tokens: int = 3000,
            language: str = "zh",
            timeout_s: int = 60,
        ) -> None:
            self.skill_id = skill_id
            self.phase_id = phase_id
            self.root = root
            self.references = references or []
            self.max_output_tokens = max_output_tokens
            self.language = language
            self.timeout_s = timeout_s

        def initial_state(self) -> BlackboardState:
            state: BlackboardState = {
                "data": {
                    "inputs": {
                        "skill_id": self.skill_id,
                        "phase_id": self.phase_id,
                        "references": self.references,
                        "max_output_tokens": self.max_output_tokens,
                        "language": self.language,
                        "timeout_s": self.timeout_s,
                    },
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

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    result = assemble_graph(
        compiled, chat_model=chat, skill_resolver=mock_skill_resolver
    ).graph.invoke(
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
                "inputs": {
                    "skill_id": "gamma2-reference",
                    "phase_id": "main",
                    "references": [
                        {
                            "id": "Guide",
                            "path": "references/guide.md",
                            "summary": "Guide text",
                        }
                    ],
                    "max_output_tokens": 3000,
                    "language": "zh",
                    "timeout_s": 60,
                },
                "phase_outputs": {},
                "scratch": {},
            },
            "flow": {"timeout_s": 60},
            "messages": [],
            "run_id": None,
        }
    ]
    assert "sandboxed guide" in chat.tool_results[0]
