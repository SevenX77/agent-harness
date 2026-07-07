from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import pytest

from tests.conftest import register_skill_index_entry

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


def _minimal_skill_detail() -> dict[str, Any]:
    return {
        "manifest": {
            "schema_version": "v0.3.0",
            "name": "demo",
            "description": "",
            "io": {
                "inputs": {"type": "object", "properties": {}},
                "outputs": {"type": "object", "properties": {}},
            },
            "phases": ["draft"],
        },
        "graph_topology": [],
        "node_schema_v21": {},
        "io_schema": {},
        "file_paths": {},
        "files": {},
        "has_golden": False,
        "latest_run_metadata": None,
        "lint_result": {"status": "passed", "errors": [], "phases_summary": []},
        "manifest_errors": [],
    }


def _register_demo_skill(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, skill_dir: Path) -> None:
    from app.core import config

    monkeypatch.setattr(config, "SKILL_INDEX_PATH", tmp_path / "global-config" / "skill_index.json")
    register_skill_index_entry("demo.skill", skill_dir)


def test_run_manager_routes_source_runs_through_engine_artifact_adapter() -> None:
    source = _source("app/services/run_manager.py")

    assert "EngineAdapter" in source
    assert ".compile(" in source
    assert ".run_artifact(" in source
    assert "run_skill(" not in source
    assert "skill_path_raw" not in source


def test_run_worker_produces_runtime_artifacts_through_run_artifact_store_only() -> None:
    tree = ast.parse(_source("app/services/run_manager.py"))
    worker = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_run_worker_main"
    )
    offenders: list[str] = []
    runtime_artifact_names = {"final_state.json", "metrics.json", "trace.jsonl"}

    for node in ast.walk(worker):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_write_json":
            rendered = ast.unparse(node)
            if any(name in rendered for name in runtime_artifact_names):
                offenders.append(f"line {node.lineno}: {rendered}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_ensure_run_files":
            offenders.append(f"line {node.lineno}: {ast.unparse(node)}")

    assert offenders == []


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


def test_compile_success_schema_exposes_artifact_identity_and_execution_fingerprint() -> None:
    from app.models.skills import CompileSuccess

    response = CompileSuccess(
        skill_id="demo.skill",
        status="ok",
        phase_count=1,
        manifest_name="demo",
        artifact_ref={
            "artifact_id": "demo.skill",
            "content_hash": f"sha256:{'1' * 64}",
            "store": "ephemeral",
            "manifest_ref": "file:///tmp/manifest.json",
            "source_map_ref": "file:///tmp/source_map.json",
            "version": None,
        },
        source_map_ref="file:///tmp/source_map.json",
        execution_fingerprint=f"sha256:{'2' * 64}",
        detail=_minimal_skill_detail(),
    )

    assert response.artifact_ref["source_map_ref"] == "file:///tmp/source_map.json"
    assert response.execution_fingerprint == f"sha256:{'2' * 64}"
    assert response.detail.lint_result is not None


def test_compile_skill_for_studio_returns_artifact_identity_from_engine_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.skills as skills_module

    skill_dir = tmp_path / "skills" / "demo.skill"
    skill_dir.mkdir(parents=True)

    async def fake_resolve_skill_dir_async(*_args: object, **_kwargs: object) -> Path:
        return skill_dir

    class FakeAdapter:
        def compile(self, payload: dict[str, Any]) -> dict[str, Any]:
            runtime_config = payload.pop("runtime_config")
            assert runtime_config["schema_version"] == "studio.runtime_config.v1"
            assert runtime_config["inputs"]["import_root"] == "import_files"
            assert "golden" not in runtime_config
            assert "ui" not in runtime_config
            assert payload == {
                "skill_dir": str(skill_dir),
                "skill_id": "demo.skill",
                "artifact_scope": "ephemeral",
            }
            return {
                "artifact_id": "demo.skill",
                "content_hash": f"sha256:{'3' * 64}",
                "store": "ephemeral",
                "manifest_ref": "file:///tmp/manifest.json",
                "source_map_ref": "file:///tmp/source_map.json",
                "execution_fingerprint": f"sha256:{'4' * 64}",
                "version": None,
            }

    async def fake_detail(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return _minimal_skill_detail()

    monkeypatch.setattr(skills_module, "resolve_skill_dir_async", fake_resolve_skill_dir_async)
    monkeypatch.setattr(skills_module, "_detail_from_manifest_async", fake_detail)
    monkeypatch.setattr(
        skills_module,
        "compile_skill",
        lambda *_args, **_kwargs: SimpleNamespace(
            manifest=SimpleNamespace(phases=["draft"], name="demo"),
            nodes=[],
            raw={},
        ),
    )
    monkeypatch.setattr(skills_module, "build_engine_adapter", lambda: FakeAdapter(), raising=False)

    response = asyncio.run(
        skills_module.compile_skill_for_studio(
            "default",
            "demo.skill",
            storage=object(),
            metadata=object(),
        )
    )

    assert response.artifact_ref["artifact_id"] == "demo.skill"
    assert response.artifact_ref["source_map_ref"] == "file:///tmp/source_map.json"
    assert response.source_map_ref == "file:///tmp/source_map.json"
    assert response.execution_fingerprint == f"sha256:{'4' * 64}"


def test_engine_adapter_compile_returns_readable_manifest_source_map_and_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.engine import EngineAdapter

    skill_dir = tmp_path / "skills" / "demo.skill"
    _write_logic_skill(skill_dir)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    result = EngineAdapter(transport="in_process").compile(
        {
            "skill_dir": str(skill_dir),
            "skill_id": "demo.skill",
            "artifact_scope": "ephemeral",
        }
    )

    assert {
        "artifact_id",
        "content_hash",
        "store",
        "manifest_ref",
        "source_map_ref",
        "execution_fingerprint",
    } <= set(result)
    assert result["artifact_id"] == "demo.skill"
    assert result["store"] == "ephemeral"
    assert result["source_map_ref"] == _read_json_ref(result["manifest_ref"])["source_map_ref"]
    assert _read_json_ref(result["source_map_ref"])["schema_version"] == "mvp1.source_map.v1"
    assert _read_json_ref(result["manifest_ref"])["execution_fingerprint"] == result["execution_fingerprint"]


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
    _seed_ephemeral_artifact_root(tmp_path, "a")

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


def test_engine_adapter_run_provider_error_redacts_secret_and_traceback_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from graph_agent.core.llm_provider import LLMProviderError

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    _seed_ephemeral_artifact_root(tmp_path, "a")

    def fail_run_artifact(*_args: object, **_kwargs: object) -> None:
        raise LLMProviderError(
            error_code="llm.provider_invoke_failed",
            message="provider exploded sk-live-secret Traceback (most recent call last)",
            retryable=True,
            details={
                "provider": "fake",
                "api_key": "sk-secret",
                "provider_message": "upstream leaked sk-live-secret Traceback (most recent call last)",
            },
        )

    monkeypatch.setattr(engine_module, "run_artifact", fail_run_artifact)

    with pytest.raises(StudioAdapterError) as exc_info:
        EngineAdapter(transport="in_process").run_artifact(
            {
                "artifact_ref": {
                    "artifact_id": "demo.skill",
                    "content_hash": f"sha256:{'a' * 64}",
                    "store": "ephemeral",
                    "manifest_ref": "manifests/demo.skill.json",
                },
                "workspace_dir": str(tmp_path / "workspace"),
                "thread_id": "run-provider-secret",
                "inputs": {},
            }
        )

    assert exc_info.value.error_code == "llm.provider_invoke_failed"
    assert exc_info.value.error_payload == {
        "detail": "Provider invocation failed",
        "details": {
            "provider": "fake",
            "provider_message": "[redacted]",
        },
        "retryable": True,
    }
    dumped = json.dumps(exc_info.value.error_payload, sort_keys=True)
    assert "sk-live-secret" not in dumped
    assert "Traceback" not in dumped


def test_engine_adapter_predict_provider_error_redacts_secret_and_traceback_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from graph_agent.core.llm_provider import LLMProviderError

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    _seed_ephemeral_artifact_root(tmp_path, "b")

    def fail_predict_artifact(*_args: object, **_kwargs: object) -> None:
        raise LLMProviderError(
            error_code="llm.provider_invoke_failed",
            message="predict leaked sk-live-secret Traceback (most recent call last)",
            retryable=False,
            details={
                "provider": "fake",
                "traceback": "Traceback (most recent call last)",
                "provider_message": "sk-live-secret",
            },
        )

    monkeypatch.setattr(engine_module, "predict_artifact", fail_predict_artifact)

    with pytest.raises(StudioAdapterError) as exc_info:
        EngineAdapter(transport="in_process").predict_artifact(
            {
                "artifact_ref": {
                    "artifact_id": "demo.skill",
                    "content_hash": f"sha256:{'b' * 64}",
                    "store": "ephemeral",
                    "manifest_ref": "manifests/demo.skill.json",
                },
                "workspace_dir": str(tmp_path / "workspace"),
                "thread_id": "predict-provider-secret",
                "inputs": {},
            }
        )

    assert exc_info.value.error_code == "llm.provider_invoke_failed"
    assert exc_info.value.error_payload == {
        "detail": "Provider invocation failed",
        "details": {
            "provider": "fake",
            "provider_message": "[redacted]",
        },
        "retryable": False,
    }
    dumped = json.dumps(exc_info.value.error_payload, sort_keys=True)
    assert "sk-live-secret" not in dumped
    assert "Traceback" not in dumped


def test_engine_adapter_artifact_methods_do_not_hide_source_runtime_calls() -> None:
    from app.core.adapters.engine import EngineAdapter

    forbidden_names = {"run_skill", "predict_skill", "artifact_executor"}
    for method_name in ("run_artifact", "predict_artifact"):
        source = inspect.getsource(getattr(EngineAdapter, method_name))
        offenders = sorted(name for name in forbidden_names if name in source)
        assert offenders == [], f"EngineAdapter.{method_name} still references old source runtime path: {offenders}"


def test_runtime_surface_discovery_forbids_source_path_parameters_and_payload_keys() -> None:
    forbidden_path_names = {
        "skill_dir",
        "skill_dir_raw",
        "skill_path",
        "source_dir",
        "source_path",
        "workspace_source_path",
    }
    runtime_callees = {
        "run_artifact",
        "predict_artifact",
        "resume_restored_runtime_state",
        "evaluate_golden_headless",
        "golden_headless_request_from_ref",
        "start_run_from_artifact",
    }
    offenders: list[str] = []

    for path in sorted((BACKEND_ROOT / "app").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        function_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)]
        for function in function_nodes:
            if function.name == "_run_worker_main" or _function_calls_any(function, runtime_callees):
                for arg in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]:
                    if arg.arg in forbidden_path_names:
                        offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{function.lineno}:{function.name}({arg.arg})")
                for call in [node for node in ast.walk(function) if isinstance(node, ast.Call)]:
                    if _call_name(call.func) not in runtime_callees:
                        continue
                    for dict_node in _dict_payloads(call):
                        for key in dict_node.keys:
                            if isinstance(key, ast.Constant) and key.value in forbidden_path_names:
                                offenders.append(
                                    f"{path.relative_to(BACKEND_ROOT)}:{key.lineno}:{function.name} payload[{key.value!r}]"
                                )

    assert offenders == []


def test_engine_adapter_resume_preserves_structured_error_codes() -> None:
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.runtime_state_store_local import LeaseToken

    lease = LeaseToken(
        lease_id="lease-structured-error",
        owner_id="engine.resume:run-structured-error",
        fencing_token=1,
        ttl_ms=30_000,
    )

    class FailingRuntimeStateStore:
        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            del run_id, owner_id, ttl_ms
            return lease

        def restore(self, run_id: str) -> object:
            raise StudioAdapterError("state.not_found", {"run_id": run_id, "detail": "Snapshot not found"})

        def release(self, run_id: str, lease: LeaseToken) -> None:
            del run_id, lease

    adapter = EngineAdapter(transport="in_process")
    adapter._build_runtime_state_store = lambda: FailingRuntimeStateStore()  # type: ignore[method-assign]

    with pytest.raises(StudioAdapterError) as exc_info:
        adapter.resume({"skill_id": "demo.skill", "run_id": "run-structured-error"})

    assert exc_info.value.error_code == "state.not_found"
    assert exc_info.value.error_payload == {
        "run_id": "run-structured-error",
        "detail": "Snapshot not found",
    }


def test_engine_adapter_resume_is_runtime_state_store_bridge_not_direct_checkpointer() -> None:
    from app.core.adapters.engine import EngineAdapter

    source = inspect.getsource(EngineAdapter.resume)

    assert "_build_runtime_state_store" in source
    assert "restore_checkpointer" in source
    assert "checkpointer=" in source
    assert "resolve_checkpointer(" not in source
    assert "get_checkpointer(" not in source


def test_d10_production_resume_entry_delegates_sdk_resume_to_runtime_state_bridge() -> None:
    from app.core.adapters.engine import EngineAdapter

    source = inspect.getsource(EngineAdapter.resume)

    assert "resume_restored_runtime_state(" in source
    assert "resume_skill(" not in source
    assert "from graph_agent import resume_skill" not in source
    assert "resolve_checkpointer(" not in source
    assert "get_checkpointer(" not in source
    assert ".list(" not in source


def test_d10_resume_production_files_keep_naked_checkpointer_access_inside_runtime_state_boundary() -> None:
    scanned_files = [
        BACKEND_ROOT / "app/core/adapters/engine.py",
        BACKEND_ROOT / "app/routers/runs.py",
    ]
    offenders: list[str] = []

    for path in scanned_files:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = _call_name(node.func)
            segment = ast.get_source_segment(source, node) or ""
            if callee in {"resolve_checkpointer", "get_checkpointer"}:
                offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{node.lineno}:{callee}")
            if callee == "list" and "checkpointer" in segment:
                offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{node.lineno}:checkpointer.list")

    assert offenders == []


def test_engine_resume_validity_denies_dirty_upstream_when_current_artifact_identity_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.runtime_state_store_local import StateSnapshot

    old_hash = f"sha256:{'1' * 64}"
    new_hash = f"sha256:{'2' * 64}"
    old_fingerprint = f"sha256:{'3' * 64}"
    new_fingerprint = f"sha256:{'4' * 64}"

    class _RuntimeStateStore:
        def restore(self, *, run_id: str) -> StateSnapshot:
            return StateSnapshot(
                run_id=run_id,
                fencing_token=7,
                state={
                    "schema_version": "studio.runtime_state.v1",
                    "run_id": run_id,
                    "artifact_ref": {
                        "artifact_id": "demo.skill",
                        "content_hash": old_hash,
                        "store": "ephemeral",
                        "manifest_ref": "object://old-manifest",
                        "source_map_ref": "object://old-source-map",
                        "execution_fingerprint": old_fingerprint,
                    },
                    "checkpoint_id": "checkpoint-beta",
                    "checkpoint_ns": "agent:beta",
                },
            )

    adapter = EngineAdapter(transport="in_process")
    monkeypatch.setattr(adapter, "_build_runtime_state_store", lambda: _RuntimeStateStore())
    monkeypatch.setattr("app.services.skills.resolve_skill_dir", lambda _skill_id: Path("/tmp/demo"))
    monkeypatch.setattr(
        adapter,
        "compile",
        lambda payload: {
            "artifact_id": payload["skill_id"],
            "content_hash": new_hash,
            "store": "ephemeral",
            "version": None,
            "manifest_ref": "object://new-manifest",
            "source_map_ref": "object://new-source-map",
            "execution_fingerprint": new_fingerprint,
        },
    )

    result = adapter.resume_validity(
        {
            "skill_id": "demo.skill",
            "run_id": "run-dirty",
            "checkpoint_id": "checkpoint-beta",
            "checkpoint_ns": "agent:beta",
            "resume_from_node_id": "beta",
            "resume_to_node_id": "gamma",
        }
    )

    assert result == {
        "run_id": "run-dirty",
        "resume_allowed": False,
        "reason": "dirty_upstream",
        "checkpoint_id": "checkpoint-beta",
        "checkpoint_ns": "agent:beta",
        "resume_from_node_id": "beta",
        "resume_to_node_id": "gamma",
        "dirty_fields": ["content_hash", "execution_fingerprint"],
        # n5-node#3: the /tmp/demo skill does not compile in this unit, so the
        # downstream slice degrades to empty (logged) -- the resume decision is
        # unaffected. A real compiled graph populates these (see test_resume_downstream).
        "dirty_node_ids": [],
        "affected_downstream": [],
        "snapshot_content_hash": old_hash,
        "current_content_hash": new_hash,
        "snapshot_execution_fingerprint": old_fingerprint,
        "current_execution_fingerprint": new_fingerprint,
    }


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


def test_engine_adapter_in_process_supplies_engine_owned_llm_provider_only_to_live_artifact_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    skill_resolver = object()
    llm_provider = object()
    calls: dict[str, object] = {}

    monkeypatch.setattr(EngineAdapter, "_build_studio_skill_resolver", lambda _self: skill_resolver)
    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: llm_provider)

    def fake_run_artifact(request: object, **kwargs: object) -> dict[str, object]:
        calls["run_request"] = request
        calls["run_skill_resolver"] = kwargs.get("skill_resolver")
        calls["run_llm_provider"] = kwargs.get("llm_provider")
        calls["run_model_resolver"] = kwargs.get("model_resolver")
        return {"run_id": "artifact-run", "status": "success", "context": {"ok": True}, "metrics": {}}

    def fake_predict_artifact(request: object, **kwargs: object) -> dict[str, object]:
        calls["predict_request"] = request
        calls["predict_skill_resolver"] = kwargs.get("skill_resolver")
        calls["predict_llm_provider"] = kwargs.get("llm_provider")
        calls["predict_model_resolver"] = kwargs.get("model_resolver")
        return {"run_id": "artifact-predict", "status": "success", "context": {"ok": True}, "metrics": {}}

    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact)
    monkeypatch.setattr(engine_module, "predict_artifact", fake_predict_artifact)
    _seed_ephemeral_artifact_root(tmp_path, "e")

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
    assert calls["run_llm_provider"] is llm_provider
    assert calls["run_model_resolver"] is None
    assert calls["predict_skill_resolver"] is skill_resolver
    assert calls["predict_llm_provider"] is None
    assert calls["predict_model_resolver"] is None


def test_engine_adapter_predict_artifact_never_builds_live_llm_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_resolver = object()
    calls: dict[str, object] = {}

    monkeypatch.setattr(EngineAdapter, "_build_studio_skill_resolver", lambda _self: skill_resolver)

    def fail_if_live_provider_is_built(_self: object) -> object:
        pytest.fail("Predict must not build or inject a Gateway-backed live LLM provider")

    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", fail_if_live_provider_is_built)

    def fake_predict_artifact(request: object, **kwargs: object) -> dict[str, object]:
        calls["request"] = request
        calls["skill_resolver"] = kwargs.get("skill_resolver")
        calls["llm_provider"] = kwargs.get("llm_provider")
        calls["model_resolver"] = kwargs.get("model_resolver")
        return {"run_id": "artifact-predict", "status": "success", "context": {"ok": True}, "metrics": {}}

    monkeypatch.setattr(engine_module, "predict_artifact", fake_predict_artifact)
    _seed_ephemeral_artifact_root(tmp_path, "7")

    result = EngineAdapter(transport="in_process").predict_artifact(
        {
            "artifact_ref": {
                "artifact_id": "demo.skill",
                "content_hash": f"sha256:{'7' * 64}",
                "store": "ephemeral",
                "manifest_ref": "manifests/demo.skill.json",
            },
            "inputs": {"topic": "predict"},
            "workspace_dir": str(tmp_path / "workspace"),
            "idempotency_key": "idem-predict-no-live-provider",
        }
    )

    assert result["run_id"] == "artifact-predict"
    assert calls["skill_resolver"] is skill_resolver
    assert calls["llm_provider"] is None
    assert calls["model_resolver"] is None


def test_engine_adapter_product_missing_artifact_preserves_not_found_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    def fail_runtime_call(*_args: object, **_kwargs: object) -> None:
        pytest.fail("product artifact missing must fail before entering graph runtime")

    monkeypatch.setattr(engine_module, "run_artifact", fail_runtime_call)
    monkeypatch.setattr(engine_module, "predict_artifact", fail_runtime_call)

    missing_product_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'9' * 64}",
        "store": "product",
        "manifest_ref": "file:///tmp/missing-manifest.json",
        "source_map_ref": "file:///tmp/missing-source-map.json",
        "version": "release-2026-06-17",
    }

    adapter = EngineAdapter(transport="in_process")
    with pytest.raises(StudioAdapterError) as run_exc:
        adapter.run_artifact(
            {
                "artifact_ref": missing_product_ref,
                "inputs": {},
                "workspace_dir": str(tmp_path / "workspace"),
                "idempotency_key": "idem-run-missing-product",
            }
        )
    with pytest.raises(StudioAdapterError) as predict_exc:
        adapter.predict_artifact(
            {
                "artifact_ref": missing_product_ref,
                "inputs": {},
                "workspace_dir": str(tmp_path / "workspace"),
                "idempotency_key": "idem-predict-missing-product",
            }
        )

    assert run_exc.value.error_code == "artifact.not_found"
    assert predict_exc.value.error_code == "artifact.not_found"
    assert run_exc.value.error_payload == {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'9' * 64}",
        "store": "product",
        "version": "release-2026-06-17",
        "release_version": "release-2026-06-17",
        "detail": "Product artifact bytes are missing",
    }
    assert predict_exc.value.error_payload == run_exc.value.error_payload


def test_engine_adapter_ephemeral_hash_mismatch_does_not_dev_rebuild_or_enter_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    import app.services.run_artifact_flow as run_artifact_flow
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.product_store_local import LocalProductArtifactStore

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    content_hash = f"sha256:{'8' * 64}"
    workspace_root = _storage_root(tmp_path)
    store = LocalProductArtifactStore(root=workspace_root)
    blob_path = store.blob_path(content_hash)
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(b"corrupted artifact bytes")

    def fail_runtime_call(*_args: object, **_kwargs: object) -> None:
        pytest.fail("hash mismatch must fail before entering graph runtime")

    def fail_dev_rebuild(_artifact_id: str) -> object:
        pytest.fail("hash mismatch must not be treated as dev missing-cache rebuild")

    monkeypatch.setattr(engine_module, "run_artifact", fail_runtime_call)
    monkeypatch.setattr(run_artifact_flow, "compile_ephemeral_for_dev_missing_hash", fail_dev_rebuild)

    adapter = EngineAdapter(transport="in_process")
    with pytest.raises(StudioAdapterError) as exc_info:
        adapter.run_artifact(
            {
                "artifact_ref": {
                    "artifact_id": "demo.skill",
                    "content_hash": content_hash,
                    "store": "ephemeral",
                    "manifest_ref": "manifests/demo.skill.json",
                },
                "inputs": {},
                "workspace_dir": str(tmp_path / "workspace"),
                "idempotency_key": "idem-run-corrupt-ephemeral",
            }
        )

    assert exc_info.value.error_code == "artifact.hash_mismatch"


def test_engine_adapter_ephemeral_missing_artifact_dev_rebuilds_once_and_runs_refreshed_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    import app.services.run_artifact_flow as run_artifact_flow
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.product_store_local import LocalProductArtifactStore

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    workspace_root = _storage_root(tmp_path)
    product_store = LocalProductArtifactStore(root=workspace_root)
    refreshed_ref = product_store.put(_zip_skill_bytes(), artifact_id="demo.skill", store="ephemeral")
    rebuild_calls: list[str] = []
    runtime_calls: list[str] = []

    def compile_dev_missing(artifact_id: str) -> object:
        rebuild_calls.append(artifact_id)
        return refreshed_ref

    def fake_run_artifact(request: object, **_kwargs: object) -> dict[str, Any]:
        runtime_calls.append(request.artifact_ref.content_hash)
        assert request.artifact_ref.content_hash == refreshed_ref.content_hash
        assert request.execution_context["artifact_root"].endswith(
            refreshed_ref.content_hash.removeprefix("sha256:")
        )
        return {"run_id": "run-dev-rebuild", "success": True, "context": {"rebuilt": True}, "metrics": {}}

    monkeypatch.setattr(run_artifact_flow, "compile_ephemeral_for_dev_missing_hash", compile_dev_missing)
    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact)

    result = EngineAdapter(transport="in_process").run_artifact(
        {
            "artifact_ref": {
                "artifact_id": "demo.skill",
                "content_hash": f"sha256:{'7' * 64}",
                "store": "ephemeral",
                "manifest_ref": "manifests/demo.skill.json",
            },
            "inputs": {},
            "workspace_dir": str(tmp_path / "workspace"),
            "idempotency_key": "idem-run-dev-rebuild",
        }
    )

    assert rebuild_calls == ["demo.skill"]
    assert runtime_calls == [refreshed_ref.content_hash]
    assert result["context"] == {"rebuilt": True}


def test_engine_adapter_ephemeral_missing_artifact_records_dev_rebuild_old_and_new_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    import app.services.run_artifact_flow as run_artifact_flow
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.product_store_local import LocalProductArtifactStore

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    workspace_root = _storage_root(tmp_path)
    product_store = LocalProductArtifactStore(root=workspace_root)
    refreshed_ref = product_store.put(_zip_skill_bytes(), artifact_id="demo.skill", store="ephemeral")
    stale_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'4' * 64}",
        "store": "ephemeral",
        "manifest_ref": "manifests/demo.skill.json",
        "source_map_ref": "source-maps/demo.skill.json",
        "version": None,
    }
    captured_context: dict[str, Any] = {}

    def compile_dev_missing(artifact_id: str) -> object:
        assert artifact_id == "demo.skill"
        return refreshed_ref

    def fake_run_artifact(request: object, **_kwargs: object) -> dict[str, Any]:
        captured_context.update(dict(request.execution_context))
        return {"run_id": "run-dev-rebuild-audit", "success": True, "context": {}, "metrics": {}}

    monkeypatch.setattr(run_artifact_flow, "compile_ephemeral_for_dev_missing_hash", compile_dev_missing)
    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact)

    EngineAdapter(transport="in_process").run_artifact(
        {
            "artifact_ref": dict(stale_ref),
            "inputs": {},
            "workspace_dir": str(tmp_path / "workspace"),
            "idempotency_key": "idem-run-dev-rebuild-audit",
        }
    )

    assert captured_context["artifact_dev_rebuild"] == {
        "reason": "ephemeral.artifact_missing",
        "old_artifact_ref": stale_ref,
        "new_artifact_ref": {
            "artifact_id": refreshed_ref.artifact_id,
            "content_hash": refreshed_ref.content_hash,
            "store": refreshed_ref.store,
            "manifest_ref": refreshed_ref.manifest_ref,
            "source_map_ref": refreshed_ref.source_map_ref,
            "version": None,
        },
    }


def test_engine_adapter_predict_ephemeral_missing_artifact_records_dev_rebuild_old_and_new_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    import app.services.run_artifact_flow as run_artifact_flow
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.product_store_local import LocalProductArtifactStore

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    workspace_root = _storage_root(tmp_path)
    product_store = LocalProductArtifactStore(root=workspace_root)
    refreshed_ref = product_store.put(_zip_skill_bytes(), artifact_id="demo.skill", store="ephemeral")
    stale_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'3' * 64}",
        "store": "ephemeral",
        "manifest_ref": "manifests/demo.skill.json",
        "source_map_ref": "source-maps/demo.skill.json",
        "version": None,
    }
    captured_context: dict[str, Any] = {}

    def compile_dev_missing(artifact_id: str) -> object:
        assert artifact_id == "demo.skill"
        return refreshed_ref

    def fake_predict_artifact(request: object, **_kwargs: object) -> dict[str, Any]:
        captured_context.update(dict(request.execution_context))
        return {"run_id": "predict-dev-rebuild-audit", "status": "success", "context": {}, "metrics": {}}

    monkeypatch.setattr(run_artifact_flow, "compile_ephemeral_for_dev_missing_hash", compile_dev_missing)
    monkeypatch.setattr(engine_module, "predict_artifact", fake_predict_artifact)

    EngineAdapter(transport="in_process").predict_artifact(
        {
            "artifact_ref": dict(stale_ref),
            "inputs": {},
            "workspace_dir": str(tmp_path / "workspace"),
            "idempotency_key": "idem-predict-dev-rebuild-audit",
        }
    )

    assert captured_context["artifact_dev_rebuild"] == {
        "reason": "ephemeral.artifact_missing",
        "old_artifact_ref": stale_ref,
        "new_artifact_ref": {
            "artifact_id": refreshed_ref.artifact_id,
            "content_hash": refreshed_ref.content_hash,
            "store": refreshed_ref.store,
            "manifest_ref": refreshed_ref.manifest_ref,
            "source_map_ref": refreshed_ref.source_map_ref,
            "version": None,
        },
    }


def test_engine_adapter_ephemeral_missing_artifact_dev_mode_false_surfaces_not_found_without_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    import app.services.run_artifact_flow as run_artifact_flow
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    def fail_runtime_call(*_args: object, **_kwargs: object) -> None:
        pytest.fail("dev_mode=false missing artifact must fail before entering graph runtime")

    def fail_dev_rebuild(_artifact_id: str) -> object:
        pytest.fail("dev_mode=false must not compile a replacement ephemeral artifact")

    monkeypatch.setattr(engine_module, "run_artifact", fail_runtime_call)
    monkeypatch.setattr(engine_module, "predict_artifact", fail_runtime_call)
    monkeypatch.setattr(run_artifact_flow, "compile_ephemeral_for_dev_missing_hash", fail_dev_rebuild)

    adapter = EngineAdapter(transport="in_process")
    for method_name in ("run_artifact", "predict_artifact"):
        with pytest.raises(StudioAdapterError) as exc_info:
            getattr(adapter, method_name)(
                {
                    "artifact_ref": {
                        "artifact_id": "demo.skill",
                        "content_hash": f"sha256:{'6' * 64}",
                        "store": "ephemeral",
                        "manifest_ref": "manifests/demo.skill.json",
                    },
                    "inputs": {},
                    "workspace_dir": str(tmp_path / "workspace"),
                    "idempotency_key": f"idem-{method_name}-dev-mode-false",
                    "dev_mode": False,
                }
            )

        assert exc_info.value.error_code == "artifact.not_found"
        assert exc_info.value.error_payload == {
            "artifact_id": "demo.skill",
            "content_hash": f"sha256:{'6' * 64}",
            "store": "ephemeral",
            "version": None,
            "release_version": None,
            "detail": "Artifact bytes are missing",
        }


def test_engine_adapter_ephemeral_dev_rebuild_error_does_not_enter_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    import app.services.run_artifact_flow as run_artifact_flow
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    rebuild_calls: list[str] = []

    def fail_runtime_call(*_args: object, **_kwargs: object) -> None:
        pytest.fail("failed dev rebuild must not fall through into graph runtime")

    def compile_dev_missing(artifact_id: str) -> object:
        rebuild_calls.append(artifact_id)
        raise StudioAdapterError("artifact.compile_failed", {"detail": "dev rebuild failed"})

    monkeypatch.setattr(engine_module, "run_artifact", fail_runtime_call)
    monkeypatch.setattr(run_artifact_flow, "compile_ephemeral_for_dev_missing_hash", compile_dev_missing)

    with pytest.raises(StudioAdapterError) as exc_info:
        EngineAdapter(transport="in_process").run_artifact(
            {
                "artifact_ref": {
                    "artifact_id": "demo.skill",
                    "content_hash": f"sha256:{'5' * 64}",
                    "store": "ephemeral",
                    "manifest_ref": "manifests/demo.skill.json",
                },
                "inputs": {},
                "workspace_dir": str(tmp_path / "workspace"),
                "idempotency_key": "idem-run-dev-rebuild-failed",
            }
        )

    assert rebuild_calls == ["demo.skill"]
    assert exc_info.value.error_code == "artifact.compile_failed"
    assert exc_info.value.error_payload == {"detail": "dev rebuild failed"}


def test_engine_adapter_resume_supplies_engine_owned_llm_provider_not_gateway_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    skill_root = tmp_path / "skills" / "demo.skill"
    skill_root.mkdir(parents=True)
    (skill_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")

    class _SkillResolver:
        def resolve_skill(self, skill_id: str) -> Path:
            assert skill_id == "demo.skill"
            return skill_root

    llm_provider = object()
    artifact_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'f' * 64}",
        "store": "ephemeral",
        "manifest_ref": "manifests/demo.skill.json",
    }
    artifact_root = tmp_path / "workspaces" / "default" / "ephemeral_run_skills" / ("f" * 64)
    artifact_root.mkdir(parents=True)
    (artifact_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    calls: dict[str, object] = {}

    class _RuntimeStateStore:
        def __init__(self) -> None:
            self.lease = LeaseToken(
                lease_id="lease-run-resume-spi",
                owner_id="engine.resume:run-resume-spi",
                fencing_token=1,
                ttl_ms=30_000,
            )

        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            del run_id, owner_id, ttl_ms
            return self.lease

        def restore(self, run_id: str) -> StateSnapshot:
            return StateSnapshot(
                run_id=run_id,
                state={"checkpoint_id": "checkpoint-ready", "artifact_ref": artifact_ref},
                fencing_token=1,
            )

        def restore_checkpointer(self, snapshot: StateSnapshot) -> object:
            del snapshot
            return object()

        def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
            del run_id
            assert lease is self.lease
            return lease

        def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken) -> StateSnapshot:
            del state
            assert lease is self.lease
            return StateSnapshot(run_id=run_id, state={}, fencing_token=1)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            del run_id
            assert lease is self.lease

    monkeypatch.setattr(EngineAdapter, "_build_studio_skill_resolver", lambda _self: _SkillResolver())
    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: llm_provider)
    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: _RuntimeStateStore())
    monkeypatch.setattr(EngineAdapter, "compile", lambda _self, _payload: artifact_ref)

    def fake_resume_skill(*args: object, **kwargs: object) -> object:
        calls["args"] = args
        calls["llm_provider"] = kwargs.get("llm_provider")
        calls["model_resolver"] = kwargs.get("model_resolver")

        class _Result:
            success = True
            started_at = None
            metrics: dict[str, object] = {}

        return _Result()

    monkeypatch.setattr(graph_agent, "resume_skill", fake_resume_skill)

    adapter = EngineAdapter(transport="in_process")
    result = adapter.resume(
        {
            "skill_id": "demo.skill",
            "run_id": "run-resume-spi",
            "human_input": "continue",
        }
    )

    assert result["status"] == "success"
    assert calls["llm_provider"] is llm_provider
    assert calls["model_resolver"] is None


def test_engine_adapter_resume_provider_error_redacts_secret_and_traceback_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.runtime_state_resume_bridge as resume_bridge
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot
    from graph_agent.core.llm_provider import LLMProviderError

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    _seed_ephemeral_artifact_root(tmp_path, "c")
    artifact_ref = _runtime_artifact_ref("c")
    lease = LeaseToken(
        lease_id="lease-resume-provider-secret",
        owner_id="engine.resume:run-resume-provider-secret",
        fencing_token=1,
        ttl_ms=30_000,
    )

    class _RuntimeStateStore:
        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            del run_id, owner_id, ttl_ms
            return lease

        def restore(self, run_id: str) -> StateSnapshot:
            return StateSnapshot(
                run_id=run_id,
                state={"checkpoint_id": "checkpoint-ready", "artifact_ref": artifact_ref},
                fencing_token=1,
            )

        def restore_checkpointer(self, snapshot: StateSnapshot) -> object:
            del snapshot
            return object()

        def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
            del run_id
            return lease

        def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken) -> StateSnapshot:
            del state, lease
            return StateSnapshot(run_id=run_id, state={}, fencing_token=1)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            del run_id, lease

    def fail_resume_bridge(*_args: object, **_kwargs: object) -> object:
        raise LLMProviderError(
            error_code="llm.provider_invoke_failed",
            message="resume leaked sk-live-secret Traceback (most recent call last)",
            retryable=True,
            details={
                "provider": "fake",
                "api_key": "sk-secret",
                "provider_message": "sk-live-secret Traceback (most recent call last)",
            },
        )

    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: _RuntimeStateStore())
    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: object())
    monkeypatch.setattr(resume_bridge, "resume_restored_runtime_state", fail_resume_bridge)

    with pytest.raises(StudioAdapterError) as exc_info:
        EngineAdapter(transport="in_process").resume(
            {"skill_id": "demo.skill", "run_id": "run-resume-provider-secret"}
        )

    assert exc_info.value.error_code == "llm.provider_invoke_failed"
    assert exc_info.value.error_payload == {
        "detail": "Provider invocation failed",
        "details": {
            "provider": "fake",
            "provider_message": "[redacted]",
        },
        "retryable": True,
    }
    dumped = json.dumps(exc_info.value.error_payload, sort_keys=True)
    assert "sk-live-secret" not in dumped
    assert "Traceback" not in dumped


def test_engine_adapter_resume_consumes_restored_runtime_state_checkpoint_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_root = tmp_path / "skills" / "demo.skill"
    skill_root.mkdir(parents=True)
    (skill_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    artifact_root = tmp_path / "workspaces" / "default" / "ephemeral_run_skills" / ("d" * 64)
    artifact_root.mkdir(parents=True)
    (artifact_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")

    class _SkillResolver:
        def resolve_skill(self, skill_id: str) -> Path:
            assert skill_id == "demo.skill"
            return skill_root

    checkpointer_bridge = object()
    runtime_lease = LeaseToken(
        lease_id="lease-restored-checkpoint",
        owner_id="engine.resume:run-restored:worker-1",
        fencing_token=11,
        ttl_ms=30_000,
    )
    restored = StateSnapshot(
        run_id="run-restored",
        state={
            "artifact_ref": _runtime_artifact_ref("d"),
            "checkpoint_id": "checkpoint-from-runtime-store",
            "checkpoint_ns": "agent:review",
        },
        fencing_token=11,
    )

    class _RuntimeStateStore:
        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            assert run_id == "run-restored"
            assert owner_id.startswith("engine.resume:run-restored:")
            assert ttl_ms > 0
            return runtime_lease

        def restore(self, run_id: str) -> StateSnapshot:
            assert run_id == "run-restored"
            return restored

        def restore_checkpointer(self, snapshot: StateSnapshot) -> object:
            assert snapshot is restored
            return checkpointer_bridge

        def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
            assert run_id == "run-restored"
            assert lease is runtime_lease
            return lease

        def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken) -> StateSnapshot:
            assert run_id == "run-restored"
            assert state["status"] == "success"
            return StateSnapshot(run_id=run_id, state=state, fencing_token=11)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            assert run_id == "run-restored"
            assert lease is runtime_lease

    monkeypatch.setattr(EngineAdapter, "_build_studio_skill_resolver", lambda _self: _SkillResolver())
    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: object())
    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: _RuntimeStateStore())
    monkeypatch.setattr(
        EngineAdapter,
        "compile",
        lambda _self, _payload: {
            "artifact_id": "demo.skill",
            "content_hash": f"sha256:{'d' * 64}",
            "store": "ephemeral",
            "manifest_ref": "manifests/demo.skill.json",
        },
    )

    captured: dict[str, object] = {}

    def fake_resume_skill(*_args: object, **kwargs: object) -> object:
        captured.update(kwargs)

        class _Result:
            success = True
            started_at = None
            metrics: dict[str, object] = {}

        return _Result()

    monkeypatch.setattr(graph_agent, "resume_skill", fake_resume_skill)

    result = EngineAdapter(transport="in_process").resume(
        {
            "skill_id": "demo.skill",
            "run_id": "run-restored",
            "human_input": "continue",
        }
    )

    assert result["status"] == "success"
    assert captured["checkpointer"] is checkpointer_bridge
    assert captured["checkpoint_id"] == "checkpoint-from-runtime-store"
    assert captured["checkpoint_ns"] == "agent:review"


def test_engine_adapter_resume_prefers_explicit_checkpoint_selector_and_structured_human_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.runtime_state_resume_bridge as bridge_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    _seed_ephemeral_artifact_root(tmp_path, "c")
    lease = SimpleNamespace(lease_id="lease-node-resume", owner_id="engine.resume:run-node-resume", fencing_token=1)
    artifact_ref = _runtime_artifact_ref("c")
    captured: dict[str, object] = {}

    class RuntimeStateStore:
        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> object:
            assert run_id == "run-node-resume"
            assert owner_id.startswith("engine.resume:run-node-resume:")
            assert ttl_ms == 30_000
            return lease

        def restore(self, run_id: str) -> object:
            assert run_id == "run-node-resume"
            return SimpleNamespace(
                state={
                    "checkpoint_id": "checkpoint-latest",
                    "checkpoint_ns": "agent:latest",
                    "artifact_ref": artifact_ref,
                }
            )

        def restore_checkpointer(self, snapshot: object) -> object:
            assert snapshot is not None
            return object()

        def heartbeat(self, run_id: str, lease: object) -> None:
            assert run_id == "run-node-resume"
            assert lease is not None

        def latest_checkpoint_state(self, **_kwargs: object) -> None:
            return None

        def snapshot(self, run_id: str, state: dict[str, object], lease: object) -> object:
            assert run_id == "run-node-resume"
            assert state["checkpoint_id"] == "checkpoint-latest"
            assert lease is not None
            return SimpleNamespace(run_id=run_id, state=state)

        def release(self, run_id: str, lease: object) -> None:
            assert run_id == "run-node-resume"
            assert lease is not None

    def fake_resume_restored_runtime_state(*_args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(success=True, started_at=None, metrics={})

    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: RuntimeStateStore())
    monkeypatch.setattr(bridge_module, "resume_restored_runtime_state", fake_resume_restored_runtime_state)

    result = EngineAdapter(transport="in_process").resume(
        {
            "skill_id": "demo.skill",
            "run_id": "run-node-resume",
            "checkpoint_id": "checkpoint-review",
            "checkpoint_ns": "agent:review",
            "context_overrides": {"draft": "manual"},
            "human_response": {"content": "approved", "tool_call_id": "tool-1"},
        }
    )

    assert result["status"] == "success"
    assert captured["checkpoint_id"] == "checkpoint-review"
    assert captured["checkpoint_ns"] == "agent:review"
    assert captured["context_overrides"] == {"draft": "manual"}
    assert captured["human_response"] == {"content": "approved", "tool_call_id": "tool-1"}


def test_engine_adapter_resume_snapshots_checkpoint_identity_produced_by_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    artifact_root = tmp_path / "workspaces" / "default" / "ephemeral_run_skills" / ("a" * 64)
    artifact_root.mkdir(parents=True)
    (artifact_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")

    checkpointer_bridge = object()
    runtime_lease = LeaseToken(
        lease_id="lease-resume-new-checkpoint",
        owner_id="engine.resume:run-new-checkpoint",
        fencing_token=17,
        ttl_ms=30_000,
    )
    restored = StateSnapshot(
        run_id="run-new-checkpoint",
        state={
            "artifact_ref": _runtime_artifact_ref("a"),
            "checkpoint_id": "checkpoint-before-resume",
            "checkpoint_ns": "before:ns",
            "metrics": {"before": 1},
        },
        fencing_token=17,
    )

    class _RuntimeStateStore:
        def __init__(self) -> None:
            self.snapshots: list[dict[str, Any]] = []

        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            assert run_id == "run-new-checkpoint"
            assert owner_id.startswith("engine.resume:run-new-checkpoint:")
            assert ttl_ms > 0
            return runtime_lease

        def restore(self, run_id: str) -> StateSnapshot:
            assert run_id == "run-new-checkpoint"
            return restored

        def restore_checkpointer(self, snapshot: StateSnapshot) -> object:
            assert snapshot is restored
            return checkpointer_bridge

        def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
            assert run_id == "run-new-checkpoint"
            assert lease is runtime_lease
            return lease

        def latest_checkpoint_state(self, *, run_id: str, checkpointer: object) -> dict[str, str]:
            assert run_id == "run-new-checkpoint"
            assert checkpointer is checkpointer_bridge
            return {
                "checkpoint_id": "checkpoint-after-resume",
                "checkpoint_ns": "after:ns",
            }

        def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken) -> StateSnapshot:
            assert run_id == "run-new-checkpoint"
            assert lease is runtime_lease
            self.snapshots.append(state)
            return StateSnapshot(run_id=run_id, state=state, fencing_token=17)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            assert run_id == "run-new-checkpoint"
            assert lease is runtime_lease

    runtime_store = _RuntimeStateStore()

    def fake_resume_skill(*_args: object, **_kwargs: object) -> object:
        class _Result:
            success = True
            started_at = None
            metrics: dict[str, object] = {"after": 2}

        return _Result()

    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: object())
    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: runtime_store)
    monkeypatch.setattr(graph_agent, "resume_skill", fake_resume_skill)

    result = EngineAdapter(transport="in_process").resume(
        {
            "skill_id": "demo.skill",
            "run_id": "run-new-checkpoint",
            "human_input": "continue",
        }
    )

    assert result["status"] == "success"
    assert runtime_store.snapshots[-1]["checkpoint_id"] == "checkpoint-after-resume"
    assert runtime_store.snapshots[-1]["checkpoint_ns"] == "after:ns"


def test_engine_adapter_resume_surfaces_typed_latest_checkpoint_state_error_without_stale_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.runtime_state_resume_bridge as bridge_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    artifact_root = tmp_path / "workspaces" / "default" / "ephemeral_run_skills" / ("9" * 64)
    artifact_root.mkdir(parents=True)
    (artifact_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")

    checkpointer_bridge = object()
    runtime_lease = LeaseToken(
        lease_id="lease-latest-checkpoint-error",
        owner_id="engine.resume:run-latest-checkpoint-error",
        fencing_token=23,
        ttl_ms=30_000,
    )
    restored = StateSnapshot(
        run_id="run-latest-checkpoint-error",
        state={
            "artifact_ref": _runtime_artifact_ref("9"),
            "checkpoint_id": "checkpoint-before-resume",
            "checkpoint_ns": "before:ns",
        },
        fencing_token=23,
    )

    class _RuntimeStateStore:
        def __init__(self) -> None:
            self.snapshots: list[dict[str, Any]] = []
            self.released = False

        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            assert run_id == "run-latest-checkpoint-error"
            assert owner_id.startswith("engine.resume:run-latest-checkpoint-error:")
            assert ttl_ms > 0
            return runtime_lease

        def restore(self, run_id: str) -> StateSnapshot:
            assert run_id == "run-latest-checkpoint-error"
            return restored

        def restore_checkpointer(self, snapshot: StateSnapshot) -> object:
            assert snapshot is restored
            return checkpointer_bridge

        def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
            assert run_id == "run-latest-checkpoint-error"
            assert lease is runtime_lease
            return lease

        def latest_checkpoint_state(self, *, run_id: str, checkpointer: object) -> dict[str, str]:
            assert run_id == "run-latest-checkpoint-error"
            assert checkpointer is checkpointer_bridge
            raise StudioAdapterError(
                "state.invalid_checkpoint",
                {
                    "run_id": run_id,
                    "checkpoint_id": "checkpoint-before-resume",
                    "detail": "Restored checkpointer could not resolve latest checkpoint",
                },
            )

        def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken) -> StateSnapshot:
            assert run_id == "run-latest-checkpoint-error"
            assert lease is runtime_lease
            self.snapshots.append(state)
            return StateSnapshot(run_id=run_id, state=state, fencing_token=23)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            assert run_id == "run-latest-checkpoint-error"
            assert lease is runtime_lease
            self.released = True

    runtime_store = _RuntimeStateStore()

    def fake_resume_restored_runtime_state(*_args: object, **_kwargs: object) -> object:
        class _Result:
            success = True
            started_at = None
            metrics: dict[str, object] = {"after": 2}

        return _Result()

    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: object())
    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: runtime_store)
    monkeypatch.setattr(bridge_module, "resume_restored_runtime_state", fake_resume_restored_runtime_state)

    with pytest.raises(StudioAdapterError) as exc_info:
        EngineAdapter(transport="in_process").resume(
            {
                "skill_id": "demo.skill",
                "run_id": "run-latest-checkpoint-error",
                "human_input": "continue",
            }
        )

    assert exc_info.value.error_code == "state.invalid_checkpoint"
    assert exc_info.value.error_payload == {
        "run_id": "run-latest-checkpoint-error",
        "checkpoint_id": "checkpoint-before-resume",
        "detail": "Restored checkpointer could not resolve latest checkpoint",
    }
    assert runtime_store.snapshots == []
    assert runtime_store.released is True


def test_engine_adapter_resume_rejects_restored_runtime_state_without_checkpoint_before_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.runtime_state_resume_bridge as bridge_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    artifact_root = tmp_path / "workspaces" / "default" / "ephemeral_run_skills" / ("e" * 64)
    artifact_root.mkdir(parents=True)
    (artifact_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")

    runtime_lease = LeaseToken(
        lease_id="lease-missing-checkpoint",
        owner_id="engine.resume:run-missing-checkpoint",
        fencing_token=7,
        ttl_ms=30_000,
    )
    restored = StateSnapshot(
        run_id="run-missing-checkpoint",
        state={
            "artifact_ref": _runtime_artifact_ref("e"),
            "checkpoint_ns": "",
        },
        fencing_token=7,
    )

    class _RuntimeStateStore:
        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            del run_id, owner_id, ttl_ms
            return runtime_lease

        def restore(self, run_id: str) -> StateSnapshot:
            assert run_id == "run-missing-checkpoint"
            return restored

        def restore_checkpointer(self, snapshot: StateSnapshot) -> object:
            assert snapshot is restored
            return object()

        def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
            del run_id, lease
            return runtime_lease

        def release(self, run_id: str, lease: LeaseToken) -> None:
            assert run_id == "run-missing-checkpoint"
            assert lease is runtime_lease

    def fail_bridge_call(*_args: object, **_kwargs: object) -> object:
        pytest.fail("EngineAdapter.resume must reject a restored state without checkpoint_id before bridge")

    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: _RuntimeStateStore())
    monkeypatch.setattr(bridge_module, "resume_restored_runtime_state", fail_bridge_call)

    with pytest.raises(StudioAdapterError) as exc_info:
        EngineAdapter(transport="in_process").resume(
            {
                "skill_id": "demo.skill",
                "run_id": "run-missing-checkpoint",
            }
        )

    assert exc_info.value.error_code == "state.invalid_checkpoint"
    assert exc_info.value.error_payload["run_id"] == "run-missing-checkpoint"


def test_engine_adapter_resume_owner_id_is_unique_per_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_root = tmp_path / "skills" / "demo.skill"
    skill_root.mkdir(parents=True)
    (skill_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    artifact_root = tmp_path / "workspaces" / "default" / "ephemeral_run_skills" / ("c" * 64)
    artifact_root.mkdir(parents=True)
    (artifact_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")

    class _SkillResolver:
        def resolve_skill(self, _skill_id: str) -> Path:
            return skill_root

    class _RuntimeStateStore:
        def __init__(self) -> None:
            self.owner_ids: list[str] = []

        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            assert run_id == "run-owner"
            assert ttl_ms > 0
            self.owner_ids.append(owner_id)
            return LeaseToken(
                lease_id=f"lease-{len(self.owner_ids)}",
                owner_id=owner_id,
                fencing_token=len(self.owner_ids),
                ttl_ms=30_000,
            )

        def restore(self, run_id: str) -> StateSnapshot:
            return StateSnapshot(
                run_id=run_id,
                state={
                    "artifact_ref": _runtime_artifact_ref("c"),
                    "checkpoint_id": f"cp-{len(self.owner_ids)}",
                },
                fencing_token=1,
            )

        def restore_checkpointer(self, snapshot: StateSnapshot) -> object:
            del snapshot
            return object()

        def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
            del run_id
            return lease

        def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken) -> StateSnapshot:
            del state, lease
            return StateSnapshot(run_id=run_id, state={}, fencing_token=1)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            del run_id, lease

    store = _RuntimeStateStore()
    monkeypatch.setattr(EngineAdapter, "_build_studio_skill_resolver", lambda _self: _SkillResolver())
    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: object())
    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: store)
    monkeypatch.setattr(
        EngineAdapter,
        "compile",
        lambda _self, _payload: {
            "artifact_id": "demo.skill",
            "content_hash": f"sha256:{'c' * 64}",
            "store": "ephemeral",
            "manifest_ref": "manifests/demo.skill.json",
        },
    )

    def fake_resume_skill(*_args: object, **_kwargs: object) -> object:
        class _Result:
            success = True
            started_at = None
            metrics: dict[str, object] = {}

        return _Result()

    monkeypatch.setattr(graph_agent, "resume_skill", fake_resume_skill)

    adapter = EngineAdapter(transport="in_process")
    for _ in range(2):
        adapter.resume({"skill_id": "demo.skill", "run_id": "run-owner"})

    assert len(store.owner_ids) == 2
    assert store.owner_ids[0] != store.owner_ids[1]
    assert all(owner_id.startswith("engine.resume:run-owner:") for owner_id in store.owner_ids)


def test_engine_adapter_resume_uses_runtime_state_store_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_root = tmp_path / "skills" / "demo.skill"
    skill_root.mkdir(parents=True)
    (skill_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    artifact_root = tmp_path / "workspaces" / "default" / "ephemeral_run_skills" / ("f" * 64)
    artifact_root.mkdir(parents=True)
    (artifact_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")

    class _SkillResolver:
        def resolve_skill(self, skill_id: str) -> Path:
            assert skill_id == "demo.skill"
            return skill_root

    class SpyRuntimeStateStore:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.lease = LeaseToken(
                lease_id="lease-run-resume-store-1",
                owner_id="engine.resume:run-resume-store",
                fencing_token=7,
                ttl_ms=30_000,
            )

        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            assert run_id == "run-resume-store"
            assert owner_id.startswith("engine.resume:run-resume-store:")
            assert ttl_ms > 0
            self.calls.append("acquire_lease")
            return self.lease

        def restore(self, run_id: str) -> StateSnapshot:
            assert run_id == "run-resume-store"
            self.calls.append("restore")
            return StateSnapshot(
                run_id=run_id,
                state={"checkpoint_id": "checkpoint-ready", "artifact_ref": _runtime_artifact_ref("f")},
                fencing_token=7,
            )

        def restore_checkpointer(self, snapshot: StateSnapshot) -> object:
            assert snapshot.run_id == "run-resume-store"
            self.calls.append("restore_checkpointer")
            return object()

        def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
            assert run_id == "run-resume-store"
            assert lease is self.lease
            self.calls.append("heartbeat")
            return lease

        def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken) -> StateSnapshot:
            assert run_id == "run-resume-store"
            assert state["status"] == "success"
            assert lease is self.lease
            self.calls.append("snapshot")
            return StateSnapshot(run_id=run_id, state=state, fencing_token=7)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            assert run_id == "run-resume-store"
            assert lease is self.lease
            self.calls.append("release")

    spy_store = SpyRuntimeStateStore()
    llm_provider = object()
    monkeypatch.setattr(EngineAdapter, "_build_studio_skill_resolver", lambda _self: _SkillResolver())
    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: llm_provider)
    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: spy_store, raising=False)
    monkeypatch.setattr(
        EngineAdapter,
        "compile",
        lambda _self, _payload: {
            "artifact_id": "demo.skill",
            "content_hash": f"sha256:{'f' * 64}",
            "store": "ephemeral",
            "manifest_ref": "manifests/demo.skill.json",
        },
    )

    def fake_resume_skill(*_args: object, **_kwargs: object) -> object:
        spy_store.calls.append("resume_skill")

        class _Result:
            success = True
            started_at = None
            metrics: dict[str, object] = {"resumed": 1}

        return _Result()

    monkeypatch.setattr(graph_agent, "resume_skill", fake_resume_skill)

    result = EngineAdapter(transport="in_process").resume(
        {
            "skill_id": "demo.skill",
            "run_id": "run-resume-store",
            "human_input": "continue",
        }
    )

    assert result["status"] == "success"
    assert spy_store.calls == [
        "acquire_lease",
        "restore",
        "restore_checkpointer",
        "heartbeat",
        "resume_skill",
        "snapshot",
        "release",
    ]


def test_engine_adapter_resume_releases_runtime_state_lease_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_root = tmp_path / "skills" / "demo.skill"
    skill_root.mkdir(parents=True)
    (skill_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    artifact_root = tmp_path / "workspaces" / "default" / "ephemeral_run_skills" / ("e" * 64)
    artifact_root.mkdir(parents=True)
    (artifact_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")

    class _SkillResolver:
        def resolve_skill(self, _skill_id: str) -> Path:
            return skill_root

    class SpyRuntimeStateStore:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.lease = LeaseToken(
                lease_id="lease-run-resume-fail-1",
                owner_id="engine.resume:run-resume-fail",
                fencing_token=3,
                ttl_ms=30_000,
            )

        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            del owner_id, ttl_ms
            self.calls.append(f"acquire_lease:{run_id}")
            return self.lease

        def restore(self, run_id: str) -> StateSnapshot:
            self.calls.append(f"restore:{run_id}")
            return StateSnapshot(
                run_id=run_id,
                state={"checkpoint_id": "checkpoint-ready", "artifact_ref": _runtime_artifact_ref("e")},
                fencing_token=3,
            )

        def restore_checkpointer(self, snapshot: StateSnapshot) -> object:
            self.calls.append(f"restore_checkpointer:{snapshot.run_id}")
            return object()

        def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
            del lease
            self.calls.append(f"heartbeat:{run_id}")
            return self.lease

        def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken) -> StateSnapshot:
            del state, lease
            self.calls.append(f"snapshot:{run_id}")
            return StateSnapshot(run_id=run_id, state={}, fencing_token=3)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            del lease
            self.calls.append(f"release:{run_id}")

    spy_store = SpyRuntimeStateStore()
    monkeypatch.setattr(EngineAdapter, "_build_studio_skill_resolver", lambda _self: _SkillResolver())
    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: object())
    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: spy_store, raising=False)
    monkeypatch.setattr(
        EngineAdapter,
        "compile",
        lambda _self, _payload: {
            "artifact_id": "demo.skill",
            "content_hash": f"sha256:{'e' * 64}",
            "store": "ephemeral",
            "manifest_ref": "manifests/demo.skill.json",
        },
    )

    def fail_resume_skill(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("resume exploded")

    monkeypatch.setattr(graph_agent, "resume_skill", fail_resume_skill)

    with pytest.raises(StudioAdapterError) as exc_info:
        EngineAdapter(transport="in_process").resume(
            {
                "skill_id": "demo.skill",
                "run_id": "run-resume-fail",
                "human_input": "continue",
            }
        )

    assert exc_info.value.error_code == "engine.resume_failed"
    assert spy_store.calls[-1] == "release:run-resume-fail"


def test_engine_adapter_resume_preserves_main_error_when_release_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.runtime_state_store_local import LeaseToken

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    lease = LeaseToken(
        lease_id="lease-main-error",
        owner_id="engine.resume:run-main-error",
        fencing_token=1,
        ttl_ms=30_000,
    )

    class FailingRuntimeStateStore:
        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            del run_id, owner_id, ttl_ms
            return lease

        def restore(self, run_id: str) -> object:
            raise StudioAdapterError("state.not_found", {"run_id": run_id, "detail": "Snapshot not found"})

        def release(self, run_id: str, lease: LeaseToken) -> None:
            del lease
            raise StudioAdapterError("state.release_failed", {"run_id": run_id, "detail": "unlink failed"})

    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: FailingRuntimeStateStore())

    with pytest.raises(StudioAdapterError) as exc_info:
        EngineAdapter(transport="in_process").resume({"skill_id": "demo.skill", "run_id": "run-main-error"})

    assert exc_info.value.error_code == "state.not_found"
    suppressed = exc_info.value.error_payload["suppressed_errors"]
    assert suppressed == [
        {
            "error_code": "state.release_failed",
            "error_payload": {"run_id": "run-main-error", "detail": "unlink failed"},
        }
    ]


def test_engine_adapter_resume_surfaces_release_error_when_cleanup_is_only_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_root = tmp_path / "skills" / "demo.skill"
    skill_root.mkdir(parents=True)
    (skill_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    artifact_root = tmp_path / "workspaces" / "default" / "ephemeral_run_skills" / ("b" * 64)
    artifact_root.mkdir(parents=True)
    (artifact_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")

    class _SkillResolver:
        def resolve_skill(self, _skill_id: str) -> Path:
            return skill_root

    lease = LeaseToken(
        lease_id="lease-release-only",
        owner_id="engine.resume:run-release-only",
        fencing_token=1,
        ttl_ms=30_000,
    )

    class ReleaseFailingRuntimeStateStore:
        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            del run_id, owner_id, ttl_ms
            return lease

        def restore(self, run_id: str) -> StateSnapshot:
            return StateSnapshot(
                run_id=run_id,
                state={"artifact_ref": _runtime_artifact_ref("b"), "checkpoint_id": "cp-1"},
                fencing_token=1,
            )

        def restore_checkpointer(self, snapshot: StateSnapshot) -> object:
            del snapshot
            return object()

        def heartbeat(self, run_id: str, lease: LeaseToken) -> LeaseToken:
            del run_id
            return lease

        def snapshot(self, run_id: str, state: dict[str, Any], lease: LeaseToken) -> StateSnapshot:
            del lease
            return StateSnapshot(run_id=run_id, state=state, fencing_token=1)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            del lease
            raise StudioAdapterError("state.release_failed", {"run_id": run_id, "detail": "unlink failed"})

    def fake_resume_skill(*_args: object, **_kwargs: object) -> object:
        class _Result:
            success = True
            started_at = None
            metrics: dict[str, object] = {}

        return _Result()

    monkeypatch.setattr(EngineAdapter, "_build_studio_skill_resolver", lambda _self: _SkillResolver())
    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: object())
    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: ReleaseFailingRuntimeStateStore())
    monkeypatch.setattr(
        EngineAdapter,
        "compile",
        lambda _self, _payload: {
            "artifact_id": "demo.skill",
            "content_hash": f"sha256:{'b' * 64}",
            "store": "ephemeral",
            "manifest_ref": "manifests/demo.skill.json",
        },
    )
    monkeypatch.setattr(graph_agent, "resume_skill", fake_resume_skill)

    with pytest.raises(StudioAdapterError) as exc_info:
        EngineAdapter(transport="in_process").resume({"skill_id": "demo.skill", "run_id": "run-release-only"})

    assert exc_info.value.error_code == "state.release_failed"
    assert exc_info.value.error_payload == {"run_id": "run-release-only", "detail": "unlink failed"}


def test_engine_adapter_run_artifact_creates_runtime_state_snapshot_that_resume_consumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graph_agent
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.runtime_state_store_local import LocalRuntimeStateStore
    from graph_agent.core.checkpointer import reset_checkpointer

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_root = tmp_path / "skills" / "demo.skill"
    _write_logic_skill(skill_root)

    class _SkillResolver:
        def resolve_skill(self, skill_id: str) -> Path:
            assert skill_id == "demo.skill"
            return skill_root

    monkeypatch.setattr(EngineAdapter, "_build_studio_skill_resolver", lambda _self: _SkillResolver())
    monkeypatch.setattr(EngineAdapter, "_build_engine_llm_provider", lambda _self: object())

    reset_checkpointer()
    try:
        adapter = EngineAdapter(transport="in_process")
        artifact_ref = adapter.compile(
            {
                "skill_dir": str(skill_root),
                "skill_id": "demo.skill",
                "artifact_scope": "ephemeral",
            }
        )

        production_workspace = tmp_path / "workspaces" / "default" / "skills" / "demo.skill" / ".workspace"

        run_result = adapter.run_artifact(
            {
                "artifact_ref": artifact_ref,
                "workspace_dir": str(production_workspace),
                "thread_id": "run-prod-resume",
                "inputs": {"topic": "alpha"},
            }
        )

        assert run_result["run_id"] == "run-prod-resume"
        runtime_store = LocalRuntimeStateStore(root=tmp_path / "workspaces" / "default")
        snapshot = runtime_store.restore("run-prod-resume")
        assert snapshot.state["checkpoint_id"]
        assert snapshot.state["checkpoint_ns"] == ""
        assert snapshot.state["checkpointer_spec"].startswith("sqlite:")
        assert snapshot.state["checkpointer_spec"].endswith("skills/demo.skill/.workspace/runs/run-prod-resume/checkpoints.db")
        assert snapshot.state["artifact_ref"]["content_hash"] == artifact_ref["content_hash"]

        captured: dict[str, object] = {}

        def fake_resume_skill(*_args: object, **kwargs: object) -> object:
            captured.update(kwargs)

            class _Result:
                success = True
                started_at = None
                metrics: dict[str, object] = {"resumed": 1}

            return _Result()

        monkeypatch.setattr(graph_agent, "resume_skill", fake_resume_skill)

        resumed = adapter.resume(
            {
                "skill_id": "demo.skill",
                "run_id": "run-prod-resume",
                "human_input": "continue",
            }
        )

        assert resumed["status"] == "success"
        assert captured["workspace_dir"] == production_workspace
        assert captured["checkpoint_id"] == snapshot.state["checkpoint_id"]
        assert captured["checkpoint_ns"] == snapshot.state["checkpoint_ns"]
        assert captured["checkpointer"] is not None
    finally:
        reset_checkpointer()


def test_engine_adapter_run_artifact_persists_outputs_through_run_artifact_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from graph_agent.core.adapter_contracts import RunSession

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    def fake_run_artifact(request: object, **kwargs: object) -> RunSession:
        assert "run_artifact_store" in kwargs
        store = kwargs["run_artifact_store"]
        assert store is not None

        run_id = "run-123"
        store.begin_run(run_id, metadata={"artifact_id": "demo.skill"})
        payload = {
            "run_id": run_id,
            "success": True,
            "context": {"answer": 42},
            "metrics": {"total_tokens": 3},
        }
        refs = store.put_batch(run_id, {"outputs.json": json.dumps(payload).encode("utf-8")})
        store.seal_run(run_id)
        ref = refs["outputs.json"] if isinstance(refs, dict) else refs[0]

        return RunSession(
            run_id=run_id,
            event_stream_ref=f"stream://{run_id}",
            result_ref=ref.bytes_ref,
            status_ref=f"state://{run_id}/status",
        )

    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact)
    monkeypatch.setattr(
        EngineAdapter,
        "_build_runtime_state_store",
        lambda _self: SimpleNamespace(latest_checkpoint_state=lambda **_kwargs: None),
    )
    _seed_ephemeral_artifact_root(tmp_path, "f")

    adapter = EngineAdapter(transport="in_process")
    workspace_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill" / ".workspace"
    workspace_dir.mkdir(parents=True)
    result = adapter.run_artifact(
        {
            "artifact_ref": {
                "artifact_id": "demo.skill",
                "content_hash": f"sha256:{'f' * 64}",
                "store": "ephemeral",
                "manifest_ref": "manifests/demo.skill.json",
            },
            "inputs": {},
            "workspace_dir": str(workspace_dir),
            "thread_id": "run-123",
        }
    )

    assert result["run_id"] == "run-123"
    assert result["success"] is True
    assert result["context"] == {"answer": 42}
    assert result["metrics"] == {"total_tokens": 3}


def test_engine_adapter_run_artifact_does_not_fail_sealed_result_when_snapshot_spec_uses_different_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot
    from graph_agent.core.adapter_contracts import RunSession

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    def fake_run_artifact(request: object, **kwargs: object) -> RunSession:
        store = kwargs["run_artifact_store"]
        run_id = "artifact-run"
        store.begin_run(run_id, metadata={"artifact_id": "demo.skill"})
        payload = {
            "run_id": run_id,
            "success": True,
            "context": {"ok": True},
            "metrics": {},
        }
        refs = store.put_batch(run_id, {"outputs.json": json.dumps(payload).encode("utf-8")})
        store.seal_run(run_id)
        ref = refs["outputs.json"] if isinstance(refs, dict) else refs[0]
        assert request.execution_context["thread_id"] == "run-123"
        assert request.execution_context["checkpointer_spec"].endswith("runs/run-123/checkpoints.db")
        return RunSession(
            run_id=run_id,
            event_stream_ref=f"stream://{run_id}",
            result_ref=ref.bytes_ref,
            status_ref=f"state://{run_id}/status",
        )

    class RuntimeStateStore:
        def latest_checkpoint_state(self, *, run_id: str, checkpointer_spec: str) -> dict[str, str]:
            if not checkpointer_spec.endswith(f"runs/{run_id}/checkpoints.db"):
                raise StudioAdapterError(
                    "state.invalid_checkpointer",
                    {
                        "run_id": run_id,
                        "checkpointer_spec": checkpointer_spec,
                        "detail": "SQLite checkpointer path must target this run's checkpoints.db",
                    },
                )
            return {"checkpoint_id": "checkpoint-1", "checkpoint_ns": ""}

        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            assert run_id == "run-123"
            assert owner_id.startswith("engine.run_artifact:run-123:")
            assert ttl_ms == 30_000
            return LeaseToken(
                lease_id="lease-different-run-id",
                owner_id=owner_id,
                fencing_token=11,
                ttl_ms=ttl_ms,
            )

        def snapshot(self, run_id: str, state: dict[str, object], lease: LeaseToken) -> StateSnapshot:
            assert run_id == "run-123"
            assert state["checkpoint_id"] == "checkpoint-1"
            assert lease.lease_id == "lease-different-run-id"
            return StateSnapshot(run_id=run_id, state=state, fencing_token=lease.fencing_token)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            assert run_id == "run-123"
            assert lease.lease_id == "lease-different-run-id"

    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact)
    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: RuntimeStateStore())
    _seed_ephemeral_artifact_root(tmp_path, "f")

    adapter = EngineAdapter(transport="in_process")
    workspace_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill" / ".workspace"
    workspace_dir.mkdir(parents=True)

    result = adapter.run_artifact(
        {
            "artifact_ref": {
                "artifact_id": "demo.skill",
                "content_hash": f"sha256:{'f' * 64}",
                "store": "ephemeral",
                "manifest_ref": "manifests/demo.skill.json",
            },
            "inputs": {},
            "workspace_dir": str(workspace_dir),
            "thread_id": "run-123",
        }
    )

    assert result["run_id"] == "artifact-run"
    assert result["success"] is True
    assert result["context"] == {"ok": True}


def test_engine_adapter_run_artifact_snapshots_runtime_state_for_owner_run_id_when_result_run_id_differs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.runtime_state_store_local import LeaseToken, StateSnapshot
    from graph_agent.core.adapter_contracts import RunSession

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    expected_result_ref: str | None = None

    def fake_run_artifact(request: object, **kwargs: object) -> RunSession:
        nonlocal expected_result_ref
        store = kwargs["run_artifact_store"]
        run_id = "artifact-run"
        store.begin_run(run_id, metadata={"artifact_id": "demo.skill"})
        payload = {
            "run_id": run_id,
            "success": True,
            "context": {"ok": True},
            "metrics": {},
        }
        refs = store.put_batch(run_id, {"outputs.json": json.dumps(payload).encode("utf-8")})
        store.seal_run(run_id)
        ref = refs["outputs.json"] if isinstance(refs, dict) else refs[0]
        expected_result_ref = ref.bytes_ref
        assert request.execution_context["thread_id"] == "run-123"
        assert request.execution_context["checkpointer_spec"].endswith("runs/run-123/checkpoints.db")
        return RunSession(
            run_id=run_id,
            event_stream_ref=f"stream://{run_id}",
            result_ref=ref.bytes_ref,
            status_ref=f"state://{run_id}/status",
        )

    runtime_lease = LeaseToken(
        lease_id="lease-owner-run-id",
        owner_id="engine.run_artifact:run-123",
        fencing_token=29,
        ttl_ms=30_000,
    )

    class RuntimeStateStore:
        def __init__(self) -> None:
            self.snapshot_calls: list[tuple[str, dict[str, object]]] = []

        def latest_checkpoint_state(self, *, run_id: str, checkpointer_spec: str) -> dict[str, str]:
            assert run_id == "run-123"
            assert checkpointer_spec.endswith("runs/run-123/checkpoints.db")
            return {"checkpoint_id": "checkpoint-1", "checkpoint_ns": ""}

        def acquire_lease(self, run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken:
            assert run_id == "run-123"
            assert owner_id.startswith("engine.run_artifact:run-123:")
            assert ttl_ms == 30_000
            return runtime_lease

        def snapshot(self, run_id: str, state: dict[str, object], lease: LeaseToken) -> StateSnapshot:
            assert run_id == "run-123"
            assert lease is runtime_lease
            self.snapshot_calls.append((run_id, state))
            return StateSnapshot(run_id=run_id, state=state, fencing_token=runtime_lease.fencing_token)

        def release(self, run_id: str, lease: LeaseToken) -> None:
            assert run_id == "run-123"
            assert lease is runtime_lease

    runtime_state_store = RuntimeStateStore()
    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact)
    monkeypatch.setattr(EngineAdapter, "_build_runtime_state_store", lambda _self: runtime_state_store)
    _seed_ephemeral_artifact_root(tmp_path, "e")

    adapter = EngineAdapter(transport="in_process")
    workspace_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill" / ".workspace"
    workspace_dir.mkdir(parents=True)

    result = adapter.run_artifact(
        {
            "artifact_ref": {
                "artifact_id": "demo.skill",
                "content_hash": f"sha256:{'e' * 64}",
                "store": "ephemeral",
                "manifest_ref": "manifests/demo.skill.json",
            },
            "inputs": {},
            "workspace_dir": str(workspace_dir),
            "thread_id": "run-123",
        }
    )

    assert result["run_id"] == "artifact-run"
    assert result["success"] is True
    assert len(runtime_state_store.snapshot_calls) == 1
    snapshot_run_id, snapshot_state = runtime_state_store.snapshot_calls[0]
    assert snapshot_run_id == "run-123"
    assert snapshot_state["run_id"] == "run-123"
    expected_checkpointer = (workspace_dir / "runs" / "run-123" / "checkpoints.db").as_posix()
    assert snapshot_state["checkpointer_spec"] == f"sqlite:{expected_checkpointer}"
    assert snapshot_state["checkpoint_id"] == "checkpoint-1"
    assert snapshot_state["checkpoint_ns"] == ""
    assert snapshot_state["result_ref"] == expected_result_ref
    assert snapshot_state["status"] == "success"
    assert snapshot_state["metrics"] == {}
    assert snapshot_state["artifact_ref"] == {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'e' * 64}",
        "store": "ephemeral",
        "manifest_ref": "manifests/demo.skill.json",
    }


@pytest.mark.parametrize("error_code", ["state.invalid_checkpointer", "state.not_found"])
def test_engine_adapter_run_artifact_surfaces_typed_runtime_state_snapshot_error_after_sealed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_code: str,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from graph_agent.core.adapter_contracts import RunSession

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    def fake_run_artifact(request: object, **kwargs: object) -> RunSession:
        store = kwargs["run_artifact_store"]
        run_id = request.execution_context["thread_id"]
        store.begin_run(run_id, metadata={"artifact_id": "demo.skill"})
        payload = {
            "run_id": run_id,
            "success": True,
            "context": {"ok": True},
            "metrics": {},
        }
        refs = store.put_batch(run_id, {"outputs.json": json.dumps(payload).encode("utf-8")})
        store.seal_run(run_id)
        ref = refs["outputs.json"] if isinstance(refs, dict) else refs[0]
        return RunSession(
            run_id=run_id,
            event_stream_ref=f"stream://{run_id}",
            result_ref=ref.bytes_ref,
            status_ref=f"state://{run_id}/status",
        )

    def fail_snapshot_runtime_state(
        self: EngineAdapter,
        *,
        run_id: str,
        run_payload: dict[str, Any],
        artifact_ref_data: dict[str, Any],
        result_ref: str | None,
        checkpointer_spec: str | None,
    ) -> None:
        del self, run_payload, artifact_ref_data, result_ref, checkpointer_spec
        raise StudioAdapterError(
            error_code,
            {
                "run_id": run_id,
                "detail": f"typed runtime-state snapshot failure: {error_code}",
            },
        )

    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact)
    monkeypatch.setattr(EngineAdapter, "_snapshot_runtime_state_after_run", fail_snapshot_runtime_state)
    _seed_ephemeral_artifact_root(tmp_path, "d")

    adapter = EngineAdapter(transport="in_process")
    workspace_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill" / ".workspace"
    workspace_dir.mkdir(parents=True)

    with pytest.raises(StudioAdapterError) as exc_info:
        adapter.run_artifact(
            {
                "artifact_ref": {
                    "artifact_id": "demo.skill",
                    "content_hash": f"sha256:{'d' * 64}",
                    "store": "ephemeral",
                    "manifest_ref": "manifests/demo.skill.json",
                },
                "inputs": {},
                "workspace_dir": str(workspace_dir),
                "thread_id": "run-typed-snapshot-error",
            }
        )

    assert exc_info.value.error_code == error_code
    assert exc_info.value.error_payload == {
        "run_id": "run-typed-snapshot-error",
        "detail": f"typed runtime-state snapshot failure: {error_code}",
    }


def test_engine_adapter_predict_artifact_rejects_file_result_ref_business_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from graph_agent.core.adapter_contracts import RunSession

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    file_result = tmp_path / "result.json"
    file_result.write_text(
        json.dumps(
            {
                "run_id": "predict-file-ref",
                "success": True,
                "skill_id": "demo.skill",
                "context": {"prediction": "legacy-file"},
            }
        ),
        encoding="utf-8",
    )

    def fake_predict_artifact(_request: object, **kwargs: object) -> RunSession:
        assert kwargs.get("run_artifact_store") is not None
        return RunSession(
            run_id="predict-file-ref",
            event_stream_ref="stream://predict-file-ref",
            result_ref=f"file://{file_result}",
            status_ref="state://predict-file-ref/status",
        )

    monkeypatch.setattr(engine_module, "predict_artifact", fake_predict_artifact)
    _seed_ephemeral_artifact_root(tmp_path, "8")

    adapter = EngineAdapter(transport="in_process")
    with pytest.raises(StudioAdapterError) as exc_info:
        adapter.predict_artifact(
            {
                "artifact_ref": {
                    "artifact_id": "demo.skill",
                    "content_hash": f"sha256:{'8' * 64}",
                    "store": "ephemeral",
                    "manifest_ref": "manifests/demo.skill.json",
                },
                "inputs": {},
                "workspace_dir": str(tmp_path / "workspace"),
                "thread_id": "predict-file-ref",
            }
        )

    assert exc_info.value.error_code == "artifact.unsupported_result_ref"
    assert exc_info.value.error_payload["result_ref"] == f"file://{file_result}"


def test_engine_adapter_run_artifact_rejects_file_result_ref_business_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    from app.core import config
    from app.core.adapters.engine import EngineAdapter
    from app.core.adapters.http_transport import StudioAdapterError
    from graph_agent.core.adapter_contracts import RunSession

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    file_result = tmp_path / "result.json"
    file_result.write_text(
        json.dumps(
            {
                "run_id": "run-file-ref",
                "success": True,
                "skill_id": "demo.skill",
                "context": {"answer": "legacy-file"},
            }
        ),
        encoding="utf-8",
    )

    def fake_run_artifact(_request: object, **kwargs: object) -> RunSession:
        assert kwargs.get("run_artifact_store") is not None
        return RunSession(
            run_id="run-file-ref",
            event_stream_ref="stream://run-file-ref",
            result_ref=f"file://{file_result}",
            status_ref="state://run-file-ref/status",
        )

    monkeypatch.setattr(engine_module, "run_artifact", fake_run_artifact)
    _seed_ephemeral_artifact_root(tmp_path, "8")

    adapter = EngineAdapter(transport="in_process")
    with pytest.raises(StudioAdapterError) as exc_info:
        adapter.run_artifact(
            {
                "artifact_ref": {
                    "artifact_id": "demo.skill",
                    "content_hash": f"sha256:{'8' * 64}",
                    "store": "ephemeral",
                    "manifest_ref": "manifests/demo.skill.json",
                },
                "inputs": {},
                "workspace_dir": str(tmp_path / "workspace"),
                "thread_id": "run-file-ref",
            }
        )

    assert exc_info.value.error_code == "artifact.unsupported_result_ref"
    assert exc_info.value.error_payload["result_ref"] == f"file://{file_result}"


def test_graph_agent_runner_persists_outputs_through_local_run_artifact_store(tmp_path: Path) -> None:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from graph_agent.core.adapter_contracts import RunArtifactRequest
    from graph_agent.core.artifacts import ArtifactRef
    from graph_agent.core.runner import run_artifact

    store = LocalRunArtifactStore(root=tmp_path)
    request = RunArtifactRequest(
        artifact_ref=ArtifactRef(
            artifact_id="demo.skill",
            content_hash=f"sha256:{'1' * 64}",
            store="ephemeral",
            manifest_ref="object://manifest.json",
            source_map_ref="object://source-map.json",
        ),
        inputs={"topic": "runner"},
        execution_context={"thread_id": "real-runner-store"},
        idempotency_key="idem-real-runner-store",
    )

    session = run_artifact(
        request,
        run_artifact_store=store,
        artifact_executor=lambda _request: {
            "run_id": "real-runner-store",
            "success": True,
            "context": {"answer": "from real runner"},
            "metrics": {"total_tokens": 7},
        },
    )

    assert session.result_ref
    assert session.result_ref.startswith("bytes://")
    stored = store.get_object(hash=session.result_ref.removeprefix("bytes://"))
    payload = json.loads(stored.decode("utf-8"))
    assert payload["success"] is True
    assert payload["context"] == {"answer": "from real runner"}
    assert payload["metrics"] == {"total_tokens": 7}


def test_predictor_persists_predict_result_through_run_artifact_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.predictor as predictor_module
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.services.predictor import PredictorService
    from graph_agent.core.result import RunResult

    skill_dir = tmp_path / "skills" / "demo.skill"
    skill_dir.mkdir(parents=True)

    class FakeAdapter:
        def compile(self, payload: dict[str, Any]) -> dict[str, Any]:
            assert payload["skill_id"] == "demo.skill"
            return {
                "artifact_id": "demo.skill",
                "content_hash": f"sha256:{'7' * 64}",
                "store": "ephemeral",
                "manifest_ref": "file:///tmp/manifest.json",
                "source_map_ref": "file:///tmp/source-map.json",
            }

        def predict_artifact(self, payload: dict[str, Any]) -> RunResult:
            assert payload["artifact_ref"]["content_hash"] == f"sha256:{'7' * 64}"
            return RunResult(
                success=True,
                run_id="predict-store-run",
                skill_id="demo.skill",
                context={"prediction": "ok"},
                source="predict",
            )

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda _skill_id: skill_dir)
    monkeypatch.setattr(predictor_module, "build_engine_adapter", lambda: FakeAdapter())

    result = PredictorService().dispatch_predict_job("demo.skill", input_data={"topic": "store"})

    assert result.run_id == "predict-store-run"
    manifest_path = skill_dir / ".workspace" / "runs" / result.run_id / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result_ref = manifest["object_refs"]["result.json"]
    stored = LocalRunArtifactStore(root=skill_dir / ".workspace").get_object(hash=result_ref["content_hash"])
    payload = json.loads(stored.decode("utf-8"))

    assert payload["run_id"] == "predict-store-run"
    assert payload["context"] == {"prediction": "ok"}


def test_predictor_preserves_artifact_identity_in_runtime_payload_and_predict_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.predictor as predictor_module
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.services.predictor import PredictorService
    from graph_agent.core.result import RunResult

    skill_dir = tmp_path / "skills" / "demo.skill"
    skill_dir.mkdir(parents=True)
    artifact_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'1' * 64}",
        "store": "ephemeral",
        "manifest_ref": "file:///tmp/manifest.json",
        "source_map_ref": "file:///tmp/source-map.json",
        "execution_fingerprint": f"sha256:{'2' * 64}",
        "version": None,
    }
    captured_payload: dict[str, Any] = {}

    class FakeAdapter:
        def compile(self, payload: dict[str, Any]) -> dict[str, Any]:
            assert payload["skill_id"] == "demo.skill"
            return dict(artifact_ref)

        def predict_artifact(self, payload: dict[str, Any]) -> RunResult:
            captured_payload.update(payload)
            return RunResult(
                success=True,
                run_id="predict-identity-run",
                skill_id="demo.skill",
                context={"prediction": "ok"},
                source="predict",
            )

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda _skill_id: skill_dir)
    monkeypatch.setattr(predictor_module, "build_engine_adapter", lambda: FakeAdapter())

    result = PredictorService().dispatch_predict_job("demo.skill", input_data={"topic": "identity"})

    assert captured_payload["artifact_ref"] == artifact_ref
    result_payload = result.model_dump(mode="json")
    assert result_payload["artifact_ref"] == artifact_ref
    assert result_payload["source_map_ref"] == artifact_ref["source_map_ref"]
    assert result_payload["execution_fingerprint"] == artifact_ref["execution_fingerprint"]

    manifest_path = skill_dir / ".workspace" / "runs" / result.run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["metadata"]["artifact_ref"] == artifact_ref
    assert manifest["metadata"]["source_map_ref"] == artifact_ref["source_map_ref"]
    assert manifest["metadata"]["execution_fingerprint"] == artifact_ref["execution_fingerprint"]

    result_ref = manifest["object_refs"]["result.json"]
    stored = LocalRunArtifactStore(root=skill_dir / ".workspace").get_object(hash=result_ref["content_hash"])
    stored_payload = json.loads(stored.decode("utf-8"))
    assert stored_payload["artifact_ref"] == artifact_ref
    assert stored_payload["execution_fingerprint"] == artifact_ref["execution_fingerprint"]


def test_run_metadata_preserves_artifact_identity_for_source_and_release_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.run_manager as run_manager_module
    import app.services.skills as skills_module
    from app.core import config
    from app.services.predict_gate import record_predict_pass
    from app.services.run_manager import RunManager

    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    skill_dir.mkdir(parents=True)
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    monkeypatch.setattr(config, "DEFAULT_SKILLS_ROOT", tmp_path / "Skills")
    source_artifact_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'3' * 64}",
        "store": "ephemeral",
        "manifest_ref": "file:///tmp/source-manifest.json",
        "source_map_ref": "file:///tmp/source-map.json",
        "execution_fingerprint": f"sha256:{'4' * 64}",
        "version": None,
    }
    release_artifact_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{'5' * 64}",
        "store": "product",
        "manifest_ref": "file:///tmp/release-manifest.json",
        "source_map_ref": "file:///tmp/release-source-map.json",
        "execution_fingerprint": f"sha256:{'6' * 64}",
        "version": "1.0.0",
    }

    class FakeAdapter:
        def compile(self, _payload: dict[str, Any]) -> dict[str, Any]:
            return dict(source_artifact_ref)

    class InlineProcess:
        def __init__(self, target: Any, args: tuple[Any, ...]) -> None:
            self._target = target
            self._args = args

        def start(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            del timeout

    manager = RunManager()
    manager.process_factory = InlineProcess
    manager.queue_factory = lambda: SimpleNamespace(put=lambda _item: None)
    manager.worker = lambda *_args: None
    async def noop_async(*_args: Any, **_kwargs: Any) -> None:
        return None

    manager._save_run_metadata = noop_async  # type: ignore[method-assign]
    manager._drain_process_queue = noop_async  # type: ignore[method-assign]
    monkeypatch.setattr(run_manager_module, "build_engine_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(skills_module, "resolve_skill_dir", lambda _skill_id: skill_dir)
    monkeypatch.setattr(run_manager_module, "resolve_skill_dir", lambda _skill_id: skill_dir)
    record_predict_pass(skill_dir, "demo.skill", "predict-pass", content_hash=source_artifact_ref["content_hash"])

    source_metadata = asyncio.run(
        manager.start_run("demo.skill", run_manager_module.RunRequest(input_data={"topic": "source"}))
    )
    release_metadata = asyncio.run(
        manager.start_run_from_artifact(
            "demo.skill",
            run_manager_module.RunRequest(input_data={"topic": "release"}),
            artifact_ref=dict(release_artifact_ref),
        )
    )

    for metadata, expected, expected_skill_dir in (
        (source_metadata, source_artifact_ref, skill_dir),
        (release_metadata, release_artifact_ref, config.DEFAULT_SKILLS_ROOT / "demo.skill"),
    ):
        assert metadata.artifact_ref == expected
        assert metadata.source_map_ref == expected["source_map_ref"]
        assert metadata.execution_fingerprint == expected["execution_fingerprint"]
        metadata_path = expected_skill_dir / ".workspace" / "runs" / metadata.run_id / "run_metadata.json"
        saved = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert saved["artifact_ref"] == expected
        assert saved["source_map_ref"] == expected["source_map_ref"]
        assert saved["execution_fingerprint"] == expected["execution_fingerprint"]


def test_run_detail_reads_final_context_from_sealed_run_artifact_store_not_legacy_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-store-detail"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(run_id="run-store-detail", status="success", started_at="2026-06-17T00:00:00Z")
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "input_data.json").write_text('{"topic": "legacy"}', encoding="utf-8")
    (run_dir / "final_state.json").write_text('{"answer": "legacy-file"}', encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run("run-store-detail", metadata={"artifact_id": "demo.skill"})
    store.put_batch(
        "run-store-detail",
        {"final_state.json": b'{"answer": "sealed-store"}', "trace.jsonl": b""},
    )
    store.seal_run("run-store-detail")

    detail = RunManager().get_run_detail("demo.skill", "run-store-detail")

    assert detail.final_context == {"answer": "sealed-store"}


def test_run_detail_reads_input_data_from_sealed_run_artifact_store_not_legacy_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-store-input-detail"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(run_id="run-store-input-detail", status="success", started_at="2026-06-17T00:00:00Z")
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "input_data.json").write_text('{"topic": "legacy"}', encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run("run-store-input-detail", metadata={"artifact_id": "demo.skill"})
    store.put_batch(
        "run-store-input-detail",
        {"input_data.json": b'{"topic": "sealed-store", "count": 2}', "trace.jsonl": b"", "final_state.json": b"{}"},
    )
    store.seal_run("run-store-input-detail")

    detail = RunManager().get_run_detail("demo.skill", "run-store-input-detail")

    assert detail.input_data == {"topic": "sealed-store", "count": 2}


def test_run_detail_reads_trace_and_artifact_list_from_sealed_run_artifact_store_not_legacy_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-store-trace-detail"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(run_id="run-store-trace-detail", status="success", started_at="2026-06-17T00:00:00Z")
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "input_data.json").write_text('{"topic": "legacy"}', encoding="utf-8")
    (run_dir / "final_state.json").write_text('{"answer": "legacy-file"}', encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(
        '{"schema_version":"1.0","event_type":"phase_start","phase_name":"legacy"}\n',
        encoding="utf-8",
    )
    legacy_artifacts = run_dir / "artifacts"
    legacy_artifacts.mkdir()
    (legacy_artifacts / "legacy-output.json").write_text('{"answer": "legacy-artifact"}', encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run("run-store-trace-detail", metadata={"artifact_id": "demo.skill"})
    store.put_batch(
        "run-store-trace-detail",
        {
            "final_state.json": b'{"answer": "sealed-store"}',
            "trace.jsonl": (
                b'{"schema_version":"1.0","event_type":"phase_start","phase_name":"sealed"}\n'
                b'{"schema_version":"1.0","event_type":"phase_end","phase_name":"sealed","status":"success"}\n'
            ),
            "artifacts/output.json": b'{"answer": "sealed-artifact"}',
        },
    )
    store.seal_run("run-store-trace-detail")
    (run_dir / "trace.jsonl").unlink()
    (legacy_artifacts / "legacy-output.json").write_text('{"answer": "polluted"}', encoding="utf-8")

    detail = RunManager().get_run_detail("demo.skill", "run-store-trace-detail")

    assert detail.final_context == {"answer": "sealed-store"}
    assert [event.event_type for event in detail.events] == ["phase_start", "phase_end"]
    assert [event.payload["phase_name"] for event in detail.events] == ["sealed", "sealed"]
    assert detail.artifacts == ["artifacts/output.json"]


def test_run_detail_does_not_recreate_latest_snapshot_during_read_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-read-no-latest"
    latest_dir = skill_dir / ".workspace" / "runs" / "latest"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(run_id="run-read-no-latest", status="success", started_at="2026-06-17T00:00:00Z")
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run("run-read-no-latest", metadata={"artifact_id": "demo.skill"})
    store.put_batch("run-read-no-latest", {"final_state.json": b"{}", "trace.jsonl": b""})
    store.seal_run("run-read-no-latest")

    detail = RunManager().get_run_detail("demo.skill", "run-read-no-latest")

    assert detail.metadata.run_id == "run-read-no-latest"
    assert not latest_dir.exists()


def test_run_detail_validates_artifact_list_object_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-corrupt-listed-artifact"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(
        run_id="run-corrupt-listed-artifact",
        status="success",
        started_at="2026-06-17T00:00:00Z",
    )
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    refs = store.put_batch(
        "run-corrupt-listed-artifact",
        {
            "final_state.json": b'{"answer": "sealed-store"}',
            "trace.jsonl": b"",
            "artifacts/output.json": b'{"answer": "sealed-artifact"}',
        },
    )
    artifact_ref = refs["artifacts/output.json"] if isinstance(refs, dict) else refs[0]
    store.seal_run("run-corrupt-listed-artifact")
    sha_val = artifact_ref.content_hash.split(":", 1)[1]
    (skill_dir / ".workspace" / "blobs" / sha_val).write_bytes(b"corrupted")

    with pytest.raises(StudioAdapterError) as exc_info:
        RunManager().get_run_detail("demo.skill", "run-corrupt-listed-artifact")

    assert exc_info.value.error_code == "artifact.hash_mismatch"


def test_run_detail_filters_none_and_non_artifact_object_ref_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-null-path-artifact"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(
        run_id="run-null-path-artifact",
        status="success",
        started_at="2026-06-17T00:00:00Z",
    )
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    refs = store.put_batch(
        "run-null-path-artifact",
        {
            "final_state.json": b'{"answer": "sealed-store"}',
            "trace.jsonl": b"",
            "logs/output.json": b"not an artifact",
            "artifacts/output.json": b'{"answer": "sealed-artifact"}',
        },
    )
    store.seal_run("run-null-path-artifact")

    none_path_ref = refs["logs/output.json"].model_copy(update={"path": None})
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["object_refs"]["none-path"] = none_path_ref.model_dump(mode="json")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    detail = RunManager().get_run_detail("demo.skill", "run-null-path-artifact")

    assert detail.artifacts == ["artifacts/output.json"]


def test_run_detail_exposes_trace_artifact_hash_mismatch_without_legacy_trace_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-corrupt-trace-detail"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(run_id="run-corrupt-trace-detail", status="success", started_at="2026-06-17T00:00:00Z")
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(
        '{"schema_version":"1.0","event_type":"phase_start","phase_name":"legacy"}\n',
        encoding="utf-8",
    )

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    refs = store.put_batch(
        "run-corrupt-trace-detail",
        {
            "final_state.json": b'{"answer": "sealed-store"}',
            "trace.jsonl": b'{"schema_version":"1.0","event_type":"phase_start","phase_name":"sealed"}\n',
        },
    )
    ref = refs["trace.jsonl"] if isinstance(refs, dict) else refs[0]
    store.seal_run("run-corrupt-trace-detail")
    sha_val = ref.content_hash.split(":", 1)[1]
    (skill_dir / ".workspace" / "blobs" / sha_val).write_bytes(b"corrupted")

    with pytest.raises(StudioAdapterError) as exc_info:
        RunManager().get_run_detail("demo.skill", "run-corrupt-trace-detail")

    assert exc_info.value.error_code == "artifact.hash_mismatch"


def test_run_detail_exposes_artifact_hash_mismatch_without_legacy_json_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-corrupt-detail"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(run_id="run-corrupt-detail", status="success", started_at="2026-06-17T00:00:00Z")
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "final_state.json").write_text('{"answer": "legacy-fallback"}', encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    refs = store.put_batch("run-corrupt-detail", {"final_state.json": b'{"answer": "sealed-store"}'})
    ref = refs["final_state.json"] if isinstance(refs, dict) else refs[0]
    store.seal_run("run-corrupt-detail")
    sha_val = ref.content_hash.split(":", 1)[1]
    (skill_dir / ".workspace" / "blobs" / sha_val).write_bytes(b"corrupted")

    with pytest.raises(StudioAdapterError) as exc_info:
        RunManager().get_run_detail("demo.skill", "run-corrupt-detail")

    assert exc_info.value.error_code == "artifact.hash_mismatch"


def test_run_detail_exposes_missing_sealed_artifact_without_legacy_json_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-missing-detail"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(run_id="run-missing-detail", status="success", started_at="2026-06-17T00:00:00Z")
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "final_state.json").write_text('{"answer": "legacy-fallback"}', encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    refs = store.put_batch("run-missing-detail", {"final_state.json": b'{"answer": "sealed-store"}'})
    ref = refs["final_state.json"] if isinstance(refs, dict) else refs[0]
    store.seal_run("run-missing-detail")
    sha_val = ref.content_hash.split(":", 1)[1]
    (skill_dir / ".workspace" / "blobs" / sha_val).unlink()

    with pytest.raises(StudioAdapterError) as exc_info:
        RunManager().get_run_detail("demo.skill", "run-missing-detail")

    assert exc_info.value.error_code == "artifact.not_found"


def test_run_detail_exposes_corrupt_sealed_json_without_legacy_json_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-corrupt-json-detail"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(run_id="run-corrupt-json-detail", status="success", started_at="2026-06-17T00:00:00Z")
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "final_state.json").write_text('{"answer": "legacy-fallback"}', encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.put_batch("run-corrupt-json-detail", {"final_state.json": b"{not valid json"})
    store.seal_run("run-corrupt-json-detail")

    with pytest.raises(StudioAdapterError) as exc_info:
        RunManager().get_run_detail("demo.skill", "run-corrupt-json-detail")

    assert exc_info.value.error_code == "artifact.corrupt_json"


def test_run_detail_exposes_corrupt_sealed_unicode_without_legacy_json_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-corrupt-unicode-detail"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(run_id="run-corrupt-unicode-detail", status="success", started_at="2026-06-17T00:00:00Z")
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "final_state.json").write_text('{"answer": "legacy-fallback"}', encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.put_batch("run-corrupt-unicode-detail", {"final_state.json": b"\xff"})
    store.seal_run("run-corrupt-unicode-detail")

    with pytest.raises(StudioAdapterError) as exc_info:
        RunManager().get_run_detail("demo.skill", "run-corrupt-unicode-detail")

    assert exc_info.value.error_code == "artifact.corrupt_json"


def test_list_runs_builds_missing_input_summary_from_sealed_run_artifact_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunManager

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    run_dir = skill_dir / ".workspace" / "runs" / "run-summary-store"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(run_id="run-summary-store", status="success", started_at="2026-06-17T00:00:00Z")
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
    (run_dir / "input_data.json").write_text('{"topic": "legacy"}', encoding="utf-8")

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run("run-summary-store", metadata={"artifact_id": "demo.skill"})
    store.put_batch(
        "run-summary-store",
        {"input_data.json": b'{"topic": "sealed topic", "count": 7}', "final_state.json": b"{}", "trace.jsonl": b""},
    )
    store.seal_run("run-summary-store")

    response = RunManager().list_runs("demo.skill")

    assert response.total == 1
    assert response.runs[0].run_id == "run-summary-store"
    assert response.runs[0].input_summary == "count=7, topic=sealed topic"


def _source(relative_path: str) -> str:
    return (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _function_calls_any(function: ast.FunctionDef | ast.AsyncFunctionDef, callee_names: set[str]) -> bool:
    return any(
        isinstance(node, ast.Call) and _call_name(node.func) in callee_names
        for node in ast.walk(function)
    )


def _dict_payloads(call: ast.Call) -> list[ast.Dict]:
    payloads: list[ast.Dict] = []
    for value in [*call.args, *(keyword.value for keyword in call.keywords)]:
        if isinstance(value, ast.Dict):
            payloads.append(value)
    return payloads


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_logic_skill(root: Path) -> None:
    _write_text(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: demo
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - draft
---
<phase depends_on="input" output>draft</phase>
""",
    )
    _write_text(
        root / "phases" / "draft" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
---
<action>draft</action>
""",
    )
    _write_text(
        root / "phases" / "draft" / "actions" / "draft.py",
        "def draft(inputs):\n"
        "    return {'answer': 'draft:' + str(inputs.get('topic', ''))}\n",
    )


def _zip_skill_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "GRAPH.md",
            """---
schema_version: "v0.3.0"
name: demo
phases:
  - draft
---
<phase depends_on="input" output>draft</phase>
""",
        )
        archive.writestr("phases/draft/LOGIC.md", "---\n---\n<action>draft</action>\n")
    return buffer.getvalue()


def _seed_ephemeral_artifact_root(tmp_path: Path, hash_char: str) -> Path:
    roots = {tmp_path / "workspaces" / "default", _storage_root(tmp_path)}
    seeded_root: Path | None = None
    for root in roots:
        artifact_root = root / "ephemeral_run_skills" / (hash_char * 64)
        artifact_root.mkdir(parents=True, exist_ok=True)
        (artifact_root / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
        seeded_root = artifact_root
    assert seeded_root is not None
    return seeded_root


def _storage_root(tmp_path: Path) -> Path:
    import app.core.adapters.engine as engine_module

    resolved = engine_module._studio_storage_root()
    expected = tmp_path / "workspaces" / "default"
    return resolved if resolved != expected else expected


def _read_json_ref(ref: str) -> dict[str, Any]:
    parsed = urlparse(ref)
    assert parsed.scheme == "file"
    raw_path = f"//{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
    path = Path(url2pathname(unquote(raw_path)))
    assert path.is_file()
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_artifact_ref(hash_char: str) -> dict[str, Any]:
    return {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{hash_char * 64}",
        "store": "ephemeral",
        "manifest_ref": "manifests/demo.skill.json",
        "source_map_ref": "",
        "version": None,
    }
