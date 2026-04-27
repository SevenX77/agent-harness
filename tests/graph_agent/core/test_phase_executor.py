"""Tests for PhaseExecutor (D-7.2).

Progressive coverage — methods are added as the extraction migrates phase
by phase. Step 4.1 covers ``execute_code_only_phase`` (the simplest node);
subsequent steps will add coverage for validation and llm phases.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from graph_agent.callbacks.base import Callback
from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.state import WorkflowState
from graph_agent.core.types import Phase


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
    context: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> WorkflowState:
    return {
        "context": dict(context or {}),
        "messages": [],
        "current_phase": "",
        "retry_counts": {},
        "metrics": dict(metrics or {}),
    }


def _capture_execute_llm_phase(
    monkeypatch: Any,
    phase: Phase,
) -> dict[str, Any]:
    from graph_agent.core import phase_executor as phase_executor_module

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
        phase_executor_module,
        "create_custom_middlewares",
        fake_create_custom_middlewares,
    )
    monkeypatch.setattr(phase_executor_module, "create_agent", fake_create_agent)

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
        state_in = _make_state(context={"foo": 1})

        executor.execute_code_only_phase(phase, state_in)

        assert state_in["context"] == {"foo": 1}
        assert state_in["current_phase"] == ""

    def test_on_phase_start_receives_name_and_context_snapshot(self):
        cb = _RecordingCallback()
        executor = PhaseExecutor([cb])
        phase = Phase(name="prep", requires_llm=False)
        state_in = _make_state(context={"k": "v"})

        executor.execute_code_only_phase(phase, state_in)

        assert cb.starts == [("prep", {"k": "v"})]

    def test_tools_run_in_order_string_result_sets_last_output(self):
        calls: list[str] = []

        def tool_a(ctx: dict[str, Any]) -> str:
            calls.append("a")
            return "a_out"

        def tool_b(ctx: dict[str, Any]) -> str:
            calls.append("b")
            return "b_out"

        phase = Phase(name="prep", requires_llm=False, tools=[tool_a, tool_b])
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        assert calls == ["a", "b"]
        # Last string return wins.
        assert state_out["context"]["_last_output"] == "b_out"

    def test_non_string_tool_result_does_not_set_last_output(self):
        def tool_none(ctx: dict[str, Any]) -> None:
            return None

        def tool_dict(ctx: dict[str, Any]) -> dict[str, Any]:
            return {"ignored": True}

        phase = Phase(name="prep", requires_llm=False, tools=[tool_none, tool_dict])  # type: ignore[list-item]
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        assert "_last_output" not in state_out["context"]

    def test_retry_feedback_popped_after_tools_run(self):
        captured: list[dict[str, Any]] = []

        def tool(ctx: dict[str, Any]) -> None:
            captured.append(dict(ctx))

        phase = Phase(name="prep", requires_llm=False, tools=[tool])  # type: ignore[list-item]
        executor = PhaseExecutor([])
        state_in = _make_state(context={"_retry_feedback": ["fix me"]})
        state_out = executor.execute_code_only_phase(phase, state_in)

        # Tool saw the retry feedback ...
        assert captured[0].get("_retry_feedback") == ["fix me"]
        # ... but the output state has it popped.
        assert "_retry_feedback" not in state_out["context"]

    def test_current_phase_set_on_output_state(self):
        phase = Phase(name="prep", requires_llm=False)
        executor = PhaseExecutor([])
        state_out = executor.execute_code_only_phase(phase, _make_state())

        assert state_out["current_phase"] == "prep"

    def test_on_phase_end_fires_after_current_phase_set(self):
        cb = _RecordingCallback()
        phase = Phase(name="prep", requires_llm=False)
        executor = PhaseExecutor([cb])
        executor.execute_code_only_phase(phase, _make_state(metrics={"tokens": 42}))

        assert len(cb.ends) == 1
        name, ctx_snap, metrics_snap = cb.ends[0]
        assert name == "prep"
        assert metrics_snap == {"tokens": 42}


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
        assert getattr(agent_model, "_wrapped") is captured["resolver_model"]


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
        phase = Phase(name="llm", max_iterations=1, max_nudges=0)
        phase.context_access = context_access  # type: ignore[attr-defined]

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

    def test_context_access_prompt_fallback_mounts_tools(self, monkeypatch) -> None:
        phase = Phase(
            name="llm",
            max_iterations=1,
            max_nudges=0,
            system_prompt=(
                "<context_access>\n"
                "  - read_artifact\n"
                "  - query_working_memory\n"
                "</context_access>"
            ),
        )

        captured = _capture_execute_llm_phase(monkeypatch, phase)
        tool_names = [
            getattr(tool, "name", getattr(tool, "__name__", ""))
            for tool in captured["create_agent_kwargs"]["tools"]
        ]

        assert "read_artifact" in tool_names
        assert "query_working_memory" in tool_names
