"""Tests for PhaseExecutor (D-7.2).

Progressive coverage — methods are added as the extraction migrates phase
by phase. Step 4.1 covers ``execute_code_only_phase`` (the simplest node);
subsequent steps will add coverage for validation and llm phases.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from graph_agent.callbacks.base import Callback
from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.core.types import Phase
from pydantic import BaseModel, Field


class _RecordingCallback(Callback):
    """Records every `on_phase_start` / `on_phase_end` invocation."""

    def __init__(self) -> None:
        self.starts: list[tuple[str, dict[str, Any]]] = []
        self.ends: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def on_phase_start(self, phase_name: str, context_snapshot: dict[str, Any]) -> None:
        self.starts.append((phase_name, context_snapshot))

    def on_phase_end(
        self,
        phase_name: str,
        context_snapshot: dict[str, Any],
        metrics_snapshot: dict[str, Any],
    ) -> None:
        self.ends.append((phase_name, context_snapshot, metrics_snapshot))


def _make_state(
    data: dict[str, Any] | None = None,
    flow: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> WorkflowState:
    flow_fields = dict(flow or {})
    if metrics is not None:
        flow_fields["metrics"] = dict(metrics)
    return {
        "data": BusinessData(**dict(data or {})),
        "flow": FrameworkState(**flow_fields),
        "messages": [],
    }


def _capture_execute_llm_phase(
    monkeypatch: Any,
    phase: Phase,
) -> dict[str, Any]:
    # Phase 3 M6 (PHASE3_DESIGN.md §2): execute_llm_phase delegates to
    # ``LLMPhaseNode`` which now owns the ``create_custom_middlewares``
    # + ``create_agent`` imports. Monkeypatch the new module instead of
    # the legacy phase_executor module.
    from graph_agent.core.phase_nodes import llm_phase_node as llm_phase_node_module

    class _ResolvedModel:
        name = "fake-model"
        profile = {"max_input_tokens": 100_000}
        _llm_type = "fake-chat"

        def _get_ls_params(self) -> dict[str, str]:
            return {"ls_provider": "fake"}

    class _Resolver:
        def __init__(self) -> None:
            self.model = _ResolvedModel()

        def resolve(self, *_args: Any, **_kwargs: Any) -> _ResolvedModel:
            return self.model

    class _Agent:
        def invoke(self, *_args: Any, **_kwargs: Any) -> dict[str, list[Any]]:
            return {"messages": []}

    captured: dict[str, Any] = {}

    def fake_create_custom_middlewares(**kwargs: Any) -> list[Any]:
        captured["middleware_kwargs"] = kwargs
        return []

    def fake_create_agent(**kwargs: Any) -> _Agent:
        captured["create_agent_kwargs"] = kwargs
        return _Agent()

    monkeypatch.setattr(
        llm_phase_node_module,
        "create_custom_middlewares",
        fake_create_custom_middlewares,
    )
    monkeypatch.setattr(llm_phase_node_module, "create_agent", fake_create_agent)

    resolver = _Resolver()
    executor = PhaseExecutor(
        [],
        resolver=resolver,
        save_compaction_sidecar=lambda **_kwargs: "sidecar",
    )

    executor.execute_llm_phase(phase, _make_state())

    captured["resolver_model"] = resolver.model
    return captured


class TestExecuteCodeOnlyPhase:
    def test_input_state_not_mutated(self):
        cb = _RecordingCallback()
        executor = PhaseExecutor([cb])
        phase = Phase(name="prep", requires_llm=False)
        state_in = _make_state(data={"foo": 1})

        executor.execute_code_only_phase(phase, state_in)

        assert state_in["data"].model_dump() == {"foo": 1}
        assert state_in["flow"].current_phase == ""

    def test_on_phase_start_receives_name_and_context_snapshot(self):
        cb = _RecordingCallback()
        executor = PhaseExecutor([cb])
        phase = Phase(name="prep", requires_llm=False)
        state_in = _make_state(data={"k": "v"})

        executor.execute_code_only_phase(phase, state_in)

        assert cb.starts == [("prep", {"k": "v"})]

    def test_tools_run_in_order_string_result_sets_last_output(self):
        calls: list[str] = []

        def tool_a(data: BusinessData) -> str:
            calls.append("a")
            return "a_out"

        def tool_b(data: BusinessData) -> str:
            calls.append("b")
            return "b_out"

        phase = Phase(name="prep", requires_llm=False, tools=[tool_a, tool_b])
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        assert calls == ["a", "b"]
        # Last string return wins.
        assert state_out["flow"].last_output == "b_out"

    def test_non_string_tool_result_does_not_set_last_output(self):
        def tool_none(data: BusinessData) -> None:
            return None

        def tool_dict(data: BusinessData) -> dict[str, Any]:
            return {"ignored": True}

        phase = Phase(name="prep", requires_llm=False, tools=[tool_none, tool_dict])  # type: ignore[list-item]
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        assert state_out["flow"].last_output is None

    def test_retry_feedback_cleared_after_tools_run(self):
        captured: list[dict[str, Any]] = []

        def tool(data: BusinessData) -> None:
            captured.append(data.model_dump())

        phase = Phase(name="prep", requires_llm=False, tools=[tool])  # type: ignore[list-item]
        executor = PhaseExecutor([])
        state_in = _make_state(flow={"retry_feedback": ["fix me"]})
        state_out = executor.execute_code_only_phase(phase, state_in)

        assert "_retry_feedback" not in captured[0]
        assert state_out["flow"].retry_feedback is None

    def test_current_phase_set_on_output_state(self):
        phase = Phase(name="prep", requires_llm=False)
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        assert state_out["flow"].current_phase == "prep"

    def test_on_phase_end_fires_after_current_phase_set(self):
        cb = _RecordingCallback()
        phase = Phase(name="prep", requires_llm=False)
        executor = PhaseExecutor([cb])
        executor.execute_code_only_phase(phase, _make_state(metrics={"tokens": 42}))

        assert len(cb.ends) == 1
        name, ctx_snap, metrics_snap = cb.ends[0]
        assert name == "prep"
        assert metrics_snap == {"tokens": 42}


class TestExecuteCodeOnlyPhaseDictMergePhase2A3:
    """Phase 2 A3 contract: code-only tool dict returns merge into BusinessData
    (no longer silently dropped); ``_``-prefixed keys raise RuntimeError;
    ``output_schema`` triggers Pydantic validation. See PHASE2_DESIGN.md §4.2.
    """

    def test_dict_result_merges_into_business_data(self):
        def tool_dict(data: BusinessData) -> dict[str, Any]:
            return {"title": "Opening", "score": 7}

        phase = Phase(name="prep", requires_llm=False, tools=[tool_dict])  # type: ignore[list-item]
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state(data={"x": 1}))

        merged = state_out["data"].model_dump()
        # Pre-existing field preserved + tool dict fields merged.
        assert merged["x"] == 1
        assert merged["title"] == "Opening"
        assert merged["score"] == 7
        # Dict path leaves last_output untouched (str path is what sets it).
        assert state_out["flow"].last_output is None

    def test_dict_result_with_reserved_key_raises_runtime_error(self):
        def tool_dict(data: BusinessData) -> dict[str, Any]:
            return {"good": 1, "_metrics": {"tokens": 99}, "_phase_internal": True}

        phase = Phase(name="prep", requires_llm=False, tools=[tool_dict])  # type: ignore[list-item]
        executor = PhaseExecutor([])

        with pytest.raises(RuntimeError) as exc_info:
            executor.execute_code_only_phase(phase, _make_state())

        message = str(exc_info.value)
        assert "Phase 2 A3" in message
        # Both reserved keys must surface in the diagnostic, sorted.
        assert "_metrics" in message
        assert "_phase_internal" in message
        assert "tool_dict" in message  # function name included for debuggability
        assert "prep" in message  # phase name included

    def test_dict_result_with_output_schema_runs_pydantic_validate(self):
        class CodePhaseOutput(BaseModel):
            title: str = Field(min_length=1)
            score: int = Field(ge=0, le=10)

        def tool_dict(data: BusinessData) -> dict[str, Any]:
            return {"title": "Opening", "score": 7}

        phase = Phase(
            name="prep",
            requires_llm=False,
            tools=[tool_dict],  # type: ignore[list-item]
            output_schema=CodePhaseOutput,
        )
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        merged = state_out["data"].model_dump()
        assert merged["title"] == "Opening"
        assert merged["score"] == 7

    def test_dict_result_failing_output_schema_raises_validation(self):
        class CodePhaseOutput(BaseModel):
            title: str = Field(min_length=1)
            score: int = Field(ge=0, le=10)

        def tool_bad(data: BusinessData) -> dict[str, Any]:
            return {"title": "", "score": 99}  # both fields violate constraints

        phase = Phase(
            name="prep",
            requires_llm=False,
            tools=[tool_bad],  # type: ignore[list-item]
            output_schema=CodePhaseOutput,
        )
        executor = PhaseExecutor([])

        # Pydantic raises ValidationError; the executor lets it propagate so
        # callers can see the precise field-level diagnostic instead of a
        # silent truncation of the offending dict.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            executor.execute_code_only_phase(phase, _make_state())

    def test_dict_with_output_schema_and_reserved_key_raises(self, caplog):
        """PHASE2_DESIGN.md §4.4 must-pass case (a1 v1 NO_RAISE probe).

        With ``output_schema`` configured, Pydantic's default ``extra='ignore'``
        would silently drop ``_metrics`` if validation ran first. The A3 v2
        contract orders the reserved-key check BEFORE validation so the
        injection raises ``RuntimeError`` and never reaches the schema.
        """

        class CodeOut(BaseModel):
            # extra defaults to "ignore" — exactly the trap §4.4 calls out.
            title: str

        def tool_attack(data: BusinessData) -> dict[str, Any]:
            return {"title": "ok", "_metrics": {"latency": 100}}

        phase = Phase(
            name="prep",
            requires_llm=False,
            tools=[tool_attack],  # type: ignore[list-item]
            output_schema=CodeOut,
        )
        executor = PhaseExecutor([])

        with (
            caplog.at_level(logging.ERROR, logger="graph_agent.core.phase_nodes.code_phase_node"),
            pytest.raises(RuntimeError) as exc_info,
        ):
            executor.execute_code_only_phase(phase, _make_state())

        message = str(exc_info.value)
        assert "Phase 2 A3" in message
        assert "_metrics" in message, (
            "reserved-key diagnostic must surface '_metrics' even when "
            "output_schema is set — Pydantic extra=ignore must not eat it."
        )
        assert "tool_attack" in message
        assert "prep" in message

        # The error log must record the reject decision before any
        # ``code_only_dict_validate`` event — i.e. validate never ran.
        decisions = [rec.message for rec in caplog.records]
        reject_idx = next(
            (
                i
                for i, m in enumerate(decisions)
                if "code_only_dict_merge" in m and "decision=reject" in m
            ),
            None,
        )
        validate_idx = next(
            (i for i, m in enumerate(decisions) if "code_only_dict_validate" in m),
            None,
        )
        assert reject_idx is not None, "reject decision must be logged"
        assert validate_idx is None, (
            "code_only_dict_validate must NOT log when reserved-key check "
            "rejects the raw dict — validate is supposed to be skipped."
        )

    def test_non_dict_non_str_result_is_no_op(self):
        # ``None`` / ``int`` / ``list`` returns must not touch state — only
        # ``str`` (legacy ``last_output``) and ``dict`` (A3) have explicit
        # contracts. Other types are a no-op so existing tools that mutate
        # ``BusinessData`` directly remain unaffected.
        def tool_none(data: BusinessData) -> None:
            return None

        def tool_int(data: BusinessData) -> int:
            return 42

        def tool_list(data: BusinessData) -> list[int]:
            return [1, 2, 3]

        phase = Phase(
            name="prep",
            requires_llm=False,
            tools=[tool_none, tool_int, tool_list],  # type: ignore[list-item]
        )
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state(data={"x": 1}))

        assert state_out["data"].model_dump() == {"x": 1}
        assert state_out["flow"].last_output is None

    def test_dict_merge_logs_decision_for_observability(self, caplog):
        def tool_dict(data: BusinessData) -> dict[str, Any]:
            return {"title": "Opening"}

        phase = Phase(name="prep", requires_llm=False, tools=[tool_dict])  # type: ignore[list-item]
        executor = PhaseExecutor([])

        with caplog.at_level(logging.INFO, logger="graph_agent.core.phase_nodes.code_phase_node"):
            executor.execute_code_only_phase(phase, _make_state())

        merge_log = next(
            (rec for rec in caplog.records if "code_only_dict_merge" in rec.message),
            None,
        )
        assert merge_log is not None, "merge decision must emit an info log"
        assert "decision=apply" in merge_log.message
        assert "tool=tool_dict" in merge_log.message

    def test_reserved_key_rejection_logs_error(self, caplog):
        def tool_dict(data: BusinessData) -> dict[str, Any]:
            return {"_secret": "x"}

        phase = Phase(name="prep", requires_llm=False, tools=[tool_dict])  # type: ignore[list-item]
        executor = PhaseExecutor([])

        with (
            caplog.at_level(logging.ERROR, logger="graph_agent.core.phase_nodes.code_phase_node"),
            pytest.raises(RuntimeError),
        ):
            executor.execute_code_only_phase(phase, _make_state())

        reject_log = next(
            (rec for rec in caplog.records if "code_only_dict_merge" in rec.message),
            None,
        )
        assert reject_log is not None, "rejection must emit an error log"
        assert "decision=reject" in reject_log.message
        assert "_secret" in reject_log.message


class TestPhaseExecutorIoHoistT7Bis:
    """MVP-2 T7-bis: ``Phase.io_specs`` drives ``IOManager.resolve_hoist``
    at phase exit and routes ``HoistResult.io_errors`` into
    ``state['flow'].io_errors`` via ``StateManager.update_framework``.

    Each test exercises one of the three phase entry points (code-only,
    validation pass, LLM finish) plus the no-op fallback when
    ``io_specs`` is empty (legacy phases must not be affected).
    """

    def test_code_only_phase_no_io_specs_is_no_op(self):
        phase = Phase(name="prep", requires_llm=False)

        def tool(data: BusinessData) -> None:
            return None

        phase.tools = [tool]  # type: ignore[list-item]
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state(data={"x": 1}))

        # Empty io_specs → BusinessData unchanged + no io_errors.
        assert state_out["data"].model_dump() == {"x": 1}
        assert state_out["flow"].io_errors == []

    def test_code_only_phase_hoist_routes_business_data(self):
        from graph_agent.core.io_manager import IODef

        phase = Phase(
            name="prep",
            requires_llm=False,
            io_specs=[IODef(source_field="title", target_field="story_title")],
        )

        def tool(data: BusinessData) -> None:
            data["title"] = "Opening"
            return None

        phase.tools = [tool]  # type: ignore[list-item]
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        # io_specs source ``title`` lands in target ``story_title``.
        assert state_out["data"].model_dump()["story_title"] == "Opening"
        assert state_out["flow"].io_errors == []

    def test_code_only_phase_hoist_records_missing_required_field(self):
        from graph_agent.core.io_manager import IODef

        phase = Phase(
            name="prep",
            requires_llm=False,
            io_specs=[IODef(source_field="absent", target_field="story_title")],
        )
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        # Missing required source field surfaces as an io_error in flow.
        assert any(
            "absent" in err and "missing" in err.lower() for err in state_out["flow"].io_errors
        )

    def test_code_only_phase_hoist_appends_to_existing_io_errors(self):
        from graph_agent.core.io_manager import IODef

        phase = Phase(
            name="prep",
            requires_llm=False,
            io_specs=[IODef(source_field="absent", target_field="story_title")],
        )
        executor = PhaseExecutor([])
        state_in = _make_state(flow={"io_errors": ["pre-existing"]})
        state_out = executor.execute_code_only_phase(phase, state_in)

        # ``StateManager.update_framework`` appends, doesn't replace.
        assert state_out["flow"].io_errors[0] == "pre-existing"
        assert any("absent" in err for err in state_out["flow"].io_errors[1:])


class TestExecuteLLMPhaseMiddlewareIntegration:
    def test_passes_resolved_model_to_summarization_middleware(self, monkeypatch):
        phase = Phase(name="llm", max_iterations=1, max_nudges=0)

        captured = _capture_execute_llm_phase(monkeypatch, phase)

        middleware_kwargs = captured["middleware_kwargs"]
        agent_model = captured["create_agent_kwargs"]["model"]
        assert middleware_kwargs["loop_detection"] is True
        assert middleware_kwargs["summarization"] is True
        assert middleware_kwargs["summarization_model"] is agent_model
        assert middleware_kwargs["summarization_trigger_fraction"] == 0.8
        assert middleware_kwargs["summarization_keep_messages"] == 20
        assert middleware_kwargs["clarification"] is True
        assert agent_model._wrapped is captured["resolver_model"]


class TestExecuteLLMPhaseSchemaRoutingPhase3M7:
    """Phase 3 M7 (PHASE3_DESIGN.md §3.4): execute_llm_phase mounts a
    single-responsibility middleware pair for every LLM phase. Strategy
    C terminated the dual-system split — the legacy parallel pipeline
    and its ``DynamicSchemaDef`` / schema-less fallbacks are gone, so
    every phase now flows through
    ``[ProtocolValidationMiddleware, CognitiveFlowMiddleware]`` regardless
    of how its ``output_schema`` was declared.
    """

    def _middleware_class_names(self, captured: dict[str, Any]) -> list[str]:
        return [type(mw).__name__ for mw in captured["create_agent_kwargs"]["middleware"]]

    def test_static_pydantic_schema_routes_to_new_pipeline(self, monkeypatch, caplog):
        class _LiveSchema(BaseModel):
            title: str
            score: int

        phase = Phase(
            name="segment",
            max_iterations=1,
            max_nudges=0,
            output_schema=_LiveSchema,
        )

        with caplog.at_level(logging.INFO, logger="graph_agent.core.phase_nodes.llm_phase_node"):
            captured = _capture_execute_llm_phase(monkeypatch, phase)

        names = self._middleware_class_names(captured)
        assert "ProtocolValidationMiddleware" in names
        assert "CognitiveFlowMiddleware" in names

        decision_log = next(
            (
                rec.message
                for rec in caplog.records
                if "middleware_pipeline" in rec.message and "phase=segment" in rec.message
            ),
            None,
        )
        assert decision_log is not None
        assert "decision=static_schema" in decision_log
        assert "schema=_LiveSchema" in decision_log

    def test_static_schema_object_routes_to_new_pipeline(self, monkeypatch):
        from graph_agent.core.schema_engine import SchemaEngine

        engine = SchemaEngine()
        schema_obj = engine.parse_from_md("title: str\nscore: int")

        phase = Phase(
            name="segment_obj",
            max_iterations=1,
            max_nudges=0,
            output_schema=schema_obj,  # type: ignore[arg-type]
        )

        captured = _capture_execute_llm_phase(monkeypatch, phase)

        names = self._middleware_class_names(captured)
        assert "ProtocolValidationMiddleware" in names
        assert "CognitiveFlowMiddleware" in names

    def test_no_legacy_validation_middleware_anywhere_in_pipeline(self, monkeypatch):
        """PHASE3_DESIGN.md §3.6 ship-standard: the legacy parallel
        pipeline must be physically gone. Even when assembling the
        middleware list against an arbitrary phase shape, no class
        with the literal name ``ValidationMiddleware`` should appear.
        """

        class _LiveSchema(BaseModel):
            title: str

        phase = Phase(
            name="x",
            max_iterations=1,
            max_nudges=0,
            output_schema=_LiveSchema,
        )

        captured = _capture_execute_llm_phase(monkeypatch, phase)
        names = self._middleware_class_names(captured)
        assert "ValidationMiddleware" not in names


class TestExecuteLLMPhaseClarificationIntegration:
    def test_mounts_ask_clarification_tool_by_default(self, monkeypatch) -> None:
        phase = Phase(name="llm", max_iterations=1, max_nudges=0)

        captured = _capture_execute_llm_phase(monkeypatch, phase)
        tool_names = [
            getattr(tool, "name", getattr(tool, "__name__", ""))
            for tool in captured["create_agent_kwargs"]["tools"]
        ]

        assert "ask_clarification" in tool_names


class TestExecuteLLMPhaseReadFileIntegration:
    def test_mounts_read_file_when_references_non_empty(
        self,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        phase = Phase(
            name="llm",
            max_iterations=1,
            max_nudges=0,
            references=["references/guide.md"],
            skill_base_dir=tmp_path,
        )

        captured = _capture_execute_llm_phase(monkeypatch, phase)
        tool_names = [
            getattr(tool, "name", getattr(tool, "__name__", ""))
            for tool in captured["create_agent_kwargs"]["tools"]
        ]

        assert "read_file" in tool_names

    def test_does_not_mount_read_file_when_references_empty(
        self,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        phase = Phase(
            name="llm",
            max_iterations=1,
            max_nudges=0,
            references=[],
            skill_base_dir=tmp_path,
        )

        captured = _capture_execute_llm_phase(monkeypatch, phase)
        tool_names = [
            getattr(tool, "name", getattr(tool, "__name__", ""))
            for tool in captured["create_agent_kwargs"]["tools"]
        ]

        assert "read_file" not in tool_names

    def test_missing_skill_base_dir_warns_and_skips_read_file(
        self,
        monkeypatch,
        caplog,
    ) -> None:
        caplog.set_level(logging.WARNING)
        phase = Phase(
            name="llm",
            max_iterations=1,
            max_nudges=0,
            references=["references/guide.md"],
            skill_base_dir=None,
        )

        captured = _capture_execute_llm_phase(monkeypatch, phase)
        tool_names = [
            getattr(tool, "name", getattr(tool, "__name__", ""))
            for tool in captured["create_agent_kwargs"]["tools"]
        ]

        assert "read_file" not in tool_names
        assert "read_file tool not mounted" in caplog.text


class TestExecuteLLMPhaseContextAccessIntegration:
    def _tool_names_for_context_access(
        self,
        monkeypatch,
        context_access: list[str],
    ) -> list[str]:
        phase = Phase(
            name="llm",
            max_iterations=1,
            max_nudges=0,
            context_access=context_access,
        )

        captured = _capture_execute_llm_phase(monkeypatch, phase)
        return [
            getattr(tool, "name", getattr(tool, "__name__", ""))
            for tool in captured["create_agent_kwargs"]["tools"]
        ]

    def test_context_access_empty_mounts_no_context_tools(self, monkeypatch) -> None:
        tool_names = self._tool_names_for_context_access(monkeypatch, [])

        assert "query_working_memory" not in tool_names
        assert "read_artifact" not in tool_names

    def test_context_access_working_memory_mounts_only_query_tool(
        self,
        monkeypatch,
    ) -> None:
        tool_names = self._tool_names_for_context_access(
            monkeypatch,
            ["working_memory"],
        )

        assert "query_working_memory" in tool_names
        assert "read_artifact" not in tool_names

    def test_context_access_artifact_mounts_only_read_artifact(
        self,
        monkeypatch,
    ) -> None:
        tool_names = self._tool_names_for_context_access(monkeypatch, ["artifact"])

        assert "read_artifact" in tool_names
        assert "query_working_memory" not in tool_names

    def test_context_access_both_mounts_both_tools(self, monkeypatch) -> None:
        tool_names = self._tool_names_for_context_access(
            monkeypatch,
            ["artifact", "working_memory"],
        )

        assert "read_artifact" in tool_names
        assert "query_working_memory" in tool_names
