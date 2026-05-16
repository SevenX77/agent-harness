from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent import assemble_graph, compile_skill
from langchain_core.messages import AIMessage


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "skills" / "product-manual"


class FakeProductManualChatModel:
    def __init__(self) -> None:
        self.messages_seen: list[list[Any]] = []

    def bind_tools(self, tools: list[Any]) -> "FakeProductManualChatModel":
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.messages_seen.append(messages)
        text = str(getattr(messages[-1], "content", "")) if messages else ""
        if "## highlights" in text:
            markdown = (
                "## highlights\n\n"
                "- 轻量机身，适合通勤携带\n"
                "- 全天续航，减少充电焦虑\n"
                "- 高亮屏幕，户外也能清晰查看"
            )
            call_id = "highlights-finish"
        elif "## scenarios" in text:
            markdown = (
                "## scenarios\n\n"
                "1. 通勤路上查看日程和消息。\n"
                "2. 户外旅行时导航和拍照。\n"
                "3. 会议间隙快速记录灵感。"
            )
            call_id = "scenarios-finish"
        else:
            markdown = (
                "## final_manual\n\n"
                "# Aurora Go 产品说明书\n\n"
                "Aurora Go 是一款面向通勤和轻旅行用户的便携设备。"
                "它以轻量机身、全天续航和高亮屏幕帮助用户在移动场景中稳定完成记录、导航和沟通。"
            )
            call_id = "manual-finish"
        return AIMessage(
            content="",
            tool_calls=[{"name": "finish_task", "args": {"markdown": markdown}, "id": call_id}],
        )


def test_product_manual_v21_e2e_fake_llm() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    graph = assemble_graph(compiled, chat_model=FakeProductManualChatModel()).graph

    result = graph.invoke(
        {
            "data": {
                "product_specs": {
                    "name": "Aurora Go",
                    "weight": "180g",
                    "battery": "18h",
                    "screen": "1200 nits",
                }
            },
            "flow": {},
            "messages": [],
            "run_id": "product-manual-v21-test",
        }
    )

    assert "轻量机身" in result["data"]["extract_highlights"]["highlights"]
    assert "通勤路上" in result["data"]["write_scenarios"]["scenarios"]
    assert "Aurora Go" in result["data"]["synthesize_report"]["final_manual"]
    assert result["flow"]["finish_task_result"]["ok"] is True


def test_product_manual_v21_compile_and_assemble() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    assembled = assemble_graph(compiled)

    assert compiled.manifest.name == "product-manual"
    assert [phase.id for phase in compiled.manifest.phases] == [
        "extract_highlights",
        "write_scenarios",
        "synthesize_report",
    ]
    assert compiled.raw["io"]["outputs"]["required"] == ["final_manual"]
    assert "final_manual" in compiled.raw["io"]["outputs"]["properties"]
    assert assembled.graph is not None
