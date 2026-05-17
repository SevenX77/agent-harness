from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_agent import assemble_graph, compile_skill
from graph_agent.core.manifest import SubgraphNodeAST
from langchain_core.messages import AIMessage

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "skills" / "examples" / "subgraph-sample" / "story-deconstruction"


class FakeStoryDeconstructionChatModel:
    def __init__(self) -> None:
        self.messages_seen: list[list[Any]] = []
        self.text_segmentation_calls = 0

    def bind_tools(self, tools: list[Any]) -> FakeStoryDeconstructionChatModel:
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.messages_seen.append(messages)
        text = str(getattr(messages[-1], "content", "")) if messages else ""
        if "segmentation_result" in text:
            markdown = (
                "## segmentation_result\n\n```json\n"
                + json.dumps(_segmentation_result(), ensure_ascii=False)
                + "\n```"
            )
            call_id = "segmentation-review-finish"
        elif "raw_segmentation" in text:
            markdown = "## raw_segmentation\n\n- 段落1 B 主角进入废墟"
            call_id = "segmentation-segment-finish"
        elif "events_raw" in text:
            markdown = "## events_raw\n\nEVT-001 主角进入废墟\n\n## parsed_events\n\nEVT-001"
            call_id = "event-aggregate-finish"
        elif "reviewed_events" in text:
            markdown = "## reviewed_events\n\nEVT-001 reviewed\n\n## review_notes\n\nno changes"
            call_id = "event-review-finish"
        elif "event_timeline" in text:
            markdown = (
                "## event_timeline\n\n```json\n"
                + json.dumps(_event_timeline(), ensure_ascii=False)
                + "\n```"
            )
            call_id = "event-settings-finish"
        elif "entity_registry" in text:
            markdown = (
                '## entity_registry\n\n{"CHR_001": "陈野"}\n\n'
                "## character_changes\n\n陈野: enters batch"
            )
            call_id = "batch-entity-finish"
        elif "tension_results" in text:
            markdown = (
                "## tension_results\n\nlow\n\n"
                "## system_results\n\nnone\n\n"
                "## prop_results\n\nnone\n\n"
                "## arc_results\n\nstarted\n\n"
                "## foreshadowing_results\n\nnone\n\n"
                "## spatiotemporal_results\n\nchapter start"
            )
            call_id = "batch-parallel-finish"
        elif "continuity_warnings" in text:
            markdown = "## continuity_warnings\n\n[]\n\n## continuity_summary\n\nno conflicts"
            call_id = "batch-continuity-finish"
        elif "climax_ranking" in text:
            markdown = (
                "## climax_ranking\n\nEVT-001: 8\n\n"
                "## foreshadowing_closure\n\nnone\n\n"
                "## character_ranking\n\n陈野: protagonist"
            )
            call_id = "global-analysis-finish"
        elif "retroactive_corrections" in text:
            markdown = (
                "## retroactive_corrections\n\n[]\n\n"
                "## corrected_event_stream\n\n"
                + json.dumps(
                    [{"event_id": "EVT-001", "summary": "陈野进入废墟"}], ensure_ascii=False
                )
            )
            call_id = "global-retroactive-finish"
        else:
            markdown = "## result\n\nok"
            call_id = "fallback-finish"
        return AIMessage(
            content="",
            tool_calls=[{"name": "finish_task", "args": {"markdown": markdown}, "id": call_id}],
        )


def _segmentation_result() -> dict[str, Any]:
    return {
        "chapter_number": 1,
        "total_paragraphs": 1,
        "paragraphs": [
            {
                "index": 1,
                "type": "B",
                "content": "主角进入废墟。",
                "start_line": 1,
                "end_line": 1,
            }
        ],
    }


def _event_timeline() -> dict[str, Any]:
    return {
        "chapter_number": 1,
        "events": [
            {
                "event_id": "EVT-001",
                "title": "主角进入废墟",
                "type": "B",
                "paragraph_indices": [1],
                "summary": "主角进入废墟",
                "location": "废墟",
                "time": "时间未明确",
            }
        ],
        "settings": [],
    }


def test_subgraph_sample_v21_e2e_fake_llm_smoke() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    assembled = assemble_graph(compiled, chat_model=FakeStoryDeconstructionChatModel())

    assert assembled.graph is not None
    assert assembled.phase_ids == [
        "segmentation",
        "event_extraction",
        "batch_analysis",
        "global_synthesis",
    ]


def test_subgraph_sample_v21_compile_topology_and_subgraph_refs() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    assembled = assemble_graph(compiled)

    assert compiled.manifest.name == "story-deconstruction-subgraph"
    assert [phase.id for phase in compiled.manifest.phases] == [
        "segmentation",
        "event_extraction",
        "batch_analysis",
        "global_synthesis",
    ]
    assert [phase.depends_on for phase in compiled.manifest.phases] == [
        [],
        ["segmentation"],
        ["event_extraction"],
        ["batch_analysis"],
    ]
    refs = {
        node.phase_name: node.ast.sub_skill_ref
        for node in compiled.nodes
        if isinstance(node.ast, SubgraphNodeAST)
    }
    assert refs == {
        "segmentation": "../../../../../text-segmentation",
        "event_extraction": "../../../../../event-extraction",
        "batch_analysis": "../../../../../batch-analysis",
        "global_synthesis": "../../../../../global-synthesis",
    }
    for node in compiled.nodes:
        assert isinstance(node.ast, SubgraphNodeAST)
        assert (node.path.parent / node.ast.sub_skill_ref).resolve().is_dir()
    assert assembled.graph is not None
