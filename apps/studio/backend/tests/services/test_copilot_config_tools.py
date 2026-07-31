"""MCP config tools parity (design B §2.2/§3): registry lexicon read, role
delete + profile apply, endpoint/route CRUD, and endpoint/route probes. Write
tools reuse the SAME routers.llm service chain the Settings UI hits; none of
them return before/after undo snapshots (undo is deleted). api_key never leaks
into the redacted registry read.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from app.services import copilot_tools


def _payload(result: dict[str, Any]) -> Any:
    return json.loads(result["content"][0]["text"])


# ── search_llm_registry (词汇发现,搜索驱动,结果有界,脱敏) ────────────────────


def test_search_llm_registry_redacts_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.llm_config import (
        ProviderEndpoint,
        ProviderRoute,
        RegistryResponse,
    )
    from app.routers import llm

    endpoint = ProviderEndpoint(
        endpoint_id="prov-x",
        display_name="Prov X",
        protocol="openai_compatible",
        base_url="https://api.prov-x.test",
        api_key="sk-super-secret-should-never-leak",
    )
    route = ProviderRoute.model_validate(
        {
            "route_id": "prov-x:gpt-x",
            "endpoint_id": "prov-x",
            "route_slug": "gpt-x",
            "provider_model_id": "gpt-x",
            "canonical_id": "gpt-x",
        }
    )
    registry = RegistryResponse(
        provider_endpoints={endpoint.endpoint_id: endpoint},
        provider_routes={route.route_id: route},
        canonical_groups=[
            {"canonical_id": "gpt-x", "display_name": "gpt-x", "routes": [route.route_id]}
        ],
    )

    async def _fake_registry() -> Any:
        return registry

    monkeypatch.setattr(llm, "get_llm_registry", _fake_registry)

    result = asyncio.run(
        copilot_tools.search_llm_registry_tool.handler({"query": "gpt-x"})
    )

    assert "is_error" not in result, result
    text = result["content"][0]["text"]
    # 搜索工具只投影词汇字段,api_key 明文物理不可达。
    assert "sk-super-secret-should-never-leak" not in text
    assert "api_key" not in text


# ── delete_llm_role (写,需审批;固定角色拒绝) ───────────────────────────────


def test_delete_llm_role_rejects_fixed_role(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import llm_fixed_roles

    monkeypatch.setattr(llm_fixed_roles, "is_fixed_role", lambda name: name == "copilot")

    result = asyncio.run(
        copilot_tools.delete_llm_role_tool.handler({"role_name": "copilot"})
    )

    assert result["is_error"] is True
    assert "copilot" in result["content"][0]["text"]


def test_delete_llm_role_deletes_non_fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import llm
    from app.services import llm_fixed_roles

    monkeypatch.setattr(llm_fixed_roles, "is_fixed_role", lambda name: False)
    called: dict[str, Any] = {}

    async def _fake_delete(role_name: str) -> Any:
        called["role_name"] = role_name
        return object()

    monkeypatch.setattr(llm, "delete_llm_role", _fake_delete)

    result = asyncio.run(
        copilot_tools.delete_llm_role_tool.handler({"role_name": "writer"})
    )

    assert "is_error" not in result, result
    assert called["role_name"] == "writer"
    assert _payload(result)["status"] == "success"


def test_delete_llm_role_requires_name() -> None:
    result = asyncio.run(copilot_tools.delete_llm_role_tool.handler({"role_name": " "}))
    assert result["is_error"] is True


# ── upsert_llm_endpoint (写,需审批;真 schema 字段) ─────────────────────────


def test_upsert_llm_endpoint_builds_endpoint_and_saves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers import llm

    captured: dict[str, Any] = {}

    async def _fake_put(request: Any) -> Any:
        captured["request"] = request
        return object()

    monkeypatch.setattr(llm, "put_registry_endpoints", _fake_put)

    result = asyncio.run(
        copilot_tools.upsert_llm_endpoint_tool.handler(
            {
                "endpoint_id": "prov-x",
                "display_name": "Prov X",
                "protocol": "openai_compatible",
                "base_url": "https://api.prov-x.test",
                "api_key": "sk-123",
            }
        )
    )

    assert "is_error" not in result, result
    request = captured["request"]
    assert "prov-x" in request.provider_endpoints
    endpoint = request.provider_endpoints["prov-x"]
    assert endpoint.protocol == "openai_compatible"
    assert endpoint.base_url == "https://api.prov-x.test"


def test_upsert_llm_endpoint_requires_id() -> None:
    result = asyncio.run(
        copilot_tools.upsert_llm_endpoint_tool.handler({"endpoint_id": ""})
    )
    assert result["is_error"] is True


def test_upsert_llm_endpoint_rejects_invalid_protocol() -> None:
    result = asyncio.run(
        copilot_tools.upsert_llm_endpoint_tool.handler(
            {
                "endpoint_id": "prov-x",
                "display_name": "Prov X",
                "protocol": "not_a_protocol",
                "base_url": "https://api.prov-x.test",
            }
        )
    )
    assert result["is_error"] is True


# ── delete_llm_endpoint / update_llm_route / delete_llm_route (写) ───────────


def test_delete_llm_endpoint_reuses_router(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import llm

    called: dict[str, Any] = {}

    async def _fake(endpoint_id: str) -> Any:
        called["endpoint_id"] = endpoint_id
        return object()

    monkeypatch.setattr(llm, "delete_registry_endpoint", _fake)

    result = asyncio.run(
        copilot_tools.delete_llm_endpoint_tool.handler({"endpoint_id": "prov-x"})
    )

    assert "is_error" not in result, result
    assert called["endpoint_id"] == "prov-x"


def test_update_llm_route_reuses_router(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import llm

    captured: dict[str, Any] = {}

    async def _fake(route_id: str, request: Any) -> Any:
        captured["route_id"] = route_id
        captured["request"] = request
        return object()

    monkeypatch.setattr(llm, "put_route_metadata", _fake)

    result = asyncio.run(
        copilot_tools.update_llm_route_tool.handler(
            {
                "route_id": "prov-x:gpt-5",
                "display_name": "GPT-5",
                "canonical_id": "gpt-5",
                "status": "verified",
            }
        )
    )

    assert "is_error" not in result, result
    assert captured["route_id"] == "prov-x:gpt-5"
    assert captured["request"].canonical_id == "gpt-5"


def test_delete_llm_route_reuses_router(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import llm

    called: dict[str, Any] = {}

    async def _fake(route_id: str) -> Any:
        called["route_id"] = route_id
        return object()

    monkeypatch.setattr(llm, "delete_registry_route", _fake)

    result = asyncio.run(
        copilot_tools.delete_llm_route_tool.handler({"route_id": "prov-x:gpt-5"})
    )

    assert "is_error" not in result, result
    assert called["route_id"] == "prov-x:gpt-5"


# ── probes / tests (只读探测) ────────────────────────────────────────────────


def test_test_llm_endpoint_reuses_router(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import llm

    called: dict[str, Any] = {}

    async def _fake(endpoint_id: str, force: bool = False) -> Any:
        called["endpoint_id"] = endpoint_id

        class _R:
            def model_dump(self, mode: str = "json") -> dict[str, Any]:
                return {"tested_endpoint_id": endpoint_id}

        return _R()

    monkeypatch.setattr(llm, "test_endpoint", _fake)

    result = asyncio.run(
        copilot_tools.test_llm_endpoint_tool.handler({"endpoint_id": "prov-x"})
    )

    assert "is_error" not in result, result
    assert called["endpoint_id"] == "prov-x"


def test_probe_llm_route_reuses_router(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import llm

    called: dict[str, Any] = {}

    async def _fake(route_id: str, request: Any, force: bool = False) -> Any:
        called["route_id"] = route_id
        called["force"] = force

        class _R:
            def model_dump(self, mode: str = "json") -> dict[str, Any]:
                return {"route_id": route_id}

        return _R()

    monkeypatch.setattr(llm, "probe_route", _fake)

    result = asyncio.run(
        copilot_tools.probe_llm_route_tool.handler({"route_id": "prov-x:gpt-5"})
    )

    assert "is_error" not in result, result
    assert called["route_id"] == "prov-x:gpt-5"


# ── apply_model_profile_to_role (写) ────────────────────────────────────────


def test_apply_model_profile_to_role_reuses_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers import llm

    captured: dict[str, Any] = {}

    async def _fake(role_name: str, request: Any) -> Any:
        captured["role_name"] = role_name
        captured["request"] = request
        return object()

    monkeypatch.setattr(llm, "apply_model_profile", _fake)

    result = asyncio.run(
        copilot_tools.apply_model_profile_to_role_tool.handler(
            {"role_name": "writer", "model_profile_id": "profile-1"}
        )
    )

    assert "is_error" not in result, result
    assert captured["role_name"] == "writer"
    assert captured["request"].model_profile_id == "profile-1"
    assert captured["request"].mode == "replace"


# ── registration ────────────────────────────────────────────────────────────


def test_mcp_server_exposes_full_parity_toolset() -> None:
    servers = copilot_tools.build_copilot_mcp_servers()
    assert set(servers) == {"studio"}
    tool_names = {t.name for t in copilot_tools._copilot_mcp_tools()}
    assert {
        "get_llm_roles",
        "search_llm_registry",
        "compile_skill",
        "run_role_test",
        "predict_skill",
        "create_skill",
        "run_skill",
        "get_run_detail",
        "list_golden",
        "get_golden_content",
        "set_golden_baseline",
        "delete_golden_baseline",
        "create_llm_role",
        "update_llm_role",
        "delete_llm_role",
        "apply_model_profile_to_role",
        "upsert_llm_endpoint",
        "delete_llm_endpoint",
        "update_llm_route",
        "delete_llm_route",
        "test_llm_endpoint",
        "test_llm_endpoint_models",
        "probe_llm_route",
    } == tool_names
