from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from graph_agent import assemble_graph, compile_skill


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "skills" / "batch-analysis"


class FakeBatchAnalysisChatModel:
    def __init__(self) -> None:
        self.bound_tool_names: list[str] = []
        self.messages_seen: list[list[Any]] = []

    def bind_tools(self, tools: list[Any]) -> "FakeBatchAnalysisChatModel":
        self.bound_tool_names = [tool.name for tool in tools]
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.messages_seen.append(messages)
        text = str(getattr(messages[-1], "content", "")) if messages else ""
        if "entity_registry" in text:
            markdown = (
                "## entity_registry\n\n{\"CHR_001\": \"陈野\"}\n\n"
                "## character_changes\n\n陈野: enters batch"
            )
            call_id = "entity-finish"
        elif "tension_results" in text:
            markdown = (
                "## tension_results\n\nlow\n\n"
                "## system_results\n\nnone\n\n"
                "## prop_results\n\nnone\n\n"
                "## arc_results\n\nstarted\n\n"
                "## foreshadowing_results\n\nnone\n\n"
                "## spatiotemporal_results\n\nchapter start"
            )
            call_id = "parallel-finish"
        elif "continuity_warnings" in text:
            markdown = "## continuity_warnings\n\n[]\n\n## continuity_summary\n\nno conflicts"
            call_id = "continuity-finish"
        else:
            markdown = "## result\n\nok"
            call_id = "fallback-finish"
        return AIMessage(
            content="",
            tool_calls=[{"name": "finish_task", "args": {"markdown": markdown}, "id": call_id}],
        )


def test_batch_analysis_v21_e2e_fake_llm_star_topology() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    graph = assemble_graph(compiled, chat_model=FakeBatchAnalysisChatModel()).graph

    result = graph.invoke(
        {
            "data": {
                "batch_events": [{"event_id": "E1", "summary": "陈野进入废墟"}],
                "accumulated_context": {"character_latest_states": {}},
                "para_text_lookup": {},
                "dynamic_dimensions": ["tension", "props"],
                "chapter_range": [1, 10],
            },
            "flow": {},
            "messages": [],
            "run_id": "batch-analysis-v21-test",
        }
    )

    assert result["data"]["batch_event_count"] == 1
    assert result["data"]["entity_and_characters"]["entity_registry"]
    assert result["data"]["parallel_analysis"]["tension_results"] == "low"
    assert result["data"]["continuity"]["continuity_summary"] == "no conflicts"
    assert result["data"]["batch_result"]["entity_and_characters"]
    assert result["data"]["updated_accumulated"]["last_batch_result"]


def test_batch_analysis_v21_compile_and_assemble() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    assembled = assemble_graph(compiled)

    assert compiled.manifest.name == "batch-analysis"
    assert [phase.id for phase in compiled.manifest.phases] == [
        "prepare",
        "entity_and_characters",
        "parallel_analysis",
        "continuity",
        "assemble",
    ]
    assert assembled.graph is not None
