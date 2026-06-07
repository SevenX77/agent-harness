---
doc: api-engine-studio-contract
status: drafted（§1-§5 五节接口面已写;§3/§4 target schema 待 FROZEN 解冻回填,§4 resume 依赖 C2,§5 错误码四轴 = Task 3）
last_verified: 2026-06-03
owns: engine↔studio 进程内 + HTTP/WS 接口契约(第2趴;第1趴 = engine↔gateway,见 temp/2026-06-02-engine-gateway-interface-needs.md)
ground_truth:
  - packages/graph-agent（引擎侧 = SSOT，签名以代码为准）
  - apps/studio/backend/app/routers（studio 暴露面）
related:
  - 06-trace-observability（事件覆盖）
  - 09-golden-eval / 10-iteration-and-resume / 11-io-and-edge-ops（各自接口）
---
<!-- 核对进度:已迁 2 块 / 未迁 17 块 / 2026-06-04 -->

~~# Engine ↔ Studio API 接口契约(第2趴)~~ → ✅[已迁入](../03-api-contract/mvp1-alignment.md#1-定义)

> 第1趴(engine↔gateway)结论:引擎对 gateway 只有一个调用面 `ModelResolverProtocol.resolve()`。
> 第2趴(本文,engine↔studio):引擎是被 studio 后端**进程内调用**(`run_skill`/`predict_skill`/`compile_skill`)的库,事件经**回调 + trace.jsonl + WS**流到前端。本文把这些接口写成显式契约。
> **铁律**:引擎侧签名以 `packages/graph-agent` 实际代码为准;file:line 引用前已复核。studio 侧暴露面以 `apps/studio/backend/app/routers` 为准。

---

~~## 0. 总览:三条接口面~~ → ✅[已迁入](../03-api-contract/mvp1-alignment.md#2-三条接口面)

| 面 | 形态 | 谁调谁 | 入口 |
|---|---|---|---|
| **执行** | 进程内 Python | studio run_manager → 引擎 | `run_skill` / `predict_skill` / `compile_skill`(引擎公开 API) |
| **事件(trace)** | typed 事件流 → 回调 + 落盘 + WS | 引擎 emit → studio 转发前端 | `event_subscriber` 回调 + `trace.jsonl` + WS `/ws/runs/{run_id}` |
| **HTTP** | REST + WS | 前端 ↔ studio 后端 | `apps/studio/backend/app/routers/*` |

---

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
## 1. Trace API(= handoff 任务4 的答案:trace 怎么和前端交互、什么协议)

**一句话**:**协议 = typed 事件流**;**live 走 WS,history 走 HTTP,落盘 trace.jsonl 是 SSOT**。

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
### 1.1 链路(已逐段核代码)

```
引擎 phase 执行
  └─ emit typed CallbackEvent (34 类, 判别联合)
       ├─(A 进程内)→ event_subscriber: Callable[[CallbackEvent], None]   ← run_skill/predict_skill 入参
       │                runner.py:382(run) / :169(predict);装配经 _prepare_v030_event_sink(runner.py:548)
       │                bridge: _EventSinkCallbackAdapter(.emit→.on_event)  graph_assembler.py:619
       │                → studio run_manager 把 event_subscriber 接成 emit_to_queue → WS
       └─(B 落盘)→ TracingCallback.on_event → trace.jsonl                  ← tracing.py:106-111
                     `<workspace>/runs/<run_id>/trace.jsonl`,一行一事件(event.model_dump_json())
                     (另有 legacy `<run_id>.jsonl`,tracing.py:82;trace.jsonl 才是 Studio-facing SSOT,:106)
```

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
### 1.2 事件契约(judge 判别联合)

- **基类 `_EventBase`**(`callbacks/events.py:42`):`schema_version: Literal["1.0"]`、`timestamp`(UTC ISO)、`sub_run_id: str | None`(parallel-map / 子运行归属)。
- **判别字段**:每类带 `event_type: Literal[...]`(如 `"phase_start"`/`"llm_call"`);大多数带 `phase_name`。前端按 `event_type` 分流渲染。
- **字段 SSOT = `callbacks/events.py`**(本文不复制每类全字段,避免漂移;只列清单 + 判别器 + V4 增补)。

**现有 34 类**(`event_type`):
`phase_start` · `predict_chain_start` · `phase_end`(带 context 黑板快照)· `llm_call` · `tool_call` · `validation_fail` · `retry` · `finish_task` · `nudge` · `working_memory_update` · `dead_end_pruned` · `compaction` · `ambiguity_report` · `ambiguity_logged` · `builtin_subagent_enter|exit|fallback` · `prompt_captured` · `llm_fallback` · `run_started` · `run_ended`(status 含 `interrupted`)· `validation_pass` · `retry_exhausted` · `model_resolved` · `artifact_saved` · `parallel_map_group_started|ended` · `agent_loop_iteration` · `interrupted` · `resumed` · `heartbeat` · `thread_cleaned_up` · `internal_error`。

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
### 1.3 studio 暴露(已核 router)

| 用途 | 端点 | 证据 |
|---|---|---|
| **live 流** | WS `/ws/runs/{run_id}` | `apps/studio/backend/app/routers/websockets.py:27` |
| **history** | HTTP `GET /runs/{id}` → `RunDetail.events`(回放 trace.jsonl) | runs router(待补精确行) |
| 列表 | HTTP `GET /skills/{id}/runs` | 同上 |

前端消费:`useRunStream`(WS live)、`useRunHistory`(HTTP history)、`TracePanel`/`PromptInspector`。
⚠️ **studio 侧待确认**:handoff 称 `useRunStream`/`TracePanel` 为"孤儿未挂载",需在 studio 前端核实挂载状态(本契约只定义引擎产出 + 后端暴露;前端挂载归 studio)。

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
### 1.4 V4 trace 增补(本契约需扩展的事件 schema)

trace 现有事件不够覆盖 mvp1 新关注点,以下需**加进事件契约**(详设计见对应关注点):
1. **微观拓扑事件**(06 #4):agent 节点内子事件需带 `parent_node_id`(=该 agent phase_id)+ `node_type`(嵌套渲染)。TracingMiddleware 的 `before_model`/`after_model`/`wrap_tool_call` 天然产出。
2. **边操作事件 ×3**(11 §4,**目前 events.py 未定义**):`blackboard_reduce` / `input_dispatch`(并联节点各一条)/ `input_file_injected`;+ 现有 `artifact_saved`/`compaction` 归入"边操作"族,前端按 edge(`from_phase`/`to_phase`)聚合。
3. **Prompt 三视图**(06 #7):核实 `prompt_captured` 是否同时带 模板 / 喂入变量 / 渲染后;若只有渲染后需补。
4. **reducer 级前后态 diff**(06 #6):权威"哪个 reducer 改了哪个 key",引擎 emit vs 前端用 `phase_end[A].context` vs `phase_start[B].context` 近似——待定。
5. **嵌套子图链路**(06 #8):微观/边事件在子图内是否需带父链路(C4 一致性已登记:边事件嵌套维度对齐微观事件)。

---

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
## 2. 执行 API(predict / run / batch)

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
### 2.1 引擎入口(进程内,SSOT = runner.py)

```python
# run_skill(runner.py:376)— 真跑
def run_skill(
    skill_path: str | Path, *,
    workspace_dir: Path,
    thread_id: str | None = None,
    unattended: bool = False,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
    artifact_saver: Any | None = None,
    initial_context: dict[str, Any] | None = None,
    cleanup_checkpoints_on_finish: bool = True,
    skill_resolver: SkillResolverProtocol,          # 必填关键字(缺则抛 [F-v3-resolver-missing])
    model_resolver: Any | None = None,              # gateway resolver(第1趴);None 时 predict 造 mock registry
    **inputs: Any,                                  # skill 输入 + 可含 mock_llm
) -> RunResult

# predict_skill(runner.py:163)— 干跑/mock(unattended 默认 True)
def predict_skill(
    skill_path, *, workspace_dir, thread_id=None, unattended=True,
    event_subscriber=None, skill_resolver, model_resolver=None,
    copilot_predict: Callable[..., Any] | None = None,
    **inputs,                                       # 可含 mock_llm / current_hashes
) -> RunResult
```
- `mock_llm` 经 `**inputs` 传(`run_skill:391` / `predict_skill:196` pop 出);类型决定 mock 策略(None→heuristic / Path→golden / list→backtest / dict→override,见 09)。
- 失败不抛异常:`GraphAgentError` 被捕获 → 返回 `success=False` 的 `WorkflowResult`(带 `error: ErrorPayload`),见 `runner.py:416-435`。

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
### 2.2 返回契约(result.py,SSOT)

```python
RunResult(BaseModel):                               # result.py:68
    success: bool; run_id: str; skill_id: str
    context: dict[str, Any]                          # 终态黑板
    metrics: WorkflowMetrics                         # input/output/total_tokens + wall_time_sec
    trace_path: Path | None                          # → trace.jsonl
    error: ErrorPayload | None
    started_at/finished_at: datetime | None; wall_time_sec: float
    source: Literal["run", "predict"] = "run"
    phases: list[PhaseRecord] | None                 # 逐节点记录(predict 必有)
    path_diff: PathDiff | None                       # 仅 predict:期望路径 vs 实际路径

PhaseRecord(result.py:58): phase_name; type: Literal["logic","llm"]; inputs; outputs;
    mocked_source: Literal["golden_case","copilot","heuristic_stub","manual"] | None
PathDiff(result.py:48): expected_path; actual_path; missing; extra; order_mismatch
WorkflowResult(RunResult)(result.py:92): 子类
```

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
### 2.3 studio HTTP(prefix `/skills/{skill_id}/runs`,SSOT = routers/runs.py)

| 端点 | 处理 | 请求 → 响应 | 证据 |
|---|---|---|---|
| `POST ` | create_run | `RunRequest` → `RunMetadata`(**202 异步**) | runs.py:27 |
| `POST /predict` | predict_run | `PredictRunRequest` → `dict[str,object]` | runs.py:32 |
| `GET ` | list_runs | → `RunListResponse` | runs.py:43 |
| `GET /{run_id}` | get_run | → `RunDetail`(含 `events` = 回放 trace.jsonl) | runs.py:53 |
| `DELETE /{run_id}` | delete_run | → 204 | runs.py:58 |
| `POST /batch-run` | create_batch_run | `BatchRunRequest` → `BatchRunResponse`(202) | runs.py:48 |
| `GET /batch/{batch_id}` | get_batch_status | → `BatchRunStatus`(batch_router) | runs.py:73 |

**关键契约边界(异步)**:引擎 `run_skill` 返回 typed `RunResult`(同步);但 studio `POST .../runs` 返回 `RunMetadata`(202)——studio **异步 spawn** `run_skill`(`run_manager`),立刻回 metadata,结果/事件经 **WS(live)+ trace.jsonl + `GET /runs/{id}`→RunDetail(history)** 取(= §1 trace 链)。即:**engine 同步 RunResult ↔ studio 异步 RunMetadata 的接缝在 run_manager**。

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
## 3. Golden API

> schema SSOT = `09-golden-eval/mvp1-alignment.md`(决策 A,2026-06-03 锁);本节只列接口面 + 建设状态。

- **golden 文件契约(target,G1)**:`phases/<phase_id>/golden.json` = `{ expected_output(匹配该节点 io.outputs schema), source: "manual"|"copilot"(永不 trace,409 天然成立), updated_at }`。随技能进 git,路径即身份。
- **逐节点 diff API(部分 target,G3)**:目标 = 引擎 SDK 纯函数 `evaluate_golden_baseline` 逐节点版,复用 `_diff_value`/`_score`(现 `apps/studio/backend/app/services/golden_diff.py:130-216`,**现作用在整 final_state**,逐节点版待建)。Studio 只渲染。
- **失效(target,G2)**:编译期 golden 缺 io.outputs 必填字段 → `[F-v3-golden-stale-fields]`(进 §5 ErrorPayload + Task 3)。
- **409 守卫(已实现)**:`assert_trace_can_be_promoted_to_golden`(`diagnostic_export.py:25-55`),predict trace → 409 `PREDICT_TRACE_CANNOT_BE_GOLDEN`。
- **拦截搬引擎(target,G5,接 D2)**:引擎侧 predict mock chat model(实现 `BaseChatModel`,`_generate` 调 `resolve_generation`)当 `create_agent(model=...)`,去 gateway 依赖。
- 建设状态:逐节点回放/diff 算法/409 = 已实现(复用);逐节点常驻 golden.json / 编译期失效 / 逐节点 diff 喂入 / 拦截搬引擎 = target。

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
## 4. Iterate / Resume API

> schema SSOT = `10-iteration-and-resume/mvp1-alignment.md`(fork F1-F5 + C1,2026-06-03 锁);本节列接口面 + 建设状态。

- **iterate 配置(target,10 §1)**:节点/图/子图声明 `iterate: {mode: batch|loop, over, item_var, range:[s,e], concurrency(仅batch), accumulate:{var,init,from,merge}(仅loop)}`。向后兼容现 `batch_spec`(= `mode:batch`)。loop 节点 `io.inputs` 必含 `item_var`+`accumulate.var`(编译校验 → `[F-v3-iterate-*]`)。
- **现状(baseline)**:节点级 batch 已实现(`graph_assembler.py:240` `_build_batch_wrapped_node`);loop / 图级迭代 / range = target。
- **resume API**:`POST /skills/{skill_id}/runs/{run_id}/resume` + `ResumeReq`(含 `context_overrides`)。
  - **已核实:`resume_run`(`runs.py:69`)仍是 501 桩**——body `raise_not_implemented`;`response_model=RunMetadata` 只是声明型、`responses={501}` 才是实际(handoff/10-baseline 没错)。`ResumeReq.context_overrides` 已定义但零消费。
  - **寻址契约(C2 已闭环,见 10 §4)**:`resume_run(run_id, from=<node_id> | <node_id>:<iter_index>, context_overrides?)` → LangGraph `get_state_history(thread_id)` 列档 → 选 `checkpoint_id`(+ loop 轮次用 `checkpoint_ns="<phase_id>"`)→ `update_state` 套 `context_overrides` / 注入 `ToolMessage`(HitL)→ 带该 checkpoint 重 `invoke`。唯一 base = LangGraph super-step thread checkpoint。
- **batch 状态(已实现)**:`GET /batch/{batch_id}` → `BatchRunStatus`(runs.py:73)。
- **失效追踪(target)**:上游/拓扑/输出 schema 变 → 下游 checkpoint 失效 → 前端 [Resume] 置灰(归 C3 统一失效模型)。

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
## 5. Compile API

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
### 5.1 引擎入口(compiler.py,SSOT)

```python
def compile_skill(root: str|Path, *, chat_model=None, cache=True,
                  skill_resolver: SkillResolverProtocol) -> CompiledSkill   # compiler.py:41

@dataclass
class CompileResult:                 # compiler.py:23
    issues: list[CompileIssue]
    @property fatals   -> [issue for severity=="FATAL"]
    @property warnings -> [issue for severity=="WARNING"]
    @property passed   -> not self.fatals
```

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
### 5.2 错误契约 `ErrorPayload`(exceptions.py:21,跨 compile+runtime 共用 — Task 3 核心)

```python
class ErrorPayload(BaseModel):       # 也是 RunResult.error 的类型
    code: str                        # [F-v3-*];构造时校验须在 ERROR_REGISTRY 且元数据完整
    level: str | None                # = severity 轴
    stage: tuple[str, ...] | None
    message: str
    doc_link: str | None
    skill_id: str | None
    phase_id: str | None             # = phase 轴
    field_path: str | None           # = field 轴
    source_path: str | None          # = file 轴(⚠️ 是否含行号 = Task 3 待核)
```
**Task 3 映射**:前端要在 canvas节点/属性/编辑器行 3 处放标记 → 需 `phase_id`(定位节点)+`field_path`(定位属性)+`source_path`(定位编辑器行)+`level`(标记色)。四个字段**都已存在**(均 `|None`)。**Task 3 = 审计每个 `[F-v3-*]` 码的实际 emit 是否都填全这四轴**(尤其 source_path 是否到行号);缺哪轴的码列清单补齐。

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
### 5.3 studio HTTP

| 端点 | 处理 | 响应 | 证据 |
|---|---|---|---|
| `POST /skills/{skill_id}/compile` | compile | `CompileSuccess`(models/skills.py:101);失败 `CompileError`(:91) | skills.py:109 |
| `POST /lint` | lint | `LintResult`(models/lint.py:12) | lint.py:13 |
| `POST /skills/{skill_id}/graph/serialize` | 图序列化 | `SerializeGraphRes` | skills.py:122 |
| `POST /skills/{skill_id}/validate_input` | 输入校验 | `ValidateInputResponse` | skills.py:454 |

> 新增 golden/iterate 错误码(`[F-v3-golden-stale-fields]` / `[F-v3-iterate-*]`,见 09/10 FROZEN 清单)也须进 `ERROR_REGISTRY` 且带全四轴 —— 一并入 Task 3。

---

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
## 6. studio 后端端点总索引(已核 router:line)

| 端点 | router:line | 请求 → 响应 | 节 |
|---|---|---|---|
| WS `/ws/runs/{run_id}` | websockets.py:27 | → 事件流 | §1 |
| `POST /skills/{id}/runs` | runs.py:27 | RunRequest → RunMetadata(202) | §2 |
| `POST /skills/{id}/runs/predict` | runs.py:32 | PredictRunRequest → dict | §2 |
| `GET /skills/{id}/runs` | runs.py:43 | → RunListResponse | §2 |
| `GET /skills/{id}/runs/{run_id}` | runs.py:53 | → RunDetail(含 events) | §1/§2 |
| `DELETE /skills/{id}/runs/{run_id}` | runs.py:58 | → 204 | §2 |
| `POST /skills/{id}/runs/batch-run` | runs.py:48 | BatchRunRequest → BatchRunResponse(202) | §2 |
| `GET /batch/{batch_id}` | runs.py:73 | → BatchRunStatus | §2/§4 |
| `POST /skills/{id}/runs/{run_id}/resume` | runs.py:69 | ResumeReq → **501 桩**(声明 RunMetadata) | §4 |
| `POST /skills/{id}/compile` | skills.py:109 | → CompileSuccess / CompileError | §5 |
| `POST /lint` | lint.py:13 | → LintResult | §5 |
| `POST /skills/{id}/graph/serialize` | skills.py:122 | → SerializeGraphRes | §5 |
| `POST /skills/{id}/validate_input` | skills.py:454 | → ValidateInputResponse | §5 |

---

<!-- ⚠️ 未迁入（正式 03-api-contract 明确为摘要并写“完整表见迁移源”，未承载完整签名、字段、端点、router:line、trace/golden/iterate/compile API 细节） → 应归入:03-api-contract/mvp1-alignment -->
## 7. 待办
1. **跨关注点链接**:06/09/10/11 各 mvp1-alignment 的"接口"部分改为**链接本文**,不复制(SSOT)。
2. **studio 前端**:核实 hook 挂载状态(useRunStream/TracePanel 是否孤儿)——归 studio,本文登记。
3. **依赖收口**:§1.4 trace 增补事件(微观 parent_node_id / 3 个边事件 / Prompt 三视图)随 06/11 实现;§4 resume 寻址依赖 **C2** 闭环;§5 错误码四轴完整性 = **Task 3**;新增码进 ERROR_REGISTRY = **Task 1**。
4. **目标 schema 落地**:§3 golden.json / §4 iterate 字段属 FROZEN 解冻(= **Task 1**),解冻后回填确切 schema。
