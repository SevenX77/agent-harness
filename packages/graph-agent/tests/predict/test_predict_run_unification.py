from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from graph_agent.callbacks.events import PhaseEndEvent, PhaseStartEvent
from graph_agent.core import runner as runner_module
from graph_agent.core._predict_internal.strategy import HeuristicStubStrategy
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.io.run_layout import predicts_root, runs_root


class _DumpData:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeGraph:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.invoke_calls = 0

    def invoke(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.invoke_calls += 1
        return {"data": _DumpData(self._payload)}


class _FakeAssembler:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.graph = _FakeGraph(payload)


def _write_empty_v030_skill(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: test
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases: []
---
""",
        encoding="utf-8",
    )
    return root


def _compiled_with_outputs(output_schema: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        nodes=[],
        raw={
            "io": {
                "outputs": output_schema,
            },
        },
    )


def test_predict_reuses_run_v030_skill_dict_single_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_empty_v030_skill(tmp_path / "skill")
    calls: list[dict[str, Any]] = []

    def fake_run_v030_skill_dict(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"args": args, "kwargs": kwargs})
        callbacks = kwargs.get("callbacks") or []
        for callback in callbacks:
            callback.on_event(PhaseStartEvent(phase_name="draft", phase_execution_id="exec-1", context={}))
            callback.on_event(
                PhaseEndEvent(phase_name="draft", phase_execution_id="exec-1", context={"text": "hello"})
            )
        return {
            "run_id": kwargs.get("thread_id") or "predict-run",
            "context": {"text": "hello"},
            "metrics": {"wall_time_sec": 0.01},
            "trace_path": str(kwargs["workspace_dir"] / "runs" / "predict-run" / "trace.jsonl"),
            "run_dir": str(kwargs["workspace_dir"] / "runs" / "predict-run"),
            "wall_time_sec": 0.01,
        }

    monkeypatch.setattr(
        "graph_agent.core.compiler.compile_skill",
        lambda *_args, **_kwargs: SimpleNamespace(nodes=[], raw={}),
    )
    monkeypatch.setattr(runner_module, "_run_v030_skill_dict", fake_run_v030_skill_dict)

    result = runner_module.predict_skill(
        skill_root,
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
    )

    assert len(calls) == 1
    assert calls[0]["args"] == (skill_root,)
    assert calls[0]["kwargs"]["predict_context"] is not None
    assert result.source == "predict"
    assert result.context == {"text": "hello"}


def test_predict_context_threaded_to_assemble_graph(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_empty_v030_skill(tmp_path / "skill")
    received_predict_contexts: list[Any] = []

    monkeypatch.setattr(
        "graph_agent.core.compiler.compile_skill",
        lambda *_args, **_kwargs: SimpleNamespace(nodes=[], raw={}),
    )

    def fake_assemble_graph(*_args: Any, **kwargs: Any) -> _FakeAssembler:
        received_predict_contexts.append(kwargs.get("predict_context"))
        return _FakeAssembler({})

    monkeypatch.setattr("graph_agent.core.graph_assembler.assemble_graph", fake_assemble_graph)

    runner_module._run_v030_skill_dict(
        skill_root,
        workspace_dir=tmp_path / "workspace-run",
        run_root=runs_root(tmp_path / "workspace-run"),
        skill_resolver=mock_skill_resolver,
    )
    runner_module._run_v030_skill_dict(
        skill_root,
        workspace_dir=tmp_path / "workspace-predict",
        run_root=predicts_root(tmp_path / "workspace-predict"),
        skill_resolver=mock_skill_resolver,
        predict_context=runner_module.SDKPredictContext(HeuristicStubStrategy(), None),
    )

    assert received_predict_contexts[0] is None
    assert received_predict_contexts[1] is not None


def test_predict_root_output_schema_validated_like_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_empty_v030_skill(tmp_path / "skill")
    output_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string"},
        },
    }
    compiled = _compiled_with_outputs(output_schema)

    monkeypatch.setattr("graph_agent.core.compiler.compile_skill", lambda *_args, **_kwargs: compiled)
    monkeypatch.setattr(
        "graph_agent.core.graph_assembler.assemble_graph",
        lambda *_args, **_kwargs: _FakeAssembler({"other": "missing text"}),
    )

    with pytest.raises(GraphAgentFatalError) as run_exc:
        runner_module._run_v030_skill_dict(
            skill_root,
            workspace_dir=tmp_path / "workspace-run",
            run_root=runs_root(tmp_path / "workspace-run"),
            skill_resolver=mock_skill_resolver,
        )
    with pytest.raises(GraphAgentFatalError) as predict_exc:
        runner_module.predict_skill(
            skill_root,
            workspace_dir=tmp_path / "workspace-predict",
            skill_resolver=mock_skill_resolver,
        )

    assert predict_exc.value.payload is not None
    assert run_exc.value.payload is not None
    assert predict_exc.value.payload.code == run_exc.value.payload.code
    assert predict_exc.value.payload.field_path == run_exc.value.payload.field_path
    assert predict_exc.value.payload.code == "[F-v3-runtime-state-mapping-failed]"


def test_predict_wrapper_still_returns_path_diff_and_deadlock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_empty_v030_skill(tmp_path / "skill")

    def fake_strategy_from_param(_param: Any) -> HeuristicStubStrategy:
        strategy = HeuristicStubStrategy()
        strategy.expected_path = ["draft", "review"]  # type: ignore[attr-defined]
        return strategy

    def fake_run_v030_skill_dict(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        callbacks = kwargs.get("callbacks") or []
        for callback in callbacks:
            callback.on_event(PhaseStartEvent(phase_name="draft", phase_execution_id="exec-1", context={}))
            callback.on_event(
                PhaseEndEvent(phase_name="draft", phase_execution_id="exec-1", context={"text": "hello"})
            )
        return {
            "run_id": kwargs.get("thread_id") or "predict-run",
            "context": {"text": "hello"},
            "metrics": {"wall_time_sec": 0.01},
            "trace_path": str(kwargs["workspace_dir"] / "runs" / "predict-run" / "trace.jsonl"),
            "run_dir": str(kwargs["workspace_dir"] / "runs" / "predict-run"),
            "wall_time_sec": 0.01,
        }

    monkeypatch.setattr(
        "graph_agent.core._predict_internal.strategy.MockStrategy.from_param",
        fake_strategy_from_param,
    )
    monkeypatch.setattr(
        "graph_agent.core.compiler.compile_skill",
        lambda *_args, **_kwargs: SimpleNamespace(nodes=[], raw={}),
    )
    monkeypatch.setattr(runner_module, "_run_v030_skill_dict", fake_run_v030_skill_dict)

    result = runner_module.predict_skill(
        skill_root,
        workspace_dir=tmp_path / "workspace-path-diff",
        skill_resolver=mock_skill_resolver,
    )

    assert result.path_diff is not None
    assert result.path_diff.expected_path == ["draft", "review"]
    assert result.path_diff.actual_path == ["draft"]
    assert result.path_diff.missing == ["review"]
    assert result.success is False

    def fake_deadlocking_run_v030_skill_dict(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        callbacks = kwargs.get("callbacks") or []
        for callback in callbacks:
            for _ in range(11):
                callback.on_event(PhaseStartEvent(phase_name="loop", phase_execution_id="exec-1", context={}))
                callback.on_event(
                    PhaseEndEvent(phase_name="loop", phase_execution_id="exec-1", context={"text": "hello"})
                )
        return {
            "run_id": kwargs.get("thread_id") or "predict-run",
            "context": {"text": "hello"},
            "metrics": {"wall_time_sec": 0.01},
            "trace_path": str(kwargs["workspace_dir"] / "runs" / "predict-run" / "trace.jsonl"),
            "run_dir": str(kwargs["workspace_dir"] / "runs" / "predict-run"),
            "wall_time_sec": 0.01,
        }

    monkeypatch.setattr(runner_module, "_run_v030_skill_dict", fake_deadlocking_run_v030_skill_dict)

    with pytest.raises(runner_module.PredictDeadlockError):
        runner_module.predict_skill(
            skill_root,
            workspace_dir=tmp_path / "workspace-deadlock",
            skill_resolver=mock_skill_resolver,
        )
