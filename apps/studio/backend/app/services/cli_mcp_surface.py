"""CLI 表面的 Studio MCP 出口(N5):同一批工具再建一个对外 Server。

Open in CLI 拉起的 codex/claude 经 streamable HTTP(挂载在 sidecar `/mcp`,
Bearer 鉴权由 main.configure_api_auth 的全局中间件覆盖)调用与面板 copilot
同源的工具实现——run/事件/状态都留在 sidecar 进程内,CLI 发起的动作与
Studio UI 呈现同一真相,不另起第二个平行世界。

级联删除类工具(delete_llm_endpoint/delete_llm_route)不对 CLI 暴露:
CLI 表面的人工闸是终端原生审批,误批一次即级联清凭据,代价不对称。
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server
from mcp.server.lowlevel import Server

from app.services.copilot_tools import COPILOT_MCP_SERVER_NAME, _copilot_mcp_tools

CLI_EXCLUDED_TOOL_NAMES = frozenset({"delete_llm_endpoint", "delete_llm_route"})


def _cli_tools() -> list[Any]:
    return [t for t in _copilot_mcp_tools() if t.name not in CLI_EXCLUDED_TOOL_NAMES]


def cli_tool_names() -> list[str]:
    return [t.name for t in _cli_tools()]


def build_cli_mcp_server() -> Server[Any, Any]:
    """CLI 表面的 MCP Server 实例(与面板同名 `studio`,工具名因此同前缀)。

    每次调用返回全新实例:StreamableHTTPSessionManager 一个实例只能 run 一次,
    lifespan 每次进入都要配一个新 Server(见 main.lifespan)。
    """

    config = create_sdk_mcp_server(
        name=COPILOT_MCP_SERVER_NAME, version="1.0.0", tools=_cli_tools()
    )
    return config["instance"]
