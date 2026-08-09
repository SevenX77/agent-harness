"""Unit tests for the CallbackEvent Pydantic union (Task 3.4)."""

import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from graph_agent.callbacks.events import (  # noqa: E402
    SCHEMA_VERSION,
    AgentLoopIterationEvent,
    AmbiguityReportEvent,
    ArtifactSavedEvent,
    CallbackEvent,
    CompactionEvent,
    DeadEndPrunedEvent,
    FinishTaskEvent,
    HeartbeatEvent,
    InternalErrorEvent,
    InterruptedEvent,
    LLMCallEvent,
    LLMFallbackEvent,
    ModelResolvedEvent,
    NudgeEvent,
    ParallelMapGroupEndedEvent,
    ParallelMapGroupStartedEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    PromptCapturedEvent,
    ResumedEvent,
    RetryEvent,
    RetryExhaustedEvent,
    RunEndedEvent,
    RunStartedEvent,
    ThreadCleanedUpEvent,
    ToolCallEvent,
    ToolCallStartedEvent,
    ValidationFailEvent,
    ValidationPassEvent,
    WorkingMemoryUpdateEvent,
)

_ALL_EVENT_CLASSES = [
    PhaseStartEvent,
    PhaseEndEvent,
    LLMCallEvent,
    ToolCallEvent,
    ToolCallStartedEvent,
    ValidationFailEvent,
    RetryEvent,
    FinishTaskEvent,
    NudgeEvent,
    WorkingMemoryUpdateEvent,
    DeadEndPrunedEvent,
    CompactionEvent,
    AmbiguityReportEvent,
    PromptCapturedEvent,
    LLMFallbackEvent,
    # Tier 1 Commit A — core lifecycle
    RunStartedEvent,
    RunEndedEvent,
    ValidationPassEvent,
    RetryExhaustedEvent,
    InternalErrorEvent,
    # Tier 1 Commit B — data + proxy enhancement
    ModelResolvedEvent,
    ArtifactSavedEvent,
    # Tier 1 Commit C — concurrency boundary (subgraph events removed
    # in MVP-0 B1, 2026-04-28)
    ParallelMapGroupStartedEvent,
    ParallelMapGroupEndedEvent,
    # Tier 1 Commit D — heartbeat
    HeartbeatEvent,
    ThreadCleanedUpEvent,
    # Tier 2 — HITL sync
    InterruptedEvent,
    ResumedEvent,
    # Tier 2 — agent loop visibility
    AgentLoopIterationEvent,
]


_MIN_CTOR: dict[type, dict] = {
    PhaseStartEvent: {"phase_name": "p"},
    PhaseEndEvent: {"phase_name": "p"},
    LLMCallEvent: {"phase_name": "p", "input_tokens": 10, "output_tokens": 5},
    ToolCallStartedEvent: {"tool_call_id": "c1", "phase_name": "p", "tool_name": "t"},
    ToolCallEvent: {"tool_call_id": "c1", "phase_name": "p", "tool_name": "t", "result": "r"},
    ValidationFailEvent: {"phase_name": "p", "retry_count": 1},
    RetryEvent: {"phase_name": "p", "target_phase": "p2"},
    FinishTaskEvent: {"phase_name": "p", "reasoning": "done"},
    NudgeEvent: {"phase_name": "p", "nudge_count": 1},
    WorkingMemoryUpdateEvent: {"phase_name": "p", "content_length": 100},
    DeadEndPrunedEvent: {"phase_name": "p", "summary": "s"},
    CompactionEvent: {"phase_name": "p", "removed_pairs": 3},
    AmbiguityReportEvent: {
        "phase_name": "p",
        "ambiguity_type": "a",
        "question": "q",
        "decision": "d",
    },
    PromptCapturedEvent: {"phase_name": "p"},
    LLMFallbackEvent: {
        "phase_name": "p",
        "from_provider": "a",
        "to_provider": "b",
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
    ValidationPassEvent: {"phase_name": "p", "retry_count": 0},
    RetryExhaustedEvent: {"phase_name": "p", "max_retries": 3},
    InternalErrorEvent: {
        "entry_point": "run",
        "error_type": "RuntimeError",
        "error_message": "boom",
        "traceback": "Traceback: ...",
    },
    # Tier 1 Commit B — data + proxy enhancement
    ModelResolvedEvent: {
        "phase_name": "p",
        "tier": "balanced",
        "role_name": "balanced",
    },
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
    HeartbeatEvent: {"elapsed_seconds": 30.0},
    ThreadCleanedUpEvent: {"thread_id": "t1"},
    # Tier 2 — HITL sync
    InterruptedEvent: {"phase_name": "p", "thread_id": "t1"},
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
        ev = PromptCapturedEvent(phase_name="p")
        assert ev.loop_index == 1

    def test_prompt_captured_loop_index_rejects_zero(self) -> None:
        for loop_index in (0, -1):
            with pytest.raises(ValidationError):
                PromptCapturedEvent(phase_name="p", loop_index=loop_index)

    def test_llm_fallback_captures_provider_transition(self) -> None:
        ev = LLMFallbackEvent(
            phase_name="analyse",
            from_provider="deepseek-reasoner",
            to_provider="deepseek-chat",
            reason="HTTP 429 rate limit",
        )
        assert ev.from_provider != ev.to_provider
        assert "rate" in ev.reason.lower()
