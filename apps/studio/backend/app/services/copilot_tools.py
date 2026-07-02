"""Copilot 结构化工具 — in-process MCP server 暴露 Studio 后端能力。

设计原则:工具由后端实现并做参数校验,天然安全 → can_use_tool 对它们默认
放行(零审批);配置真相只经既有服务路径(gateway truth),copilot 绝不直改
`llm/` 配置文件。第一批只上低风险面:角色配置快照(只读)+ 编译(纯校验类
动作);mutation 类(update_role / run_model_test / predict / run)等各自
契约敲定后分批补,不上线半生不熟的写接口。
"""

from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpServerConfig

COPILOT_MCP_SERVER_NAME = "studio"
COPILOT_MCP_TOOL_PREFIX = f"mcp__{COPILOT_MCP_SERVER_NAME}__"


def _text_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["is_error"] = True
    return result


@tool(
    "get_llm_roles",
    "读取 Studio 的 LLM 角色配置快照:每个角色的类型(graph_agent/copilot)与"
    "兜底链(fallback_chain 路由列表)。用户问「有哪些角色 / 为什么某角色不可用 / "
    "现在用的什么模型」时用;只读,改配置要指引用户去 Settings。",
    {},
)
async def get_llm_roles_tool(args: dict[str, Any]) -> dict[str, Any]:
    del args
    # 与 GET /api/llm/roles 同一条真相路径(载入 + 物化),不自建第二份读取逻辑。
    from app.routers.llm import _load_roles_or_empty, _materialize_roles_for_response

    data = _materialize_roles_for_response(_load_roles_or_empty())
    snapshot: dict[str, Any] = {}
    for name, role in data.roles.items():
        dumped = role.model_dump(mode="json")
        snapshot[name] = {
            "role_kind": dumped.get("role_kind"),
            "model_fallback_enabled": dumped.get("model_fallback_enabled"),
            "fallback_chain": dumped.get("fallback_chain", []),
        }
    return _text_result({"roles": snapshot, "role_count": len(snapshot)})


@tool(
    "compile_skill",
    "编译指定 skill 并返回结果:成功给编译产物摘要,失败给完整错误列表"
    "([F-v3-*] 错误码 + 文件 + 行号)。改完 skill 文件后必须用它验证,"
    "不要让用户手动去点 Compile 再把错误贴回来。",
    {"skill_id": str},
)
async def compile_skill_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.core.backends import get_backend_config, get_metadata, get_storage
    from app.services.skills import CompileFailedError, compile_skill_for_studio

    skill_id = str(args.get("skill_id", "")).strip()
    if not skill_id:
        return _text_result("skill_id 不能为空", is_error=True)
    try:
        result = await compile_skill_for_studio(
            get_backend_config().default_user_id,
            skill_id,
            get_storage(),
            get_metadata(),
        )
    except CompileFailedError as exc:
        return _text_result(exc.failure.model_dump(mode="json"), is_error=True)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都必须落成
        # is_error 工具结果回给模型,绝不让异常炸断 ws 事件流。
        return _text_result(f"compile_skill 失败: {exc}", is_error=True)
    return _text_result(result.model_dump(mode="json"))


def build_copilot_mcp_servers() -> dict[str, McpServerConfig]:
    """Chat 会话的 in-process MCP server 集(probe 路不挂,保持探测确定性)。"""

    return {
        COPILOT_MCP_SERVER_NAME: create_sdk_mcp_server(
            name=COPILOT_MCP_SERVER_NAME,
            version="1.0.0",
            tools=[get_llm_roles_tool, compile_skill_tool],
        )
    }
