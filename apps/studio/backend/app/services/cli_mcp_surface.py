"""CLI 表面的 Studio MCP 出口(N5):同一批工具再建一个对外 Server。

Open in CLI 拉起的 codex/claude 经 streamable HTTP(挂载在 sidecar `/mcp`,
Bearer 鉴权由 main.configure_api_auth 的全局中间件覆盖)调用与面板 copilot
同源的工具实现——run/事件/状态都留在 sidecar 进程内,CLI 发起的动作与
Studio UI 呈现同一真相,不另起第二个平行世界。

级联删除类工具(delete_llm_endpoint/delete_llm_route)不对 CLI 暴露:
CLI 表面的人工闸是终端原生审批,误批一次即级联清凭据,代价不对称。

**这里的工具不绑定 skill**,与面板 copilot 不同(见 copilot_skill_binding):
`/mcp` 是**一个进程级 HTTP 挂载**,由 main.lifespan 建一次、服务任何连上来的 CLI
进程,连接本身不携带"我打开的是哪个 skill"。CLI 侧现有的对策在启动那一端:
`apps/studio/tauri/src/lib.rs:3718-3726` 用注册表反查
(`native_fs::registered_skill_id_for_root`)把 `SessionSkillContext{skill_id,
workspace_root}` 注进会话配置,即**告诉**模型它绑定在哪个 skill 上,而不是让它猜。
把这条 HTTP 表面也做成按连接绑定,需要先给 `/mcp` 一个连接级会话身份,那是另一件
设计工作,记在决议
`.kiro/specs/decision-2026-08-16-copilot-tools-bound-to-the-open-skill.md` 的
「未做的部分」。
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server
from mcp.server.lowlevel import Server

from app.services.copilot_tools import COPILOT_MCP_SERVER_NAME, copilot_mcp_tools

CLI_EXCLUDED_TOOL_NAMES = frozenset({"delete_llm_endpoint", "delete_llm_route"})


def _cli_tools() -> list[Any]:
    return [t for t in copilot_mcp_tools() if t.name not in CLI_EXCLUDED_TOOL_NAMES]


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
