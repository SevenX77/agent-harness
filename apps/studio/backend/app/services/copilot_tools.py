"""Copilot 结构化工具 — in-process MCP server 暴露 Studio 后端能力。

与 Settings 鼠标能力对齐(读写对称 + 探测复用):MoirAI 能看/能测/能改的实体,
Settings 也能,反之亦然。所有工具走 routers/llm.py 背后同一条服务链(校验/
canonicalize/级联/领域事件全复用),copilot 绝不直改 `llm/` 配置文件。

- 只读/探测(get_llm_roles/search_llm_registry/compile/run_role_test/predict/
  get_run_detail/list_golden/get_golden_content/test_llm_endpoint(_models)/
  probe_llm_route):天然安全,免审批放行(copilot._DECLARATIVE_ALLOWED_TOOLS)。
- 写/执行(配置真相:create/update/delete role、endpoint 增删、route 增删、apply
  profile;skill 实体:create_skill;真实执行:run_skill;golden 基准:
  set/delete_golden_baseline):一律经 can_use_tool 挂起事前审批
  (copilot._MCP_APPROVAL_WRITE_TOOLS),失败返回结构化错误。旧的
  「零审批直写 + before/after 一键撤销」已整体废除。
- 明文密钥安全隔离:注册表读工具靠 SecretStr 自动脱敏;endpoint 写工具的审批
  明细硬脱敏 api_key。读取明文密钥的 REST 接口绝不投影给 MCP 工具面。
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
    "compile_skill 干净之后的第二级诊断;predict 干净后可用 run_skill"
    "(需用户审批)发起真实运行。",
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


@tool(
    "create_skill",
    "新建一个 skill:落到默认 Skills 目录并登记索引(UI 立即可见)。skill_id 用"
    "小写字母开头、只含小写字母/数字/连字符;files 可选(相对路径→内容),缺省时"
    "服务端自动铺可编译的骨架文件,不留裸目录。创建后用 Write/Edit 完善内容、"
    "compile_skill 验证。属于写操作, 需用户审批。",
    {"skill_id": str, "files": dict},
)
async def create_skill_tool(args: dict[str, Any]) -> dict[str, Any]:
    from pydantic import ValidationError

    from app.core.backends import get_backend_config, get_metadata, get_storage
    from app.models.skills import CreateSkillReq
    from app.services.skills import create_new_skill

    skill_id = str(args.get("skill_id", "")).strip()
    if not skill_id:
        return _text_result("skill_id 不能为空", is_error=True)
    try:
        # 与 POST /api/skills 同一份入参契约(CreateSkillReq 的 pattern/字段校验),
        # 拼写错误在工具边界一次拒绝,不落半成品目录。
        req = CreateSkillReq(skill_id=skill_id, files=dict(args.get("files") or {}))
    except ValidationError as exc:
        return _text_result(f"create_skill 入参无效:\n{exc}", is_error=True)
    try:
        summary = await create_new_skill(
            get_backend_config().default_user_id,
            req.skill_id,
            req.files,
            get_storage(),
            get_metadata(),
        )
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        detail = getattr(exc, "detail", None)
        payload: Any = detail if detail is not None else f"create_skill 失败: {exc}"
        return _text_result(payload, is_error=True)
    return _text_result(
        {
            "status": "success",
            "skill_id": summary.id,
            "directory_path": summary.directory_path,
            "message": f"Skill '{summary.id}' 已创建并登记索引。",
        }
    )


@tool(
    "run_skill",
    "真实运行指定 skill(调用真实 LLM、消耗 token):异步启动,立即返回 run_id 与 "
    "running 状态,之后用 get_run_detail 查询进度与结果。input_data 可选(skill 的"
    "根输入对象);golden_id 可选(用该 golden 用例的输入起跑)。跑前先保证 "
    "compile_skill 干净、predict_skill 无结构性诊断。属于真实执行操作, 需用户审批。",
    {"skill_id": str, "input_data": dict, "golden_id": str},
)
async def run_skill_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.models.runs import RunRequest
    from app.services.run_manager import run_manager

    skill_id = str(args.get("skill_id", "")).strip()
    if not skill_id:
        return _text_result("skill_id 不能为空", is_error=True)
    raw_input = args.get("input_data")
    if raw_input is not None and not isinstance(raw_input, dict):
        return _text_result("input_data 必须是 JSON 对象", is_error=True)
    golden_id = str(args.get("golden_id") or "").strip() or None
    try:
        metadata = await run_manager.start_run(
            skill_id, RunRequest(input_data=raw_input, golden_id=golden_id)
        )
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        detail = getattr(exc, "detail", None)
        payload: Any = detail if detail is not None else f"run_skill 失败: {exc}"
        return _text_result(payload, is_error=True)
    return _text_result(
        {
            "status": metadata.status,
            "run_id": metadata.run_id,
            "started_at": metadata.started_at.isoformat(),
            "detail_hint": f".workspace/runs/{metadata.run_id}/",
            "message": "Run 已启动;用 get_run_detail 轮询状态与结果(勿高频)。",
        }
    )


# get_run_detail 的有界投影参数:错误摘录条数与 final_context 字符上限,把工具
# 结果的 JSON 字符量硬压在 MCP 上限内(同 search_llm_registry 的有界纪律)。
_RUN_ERRORS_LIMIT = 5
_RUN_FINAL_CONTEXT_CHAR_LIMIT = 4000


@tool(
    "get_run_detail",
    "查询一次真实 run 的状态与结果(紧凑投影):整体状态、token 用量、事件类型"
    "计数、错误摘录(最多 5 条)、最终输出(final_context,超长截断)与产物清单。"
    "只读;run 还是 running 时隔一会儿再查,不要高频轮询。逐事件细节用 Read 打开 "
    ".workspace/runs/<run_id>/。",
    {"skill_id": str, "run_id": str},
)
async def get_run_detail_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.run_manager import run_manager

    skill_id = str(args.get("skill_id", "")).strip()
    run_id = str(args.get("run_id", "")).strip()
    if not skill_id or not run_id:
        return _text_result("skill_id 与 run_id 都不能为空", is_error=True)
    try:
        detail = run_manager.get_run_detail(skill_id=skill_id, run_id=run_id)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        payload: Any = getattr(exc, "detail", None) or f"get_run_detail 失败: {exc}"
        return _text_result(payload, is_error=True)

    event_type_counts: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    for event in detail.events:
        event_type_counts[event.event_type] = event_type_counts.get(event.event_type, 0) + 1
        if event.error_code or event.error_payload:
            errors.append(
                {
                    "event_type": event.event_type,
                    "error_code": event.error_code
                    or (event.error_payload.error_code if event.error_payload else None),
                    "message": event.error_payload.message if event.error_payload else None,
                }
            )

    final_context_json: str | None = None
    final_context_truncated = False
    if detail.final_context is not None:
        final_context_json = json.dumps(detail.final_context, ensure_ascii=False)
        if len(final_context_json) > _RUN_FINAL_CONTEXT_CHAR_LIMIT:
            final_context_json = final_context_json[:_RUN_FINAL_CONTEXT_CHAR_LIMIT]
            final_context_truncated = True

    metadata = detail.metadata
    return _text_result(
        {
            "run_id": metadata.run_id,
            "status": metadata.status,
            "started_at": metadata.started_at.isoformat(),
            "metrics": metadata.metrics.model_dump(mode="json") if metadata.metrics else None,
            "input_summary": metadata.input_summary,
            "events_total": len(detail.events),
            "event_type_counts": event_type_counts,
            "errors": errors[-_RUN_ERRORS_LIMIT:],
            "errors_total": len(errors),
            "artifacts": detail.artifacts,
            "final_context_json": final_context_json,
            "final_context_truncated": final_context_truncated,
            "detail_hint": f".workspace/runs/{metadata.run_id}/",
        }
    )


# golden 基准工具(旅程 04 验收面):读走与 GET /golden 同一条服务链;写(set/
# delete)直调 golden_diff 服务层——HTTP 路由上的 X-Studio-Write-Fallback 护栏
# 是针对"浏览器绕过 Rust native-fs"的边界,copilot 后端写是 MVP1 已接受的独立
# 授权写路径(同 Write/Edit 例外,DEF-027),权限由审批卡兜底,不装浏览器头。


@tool(
    "list_golden",
    "列出指定 skill 的全部 golden 基准(验收基线):每条给 id、来源 run、锁定态、"
    "创建时间与各节点 case 概览。只读;看某条基准里到底存了什么用 "
    "get_golden_content。",
    {"skill_id": str},
)
async def list_golden_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.services import golden_diff

    skill_id = str(args.get("skill_id", "")).strip()
    if not skill_id:
        return _text_result("skill_id 不能为空", is_error=True)
    try:
        baselines = golden_diff.list_golden_baselines_for_skill(skill_id)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        payload: Any = getattr(exc, "detail", None) or f"list_golden 失败: {exc}"
        return _text_result(payload, is_error=True)
    return _text_result(
        {
            "golden_count": len(baselines),
            "baselines": [
                {
                    "id": b.id,
                    "source_run_id": b.source_run_id,
                    "linked_input_id": b.linked_input_id,
                    "created_at": b.created_at.isoformat(),
                    "locked": b.locked,
                    "cases": [
                        {"case_id": c.case_id, "node_id": c.node_id} for c in b.cases
                    ],
                }
                for b in baselines
            ],
        }
    )


# 单个 golden case 的 expected_output 字符上限(有界纪律,同 get_run_detail)。
_GOLDEN_CASE_CHAR_LIMIT = 4000


@tool(
    "get_golden_content",
    "读取一条 golden 基准的实际内容:每个节点 case 的 expected_output(超长截断)。"
    "node_id 可选,只看某一个节点的 case。只读。",
    {"skill_id": str, "golden_id": str, "node_id": str},
)
async def get_golden_content_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.services import golden_diff

    skill_id = str(args.get("skill_id", "")).strip()
    golden_id = str(args.get("golden_id", "")).strip()
    if not skill_id or not golden_id:
        return _text_result("skill_id 与 golden_id 都不能为空", is_error=True)
    node_id = str(args.get("node_id") or "").strip() or None
    try:
        content = golden_diff.read_golden_baseline_content(
            skill_id, golden_id, node_id=node_id
        )
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        payload: Any = getattr(exc, "detail", None) or f"get_golden_content 失败: {exc}"
        return _text_result(payload, is_error=True)

    cases: list[dict[str, Any]] = []
    for case in content.cases:
        expected_json = json.dumps(case.expected_output, ensure_ascii=False)
        truncated = len(expected_json) > _GOLDEN_CASE_CHAR_LIMIT
        cases.append(
            {
                "case_id": case.case_id,
                "node_id": case.node_id,
                "phase_id": case.phase_id,
                "expected_output_json": expected_json[:_GOLDEN_CASE_CHAR_LIMIT],
                "expected_output_truncated": truncated,
            }
        )
    return _text_result(
        {
            "id": content.id,
            "source_run_id": content.source_run_id,
            "locked": content.locked,
            "cases": cases,
        }
    )


@tool(
    "set_golden_baseline",
    "把一次已完成的真实 run 的输出定为 golden 基准(验收基线):run 必须已成功收口"
    "(sealed)。node_id 可选(只提升该节点);lock 可选(锁定基准防误改)。"
    "属于写操作, 需用户审批。",
    {"skill_id": str, "run_id": str, "lock": bool, "node_id": str},
)
async def set_golden_baseline_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.services import golden_diff

    skill_id = str(args.get("skill_id", "")).strip()
    run_id = str(args.get("run_id", "")).strip()
    if not skill_id or not run_id:
        return _text_result("skill_id 与 run_id 都不能为空", is_error=True)
    node_id = str(args.get("node_id") or "").strip() or None
    lock = bool(args.get("lock", False))
    try:
        baseline = golden_diff.set_golden_baseline_for_run(
            skill_id, run_id, lock=lock, node_id=node_id
        )
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        payload: Any = getattr(exc, "detail", None) or f"set_golden_baseline 失败: {exc}"
        return _text_result(payload, is_error=True)
    return _text_result(
        {
            "status": "success",
            "golden_id": baseline.id,
            "locked": baseline.locked,
            "case_count": len(baseline.cases),
            "message": f"Run '{run_id}' 已定为 golden 基准 '{baseline.id}'。",
        }
    )


@tool(
    "delete_golden_baseline",
    "删除一条 golden 基准。属于写操作, 需用户审批。",
    {"skill_id": str, "golden_id": str},
)
async def delete_golden_baseline_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.services import golden_diff

    skill_id = str(args.get("skill_id", "")).strip()
    golden_id = str(args.get("golden_id", "")).strip()
    if not skill_id or not golden_id:
        return _text_result("skill_id 与 golden_id 都不能为空", is_error=True)
    try:
        golden_diff.delete_golden_baseline_for_skill(skill_id, golden_id)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        payload: Any = getattr(exc, "detail", None) or f"delete_golden_baseline 失败: {exc}"
        return _text_result(payload, is_error=True)
    return _text_result(
        {
            "status": "success",
            "golden_id": golden_id,
            "message": f"Golden 基准 '{golden_id}' 已删除。",
        }
    )


# 角色配置写工具(R10):经 routers/llm.py 背后同一条服务链(校验/canonicalize/
# 级联/领域事件全复用),绝不直写配置文件;凭据与 endpoint 不提供写入(R10.3)。
# 入参形状=扁平路由链(读写对称,Requirement 12):客户端只给 route_id 列表,组结构
# (canonical_id/display_name/分组)一律由服务端查注册表派生,客户端永不拼 canonical。
_ROLE_UPDATE_OPS = ("set_fallback_chain", "model_fallback_enabled", "intent")


class _FlatRouteInputError(ValueError):
    """MCP 边界拒绝:扁平路由链里出现无法解析或注册表中不存在的 route_id。

    诊断信息本身即最终返回给模型的文本,一次列全所有非法项(不止第一个)。"""


def _route_id_from_item(item: Any, index: int) -> str:
    """宽容解包一个扁平路由项 → route_id。

    元素可为纯 `str`(route_id),或含 `route_id` 键的 `dict`(其余字段——如 MoirAI
    从 get_llm_roles 读回来的物化 `runtime_settings`——静默丢弃)。这样 MoirAI「读到
    什么原样写回什么」不会因携带多余字段爆 ValidationError(Requirement 12.2)。"""

    if isinstance(item, str):
        route_id = item.strip()
    elif isinstance(item, dict):
        raw = item.get("route_id")
        route_id = raw.strip() if isinstance(raw, str) else ""
    else:
        raise _FlatRouteInputError(
            f"fallback_chain[{index}] 无法解析出 route_id"
            f"(元素须为 route_id 字符串或含 route_id 键的对象): {item!r}"
        )
    if not route_id:
        raise _FlatRouteInputError(f"fallback_chain[{index}] 的 route_id 为空")
    return route_id


def _route_display_name(route: Any, canonical_id: str) -> str:
    """组的 display_name 派生源:优先 ProviderRoute.display_name,其次 metadata,
    都缺则降级为 canonical_id(不假设字段一定存在)。"""

    name = getattr(route, "display_name", None)
    if isinstance(name, str) and name.strip():
        return name
    metadata = getattr(route, "metadata", None)
    if isinstance(metadata, dict):
        meta_name = metadata.get("display_name")
        if isinstance(meta_name, str) and meta_name.strip():
            return meta_name
    return canonical_id


def _transform_fallback_chain_to_model_groups(
    fallback_chain: list[Any],
    credentials: Any,
) -> list[Any]:
    """把 MoirAI 传入的扁平路由链转换成底层的 RoleModelGroup 列表(Requirement 12.3)。

    对每个 route_id 查 `credentials.provider_routes` 的 ProviderRoute,取其**派生**
    `canonical_id`(gateway 的 computed_field),按 canonical 首次出现顺序建组、组内
    保持传入顺序、同组内去重同一 route_id。任一 route_id 不在注册表中 → 一次列全所有
    非法项后 fail-fast(Requirement 12.4),杜绝毒数据落盘。"""

    from app.models.llm_config import RoleModelGroup, RoleProviderModel

    provider_routes = credentials.provider_routes
    route_ids = [_route_id_from_item(item, i) for i, item in enumerate(fallback_chain)]

    unknown = [rid for rid in dict.fromkeys(route_ids) if rid not in provider_routes]
    if unknown:
        raise _FlatRouteInputError(
            "以下 route_id 不在当前凭据注册表中"
            "(先用 search_llm_registry 查合法 route_id):\n"
            + "\n".join(f"  - {rid}" for rid in unknown)
        )

    groups_map: dict[str, Any] = {}
    ordered_canonicals: list[str] = []
    for route_id in route_ids:
        route = provider_routes[route_id]
        canonical_id = route.canonical_id
        group = groups_map.get(canonical_id)
        if group is None:
            group = RoleModelGroup(
                canonical_id=canonical_id,
                display_name=_route_display_name(route, canonical_id),
                provider_models=[],
            )
            groups_map[canonical_id] = group
            ordered_canonicals.append(canonical_id)
        if not any(pm.route_id == route_id for pm in group.provider_models):
            group.provider_models.append(RoleProviderModel(route_id=route_id))
    return [groups_map[cid] for cid in ordered_canonicals]


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
    "新建一个 LLM 角色:给角色名和 fallback_chain(**扁平 route_id 列表**,元素为 "
    "route_id 字符串或 {route_id} 对象;服务端查注册表按派生 canonical 自动分组、补 "
    "display_name,你不用自己拼 canonical/组结构)。可选 intent(thinking/"
    "max_output_tokens/temperature)。走与 Settings 保存完全相同的服务链;属于写配置操作, "
    "需用户审批。凭据与 endpoint 不可写。先用 search_llm_registry 查合法 route_id。",
    {"name": str, "fallback_chain": list, "intent": dict},
)
async def create_llm_role_tool(args: dict[str, Any]) -> dict[str, Any]:
    from pydantic import ValidationError

    from app.models.llm_config import RoleEntry, RoleIntent
    from app.routers import llm
    from app.services import llm_credentials

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
            "model_groups": _transform_fallback_chain_to_model_groups(
                list(args.get("fallback_chain") or []), llm_credentials.load_credentials()
            )
        }
        if args.get("intent") is not None:
            fields["intent"] = RoleIntent.model_validate(args["intent"])
        role = RoleEntry(**fields)
    except _FlatRouteInputError as exc:
        return _text_result(str(exc), is_error=True)
    except ValidationError as exc:
        return _text_result(f"角色配置无效:\n{exc}", is_error=True)
    try:
        await _save_single_role(name, role)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"create_llm_role 失败: {exc}", is_error=True)
    return _text_result(
        {"status": "success", "role_name": name, "message": f"LLM Role '{name}' 创建成功。"}
    )


@tool(
    "update_llm_role",
    "修改既有 LLM 角色。ops 支持:set_fallback_chain(**扁平 route_id 列表**,整表替换"
    "=增删/排序;元素为 route_id 字符串或 {route_id} 对象,服务端按派生 canonical 自动"
    "分组,你可把 get_llm_roles 读到的 fallback_chain 原样写回)、model_fallback_enabled"
    "(开关)、intent(部分更新 thinking/max_output_tokens/temperature)。走与 Settings 保存"
    "完全相同的服务链;属于写配置操作, 需用户审批。凭据与 endpoint 不可写。",
    {"role_name": str, "ops": dict},
)
async def update_llm_role_tool(args: dict[str, Any]) -> dict[str, Any]:
    from pydantic import ValidationError

    from app.models.llm_config import RoleIntent
    from app.routers import llm
    from app.services import llm_credentials

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
    try:
        update_fields: dict[str, Any] = {}
        if "set_fallback_chain" in ops:
            update_fields["model_groups"] = _transform_fallback_chain_to_model_groups(
                list(ops["set_fallback_chain"] or []), llm_credentials.load_credentials()
            )
        if "model_fallback_enabled" in ops:
            update_fields["model_fallback_enabled"] = bool(ops["model_fallback_enabled"])
        if "intent" in ops:
            update_fields["intent"] = RoleIntent.model_validate(
                {**role.intent.model_dump(mode="json"), **(ops["intent"] or {})}
            )
        updated = role.model_copy(update=update_fields)
    except _FlatRouteInputError as exc:
        return _text_result(str(exc), is_error=True)
    except ValidationError as exc:
        return _text_result(f"角色配置无效:\n{exc}", is_error=True)
    try:
        await _save_single_role(role_name, updated)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"update_llm_role 失败: {exc}", is_error=True)
    return _text_result(
        {
            "status": "success",
            "role_name": role_name,
            "message": f"LLM Role '{role_name}' 更新成功。",
        }
    )


# ── 词汇发现 · 只读 ──────────────────────────────────────────────────────────


# 结果有界纪律:搜索工具单次最多返回这么多 canonical 组,把 JSON 字符量硬压在
# MCP 工具结果上限内,从结构上根除全量转储撑爆上下文(旧 get_llm_registry 的病根)。
_SEARCH_REGISTRY_LIMIT_DEFAULT = 20
_SEARCH_REGISTRY_LIMIT_MAX = 50


def _search_registry_projection(
    registry: Any,
    query: str,
    limit: int,
) -> dict[str, Any]:
    """把全量注册表投影成搜索驱动、结果有界的紧凑词汇视图。

    只投影配置写调用真正需要的词汇字段:每个 canonical 组 → display_name →
    其 routes[{route_id, endpoint_id, status, is_official}]。probe_catalog /
    社区目录 / 逐路由运行时元数据 / lint 结果一律不投影(结构上不可能撑爆上下文)。
    分组只认注册表当前产出的 canonical_id —— 对 canonicalization 结果保持中立。
    """

    tokens = [t for t in query.lower().split() if t]
    matched: list[dict[str, Any]] = []
    for group in registry.canonical_groups:
        canonical_id = str(group.get("canonical_id", ""))
        display_name = str(group.get("display_name", canonical_id))
        route_ids = [str(rid) for rid in group.get("routes", [])]
        routes: list[dict[str, Any]] = []
        endpoint_ids: list[str] = []
        for route_id in route_ids:
            route = registry.provider_routes.get(route_id)
            if route is None:
                continue
            endpoint = registry.provider_endpoints.get(route.endpoint_id)
            endpoint_ids.append(route.endpoint_id)
            routes.append(
                {
                    "route_id": route.route_id,
                    "endpoint_id": route.endpoint_id,
                    "status": route.status,
                    "is_official": endpoint is not None
                    and endpoint.provider_kind == "official",
                }
            )
        haystack = " ".join([canonical_id, display_name, *endpoint_ids]).lower()
        if all(token in haystack for token in tokens):
            matched.append(
                {
                    "canonical_id": canonical_id,
                    "display_name": display_name,
                    "routes": routes,
                }
            )
    return {
        "canonical_groups": matched[:limit],
        "total_count": len(matched),
        "returned_count": min(len(matched), limit),
    }


@tool(
    "search_llm_registry",
    "模糊搜索 Studio 注册表里可用的法定模型(canonical groups)及其路由。配置发现的"
    "首选第一步:结果按 canonical_id 分组、结果有界(默认 20 条、硬上限 50),对 "
    "canonical_id / display_name / endpoint_id 做模糊匹配。每条 route 只给 route_id / "
    "endpoint_id / status / is_official(官方直连)。新增/更新角色前先用它核对合法的 "
    "canonical_id / route_id, 消灭拼错。",
    {"query": str, "limit": int},
)
async def search_llm_registry_tool(args: dict[str, Any]) -> dict[str, Any]:
    # 与 GET /api/llm/registry 同一条真相路径(载入凭据+角色→CPU-bound 投影→
    # SecretStr 自动脱敏),不自建第二份读取逻辑;拿到全量后服务端过滤 + 紧凑投影。
    from app.routers import llm

    query = str(args.get("query") or "").strip()
    raw_limit = args.get("limit")
    limit = _SEARCH_REGISTRY_LIMIT_DEFAULT if raw_limit is None else int(raw_limit)
    limit = max(1, min(limit, _SEARCH_REGISTRY_LIMIT_MAX))
    try:
        registry = await llm.get_llm_registry()
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"search_llm_registry 失败: {exc}", is_error=True)
    return _text_result(_search_registry_projection(registry, query, limit))


# ── 角色写工具(需审批) ──────────────────────────────────────────────────────


@tool(
    "delete_llm_role",
    "删除一个持久化的自定义 LLM 角色。内置固定角色(如 copilot)不可删除。"
    "属于写配置操作, 需用户审批。",
    {"role_name": str},
)
async def delete_llm_role_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.routers import llm
    from app.services.llm_fixed_roles import is_fixed_role

    role_name = str(args.get("role_name", "")).strip()
    if not role_name:
        return _text_result("role_name 不能为空", is_error=True)
    if is_fixed_role(role_name):
        return _text_result(f"固定内置角色无法删除: {role_name}", is_error=True)
    try:
        await llm.delete_llm_role(role_name)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"delete_llm_role 失败: {exc}", is_error=True)
    return _text_result(
        {"status": "success", "role_name": role_name, "message": f"LLM Role '{role_name}' 已删除。"}
    )


@tool(
    "apply_model_profile_to_role",
    "将预设的 Model Profile(某模型推荐的路由组配置)整表应用覆盖到指定角色。"
    "属于写配置操作, 需用户审批。",
    {"role_name": str, "model_profile_id": str},
)
async def apply_model_profile_to_role_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.routers import llm
    from app.routers.llm import RoleApplyProfileRequest

    role_name = str(args.get("role_name", "")).strip()
    profile_id = str(args.get("model_profile_id", "")).strip()
    if not role_name or not profile_id:
        return _text_result("role_name 和 model_profile_id 不能为空", is_error=True)
    try:
        req = RoleApplyProfileRequest(model_profile_id=profile_id, mode="replace")
        await llm.apply_model_profile(role_name, req)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"apply_model_profile_to_role 失败: {exc}", is_error=True)
    return _text_result(
        {
            "status": "success",
            "role_name": role_name,
            "message": f"已将 Profile '{profile_id}' 应用于角色 '{role_name}'。",
        }
    )


# ── Endpoint 写工具(需审批) ────────────────────────────────────────────────


@tool(
    "upsert_llm_endpoint",
    "新增或修改一个 LLM 提供商凭据(Endpoint):endpoint_id 已存在则更新、否则创建。"
    "protocol 取 openai_compatible / anthropic_compatible / google_genai / ark_runtime;"
    "api_key 留空代表不改动已有 key(审批明细里会自动脱敏)。属于写配置操作, 需用户审批。",
    {
        "endpoint_id": str,
        "display_name": str,
        "protocol": str,
        "base_url": str,
        "api_key": str,
    },
)
async def upsert_llm_endpoint_tool(args: dict[str, Any]) -> dict[str, Any]:
    from pydantic import ValidationError

    from app.models.llm_config import ProviderEndpoint
    from app.routers import llm
    from app.routers.llm import EndpointUpsertRequest

    eid = str(args.get("endpoint_id", "")).strip()
    if not eid:
        return _text_result("endpoint_id 不能为空", is_error=True)
    fields: dict[str, Any] = {
        "endpoint_id": eid,
        "display_name": str(args.get("display_name") or eid),
        "protocol": str(args.get("protocol") or "openai_compatible"),
        "base_url": str(args.get("base_url") or ""),
    }
    if args.get("api_key"):
        fields["api_key"] = args["api_key"]
    try:
        endpoint = ProviderEndpoint.model_validate(fields)
        req = EndpointUpsertRequest(provider_endpoints={eid: endpoint})
        await llm.put_registry_endpoints(req)
    except ValidationError as exc:
        return _text_result(f"endpoint 配置无效:\n{exc}", is_error=True)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"upsert_llm_endpoint 失败: {exc}", is_error=True)
    return _text_result(
        {"status": "success", "endpoint_id": eid, "message": f"Endpoint '{eid}' 配置已更新。"}
    )


@tool(
    "delete_llm_endpoint",
    "删除指定 Endpoint 凭据 —— 级联删除其下属所有 Route, 并清除所有角色对这些 Route 的引用。"
    "影响较大, 属于写配置操作, 需用户审批。",
    {"endpoint_id": str},
)
async def delete_llm_endpoint_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.routers import llm

    eid = str(args.get("endpoint_id", "")).strip()
    if not eid:
        return _text_result("endpoint_id 不能为空", is_error=True)
    try:
        await llm.delete_registry_endpoint(eid)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"delete_llm_endpoint 失败: {exc}", is_error=True)
    return _text_result(
        {
            "status": "success",
            "endpoint_id": eid,
            "message": f"Endpoint '{eid}' 及其关联路由/角色引用已清除。",
        }
    )


# ── Route 写工具(需审批) ────────────────────────────────────────────────────


@tool(
    "update_llm_route",
    "修改一条 Route 的可编辑元数据(不改身份):display_name、canonical_id、status"
    "(verified/unverified_manual/disabled/failed)。属于写配置操作, 需用户审批。",
    {"route_id": str, "display_name": str, "canonical_id": str, "status": str},
)
async def update_llm_route_tool(args: dict[str, Any]) -> dict[str, Any]:
    from pydantic import ValidationError

    from app.routers import llm
    from app.routers.llm import RouteEditableUpdate

    route_id = str(args.get("route_id", "")).strip()
    if not route_id:
        return _text_result("route_id 不能为空", is_error=True)
    try:
        req = RouteEditableUpdate(
            display_name=str(args.get("display_name") or ""),
            canonical_id=str(args.get("canonical_id") or ""),
            status=str(args.get("status") or "unverified_manual"),  # type: ignore[arg-type]
        )
        await llm.put_route_metadata(route_id, req)
    except ValidationError as exc:
        return _text_result(f"route 配置无效:\n{exc}", is_error=True)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"update_llm_route 失败: {exc}", is_error=True)
    return _text_result(
        {"status": "success", "route_id": route_id, "message": f"Route '{route_id}' 已更新。"}
    )


@tool(
    "delete_llm_route",
    "删除一条 Route。仍被角色/预设包引用时后端会拒绝(先解除引用再删)。"
    "属于写配置操作, 需用户审批。",
    {"route_id": str},
)
async def delete_llm_route_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.routers import llm

    route_id = str(args.get("route_id", "")).strip()
    if not route_id:
        return _text_result("route_id 不能为空", is_error=True)
    try:
        await llm.delete_registry_route(route_id)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"delete_llm_route 失败: {exc}", is_error=True)
    return _text_result(
        {"status": "success", "route_id": route_id, "message": f"Route '{route_id}' 已删除。"}
    )


# ── 探测/测试工具(只读, 免审批) ────────────────────────────────────────────


@tool(
    "test_llm_endpoint",
    "测试一个 Endpoint 的连通性(发 provider 的最小 models-list 调用), 返回注册表快照。"
    "只探测、不改配置词汇。排障凭结构化状态判断, 绝不读取明文密钥。",
    {"endpoint_id": str},
)
async def test_llm_endpoint_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.routers import llm

    eid = str(args.get("endpoint_id", "")).strip()
    if not eid:
        return _text_result("endpoint_id 不能为空", is_error=True)
    try:
        response = await llm.test_endpoint(eid)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"test_llm_endpoint 失败: {exc}", is_error=True)
    return _text_result(response.model_dump(mode="json"))


@tool(
    "test_llm_endpoint_models",
    "对一个 Endpoint 探测一批模型 ID 的可用性(逐模型 status + message), 并 upsert 路由结果。"
    "只探测、不改配置词汇。",
    {"endpoint_id": str, "model_ids": list},
)
async def test_llm_endpoint_models_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.routers import llm
    from app.routers.llm import EndpointModelTestRequest

    eid = str(args.get("endpoint_id", "")).strip()
    if not eid:
        return _text_result("endpoint_id 不能为空", is_error=True)
    try:
        req = EndpointModelTestRequest(model_ids=list(args.get("model_ids") or []))
        response = await llm.test_endpoint_models(eid, req)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"test_llm_endpoint_models 失败: {exc}", is_error=True)
    return _text_result(response.model_dump(mode="json"))


@tool(
    "probe_llm_route",
    "探测一条 Route 的连通性/能力(真实探测该模型), 返回更新后的注册表快照。"
    "只探测、不改配置词汇。",
    {"route_id": str},
)
async def probe_llm_route_tool(args: dict[str, Any]) -> dict[str, Any]:
    from app.routers import llm
    from app.routers.llm import RouteProbeRequest

    route_id = str(args.get("route_id", "")).strip()
    if not route_id:
        return _text_result("route_id 不能为空", is_error=True)
    try:
        response = await llm.probe_route(route_id, RouteProbeRequest(), force=True)
    except Exception as exc:  # noqa: BLE001 — 工具边界:任何失败都落成 is_error
        return _text_result(f"probe_llm_route 失败: {exc}", is_error=True)
    return _text_result(response.model_dump(mode="json"))


def _copilot_mcp_tools() -> list[Any]:
    """MoirAI 面向 Settings 鼠标能力的 MCP 工具全集(读写对称 + 探测复用)。
    写工具经 can_use_tool 挂起审批(见 copilot._MCP_APPROVAL_WRITE_TOOLS),读/探测
    工具在 copilot._DECLARATIVE_ALLOWED_TOOLS 免审批放行。"""

    return [
        get_llm_roles_tool,
        search_llm_registry_tool,
        compile_skill_tool,
        run_role_test_tool,
        predict_skill_tool,
        create_skill_tool,
        run_skill_tool,
        get_run_detail_tool,
        list_golden_tool,
        get_golden_content_tool,
        set_golden_baseline_tool,
        delete_golden_baseline_tool,
        create_llm_role_tool,
        update_llm_role_tool,
        delete_llm_role_tool,
        apply_model_profile_to_role_tool,
        upsert_llm_endpoint_tool,
        delete_llm_endpoint_tool,
        update_llm_route_tool,
        delete_llm_route_tool,
        test_llm_endpoint_tool,
        test_llm_endpoint_models_tool,
        probe_llm_route_tool,
    ]


def build_copilot_mcp_servers() -> dict[str, McpServerConfig]:
    """Chat 会话的 in-process MCP server 集(probe 路不挂,保持探测确定性)。"""

    return {
        COPILOT_MCP_SERVER_NAME: create_sdk_mcp_server(
            name=COPILOT_MCP_SERVER_NAME,
            version="1.0.0",
            tools=[
                *_copilot_mcp_tools(),
            ],
        )
    }
