from __future__ import annotations

import ast
import json as jsonlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.core.adapters.loopback_host import LOOPBACK_TOKEN_HEADER
from app.core.backends import clear_backend_caches
from app.services import predictor as predictor_module
from app.services import run_manager as run_manager_module
from app.services.predictor import PredictorService

BUSINESS_PATH_ROOTS = (Path("app/services"), Path("app/routers"))


@pytest.fixture(autouse=True)
def _clear_backend_config_cache() -> Iterator[None]:
    clear_backend_caches()
    yield
    clear_backend_caches()


class _Queue:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def put(self, item: dict[str, Any]) -> None:
        self.items.append(item)


def test_engine_business_paths_do_not_hardcode_in_process_transport() -> None:
    offenders: list[str] = []
    backend_root = Path(__file__).resolve().parents[2]

    for root in BUSINESS_PATH_ROOTS:
        for relative_path in sorted((backend_root / root).rglob("*.py")):
            relative_path = relative_path.relative_to(backend_root)
            path = backend_root / relative_path
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not _is_engine_adapter_call(node.func):
                    continue
                for keyword in node.keywords:
                    if (
                        keyword.arg == "transport"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value == "in_process"
                    ):
                        offenders.append(f"{relative_path}:{node.lineno}")

    assert offenders == [], "Business services still hardcode in_process EngineAdapter: " + ", ".join(offenders)


def test_gateway_business_paths_do_not_hardcode_in_process_transport() -> None:
    offenders: list[str] = []
    backend_root = Path(__file__).resolve().parents[2]

    for root in BUSINESS_PATH_ROOTS:
        for relative_path in sorted((backend_root / root).rglob("*.py")):
            relative_path = relative_path.relative_to(backend_root)
            path = backend_root / relative_path
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not _is_gateway_adapter_call(node.func):
                    continue
                for keyword in node.keywords:
                    if (
                        keyword.arg == "transport"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value == "in_process"
                    ):
                        offenders.append(f"{relative_path}:{node.lineno}")

    assert offenders == [], "Business services still hardcode in_process GatewayAdapter: " + ", ".join(offenders)


def test_gateway_business_paths_do_not_bypass_gateway_adapter_with_model_resolver() -> None:
    offenders: list[str] = []
    backend_root = Path(__file__).resolve().parents[2]
    allowed_paths = {Path("app/services/gateway_resolver.py")}

    for root in BUSINESS_PATH_ROOTS:
        for relative_path in sorted((backend_root / root).rglob("*.py")):
            relative_path = relative_path.relative_to(backend_root)
            if relative_path in allowed_paths:
                continue
            path = backend_root / relative_path
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        if (
                            module == "app.services.gateway_resolver"
                            and alias.name == "build_gateway_model_resolver"
                        ):
                            offenders.append(f"{relative_path}:{node.lineno}:build_gateway_model_resolver import")
                elif isinstance(node, ast.Call):
                    if _is_name_or_attr(node.func, "build_gateway_model_resolver"):
                        offenders.append(f"{relative_path}:{node.lineno}:build_gateway_model_resolver call")
                    if _is_name_or_attr(node.func, "ModelResolver"):
                        offenders.append(f"{relative_path}:{node.lineno}:ModelResolver call")

    assert offenders == [], "Business services bypass GatewayAdapter with Gateway resolver: " + ", ".join(offenders)


def test_predictor_uses_configured_http_loopback_engine_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config
    from app.core.adapters.engine import RunResult

    _configure_http_loopback(monkeypatch)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("# Skill\n", encoding="utf-8")
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda _skill_id: skill_dir)

    import app.core.adapters.engine as engine_adapter_module

    init_calls: list[dict[str, Any]] = []
    predict_payloads: list[dict[str, Any]] = []
    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    art_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }

    def fake_init(self: object, transport: str, http_transport: object | None = None) -> None:
        setattr(self, "transport", transport)
        setattr(self, "http_transport", http_transport)
        init_calls.append(
            {
                "transport": transport,
                "base_url": getattr(http_transport, "base_url", None),
            }
        )

    def fake_compile(_adapter: object, _payload: dict[str, Any]) -> dict[str, str]:
        return art_ref

    def fake_predict_artifact(_adapter: object, payload: dict[str, Any]) -> dict[str, Any]:
        predict_payloads.append(payload)
        result = RunResult(
            run_id="predict-loopback-1",
            success=True,
            skill_id="demo.skill",
            context={},
            metrics={},
        )
        return result.model_dump(mode="json")

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "__init__", fake_init)
    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "compile", fake_compile)
    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact)

    result = PredictorService().dispatch_predict_job("demo.skill", input_data={"topic": "loopback"})

    assert result.run_id == "predict-loopback-1"
    assert predict_payloads[0]["artifact_ref"] == art_ref
    assert init_calls == [{"transport": "http_loopback", "base_url": "http://loopback.test"}]


def test_gateway_factory_uses_configured_http_loopback_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_gateway_http_loopback(monkeypatch)

    from app.core.adapters.transport_factory import build_gateway_adapter

    adapter = build_gateway_adapter()

    assert adapter.transport == "http_loopback"
    assert adapter.http_transport is not None
    assert adapter.http_transport.base_url == "http://gateway-loopback.test"


def test_run_worker_uses_configured_http_loopback_engine_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_http_loopback(monkeypatch)

    import app.core.adapters.engine as engine_adapter_module

    init_calls: list[dict[str, Any]] = []
    run_payloads: list[dict[str, Any]] = []
    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    art_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }

    def fake_init(self: object, transport: str, http_transport: object | None = None) -> None:
        setattr(self, "transport", transport)
        setattr(self, "http_transport", http_transport)
        init_calls.append(
            {
                "transport": transport,
                "base_url": getattr(http_transport, "base_url", None),
            }
        )

    def fake_compile(_adapter: object, _payload: dict[str, Any]) -> dict[str, str]:
        return art_ref

    def fake_run_artifact(_adapter: object, payload: dict[str, Any]) -> dict[str, Any]:
        run_payloads.append(payload)
        return {"context": {}, "metrics": {}, "success": True}

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "__init__", fake_init)
    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "compile", fake_compile)
    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "run_artifact", fake_run_artifact)

    run_dir = tmp_path / "skill" / ".workspace" / "runs" / "run-loopback-1"
    queue = _Queue()
    run_manager_module._run_worker_main(
        "demo.skill",
        str(run_dir),
        {"topic": "loopback"},
        queue,
        art_ref,
    )

    assert run_payloads[0]["artifact_ref"] == art_ref
    assert run_payloads[0]["inputs"] == {"topic": "loopback"}
    assert init_calls == [{"transport": "http_loopback", "base_url": "http://loopback.test"}]


def test_run_worker_http_loopback_payload_is_json_serializable_and_omits_callback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_http_loopback(monkeypatch)

    import app.core.adapters.http_transport as http_transport_module

    captured_requests: list[dict[str, Any]] = []

    class FakeHttpClient:
        def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
            captured_requests.append({"url": url, "payload": json, "headers": dict(headers)})
            jsonlib.dumps(json)
            return httpx.Response(
                200,
                json={
                    "schema_version": http_transport_module.SCHEMA_VERSION,
                    "ok": True,
                    "data": {"context": {"done": True}, "metrics": {}, "success": True},
                },
            )

    monkeypatch.setattr(http_transport_module.httpx, "Client", FakeHttpClient)

    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    art_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    run_dir = tmp_path / "skill" / ".workspace" / "runs" / "run-http-loopback-1"
    queue = _Queue()

    run_manager_module._run_worker_main(
        "demo.skill",
        str(run_dir),
        {"topic": "loopback"},
        queue,
        art_ref,
    )

    assert captured_requests[0]["url"] == "http://loopback.test/engine/run_artifact"
    assert captured_requests[0]["headers"]["Idempotency-Key"] == "run-http-loopback-1"
    assert captured_requests[0]["headers"]["Authorization"] == "Bearer studio-test-token"
    assert captured_requests[0]["headers"][LOOPBACK_TOKEN_HEADER]
    assert captured_requests[0]["payload"]["idempotency_key"] == "run-http-loopback-1"
    assert "event_subscriber" not in captured_requests[0]["payload"]
    assert queue.items[-1]["status"] == "success"


def _configure_http_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDIO_ENGINE_TRANSPORT", "http_loopback")
    monkeypatch.setenv("STUDIO_ENGINE_LOOPBACK_BASE_URL", "http://loopback.test")
    clear_backend_caches()


def _configure_gateway_http_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDIO_GATEWAY_TRANSPORT", "http_loopback")
    monkeypatch.setenv("STUDIO_GATEWAY_LOOPBACK_BASE_URL", "http://gateway-loopback.test")
    clear_backend_caches()


def _is_engine_adapter_call(func: ast.expr) -> bool:
    if isinstance(func, ast.Name):
        return func.id == "EngineAdapter"
    if isinstance(func, ast.Attribute):
        return func.attr == "EngineAdapter"
    return False


def _is_gateway_adapter_call(func: ast.expr) -> bool:
    if isinstance(func, ast.Name):
        return func.id == "GatewayAdapter"
    if isinstance(func, ast.Attribute):
        return func.attr == "GatewayAdapter"
    return False


def _is_name_or_attr(func: ast.expr, name: str) -> bool:
    if isinstance(func, ast.Name):
        return func.id == name
    if isinstance(func, ast.Attribute):
        return func.attr == name
    return False
