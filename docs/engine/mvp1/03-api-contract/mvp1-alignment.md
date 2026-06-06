---
module: 03-api-contract
doc: mvp1-alignment
status: drafted（**17 块迁移源已 consolidate**:执行签名/返回/事件/HTTP 端点总索引(13)/Golden/Iterate-Resume/Compile API 面全成段;**U10 可锁候选**——余 resume/golden/iterate target schema + 错误 V2 = impl 归 kiro,studio HTTP 路由引用不 own、并发 session 协同）
aligns_with: ../00-architecture-overview.md（§4 API契约层 C）
---

# 03-api-contract — API 契约 C · engine↔studio 操作边界

> **Tier**: API 契约层 C | **Owns**: 引擎被 studio 进程内调用(run/predict/compile)+ 事件流 + HTTP 端点 的完整接口 SSOT | **现状**: 完整接口面已成段(17 块迁移源 consolidate);U10 可锁候选 | **Related**: `07-runtime`(实现 run/predict 入口)· `06-seam/02-observability`(供事件流)· `data-contracts`(RunResult/ErrorPayload 形状)

## 1. 定义
引擎是被 studio 后端**进程内调用**(`run_skill`/`predict_skill`/`compile_skill`)的库;事件经**回调 + trace.jsonl + WS** 流到前端。本域是这些接口的**显式契约 SSOT**——所有 consumer 只链接、不复制。**它是"怎么调引擎",和契约层 A("skill 是什么")不同类。**

## 2. 三条接口面
| 面 | 形态 | 入口 |
|---|---|---|
| 执行 | 进程内 Python | `run_skill`/`predict_skill`/`compile_skill`(runner.py/compiler.py) |
| 事件 | typed 事件流 → 回调+落盘+WS | `event_subscriber` 回调 + `trace.jsonl`(SSOT)+ WS `/ws/runs/{run_id}` |
| HTTP | REST+WS | `apps/studio/backend/app/routers/*`(studio 暴露面) |

### 2.1 执行签名 + 返回契约(SSOT = runner.py / result.py)
**run_skill**(`runner.py:376`,真跑):
`run_skill(skill_path, *, workspace_dir, thread_id=None, unattended=False, event_subscriber=None, artifact_saver=None, initial_context=None, cleanup_checkpoints_on_finish=True, skill_resolver(必填,缺则 [F-v3-resolver-missing]), model_resolver=None, **inputs) -> RunResult`
**predict_skill**(`runner.py:163`,干跑/mock,`unattended` 默认 True):同签名 + `copilot_predict=None`;`**inputs` 可含 `mock_llm`(类型决定 mock 策略:None→heuristic / Path→golden / list→backtest / dict→override)+ `current_hashes`(golden 失效告警),均经 `**inputs` pop(`runner.py:196/197`)。
- **失败不抛**:`GraphAgentError` 捕获 → `success=False` 的 `RunResult`(带 `error: ErrorPayload`,`runner.py:416-435`)。
**RunResult**(`result.py:68`,形状归 `data-contracts`,此处列字段供 consumer 对账):`success/run_id/skill_id/context(终态黑板)/metrics(WorkflowMetrics)/trace_path/error(ErrorPayload|None)/started_at/finished_at/wall_time_sec/source("run"|"predict")/phases(list[PhaseRecord],predict 必有)/path_diff(仅 predict)`;`PhaseRecord{phase_name,type,inputs,outputs,mocked_source}`、`PathDiff{expected_path,actual_path,missing,extra,order_mismatch}`。
> RunResult/ErrorPayload 字段形状归 `data-contracts`(本域引用不复制)。
> **错误契约 V2(目标)**:`RunResult` 加 `diagnostics: list[ErrorPayload]`(FATAL+WARN 全集),consumer 一处拿全;`ErrorPayload` 加 `details`/`remediation`。形状归 `data-contracts` DC5、规则归 `compile-rules` §3.1;本域负责 **API 暴露**(diagnostics 字段透传 + 公开错误码表端点,见 §3)。
> `skill_resolver` 的 **DI 协议形状**(输入绝对 path+边界 / 输出子图 root / 失败 raise)归 [`02-resolver`](../02-mechanism/02-resolver/mvp1-alignment.md) §3;本域只定它是 run/compile 的必填参数。

### 2.2 事件协议
33 类 typed `CallbackEvent`(判别字段 `event_type`),字段 SSOT = `callbacks/events.py`(归 `02-observability`);live 走 WS、history 走 HTTP、`trace.jsonl` 落盘 SSOT。
> **错误契约 V2(目标)**:新增 `DiagnosticEmittedEvent`(实时诊断,带完整 `ErrorPayload` + `diagnostic_id`),与 `RunResult.diagnostics`(最终快照,`diagnostic_id` 关联)**双轨、不双写语义**(细化见 `compile-rules` §3.1.1)。

### 2.3 关键异步接缝
引擎 `run_skill` 返回**同步** RunResult;studio `POST .../runs` 返回 RunMetadata(202,**异步** spawn)——接缝在 studio `run_manager`。

## 3. studio HTTP 端点总索引(SSOT = `apps/studio/backend/app/routers`,已核 router:line)
| 端点 | router:line | 请求 → 响应 | 面 |
|---|---|---|---|
| WS `/ws/runs/{run_id}` | `websockets.py:27` | → 事件流(live) | §2.2 |
| `POST /skills/{id}/runs` | `runs.py:27` | `RunRequest` → `RunMetadata`(202 异步) | §2 |
| `POST /skills/{id}/runs/predict` | `runs.py:32` | `PredictRunRequest` → `dict` | §2 |
| `GET /skills/{id}/runs` | `runs.py:43` | → `RunListResponse` | §2 |
| `GET /skills/{id}/runs/{run_id}` | `runs.py:53` | → `RunDetail`(含 `events`=回放 trace.jsonl) | §2.2 |
| `DELETE /skills/{id}/runs/{run_id}` | `runs.py:58` | → 204 | §2 |
| `POST /skills/{id}/runs/batch-run` | `runs.py:48` | `BatchRunRequest` → `BatchRunResponse`(202) | §2 |
| `GET /batch/{batch_id}` | `runs.py:73` | → `BatchRunStatus` | §3.2 |
| `POST /skills/{id}/runs/{run_id}/resume` | `runs.py:69` | `ResumeReq` → **501 桩**(声明 RunMetadata,待 C2) | §3.2 |
| `POST /skills/{id}/compile` | `skills.py:109` | → `CompileSuccess`/`CompileError` | §3.3 |
| `POST /lint` | `lint.py:13` | → `LintResult` | §3.3 |
| `POST /skills/{id}/graph/serialize` | `skills.py:122` | → `SerializeGraphRes` | §3.3 |
| `POST /skills/{id}/validate_input` | `skills.py:454` | → `ValidateInputResponse` | §3.3 |
| `GET /errors`(目标,G4) | — | → 版本化信封 `{registry_version, schema_version, items:[{code,level,stage_id,domain,remediation,doc_ref,doc_url,status}], next_cursor?, etag}` + 过滤(细化 `compile-rules` §3.1.1) | §3.3 |
> consumer(旧 06/09/10/11 关注点)的"接口"段链接本文、不复制(SSOT);⚠️ studio 前端 hook 挂载(useRunStream/TracePanel 是否孤儿)归 studio 核实。

### 3.1 Golden API 面(schema SSOT = `06-golden-eval`)
- **golden 文件**(目标):`phases/<phase_id>/golden.json` = `{expected_output(匹配该节点 io.outputs), source:"manual"|"copilot"(永不 trace,409 天然成立), updated_at}`,随技能进 git、路径即身份。
- **逐节点 diff**(部分目标):引擎 SDK 纯函数 `evaluate_golden_baseline` 逐节点版(现 `golden_diff.py` 作用在整 final_state,逐节点待建);studio 只渲染。
- **失效**(目标):eval 期 golden 缺 io.outputs 必填字段 → `[F-v3-golden-stale-fields]`(归 `compile-rules` §6 + V2 G6 注册)。
- **409 守卫**(live):`assert_trace_can_be_promoted_to_golden`(`diagnostic_export.py:25`),predict trace→golden 拒。

### 3.2 Iterate / Resume API 面(SSOT = `02-iterate` / `03-checkpoint`)
- **iterate 配置**(目标):节点/图/子图声明 `iterate:{mode,over,item_var,range,concurrency,accumulate}`(语法 `skill-syntax §2.9`、执行 `02-iterate`);现状节点级 batch live,loop/图级/range 目标。
- **resume**(目标):`POST .../runs/{run_id}/resume` + `ResumeReq{context_overrides}`;**现 501 桩**(`runs.py:69`,`ResumeReq` 零消费)。寻址契约(C2 闭环):`resume_run(run_id, from=<node_id>|<node_id>:<iter>, context_overrides?)` → LangGraph `get_state_history` 选 checkpoint(loop 轮用 `checkpoint_ns`)→ `update_state` 套 overrides / 注 ToolMessage(HitL)→ 带该 checkpoint 重 invoke(归 `03-checkpoint`)。
- **失效追踪**(目标):上游/拓扑/输出 schema 变 → 下游 checkpoint 失效 → 前端 [Resume] 置灰(归 `05-invalidation`)。

### 3.3 Compile API 面(SSOT = `compiler.py` / `compile-rules`)
- `compile_skill(root, *, chat_model=None, cache=True, skill_resolver(必填)) -> CompiledSkill`(`compiler.py:41`);`CompileResult{issues; fatals; warnings; passed}`(`compiler.py:23`,诊断容器)。
- `ErrorPayload`(`exceptions.py:21`,跨 compile+runtime 共用,形状归 `data-contracts`):四轴 `level`(severity)/`stage`/`phase_id`/`field_path`/`source_path` + `code`/`message`/`doc_link`——前端 canvas 节点/属性/编辑器行 3 处标记靠这四轴。**V2 增补**(`compile-rules §3.1.1`):`source_span`/`details`/`remediation`/`stage_id` + Task 3(逐码审 emit 四轴填全)。
- 端点:compile / lint / serialize / validate_input(见 §3 表)。

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

## 8. gaps / 待设计(接口面已成段:17 块迁移源 consolidate;以下均 impl-target 归 kiro / studio 协同)
1. resume `501 桩` → C2 寻址契约落地(与 `02-iterate`/`03-checkpoint` 协同)。
2. V4 trace 增补事件 schema(随 `02-observability` 实现)。
3. golden/iterate target schema 待 FROZEN 解冻回填。
4. **错误契约 V2 API 面(G4/G5)**:`RunResult.diagnostics` 透传 + `GET /errors` 公开码表端点(规则/形状见 `compile-rules` §3.1 / `data-contracts` DC5)——impl 归 kiro。

## 交叉引用(链接, 不复制)
00-architecture-overview §4 · `07-runtime` · `06-seam/02-observability` · `data-contracts`
