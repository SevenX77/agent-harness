"""Copilot 结构化工具 — in-process MCP server 暴露 Studio 后端能力。

设计原则:工具由后端实现并做参数校验,天然安全 → can_use_tool 对它们默认
放行(零审批);配置真相只经既有服务路径(gateway truth),copilot 绝不直改
`llm/` 配置文件。已上非破坏面:角色配置快照(只读)、编译(纯校验)、角色测试
(只探测不改配置)。真·mutation 类(update_role 写配置真相、图结构 mutation)
各自契约敲定后单独 PR 补,不上线半生不熟的写接口。
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


@tool(
    "run_role_test",
    "测试指定 LLM 角色的兜底链连通性:对每条路由发真实探测,返回整体状态 + 每个"
    "模型组各路由的通过/失败(status + message)。用户问「某角色能不能用 / 帮我测下"
    "这个角色 / 换的模型通不通」时用;只探测、不改配置;角色名必须是现有角色"
    "(未知角色直接报错,不越界)。",
    {"role_name": str},
)
async def run_role_test_tool(args: dict[str, Any]) -> dict[str, Any]:
    # 与 POST /api/llm/roles/{role_name}/test 同一条服务路径(载入→物化→探测),
    # 不自建第二份测试逻辑;冗长明细(evidence / 逐条 warnings)压成紧凑快照。
    from app.routers.llm import (
        _load_roles_or_empty,
        _materialize_role_for_response,
        _role_test_targets,
        _run_role_test_targets,
    )
    from app.services.llm_credentials import load_credentials

    role_name = str(args.get("role_name", "")).strip()
    if not role_name:
        return _text_result("role_name 不能为空", is_error=True)
    data = _load_roles_or_empty()
    role = data.roles.get(role_name)
    if role is None:
        # 范围自校验:只允许测现有角色,未知角色落成工具错误(免审批的前提是工具
        # 自己把住边界,同 Write/Edit 出 workspace 直接拒)。
        return _text_result(
            f"未知 LLM 角色: {role_name};现有角色: {sorted(data.roles)}",
            is_error=True,
        )
    try:
        credentials = load_credentials()
        materialized = _materialize_role_for_response(role, credentials)
        result = await _run_role_test_targets(
            role_name, _role_test_targets(materialized, credentials)
        )
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"run_role_test 失败: {exc}", is_error=True)

    groups = [
        {
            "canonical_id": group.get("canonical_id"),
            "display_name": group.get("display_name"),
            "routes": [
                {"status": pr.get("status"), "message": pr.get("message")}
                for pr in group.get("provider_results", [])
            ],
        }
        for group in result.get("model_groups", [])
    ]
    return _text_result(
        {
            "role_name": result.get("role_name", role_name),
            "status": result.get("status"),
            "model_groups": groups,
            "warning_count": len(result.get("warnings", [])),
        }
    )


_PREDICT_DIAGNOSTICS_LIMIT = 20


@tool(
    "predict_skill",
    "对指定 skill 做无 LLM 空跑(Predict):编译干净但行为可疑时用它——"
    "返回 phase 路径、path diff、诊断摘要;深查细节去 .workspace/runs/<run_id>/。"
    "compile_skill 干净之后的第二级诊断;真实运行(Run)只能由用户在 UI 触发。",
    {"skill_id": str},
)
async def predict_skill_tool(args: dict[str, Any]) -> dict[str, Any]:
    import asyncio

    from app.services import predictor

    skill_id = str(args.get("skill_id", "")).strip()
    if not skill_id:
        return _text_result("skill_id 不能为空", is_error=True)
    try:
        result = await asyncio.to_thread(
            predictor.predictor_service.dispatch_predict_job, skill_id
        )
        export = predictor.predictor_service.export_diagnostics(result)
    except predictor.PredictArtifactError as exc:
        return _text_result(
            {"error_code": exc.error_code, "message": str(exc), "run_id": exc.run_id},
            is_error=True,
        )
    except predictor.PredictDeadlockError as exc:
        return _text_result(
            {
                "error_code": "engine.predict_deadlock",
                "message": str(exc),
                "phase_name": exc.phase_name,
                "actual_path": exc.actual_path,
            },
            is_error=True,
        )
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"predict_skill 失败: {exc}", is_error=True)

    diagnostics = [d.model_dump(mode="json") for d in export.diagnostics]
    truncated = export.diagnostics_truncated or len(diagnostics) > _PREDICT_DIAGNOSTICS_LIMIT
    return _text_result(
        {
            "success": export.status == "success",
            "run_id": result.run_id,
            "phases": [
                {
                    "phase_name": p.phase_name,
                    "type": p.type,
                    "mocked_source": p.mocked_source,
                }
                for p in export.phases
            ],
            "path_diff": export.path_diff.model_dump(mode="json") if export.path_diff else None,
            "diagnostics": diagnostics[:_PREDICT_DIAGNOSTICS_LIMIT],
            "diagnostics_truncated": truncated,
            "diagnostics_total": len(diagnostics),
            "diagnostic_counts": export.diagnostic_counts,
            "detail_hint": f".workspace/runs/{result.run_id}/",
        }
    )


# 角色配置写工具(R10):经 routers/llm.py 背后同一条服务链(校验/canonicalize/
# 级联/领域事件全复用),绝不直写配置文件;凭据与 endpoint 不提供写入(R10.3)。
_ROLE_UPDATE_OPS = ("set_model_groups", "model_fallback_enabled", "intent")


def _model_groups_violation(groups: list[Any]) -> str | None:
    """路由词汇表一致性(fail fast at the boundary):`route_id` 的格式是
    `<endpoint_id>:<canonical_id>`,组的 canonical_id 必须与其每条路由的
    canonical 部分一致。实测教训(2026-07-11 人工验收):agent 把
    "anthropic.claude-opus-4.8" 这类带 provider 前缀的模型名当 canonical_id
    写入,保存校验只查 route 存在性(通过),但前端按注册表词汇找不到该组 →
    Settings 展示为空,随后的自动保存把空状态写回真相,模型组静默丢失。"""

    problems: list[str] = []
    for group in groups:
        for provider_model in group.provider_models:
            route_id = provider_model.route_id
            _, _, canonical_part = route_id.partition(":")
            if canonical_part != group.canonical_id:
                problems.append(
                    f"route {route_id!r} does not belong to canonical model"
                    f" {group.canonical_id!r}"
                )
    if not problems:
        return None
    return (
        "model_groups 词汇不一致:\n"
        + "\n".join(f"  - {p}" for p in problems)
        + "\ncanonical_id 必须等于 route_id 冒号后的模型部分"
        "(route_id 格式: <endpoint_id>:<canonical_id>);"
        "先用 get_llm_roles 查现有角色的取值当参照。"
    )


def _role_snapshot(role: Any) -> dict[str, Any]:
    dumped = role.model_dump(mode="json")
    return {
        "role_kind": dumped.get("role_kind"),
        "model_fallback_enabled": dumped.get("model_fallback_enabled"),
        "intent": dumped.get("intent"),
        "model_groups": dumped.get("model_groups", []),
    }


async def _save_single_role(role_name: str, role: Any) -> Any:
    """put_llm_roles 的单角色等价路径:merge → materialize → save → 领域事件。"""

    from app.routers import llm
    from app.services import llm_credentials, runtime_activity

    current = llm._load_roles_or_empty()
    merged = current.model_copy(update={"roles": {**current.roles, role_name: role}})
    credentials = llm_credentials.load_credentials()
    materialized = llm._materialize_roles_for_response(merged, credentials)
    saved = llm._save_roles_with_active_routes(materialized)
    await llm._publish_roles_changed()
    runtime_activity.record_runtime_activity(
        source_id="llm_roles",
        action="copilot_role_write",
        message=f"Copilot tool saved LLM role '{role_name}'.",
        changes={"role_name": role_name},
    )
    return saved.roles[role_name]


@tool(
    "create_llm_role",
    "新建一个 LLM 角色:给角色名和模型组列表(每组 canonical_id/display_name/"
    "provider_models[{route_id}]),可选 intent(thinking/max_output_tokens/"
    "temperature)。走与 Settings 保存完全相同的服务链;返回 before/after 变更摘要"
    "(before=null)。凭据与 endpoint 不可写。",
    {"name": str, "model_groups": list, "intent": dict},
)
async def create_llm_role_tool(args: dict[str, Any]) -> dict[str, Any]:
    from pydantic import ValidationError

    from app.models.llm_config import RoleEntry, RoleIntent, RoleModelGroup
    from app.routers import llm

    name = str(args.get("name", "")).strip()
    if not name:
        return _text_result("name 不能为空", is_error=True)
    data = llm._load_roles_or_empty()
    if name in data.roles:
        return _text_result(
            f"角色 {name} 已存在;改配置用 update_llm_role", is_error=True
        )
    try:
        fields: dict[str, Any] = {
            "model_groups": [
                RoleModelGroup.model_validate(g) for g in (args.get("model_groups") or [])
            ]
        }
        if args.get("intent") is not None:
            fields["intent"] = RoleIntent.model_validate(args["intent"])
        role = RoleEntry(**fields)
    except ValidationError as exc:
        return _text_result(f"角色配置无效:\n{exc}", is_error=True)
    violation = _model_groups_violation(role.model_groups)
    if violation is not None:
        return _text_result(violation, is_error=True)
    try:
        saved_role = await _save_single_role(name, role)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"create_llm_role 失败: {exc}", is_error=True)
    return _text_result(
        {"role_name": name, "before": None, "after": _role_snapshot(saved_role)}
    )


@tool(
    "update_llm_role",
    "修改既有 LLM 角色。ops 支持:set_model_groups(整表替换=增删/排序)、"
    "model_fallback_enabled(开关)、intent(部分更新 thinking/max_output_tokens/"
    "temperature)。走与 Settings 保存完全相同的服务链;返回 before/after 变更摘要,"
    "用户可据 before 一键撤销。凭据与 endpoint 不可写。",
    {"role_name": str, "ops": dict},
)
async def update_llm_role_tool(args: dict[str, Any]) -> dict[str, Any]:
    from pydantic import ValidationError

    from app.models.llm_config import RoleIntent, RoleModelGroup
    from app.routers import llm

    role_name = str(args.get("role_name", "")).strip()
    if not role_name:
        return _text_result("role_name 不能为空", is_error=True)
    ops = args.get("ops") or {}
    unknown = sorted(set(ops) - set(_ROLE_UPDATE_OPS))
    if unknown:
        return _text_result(
            f"未知 ops {unknown};支持的操作: {list(_ROLE_UPDATE_OPS)}", is_error=True
        )
    data = llm._load_roles_or_empty()
    role = data.roles.get(role_name)
    if role is None:
        return _text_result(
            f"未知 LLM 角色: {role_name};现有角色: {sorted(data.roles)}", is_error=True
        )
    before = _role_snapshot(role)
    try:
        update_fields: dict[str, Any] = {}
        if "set_model_groups" in ops:
            update_fields["model_groups"] = [
                RoleModelGroup.model_validate(g) for g in (ops["set_model_groups"] or [])
            ]
        if "model_fallback_enabled" in ops:
            update_fields["model_fallback_enabled"] = bool(ops["model_fallback_enabled"])
        if "intent" in ops:
            update_fields["intent"] = RoleIntent.model_validate(
                {**role.intent.model_dump(mode="json"), **(ops["intent"] or {})}
            )
        updated = role.model_copy(update=update_fields)
    except ValidationError as exc:
        return _text_result(f"角色配置无效:\n{exc}", is_error=True)
    violation = _model_groups_violation(updated.model_groups)
    if violation is not None:
        return _text_result(violation, is_error=True)
    try:
        saved_role = await _save_single_role(role_name, updated)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"update_llm_role 失败: {exc}", is_error=True)
    return _text_result(
        {"role_name": role_name, "before": before, "after": _role_snapshot(saved_role)}
    )


def build_copilot_mcp_servers() -> dict[str, McpServerConfig]:
    """Chat 会话的 in-process MCP server 集(probe 路不挂,保持探测确定性)。"""

    return {
        COPILOT_MCP_SERVER_NAME: create_sdk_mcp_server(
            name=COPILOT_MCP_SERVER_NAME,
            version="1.0.0",
            tools=[
                get_llm_roles_tool,
                compile_skill_tool,
                run_role_test_tool,
                predict_skill_tool,
                create_llm_role_tool,
                update_llm_role_tool,
            ],
        )
    }
