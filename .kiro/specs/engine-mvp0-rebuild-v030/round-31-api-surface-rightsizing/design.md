# Round 31 Ground-Up API Catalog Redesign (a1 draft v5 — based on 1f audit)

## §0 一句话总览

graph-agent SDK 是文档驱动的黑盒图执行虚拟机。它只暴露编译、运行、预演、基线评估、图序列化和图回写这 6 个引擎入口；模型环境、即席聊天、provider 解析和 Copilot 预测器归 Gateway；Studio HTTP 层负责自己的产品功能编排。

本轮 catalog 的核心变化是把 SDK 从“运行时工具箱”收敛成“给 workspace、给 resolver、给输入，然后得到同形结果和事件流”的内核 API。Tracing 默认自动落盘，实时进度通过订阅器派发；predict 与 run 输出同形；workspace 子目录规范归 Engine 文档所有。

## §0.1 SDK 边界外 (Studio HTTP-only, 不纳入本 catalog)

以下 Studio user-visible 功能继续由 Studio backend HTTP/WebSocket 层自管，不纳入 graph-agent SDK public API：

- Skill 文件 CRUD：list / create / update / delete / fork。
- Git 协作：sync / save_to_team / submit_for_review / publish / history / revert。
- App settings / health / shutdown。
- Terminal PTY session 与 terminal WebSocket stream。
- Skill templates。
- Test inputs CRUD。
- Golden baseline CRUD 与 run artifact 管理。
- LLM provider 连通性测试、notable models、manual model probing。
- Audit / debug / compare router 等 HTTP-only 端点。

Studio backend 在接入 v4 SDK 时保留这些产品功能，只把 engine-facing 的编译、运行、预演、事件、workspace 文件写入和错误捕获迁移到本 catalog 的新边界。

## §1 Downstream Persona (谁会用 graph-agent SDK?)

设计时不仅考虑现在的 Studio 编辑器，还推演了未来生态中其他典型消费者：

1. **GUI 可视化编辑器 (如目前的 Studio)**
   - 描述：面向用户的低代码业务画图工作台。
   - 想干：把 Markdown 技能解析成图在画布上渲染；调用引擎编译校验找语法错；用户点“预演”时模拟跑一遍看路线；管理和编辑基线测试数据；配置 LLM 秘钥和角色。
2. **API 网关 / 线上 Runner 服务**
   - 描述：在多租户、高并发环境下实际对外提供服务接口的后端引擎。
   - 想干：根据用户的 REST 请求触发真正的 skill 执行；将大模型打字机输出、节点切换状态通过标准 JSON 事件流推送到 WebSocket；处理提供商超时和 fallback。
3. **CLI 开发者自动化工具 (DevOps / CI 工具)**
   - 描述：给开发者在本地命令行或 CI/CD 流水线上跑的脚本。
   - 想干：提交代码前批量 lint；在流水线中批量跑 golden baseline；导出技能文件。
4. **外部监控与可观测性平台**
   - 描述：日志大屏或审计系统。
   - 想干：订阅执行过程中的 tracing，沉淀 token 消费与节点耗时数据；统一抓取各类报错，判定责任归属。

## §2 Verbs 完整清单

### SDK verbs (保留 6 个)

1. `compile_skill(workspace: SkillWorkspace) -> CompileResult`
   - 功能：编译并静态校验一个 skill，输出可执行黑盒句柄和结构化诊断。
   - 工程含义：现有 `compile_skill` 已存在，但返回与错误形态需要对齐新 `CompileResult`。

2. `run_skill(compiled_skill: CompiledSkill, inputs: dict, model_resolver: ModelResolverProtocol, workspace_dir: Path, event_subscriber: Callable[[CallbackEvent], None] | None = None) -> RunResult`
   - 功能：真实执行已编译 skill。
   - 关键约束：不再接收 `llm_env`。Gateway 管模型环境，SDK 只接收 resolver protocol。
   - 现状证据：当前 `run_skill` 仍接收 path、`trace_dir`、`callbacks`、`model_resolver`，见 `packages/graph-agent/src/graph_agent/core/runner.py:59-73`；V0.3 主线在 `_run_v030_skill_dict()` 中通过 `trace_dir` 和 `callbacks` 透传，见 `packages/graph-agent/src/graph_agent/core/runner.py:221-275`。

3. `predict_skill(compiled_skill: CompiledSkill, inputs: dict, model_resolver: ModelResolverProtocol, workspace_dir: Path, event_subscriber: Callable[[CallbackEvent], None] | None = None) -> RunResult`
   - 功能：执行 predict 工序，逻辑节点真实跑，LLM 节点由 Gateway resolver 路由到 Copilot predictor。
   - 返回：与真实 run 同形的 `RunResult`，顶层 `source="predict"`。
   - 关键约束：SDK 不直接调用 Copilot，不保留 SDK 内部 `PredictGatewayChatModel`。

4. `evaluate_golden_baseline(compiled_skill: CompiledSkill, dataset: BaselineDataset, model_resolver: ModelResolverProtocol, workspace_dir: Path) -> BaselineReport`
   - 功能：批量执行 baseline 对比，产出通过率和差异报告。
   - 文件约束：Engine 按 §7 写入 workspace，不由 Studio 拼内部路径。

5. `serialize_skill_graph(compiled_skill: CompiledSkill) -> SerializedGraphData`
   - 功能：把编译产物转换成 UI 可画的节点、边、IO、元数据。
   - 关键约束：不暴露 AST internals。

6. `serialize_graph_back_to_markdown(graph_edits: SerializedGraphData, original_markdown: str) -> str`
   - 功能：把画布编辑反向合并回 Markdown。
   - 关键约束：这是 UI authoring API，不是执行 API；必须按 round-trip 语义保留未触碰文本。

### 移出 SDK 的 verbs (Gateway-owned)

- `configure_llm_environment(...)`
  - 去向：Gateway 包。
  - 原因：Q3 已拍，模型环境加载、验证、provider fallback、熔断、热加载不属于 SDK。

- `chat_with_role(...)`
  - 去向：Gateway 包。
  - 原因：即席对话直接消费 role/provider/model 环境，和 predict LLM 模拟同属 Gateway chat/predict facade。

## §2.5 predict↔golden↔run↔copilot 协作链契约

本节是叙事契约，不新增 API。它说明 `predict_skill`、`run_skill`、`evaluate_golden_baseline`、Gateway Copilot 和 Studio HTTP golden 编排如何配套工作。

1. **predict 阶段**
   - Owner：SDK 负责编排 `predict_skill`；Gateway 负责 Copilot predictor；Studio 负责触发按钮和展示。
   - 用户配完 skill 并 compile 通过后点击 Predict。SDK `predict_skill` 跑模拟图：逻辑节点真实执行，LLM 节点由 `model_resolver` 路由到 Gateway 的 Copilot predictor，也就是 Gateway chat/predict facade，用来预测该 prompt 大概会得到什么输出。
   - 输出：`RunResult(source="predict")`。
   - 文件：SDK 写 `<workspace_dir>/runs/<run_id>/trace.jsonl` 和同 run 结构的结果 artifacts。

2. **Copilot 辅助调 prompt**
   - Owner：Gateway 生成建议；Studio 负责把建议呈现给用户并驱动编辑。
   - 用户读取 predict 结果后，和 Gateway Copilot 协作迭代 prompt、phase 结构、few-shot、protocol。SDK 不参与 chat，不持有 provider 环境。

3. **Golden 转化**
   - Owner：Studio HTTP 层。
   - 用户满意后，Studio golden CRUD endpoint 把本次 predict 的同形 `RunResult` 一键转化为 Golden Baseline。该转化是 Studio 产品编排，不新增 SDK verb。

4. **真 run 阶段**
   - Owner：SDK。
   - 用户点击 Run，SDK `run_skill` 通过同一个 `model_resolver` contract 跑真实大模型。
   - 输出：`RunResult(source="run")`，同样落入 `<workspace_dir>/runs/<run_id>/`。

5. **Golden 对比 + Copilot 建议迭代**
   - Owner：SDK 负责 `evaluate_golden_baseline`；Gateway 负责 Copilot 建议生成；Studio HTTP 层负责编排闭环。
   - Studio 调 SDK `evaluate_golden_baseline` 对比真 run 结果与 Golden Baseline。Gateway Copilot 根据 diff 给出针对性 prompt、few-shot、protocol 调整建议。用户依此迭代，直到真实 run 接近 golden。

## §3 Nouns 完整清单

### SDK public nouns

- `SkillWorkspace`
  - 指向 skill root 与 workspace root 的上下文容器。
- `CompileResult`
  - 编译成功时包含 `compiled_skill` 与 warnings；失败时包含 `GraphCompileError` 诊断数组。
- `CompiledSkill`
  - 只读黑盒执行句柄。调用方只允许传给 SDK verbs，不拆内部字段。
- `SkillManifest`
  - skill 元数据访问器，提供 name / description / phases / IO 摘要。
- `RunResult`
  - run 与 predict 的同形结果。
  - 必含字段：`source: "run" | "predict"`、`success`、`run_id`、`skill_id`、`context`、`metrics`、`trace_path`、`error`、`started_at`、`finished_at`、`wall_time_sec`、`phases: list[PhaseRecord] | None`、`path_diff: PathDiff | None`。
  - 现状证据：当前 `WorkflowResult` 已有 `success/run_id/skill_id/context/metrics/trace_path/error/started_at/finished_at/wall_time_sec`，见 `packages/graph-agent/src/graph_agent/core/result.py:46-60`。
- `PhaseRecord`
  - 从 private predict model 晋升 public；记录 phase_name、phase type、inputs、outputs、mocked_source。
  - 现状证据：当前定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:24-31`。
- `PathDiff`
  - 从 private predict model 晋升 public；记录 expected_path、actual_path、missing、extra、order_mismatch。
  - 现状证据：当前定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:37-44`。
- `BaselineReport`
  - baseline 批量执行统计、失败样本、差异摘要。
- `SerializedGraphData`
  - UI 图数据，包含节点、边、布局、schema 摘要。
- `CallbackEvent`
  - 跨语言事件 payload；作为 `event_subscriber` 输入，而不是 callback class 继承体系。

### 移出 SDK 的 nouns (Gateway-owned)

- `LLMEnvironment`
- `ChatResponse`
- `ChatStream`
- Provider/model/role runtime entities that currently live in SDK config/model modules.

现状证据：

- SDK heavy config file 有 755 行，含 `ModelDef`、`ProviderDef`、`RoleModelEntry`、`RoleDef`、`ResolvedProvider`、`ResolvedRole`、`CircuitBreakerConfig`、`RoleConfigData`、`load_config()`、`get_role_config()`、`reset_role_config()`，见 `packages/graph-agent/src/graph_agent/config/llm_config.py:40`、`:54`、`:71`、`:79`、`:91`、`:102`、`:115`、`:176`、`:640`、`:748`、`:753`。
- Gateway current schema file 有 132 行，含 Pydantic `ModelEntry`、`ProviderEntry`、`RoleModelEntry`、`RoleEntry`、`RolesData`、`ModelDef`、`ProviderDef`、`ResolvedProvider`、`ResolvedRole`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:10`、`:24`、`:41`、`:51`、`:64`、`:77`、`:92`、`:110`、`:122`。
- Gateway resolver 依赖 Pydantic `model_dump()`，并读取 role/model `temperature` 与 `max_tokens`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:151-168`、`:181-188`。
- Studio 当前 import SDK config 的影响点：`apps/studio/backend/app/services/copilot.py:36`、`apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py:22`。
- SDK `llm_client_manager.py` 仍存在，并 import `ProviderDef` / `ResolvedProvider`，见 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:1-5`、`:24`；该文件需随 Q3 迁往 Gateway。

## §4 Observability

### 新形态

- Tracing 默认自动落盘，不再让用户实例化 `TracingCallback(trace_dir=...)`。
- `run_skill` / `predict_skill` 接收 `event_subscriber: Callable[[CallbackEvent], None] | None`。
- Engine 对同一份内部事件源做两个出口：
  - 默认出口：写 `<workspace_dir>/runs/<run_id>/trace.jsonl`。
  - 可选出口：调用 `event_subscriber(event)`，供 WebSocket / UI timeline 实时推送。
- `CallbackEvent` 保留为 wire payload contract。

### 废除项

- [BREAKING] 废除 public `AgentCallback` / `Callback` base class 暴露。
- [BREAKING] 废除 `EventStreamCallback` 作为独立用户可实例化类。
- [BREAKING] `TracingCallback` 不再是 public setup API，仅可作为内部实现细节或过渡兼容层。

### StudioQueueCallback 迁移

现状：Studio worker 构造 `StudioQueueCallback(process_queue)` 并传 `TracingCallback(trace_dir=run_dir)` 与 `callbacks=[...]`，见 `apps/studio/backend/app/services/run_manager.py:230-235`。

迁移：把 `StudioQueueCallback` 从继承 callback 的类，改为 `event_subscriber` 适配器函数：

```python
def enqueue_event(event: CallbackEvent) -> None:
    process_queue.put(event.model_dump(mode="json"))
```

### 现状证据

- `TracingCallback` 当前 public class 定义在 `packages/graph-agent/src/graph_agent/callbacks/tracing.py:58`。
- `TracingCallback` 当前会写固定名 `tracing.jsonl`，见 `packages/graph-agent/src/graph_agent/callbacks/tracing.py:78-85`。
- `PredictTracingCallback` 当前继承 `TracingCallback`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76-86`。
- 当前 `run_skill` 仍有 `callbacks` 与 `trace_dir` 参数，见 `packages/graph-agent/src/graph_agent/core/runner.py:63-67`。

## §5 Errors [BREAKING Cutover]

### 新四大家族

- `GraphAgentError`
  - SDK root error，保留。
- `GraphCompileError`
  - 用户可修复的编译、解析、schema、契约、输入资源错误。
- `GraphExecutionError`
  - 引擎执行、状态转换、工具运行、trace 写入、artifact 写入等运行期错误。
- `ModelProviderError`
  - Gateway/provider/role/model/fallback 失败。
- `ResourceNotFoundError`
  - 文件、skill ref、resource ref、workspace path 等定位失败。

### 当前错误层级证据

当前 public `graph_agent.__init__` 只导出 `GraphAgentError`、`SkillLoadError`、`SkillCompilationError`，见 `packages/graph-agent/src/graph_agent/__init__.py:37-39`、`:68-70`。

当前 `core/exceptions.py` 的实际错误类包括：

| Current class | Evidence |
|---|---|
| `GraphAgentError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:82` |
| `GraphAgentFatalError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:103` |
| `LoaderError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:110` |
| `SkillParseError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:119` |
| `SkillModuleLoadError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:128` |
| `PhaseBuildError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:137` |
| `SkillCompileError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:146` |
| `ValidationError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:161` |
| `SchemaValidationError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:170` |
| `ContractValidationError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:179` |
| `ExecutionError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:191` |
| `PhaseExecutionError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:200` |
| `StateTransformError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:209` |
| `ToolExecutionError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:221` |
| `PersistenceError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:234` |
| `CheckpointError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:243` |
| `TraceWriteError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:252` |
| `ArtifactError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:261` |
| `SkillLoadError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:272` |
| `SkillCompilationError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:276` |
| `TemplateRenderError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:318` |
| `MaxRetriesExceededError` | `packages/graph-agent/src/graph_agent/core/exceptions.py:338` |

Gateway 当前 `GatewayError` 继承 SDK `ExecutionError`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:7-13`；v4 cutover 后必须改为继承 `ModelProviderError`。

### 旧 -> 新完整迁移映射

| Old | New | Rationale | Studio/import impact |
|---|---|---|---|
| `GraphAgentError` | `GraphAgentError` | root 保留 | Studio catch root 的地方继续可用 |
| `GraphAgentFatalError` | `GraphExecutionError` | hard invariant failure belongs to engine runtime | Engine callers update catch |
| `LoaderError` | `GraphCompileError` | load/parse/build before execution | SDK internals update |
| `SkillParseError` | `GraphCompileError` | user-authored document parse failure | SDK internals update |
| `SkillModuleLoadError` | `GraphCompileError` | skill module cannot load before graph runs | SDK internals update |
| `PhaseBuildError` | `GraphCompileError` | phase cannot become runtime node | SDK internals update |
| `SkillCompileError` | `GraphCompileError` | compile contract failure | SDK internals update |
| `ValidationError` | `GraphCompileError` | schema/preflight user-fixable failure | SDK internals update |
| `SchemaValidationError` | `GraphCompileError` | schema validation failure | SDK internals update |
| `ContractValidationError` | `GraphCompileError` | graph/IO contract failure | SDK internals update |
| `SkillLoadError` | `GraphCompileError` or `ResourceNotFoundError` | malformed skill -> compile; missing referenced file/skill -> resource | Studio `apps/studio/backend/app/services/skills.py:20` imports it today |
| `SkillCompilationError` | `GraphCompileError` | public compile catch-all | Studio `apps/studio/backend/app/services/skills.py:20` imports it today |
| `ExecutionError` | `GraphExecutionError` | runtime graph execution failure | Gateway currently subclasses it |
| `PhaseExecutionError` | `GraphExecutionError` | phase runtime failure | SDK internals update |
| `StateTransformError` | `GraphExecutionError` | engine state conversion failure | SDK internals update |
| `ToolExecutionError` | `GraphExecutionError` | tool runtime failure | SDK internals update |
| `PersistenceError` | `GraphExecutionError` | run-owned write failure | SDK internals update |
| `CheckpointError` | `GraphExecutionError` | run checkpoint write/read failure | SDK internals update |
| `TraceWriteError` | `GraphExecutionError` | run trace write failure | SDK internals update |
| `ArtifactError` | `GraphExecutionError` | run artifact write/read failure | SDK internals update |
| `TemplateRenderError` | `GraphCompileError` | prompt/template contract failure before provider call | SDK internals update |
| `MaxRetriesExceededError` | `GraphExecutionError` | runtime retry exhaustion | SDK internals update |
| `GatewayError` | `ModelProviderError` | provider/model/role domain | `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:13` |
| `AllProvidersFailedError` | `ModelProviderError` | provider fallback exhausted | Gateway callers update |
| `GatewayResolverMissingError` | `ModelProviderError` | required model resolver missing for LLM phase | Gateway callers update |
| `GatewayRoleNotConfiguredError` | `ModelProviderError` | role/model config absent | Gateway callers update |
| `SkillResolutionError` | `ResourceNotFoundError` | skill reference cannot resolve | Studio resolver import path updates where used |
| resource file not found/path invalid payloads | `ResourceNotFoundError` | reference/example/resource lookup failure | SDK resource helpers update |

## §6 [BREAKING] 迁移路径汇总

All items below are A 类：属于 Round 31 ground-up API catalog charter 内，PM Q3-Q5 已拍方向；不需要再抛 PM，按 cutover 计划推进。B 类：无。

### [BREAKING] 1. LLM config / provider runtime 移出 SDK

- 理由：Q3 已拍“Gateway 管模型环境，SDK 只管执行”。
- 迁移路径：
  1. Gateway 先实现 loader/validator API，保留现有 Pydantic `RolesData` resolver contract。
  2. 不把 SDK dataclass 机械覆盖到 Gateway schema；resolver 依赖 `model_dump()`、`temperature`、`max_tokens`。
  3. `llm_client_manager.py` 随 provider runtime 一并迁 Gateway。
  4. Studio Copilot import 从 `graph_agent.config.llm_config` 切到 Gateway 统一入口。
- 影响点：
  - `packages/graph-agent/src/graph_agent/config/llm_config.py:40-753`
  - `packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:10-122`
  - `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:151-188`
  - `apps/studio/backend/app/services/copilot.py:36`
  - `apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py:22`
  - `packages/graph-agent/src/graph_agent/models/llm_client_manager.py:24`

### [BREAKING] 2. `run_skill` / `predict_skill` 改为 workspace_dir 必传

- 理由：Engine 写文件，Engine 规定 workspace 内部结构；Studio 只决定 workspace root。
- 迁移路径：
  1. 删除 public `trace_dir` 参数。
  2. 删除 `inputs["output_dir"] / "traces"` fallback。
  3. 新签名强制传 `workspace_dir: Path`。
  4. Engine 创建 `<workspace_dir>/runs/<run_id>/` 并写 trace/result。
- 影响点：
  - `packages/graph-agent/src/graph_agent/core/runner.py:59-73`
  - `packages/graph-agent/src/graph_agent/core/runner.py:235-239`
  - `apps/studio/backend/app/services/run_manager.py:230-235`

### [BREAKING] 3. TracingCallback / Callback inheritance 改为 event_subscriber

- 理由：用户不应创建 tracing callback 或指定 trace file；eventstream 与 tracing 同源不同出口。
- 迁移路径：
  1. SDK 内部生成 tracing writer。
  2. Public API 只接受 `event_subscriber(event: CallbackEvent)`.
  3. Studio `StudioQueueCallback` 改为 queue adapter function。
- 影响点：
  - `packages/graph-agent/src/graph_agent/callbacks/tracing.py:58`
  - `packages/graph-agent/src/graph_agent/core/runner.py:63-67`
  - `apps/studio/backend/app/services/run_manager.py:230`

### [BREAKING] 4. PredictResult 废除，RunResult 同形化

- 理由：PM Q4 指定 predict 最终记录结果应与真实 run 一样。
- 迁移路径：
  1. `RunResult` 增加 `source`、`phases`、`path_diff`。
  2. `PhaseRecord`、`PathDiff` 晋升 public。
  3. `PredictResult` 删除；Studio predict diagnostics 改读 `RunResult(source="predict")`。
- 影响点：
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:24`
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:37`
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:47`
  - `packages/graph-agent/src/graph_agent/core/result.py:46-60`

### [BREAKING] 5. Predict interception 全搬 Gateway

- 理由：Copilot predictor 是 Gateway chat/predict facade；SDK 不能反向依赖 Gateway implementation。
- 迁移路径：
  1. `PredictGatewayChatModel`、predict interception、mock source routing 搬到 Gateway。
  2. Gateway resolver 负责把 predict LLM phase 路由到 Copilot predictor。
  3. SDK 只消费 `ModelResolverProtocol`。
- 影响点：
  - SDK 当前 import Gateway `GatewayChatModel`：`packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:11`
  - Gateway 当前反向 import SDK `PredictGatewayChatModel`：`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74`

### [BREAKING] 6. `.workspace/predict/` 顶层子目录废除

- 理由：predict 与 run 同形，predict artifacts 进入 `runs/<run_id>/`；避免双轨存储。
- 迁移路径：
  1. 删除 `predict_dir_for()`。
  2. 删除 API response `file_paths.predict_dir`。
  3. `predictor.py` 不再写 `.workspace/predict/latest_predict.json`，改读 SDK 返回的 run-scoped artifacts。
  4. 在 `STUDIO_GITIGNORE` template (`apps/studio/backend/app/services/git_local.py:21-26`) 中移除 `!/.workspace/predict/` 行 — 该 template 由 `write_studio_gitignore()` (`apps/studio/backend/app/services/git_local.py:320-323`) 写入每个 skill 项目目录的 `.gitignore`。
  5. 旧 `.workspace/predict/latest_predict.json` 不兼容迁移，部署后重新生成。
- 影响点：
  - Studio doc 当前列 `.workspace/predict`：`docs/studio/system-level/workspace-file-system/baseline.md:365-368`
  - `apps/studio/backend/app/services/skills.py:746-747`
  - `apps/studio/backend/app/services/skills.py:964`
  - `apps/studio/backend/app/services/skills.py:996`
  - `apps/studio/backend/app/services/skills.py:1036`
  - `apps/studio/backend/app/services/predictor.py:33`
  - `apps/studio/backend/app/services/predictor.py:114-118`
  - `apps/studio/backend/app/services/git_local.py:21-26`
  - `apps/studio/backend/tests/test_skill_git_p0.py:40-44`
  - `apps/studio/backend/tests/test_api.py:167-170`

### [BREAKING] 7. Errors 四大家族 cutover

- 理由：调用方需要按责任归属 catch，而不是按内部模块层级 catch。
- 迁移路径：
  1. 新增 `GraphCompileError`、`GraphExecutionError`、`ModelProviderError`、`ResourceNotFoundError`。
  2. 按 §5 映射更新 SDK 内部 raise/catch。
  3. Gateway `GatewayError` 改继承 `ModelProviderError`。
  4. Studio catch `SkillLoadError` / `SkillCompilationError` 的位置改为 `GraphCompileError` / `ResourceNotFoundError`。
- 影响点：
  - `packages/graph-agent/src/graph_agent/__init__.py:37-39`
  - `packages/graph-agent/src/graph_agent/__init__.py:68-70`
  - `packages/graph-agent/src/graph_agent/core/exceptions.py:82-338`
  - `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:7-13`

### [BREAKING] 8. Gateway verbs/nouns ownership cutover

- 理由：`configure_llm_environment`、`chat_with_role`、`LLMEnvironment`、`ChatResponse`、`ChatStream` 均是 model/provider/role domain，不属于 SDK core。
- 迁移路径：
  1. 从 SDK catalog 删除这些 symbols。
  2. Gateway 单独定义 chat/predict facade。
  3. Studio Copilot/Settings 改接 Gateway。
- 影响点：
  - `apps/studio/backend/app/services/copilot.py:36`
  - `apps/studio/backend/tests/routers/test_copilot_ws_endpoint.py:22`

## §7 workspace 文件夹结构规范

本节属于 Engine 文档。Studio 文档只说明 workspace root 如何决定；Engine 文档规定 root 下面怎么写。

### Root

`workspace_dir: Path` 由宿主应用传入，必须是绝对路径。SDK 不决定这个目录放在用户机器哪里。

### Required subdirectories

1. `<workspace_dir>/runs/`
   - Engine-owned run artifact root。
   - 每次 `run_skill` 与 `predict_skill` 都创建 `<workspace_dir>/runs/<run_id>/`。
   - 字段级内容：
     - `trace.jsonl`: one JSON `CallbackEvent` per line。
     - `result.json`: serialized `RunResult`。
     - `final_state.json`: final `RunResult.context` snapshot。
     - `metrics.json`: serialized `RunResult.metrics`。
     - `artifacts/`: phase/tool generated sidecars。
   - Predict run 同样写这里，`RunResult.source="predict"`。

2. `<workspace_dir>/golden/`
   - Engine-owned baseline root。
   - `evaluate_golden_baseline` 读取/写入 baseline dataset 与 reports。
   - 字段级内容：
     - `<baseline_id>/baseline.json`
     - `<baseline_id>/report.json`
     - `<baseline_id>/cases/*.json`

3. `<workspace_dir>/test_inputs/`
   - Engine-owned reusable input dataset root。
   - 字段级内容：
     - `<input_id>.json`
     - optional `index.json` for metadata cache。

### Removed subdirectory

- `<workspace_dir>/predict/` 不再存在。
- 现状证据：Studio 文档目前还列 `.workspace/predict`，见 `docs/studio/system-level/workspace-file-system/baseline.md:365-368`；Studio backend 也有 `predict_dir_for()`，见 `apps/studio/backend/app/services/skills.py:746-747`。v4 cutover 必须清理这些旧入口。

### Invariants

- Engine 不写 workspace root 之外的 run/predict/golden artifacts。
- Host app 可以删除整个 `workspace_dir`，但不应重命名 Engine 子目录。
- `run_id` 是 `runs/<run_id>` 的唯一索引；predict 不再有独立 latest file。
- Event stream 与 trace file 同源：`event_subscriber` 收到的 payload 必须能逐行写入 `trace.jsonl` 后被 replay。
