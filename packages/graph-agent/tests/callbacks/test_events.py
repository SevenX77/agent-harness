"""Unit tests for the CallbackEvent Pydantic union (Task 3.4)."""

import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from graph_agent.callbacks.events import (  # noqa: E402
    SCHEMA_VERSION,
    AgentLoopIterationEvent,
    ArtifactSavedEvent,
    CallbackEvent,
    CompactionEvent,
    DeadEndPrunedEvent,
    EdgeEndEvent,
    EdgeStartEvent,
    InterruptedEvent,
    LLMCallEvent,
    LLMDeltaEvent,
    LLMRouteDecisionEvent,
    NudgeEvent,
    ParallelMapGroupEndedEvent,
    ParallelMapGroupStartedEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    PromptCapturedEvent,
    ResumedEvent,
    RunEndedEvent,
    RunStartedEvent,
    ToolCallEvent,
    ToolCallStartedEvent,
    WorkingMemoryUpdateEvent,
)

_ALL_EVENT_CLASSES = [
    PhaseStartEvent,
    PhaseEndEvent,
    EdgeStartEvent,
    EdgeEndEvent,
    LLMCallEvent,
    LLMDeltaEvent,
    ToolCallEvent,
    ToolCallStartedEvent,
    NudgeEvent,
    WorkingMemoryUpdateEvent,
    DeadEndPrunedEvent,
    CompactionEvent,
    PromptCapturedEvent,
    LLMRouteDecisionEvent,
    # Tier 1 Commit A — core lifecycle
    RunStartedEvent,
    RunEndedEvent,
    # Tier 1 Commit B — data + proxy enhancement
    ArtifactSavedEvent,
    # Tier 1 Commit C — concurrency boundary (subgraph events removed
    # in MVP-0 B1, 2026-04-28)
    ParallelMapGroupStartedEvent,
    ParallelMapGroupEndedEvent,
    # Tier 2 — HITL sync
    InterruptedEvent,
    ResumedEvent,
    # Tier 2 — agent loop visibility
    AgentLoopIterationEvent,
]


_MIN_CTOR: dict[type, dict] = {
    PhaseStartEvent: {"phase_name": "p", "phase_execution_id": "exec-1"},
    PhaseEndEvent: {"phase_name": "p", "phase_execution_id": "exec-1", "status": "completed"},
    EdgeStartEvent: {
        "edge_transition_id": "t-1",
        "from_phases": ["a"],
        "from_phase_execution_ids": ["exec-a"],
        "to_phase": "b",
        "to_phase_execution_id": "exec-b",
    },
    EdgeEndEvent: {
        "edge_transition_id": "t-1",
        "from_phases": ["a"],
        "from_phase_execution_ids": ["exec-a"],
        "to_phase": "b",
        "to_phase_execution_id": "exec-b",
    },
    LLMCallEvent: {
        "phase_name": "p",
        "step_id": "step-1",
        "input_tokens": 10,
        "output_tokens": 5,
        "response_data": {"content": "ok"},
    },
    LLMDeltaEvent: {"phase_name": "p", "step_id": "step-1", "channel": "text"},
    ToolCallStartedEvent: {"tool_call_id": "c1", "phase_name": "p", "tool_name": "t"},
    ToolCallEvent: {"tool_call_id": "c1", "phase_name": "p", "tool_name": "t", "result": "r"},
    NudgeEvent: {"phase_name": "p", "nudge_count": 1},
    WorkingMemoryUpdateEvent: {"phase_name": "p", "content_length": 100},
    DeadEndPrunedEvent: {"phase_name": "p", "summary": "s"},
    CompactionEvent: {"phase_name": "p", "removed_message_count": 3},
    PromptCapturedEvent: {"phase_name": "p", "step_id": "step-1"},
    LLMRouteDecisionEvent: {
        "phase_name": "p",
        "decision": "fell_back",
        "reason": "r",
    },
    # Tier 1 Commit A — core lifecycle
    RunStartedEvent: {
        "run_id": "r1",
        "thread_id": "t1",
    },
    RunEndedEvent: {
        "run_id": "r1",
        "thread_id": "t1",
        "wall_time_seconds": 1.23,
    },
    # Tier 1 Commit B — data + proxy enhancement
    ArtifactSavedEvent: {
        "name": "x.json",
        "path": "/tmp/x.json",
        "size_bytes": 128,
    },
    # Tier 1 Commit C — concurrency boundary (subgraph events removed
    # in MVP-0 B1, 2026-04-28)
    ParallelMapGroupStartedEvent: {
        "group_key": "abc123",
        "skill_path": "skills/scene/SKILL.md",
        "item_count": 10,
        "max_concurrent": 3,
        "item_as": "scene",
    },
    ParallelMapGroupEndedEvent: {
        "group_key": "abc123",
        "succeeded": 9,
        "failed": 1,
        "wall_time_seconds": 12.3,
    },
    # Tier 2 — HITL sync
    InterruptedEvent: {"phase_name": "p", "thread_id": "t1", "reason": "awaiting_human"},
    ResumedEvent: {"thread_id": "t1", "human_input": "yes"},
    AgentLoopIterationEvent: {"phase_name": "p", "iteration": 1},
}


class TestSchemaInvariants:
    @pytest.mark.parametrize("cls", _ALL_EVENT_CLASSES)
    def test_every_class_stamps_schema_version_1_0(self, cls: type) -> None:
        ev = cls(**_MIN_CTOR[cls])
        assert ev.schema_version == SCHEMA_VERSION == "1.0"

    @pytest.mark.parametrize("cls", _ALL_EVENT_CLASSES)
    def test_every_class_fills_timestamp(self, cls: type) -> None:
        ev = cls(**_MIN_CTOR[cls])
        # default_factory should produce an ISO8601 timestamp ending in +00:00
        assert ev.timestamp
        assert "T" in ev.timestamp

    @pytest.mark.parametrize("cls", _ALL_EVENT_CLASSES)
    def test_every_class_forbids_extra_fields(self, cls: type) -> None:
        payload = {**_MIN_CTOR[cls], "unexpected_field": 42}
        with pytest.raises(ValidationError):
            cls(**payload)


class TestUnionDiscriminator:
    _ADAPTER = TypeAdapter(CallbackEvent)

    @pytest.mark.parametrize("cls", _ALL_EVENT_CLASSES)
    def test_round_trip_through_json(self, cls: type) -> None:
        ev = cls(**_MIN_CTOR[cls])
        json_payload = ev.model_dump_json()
        back = self._ADAPTER.validate_json(json_payload)
        assert isinstance(back, cls)
        assert back.model_dump() == ev.model_dump()

    def test_unknown_event_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._ADAPTER.validate_python(
                {
                    "event_type": "not_a_real_type",
                    "phase_name": "p",
                    "schema_version": "1.0",
                    "timestamp": "2026-04-23T00:00:00+00:00",
                }
            )


def test_resume_related_events_carry_checkpoint_identity() -> None:
    started = RunStartedEvent(
        run_id="run-1",
        thread_id="thread-1",
        is_resume=True,
        checkpoint_id="cp-1",
        checkpoint_ns="",
    )
    interrupted = InterruptedEvent(
        phase_name="review",
        thread_id="thread-1",
        reason="awaiting_human",
        checkpoint_id="cp-1",
        checkpoint_ns="",
        namespace="",
        ns="",
    )
    resumed = ResumedEvent(
        thread_id="thread-1",
        human_input="approved",
        resumed_from_phase="review",
        checkpoint_id="cp-1",
        checkpoint_ns="",
        namespace="",
        ns="",
    )

    assert started.checkpoint_id == "cp-1"
    assert interrupted.checkpoint_id == "cp-1"
    assert resumed.checkpoint_id == "cp-1"


class TestParallelMapGrouping:
    def test_sub_run_id_and_group_key_preserved(self) -> None:
        ev = PromptCapturedEvent(
            step_id="step-1",
            phase_name="p",
            sub_run_id="sub-42",
            group_key="pmap-xyz",
            template_source="writer.j2",
        )
        assert ev.sub_run_id == "sub-42"
        assert ev.group_key == "pmap-xyz"
        data = ev.model_dump()
        assert data["sub_run_id"] == "sub-42"
        assert data["group_key"] == "pmap-xyz"

    def test_default_grouping_fields_are_none(self) -> None:
        ev = ToolCallEvent(tool_call_id="c1", phase_name="p", tool_name="t", result="r")
        assert ev.sub_run_id is None
        assert ev.group_key is None


class TestNewEventShapes:
    def test_prompt_captured_captures_triple(self) -> None:
        ev = PromptCapturedEvent(
            phase_name="extract",
            step_id="step-1",
            llm_role="writer",
            resolved_model="claude-sonnet-4-6",
            template_source="prompts/writer.j2",
            variables={"scene": "intro"},
            resolved_prompt=[{"role": "system", "content": "hi"}],
        )
        assert ev.template_source == "prompts/writer.j2"
        assert ev.variables == {"scene": "intro"}
        assert ev.resolved_prompt[0]["role"] == "system"

    def test_prompt_captured_loop_index_default(self) -> None:
        ev = PromptCapturedEvent(phase_name="p", step_id="step-1")
        assert ev.loop_index == 1

    def test_prompt_captured_loop_index_rejects_zero(self) -> None:
        for loop_index in (0, -1):
            with pytest.raises(ValidationError):
                PromptCapturedEvent(phase_name="p", step_id="step-1", loop_index=loop_index)

    def test_a_route_decision_captures_the_provider_transition(self) -> None:
        ev = LLMRouteDecisionEvent(
            phase_name="analyse",
            decision="fell_back",
            route_id="deepseek-reasoner",
            next_route_id="deepseek-chat",
            reason="HTTP 429 rate limit",
        )
        assert ev.route_id != ev.next_route_id
        assert "rate" in ev.reason.lower()
