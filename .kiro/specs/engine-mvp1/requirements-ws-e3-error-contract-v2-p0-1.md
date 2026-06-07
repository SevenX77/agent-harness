---
ws_id: WS-E3-error-contract-v2-p0-1
modules:
  - 01-contract/03-compile-rules
  - 01-contract/04-data-contracts
  - 03-api-contract
depends_on: []
blocks: []
owns_files:
  - packages/graph-agent/src/graph_agent/core/exceptions.py
  - packages/graph-agent/src/graph_agent/core/result.py
  - packages/graph-agent/tests/core/test_error_payload_contract.py
  - packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py
  - packages/graph-agent/tests/predict/test_predict_skill_run_result.py
  - packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py
spec_ssot:
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md §3.1/§3.1.1
  - docs/engine/mvp1/01-contract/04-data-contracts/mvp1-alignment.md §3/§5 DC5/§6
  - docs/engine/mvp1/03-api-contract/mvp1-alignment.md §2.1/§2.2/§3.3
status: drafted
created: 2026-06-06
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md
review_flow: Claude 写需求书 -> Codex 写 RED 测试 -> Claude 契约门 -> Codex 写 task.md + Gemini prompt -> Gemini 实现 GREEN -> Codex 审 -> Codex 回写 baseline -> Claude 终审
---

# WS-E3 错误契约 V2 P0-1 - 需求书

> 本需求书是 WS-E3 的第一段 P0-1 流水线输入。下一步是 Codex 按 §6 写失败测试；未见 RED、未过 Claude 契约门，不得开始实现或写 Gemini 实施任务书。

## 1. 目标(intent + why)

给 engine 通用错误协议补上 V2 的最小闭环：`ErrorPayload` 能承载结构化 `details`，`GraphAgentError.context` 不再在转 payload 时丢失，`RunResult` 能返回有界 `diagnostics` 最终快照。这样 studio 和其他 app 不必只靠单个 `error` 或正则解析 `message` 才能定位失败；同时保留现有 `error` 主 fatal 兼容面。目标机制细节以 `spec_ssot` 为唯一真理，本需求书只定义范围、契约、测试和验收边界。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标唯一真理：
  - `docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md` §3.1 G2/G5 与 §3.1.1 P0-1。
  - `docs/engine/mvp1/01-contract/04-data-contracts/mvp1-alignment.md` §3、§5 DC5、§6。
  - `docs/engine/mvp1/03-api-contract/mvp1-alignment.md` §2.1、§2.2、§3.3。
- 实施计划：`docs/engine/mvp1/_impl/IMPL_PLAN.md` §二/§三/§六，WS-E3 为错误契约 V2 独立轨，首段优先级 P0-1。
- Backlog 来源：`docs/engine/mvp1/_impl-backlog.md` Tier 3 V2a。
- 现状锚点：
  - `docs/engine/mvp1/01-contract/04-data-contracts/baseline.md`
  - `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`
  - `docs/engine/mvp1/03-api-contract/baseline.md`
- 必读源码(实现前先读并回述关键符号/现状，行号只作 grounding，不作编辑坐标)：
  - `packages/graph-agent/src/graph_agent/core/exceptions.py` 的 `ErrorPayload`、`make_error_payload`、`GraphAgentError.__init__`。现状 payload 扁平，`context` 存在于异常对象但不会自动进入 payload。
  - `packages/graph-agent/src/graph_agent/core/result.py` 的 `RunResult`/`WorkflowResult`。现状只有单个 `error`，没有 `diagnostics`、limit、truncated、counts。
  - `packages/graph-agent/src/graph_agent/core/runner.py` 的 `run_skill`/`predict_skill` 失败边界与 `_write_workflow_result_artifacts`。本 WS 不 owns `runner.py`，只用它做真实 e2e 验证，除非契约门后 PM 另行扩 owns。
  - `packages/graph-agent/src/graph_agent/callbacks/events.py` 与 `callbacks/emit.py`。本 WS 不 owns 事件文件，只定义 `RunResult.diagnostics` 与未来 `DiagnosticEmittedEvent` 的关系。
  - 既有测试：`packages/graph-agent/tests/core/test_error_payload_contract.py`、`packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py`、`packages/graph-agent/tests/predict/test_predict_skill_run_result.py`。

## 3. 文件归属(并发锁,IR1)

本 WS owns 见 frontmatter `owns_files`。允许新增 `packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py`，用于真实 run/predict 边界的诊断快照测试。

禁止触碰：

- `packages/graph-agent/src/graph_agent/core/error_registry.py`：P0-2/P0-3 owns，registry dataclass、`remediation`、`doc_ref`、`doc_url`、`details_schema`、新错误码注册都不在 P0-1。
- `packages/graph-agent/src/graph_agent/callbacks/events.py`、`packages/graph-agent/src/graph_agent/callbacks/emit.py`：WS-E4 owns。`DiagnosticEmittedEvent` 的事件类和 emit 接线不在本 WS。
- `packages/graph-agent/src/graph_agent/core/runner.py`：WS-E7/WS-E1-io 等后续会碰运行边界；P0-1 只通过 `RunResult` 形状和实际调用测试验证兼容，不直接改 runner。
- `apps/studio/**`：studio 同步模型、HTTP DTO、前端消费另行路由，不在 engine WS-E3。

共享文件协调：

- WS-E4 的 `DiagnosticEmittedEvent` 子项需要消费本 WS 落地后的 `ErrorPayload` V2 形状；但按 `IMPL_PLAN`，WS-E4 的非诊断 V4 trace 事件可独立推进。本 WS 不在 frontmatter 声明硬阻塞，只在执行时协调诊断事件子项。
- 若 Codex 写 RED 时证明不改 `runner.py` 无法满足 §5 的最小 e2e，必须停下回报 PM 扩 owns 或拆出后续 WS，不得偷偷越界。

## 4. 现状锚点(baseline)

现状 `ErrorPayload` 只含 `code/level/stage/message/doc_link` 和可选定位字段，`GraphAgentError.context` 只保存在异常对象上；转成 payload 后丢失。`RunResult`/`WorkflowResult` 只有 `error: ErrorPayload | None`，没有诊断列表、截断标记或计数。run 失败边界会返回 `success=False` 与主 `error`，但 WARN 与多诊断全集需要消费者自行从 trace 或其他来源拼。

## 5. 目标行为(可测的契约)

### 5.1 `ErrorPayload.details` 是 JSON-safe 结构化诊断负载

- `ErrorPayload` 必须新增 `details`，默认是空对象，序列化后稳定存在或稳定可读；具体是否排除空对象由实现者决定，但 API 边界必须能读到空对象语义。
- `details` 只能承载 JSON-safe 数据；不可序列化对象、路径、异常对象、集合、Pydantic 对象等必须被规范化为可传输形状或安全字符串，不能让 `model_dump_json()`/`result.json` 写盘失败。
- `details` 不替代 `message`。`message` 仍是人类可读摘要；结构化字段给 app 做定位、分组、自动修复和富 UX。
- P0-1 不定义每个错误码的 `details_schema`；那是 P0-2 registry 化范围。P0-1 只要求容器存在、JSON-safe、可序列化、可从异常 context 自动带出。

### 5.2 `GraphAgentError.context` 必须进入 payload details

- 当 `GraphAgentError` 或子类带 `context` 且已有/可生成 `ErrorPayload` 时，payload 的 `details` 必须包含该 context 的 JSON-safe 表达。
- 如果调用点已显式给了 payload details，同时异常又带 context，二者不能互相吞掉；合并规则由实现者决定，但必须满足“显式 details 不丢、context 也可见、冲突键有可预测胜负”。
- 兼容旧调用：不带 context、不带 details 的错误仍按现有 registry metadata 自动回填 `level/stage/doc_link`。

### 5.3 `RunResult.diagnostics` 是有界最终快照

- `RunResult` 必须新增 `diagnostics: list[ErrorPayload]`，语义是本次 run/predict 的最终诊断快照。
- `error` 保留为主 fatal，向后兼容旧 consumer；当 `error` 存在而调用方未显式提供 diagnostics 时，`diagnostics` 至少必须包含主 fatal。
- `diagnostics` 必须有界，暴露最小元数据：`diagnostics_limit`、`diagnostics_truncated`、`diagnostic_counts`。计数至少能按 `level` 和 `code` 支撑 consumer 判断“有多少、是否被截断、主类是什么”。
- 有界策略必须稳定：超过上限时保留确定性的前 N 条或等价确定性选择，标记 truncated，并让 counts 反映完整输入或明确的可解释计数范围。
- 成功结果默认 diagnostics 为空列表，limit/truncated/counts 处于安全默认值，不破坏既有 `RunResult(... success=True ...)` 构造。

### 5.4 snapshot 与 event 的关系必须被写清，但事件实现不在本 WS

- P0-1 只落 `RunResult.diagnostics` 快照和 `ErrorPayload.details` 形状。
- `DiagnosticEmittedEvent` 是 WS-E4 的事件实现范围。它后续应携带完整 `ErrorPayload` 与 `diagnostic_id`，并与 `RunResult.diagnostics` 通过同一诊断身份关联。
- 本 WS 不在事件流里双写语义，不要求改 `CallbackEvent` union；只要结果快照 shape 能被 WS-E4 消费即可。

### 5.5 向后兼容

- 现有 `ErrorPayload(code, message)`、`make_error_payload(...)`、`GraphAgentError(message, payload=...)`、`RunResult(... error=payload ...)` 构造必须继续可用。
- 现有 `model_dump(mode="json")` 和 `model_dump_json()` 边界继续可用，新增字段不得引入非 JSON 类型。
- `WorkflowResult` 作为 `RunResult` 兼容包装继续继承新字段和 dict-like shim。
- P0-1 不改变 `ERROR_REGISTRY` 的 key set，不改变 `ErrorCodeMetadata` 形状，不改变 `doc_link` 语义。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，Claude 契约门通过后才能写实施任务书。标 ★ 的必须有真实或接近真实的端到端验证，不许只 mock 到绿。

- `ErrorPayload.details` 容器：默认空对象语义可读；显式 details 会出现在 `model_dump(mode="json")` 与 `model_dump_json()`；metadata 自动回填不回归。
- JSON-safe 规范化：details/context 中包含 `Path`、异常对象、集合、嵌套 Pydantic/BaseModel 或其他非原生 JSON 值时，payload 和 result 写盘不会失败，输出形状稳定。
- context 进入 payload：`GraphAgentError(..., context={...})` 在有显式 payload、无显式 payload、payload 已有 details 三种情况下都不丢 context。
- 兼容旧错误码校验：unknown code 仍拒绝；外部 gateway code 的现有兼容分支不回归；`ERROR_REGISTRY` 93 码 key set 不因 P0-1 改变。
- `RunResult.diagnostics` 默认：成功结果为空；失败结果只传 `error` 时 diagnostics 自动含主 fatal；显式 diagnostics 时主 fatal 与列表关系符合 §5.3，不出现重复或丢失。
- 有界与计数：构造超过 limit 的 diagnostics，断言 `diagnostics_truncated`、`diagnostics_limit`、`diagnostic_counts` 稳定且可序列化；按 code/level 的统计能覆盖 FATAL 与 WARN。
- `WorkflowResult` 兼容：旧 dict-like `get`/`__getitem__` 读取不回归，`result.json` 中新增诊断字段 JSON-safe。
- `predict_skill`/`RunResult` 既有测试改写：现有只断言 `error` 的失败结果测试要增加 diagnostics 快照断言，不移除原 `error` 断言。
- ★ 真实 run failure e2e：用一个会触发 engine 已有 `GraphAgentError` 的真实入口，例如传入非 V0.3 skill root 或缺 `GRAPH.md` 的目录调用 `run_skill`，断言返回 `success=False`、主 `error` 保留、`diagnostics` 至少含同一主 fatal、`result.json` 可读且含 diagnostics。不得只手工 new `RunResult`。
- 负面边界：P0-1 测试不得要求 `DiagnosticEmittedEvent` 已存在，不得要求 `GET /errors`、`remediation`、`doc_ref`、`doc_url`、`details_schema`、运行期细分码已实现。

## 7. 硬依赖约束(若 WS 内组件间有强制先后)

1. `ErrorPayload.details` 与 context 序列化必须先稳定；`RunResult.diagnostics` 只能承载已经 JSON-safe 的 `ErrorPayload`。
2. `RunResult` 的默认派生和有界策略必须在真实 run failure e2e 前完成，否则 e2e 会只看到旧 `error`。
3. WS-E4 的 `DiagnosticEmittedEvent` 只能在本 WS shape 契约稳定后实现诊断事件；本 WS 不反向修改事件 union。

## 8. 验收标准(硬退出,IR4)

- [ ] §6 RED 测试先失败，契约门通过后实现到 GREEN。
- [ ] `ErrorPayload` 支持 JSON-safe `details`，旧 metadata 自动回填和 unknown code 拒绝不回归。
- [ ] `GraphAgentError.context` 能进入 payload details，且不吞显式 details。
- [ ] `RunResult`/`WorkflowResult` 暴露有界 diagnostics 快照、limit、truncated、counts；失败只传 `error` 时 diagnostics 至少包含主 fatal。
- [ ] `model_dump(mode="json")`、`model_dump_json()`、`result.json` 写盘均通过非 JSON 值 details/context 回归测试。
- [ ] `ERROR_REGISTRY` 93 码 key set 和 `ErrorCodeMetadata` 形状未改变。
- [ ] 无回归：现有 `error` 字段、`status` property、predict/run 失败结果、WorkflowResult dict-like shim 继续可用。
- [ ] 至少一条真实 run failure e2e 通过，且不是纯构造模型到绿。
- [ ] P0-2/P0-3/WS-E4 范围没有被顺手实现。
- [ ] 验证命令至少包括：`uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py packages/graph-agent/tests/exceptions/test_error_catalog_rightsizing.py packages/graph-agent/tests/predict/test_predict_skill_run_result.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q`。

## 9. 不做(范围锁定,IR7)

- 不改 `error_registry.py`，不把 `ErrorCodeMetadata` 改 dataclass，不新增 `remediation`、`doc_ref`、`doc_url`、`details_schema`、`schema_version`。
- 不实现 `GET /errors`，不改 studio HTTP DTO 或前端消费。
- 不注册 golden/iterate 新码，不拆运行期 tool/state-transform/persistence/provider 细分码，不处理 catch-all 消减。
- 不做 `source_span`、`phase_path`、`location_requirements` 全面轴审计。
- 不做 i18n、错误码生命周期、分页、过滤、`remediation_actions`。
- 不改 `callbacks/events.py`/`emit.py`，不实现 `DiagnosticEmittedEvent`，只为它保留 shape 契约。
- 不改 `runner.py`。若真实 e2e 必须改 runner 才能过，先回报 PM 扩 owns 或另拆 WS。
- 范围外问题记 `docs/deferred-items.md`，不得顺手改。

## 10. baseline 回写指令(IR6)

实现落地后，Codex 按真实代码回写：

- `docs/engine/mvp1/01-contract/04-data-contracts/baseline.md`：记录 `ErrorPayload.details`、context 序列化策略、`RunResult.diagnostics` 及有界字段的真实形状。
- `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`：只回写 P0-1 已真实落地的错误契约 V2 最小闭环；不得提前写 P0-2/P0-3。
- `docs/engine/mvp1/03-api-contract/baseline.md`：记录 run/predict 返回 `diagnostics` 快照的真实 API 形状，以及 `DiagnosticEmittedEvent` 仍属后续 WS-E4 时不得写成 live。

## 11. 评审检查点

- 契约门(Claude 审测试)：重点查测试是否忠实编码 `details + context + diagnostics 有界快照`，是否有真实 run failure e2e，是否错误地把 WS-E4/P0-2/P0-3 拉进 P0-1。
- Codex 审查退出：只按 §8 硬退出条件，不按“模型字段看起来加了”主观放行；尤其要查 JSON-safe 写盘和旧 consumer 兼容。
- Claude 终审：看意图是否落实、baseline 是否照真实代码诚实回写、测试是否存在只 mock 到绿或把未来目标当现状。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准测试写 kiro `task.md`，落点 `.kiro/specs/engine-mvp1/task-ws-e3-error-contract-v2-p0-1.md`，遵守：

- 来源 = 已批准测试，测试是契约；不凭空设计实现步骤。
- 格式 = Phase 分段 + `- [ ]` 勾选项 + 每条挂 `_Requirements: <模块.功能>` + 验证命令。
- frontmatter 指回本需求书和 `spec_ssot`，不重写设计。
- 嵌入编排注解：`owns_files`、实现者 = Gemini、§8 硬退出。
- 行号 Codex 落地时自己重新核；本需求书行号只作 grounding。
- 不跑 `/kiro:spec-tasks`，避免 clobber。
- 同步输出 Gemini prompt，包含工作区路径、必读文件、RED 测试结果、owns_files/禁止触碰、目标行为、验证命令、回报格式。
- 完整规范见 `docs/development/task-spec-standard.md` §四 4.2。
