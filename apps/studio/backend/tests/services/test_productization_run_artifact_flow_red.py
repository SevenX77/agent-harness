from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


def test_run_manager_routes_source_runs_through_engine_artifact_adapter() -> None:
    source = _source("app/services/run_manager.py")

    assert "EngineAdapter" in source
    assert ".compile(" in source
    assert ".run_artifact(" in source
    assert "run_skill(" not in source
    assert "skill_path_raw" not in source


def test_predictor_routes_prediction_through_ephemeral_artifact_adapter() -> None:
    source = _source("app/services/predictor.py")

    assert "EngineAdapter" in source
    assert ".compile(" in source
    assert ".predict_artifact(" in source
    assert "predict_skill(" not in source
    assert "SkillLoader" not in source
    assert "run_skill_fn" not in source
    assert "_run_skill" not in source


def test_run_artifact_flow_declares_hash_integrity_and_dev_prod_policy() -> None:
    try:
        flow = importlib.import_module("app.services.run_artifact_flow")
    except ModuleNotFoundError as exc:
        pytest.fail(f"app.services.run_artifact_flow is missing: {exc}")

    assert callable(getattr(flow, "resolve_artifact_for_run", None))
    assert callable(getattr(flow, "load_verified_artifact_bytes", None))
    assert callable(getattr(flow, "compile_ephemeral_for_dev_missing_hash", None))
    assert callable(getattr(flow, "reject_prod_missing_hash", None))


def test_engine_adapter_run_and_predict_return_json_serializable_dicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    def fake_run_artifact(_request: object, **_kwargs: Any) -> dict[str, Any]:
        return {"run_id": "run-123", "status": "success", "context": {"answer": 42}, "metrics": {"total_tokens": 3}}

    def fake_predict_artifact(_request: object, **_kwargs: Any) -> dict[str, Any]:
        return {"run_id": "predict-123", "status": "success", "context": {"prediction": "ok"}, "metrics": {}}

    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact)
    monkeypatch.setattr(engine_module, "predict_artifact", fake_predict_artifact)

    adapter = EngineAdapter(transport="in_process")
    artifact_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'a' * 64}",
        "store": "ephemeral",
        "manifest_ref": "manifests/demo.skill.json",
    }

    run_result = adapter.run_artifact(
        {
            "artifact_ref": artifact_ref,
            "workspace_dir": str(tmp_path / "workspace"),
            "thread_id": "run-123",
            "inputs": {},
        }
    )
    predict_result = adapter.predict_artifact(
        {
            "artifact_ref": artifact_ref,
            "mock_llm": None,
            "current_hashes": None,
            "inputs": {},
        }
    )

    assert isinstance(run_result, dict)
    assert isinstance(predict_result, dict)
    assert run_result["run_id"] == "run-123"
    assert predict_result["run_id"] == "predict-123"
    json.dumps(run_result)
    json.dumps(predict_result)


def test_engine_adapter_artifact_methods_do_not_hide_source_runtime_calls() -> None:
    from app.core.adapters.engine import EngineAdapter

    forbidden_names = {"run_skill", "predict_skill", "artifact_executor"}
    for method_name in ("run_artifact", "predict_artifact"):
        source = inspect.getsource(getattr(EngineAdapter, method_name))
        offenders = sorted(name for name in forbidden_names if name in source)
        assert offenders == [], f"EngineAdapter.{method_name} still references old source runtime path: {offenders}"


def test_engine_adapter_resume_preserves_structured_error_codes() -> None:
    from app.core.adapters.engine import EngineAdapter

    source = inspect.getsource(EngineAdapter.resume)

    assert 'StudioAdapterError("engine.resume_failed"' not in source
    assert 'getattr(exc, "error_code", "engine.resume_failed")' in source
    assert 'getattr(exc, "error_payload", {"detail": str(exc)})' in source


def test_engine_adapter_artifact_runtime_uses_new_artifact_apis_not_source_skill_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    sha_val = "d" * 64
    ephemeral_dir = tmp_path / "workspaces" / "default" / "ephemeral_run_skills" / sha_val
    ephemeral_dir.mkdir(parents=True)
    (ephemeral_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")

    def fail_old_run_skill(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("EngineAdapter.run_artifact still called old run_skill source runtime")

    def fail_old_predict_skill(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("EngineAdapter.predict_artifact still called old predict_skill source runtime")

    calls: dict[str, dict[str, Any]] = {}

    def fake_run_artifact(
        request: Any,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        artifact_ref_value = request.artifact_ref
        calls["run"] = {
            "artifact_ref": {
                "artifact_id": artifact_ref_value.artifact_id,
                "content_hash": artifact_ref_value.content_hash,
                "store": artifact_ref_value.store,
                "manifest_ref": artifact_ref_value.manifest_ref,
            },
            "inputs": request.inputs,
            "execution_context": request.execution_context,
            "idempotency_key": request.idempotency_key,
        }
        return {"run_id": "artifact-run", "status": "success", "context": {"ok": True}, "metrics": {}}

    def fake_predict_artifact(
        request: Any,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        artifact_ref_value = request.artifact_ref
        calls["predict"] = {
            "artifact_ref": {
                "artifact_id": artifact_ref_value.artifact_id,
                "content_hash": artifact_ref_value.content_hash,
                "store": artifact_ref_value.store,
                "manifest_ref": artifact_ref_value.manifest_ref,
            },
            "inputs": request.inputs,
            "execution_context": request.execution_context,
            "idempotency_key": request.idempotency_key,
        }
        return {"run_id": "artifact-predict", "status": "success", "context": {"ok": True}, "metrics": {}}

    monkeypatch.setattr(engine_module, "run_skill", fail_old_run_skill, raising=False)
    monkeypatch.setattr(engine_module, "predict_skill", fail_old_predict_skill, raising=False)
    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact, raising=False)
    monkeypatch.setattr(engine_module, "predict_artifact", fake_predict_artifact, raising=False)

    artifact_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "manifests/demo.skill.json",
    }
    execution_context = {"workspace_dir": str(tmp_path / "workspace"), "thread_id": "thread-123"}

    adapter = EngineAdapter(transport="in_process")
    run_result = adapter.run_artifact(
        {
            "artifact_ref": artifact_ref,
            "inputs": {"topic": "run"},
            "execution_context": execution_context,
            "idempotency_key": "idem-run-123",
            "workspace_dir": execution_context["workspace_dir"],
            "thread_id": execution_context["thread_id"],
        }
    )
    predict_result = adapter.predict_artifact(
        {
            "artifact_ref": artifact_ref,
            "inputs": {"topic": "predict"},
            "execution_context": execution_context,
            "idempotency_key": "idem-predict-123",
            "workspace_dir": execution_context["workspace_dir"],
        }
    )

    assert run_result["run_id"] == "artifact-run"
    assert predict_result["run_id"] == "artifact-predict"
    assert calls["run"] == {
        "artifact_ref": artifact_ref,
        "inputs": {"topic": "run"},
        "execution_context": execution_context,
        "idempotency_key": "idem-run-123",
    }
    assert calls["predict"] == {
        "artifact_ref": artifact_ref,
        "inputs": {"topic": "predict"},
        "execution_context": execution_context,
        "idempotency_key": "idem-predict-123",
    }


def test_engine_adapter_in_process_supplies_resolvers_to_artifact_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    skill_resolver = object()
    model_resolver = object()
    calls: dict[str, object] = {}

    monkeypatch.setattr(EngineAdapter, "_build_studio_skill_resolver", lambda _self: skill_resolver)
    monkeypatch.setattr(EngineAdapter, "_build_gateway_model_resolver", lambda _self: model_resolver)

    def fake_run_artifact(request: object, **kwargs: object) -> dict[str, object]:
        calls["run_request"] = request
        calls["run_skill_resolver"] = kwargs.get("skill_resolver")
        calls["run_model_resolver"] = kwargs.get("model_resolver")
        return {"run_id": "artifact-run", "status": "success", "context": {"ok": True}, "metrics": {}}

    def fake_predict_artifact(request: object, **kwargs: object) -> dict[str, object]:
        calls["predict_request"] = request
        calls["predict_skill_resolver"] = kwargs.get("skill_resolver")
        calls["predict_model_resolver"] = kwargs.get("model_resolver")
        return {"run_id": "artifact-predict", "status": "success", "context": {"ok": True}, "metrics": {}}

    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact)
    monkeypatch.setattr(engine_module, "predict_artifact", fake_predict_artifact)

    artifact_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'e' * 64}",
        "store": "ephemeral",
        "manifest_ref": "manifests/demo.skill.json",
    }

    adapter = EngineAdapter(transport="in_process")
    adapter.run_artifact(
        {
            "artifact_ref": artifact_ref,
            "inputs": {"topic": "run"},
            "workspace_dir": str(tmp_path / "workspace"),
            "idempotency_key": "idem-run-resolver",
        }
    )
    adapter.predict_artifact(
        {
            "artifact_ref": artifact_ref,
            "inputs": {"topic": "predict"},
            "workspace_dir": str(tmp_path / "workspace"),
            "idempotency_key": "idem-predict-resolver",
        }
    )

    assert calls["run_skill_resolver"] is skill_resolver
    assert calls["run_model_resolver"] is model_resolver
    assert calls["predict_skill_resolver"] is skill_resolver
    assert calls["predict_model_resolver"] is model_resolver


def _source(relative_path: str) -> str:
    return (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
