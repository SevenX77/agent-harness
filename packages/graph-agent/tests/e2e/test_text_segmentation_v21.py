from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_agent import assemble_graph, compile_skill
from langchain_core.messages import AIMessage

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "skills" / "text-segmentation"


class FakeTextSegmentationChatModel:
    def __init__(self) -> None:
        self.bound_tools: list[Any] = []
        self.messages_seen: list[list[Any]] = []
        self._calls = [
            {
                "name": "finish_task",
                "args": {
                    "markdown": (
                        "## raw_segmentation\n\n- **段落1（B类-事件）**：主角进入废墟 行号：1-2"
                    )
                },
                "id": "segment-finish",
            },
            {
                "name": "finish_task",
                "args": {
                    "markdown": (
                        "## segmentation_result\n\n"
                        "```json\n"
                        + json.dumps(
                            {
                                "chapter_number": 1,
                                "total_paragraphs": 1,
                                "paragraphs": [
                                    {
                                        "index": 1,
                                        "type": "B",
                                        "content": "主角进入废墟。\n他听见远处的广播声。",
                                        "start_line": 1,
                                        "end_line": 2,
                                        "description": "主角进入废墟并听见广播",
                                    }
                                ],
                                "metadata": {"reviewed": True},
                            },
                            ensure_ascii=False,
                        )
                        + "\n```"
                    )
                },
                "id": "review-finish",
            },
        ]

    def bind_tools(self, tools: list[Any]) -> FakeTextSegmentationChatModel:
        self.bound_tools = tools
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.messages_seen.append(messages)
        return AIMessage(content="", tool_calls=[self._calls.pop(0)])


def test_text_segmentation_v21_e2e_fake_llm() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    chat_model = FakeTextSegmentationChatModel()
    graph = assemble_graph(compiled, chat_model=chat_model).graph

    result = graph.invoke(
        {
            "data": {
                "chapter_content": "主角进入废墟。\n他听见远处的广播声。",
                "chapter_number": 1,
            },
            "flow": {},
            "messages": [],
            "run_id": "text-segmentation-v21-test",
        }
    )

    assert result["data"]["chapter_with_line_numbers"].startswith("   1| 主角进入废墟。")
    segmentation = result["data"]["review"]["segmentation_result"]
    assert segmentation["chapter_number"] == 1
    assert segmentation["paragraphs"][0]["type"] == "B"
    assert result["flow"]["finish_task_result"]["ok"] is True
    assert any(
        "finish_task" in message.content for turn in chat_model.messages_seen for message in turn
    )


def test_text_segmentation_v21_compile_and_assemble() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    assembled = assemble_graph(compiled)

    assert compiled.manifest.name == "text-segmentation"
    assert [phase.id for phase in compiled.manifest.phases] == ["setup", "segment", "review"]
    assert {node.phase_name for node in compiled.nodes} == {"setup", "segment", "review"}
    assert assembled.graph is not None
