from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.services import predictor as predictor_module
from app.services import run_manager as run_manager_module
from app.services.predictor import (
    PredictArtifactError,
    PredictDeadlockError,
    PredictorService,
)
from graph_agent import PathDiff, PhaseRecord, RunResult
from graph_agent.callbacks.events import PhaseStartEvent, RunEndedEvent, RunStartedEvent


@pytest.fixture(autouse=True)
def _isolate_studio_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


def test_dispatch_predict_job_delegates_to_engine_predict_artifact_and_persists_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    import app.core.adapters.engine as engine_adapter_module

    mock_art_ref = {
        "artifact_id": "skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "compile",
        lambda *a, **k: mock_art_ref,
    )

    mock_result = RunResult(
        success=True,
        run_id="predict-run-777",
        skill_id="skill",
        context={"topic": "predict"},
        source="predict",
        phases=[
            PhaseRecord(
                phase_name="draft",
                type="llm",
                inputs={"topic": "predict"},
                outputs={"text": "hello"},
                mocked_source="heuristic_stub",
            )
        ],
        path_diff=PathDiff(
            expected_path=["draft"],
            actual_path=["draft"],
            missing=[],
            extra=[],
            order_mismatch=False,
        ),
    )

    calls = []

    def fake_predict_artifact(_adapter: object, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return mock_result.model_dump(mode="json")

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact)

    service = PredictorService()
    result = service.dispatch_predict_job(
        "skill",
        mock_param={"draft": {"text": "custom"}},
        input_data={"topic": "predict"},
        current_hashes={"draft": {"prompt_hash": "abc"}},
    )

    # 验证返回值携带本次 Predict 绑定的 artifact identity
    assert result.model_dump(mode="json") == {
        **mock_result.model_dump(mode="json"),
        "artifact_ref": mock_art_ref,
    }

    # 验证向 Engine artifact runtime 的参数传递
    assert len(calls) == 1
    assert calls[0]["mock_llm"] == {"draft": {"text": "custom"}}
    assert calls[0]["artifact_ref"] == mock_art_ref
    assert calls[0]["inputs"] == {"topic": "predict"}
    assert calls[0]["current_hashes"] == {"draft": {"prompt_hash": "abc"}}

    # 验证是否成功持久化了 result.json 到 runs 目录
    from app.services.skills import workspace_dir_for

    expected_result_json = workspace_dir_for(skill_dir) / "runs" / "predict-run-777" / "result.json"
    assert expected_result_json.exists()
    saved_data = json.loads(expected_result_json.read_text(encoding="utf-8"))
    assert saved_data["run_id"] == "predict-run-777"
    assert saved_data["success"] is True

    # 验证成功 predict 在 .workspace 落了 predict-pass 记录(供 run-spawn gate 消费)
    from app.services.predict_gate import last_predict_path_for

    predict_pass_record = json.loads(
        last_predict_path_for(skill_dir).read_text(encoding="utf-8")
    )
    assert predict_pass_record["success"] is True
    assert predict_pass_record["skill_id"] == "skill"
    assert predict_pass_record["run_id"] == "predict-run-777"


def test_dispatch_predict_job_translates_sdk_deadlock_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    import app.core.adapters.engine as engine_adapter_module

    mock_art_ref = {
        "artifact_id": "skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "compile",
        lambda *a, **k: mock_art_ref,
    )

    def fake_predict_artifact_deadlock(_adapter: object, _payload: dict[str, Any]) -> None:
        from app.core.adapters.http_transport import StudioAdapterError

        raise StudioAdapterError("engine.predict_deadlock", {"phase_name": "draft", "actual_path": ["draft"] * 11})

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact_deadlock)

    service = PredictorService()
    with pytest.raises(PredictDeadlockError) as exc_info:
        service.dispatch_predict_job("skill", None)

    assert exc_info.value.phase_name == "draft"
    assert exc_info.value.actual_path == ["draft"] * 11


def test_dispatch_predict_job_projects_artifact_error_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    import app.core.adapters.engine as engine_adapter_module

    mock_art_ref = {
        "artifact_id": "skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "compile",
        lambda *a, **k: mock_art_ref,
    )

    def fake_predict_artifact(_adapter: object, _payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "error_code": "llm.provider_not_configured",
            "error_payload": {"message": "LLM Provider is not configured"},
            "retryable": False,
            "run_id": "predict-error-1",
        }

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact)

    service = PredictorService()
    with pytest.raises(PredictArtifactError) as exc_info:
        service.dispatch_predict_job("skill", None)

    assert exc_info.value.error_code == "llm.provider_not_configured"
    assert exc_info.value.error_payload == {"message": "LLM Provider is not configured"}
    assert exc_info.value.run_id == "predict-error-1"
    assert exc_info.value.retryable is False


def test_predict_event_subscriber_threaded_three_layers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.core.adapters.engine as engine_adapter_module
    import graph_agent.core.runner as sdk_runner
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda _skill_id: skill_dir)

    art_ref = {
        "artifact_id": "skill",
        "content_hash": "sha256:" + "1" * 64,
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "compile", lambda *_args, **_kwargs: art_ref)
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "_ensure_local_artifact_root",
        lambda *_args, **_kwargs: skill_dir,
    )
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "_build_studio_skill_resolver",
        lambda _self: object(),
    )
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "_build_engine_llm_provider",
        lambda _self: None,
    )

    adapter_subscribers: list[Any] = []
    sdk_subscribers: list[Any] = []
    predict_subscribers: list[Any] = []

    original_sdk_predict_artifact = sdk_runner.predict_artifact

    def recording_sdk_predict_artifact(request: Any, **kwargs: Any) -> Any:
        sdk_subscribers.append(request.execution_context.get("event_subscriber"))
        return original_sdk_predict_artifact(request, **kwargs)

    def fake_predict_skill(*_args: Any, **kwargs: Any) -> RunResult:
        predict_subscribers.append(kwargs.get("event_subscriber"))
        return RunResult(
            success=True,
            run_id="predict-s1-threaded",
            skill_id="skill",
            context={},
            source="predict",
            phases=[],
        )

    def fake_bytes_result_payload(result: Any, _store: Any) -> Any:
        return RunResult(
            success=True,
            run_id=getattr(result, "run_id", "predict-s1-threaded"),
            skill_id="skill",
            context={},
            source="predict",
            phases=[],
        ).model_dump(mode="json")

    def recording_predict_artifact(self: object, payload: dict[str, Any]) -> Any:
        adapter_subscribers.append(payload.get("event_subscriber"))
        return original_predict_artifact(self, payload)

    original_predict_artifact = engine_adapter_module.EngineAdapter.predict_artifact
    monkeypatch.setattr(sdk_runner, "predict_artifact", recording_sdk_predict_artifact)
    monkeypatch.setattr(sdk_runner, "predict_skill", fake_predict_skill)
    monkeypatch.setattr(engine_adapter_module, "predict_artifact", recording_sdk_predict_artifact)
    monkeypatch.setattr(engine_adapter_module, "_bytes_result_payload", fake_bytes_result_payload)
    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", recording_predict_artifact)

    result = PredictorService().dispatch_predict_job("skill")

    assert result.source == "predict"
    assert callable(adapter_subscribers[0])
    assert callable(sdk_subscribers[0])
    assert callable(predict_subscribers[0])


def test_predict_events_reach_transient_run_record_ws_queue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.core.adapters.engine as engine_adapter_module
    import graph_agent.core.runner as sdk_runner
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda _skill_id: skill_dir)

    art_ref = {
        "artifact_id": "skill",
        "content_hash": "sha256:" + "2" * 64,
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "compile", lambda *_args, **_kwargs: art_ref)
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "_ensure_local_artifact_root",
        lambda *_args, **_kwargs: skill_dir,
    )
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "_build_studio_skill_resolver",
        lambda _self: object(),
    )
    captured_queue: list[Any] = []

    def fake_predict_skill(*_args: Any, **kwargs: Any) -> RunResult:
        run_id = str(kwargs["thread_id"])
        captured_queue.append(run_manager_module.run_manager._runs[run_id].ws_queue)
        subscriber = kwargs["event_subscriber"]
        subscriber(RunStartedEvent(run_id=run_id, thread_id=run_id, initial_context={}))
        subscriber(PhaseStartEvent(phase_name="draft", context={}))
        subscriber(RunEndedEvent(run_id=run_id, thread_id=run_id, status="completed", wall_time_seconds=0.1))
        return RunResult(
            success=True,
            run_id=run_id,
            skill_id="skill",
            context={},
            source="predict",
            phases=[],
        )

    def fake_bytes_result_payload(result: Any, _store: Any) -> Any:
        return RunResult(
            success=True,
            run_id=getattr(result, "run_id", "predict-s1-events"),
            skill_id="skill",
            context={},
            source="predict",
            phases=[],
        ).model_dump(mode="json")

    monkeypatch.setattr(sdk_runner, "predict_skill", fake_predict_skill)
    monkeypatch.setattr(engine_adapter_module, "_bytes_result_payload", fake_bytes_result_payload)

    result = PredictorService().dispatch_predict_job("skill")

    assert result.source == "predict"
    assert captured_queue
    queue = captured_queue[0]
    first = queue.get_nowait()
    second = queue.get_nowait()
    third = queue.get_nowait()
    sentinel = queue.get_nowait()
    assert [first["event_type"], second["event_type"], third["event_type"]] == [
        "run_started",
        "phase_start",
        "run_ended",
    ]
    assert sentinel is None
    assert result.run_id not in run_manager_module.run_manager._runs


def test_predict_dispatch_api_stays_synchronous(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.core.adapters.engine as engine_adapter_module
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda _skill_id: skill_dir)

    art_ref = {
        "artifact_id": "skill",
        "content_hash": "sha256:" + "3" * 64,
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "compile", lambda *_args, **_kwargs: art_ref)
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "predict_artifact",
        lambda *_args, **_kwargs: RunResult(
            success=True,
            run_id="predict-sync",
            skill_id="skill",
            context={},
            source="predict",
            phases=[],
        ).model_dump(mode="json"),
    )

    result = PredictorService().dispatch_predict_job("skill")

    assert isinstance(result, RunResult)
