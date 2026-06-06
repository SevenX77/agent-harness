---
module: 03-api-contract
doc: mvp1-alignment
status: drafted（A 摘要成段;_migration-src/api-engine-studio-contract 17 块未迁入）
aligns_with: ../00-architecture-overview.md（§4 API契约层 C）
---

# 03-api-contract — API 契约 C · engine↔studio 操作边界

> **Tier**: API 契约层 C | **Owns**: 引擎被 studio 进程内调用(run/predict/compile)+ 事件流 + HTTP 端点 的完整接口 SSOT | **现状**: A 摘要成段;完整表 17 块未迁 | **Related**: `07-runtime`(实现 run/predict 入口)· `06-seam/02-observability`(供事件流)· `data-contracts`(RunResult/ErrorPayload 形状)

## 1. 定义
引擎是被 studio 后端**进程内调用**(`run_skill`/`predict_skill`/`compile_skill`)的库;事件经**回调 + trace.jsonl + WS** 流到前端。本域是这些接口的**显式契约 SSOT**——所有 consumer 只链接、不复制。**它是"怎么调引擎",和契约层 A("skill 是什么")不同类。**

## 2. 三条接口面
| 面 | 形态 | 入口 |
|---|---|---|
| 执行 | 进程内 Python | `run_skill`/`predict_skill`/`compile_skill`(runner.py/compiler.py) |
| 事件 | typed 事件流 → 回调+落盘+WS | `event_subscriber` 回调 + `trace.jsonl`(SSOT)+ WS `/ws/runs/{run_id}` |
| HTTP | REST+WS | `apps/studio/backend/app/routers/*`(studio 暴露面) |

### 2.1 执行签名(SSOT = runner.py)
- `run_skill(skill_path, *, workspace_dir, thread_id?, unattended?, event_subscriber?, skill_resolver(必填), model_resolver?, **inputs) -> RunResult`
- `predict_skill(...同, unattended 默认 True, copilot_predict?) -> RunResult`(干跑/mock;`mock_llm` 经 `**inputs`)
- 失败不抛:`GraphAgentError` 捕获 → `success=False` 的 RunResult(带 `error: ErrorPayload`)。
> RunResult/ErrorPayload 字段形状归 `data-contracts`(本域引用不复制)。
> **错误契约 V2(目标)**:`RunResult` 加 `diagnostics: list[ErrorPayload]`(FATAL+WARN 全集),consumer 一处拿全;`ErrorPayload` 加 `details`/`remediation`。形状归 `data-contracts` DC5、规则归 `compile-rules` §3.1;本域负责 **API 暴露**(diagnostics 字段透传 + 公开错误码表端点,见 §3)。
> `skill_resolver` 的 **DI 协议形状**(输入绝对 path+边界 / 输出子图 root / 失败 raise)归 [`02-resolver`](../02-mechanism/02-resolver/mvp1-alignment.md) §3;本域只定它是 run/compile 的必填参数。

### 2.2 事件协议
33 类 typed `CallbackEvent`(判别字段 `event_type`),字段 SSOT = `callbacks/events.py`(归 `02-observability`);live 走 WS、history 走 HTTP、`trace.jsonl` 落盘 SSOT。
> **错误契约 V2(目标)**:新增 `DiagnosticEmittedEvent`(实时诊断,带完整 `ErrorPayload` + `diagnostic_id`),与 `RunResult.diagnostics`(最终快照,`diagnostic_id` 关联)**双轨、不双写语义**(细化见 `compile-rules` §3.1.1)。

### 2.3 关键异步接缝
引擎 `run_skill` 返回**同步** RunResult;studio `POST .../runs` 返回 RunMetadata(202,**异步** spawn)——接缝在 studio `run_manager`。

## 3. 接口契约(端点索引,完整表见迁移源)
| 端点 | 请求→响应 |
|---|---|
| WS `/ws/runs/{run_id}` | → 事件流 |
| `POST/GET /skills/{id}/runs[/predict]` | → RunMetadata(202) / RunDetail(含 events) |
| `POST .../runs/{run_id}/resume` | ResumeReq → **501 桩**(待 C2 寻址) |
| `POST /skills/{id}/compile` `/lint` | → CompileSuccess/CompileError |
| `GET /errors`(目标,G4) | → 版本化信封 `{registry_version, schema_version, items:[{code,level,stage_id,domain,remediation,doc_ref,doc_url,status}], next_cursor?, etag}` + level/stage/domain/code_prefix/deprecated 过滤(细化见 `compile-rules` §3.1.1);外部 app 自建 error UX |
> consumer(旧 06/09/10/11 关注点)的"接口"段改为**链接本文**,不复制(SSOT)。

## 4. 设计决策基础(用户原话)
> 三层(2026-06-03 PM):"前面还说有3层的,现在怎么就剩2层了?" → C(操作 API)和 A(skill 语言)不同类,独立成层。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| API1 | 共享接口独立成 SSOT,consumer 只链接 | DESIGN-PROCESS §3.2;防各模块各写接口打架 |
| API2 | engine 同步 RunResult ↔ studio 异步 RunMetadata,接缝在 run_manager | 进程内库 vs HTTP 异步 |

## 6. 测试关键点
1. run/predict 都写 `runs/<run_id>/`,`RunResult.source` 区分。
2. `trace.jsonl` 一行一 CallbackEvent;WS live 与 history 一致。

## 7. 涉及 region / platform
engine↔studio 边界;前端 hook 挂载归 studio(本契约只定义引擎产出 + 后端暴露)。

## 8. gaps / 待设计
1. resume `501 桩` → C2 寻址契约落地(与 `02-iterate`/`03-checkpoint` 协同)。
2. V4 trace 增补事件 schema(随 `02-observability` 实现)。
3. golden/iterate target schema 待 FROZEN 解冻回填。
4. **错误契约 V2 API 面(G4/G5)**:`RunResult.diagnostics` 透传 + `GET /errors` 公开码表端点(规则/形状见 `compile-rules` §3.1 / `data-contracts` DC5)——impl 归 kiro。

## 交叉引用(链接, 不复制)
00-architecture-overview §4 · `07-runtime` · `06-seam/02-observability` · `data-contracts`
