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

    expected_result_json = workspace_dir_for(skill_dir) / "predicts" / "predict-run-777" / "result.json"
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


def test_predict_writes_its_account_before_dropping_the_live_record(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The run must never exist nowhere.

    The transient record is the live event source; run_metadata.json is the
    account a later reader replays from. If the record is dropped first there is
    a window in which a subscriber finds neither, and the trace panel is told the
    run does not exist.
    """
    import app.services.run_manager as run_manager_module

    skill_dir = _predict_fixture(monkeypatch, tmp_path, run_id="predict-order", success=True)
    run_dir = skill_dir / ".workspace" / "predicts" / "predict-order"
    account_existed_at_teardown: list[bool] = []
    real_finish = run_manager_module.run_manager.finish_transient_predict_run

    def recording_finish(run_id: str) -> None:
        account_existed_at_teardown.append((run_dir / "run_metadata.json").exists())
        real_finish(run_id)

    monkeypatch.setattr(run_manager_module.run_manager, "finish_transient_predict_run", recording_finish)

    PredictorService().dispatch_predict_job("skill")

    assert account_existed_at_teardown == [True]


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


def _predict_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    run_id: str,
    success: bool,
) -> Path:
    """Wire a predict dispatch over fakes and return the skill dir."""
    import app.core.adapters.engine as engine_adapter_module
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda _skill_id: skill_dir)

    art_ref = {
        "artifact_id": "skill",
        "content_hash": "sha256:" + "4" * 64,
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "compile", lambda *_a, **_k: art_ref)

    def fake_predict_artifact(_adapter: object, _payload: dict[str, Any]) -> dict[str, Any]:
        # The engine drops the trace into the run directory before Studio seals it;
        # reproduce that here, because whether the seal picks the trace up is exactly
        # what these tests are about.
        run_dir = skill_dir / ".workspace" / "predicts" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "trace.jsonl").write_text(
            json.dumps({"event_type": "phase_start", "phase": "draft", "seq": 1}) + "\n",
            encoding="utf-8",
        )
        return RunResult(
            success=success,
            run_id=run_id,
            skill_id="skill",
            context={"topic": "predict"},
            source="predict",
            phases=[],
        ).model_dump(mode="json")

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact)
    return skill_dir


def test_finished_predict_leaves_the_status_account_a_run_reader_needs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # A sealed predict directory used to carry every artifact except an account of
    # what happened, so nothing could answer questions about it once the process
    # ended: `_metadata_for` found no record and no run_metadata.json, and
    # get_run_detail / query_run_trace raised RESUME_CHECKPOINT_NOT_FOUND.
    from app.models.runs import RunMetadata
    from app.services.skills import workspace_dir_for

    skill_dir = _predict_fixture(monkeypatch, tmp_path, run_id="predict-account", success=True)

    PredictorService().dispatch_predict_job("skill")

    account = workspace_dir_for(skill_dir) / "predicts" / "predict-account" / "run_metadata.json"
    assert account.exists(), "a sealed predict run must record its own outcome"
    metadata = RunMetadata.model_validate_json(account.read_text(encoding="utf-8"))
    assert metadata.run_id == "predict-account"
    assert metadata.status == "success"
    # Timeline design (03_regions/timeline F1): predict rows are told apart from
    # run rows by the metadata itself, not by sniffing the run_id prefix.
    assert metadata.kind == "predict"


def test_run_metadata_kind_defaults_to_run() -> None:
    from app.models.runs import RunMetadata

    metadata = RunMetadata.model_validate(
        {"run_id": "r1", "status": "success", "started_at": "2026-08-07T00:00:00Z"}
    )
    assert metadata.kind == "run"


def test_failed_predict_records_the_same_verdict_the_gate_broadcasts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # One judge only: the account must agree with export_predict_diagnostics,
    # the projection the gate event and the frontend already decide on.
    from app.models.runs import RunMetadata
    from app.services.skills import workspace_dir_for

    skill_dir = _predict_fixture(monkeypatch, tmp_path, run_id="predict-bad", success=False)

    result = PredictorService().dispatch_predict_job("skill")

    account = workspace_dir_for(skill_dir) / "predicts" / "predict-bad" / "run_metadata.json"
    metadata = RunMetadata.model_validate_json(account.read_text(encoding="utf-8"))
    assert metadata.status == "failed"
    assert metadata.status == predictor_module.export_predict_diagnostics(result).status


def test_query_run_trace_can_answer_for_a_finished_predict_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The seam the session actually walked into: it asked what a phase received
    # during predict, no tool could answer, and it fell back to parsing files by
    # hand — while the trace sat in the run directory the whole time.
    from app.services import skills as skills_module
    from app.services.run_manager import run_manager

    skill_dir = _predict_fixture(monkeypatch, tmp_path, run_id="predict-readable", success=True)
    # get_run_detail resolves the run dir through the skill registry, which this
    # fixture never populates; point it at the same directory predict wrote to.
    monkeypatch.setattr(skills_module, "resolve_skill_dir", lambda _skill_id: skill_dir)

    PredictorService().dispatch_predict_job("skill")

    detail = run_manager.get_run_detail(skill_id="skill", run_id="predict-readable")

    assert detail.metadata.status == "success"
    assert [event.event_type for event in detail.events] == ["phase_start"]
    assert detail.final_context == {"topic": "predict"}
