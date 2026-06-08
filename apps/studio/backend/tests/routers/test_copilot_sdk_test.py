"""WS-5 RED: Copilot SDK Test parity.

MVP1 contract (settings-ux-spec §3.4/§3.8, llm-copilot-http-api §6, copilot-assist):
the Copilot SDK Test endpoint must verify the *same* runtime path that real
Copilot chat uses — a ``ClaudeSDKClient`` spawned with per-session
``ANTHROPIC_*`` env injection — NOT a bare ``anthropic.AsyncAnthropic`` HTTP
probe. A passing SDK test must therefore prove that the spawn/env/tool-loop path
works, otherwise the "Ready" signal is fake.

These tests intentionally DO NOT mock ``_probe_copilot_sdk_tool_call`` (the old
fake-green seam). Instead they forbid ``anthropic.AsyncAnthropic`` and drive the
real Copilot ``_session_factory`` seam used by ``stream_query``. They are RED on
the current implementation, which still builds an ``AsyncAnthropic`` client.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
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
from app.services import copilot as copilot_service
from app.services.llm_credentials import save_credentials
from app.services.llm_import_drafts import load_evidence_library
from app.services.llm_roles import save_roles_file
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    ToolUseBlock,
)
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


class _FakeClaudeSdkClient:
    """A fake ``ClaudeSDKClient`` that records the per-session env injection and
    emits one tool-use turn, mirroring the real Copilot runtime contract."""

    last_options: Any = None

    def __init__(self, options: Any) -> None:
        type(self).last_options = options
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def query(self, prompt: str, session_id: str = "default") -> None:
        del prompt, session_id

    async def receive_response(self) -> AsyncIterator[object]:
        yield AssistantMessage(
            content=[ToolUseBlock(id="t1", name="Read", input={"file_path": "SKILL.md"})],
            model="claude",
        )
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="session",
        )


def _install_real_sdk_runtime(monkeypatch) -> type[_FakeClaudeSdkClient]:
    """Forbid the bare Anthropic HTTP client and route through the same
    ``ClaudeSDKClient`` session factory the real Copilot chat uses."""

    import anthropic

    def _forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(
            "Copilot SDK Test must use ClaudeSDKClient + per-session env, "
            "not anthropic.AsyncAnthropic"
        )

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _forbidden)
    _FakeClaudeSdkClient.last_options = None
    monkeypatch.setattr(
        copilot_service,
        "_session_factory",
        lambda options: _FakeClaudeSdkClient(options),
    )
    return _FakeClaudeSdkClient


def test_copilot_sdk_probe_uses_claude_sdk_client_runtime_not_async_anthropic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """RED: the probe must spawn a ClaudeSDKClient with injected ANTHROPIC env,
    not a bare AsyncAnthropic client."""

    _seed_custom_copilot_role(tmp_path, monkeypatch)
    fake = _install_real_sdk_runtime(monkeypatch)

    endpoint = ProviderEndpoint(
        endpoint_id="custom-copilot-provider",
        display_name="Custom Copilot Provider",
        protocol="anthropic_compatible",
        base_url="https://api.custom-copilot.example/v1",
        api_key="secret",
        status="verified",
        provider_kind="custom",
    )
    route = ProviderRoute(
        route_id="custom-copilot-provider:copilot-model",
        endpoint_id="custom-copilot-provider",
        route_slug="copilot-model",
        provider_model_id="copilot-model",
        canonical_id="copilot-model",
        display_name="Copilot Model",
        status="verified",
        capabilities={},
    )

    result = asyncio.run(llm_router._probe_copilot_sdk_tool_call(endpoint, route))

    assert result.status == "ok"
    assert fake.last_options is not None, "ClaudeSDKClient was never constructed"
    assert fake.last_options.env["ANTHROPIC_API_KEY"] == "secret"
    assert fake.last_options.env.get("ANTHROPIC_BASE_URL") == (
        "https://api.custom-copilot.example/v1"
    )


def test_copilot_sdk_test_endpoint_persists_claude_sdk_tools_capability(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """RED: end-to-end SDK test endpoint persists tool capability ONLY when the
    real ClaudeSDKClient path succeeds (no mocked probe)."""

    active_credentials_path = _seed_custom_copilot_role(tmp_path, monkeypatch)
    _install_real_sdk_runtime(monkeypatch)

    response = client.post("/api/copilot/roles/copilot_chat/test-sdk", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"

    saved_credentials = json.loads(active_credentials_path.read_text(encoding="utf-8"))
    route = saved_credentials["provider_routes"]["custom-copilot-provider:copilot-model"]
    assert route["capabilities"]["claude_sdk_tools"]["value"] is True
    assert route["capabilities"]["claude_sdk_tools"]["source"] == "probed_verified"

    evidence_records = load_evidence_library().evidence_records
    assert len(evidence_records) >= 1
    probe_record = next(
        (rec for rec in evidence_records if rec.route_id == "custom-copilot-provider:copilot-model"),
        None,
    )
    assert probe_record is not None
    assert probe_record.trust_state == "probe-verified"
    assert probe_record.candidate_capabilities.get("claude_sdk_tools").value is True


def test_copilot_role_test_jobs_aligns_with_sdk_probe(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """RED: the role test-jobs path that drives Copilot roles must also exercise
    the real ClaudeSDKClient probe and persist tool capability."""

    active_credentials_path = _seed_custom_copilot_role(
        tmp_path,
        monkeypatch,
        role_kind="copilot",
    )
    _install_real_sdk_runtime(monkeypatch)

    response = client.post("/api/llm/roles/copilot_chat/test-jobs", json={})
    assert response.status_code == 200
    job_info = response.json()
    job_id = job_info["job_id"]

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

    saved_credentials = json.loads(active_credentials_path.read_text(encoding="utf-8"))
    route = saved_credentials["provider_routes"]["custom-copilot-provider:copilot-model"]
    assert route["capabilities"]["claude_sdk_tools"]["value"] is True
    assert route["capabilities"]["claude_sdk_tools"]["source"] == "probed_verified"
