# Round 32 正式设计：Post-V2 Engine Rework

## 0. 总览

本设计覆盖 round-32 的 T2/T3/T4，目标是把 v0.3.1 引擎的后 V2 遗留面收束到一个可维护的公共 API、事件流和 predict 执行链。

权威输入以 round-31 `decisions.md` 为准：

- T4 predict 结果必须回到统一 `RunResult`，并用 `source` 区分 run/predict；`PredictResult` 不再作为最终公共结果模型，见 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:86` 到 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:99`。
- 工作区与 run 目录保持 `<workspace_dir>/runs` 语义，见 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:112` 到 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:136`。
- predict cache 与 ABC 由 SDK 拥有，cache key 是 `(phase_id, prompt_hash, input_hash)`；`input_hash` 只基于对应 phase 的 `io.inputs`，见 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:160` 到 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:188`。
- Gateway 只做模型与调用通道，不承载业务编排；Studio 可注入 Copilot callable，但 Gateway 不 import Studio，见 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:287` 到 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:307`。
- Copilot 接口在 Studio，Gateway 通过注入 callable 调用它，见 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:330` 到 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:350`。
- callback inheritance cut 的目标接口是 `event_subscriber(event: CallbackEvent) -> None`，见 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:449` 到 `.kiro/specs/engine-mvp0-rebuild-v030/round-31-api-surface-rightsizing/decisions.md:463`。

本轮是 A 类批准后的工程切换，不再把破坏性 API 变更拆成新的 PM 决策点。实现上可以用短生命周期兼容层降低 PR 风险，但最终公共面必须以本文件的收束结果为准。

### 0.1 当前代码实证摘要

- `run_skill` 当前公共签名仍返回 `WorkflowResult`，并暴露 `mock_llm`、`callbacks`、`model_resolver`，见 `packages/graph-agent/src/graph_agent/core/runner.py:61` 到 `packages/graph-agent/src/graph_agent/core/runner.py:75`；公共 API 测试也把这些参数固化在契约里，见 `packages/graph-agent/tests/test_public_api_contract.py:194` 到 `packages/graph-agent/tests/test_public_api_contract.py:207`。
- `WorkflowResult` 当前字段只有执行通用字段，没有 `source`、`phases`、`path_diff`，见 `packages/graph-agent/src/graph_agent/core/result.py:48` 到 `packages/graph-agent/src/graph_agent/core/result.py:68`。
- 顶层 `graph_agent.__all__` 当前导出 `WorkflowResult` 与 callback 类，见 `packages/graph-agent/src/graph_agent/__init__.py:55` 到 `packages/graph-agent/src/graph_agent/__init__.py:76`。
- 公共 API 指纹测试当前固定 65 个 contract symbols、6 个 vendor-only symbols、12 个 predict internal symbols，见 `packages/graph-agent/tests/test_public_api_contract.py:906` 到 `packages/graph-agent/tests/test_public_api_contract.py:910`。
- `EXPECTED_PREDICT_INTERNAL_SYMBOLS` 当前把 `_predict_internal` 里的 12 个符号固化成测试契约，见 `packages/graph-agent/tests/test_public_api_contract.py:101` 到 `packages/graph-agent/tests/test_public_api_contract.py:114`。
- 当前 `_predict_internal.models` 定义 `GoldenCase`、`PhaseRecord`、`PathDiff`、`PredictResult`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:10` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:52`。
- 当前 SDK 侧 `PredictGatewayChatModel` 是完整 LangChain chat model 拦截实现，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:29` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:180`。
- Gateway 侧 `PredictGatewayChatModel` 当前只是返回 `"predict mock"` 的占位实现，见 `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:15` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:42`。
- Gateway `ModelResolver.resolve` 虽接受 `**kwargs`，但当前直接丢弃，见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:53` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:63`。
- Studio predictor 当前直接 import SDK `_predict_internal` 的模型、策略、diff、tracing callback，见 `apps/studio/backend/app/services/predictor.py:13` 到 `apps/studio/backend/app/services/predictor.py:27`。
- Studio predictor 当前通过 `mock_llm=mock_param` 和 `model_resolver=build_gateway_model_resolver()` 同时调用 `run_skill`，见 `apps/studio/backend/app/services/predictor.py:74` 到 `apps/studio/backend/app/services/predictor.py:82`。
- graph assembler 当前只有 agent phase 传入 callbacks 并发真实 lifecycle 事件；logic phase 与 subgraph phase 没有传入 callbacks，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:169` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:210`。
- `StateMapper.build_phase_input` 当前已经按 phase-local inputs 构造输入，且通过 `filter_runtime_inputs(..., self.input_schema)` 裁剪到当前 phase schema，见 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:44` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:60`。

## 0.5 继承字段与切换表

| 面 | 当前状态 | 实证来源 | round-32 目标 |
| --- | --- | --- | --- |
| `run_skill` | 返回 `WorkflowResult`，参数含 `mock_llm`、`callbacks`、`model_resolver` | `packages/graph-agent/src/graph_agent/core/runner.py:61` 到 `packages/graph-agent/src/graph_agent/core/runner.py:75` | [BREAKING] 返回 `RunResult`；公共事件入口改为 `event_subscriber`；predict 专用入口从 `run_skill` 挪到 `predict_skill` |
| `WorkflowResult` | 字段为 `success/run_id/skill_id/context/metrics/trace_path/error/started_at/finished_at/wall_time_sec` | `packages/graph-agent/src/graph_agent/core/result.py:48` 到 `packages/graph-agent/src/graph_agent/core/result.py:68` | [BREAKING] 新增 canonical `RunResult`；`WorkflowResult` 最多作为短期 alias，不进入最终公共契约 |
| `PredictResult` | `_predict_internal.models.PredictResult` 字段为 `status/phases/path_diff`，其中 `status: Literal["success", "failed"]` | `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:47` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:52` | [BREAKING] 删除最终公共结果模型；predict 结果折入 `RunResult(source="predict")`，`status` 映射到 predict 路径的 `RunResult.success` |
| `PathDiff` | `_predict_internal.models.PathDiff` 字段为 `expected_path/actual_path/missing/extra/order_mismatch` | `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:37` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:44` | 作为 `RunResult.path_diff` 的诊断数据保留语义，类型位置不再由 `_predict_internal` 对外承诺 |
| `PhaseRecord` | `_predict_internal.models.PhaseRecord` 字段为 `phase_name/type/inputs/outputs/mocked_source`，其中 `type: Literal["logic", "llm"]`，`mocked_source` 为 `golden_case/copilot/heuristic_stub/manual` 或 `None` | `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:24` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:31` | 作为 `RunResult.phases` 的 predict 诊断数据保留语义，最终类型纳入 result 或 predict 公共子模型 |
| `GoldenCase` | `_predict_internal.models.GoldenCase` 字段为 `inputs/metadata/expected_traces`，其中 `expected_traces` 是 `phase_name -> expected_output` 映射 | `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:10` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:21` | SDK predict cache 内部模型，不再作为 contract symbol |
| `EXPECTED_PREDICT_INTERNAL_SYMBOLS` | 12 个 `_predict_internal` 符号被测试固化 | `packages/graph-agent/tests/test_public_api_contract.py:101` 到 `packages/graph-agent/tests/test_public_api_contract.py:114` | [BREAKING] 删除该变量和对应测试；不允许把内部 predict implementation 继续做公共指纹 |
| callback 类 | `Callback/LoggingCallback/MetricsCallback/TracingCallback` 在顶层导出 | `packages/graph-agent/src/graph_agent/__init__.py:32` 到 `packages/graph-agent/src/graph_agent/__init__.py:35`；`packages/graph-agent/src/graph_agent/__init__.py:67` 到 `packages/graph-agent/src/graph_agent/__init__.py:70` | [BREAKING] 从公共 API 移除继承式 callback；保留 `CallbackEvent` 数据模型和 `event_subscriber` 函数入口 |
| `CallbackEvent` union | 当前 union 覆盖 run/phase/LLM/tool/model/predict/cache/checkpoint 事件 | `packages/graph-agent/src/graph_agent/callbacks/events.py:450` 到 `packages/graph-agent/src/graph_agent/callbacks/events.py:485` | 保留为事件数据契约；不新增另一套平行事件模型 |
| trace 文件名 | 当前 `TracingCallback` 写 `tracing.jsonl` | `packages/graph-agent/src/graph_agent/callbacks/tracing.py:85` 到 `packages/graph-agent/src/graph_agent/callbacks/tracing.py:111` | [BREAKING] 引擎 trace writer 写 `<workspace_dir>/runs/<run_id>/trace.jsonl`；Studio 与测试同步迁移 |
| phase lifecycle | agent phase 发真实 `PhaseStartEvent/PhaseEndEvent`；runner 在 auto trace 分支补 fake/batch lifecycle | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:389` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:392`；`packages/graph-agent/src/graph_agent/core/runner.py:349` 到 `packages/graph-agent/src/graph_agent/core/runner.py:414` | [BREAKING] lifecycle 从通用 phase wrapper 发出，logic/subgraph/agent 一致；runner 不再补 phase fake/batch 事件 |
| Gateway predict | resolver 用 magic attr 切到 Gateway `PredictGatewayChatModel`，placeholder 返回 `"predict mock"` | `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:97` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:112`；`packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:31` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:42` | [BREAKING] 改为显式 predict context/callable 注入；删除 magic attr 语义 |
| hash helpers | 当前只有 `prompt_hash`、`schema_hash` | `packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py:13` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py:36` | [NEW] 增加 `input_hash`，输入来自 `StateMapper.build_phase_input(...).inputs` 按 phase schema 裁剪后的值 |

## T2. Public API Fingerprint Debt Cleanup

### T2.1 目标

T2 的目标不是把内部实现藏得更深，而是删除已经被测试误固化的内部面。最终公共契约只保留用户应直接依赖的入口、结果模型与事件数据模型：

- `run_skill` 用于真实执行。
- `predict_skill` 用于 predict。
- `RunResult` 统一承载 run 与 predict 结果。
- `CallbackEvent` 及其事件变体作为事件数据契约。
- 不再把 `_predict_internal` 的策略、diff assembler、predict tracing callback、mock chat model 作为公共或半公共符号。

### T2.2 当前状态

当前公共契约测试有三层固化：

- 顶层 contract symbols 固定 `run_skill`、`WorkflowResult`、callback 类和 `_predict_internal` 相关符号，见 `packages/graph-agent/tests/test_public_api_contract.py:16` 到 `packages/graph-agent/tests/test_public_api_contract.py:77`。
- predict internal symbols 单独固定 12 个符号，见 `packages/graph-agent/tests/test_public_api_contract.py:101` 到 `packages/graph-agent/tests/test_public_api_contract.py:114`。
- 测试要求 `_predict_internal` 这些符号仍能被 import，见 `packages/graph-agent/tests/test_public_api_contract.py:991` 到 `packages/graph-agent/tests/test_public_api_contract.py:998`。

这使内部实现无法根据 T4 设计移动到 SDK predict service、Gateway facade 或 result 模型下。

### T2.3 设计

1. 删除 `EXPECTED_PREDICT_INTERNAL_SYMBOLS`。

   `packages/graph-agent/tests/test_public_api_contract.py:101` 到 `packages/graph-agent/tests/test_public_api_contract.py:114` 这组常量与 `packages/graph-agent/tests/test_public_api_contract.py:991` 到 `packages/graph-agent/tests/test_public_api_contract.py:998` 的测试一起删除，而不是改成空集合。原因是内部 predict 符号不应继续拥有一个“为空也算契约”的占位测试面。

2. 更新 `EXPECTED_CONTRACT_SYMBOLS`。

   当前 contract symbol 数量在 `packages/graph-agent/tests/test_public_api_contract.py:906` 到 `packages/graph-agent/tests/test_public_api_contract.py:910` 被硬编码。T2 最终测试应做以下变更：

   - 删除 `WorkflowResult`，新增 `RunResult`。
   - 新增 `predict_skill`。
   - 删除 `Callback`、`LoggingCallback`、`MetricsCallback`、`TracingCallback` 作为顶层公共类。
   - 删除 `_predict_internal` 相关条目。
   - 保留 `CallbackEvent` 及事件变体测试，但测试目标从继承式 callback protocol 改为事件模型与 `event_subscriber` 参数。

3. 收束 12 个 predict internal symbols。

   | 当前符号 | 当前实证 | T2/T4 去向 |
   | --- | --- | --- |
   | `BaseMockStrategy` | `packages/graph-agent/tests/test_public_api_contract.py:40` | SDK predict 内部策略；不 export、不 contract |
   | `MockStrategy` | `packages/graph-agent/tests/test_public_api_contract.py:57` | SDK predict 内部策略；不 export、不 contract |
   | `GoldenCaseStrategy` | `packages/graph-agent/tests/test_public_api_contract.py:48` | SDK predict 内部策略；不 export、不 contract |
   | `HeuristicStubStrategy` | `packages/graph-agent/tests/test_public_api_contract.py:52` | SDK predict 内部策略；不 export、不 contract |
   | `GoldenCase` | `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:10` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:21` | SDK cache/ABC 内部模型 |
   | `PhaseRecord` | `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:24` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:31` | 语义进入 `RunResult.phases`，类型位置从 `_predict_internal` 移出 |
   | `PathDiff` | `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:37` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:44` | 语义进入 `RunResult.path_diff`，类型位置从 `_predict_internal` 移出 |
   | `PredictResult` | `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:47` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:52` | 删除；由 `RunResult(source="predict")` 替代 |
   | `PredictGatewayChatModel` | `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:29` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:180` | 删除 SDK 侧 chat model；Gateway facade 实现 callable bridge |
   | `PredictTracingCallback` | `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:139` | 删除；事件写入由 T3 trace writer 负责，predict 诊断由 `RunResult` 聚合 |
   | `assemble_phase_record` | `packages/graph-agent/tests/test_public_api_contract.py:77` | SDK predict 内部 assembler；不 export、不 contract |
   | `compute_diff` | `packages/graph-agent/tests/test_public_api_contract.py:78` | SDK predict 内部 diff helper；不 export、不 contract |

4. `WorkflowResult` 到 `RunResult`。

   当前 `WorkflowResult` 字段见 `packages/graph-agent/src/graph_agent/core/result.py:48` 到 `packages/graph-agent/src/graph_agent/core/result.py:68`。T4 引入 `RunResult` 时必须覆盖这些已有字段，并新增：

   - `source: Literal["run", "predict"]`。
   - `phases: list[PhaseRecordLike] | None`，用于 predict 诊断。
   - `path_diff: PathDiffLike | None`，用于 predict 与 warning 诊断。

   实现可以在 T4 PR 内短期提供 `WorkflowResult = RunResult` alias 让迁移分步落地，但 T2 最终公共契约、README 与 docs 不再把 `WorkflowResult` 写成 canonical 名称。

### T2.4 代码变更范围

- `packages/graph-agent/src/graph_agent/__init__.py`
  - 移除 callback 类与 `WorkflowResult` 的公共导出。
  - 新增 `RunResult`、`predict_skill` 导出。
- `packages/graph-agent/src/graph_agent/core/result.py`
  - 新增或重命名为 `RunResult`。
  - 保留已有执行字段。
  - 增加 `source/phases/path_diff`。
- `packages/graph-agent/tests/test_public_api_contract.py`
  - 删除 `EXPECTED_PREDICT_INTERNAL_SYMBOLS`。
  - 删除继承式 callback protocol 测试 `EXPECTED_CALLBACK_PROTOCOL_METHODS`，当前定义见 `packages/graph-agent/tests/test_public_api_contract.py:621` 到 `packages/graph-agent/tests/test_public_api_contract.py:679`。
  - 保留并更新 `EXPECTED_CALLBACK_EVENT_VARIANTS`，当前定义见 `packages/graph-agent/tests/test_public_api_contract.py:587` 到 `packages/graph-agent/tests/test_public_api_contract.py:619`。
- docs/spec
  - `docs/engine/mvp0/public-api-contract.md:33` 当前描述 `run_skill` 签名，需改为 `RunResult` 与 `event_subscriber`。
  - `docs/engine/mvp0/public-api-contract.md:38` 当前有 `WorkflowResult` 小节，需迁移为 `RunResult`。
  - `packages/graph-agent/README.md:94`、`packages/graph-agent/README.md:125` 到 `packages/graph-agent/README.md:126`、`packages/graph-agent/README.md:173` 到 `packages/graph-agent/README.md:177` 当前提到 `WorkflowResult`，需同步。

### T2.5 迁移策略

- T2 不能先于 T4 单独合并。因为 `PredictResult` 删除前必须已有 `predict_skill -> RunResult` 替代链。
- 若分 PR，T4 PR 可暂留 `WorkflowResult` alias；T2 PR 删除 alias 的公共测试、文档和导出。
- Studio 侧不得继续 import `_predict_internal`。当前 import 点在 `apps/studio/backend/app/services/predictor.py:13` 到 `apps/studio/backend/app/services/predictor.py:27`、`apps/studio/backend/app/models/runs.py:8` 到 `apps/studio/backend/app/models/runs.py:9`、`apps/studio/backend/app/services/diagnostic_export.py:7`，必须随 T4 迁出后才能做 T2 contract cleanup。

### T2.6 测试

- 更新 `packages/graph-agent/tests/test_public_api_contract.py`：
  - 顶层导出只测最终公共面。
  - `run_skill` 签名测 `event_subscriber`，不测 `callbacks`。
  - `predict_skill` 签名测返回 `RunResult`。
  - `RunResult` 字段覆盖旧 `WorkflowResult` 字段与 `source/phases/path_diff`。
  - 删除 `_predict_internal` import contract 测试。
- 增加一个负向契约测试：`graph_agent.core._predict_internal` 不作为 public API 入口出现在 contract map 中。
- 更新 docs/spec contract map。当前 `packages/graph-agent/spec/contract_map.yaml` 有独立 `PredictResult` 条目，`grep` 实证在 `packages/graph-agent/spec/contract_map.yaml:122`，删除 `PredictResult` 后这条必须迁移或删除；`WorkflowResult` 条目在 `packages/graph-agent/spec/contract_map.yaml:164` 和 `packages/graph-agent/spec/contract_map.yaml:359`，需改为 `RunResult`。

## T3. Trace/Eventstream Callback Inheritance Cut

### T3.1 目标

T3 的目标是删除用户继承 `Callback` 的公共模式，改成数据事件订阅：

```python
def event_subscriber(event: CallbackEvent) -> None:
    ...
```

SDK 内部可以保留事件分发 helper，但公共 API 不再要求用户继承 `Callback`、`LoggingCallback`、`MetricsCallback` 或 `TracingCallback`。

### T3.2 当前状态

- `Callback` 基类当前有多个 legacy hook，如 `on_phase_start`、`on_phase_end`，并在 `on_event` 内分发到 hook，见 `packages/graph-agent/src/graph_agent/callbacks/base.py:38` 到 `packages/graph-agent/src/graph_agent/callbacks/base.py:149`。
- `TracingCallback` 当前写 `tracing.jsonl`，见 `packages/graph-agent/src/graph_agent/callbacks/tracing.py:58` 到 `packages/graph-agent/src/graph_agent/callbacks/tracing.py:113`。
- `_safe_emit_event` 当前接收 callback 列表并调用 `callback.on_event(event)`，见 `packages/graph-agent/src/graph_agent/callbacks/emit.py:11` 到 `packages/graph-agent/src/graph_agent/callbacks/emit.py:21`。
- `run_skill` 与 `_run_v030_skill_dict` 当前都接收 `callbacks`，见 `packages/graph-agent/src/graph_agent/core/runner.py:61` 到 `packages/graph-agent/src/graph_agent/core/runner.py:75`、`packages/graph-agent/src/graph_agent/core/runner.py:316` 到 `packages/graph-agent/src/graph_agent/core/runner.py:326`。
- `_prepare_v030_callbacks` 当前在没有 callbacks 时自动追加 `TracingCallback`，见 `packages/graph-agent/src/graph_agent/core/runner.py:231` 到 `packages/graph-agent/src/graph_agent/core/runner.py:247`。
- runner 当前用 `emit_auto_trace_events = callbacks is None` 判断是否补 fake/batch phase events，见 `packages/graph-agent/src/graph_agent/core/runner.py:337` 到 `packages/graph-agent/src/graph_agent/core/runner.py:414`。
- graph assembler 当前 agent phase 内部发 `PhaseStartEvent`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:389` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:392`；`PhaseEndEvent` 由 `_PhaseEndEmitter` 发出，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:525` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:548`。
- logic phase 与 subgraph phase 当前没有生命周期事件入口，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:169` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:190`。
- Studio 当前用 `StudioQueueCallback(Callback)` 消费事件，见 `apps/studio/backend/app/services/run_manager.py:91` 到 `apps/studio/backend/app/services/run_manager.py:115`；worker 传入 `[StudioQueueCallback(...), TracingCallback(...)]`，见 `apps/studio/backend/app/services/run_manager.py:232` 到 `apps/studio/backend/app/services/run_manager.py:243`。

### T3.3 设计

1. 公共入口改为 `event_subscriber`。

   `run_skill` 新签名包含：

   ```python
   event_subscriber: Callable[[CallbackEvent], None] | None = None
   ```

   `predict_skill` 使用同一事件入口。`callbacks` 从公共签名移除。若内部需要桥接旧代码，可在私有层把 `event_subscriber` 包成 event sink，但不能把 `Callback` 继续导出为用户继承面。

2. 引入私有 event sink。

   内部统一成一个极小接口：

   ```python
   class _EventSink(Protocol):
       def emit(self, event: CallbackEvent) -> None: ...
   ```

   运行时组合两个 sink：

   - `_TraceJsonlSink`：写 `<workspace_dir>/runs/<run_id>/trace.jsonl`。
   - `_SubscriberSink`：如果用户传入 `event_subscriber`，同步调用它。

   当前 `CallbackEvent` union 继续作为数据模型，见 `packages/graph-agent/src/graph_agent/callbacks/events.py:450` 到 `packages/graph-agent/src/graph_agent/callbacks/events.py:485`。

3. trace 文件名切换。

   当前 trace 文件名是 `tracing.jsonl`，由 `TracingCallback` 固定在 `packages/graph-agent/src/graph_agent/callbacks/tracing.py:85`。T3 后引擎写：

   ```text
   <workspace_dir>/runs/<run_id>/trace.jsonl
   ```

   `run_id` 沿用当前 `thread_id or uuid.uuid4()` 语义，见 `packages/graph-agent/src/graph_agent/core/runner.py:334`；目录沿用当前 `trace_output = workspace_dir / "runs" / run_id`，见 `packages/graph-agent/src/graph_agent/core/runner.py:335`。

4. phase lifecycle 从 common wrapper 发出。

   当前 `_wrap_phase_runtime_node` 只做 `StateMapper` 与 `PhaseWrapper` 包装，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:214` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:220`。T3 后这里接收 event sink，并在所有 phase 类型外层统一发：

   - `PhaseStartEvent`
   - phase node 执行
   - `PhaseEndEvent`

   这样 agent、logic、subgraph 都有一致 lifecycle。agent 内部已有的 `PhaseStartEvent` 与 `_PhaseEndEmitter` 迁出或删除，避免重复。

5. subgraph 传递事件 sink。

   当前 child `assemble_graph` 调用没有传 callbacks，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:285` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:293`。T3 后必须把同一个 event sink 传入子图，使 subgraph 内部 phase lifecycle、LLM/tool 事件进入同一 run trace。

6. runner 不再补 fake/batch phase events。

   当前 runner 对无 callbacks 的 auto trace 分支手动补 `RunStartedEvent`、`PhaseStartEvent`、`PhaseEndEvent`、`RunEndedEvent`，见 `packages/graph-agent/src/graph_agent/core/runner.py:349` 到 `packages/graph-agent/src/graph_agent/core/runner.py:414`。T3 后：

   - runner 只负责 `RunStartedEvent` 与 `RunEndedEvent`。
   - phase lifecycle 只由 phase wrapper 发。
   - `emit_auto_trace_events = callbacks is None` 这种分支删除。

7. Studio event queue 改成函数订阅。

   `apps/studio/backend/app/services/run_manager.py:91` 到 `apps/studio/backend/app/services/run_manager.py:115` 的 `StudioQueueCallback` 改为普通函数或闭包：

   ```python
   def emit_to_queue(event: CallbackEvent) -> None:
       ...
   ```

   worker 调用 `run_skill(..., event_subscriber=emit_to_queue, model_resolver=...)`，不再构造 `TracingCallback`。trace 文件由 SDK 默认 sink 写入。

### T3.4 代码变更范围

- `packages/graph-agent/src/graph_agent/core/runner.py`
  - `callbacks` 参数替换为 `event_subscriber`。
  - 删除 `_prepare_v030_callbacks` 或改成 `_prepare_event_sink`。
  - `_save_v030_trace` 迁移到新 trace sink，当前实现位置见 `packages/graph-agent/src/graph_agent/core/runner.py:257` 到 `packages/graph-agent/src/graph_agent/core/runner.py:270`。
- `packages/graph-agent/src/graph_agent/callbacks/`
  - `events.py` 保留。
  - `base.py`、`tracing.py`、`logging.py`、`metrics.py` 从公共 API 移出；可短期保留私有兼容实现，但不从 `graph_agent.__all__` 导出。
  - `emit.py` 改为 event sink emit helper。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `assemble_graph` 签名从 `callbacks` 改为 event sink 或 subscriber 透传。
  - `_wrap_phase_runtime_node` 统一发 lifecycle。
  - `_build_subgraph_node` 把 event sink 传给 child graph。
  - `_build_skill_node` 保留 LLM/tool 事件，移除 phase start/end。
- Studio backend
  - `apps/studio/backend/app/services/run_manager.py` 改掉 `StudioQueueCallback` 继承和 `TracingCallback` 构造。
  - `apps/studio/backend/app/services/predictor.py:74` 到 `apps/studio/backend/app/services/predictor.py:82` 仍在 predict 路径调用 `run_skill(..., callbacks=[tracing_callback])`，PR-1 必须先过渡为 `event_subscriber` 调用；PR-2 再整体改成 `predict_skill`。
  - `apps/studio/backend/app/services/run_manager.py:277` 当前 touch `tracing.jsonl`，需改成 `trace.jsonl`。
  - `apps/studio/backend/app/services/run_manager.py:426` 当前读取 `tracing.jsonl`，需改成 `trace.jsonl`。

### T3.5 迁移策略

- 第一阶段可以保留 `callbacks` 作为私有参数只供内部测试桥接，但公共 `run_skill`/`predict_skill` 不接受它；生产 caller 不能依赖该私有桥接。
- PR-1 必须同时迁移两个 Studio `callbacks=` caller：`apps/studio/backend/app/services/run_manager.py:238` 和 `apps/studio/backend/app/services/predictor.py:81`。否则 PR-1 删除 public `run_skill(callbacks=...)` 后、PR-2 尚未引入 `predict_skill` 前，predict endpoint 会因 `TypeError` 红 CI。
- Studio 与 tests 同 PR 迁移到 `trace.jsonl`，避免同时支持两个文件名造成新旧 trace 语义混杂。
- 对旧文档中的 `tracing.jsonl` 做一次性替换。已知测试点包括：
  - `apps/studio/tests-e2e/test_run_flow.py:79` 与 `apps/studio/tests-e2e/test_run_flow.py:89`。
  - `packages/graph-agent/tests/runner/test_v030_trace_auto_attach.py:110`。
  - `packages/graph-agent/tests/core/test_workspace_dir_contract_red.py:149`。
  - `apps/studio/backend/tests/test_api.py:397` 与 `apps/studio/backend/tests/test_api.py:763`。

### T3.6 测试

- SDK runner tests：
  - 无 `event_subscriber` 时仍写 `<workspace_dir>/runs/<run_id>/trace.jsonl`。
  - 有 `event_subscriber` 时 subscriber 收到 `RunStartedEvent`、每个 phase 的 start/end、LLM/tool 事件、`RunEndedEvent`。
  - logic phase 与 subgraph phase 都必须有 `PhaseStartEvent/PhaseEndEvent`。
- public API contract：
  - `run_skill` 不含 `callbacks`。
  - `run_skill` 含 `event_subscriber`。
  - 不再测试 `Callback` protocol methods。
- Studio backend tests：
  - run detail 从 `trace.jsonl` 读取。
  - queue event 仍能驱动状态更新。
- E2E：
  - 原 `tracing.jsonl` 断言全部改成 `trace.jsonl`。

## T4. Predict/Cache/Gateway Copilot Rework

### T4.1 目标

T4 的目标是把 predict 从“通过 `mock_llm` 注入 run_skill 的旁路模式”改成正式的 SDK predict 执行链：

- 新增 `predict_skill`。
- predict 返回 `RunResult(source="predict")`。
- SDK 拥有 predict strategy、golden case/cache、phase diff 与 RunResult 聚合。
- Gateway 只做模型 facade，并通过注入 callable 调 Studio Copilot。
- Studio 不再 import `graph_agent.core._predict_internal`。
- cache key 使用 `(phase_id, prompt_hash, input_hash)`，其中 `input_hash` 基于 phase-local `io.inputs`。

### T4.2 当前状态

- `run_skill` 暴露 `mock_llm`，见 `packages/graph-agent/src/graph_agent/core/runner.py:622`。
- `_run_v030_skill_dict` 当前在 `mock_llm` 存在时把 `chat_model` 设为 mock，并禁用 `model_resolver`，见 `packages/graph-agent/src/graph_agent/core/runner.py:655` 到 `packages/graph-agent/src/graph_agent/core/runner.py:656`。
- `assemble_graph` 当前同时接收 `chat_model` 与 `model_resolver`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:88` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:100`。
- `_resolve_phase_chat_model` 当前如果 `chat_model is not None` 或 `model_resolver is None` 就直接返回 `chat_model`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:581` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:591`。
- Studio predictor 当前构造 mock strategy 并传给 `run_skill(mock_llm=mock_param, model_resolver=build_gateway_model_resolver())`，见 `apps/studio/backend/app/services/predictor.py:66` 到 `apps/studio/backend/app/services/predictor.py:82`。
- Studio gateway resolver 工厂当前只接收 `roles_path`，见 `apps/studio/backend/app/services/gateway_resolver.py:15` 到 `apps/studio/backend/app/services/gateway_resolver.py:21`。
- Gateway resolver 当前通过 magic attr `_graph_agent_predict_mock_strategy` 切换 predict，见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:97` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:112`。
- Gateway predict chat model 当前不调 callable，只返回固定 `"predict mock"`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:31` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:42`。
- `hash.py` 当前只有 `prompt_hash`、`schema_hash`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py:13` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py:36`。

### T4.3 设计

1. 新增 `predict_skill`。

   公共形态与 `run_skill` 对齐：

   ```python
   def predict_skill(
       skill_path: str | Path,
       *,
       workspace_dir: str | Path,
       thread_id: str | None = None,
       unattended: bool = True,
       event_subscriber: Callable[[CallbackEvent], None] | None = None,
       skill_resolver: SkillResolver | None = None,
       model_resolver: ModelResolverProtocol | None = None,
       copilot_predict: CopilotPredictCallable | None = None,
       **inputs: Any,
   ) -> RunResult:
       ...
   ```

   `copilot_predict` 是 SDK 到 Gateway 再到 Studio Copilot 的 per-run callable 注入点。若 CLI 或测试环境没有 Copilot，可传 `None`，由 SDK predict strategy 选择 cache/golden/heuristic fallback。该 fallback 仍是 SDK predict 内部策略，不进入 public API。

2. `RunResult` 统一结果模型。

   `RunResult` 覆盖当前 `WorkflowResult` 的执行字段，见 `packages/graph-agent/src/graph_agent/core/result.py:48` 到 `packages/graph-agent/src/graph_agent/core/result.py:68`，并新增：

   ```python
   source: Literal["run", "predict"]
   phases: list[PhaseRecordLike] | None = None
   path_diff: PathDiffLike | None = None
   ```

   对真实 `run_skill`，`source="run"`，`phases/path_diff` 通常为 `None`。对 `predict_skill`，`source="predict"`，`phases/path_diff` 承载当前 `PredictResult` 的诊断能力。当前 `PredictResult` 字段是 `status/phases/path_diff`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:47` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:52`；其中 `status: Literal["success", "failed"]` 是用户可见的 predict 成功/失败判定。迁移到 `RunResult` 后，predict 路径的 `RunResult.success` 必须由 `path_diff` 派生：当 `path_diff.missing`、`path_diff.extra` 或 `path_diff.order_mismatch` 任一为真时为失败，否则为成功；当前 Studio 判定逻辑实证见 `apps/studio/backend/app/services/predictor.py:99` 到 `apps/studio/backend/app/services/predictor.py:109`。

3. SDK 拥有 predict 编排。

   当前 Studio predictor 负责调 `_predict_internal` 的 strategy、diff、phase record 与 tracing，见 `apps/studio/backend/app/services/predictor.py:13` 到 `apps/studio/backend/app/services/predictor.py:27`。T4 后这些职责移入 SDK：

   - manifest/phase 展开。
   - phase input 裁剪。
   - cache lookup/write。
   - golden case selection。
   - Copilot fallback request 构造。
   - trace event 与 `RunResult` 聚合。

   Studio predictor 只负责：

   - 解析 API request。
   - 准备 `workspace_dir`，当前 helper 是 `workspace_dir_for(skill_dir)`，见 `apps/studio/backend/app/services/skills.py:768` 到 `apps/studio/backend/app/services/skills.py:769`。
   - 提供 Copilot callable。
   - 调用 `predict_skill(...)`。
   - 返回 `RunResult.model_dump(mode="json")`。

4. Gateway callable bridge。

   `ModelResolverProtocol.resolve` 当前接受 `**kwargs`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:14` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:23`；实现却 `del kwargs`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:53` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:63`。T4 后显式增加 typed predict 参数，例如：

   ```python
   def resolve(
       self,
       role: str,
       *,
       callbacks: list[Any] | None = None,
       phase_name: str | None = None,
       predict_context: PredictContext | None = None,
   ) -> BaseChatModel:
       ...
   ```

   如果 `predict_context` 存在，resolver 返回 Gateway `PredictGatewayChatModel`，该 model 在 `_generate` 中调用 `predict_context.copilot_predict(request)`。Gateway 不 import Studio。Studio 通过 `build_gateway_model_resolver(..., copilot_predict=...)` 或 per-call `predict_context` 提供 callable。

5. 删除 magic attr。

   当前 SDK `bind_predictor` 写 `_graph_agent_predict_mock_strategy`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/__init__.py:15` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/__init__.py:22`；Gateway resolver 再读该 attr，见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:97`。T4 后删除这个隐式协议，改用显式 `predict_context`。

6. `mock_llm` 退出公共 predict 路径。

   当前 `_run_v030_skill_dict` 用 `mock_llm` 覆盖 `chat_model` 并禁用 resolver，见 `packages/graph-agent/src/graph_agent/core/runner.py:655` 到 `packages/graph-agent/src/graph_agent/core/runner.py:656`。T4 后 predict 不能再依赖这个路径，因为它绕过 Gateway/Copilot callable。`mock_llm` 从公共 run/predict 签名删除；如果测试仍需要，只能降级为私有 test-only helper。公共 `predict_skill` 不传 `mock_llm`，因此进入 graph assembler 时 `chat_model` 恒为 `None`，`_resolve_phase_chat_model` 现有 `if chat_model is not None or model_resolver is None: return chat_model` 短路不会触发；该短路无需删除，只需在调用 `model_resolver.resolve(...)` 时透传 `predict_context`。当前短路实证见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:581` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:591`。

7. cache key 与 `input_hash`。

   新增 `input_hash(value: Mapping[str, Any]) -> str`，语义是稳定 JSON canonicalization 后 hash。输入必须来自当前 phase 的 schema 裁剪结果：

   - `PhaseIOSchema.inputs` 定义在 `packages/graph-agent/src/graph_agent/core/manifest.py:31` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:37`。
   - `StateMapper.build_phase_input` 当前已经调用 `filter_runtime_inputs(_phase_local_inputs(...), self.input_schema)`，见 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:44` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:60`。
   - `_phase_local_inputs` 当前把 root inputs 与已完成 phase outputs 合并，见 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:94` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:102`。

   因此 T4 的 cache 逻辑应复用同一 phase input 生成路径，避免用全局 run inputs 生成 `input_hash`。逻辑 key 按决策为：

   ```text
   (phase_id, prompt_hash, input_hash)
   ```

   存储层可以按 `skill_id` 或 workspace namespace 分目录，但不改变逻辑 key。

8. trace 与 predict event。

   `predict_skill` 使用 T3 的 event sink。predict cache hit/miss、Copilot fallback、phase diagnostics 继续用 `CallbackEvent` 体系内已有 predict/cache/model 事件；不要创建第二套 Studio-only 事件模型。

### T4.4 代码变更范围

- SDK
  - `packages/graph-agent/src/graph_agent/core/runner.py`：新增 `predict_skill` 或把 shared runner 抽成 private `_execute_skill(mode=...)`。
  - `packages/graph-agent/src/graph_agent/core/result.py`：新增 `RunResult`。
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`：`assemble_graph` 接收并透传 `predict_context`；`_resolve_phase_chat_model` 保留 `chat_model is not None` 短路，但 predict 路径保证 `chat_model=None`，并把 `predict_context` 传给 resolver。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/`：改成纯内部目录；移除 `__all__` 的 public 语义；删除 SDK 侧 `PredictGatewayChatModel`。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py`：新增 `input_hash`。
  - tasks 阶段确认 SDK 内部 3 处嵌套 `run_skill` 调用的返回类型同步和 trace 范围：
    - `packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:306` 已在 PR-1 从嵌套 `callbacks=callbacks` 迁到 `event_subscriber=_legacy_callback_subscriber(callbacks)`；PR-2 需决定保留该 legacy 桥，还是把 nested sub-run 统一透传到 `event_subscriber` / 同一条 trace，并随 `WorkflowResult` -> `RunResult` 同步返回值形状。
    - `packages/graph-agent/src/graph_agent/core/skill_tool_factory.py:110` 与 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:578` 当前不传 `callbacks` / `event_subscriber`，不受 PR-1 删除 public `callbacks` 参数直接影响；但 PR-2 的 `WorkflowResult` -> `RunResult` 改动仍需同步这两处 caller 的 dict 式 result 消费。
    - 这 3 处都依赖 dict-shaped result：`parallel_map` 把 nested `run_skill` 返回值 `model_dump()` 后作为 `list[dict]` 元素返回，`skill_tool_factory` 用 `result.get("context", {}).get("final_output")`，`md_to_json` 用 `result["context"]["final_results"]`。因此 `RunResult` 设计 / 兼容层必须明确支持或迁移这些 dict 式取值。
- Gateway
  - `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py`：显式声明 `predict_context`。
  - `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`：删除 magic attr；消费 `predict_context`。
  - `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py`：把 placeholder `_generate` 替换为 callable bridge。
- Studio
  - `apps/studio/backend/app/services/gateway_resolver.py`：支持 Copilot callable 注入或 per-call predict context。
  - `apps/studio/backend/app/services/predictor.py`：删除 `_predict_internal` imports；调用 SDK `predict_skill`。
  - `apps/studio/backend/app/models/runs.py`：删除对 `_predict_internal.models` 的导入，改用 SDK public result/diagnostic schema 或本地 API response model。
  - `apps/studio/backend/app/services/diagnostic_export.py`：从 `PredictResult` 改为 `RunResult(source="predict")`。

### T4.5 迁移策略

- 先在 SDK 内引入 `RunResult` 与 `predict_skill`，保留旧 Studio predictor 不动，跑 SDK tests。
- 再切 Studio predictor 到 `predict_skill`，删除 Studio 对 `_predict_internal` 的 imports。
- 再切 Gateway callable bridge，删除 magic attr。
- 最后由 T2 删除 public API 指纹里的 `_predict_internal` 依赖。

这一路径避免在没有替代 API 时先删除 `PredictResult`，也避免 Studio 在中间状态同时维护两套 predict 结果模型。

### T4.6 测试

- SDK predict tests：
  - `predict_skill` 返回 `RunResult(source="predict")`。
  - `run_skill` 返回 `RunResult(source="run")`。
  - `PredictResult` 不再是 public contract。
  - `input_hash` 只随 phase `io.inputs` 变化；无关 root inputs 不改变同一 phase 的 cache key。
  - cache hit 不调用 Copilot callable；cache miss 调用一次。
- Gateway tests：
  - `resolve(..., predict_context=...)` 返回 predict chat model。
  - predict chat model `_generate` 调 injected callable。
  - `predict_context=None` 时仍返回普通 `GatewayChatModel`。
  - resolver 不再识别 `_graph_agent_predict_mock_strategy` magic attr。
- Studio backend tests：
  - `/runs/{id}/predict` 或现有 predict endpoint 返回 `RunResult` JSON。
  - predict 路径的 `RunResult.success` 覆盖 path diff 成功/失败：`missing/extra/order_mismatch` 任一存在时为 false。
  - predictor service 不 import `_predict_internal`。
  - diagnostic export 接受 `RunResult(source="predict")`。
- Integration/E2E：
  - predict run 写 `trace.jsonl`。
  - Copilot callable 路径与 cache fallback 路径都覆盖。

## 1. 关键决策

1. `RunResult` 是最终公共结果名。

   `WorkflowResult` 当前是事实公共名，但 round-31 已决定 predict 回到 `RunResult`。本轮允许短期 alias，但不允许最终 contract、README、docs 继续把 `WorkflowResult` 作为 canonical。

2. `PredictResult` 删除，不做 public alias。

   当前 `PredictResult` 只在 `_predict_internal` 模块中定义，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:47` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:52`。它的能力通过 `RunResult(source="predict")` 保留，名称不保留。

3. `CallbackEvent` 保留，`Callback` 继承删除。

   删除继承式 callback 不等于删除事件模型。`CallbackEvent` union 是现有数据契约，见 `packages/graph-agent/src/graph_agent/callbacks/events.py:450` 到 `packages/graph-agent/src/graph_agent/callbacks/events.py:485`，T3 只替换消费接口。

4. phase lifecycle 必须由 common wrapper 发出。

   当前 agent/logic/subgraph lifecycle 不一致，runner 又补 fake/batch events。最终设计只有一个 phase lifecycle 来源：phase runtime wrapper。这样 trace、Studio queue、predict diagnostics 才能对所有 phase 类型一致。

5. Gateway callable 必须显式注入。

   Magic attr `_graph_agent_predict_mock_strategy` 是临时协议，当前 SDK 写入点见 `packages/graph-agent/src/graph_agent/core/_predict_internal/__init__.py:15` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/__init__.py:22`，Gateway 读取点见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:97`。T4 删除它，改用 typed `predict_context`。

6. `input_hash` 必须基于 phase-local schema inputs。

   不能用全局 run inputs 直接 hash。实证上 `StateMapper.build_phase_input` 已经提供当前 phase 裁剪后的输入路径，见 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:44` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:60`。

## 2. 最终 PR 顺序与依赖

### PR-1：T3 eventstream/trace substrate

依赖：无，优先做。

内容：

- `callbacks` 公共参数改为 `event_subscriber`。
- 新 trace sink 写 `trace.jsonl`。
- phase lifecycle 移到 common wrapper。
- Studio run queue 改成函数订阅。
- Studio predictor 的临时 `run_skill` 调用也在 PR-1 内从 `callbacks=[tracing_callback]` 过渡到 `event_subscriber`，避免 PR-1/PR-2 之间断档。
- 所有 `tracing.jsonl` 测试改为 `trace.jsonl`。

风险控制：

- 这一 PR 不碰 predict 结果模型。
- 保留 `CallbackEvent` schema，减少前端和 Studio backend 事件解析变更。

### PR-2：T4 predict_skill/RunResult/Gateway callable

依赖：PR-1。

内容：

- 引入 `RunResult`。
- 新增 `predict_skill`。
- SDK 接管 predict cache/ABC/diff 聚合。
- Gateway resolver 支持 typed `predict_context`。
- Gateway `PredictGatewayChatModel` 调用 injected Copilot callable。
- Studio predictor 迁移到 `predict_skill`，删除 `_predict_internal` imports。

风险控制：

- 可在 PR 内短期保留 `WorkflowResult = RunResult` alias。
- 不在此 PR 删除全部 public API 指纹测试，只更新必要断言让实现可跑通。

### PR-3：T2 public API contract cleanup

依赖：PR-2。

内容：

- 删除 `EXPECTED_PREDICT_INTERNAL_SYMBOLS` 与对应 import contract 测试。
- 删除 public callback inheritance contract。
- 顶层导出收束到 `run_skill/predict_skill/RunResult/CallbackEvent` 等最终公共面。
- README、docs、spec contract map 从 `WorkflowResult/PredictResult/tracing.jsonl/callbacks` 迁到最终术语。

风险控制：

- 只做 contract 和文档清理，不再改 predict 主链。
- 若 PR-2 的 alias 已存在，本 PR 删除 public alias 或至少从 `__all__` 和 contract map 移除。

## 3. 完成标准

- `rg -n "EXPECTED_PREDICT_INTERNAL_SYMBOLS|PredictResult|WorkflowResult|tracing\.jsonl|callbacks=" packages apps docs .kiro/specs/engine-mvp0-rebuild-v030` 不再命中任何最终公共面引用；测试 fixture 或历史 round 文档例外需用路径白名单解释。
- `run_skill` 与 `predict_skill` 均返回 `RunResult`。
- Studio backend 不再 import `graph_agent.core._predict_internal`。
- Gateway resolver 不再读取 `_graph_agent_predict_mock_strategy`。
- predict cache key 有测试证明只由 `(phase_id, prompt_hash, input_hash)` 决定。
- trace 文件统一为 `<workspace_dir>/runs/<run_id>/trace.jsonl`。
