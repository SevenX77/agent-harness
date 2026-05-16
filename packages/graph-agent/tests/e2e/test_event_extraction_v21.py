from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_agent import assemble_graph, compile_skill
from graph_agent.cognitive.md2json import parse_finish_markdown
from graph_agent.cognitive.md_patch import FakeMdPatchClient
from graph_agent.core.graph_assembler import _is_terminal_phase
from graph_agent.cognitive.finish_task import build_finish_task_tool
from langchain_core.messages import AIMessage


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "skills" / "event-extraction"


class FakeEventExtractionChatModel:
    def __init__(self) -> None:
        self.messages_seen: list[list[Any]] = []

    def bind_tools(self, tools: list[Any]) -> "FakeEventExtractionChatModel":
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.messages_seen.append(messages)
        text = str(getattr(messages[-1], "content", "")) if messages else ""
        if "events_raw" in text:
            markdown = "## events_raw\n\nEVT-001 主角进入废墟\n\n## parsed_events\n\nEVT-001"
            call_id = "aggregate-finish"
        elif "reviewed_events" in text:
            markdown = "## reviewed_events\n\nEVT-001 reviewed\n\n## review_notes\n\nno changes"
            call_id = "review-finish"
        elif "event_timeline" in text:
            markdown = (
                "## event_timeline\n\n```json\n"
                + json.dumps(_event_timeline(), ensure_ascii=False)
                + "\n```"
            )
            call_id = "settings-finish"
        else:
            markdown = "## result\n\nok"
            call_id = "fallback-finish"
        return AIMessage(
            content="",
            tool_calls=[{"name": "finish_task", "args": {"markdown": markdown}, "id": call_id}],
        )


def _event_timeline() -> dict[str, Any]:
    return {
        "chapter_number": 1,
        "events": [
            {
                "event_id": "EVT-001",
                "title": "主角进入废墟",
                "type": "B",
                "paragraph_indices": [1],
                "summary": "主角进入废墟并听见广播",
                "location": "废墟",
                "time": "时间未明确",
            }
        ],
        "settings": [],
        "metadata": {"reviewed": True},
    }


def test_event_extraction_v21_e2e_fake_llm() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    graph = assemble_graph(compiled, chat_model=FakeEventExtractionChatModel()).graph

    result = graph.invoke(
        {
            "data": {
                "segmentation_result": {
                    "paragraphs": [
                        {
                            "index": 1,
                            "type": "B",
                            "content": "主角进入废墟并听见广播。",
                            "start_line": 1,
                            "end_line": 2,
                        }
                    ]
                },
                "chapter_number": 1,
                "prev_chapter_last_event": {},
            },
            "flow": {},
            "messages": [],
            "run_id": "event-extraction-v21-test",
        }
    )

    assert "段落1" in result["data"]["formatted_paragraphs"]
    assert result["data"]["settings"]["event_timeline"]["events"][0]["event_id"] == "EVT-001"
    assert result["flow"]["finish_task_result"]["ok"] is True


def test_event_extraction_v21_compile_and_assemble() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    assembled = assemble_graph(compiled)

    assert compiled.manifest.name == "event-extraction"
    assert [phase.id for phase in compiled.manifest.phases] == [
        "setup",
        "aggregate",
        "review",
        "settings",
    ]
    assert _is_terminal_phase("settings", compiled.manifest)
    assert assembled.graph is not None


def test_event_extraction_v21_md_patch_repairs_missing_fence() -> None:
    output_schema = {
        "type": "object",
        "properties": {
            "event_timeline": {
                "type": "object",
                "properties": {
                    "chapter_number": {"type": "integer"},
                    "events": {"type": "array"},
                },
                "required": ["chapter_number", "events"],
            }
        },
        "required": ["event_timeline"],
    }
    malformed = "## event_timeline\n\n```json\n" + json.dumps(_event_timeline(), ensure_ascii=False)
    repaired = malformed + "\n```"
    patcher = FakeMdPatchClient([repaired])
    tool = build_finish_task_tool(output_schema, parse_finish_markdown, patcher=patcher)

    result = tool.invoke({"markdown": malformed})

    assert result["ok"] is True
    assert result["repaired"] is True
    assert result["attempts"] == 1
    assert result["data"]["event_timeline"]["events"][0]["event_id"] == "EVT-001"
    assert len(patcher.calls) == 1
