from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent import assemble_graph, compile_skill
from langchain_core.messages import AIMessage


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "skills" / "hello-world"


class FakeHelloWorldChatModel:
    def __init__(self) -> None:
        self.bound_tools: list[Any] = []
        self.react_turns = 0

    def bind_tools(self, tools: list[Any]) -> "FakeHelloWorldChatModel":
        self.bound_tools = tools
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.react_turns += 1
        if self.react_turns == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "generate_greeting",
                        "args": {"user_name": "Ada"},
                        "id": "greet-tool",
                    }
                ],
            )
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {"markdown": "## greeting\n\nHello, Ada!"},
                    "id": "greet-finish",
                }
            ],
        )


def test_hello_world_v21_e2e_tool_then_finish_task() -> None:
    chat = FakeHelloWorldChatModel()
    compiled = compile_skill(SKILL_ROOT, cache=False)
    graph = assemble_graph(compiled, chat_model=chat).graph

    result = graph.invoke(
        {
            "data": {"user_name": "Ada"},
            "flow": {},
            "messages": [],
            "run_id": "hello-world-v21-test",
        }
    )

    assert result["data"]["greet"]["greeting"] == "Hello, Ada!"
    assert result["flow"]["finish_task_result"]["ok"] is True
    assert any(tool.name == "generate_greeting" for tool in chat.bound_tools)


def test_hello_world_v21_compile_and_assemble() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    assembled = assemble_graph(compiled)

    assert compiled.manifest.name == "hello-world"
    assert [phase.id for phase in compiled.manifest.phases] == ["greet"]
    assert compiled.nodes[0].mode == "skill"
    assert [tool.name for tool in compiled.tools.for_phase("greet")] == ["generate_greeting"]
    assert assembled.graph is not None
