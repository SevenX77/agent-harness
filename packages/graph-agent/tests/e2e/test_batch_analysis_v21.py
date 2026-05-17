from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent import assemble_graph, compile_skill
from graph_agent.runtime.state import shallow_dict_merge
from langchain_core.messages import AIMessage

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "skills" / "batch-analysis"


class FakeBatchAnalysisChatModel:
    def __init__(self) -> None:
        self.bound_tool_names: list[str] = []
        self.messages_seen: list[list[Any]] = []

    def bind_tools(self, tools: list[Any]) -> FakeBatchAnalysisChatModel:
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
    assembled = assemble_graph(compiled, chat_model=FakeBatchAnalysisChatModel())

    assert assembled.graph is not None
    assert set(assembled.edges) >= {
        ("prepare", "entity_and_characters"),
        ("prepare", "parallel_analysis"),
        ("prepare", "continuity"),
        ("entity_and_characters", "assemble"),
        ("parallel_analysis", "assemble"),
        ("continuity", "assemble"),
    }


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


def test_batch_analysis_v21_reference_fanout_topology() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    assembled = assemble_graph(compiled, chat_model=FakeBatchAnalysisChatModel())

    depends_on = {phase.id: phase.depends_on for phase in compiled.manifest.phases}

    assert depends_on == {
        "prepare": [],
        "entity_and_characters": ["prepare"],
        "parallel_analysis": ["prepare"],
        "continuity": ["prepare"],
        "assemble": ["entity_and_characters", "parallel_analysis", "continuity"],
    }
    assert set(assembled.edges) >= {
        ("prepare", "entity_and_characters"),
        ("prepare", "parallel_analysis"),
        ("prepare", "continuity"),
        ("entity_and_characters", "assemble"),
        ("parallel_analysis", "assemble"),
        ("continuity", "assemble"),
    }

    merged = shallow_dict_merge(
        {"entity_and_characters": {"entity_registry": {"CHR_001": "陈野"}}},
        {"parallel_analysis": {"tension_results": "low"}},
    )
    merged = shallow_dict_merge(
        merged,
        {"continuity": {"continuity_summary": "no conflicts"}},
    )

    assert set(merged) == {"entity_and_characters", "parallel_analysis", "continuity"}
