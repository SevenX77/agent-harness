# Round 31 Ground-Up API Catalog Redesign (a1 draft v6 — based on decisions baseline)

## §0 一句话总览

graph-agent SDK 是文档驱动的黑盒图执行虚拟机。它只暴露编译、运行、预演、基线评估、图序列化和图回写这 6 个引擎入口；模型环境、即席聊天、provider 解析和 Copilot 预测器归 Gateway；Studio HTTP 层负责自己的产品功能编排。

本轮 catalog 的核心变化是把 SDK 从“运行时工具箱”收敛成“给 workspace、给 resolver、给输入，然后得到同形结果和事件流”的内核 API。Tracing 默认自动落盘，实时进度通过订阅器派发；predict 与 run 输出同形；workspace 子目录规范归 Engine 文档所有。

## §0.2 Changelog

- v6 (2026-05-30): 补 cache 链式机制 + golden 警告 + 一刀切阻塞点; 引用 decisions.md 权威源.

## §0.5 权威源

本 design 受 [decisions.md](decisions.md) 16 项 PM 拍板基线约束。任何跟 decisions.md 冲突的描述，一律以 decisions.md 为准。

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

### SDK verbs (收敛暴露 6 个)

1. `compile_skill(workspace: SkillWorkspace) -> CompileResult`
   - 功能：编译并静态校验一个 skill，输出可执行黑盒句柄和结构化诊断。
   - 工程含义：现有 `compile_skill` 已存在，但返回与错误形态需要对齐新 `CompileResult`。

2. `run_skill(compiled_skill: CompiledSkill, inputs: dict, model_resolver: ModelResolverProtocol, workspace_dir: Path, event_subscriber: Callable[[CallbackEvent], None] | None = None) -> RunResult`
   - 功能：真实执行已编译 skill。
   - 关键约束：不再接收 `llm_env`。Gateway 管模型环境，SDK 只接收 resolver protocol。
   - 现状证据：当前 `run_skill` 仍接收 path、`trace_dir`、`callbacks`、`model_resolver`，见 `packages/graph-agent/src/graph_agent/core/runner.py:59-73`；V0.3 主线在 `_run_v030_skill_dict()` 中通过 `trace_dir` 和 `callbacks` 透传，见 `packages/graph-agent/src/graph_agent/core/runner.py:221-275`。

3. `predict_skill(compiled_skill: CompiledSkill, inputs: dict, model_resolver: ModelResolverProtocol, workspace_dir: Path, event_subscriber: Callable[[CallbackEvent], None] | None = None) -> RunResult`
   - 功能：执行 predict 工序，逻辑节点真实跑；SDK 负责 predict cache / ABC 选择 / 链式失效判断，只有 cache miss 且需要 Copilot 模拟时，才通过 Gateway predict chat model 调 Studio 注入的 Copilot callable。
   - 返回：与真实 run 同形的 `RunResult`，顶层 `source="predict"`。
   - 关键约束：Gateway 不存 cache、不做业务决策；SDK 不 import Studio，只通过 `model_resolver` 触达 Gateway callable bridge。

4. `evaluate_golden_baseline(compiled_skill: CompiledSkill, dataset: BaselineDataset, model_resolver: ModelResolverProtocol, workspace_dir: Path) -> BaselineReport`
   - 功能：批量执行 baseline 对比，产出通过率和差异报告。
   - 文件约束：Engine 按 §7 写入 workspace，不由 Studio 拼内部路径。

5. `serialize_skill_graph(compiled_skill: CompiledSkill) -> SerializedGraphData`
   - 功能：把编译产物转换成 UI 可画的节点、边、IO、元数据。
   - 关键约束：不暴露 AST internals。

6. `serialize_graph_back_to_markdown(graph_edits: SerializedGraphData, original_markdown: str) -> str`
   - 功能：把画布编辑反向合并回 Markdown。
   - 关键约束：[NEW v6] 这是 UI authoring API，不是执行 API；必须按 round-trip 语义保留未触碰文本。
   - 实施：`packages/graph-agent/src/graph_agent/core/skill/io/graph_serializer.py:27` 当前 `del original_md` (fresh-render)；round-31 实施时改成 `ruamel.yaml` round-trip (`.venv` 已装 ruamel, 业内 authoring 工具行业标准)。

### 移出 SDK 的 verbs (Gateway-owned)

- `configure_llm_environment(...)`
  - 去向：Gateway 包。
  - 原因：Q3 已拍，模型环境加载、验证、provider fallback、熔断、热加载不属于 SDK。

- `chat_with_role(...)`
  - 去向：Gateway 包。
  - 原因：即席对话直接消费 role/provider/model 环境，和 predict LLM 模拟同属 Gateway chat/predict facade。

## §2.5 predict↔golden↔run↔copilot 协作链契约

本节是叙事契约，不新增 API。它说明 `predict_skill`、`run_skill`、`evaluate_golden_baseline`、Gateway Copilot callable 和 Studio HTTP golden 编排如何配套工作。以 [decisions.md §4](decisions.md#§4-q4-predict-定位--copilot-协作迭代-prompt-工程入口)、[decisions.md §7](decisions.md#§7-阻塞点-2-predict-cache-在-sdk--链式失效)、[decisions.md §10](decisions.md#§10-阻塞点-5-cache-累积--golden-锁定--链式豁免--结构调整警告) 为准。

1. **predict 阶段**
   - Owner：SDK 负责编排 `predict_skill`、predict cache、ABC 选择和链式失效；Gateway 负责 predict chat model / callable bridge；Studio 负责触发按钮、展示和注入 Copilot callable。
   - 用户配完 skill 并 compile 通过后点击 Predict。SDK `predict_skill` 跑模拟图：逻辑节点真实执行；LLM 节点先查 SDK predict cache，miss 且 `predict_mode=True` 时，由 `model_resolver` 路由到 Gateway predict chat model，再调用 Studio 注入的 Copilot callable 预测输出。
   - 输出：`RunResult(source="predict")`。
   - 文件：SDK 写 `<workspace_dir>/runs/<run_id>/trace.jsonl` 和同 run 结构的结果 artifacts。
   - Cache key：`(phase_id, prompt_hash, input_hash)`。
   - `input_hash` 算法：只 hash 当前 phase 在 `io.inputs` 中声明的字段，不 hash 全量 `BlackboardState`。理由是 phase IO schema 是节点真实输入视图；全量 state 会破坏 phase 沙箱隔离。现状证据：`BlackboardData` 三分区在 `packages/graph-agent/src/graph_agent/runtime/state.py:15-20`，`BlackboardState.data` 在 `packages/graph-agent/src/graph_agent/runtime/state.py:88-94`；`PhaseIOSchema.inputs/outputs` 在 `packages/graph-agent/src/graph_agent/core/manifest.py:31-38`。
   - 数据链路：`BlackboardState.data.inputs` 是全局只读输入；`phase_outputs[phase_id]` 保存每个 phase 的输出；`scratch` 是运行期临时区。phase 开跑前按 `io.inputs` 从 blackboard 取输入视图，phase 结束后写 `phase_outputs[phase_id]`。

2. **Copilot 辅助调 prompt**
   - Owner：Gateway 生成建议；Studio 负责把建议呈现给用户并驱动编辑。
   - 用户读取 predict 结果后，和 Studio Copilot 协作迭代 prompt、phase 结构、few-shot、protocol。SDK 不参与 chat，不持有 provider 环境；Gateway 仅作为 callable bridge 调用 Studio 提供的模拟能力。

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

### 链式失效示例

假设图为 `A -> B -> C`：

1. 初始 predict：A/B/C 都按 `(phase_id, prompt_hash, input_hash)` 写入 cache。
2. 用户修改 A 的 prompt，A 的 `prompt_hash` 变化，A cache miss，A 重新执行并写 `phase_outputs["A"]`。
3. B 的 `io.inputs` 声明读取 A 输出字段；A 输出变了，所以 B 的 `input_hash` 变化，B cache miss。
4. B 重新执行并写 `phase_outputs["B"]`。
5. C 的 `io.inputs` 声明读取 B 输出字段；B 输出变了，所以 C 的 `input_hash` 变化，C cache miss。链式失效自然发生，不需要 Gateway 参与业务判断。

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
  - 必含字段：`source: "run" | "predict"`、`success`、`run_id`、`skill_id`、`context`、`metrics`、`trace_path`、`error`、`warnings`、`started_at`、`finished_at`、`wall_time_sec`、`phases: list[PhaseRecord] | None`、`path_diff: PathDiff | None`。
  - 现状证据：当前 `WorkflowResult` 已有 `success/run_id/skill_id/context/metrics/trace_path/error/started_at/finished_at/wall_time_sec`，见 `packages/graph-agent/src/graph_agent/core/result.py:46-60`。
  - Round-31 cutover 后 `RunResult.error` / `WorkflowResult.error` 类型从当前 `str | None` 升级为 `ErrorPayload | None`，以承载被 de-export leaf class 的 `code` / `level` / `stage` / `field_path` / `doc_link` 颗粒度；`ErrorPayload` 现状定义见 `packages/graph-agent/src/graph_agent/core/exceptions.py:21-45`。
- `PhaseRecord`
  - 从 private predict model 晋升 public；记录 phase_name、phase type、inputs、outputs、mocked_source。
  - 现状证据：当前定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:24-31`。
- `PathDiff`
  - 从 private predict model 晋升 public；记录 expected_path、actual_path、missing、extra、order_mismatch、`structural_mismatch [NEW v6]`。
  - 现状证据：当前定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:37-44`，含 expected_path / actual_path / missing / extra / order_mismatch；structural_mismatch 为 v6 新增字段。
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

## §3.5 Predict cache 行为

本节以 [decisions.md §7](decisions.md#§7-阻塞点-2-predict-cache-在-sdk--链式失效)、[decisions.md §10](decisions.md#§10-阻塞点-5-cache-累积--golden-锁定--链式豁免--结构调整警告)、[decisions.md §12](decisions.md#§12-gateway-不管业务)、[decisions.md §14](decisions.md#§14-copilot-接口在-studio-业务) 为准。

### Owner

- SDK owns：cache table、cache key 计算、ABC 选择、链式失效、predict/run graph 编排。
- Gateway owns：provider/model/role 解析、predict chat model、调用 Studio 注入的 Copilot callable。
- Studio owns：Copilot callable 的业务实现、Copilot UI、golden CRUD 编排。

### Cache table

Predict cache 是一张 SDK-owned 大 hash 表：

| Key | Value |
|---|---|
| `(skill_id, phase_id, prompt_hash, input_hash)` | phase output + metadata |

`input_hash` 只计算 phase `io.inputs` 声明字段，不计算全量 blackboard。现状证据同 §2.5：`BlackboardData` 在 `packages/graph-agent/src/graph_agent/runtime/state.py:15-20`，`PhaseIOSchema` 在 `packages/graph-agent/src/graph_agent/core/manifest.py:31-38`。

### 命中

SDK 内查 cache table。命中时直接返回 cached phase output，不调用 Gateway / LLM / Copilot callable。

### 未命中 (普通 run)

`predict_mode=False` 时，SDK 按真实 graph 执行 LOGIC / SUBGRAPH / LLM phase。LLM phase 通过 Gateway resolver 走真实 provider。执行成功后写入 cache table。

入口示意：

```python
await run_skill(skill_id, *, workspace_dir, predict_mode=False, ...)
```

### 未命中 (predict mode)

`predict_mode=True` 且 cache miss 时：

1. SDK 判断当前 phase 需要 LLM 模拟。
2. SDK 通过 `model_resolver` 请求 Gateway predict chat model。
3. Gateway predict chat model 调 Studio 注入的 Copilot callable。
4. SDK 拿到模拟输出，写入 cache table，标记 `source="predict"`。
5. `RunResult(source="predict")` 写入 `<workspace_dir>/runs/<run_id>/`。

入口示意：

```python
await run_skill(skill_id, *, workspace_dir, predict_mode=True, ...)
```

或 facade：

```python
await predict_skill(compiled_skill, inputs, model_resolver, workspace_dir)
```

### Cache 累积

Cache 多版本自然累积：prompt 变化、输入变化、phase 变化都会产生新 key。Round 31 不设计主动 GC；后续若要清理 cache，必须作为独立 storage policy 设计，不得影响本轮 API cutover。

## §4 Observability

### 新形态

- Tracing 默认自动落盘，不再让用户实例化 `TracingCallback(trace_dir=...)`。
- `run_skill` / `predict_skill` 接收 `event_subscriber: Callable[[CallbackEvent], None] | None`。
- Engine 对同一份内部事件源做两个出口：
  - 默认出口：写 `<workspace_dir>/runs/<run_id>/trace.jsonl`。
  - 可选出口：调用 `event_subscriber(event)`，供 WebSocket / UI timeline 实时推送。
- `CallbackEvent` 是唯一保留的事件契约 (浓缩后 wire payload)。

### 废除项

- [BREAKING] 废除 public `AgentCallback` / `Callback` base class 暴露。
- [BREAKING] 废除 `EventStreamCallback` 作为独立用户可实例化类。
- [BREAKING] `TracingCallback` 仅作为 SDK 内部实现细节 (internal trace writer, 黑盒写 `.jsonl`)。不作 public 兼容层；若内部不再用直接删类。

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

Round-31 真任务: Exception API catalog 从约 24 个公开 class 浓缩为 5 个 public class. 约 22 个细粒度 class 从 public `graph_agent.__init__` de-export, 不再作为 public isinstance catch 面承诺; 子颗粒度通过 `ErrorPayload.code` + `ERROR_REGISTRY` 保留.

### 最终 public 5 class

- `GraphAgentError`
  - SDK root error，保留。
- `GraphCompileError`
  - 用户可修复的编译、解析、schema、契约、输入资源错误 family.
- `GraphExecutionError`
  - 引擎执行、状态转换、工具运行、trace 写入、artifact 写入等运行期错误 family.
- `ModelProviderError`
  - Gateway/provider/role/model/fallback 失败 family.
- `ResourceNotFoundError`
  - 文件、skill ref、resource ref、workspace path 等定位失败 family.

本方案比 OpenAI / Anthropic 的 leaf-class 保留策略更激进; 原因是 graph-agent 的主要消费面是 Studio HTTP 与 SDK 边界调用, 按责任级 catch family class, 不需要把每个 per-condition leaf class 维持为 public API.

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

`SkillResolutionError` 当前定义在 `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:15`。Gateway 当前 `GatewayError` 继承 SDK `ExecutionError`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:7-13`；Round 31 cutover 后必须改为继承 `ModelProviderError`。

### 具体异常类 -> family 映射

| Current class | Family |
|---|---|
| `LoaderError` | `GraphCompileError` |
| `SkillParseError` | `GraphCompileError` |
| `SkillModuleLoadError` | `GraphCompileError` |
| `PhaseBuildError` | `GraphCompileError` |
| `SkillCompileError` | `GraphCompileError` |
| `ValidationError` | `GraphCompileError` |
| `SchemaValidationError` | `GraphCompileError` |
| `ContractValidationError` | `GraphCompileError` |
| `SkillLoadError` | `GraphCompileError` |
| `SkillCompilationError` | `GraphCompileError` |
| `TemplateRenderError` | `GraphCompileError` |
| `ExecutionError` | `GraphExecutionError` |
| `PhaseExecutionError` | `GraphExecutionError` |
| `StateTransformError` | `GraphExecutionError` |
| `ToolExecutionError` | `GraphExecutionError` |
| `PersistenceError` | `GraphExecutionError` |
| `CheckpointError` | `GraphExecutionError` |
| `TraceWriteError` | `GraphExecutionError` |
| `ArtifactError` | `GraphExecutionError` |
| `MaxRetriesExceededError` | `GraphExecutionError` |
| `GraphAgentFatalError` | `GraphExecutionError` |
| `GatewayError` | `ModelProviderError` |
| `AllProvidersFailedError` | `ModelProviderError` |
| `GatewayResolverMissingError` | `ModelProviderError` |
| `GatewayRoleNotConfiguredError` | `ModelProviderError` |
| `SkillResolutionError` | `ResourceNotFoundError` |

De-export 去向: 细粒度 class 可作为 internal implementation detail 保留, 但从 public `graph_agent.__init__` 移出; 用户按 `GraphCompileError` / `GraphExecutionError` / `ModelProviderError` / `ResourceNotFoundError` catch, 再用 `ErrorPayload.code` + `ERROR_REGISTRY` 区分原 leaf 颗粒度.

Studio 迁移: `apps/studio/backend/app/services/skills.py:20,304,327,1152` 从 `SkillLoadError` / `SkillCompilationError` tuple catch 改为 `GraphCompileError` / `ResourceNotFoundError` 等 family catch; Studio 不按 leaf class 做控制流分流.

## §5.5 Golden 锁定与结构性大调整警告

本节以 [decisions.md §10](decisions.md#§10-阻塞点-5-cache-累积--golden-锁定--链式豁免--结构调整警告) 为准。

### Golden 语义

- Golden 是用户标记锁定的"最后一版" phase output / run output 目标。
- Golden 不受链式失效影响：上游 `input_hash` 变化会触发普通 cache miss 重算，但不会覆盖用户锁定的 golden 条目。
- Golden 不是普通 transient cache row；它是阶段性结果目标。
- Studio HTTP golden CRUD 负责用户标记与锁定动作；SDK `evaluate_golden_baseline` 负责读取 dataset 与输出 report。

### 结构性大调整检测

Predict 时 SDK 主动检测以下三类信号，任一发生就触发 Copilot 轻量预测干预：

1. **IO Schema 突变**：字段增、删、改名，等价于数据血液断供。
2. **拓扑结构重排**：前序依赖节点删除，或节点类型在 `LOGIC` / `LLM` / `SUBGRAPH` 间变化。
3. **Role 变更**：角色定位发生极大差异，例如前端画图角色改成 SQL 专家角色。

不触发结构性警告的情况：

- prompt 纯文本微调。这只走 normal cache miss，不触发 structural mismatch。

### 触发后流程

1. SDK 发现结构性大调整信号。
2. SDK 通过 Gateway predict chat model 调 Studio 注入的 Copilot callable。
3. Copilot prompt 固定语义："评估 golden Y 在新结构下是否还兼容；不兼容则返回 FATAL + 字段级理由。"
4. SDK 将偏差大警告挂载到 `RunResult`。

### 警告挂载

主载体：

- `RunResult.path_diff.structural_mismatch`

`PathDiff` 当前已有 `missing`、`extra`、`order_mismatch`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:37-44`；v6 目标是在晋升 public 时扩展 `structural_mismatch` 字段。

备选载体：

- `RunResult.warnings`

当结构性警告不是路径差异本身，而是 role/IO 兼容性诊断时，可同时写入 `warnings`，供 Studio 以非 fatal 警告展示。

## §6 [BREAKING] 迁移路径汇总

BREAKING 1-8 全是 A 类 (Q3-Q5 / 阻塞点 / charter 内 / round-31 API catalog rightsizing). 不需要再抛 PM. B 类未授权: 无.

### [BREAKING] 1. LLM config / provider runtime 移出 SDK

- 理由：Q3 已拍“Gateway 管模型环境，SDK 只管执行”；[decisions.md §6](decisions.md#§6-阻塞点-1-llm-配置一刀切搬-gateway) 进一步拍定阻塞点 1：一刀切。
- 迁移路径：
  1. 一个 PR 内完成整体搬迁、Studio import 全 rename、SDK 老 provider/runtime code 删除。
  2. 不做 SDK 老 `llm_config` 与 Gateway 新 config 双栈过渡期。
  3. 不做 SDK -> Gateway compatibility proxy。
  4. Gateway 主导自己的 Resolver Schema 契约 (作为 Gateway public noun, 替代原 SDK Config)。
  5. 不把 SDK dataclass 机械覆盖到 Gateway schema；Gateway 自身已有 132 行 Pydantic schema + `resolver.py` 依赖 `model_dump()` / `temperature` / `max_tokens`, 必须保护。Gateway 主导的同时, 在此基础上向上透明兼容 Studio 输入。
  6. `llm_client_manager.py` 随 provider runtime 一并迁 Gateway。
  7. Studio Copilot import 从 `graph_agent.config.llm_config` 切到 Gateway 统一入口。
  8. 砍掉的 SDK LLM 配置能力去向必须写清：yaml 加载 / 验证 / 熔断 / 热加载 / provider/role 解析全部归 Gateway；真砍未列入 [decisions.md §16](decisions.md#§16-round-31-用户能力调整清单) 的能力必须停下来 escalate PM。
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

### [BREAKING] 5. Predict callable bridge 归 Gateway，cache / ABC / 链式失效归 SDK

- 理由：Copilot callable bridge 是 Gateway chat/predict facade；但 predict cache、ABC 选择和链式失效是 SDK 业务逻辑，以 [decisions.md §7](decisions.md#§7-阻塞点-2-predict-cache-在-sdk--链式失效) 为准。
- 迁移路径：
  1. Gateway 提供 predict chat model，用于调用 Studio 注入的 Copilot callable。
  2. SDK 删除对 Gateway implementation 的反向 import，只消费 `ModelResolverProtocol`。
  3. SDK 内部全权接管并封装 predict cache、ABC 决策、链式失效机制 (作为纯粹 internal implementation)；对外不暴露 cache nouns, 不进 public API catalog 表面。decisions §7 PM 拍板 ownership。
  4. SDK 只有在 cache miss 且 predict mode 需要 Copilot 模拟时才调用 Gateway。
  5. Gateway 不存 cache、不判断 golden、不做 ABC、不做链式失效。
- 影响点：
  - SDK 当前 import Gateway `GatewayChatModel`：`packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:11`
  - Gateway 当前反向 import SDK `PredictGatewayChatModel`：`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74`
  - SDK 当前 predict strategy/cache-like 业务入口：`packages/graph-agent/src/graph_agent/core/_predict_internal/strategy.py:14-194`

### [BREAKING] 6. `.workspace/predict/` 顶层子目录废除

- 理由：predict 与 run 同形，predict artifacts 进入 `runs/<run_id>/`；避免双轨存储。
- 迁移路径：
  1. 删除 `predict_dir_for()`。
  2. 删除 API response `file_paths.predict_dir`。
  3. `predictor.py` 不再写 `.workspace/predict/latest_predict.json`，改读 SDK 返回的 run-scoped artifacts。
  4. 在 `STUDIO_GITIGNORE` template (`apps/studio/backend/app/services/git_local.py:21-26`) 中移除 `!/.workspace/predict/` 行 — 该 template 由 `write_studio_gitignore()` (`apps/studio/backend/app/services/git_local.py:320-323`) 写入每个 skill 项目目录的 `.gitignore`。
  5. 旧 `.workspace/predict/latest_predict.json` 不兼容迁移，部署后重新生成。
- 影响点：
  - Studio workspace 文档已标记 `predict_dir_for()` 废除：`docs/studio/system-level/workspace-file-system/baseline.md:64-66`
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

> **[REVISED — 24->5 浓缩, 22 子类 de-export, code-based 颗粒度]**

- 理由：round-31 目标是 API catalog rightsizing; 调用方按责任归属 catch family class, 具体条件颗粒度走 `ErrorPayload.code` + `ERROR_REGISTRY`.
- 迁移路径：
  1. 新增 `GraphCompileError`、`GraphExecutionError`、`ModelProviderError`、`ResourceNotFoundError` 四个 family class, 全部直接继承 `GraphAgentError`.
  2. 约 22 个具体子类继承改成挂到对应 4 个 family class; internal raise 路径不动.
  3. 约 22 个具体子类从 `packages/graph-agent/src/graph_agent/__init__.py:37-39,68-70` de-export, 移出 public SDK catalog.
  4. `WorkflowResult.error` / `RunResult.error` 升级为 `ErrorPayload | None`, 含 `code` / `level` / `stage` / `field_path` / `doc_link`.
  5. Studio backend `apps/studio/backend/app/services/skills.py:20,304,327,1152` catch tuple 改成新 family, 例如 `except (GraphCompileError, ResourceNotFoundError)`.
  6. Gateway `GatewayError` 改继承 `ModelProviderError`; Gateway 4 个 ModelProviderError 子类可保留 internal 或由 Gateway public surface 自行决定.
  7. 现有 tests 中依赖具体 class 的 `pytest.raises` / `except` / `isinstance` 迁移到 4 family + `ErrorPayload.code` 断言.
- 影响点：
  - `packages/graph-agent/src/graph_agent/__init__.py:37-39`
  - `packages/graph-agent/src/graph_agent/__init__.py:68-70`
  - `packages/graph-agent/src/graph_agent/core/exceptions.py:82-338`
  - `packages/graph-agent/src/graph_agent/core/result.py:57`
  - `packages/graph-agent/src/graph_agent/core/error_registry.py`
  - `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:7-13`
  - `apps/studio/backend/app/services/skills.py:20,304,327,1152`

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
- 现状证据：Studio workspace 文档已标记 `predict_dir_for()` 废除，见 `docs/studio/system-level/workspace-file-system/baseline.md:64-66`；Studio backend 仍有 `predict_dir_for()`，见 `apps/studio/backend/app/services/skills.py:746-747`。Round 31 cutover 必须清理这些旧入口。

### Invariants

- Engine 不写 workspace root 之外的 run/predict/golden artifacts。
- Host app 可以删除整个 `workspace_dir`，但不应重命名 Engine 子目录。
- `run_id` 是 `runs/<run_id>` 的唯一索引；predict 不再有独立 latest file。
- Event stream 与 trace file 同源：`event_subscriber` 收到的 payload 必须能逐行写入 `trace.jsonl` 后被 replay。
