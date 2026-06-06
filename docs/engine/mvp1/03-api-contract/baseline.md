---
module: 03-api-contract
doc: baseline
status: drafted（B 成段:engine 入口/返回/端点现状对真实代码;字段级形状链 owner 模块不复述）
---

# 03-api-contract — Baseline(现状)

> **Scope**: engine↔studio 操作面的**现状**——engine 入口签名(`runner.py`/`compiler.py`)、返回类型(`result.py`)、事件流落盘、studio HTTP 端点(`apps/studio/backend/app/routers`)的 live/桩 状态。字段级形状不复述(RunResult/ErrorPayload→`data-contracts`、事件 schema→`02-observability`、resume 寻址→`03-checkpoint`)。
> **现状一句话**:三接口面**主体 live**——执行入口(`run_skill`/`predict_skill`/`compile_skill`)、事件流(`event_subscriber`+`trace.jsonl`+WS)、studio 13 端点中 12 live;**唯一 501 桩 = resume**(`runs.py:69`)。golden 逐节点 / iterate loop·图级 / 错误契约 V2 / V4 trace 增补 = target(归各 owner)。

## UI/UX
N/A —— 本域是 API 契约;前端挂载归 studio。

## 前端逻辑
N/A。

## 后端功能

### 1. 执行入口(进程内,SSOT=runner.py/compiler.py)
- `run_skill(...) -> RunResult`(`runner.py:376`)/ `predict_skill(...) -> RunResult`(`:163`)——live;失败不抛(`GraphAgentError`→`success=False` 的 RunResult,`:416-435`)。
- `compile_skill(root, *, chat_model=None, cache=True, skill_resolver) -> CompiledSkill`(`compiler.py:41`)——live。
- 签名全表 + 返回字段见 `mvp1-alignment.md §2.1`(不在此复制)。

### 2. 返回类型(SSOT=result.py)
`RunResult`(`result.py:68`)/ `PhaseRecord`(`:58`)/ `PathDiff`(`:48`)/ `WorkflowMetrics`(`:14`)——live,形状归 `data-contracts`。`error: ErrorPayload | None`(`exceptions.py:21`)。

### 3. 事件流(SSOT=callbacks/events.py)
33 类 typed `CallbackEvent` → `event_subscriber` 回调 + `trace.jsonl`(`emit.py:15`/`tracing.py`)落盘 + WS。live;字段/emit 归 `02-observability`。

### 4. studio HTTP 端点(SSOT=routers/*,现状)
12/13 live:`POST/GET/DELETE /skills/{id}/runs[...]`(`runs.py:27/32/43/53/58`)、batch(`:48`/`:73`)、compile/lint/serialize/validate_input(`skills.py:109/122/454`、`lint.py:13`)、WS(`websockets.py:27`)。**`POST .../runs/{run_id}/resume`(`runs.py:69`)= 501 桩**(`ResumeReq` 已定义、零消费)。端点全表见 `mvp1-alignment.md §3`。

## API
入口签名 + 端点全表见 `mvp1-alignment.md`(§2.1/§3)——本 baseline 只记 live/桩 状态,不复述签名。

## Data Model / State
RunResult/ErrorPayload/CompiledSkill 形状归 `data-contracts`;事件 schema 归 `02-observability`。

## 当前边界(这个模块现在不是什么)
- **不 own 形状/事件/路由实现**:形状→`data-contracts`、事件→`02-observability`、HTTP 路由 → studio(`apps/studio/backend`)。本域只 own**契约**(签名/端点/协议的显式 SSOT)。
- **resume 未实现**:501 桩(归 `03-checkpoint` C2 寻址)。
- **错误契约 V2 / golden 逐节点 / iterate loop·图级 / V4 trace 增补** = target(归 compile-rules§3.1.1 / 06-golden-eval / 02-iterate / 02-observability)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| resume | `runs.py:69` 501 桩 | `resume_run` C2 寻址实现 |
| 错误负载 | ErrorPayload 四轴(部分 emit 未填全) | V2:details/source_span/diagnostics(compile-rules §3.1.1) |
| 错误码表 | 无对外端点 | `GET /errors` 版本化信封 |
| golden | whole-run mock + studio whole-state diff | 逐节点 golden.json + diff SDK |

> **验"是否按 mvp1 改了"**:① resume 从 501 → 真实 checkpoint 寻址续跑;② RunResult 带 `diagnostics` 列表;③ `GET /errors` 可枚举码表。

## 读代码主路径提示
入口 `runner.py:376/163`、`compiler.py:41` → 返回 `result.py:68` → 事件 `callbacks/events.py`+`emit.py` → studio 暴露 `routers/runs.py`/`skills.py`/`websockets.py`。

## 交叉引用(链接, 不复制)
[mvp1-alignment](./mvp1-alignment.md)(签名/端点全表 + Golden/Iterate-Resume/Compile API 面)· `02-mechanism/07-runtime`(入口实现)· `06-seam/02-observability`(事件流)· `01-contract/04-data-contracts`(RunResult/ErrorPayload)· `_migration-src/api-engine-studio-contract.md`(迁移源,已 consolidate)
