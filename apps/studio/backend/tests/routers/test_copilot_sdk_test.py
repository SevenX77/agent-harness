from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import app.routers.llm as llm_router
from app.core import config
from app.models.llm_config import (
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
    RolesData,
)
from app.services.llm_credentials import save_credentials
from app.services.llm_import_drafts import load_evidence_library
from app.services.llm_roles import save_roles_file
from fastapi.testclient import TestClient


def test_copilot_sdk_test_endpoint_documents_error_responses(client: TestClient) -> None:
    schema = client.app.openapi()
    operation = schema["paths"]["/api/copilot/roles/{role_name}/test-sdk"]["post"]

    assert set(operation["responses"]) >= {"400", "404"}


def _seed_custom_copilot_role(
    tmp_path: Path,
    monkeypatch,
    *,
    role_kind: str | None = None,
) -> Path:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"

    credentials = LLMCredentialsFile(
        provider_endpoints={
            "custom-copilot-provider": ProviderEndpoint(
                endpoint_id="custom-copilot-provider",
                display_name="Custom Copilot Provider",
                protocol="anthropic_compatible",
                base_url="https://api.custom-copilot.example/v1",
                api_key="secret",
                status="verified",
                provider_kind="custom",
            )
        },
        provider_routes={
            "custom-copilot-provider:copilot-model": ProviderRoute(
                route_id="custom-copilot-provider:copilot-model",
                endpoint_id="custom-copilot-provider",
                route_slug="copilot-model",
                provider_model_id="copilot-model",
                canonical_id="copilot-model",
                display_name="Copilot Model",
                status="verified",
                capabilities={},
            )
        },
    )
    save_credentials(credentials, active_credentials_path)

    role_kwargs: dict[str, Any] = {
        "fallback_chain": [
            RoleRouteEntry(route_id="custom-copilot-provider:copilot-model")
        ],
    }
    if role_kind is not None:
        role_kwargs["role_kind"] = role_kind
    save_roles_file(
        roles_path,
        RolesData(
            roles={
                "copilot_chat": RoleEntry(**role_kwargs)
            }
        ),
        known_route_ids=set(credentials.provider_routes),
    )
    return active_credentials_path


def _mock_successful_sdk_probe(monkeypatch) -> list[str]:
    probe_calls = []

    async def mock_probe_sdk_tool_call(
        endpoint,
        route,
    ) -> Any:
        probe_calls.append(route.provider_model_id)
        from app.services.copilot_test import ModelProbeResult
        return ModelProbeResult(
            model_id=route.provider_model_id,
            status="ok",
            latency_ms=150,
            message="Claude SDK tools simulation succeeded",
        )

    monkeypatch.setattr(llm_router, "_probe_copilot_sdk_tool_call", mock_probe_sdk_tool_call)
    return probe_calls


def test_copilot_sdk_test_endpoint_persists_claude_sdk_tools_capability(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    active_credentials_path = _seed_custom_copilot_role(tmp_path, monkeypatch)
    probe_calls = _mock_successful_sdk_probe(monkeypatch)

    # Send request to the new endpoint
    response = client.post("/api/copilot/roles/copilot_chat/test-sdk", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert probe_calls == ["copilot-model"]

    # Assert credentials.json route has 'claude_sdk_tools' capability
    saved_credentials = json.loads(active_credentials_path.read_text(encoding="utf-8"))
    route = saved_credentials["provider_routes"]["custom-copilot-provider:copilot-model"]
    assert route["capabilities"]["claude_sdk_tools"]["value"] is True
    assert route["capabilities"]["claude_sdk_tools"]["source"] == "probed_verified"

    # Assert import_drafts.json evidence record has 'claude_sdk_tools' True
    evidence_records = load_evidence_library().evidence_records
    assert len(evidence_records) >= 1
    probe_record = next(
        (rec for rec in evidence_records if rec.route_id == "custom-copilot-provider:copilot-model"),
        None
    )
    assert probe_record is not None
    assert probe_record.trust_state == "probe-verified"
    assert probe_record.candidate_capabilities.get("claude_sdk_tools").value is True


def test_copilot_role_test_jobs_aligns_with_sdk_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    active_credentials_path = _seed_custom_copilot_role(
        tmp_path,
        monkeypatch,
        role_kind="copilot",
    )
    probe_calls = _mock_successful_sdk_probe(monkeypatch)

    # POST to the general LLM test jobs endpoint
    response = client.post("/api/llm/roles/copilot_chat/test-jobs", json={})
    assert response.status_code == 200
    job_info = response.json()
    job_id = job_info["job_id"]

    # Poll until completed
    import time
    for _ in range(20):
        poll = client.get(f"/api/llm/role-test-jobs/{job_id}")
        assert poll.status_code == 200
        poll_info = poll.json()
        if poll_info["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)

    poll = client.get(f"/api/llm/role-test-jobs/{job_id}")
    assert poll.status_code == 200
    final_info = poll.json()
    assert final_info["status"] == "completed"
    assert probe_calls == ["copilot-model"]

    # Assert credentials.json route has 'claude_sdk_tools' capability
    saved_credentials = json.loads(active_credentials_path.read_text(encoding="utf-8"))
    route = saved_credentials["provider_routes"]["custom-copilot-provider:copilot-model"]
    assert route["capabilities"]["claude_sdk_tools"]["value"] is True
    assert route["capabilities"]["claude_sdk_tools"]["source"] == "probed_verified"
