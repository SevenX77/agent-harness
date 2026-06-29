---
module: 03-api-contract
doc: baseline
status: drafted（WS-E7 回写:engine 入口/返回/端点现状对真实代码;RunResult.diagnostics 与 error catalog export 已 live;Engine resume/golden public API 已 live;Studio HTTP resume 仍 501）
---

# 03-api-contract — Baseline(现状)

> **Scope**: engine↔studio 操作面的**现状**——engine 入口签名(`runner.py`/`compiler.py`)、返回类型(`result.py`)、事件流落盘、studio HTTP 端点(`apps/studio/backend/app/routers`)的 live/桩 状态。字段级形状不复述(RunResult/ErrorPayload→`data-contracts`、事件 schema→`02-observability`、resume 寻址→`03-checkpoint`)。
> **现状一句话**:三接口面**主体 live**——Engine 进程内入口(`run_skill`/`predict_skill`/`resume_skill`/`evaluate_golden_baseline`/`compile_skill`)、事件流(`event_subscriber`+`trace.jsonl`+WS)、studio 13 端点中 12 live;**Studio HTTP 唯一 501 桩仍是 resume**(`runs.py:69`)。WS-E3 P0-1 已让 run/predict `RunResult` 暴露 `diagnostics` 最终快照;WS-E3 P0-2 已在 engine 内提供 `export_error_catalog()` / `export_error_metadata(code)` 作为错误目录 SSOT，但没有实现 Studio HTTP `GET /errors` route。

## UI/UX
N/A —— 本域是 API 契约;前端挂载归 studio。

## 前端逻辑
N/A。

## 后端功能

### 1. 执行入口(进程内,SSOT=runner.py/compiler.py)
- `run_skill(...) -> RunResult`(`runner.py:376`)/ `predict_skill(...) -> RunResult`(`:163`)/ `resume_skill(...) -> RunResult` / `evaluate_golden_baseline(...) -> dict[str, Any]`——Engine 进程内 public API live;`run_skill` 失败不抛(`GraphAgentError`→`success=False` 的 RunResult,`:416-435`)。
- `compile_skill(root, *, chat_model=None, cache=True, skill_resolver) -> CompiledSkill`(`compiler.py:41`)——live。
- 签名全表 + 返回字段见 `mvp1-alignment.md §2.1`(不在此复制)。

### 2. 返回类型(SSOT=result.py)
`RunResult`(`result.py:68`)/ `PhaseRecord`(`:58`)/ `PathDiff`(`:48`)/ `WorkflowMetrics`(`:14`)——live,形状归 `data-contracts`。`error: ErrorPayload | None`(`exceptions.py:48`) 仍是主 fatal 兼容面。

WS-E3 P0-1 后，run/predict 返回模型新增诊断快照字段:

- `diagnostics: list[ErrorPayload]`(`result.py:86`):最终有界诊断快照。
- `diagnostics_limit: int`(`:87`,默认 100)。
- `diagnostics_truncated: bool`(`:88`)。
- `diagnostic_counts: dict[str, Any]`(`:89`,JSON 形状 `{total, by_level, by_code}`)。

这些字段随 `RunResult.model_dump(mode="json")` 出现在 `result.json` 写盘边界;真实 `run_skill` 缺 `GRAPH.md` 失败结果已能同时保留主 `error` 和 diagnostics 中的同一主 fatal。`predict_skill` 成功结果默认 diagnostics 为空;调用方显式传入 WARN diagnostics 时会保留。

### 3. 事件流(SSOT=callbacks/events.py)
33 类 typed `CallbackEvent` → `event_subscriber` 回调 + `trace.jsonl`(`emit.py:15`/`tracing.py`)落盘 + WS。live;字段/emit 归 `02-observability`。WS-E3 P0-1 **未**新增 `DiagnosticEmittedEvent`，也未改 `CallbackEvent` union/`emit.py`;诊断实时事件仍属 WS-E4 后续范围。

### 4. Engine-side 错误目录导出(SSOT=core/error_registry.py)
WS-E3 P0-2 后，engine 提供进程内错误目录读取契约:

- `export_error_catalog() -> dict[str, Any]`:返回 `{registry_version, schema_version, items}` envelope；当前 `registry_version="engine-mvp1.error-catalog.v1"`，`schema_version="engine-mvp1.error-metadata.v1"`。
- `export_error_metadata(code: str) -> dict[str, Any]`:返回单个 code 的 JSON-safe catalog item；unknown engine code 继续拒绝。
- 每个 item 至少包含 `code/level/stage/domain/remediation/doc_link/doc_ref/doc_url/status/details_schema/schema_version`。`stage` 在 export 边界是 list，items 按 code 字符串稳定排序，适合 snapshot/HTTP cache。

这是 host/app 的 engine SSOT。当前未做 Studio route；如果后续加 `GET /errors`，HTTP 层只能薄透传这个 engine export，不能复制 registry 数据。

### 5. studio HTTP 端点(SSOT=routers/*,现状)
12/13 live:`POST/GET/DELETE /skills/{id}/runs[...]`(`runs.py:27/32/43/53/58`)、batch(`:48`/`:73`)、compile/lint/serialize/validate_input(`skills.py:109/122/454`、`lint.py:13`)、WS(`websockets.py:27`)。**`POST .../runs/{run_id}/resume`(`runs.py:69`)= 501 桩**(`ResumeReq` 已定义、零消费)。端点全表见 `mvp1-alignment.md §3`。

## API
入口签名 + 端点全表见 `mvp1-alignment.md`(§2.1/§3)——本 baseline 只记 live/桩 状态,不复述签名。

## Data Model / State
RunResult/ErrorPayload/CompiledSkill 形状归 `data-contracts`;事件 schema 归 `02-observability`。

## 当前边界(这个模块现在不是什么)
- **不 own 形状/事件/路由实现**:形状→`data-contracts`、事件→`02-observability`、HTTP 路由 → studio(`apps/studio/backend`)。本域只 own**契约**(签名/端点/协议的显式 SSOT)。
- **Studio HTTP resume 未实现**:`POST .../runs/{run_id}/resume` 仍是 501 桩;Engine 进程内 `resume_skill` 已实现 checkpoint 寻址续跑、context overrides 与 HITL ToolMessage 注入。
- **Studio `GET /errors` route / iterate loop·图级 / DiagnosticEmittedEvent** = target(归后续 Studio thin route / 02-iterate / 02-observability)。P0-1 的 `details` + `diagnostics` 已 live；P0-2 的 engine-side catalog export 已 live；WS-E7 的 Engine golden eval 已 live。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| resume | Engine `resume_skill` 已 live;Studio `runs.py:69` HTTP route 仍 501 桩 | Studio route 薄接 Engine resume API |
| 错误负载 | `ErrorPayload.details` + `RunResult.diagnostics` 已 live;部分定位轴 emit 仍未填全 | V2 后续:`source_span`/`phase_path`/diagnostic event(compile-rules §3.1.1) |
| 错误码表 | engine-side `export_error_catalog()` / `export_error_metadata(code)` 已 live；Studio HTTP route 仍未 live | 若做 `GET /errors`，只能薄透传 engine 版本化信封 |
| golden | Engine `evaluate_golden_baseline` 已逐节点 diff/report;Studio 旧 whole-state diff 仍存在 | Studio UI/HTTP 消费 Engine report,不复制评估规则 |

> **验"是否按 mvp1 改了"**:① Engine `resume_skill` 能真实 checkpoint 寻址续跑;② Studio HTTP resume 从 501 薄接 Engine API;③ Studio `GET /errors` 可枚举码表且薄透传 engine export;④ `DiagnosticEmittedEvent` 实时诊断事件 live。`RunResult.diagnostics` 列表已由 WS-E3 P0-1 完成；engine-side catalog export 已由 WS-E3 P0-2 完成；Engine golden eval 已由 WS-E7 完成。

## 读代码主路径提示
入口 `runner.py:376/163`、`compiler.py:41` → 返回 `result.py:68` → 错误目录 `core/error_registry.py:export_error_catalog` → 事件 `callbacks/events.py`+`emit.py` → studio 暴露 `routers/runs.py`/`skills.py`/`websockets.py`。

## 交叉引用(链接, 不复制)
[mvp1-alignment](./mvp1-alignment.md)(签名/端点全表 + Golden/Iterate-Resume/Compile API 面)· `02-mechanism/07-runtime`(入口实现)· `06-seam/02-observability`(事件流)· `01-contract/04-data-contracts`(RunResult/ErrorPayload)
