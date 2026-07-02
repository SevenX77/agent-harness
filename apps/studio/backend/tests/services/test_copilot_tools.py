"""Copilot 结构化工具(in-process MCP server):零审批的后端能力面。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.services import copilot, copilot_tools
from claude_agent_sdk import PermissionResultAllow


def test_mcp_server_exposes_first_batch_tools() -> None:
    servers = copilot_tools.build_copilot_mcp_servers()
    assert set(servers) == {"studio"}
    # SdkMcpTool names — 第一批只有只读快照 + 编译两个低风险面。
    tool_names = {t.name for t in (copilot_tools.get_llm_roles_tool, copilot_tools.compile_skill_tool)}
    assert tool_names == {"get_llm_roles", "compile_skill"}


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


def test_build_options_attaches_studio_mcp_for_chat_only(tmp_path: Path) -> None:
    async def cb(name, tool_input, ctx):  # noqa: ANN001
        return PermissionResultAllow()

    chat_options = copilot.build_options(None, "key", tmp_path, can_use_tool=cb)
    probe_options = copilot.build_options(None, "key", tmp_path)

    assert set(chat_options.mcp_servers) == {"studio"}
    assert probe_options.mcp_servers == {}
