"""Copilot 结构化工具(in-process MCP server):零审批的后端能力面。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.services import copilot, copilot_tools
from claude_agent_sdk import PermissionResultAllow


def test_mcp_server_exposes_tools() -> None:
    servers = copilot_tools.build_copilot_mcp_servers()
    assert set(servers) == {"studio"}
    # SdkMcpTool names — 只读快照 + 编译 + 角色测试(slice2 免审批、非破坏)。
    tool_names = {
        t.name
        for t in (
            copilot_tools.get_llm_roles_tool,
            copilot_tools.compile_skill_tool,
            copilot_tools.run_role_test_tool,
        )
    }
    assert tool_names == {"get_llm_roles", "compile_skill", "run_role_test"}


def test_get_llm_roles_tool_returns_compact_snapshot() -> None:
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


def test_build_options_attaches_studio_mcp_for_chat_only(tmp_path: Path) -> None:
    async def cb(name, tool_input, ctx):  # noqa: ANN001
        return PermissionResultAllow()

    chat_options = copilot.build_options(None, "key", tmp_path, can_use_tool=cb)
    probe_options = copilot.build_options(None, "key", tmp_path)

    assert set(chat_options.mcp_servers) == {"studio"}
    assert probe_options.mcp_servers == {}
