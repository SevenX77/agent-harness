"""Copilot 结构化工具(in-process MCP server):零审批的后端能力面。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.models.llm_config import ProviderEndpoint, ProviderRoute, RegistryResponse
from app.services import copilot, copilot_tools
from claude_agent_sdk import PermissionResultAllow


def test_mcp_server_exposes_tools() -> None:
    servers = copilot_tools.build_copilot_mcp_servers()
    assert set(servers) == {"studio"}
    # 读/探测三件的免审批基线仍在(完整全集见 test_copilot_config_tools.py)。
    tool_names = {
        t.name
        for t in (
            copilot_tools.get_llm_roles_tool,
            copilot_tools.compile_skill_tool,
            copilot_tools.run_role_test_tool,
        )
    }
    assert tool_names == {"get_llm_roles", "compile_skill", "run_role_test"}


def test_get_llm_roles_tool_returns_compact_snapshot(
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    result = asyncio.run(copilot_tools.get_llm_roles_tool.handler({}))

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert "roles" in payload
    assert payload["role_count"] == len(payload["roles"])
    for entry in payload["roles"].values():
        assert set(entry) == {"role_kind", "model_fallback_enabled", "fallback_chain"}


def test_compile_skill_tool_requires_skill_id() -> None:
    result = asyncio.run(copilot_tools.compile_skill_tool.handler({"skill_id": "  "}))

    assert result["is_error"] is True
    assert "skill_id" in result["content"][0]["text"]


def test_compile_skill_tool_reports_failure_as_tool_error() -> None:
    # 不存在的 skill:解析失败必须落成 is_error 工具结果,不许异常炸断事件流。
    result = asyncio.run(
        copilot_tools.compile_skill_tool.handler({"skill_id": "no-such-skill-xyz"})
    )

    assert result["is_error"] is True
    assert result["content"][0]["text"]


def test_run_role_test_tool_requires_role_name() -> None:
    result = asyncio.run(copilot_tools.run_role_test_tool.handler({"role_name": "  "}))

    assert result["is_error"] is True
    assert "role_name" in result["content"][0]["text"]


def test_run_role_test_tool_rejects_unknown_role(monkeypatch) -> None:  # noqa: ANN001
    # 范围自校验:只允许测现有角色,未知角色落成 is_error(不越界)。
    from app.routers import llm

    class _Data:
        roles: dict[str, object] = {}

    monkeypatch.setattr(llm, "_load_roles_or_empty", lambda: _Data())

    result = asyncio.run(copilot_tools.run_role_test_tool.handler({"role_name": "ghost"}))

    assert result["is_error"] is True
    assert "ghost" in result["content"][0]["text"]


def test_run_role_test_tool_compacts_result(monkeypatch) -> None:  # noqa: ANN001
    # 走既有服务路径(test_llm_role 同款: 载入→物化→_run_role_test_targets),
    # 把冗长明细压成 status+message 的紧凑快照回给模型。
    from app.routers import llm

    sentinel_role = object()

    class _Data:
        roles = {"copilot_chat": sentinel_role}

    async def _fake_run(role_name: str, targets: object) -> dict[str, object]:
        return {
            "role_name": role_name,
            "status": "ok",
            "warnings": [{"code": "w1"}],
            "model_groups": [
                {
                    "canonical_id": "openai:gpt-x",
                    "display_name": "GPT-X",
                    "provider_results": [
                        {
                            "status": "ok",
                            "message": None,
                            "warnings": [{"code": "noise"}],
                            "evidence": {"big": "blob"},
                        }
                    ],
                }
            ],
        }

    from app.services import llm_credentials

    monkeypatch.setattr(llm, "_load_roles_or_empty", lambda: _Data())
    monkeypatch.setattr(llm_credentials, "load_credentials", lambda: object())
    monkeypatch.setattr(llm, "_materialize_role_for_response", lambda role, creds: role)
    monkeypatch.setattr(llm, "_role_test_targets", lambda role, creds: [])
    monkeypatch.setattr(llm, "_run_role_test_targets", _fake_run)

    result = asyncio.run(
        copilot_tools.run_role_test_tool.handler({"role_name": "copilot_chat"})
    )

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert payload["role_name"] == "copilot_chat"
    assert payload["status"] == "ok"
    assert payload["warning_count"] == 1
    group = payload["model_groups"][0]
    assert group["canonical_id"] == "openai:gpt-x"
    assert group["display_name"] == "GPT-X"
    # 冗长明细(evidence / 逐条 warnings)被压掉,每个路由只留 status+message。
    assert set(group["routes"][0]) == {"status", "message"}
    assert group["routes"][0]["status"] == "ok"


# ── search_llm_registry(搜索驱动、结果有界的词汇发现) ─────────────────────────


def _endpoint(
    endpoint_id: str,
    *,
    provider_kind: str = "third_party",
    api_key: str | None = None,
) -> ProviderEndpoint:
    fields: dict[str, object] = {
        "endpoint_id": endpoint_id,
        "display_name": endpoint_id,
        "protocol": "openai_compatible",
        "base_url": f"https://{endpoint_id}.example/v1",
        "provider_kind": provider_kind,
    }
    if api_key is not None:
        fields["api_key"] = api_key
    return ProviderEndpoint.model_validate(fields)


def _route(endpoint_id: str, canonical_id: str, *, status: str = "verified") -> ProviderRoute:
    return ProviderRoute.model_validate(
        {
            "route_id": f"{endpoint_id}:{canonical_id}",
            "endpoint_id": endpoint_id,
            "route_slug": canonical_id,
            "provider_model_id": canonical_id,
            "canonical_id": canonical_id,
            "status": status,
        }
    )


def _registry(
    routes: list[ProviderRoute],
    endpoints: list[ProviderEndpoint],
) -> RegistryResponse:
    routes_by_canonical: dict[str, list[str]] = {}
    for route in routes:
        routes_by_canonical.setdefault(route.canonical_id, []).append(route.route_id)
    return RegistryResponse(
        provider_endpoints={e.endpoint_id: e for e in endpoints},
        provider_routes={r.route_id: r for r in routes},
        canonical_groups=[
            {"canonical_id": cid, "display_name": cid, "routes": rids}
            for cid, rids in sorted(routes_by_canonical.items())
        ],
    )


def _patch_registry(monkeypatch, registry: RegistryResponse) -> None:  # noqa: ANN001
    from app.routers import llm

    async def _fake() -> RegistryResponse:
        return registry

    monkeypatch.setattr(llm, "get_llm_registry", _fake)


def test_search_llm_registry_filters_and_groups(monkeypatch) -> None:  # noqa: ANN001
    endpoints = [
        _endpoint("anthropic", provider_kind="official"),
        _endpoint("openrouter"),
        _endpoint("openai"),
    ]
    routes = [
        _route("anthropic", "claude-opus-4.8"),
        _route("openrouter", "anthropic.claude-opus-4.8"),
        _route("openai", "gpt-4o"),
    ]
    _patch_registry(monkeypatch, _registry(routes, endpoints))

    result = asyncio.run(copilot_tools.search_llm_registry_tool.handler({"query": "opus"}))

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    matched = {g["canonical_id"] for g in payload["canonical_groups"]}
    # 只命中含 "opus" 的两个 canonical 组;gpt-4o 被过滤掉。
    assert matched == {"claude-opus-4.8", "anthropic.claude-opus-4.8"}
    official = next(
        g for g in payload["canonical_groups"] if g["canonical_id"] == "claude-opus-4.8"
    )
    # 每条 route 只投影有界的词汇字段;官方直连端点 is_official=True。
    assert official["routes"] == [
        {
            "route_id": "anthropic:claude-opus-4.8",
            "endpoint_id": "anthropic",
            "status": "verified",
            "is_official": True,
        }
    ]
    third_party = next(
        g
        for g in payload["canonical_groups"]
        if g["canonical_id"] == "anthropic.claude-opus-4.8"
    )
    assert third_party["routes"][0]["is_official"] is False


def test_search_llm_registry_result_is_bounded(monkeypatch) -> None:  # noqa: ANN001
    endpoints = [_endpoint("bigprov")]
    routes = [_route("bigprov", f"model-{i:03d}") for i in range(200)]
    _patch_registry(monkeypatch, _registry(routes, endpoints))

    result = asyncio.run(copilot_tools.search_llm_registry_tool.handler({"query": "model"}))

    payload = json.loads(result["content"][0]["text"])
    # 200 条全部匹配,但只返回默认 limit(20)条,total_count 反映匹配总数。
    assert payload["total_count"] == 200
    assert len(payload["canonical_groups"]) == 20
    # 结构上根除 token 撑爆:整串序列化远小于 50KB。
    assert len(result["content"][0]["text"]) < 50_000


def test_search_llm_registry_hard_caps_limit(monkeypatch) -> None:  # noqa: ANN001
    endpoints = [_endpoint("bigprov")]
    routes = [_route("bigprov", f"model-{i:03d}") for i in range(200)]
    _patch_registry(monkeypatch, _registry(routes, endpoints))

    result = asyncio.run(
        copilot_tools.search_llm_registry_tool.handler({"query": "model", "limit": 999})
    )

    payload = json.loads(result["content"][0]["text"])
    assert len(payload["canonical_groups"]) <= 50


def test_search_llm_registry_never_leaks_api_key(monkeypatch) -> None:  # noqa: ANN001
    secret = "sk-supersecret-do-not-leak-abc123"
    endpoints = [_endpoint("anthropic", provider_kind="official", api_key=secret)]
    routes = [_route("anthropic", "claude-opus-4.8")]
    _patch_registry(monkeypatch, _registry(routes, endpoints))

    result = asyncio.run(copilot_tools.search_llm_registry_tool.handler({"query": "opus"}))

    text = result["content"][0]["text"]
    assert secret not in text
    assert "api_key" not in text


def test_get_llm_registry_tool_is_removed() -> None:
    # 旧的全量转储工具被彻底废除(不留别名、不进白名单)。
    assert not hasattr(copilot_tools, "get_llm_registry_tool")
    tool_names = {t.name for t in copilot_tools._copilot_mcp_tools()}
    assert "get_llm_registry" not in tool_names
    assert "search_llm_registry" in tool_names
    assert "mcp__studio__get_llm_registry" not in copilot._DECLARATIVE_ALLOWED_TOOLS
    assert "mcp__studio__search_llm_registry" in copilot._DECLARATIVE_ALLOWED_TOOLS


def test_build_options_attaches_studio_mcp_for_chat_only(tmp_path: Path) -> None:
    async def cb(name, tool_input, ctx):  # noqa: ANN001
        return PermissionResultAllow()

    chat_options = copilot.build_options(None, "key", tmp_path, can_use_tool=cb)
    probe_options = copilot.build_options(None, "key", tmp_path)

    assert set(chat_options.mcp_servers) == {"studio"}
    assert probe_options.mcp_servers == {}
