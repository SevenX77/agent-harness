"""Tests for MVP-3 T7 ProtocolValidationMiddleware."""

from __future__ import annotations

import pytest
from graph_agent.core.schema_engine import SchemaEngine, SchemaObject
from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    WorkflowState,
)
from graph_agent.middleware.protocol_validation import (
    ProtocolValidationError,
    ProtocolValidationMiddleware,
)


def _state(
    *,
    data: BusinessData | None = None,
    flow: FrameworkState | None = None,
) -> WorkflowState:
    return {
        "data": data if data is not None else BusinessData(),
        "flow": flow if flow is not None else FrameworkState(),
        "messages": [],
    }


class TestInit:
    def test_init_minimal(self) -> None:
        mw = ProtocolValidationMiddleware()

        assert mw._schema_engine is None
        assert mw._current_phase_schema is None
        assert mw._phase_name == "unknown"

    def test_init_records_phase_name_and_engine(self) -> None:
        engine = SchemaEngine()
        schema = SchemaObject(fields=(), required_fields=frozenset())

        mw = ProtocolValidationMiddleware(
            engine, schema, phase_name="segment"
        )

        assert mw._schema_engine is engine
        assert mw._current_phase_schema is schema
        assert mw._phase_name == "segment"

    def test_name_property_defaults_to_class(self) -> None:
        # AgentMiddleware.name defaults to class name; we don't override.
        assert ProtocolValidationMiddleware().name == "ProtocolValidationMiddleware"


class TestBeforeModel:
    def test_clean_state_returns_none(self) -> None:
        mw = ProtocolValidationMiddleware()
        state = _state(data=BusinessData(title="ok"), flow=FrameworkState())

        result = mw.before_model(state, runtime=None)  # type: ignore[arg-type]

        assert result is None

    def test_underscore_prefix_in_business_data_raises(self) -> None:
        mw = ProtocolValidationMiddleware(phase_name="segment")
        # ``BusinessData`` is ``extra='allow'`` but the protocol contract
        # forbids ``_``-prefixed keys; the middleware is the gate that
        # enforces it (Pydantic itself accepts the field at construction).
        # Build via model_validate so the underscore key actually lands.
        data = BusinessData.model_validate({"_sneaky": "framework leak"})
        state = _state(data=data)

        with pytest.raises(ProtocolValidationError) as exc:
            mw.before_model(state, runtime=None)  # type: ignore[arg-type]

        labels = [label for label, _ in exc.value.violations]
        assert "business_data_underscore_prefix" in labels

    def test_violation_message_includes_phase_name(self) -> None:
        mw = ProtocolValidationMiddleware(phase_name="my_phase")
        data = BusinessData.model_validate({"_x": 1})
        state = _state(data=data)

        with pytest.raises(ProtocolValidationError) as exc:
            mw.before_model(state, runtime=None)  # type: ignore[arg-type]

        assert "my_phase" in str(exc.value)

    def test_no_pydantic_state_yields_no_violation(self) -> None:
        """A LangGraph default ``AgentState`` lacks ``data``/``flow`` keys —
        the middleware tolerates that so it can be installed in
        non-WorkflowState pipelines without crashing every step."""
        mw = ProtocolValidationMiddleware()

        result = mw.before_model({"messages": []}, runtime=None)  # type: ignore[arg-type]

        assert result is None


class TestAfterModel:
    def test_clean_state_returns_none(self) -> None:
        mw = ProtocolValidationMiddleware()
        state = _state(data=BusinessData(title="ok"))

        result = mw.after_model(state, runtime=None)  # type: ignore[arg-type]

        assert result is None

    def test_underscore_prefix_after_model_raises(self) -> None:
        mw = ProtocolValidationMiddleware(phase_name="segment")
        data = BusinessData.model_validate({"_finish_task_result": {"x": 1}})
        state = _state(data=data)

        with pytest.raises(ProtocolValidationError):
            mw.after_model(state, runtime=None)  # type: ignore[arg-type]


class TestSchemaEngineIntegration:
    def test_after_model_runs_schema_engine_when_configured(self) -> None:
        engine = SchemaEngine()
        # Schema demanding a required ``title: str`` field.
        schema = engine.parse_from_md("title: str\nscore: int")

        mw = ProtocolValidationMiddleware(engine, schema, phase_name="segment")

        # BusinessData missing the required ``score`` field — schema_engine
        # validation must reject it on the after_model boundary.
        state = _state(data=BusinessData(title="ok"))

        with pytest.raises(ProtocolValidationError) as exc:
            mw.after_model(state, runtime=None)  # type: ignore[arg-type]

        labels = [label for label, _ in exc.value.violations]
        assert "schema_engine_validate" in labels

    def test_before_model_skips_schema_engine_check(self) -> None:
        """``before_model`` validates the state contracts but does not run
        the schema engine — the schema describes the *output*, and the
        LLM has not produced the next turn yet at this boundary."""
        engine = SchemaEngine()
        schema = engine.parse_from_md("title: str\nscore: int")

        mw = ProtocolValidationMiddleware(engine, schema, phase_name="segment")
        # Missing ``score`` — would fail in after_model, must pass here.
        state = _state(data=BusinessData(title="ok"))

        assert mw.before_model(state, runtime=None) is None  # type: ignore[arg-type]

    def test_schema_engine_pass_keeps_no_violation(self) -> None:
        engine = SchemaEngine()
        schema = engine.parse_from_md("title: str")

        mw = ProtocolValidationMiddleware(engine, schema)
        state = _state(data=BusinessData(title="ok"))

        assert mw.after_model(state, runtime=None) is None  # type: ignore[arg-type]


class TestFrameworkStateRoundTrip:
    def test_round_trip_passes_for_default_flow(self) -> None:
        mw = ProtocolValidationMiddleware()
        state = _state(flow=FrameworkState(thread_id="t-1", run_id="r-1"))

        assert mw.before_model(state, runtime=None) is None  # type: ignore[arg-type]

    def test_violations_payload_attached_to_exception(self) -> None:
        """The structured ``violations`` list is callers' contract for
        producing actionable feedback (LLM retry / operator log)."""
        mw = ProtocolValidationMiddleware(phase_name="x")
        data = BusinessData.model_validate({"_a": 1, "_b": 2})
        state = _state(data=data)

        with pytest.raises(ProtocolValidationError) as exc:
            mw.before_model(state, runtime=None)  # type: ignore[arg-type]

        assert isinstance(exc.value.violations, list)
        assert len(exc.value.violations) >= 1
        for label, detail in exc.value.violations:
            assert isinstance(label, str)
            assert isinstance(detail, str)
