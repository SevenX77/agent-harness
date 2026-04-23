"""Unit tests for the CallbackEvent Pydantic union (Task 3.4)."""
import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src" / "core"))

from graph_agent.callbacks.events import (  # noqa: E402
    SCHEMA_VERSION,
    AmbiguityReportEvent,
    CallbackEvent,
    CompactionEvent,
    DeadEndPrunedEvent,
    FinishTaskEvent,
    LLMCallEvent,
    LLMFallbackEvent,
    NudgeEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    PromptCapturedEvent,
    RetryEvent,
    ToolCallEvent,
    ValidationFailEvent,
    WorkingMemoryUpdateEvent,
)


_ALL_EVENT_CLASSES = [
    PhaseStartEvent,
    PhaseEndEvent,
    LLMCallEvent,
    ToolCallEvent,
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
]


_MIN_CTOR: dict[type, dict] = {
    PhaseStartEvent: {"phase_name": "p"},
    PhaseEndEvent: {"phase_name": "p"},
    LLMCallEvent: {"phase_name": "p", "input_tokens": 10, "output_tokens": 5},
    ToolCallEvent: {"phase_name": "p", "tool_name": "t", "result": "r"},
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
            self._ADAPTER.validate_python({
                "event_type": "not_a_real_type",
                "phase_name": "p",
                "schema_version": "1.0",
                "timestamp": "2026-04-23T00:00:00+00:00",
            })


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
        ev = ToolCallEvent(phase_name="p", tool_name="t", result="r")
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

    def test_llm_fallback_captures_provider_transition(self) -> None:
        ev = LLMFallbackEvent(
            phase_name="analyse",
            from_provider="deepseek-coder",
            to_provider="deepseek-chat",
            reason="HTTP 429 rate limit",
        )
        assert ev.from_provider != ev.to_provider
        assert "rate" in ev.reason.lower()
