from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from graph_agent import assemble_graph, compile_skill


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "skills" / "global-synthesis"


class FakeGlobalSynthesisChatModel:
    def __init__(self) -> None:
        self.messages_seen: list[list[Any]] = []

    def bind_tools(self, tools: list[Any]) -> "FakeGlobalSynthesisChatModel":
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.messages_seen.append(messages)
        text = str(getattr(messages[-1], "content", "")) if messages else ""
        if "climax_ranking" in text:
            markdown = (
                "## climax_ranking\n\nEVT-001: 8\n\n"
                "## foreshadowing_closure\n\nnone\n\n"
                "## character_ranking\n\n陈野: protagonist"
            )
            call_id = "global-finish"
        elif "retroactive_corrections" in text:
            markdown = (
                "## retroactive_corrections\n\n[]\n\n"
                "## corrected_event_stream\n\n"
                + json.dumps([{"event_id": "EVT-001", "summary": "陈野进入废墟"}], ensure_ascii=False)
            )
            call_id = "retroactive-finish"
        else:
            markdown = "## result\n\nok"
            call_id = "fallback-finish"
        return AIMessage(
            content="",
            tool_calls=[{"name": "finish_task", "args": {"markdown": markdown}, "id": call_id}],
        )


def test_global_synthesis_v21_e2e_fake_llm() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    graph = assemble_graph(compiled, chat_model=FakeGlobalSynthesisChatModel()).graph

    result = graph.invoke(
        {
            "data": {
                "batch_outputs": [
                    {
                        "batch_result": {
                            "events": [{"event_id": "EVT-001", "summary": "陈野进入废墟"}]
                        }
                    }
                ],
                "accumulated_context": {},
                "entity_registry": {"CHR_001": "陈野"},
            },
            "flow": {},
            "messages": [],
            "run_id": "global-synthesis-v21-test",
        }
    )

    assert result["data"]["global_analysis"]["climax_ranking"] == "EVT-001: 8"
    assert result["data"]["scenes"][0]["event_id"] == "EVT-001"
    assert result["data"]["story_framework"]["character_ranking"] == "陈野: protagonist"
    assert result["flow"]["finish_task_result"]["ok"] is True


def test_global_synthesis_v21_compile_and_assemble() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    assembled = assemble_graph(compiled)

    assert compiled.manifest.name == "global-synthesis"
    assert [phase.id for phase in compiled.manifest.phases] == [
        "global_analysis",
        "scene_assembly",
        "retroactive",
        "export",
    ]
    assert assembled.graph is not None


def test_global_synthesis_io_field_flow_consistency() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    inputs_schema = compiled.raw["io"]["inputs"]
    outputs_schema = compiled.raw["io"]["outputs"]
    phase_io = compiled.manifest.metadata["phase_io"]

    external_inputs = set(inputs_schema["properties"])
    declared_outputs = set(outputs_schema["properties"])
    produced: set[str] = set(external_inputs)

    phase_by_id = {phase.id: phase for phase in compiled.manifest.phases}
    for phase in compiled.manifest.phases:
        spec = phase_io[phase.id]
        assert set(spec["inputs"]).issubset(produced)
        produced.update(spec["outputs"])
        for downstream in compiled.manifest.phases:
            if phase.id in downstream.depends_on:
                downstream_inputs = set(phase_io[downstream.id]["inputs"])
                assert set(spec["outputs"]) & downstream_inputs
        assert phase_by_id[phase.id].id == phase.id

    for phase, spec in phase_io.items():
        assert set(spec["outputs"]).issubset(declared_outputs), phase
    assert "story_framework" in declared_outputs
