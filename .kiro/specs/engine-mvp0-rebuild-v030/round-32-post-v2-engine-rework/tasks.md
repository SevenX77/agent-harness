# Round 32 Tasks: Post-V2 Engine Rework

## 0. 执行约束

- PR 顺序固定：PR-1 T3 tracing/event_subscriber -> PR-2 T4 predict+cache/Gateway -> PR-3 T2 指纹基线对账。
- 每个 PR 第一项必须先写 failing tests，标 `[TESTS-FIRST]`。
- 本轮所有 `[BREAKING]` 均继承 design §0.5，属于 V0.3.0 charter 已批准 cutover；task 内列迁移路径，不再追加 PM 拍板。
- 签名变更必须同 PR 迁移 caller。PR-1 必须迁移 `apps/studio/backend/app/services/run_manager.py:238` 与 `apps/studio/backend/app/services/predictor.py:81`；SDK 内部 3 处 `run_skill` 调用在 PR-1/PR-2 任务中同步确认。
- PR-1 选择工程上更干净的独立可绿策略：PR-1 内先把 `predictor.py` 的临时 `run_skill(callbacks=...)` 过渡到 `event_subscriber`，PR-2 再整体改成 `predict_skill`。
- Studio 前端不在 round-32 修改范围；predict endpoint 的前端 JSON 契约必须由 backend 保形 adapter 维持为 `PredictDiagnosticExport` 形态。

## PR-1: T3 tracing/event_subscriber substrate

### Task PR1-1 [TESTS-FIRST] 写 event_subscriber + trace.jsonl + 单一 lifecycle 红灯测试

Files:

- Modify:
  - `packages/graph-agent/tests/runner/test_v030_trace_auto_attach.py:110`：把 trace 文件期望从 `tracing.jsonl` 改为 `trace.jsonl`，新增 `event_subscriber` 收到 run/phase/LLM/tool 事件的断言。
  - `packages/graph-agent/tests/runner/test_v030_trace_auto_attach.py:133`：覆盖无 subscriber 也自动落盘 `trace.jsonl`。
  - `packages/graph-agent/tests/runner/test_v030_trace_auto_attach.py:153`：断言所有 phase 类型都有真实 start/end，且 runner 不再批量预发假 lifecycle。
  - `packages/graph-agent/tests/runner/test_v030_trace_auto_attach.py:202`、`packages/graph-agent/tests/runner/test_v030_trace_auto_attach.py:220`：崩溃路径仍写 `trace.jsonl`。
  - `packages/graph-agent/tests/core/test_workspace_dir_contract_red.py:149`：workspace contract 改为 `<workspace_dir>/runs/<run_id>/trace.jsonl`。
  - `packages/graph-agent/tests/test_public_api_contract.py:194` 到 `packages/graph-agent/tests/test_public_api_contract.py:207`：`run_skill` 签名红灯改为 `event_subscriber`，不再接受 public `callbacks`。
  - `apps/studio/backend/tests/test_api.py:397`、`apps/studio/backend/tests/test_api.py:763`：Studio backend trace 文件名改为 `trace.jsonl`。
  - `apps/studio/tests-e2e/test_run_flow.py:79`、`apps/studio/tests-e2e/test_run_flow.py:89`：E2E trace 文件名改为 `trace.jsonl`。
- Delete:
  - 文件内删除/改写旧 `tracing.jsonl` 断言，不删除测试文件。
- New:
  - 可新增 `packages/graph-agent/tests/runner/test_event_subscriber_cutover.py`，专门覆盖 subscriber 函数、logic/subgraph lifecycle、无重复 phase 事件。

依赖:

- 无前置 task。

验收标准:

- 先红：旧实现仍写 `tracing.jsonl`、`callbacks` 仍在签名中、logic/subgraph lifecycle 缺失，新增测试必须失败。
- 目标绿：SDK runner tests、public API signature test、Studio backend trace tests、E2E trace path tests 全部通过。

### Task PR1-2 [BREAKING] 将 public `run_skill(callbacks=...)` 切到 `event_subscriber`

建议 commit prefix: `feat()!`

Files:

- Modify:
  - `packages/graph-agent/src/graph_agent/core/runner.py:61` 到 `packages/graph-agent/src/graph_agent/core/runner.py:75`：public `run_skill` 参数从 `callbacks` 改为 `event_subscriber`，返回类型暂仍可沿用当前实现，PR-2 再统一到 `RunResult`。
  - `packages/graph-agent/src/graph_agent/core/runner.py:316` 到 `packages/graph-agent/src/graph_agent/core/runner.py:326`：`_run_v030_skill_dict` 接收 event sink/subscriber，不再暴露 public `callbacks`。
  - `packages/graph-agent/src/graph_agent/core/runner.py:231` 到 `packages/graph-agent/src/graph_agent/core/runner.py:247`：`_prepare_v030_callbacks` 改为私有 event sink 准备逻辑。
  - `packages/graph-agent/src/graph_agent/core/runner.py:257` 到 `packages/graph-agent/src/graph_agent/core/runner.py:270`：`_save_v030_trace` 迁移到新 trace sink。
  - `packages/graph-agent/src/graph_agent/callbacks/events.py:450` 到 `packages/graph-agent/src/graph_agent/callbacks/events.py:485`：保留 `CallbackEvent` union 作为 subscriber 数据契约。
  - `packages/graph-agent/src/graph_agent/callbacks/emit.py:11` 到 `packages/graph-agent/src/graph_agent/callbacks/emit.py:21`：从 callback list dispatch 改为 event sink emit helper 或私有兼容桥。
  - `packages/graph-agent/src/graph_agent/callbacks/base.py:38` 到 `packages/graph-agent/src/graph_agent/callbacks/base.py:149`：继承式 callback 降级为内部兼容，不再作为 public extension 入口。
  - `packages/graph-agent/src/graph_agent/callbacks/tracing.py:58` 到 `packages/graph-agent/src/graph_agent/callbacks/tracing.py:113`：trace 写入逻辑迁移到 `<workspace_dir>/runs/<run_id>/trace.jsonl`。
- Delete:
  - 文件内删除 public `callbacks` 参数语义；不删除 `CallbackEvent` 模型。
- New:
  - 可新增私有 `_TraceJsonlSink` / `_SubscriberSink` 模块或类，位置由实现选择，但不得成为 public API。

依赖:

- 依赖 PR1-1 红灯测试。

迁移路径:

- 用户继承 `Callback` 的入口迁到 `event_subscriber(event: CallbackEvent) -> None`。
- PR-1 结束后生产代码不得再调用 public `run_skill(callbacks=...)`。

验收标准:

- `run_skill` public 签名包含 `event_subscriber`，不包含 public `callbacks`。
- 无 subscriber 时仍自动写 `<workspace_dir>/runs/<run_id>/trace.jsonl`。
- 有 subscriber 时事件同步进入 subscriber，trace 文件也保留。

### Task PR1-3 [BREAKING] 将 phase lifecycle 收敛到 common wrapper，删除 runner fake/batch phase 事件

建议 commit prefix: `feat()!`

Files:

- Modify:
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:214` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:220`：`_wrap_phase_runtime_node` 接收 event sink 并统一发 `PhaseStartEvent` / `PhaseEndEvent`。
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:169` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:190`：logic/subgraph phase 也进入 common lifecycle wrapper。
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:285` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:293`：child `assemble_graph` 透传同一个 event sink。
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:389` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:392`：移除 agent phase 内部重复 `PhaseStartEvent`。
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:525` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:548`：移除或改造 `_PhaseEndEmitter`，避免与 common wrapper 双发。
  - `packages/graph-agent/src/graph_agent/core/runner.py:334` 到 `packages/graph-agent/src/graph_agent/core/runner.py:335`：保留 run_id 与 run_dir 语义。
  - `packages/graph-agent/src/graph_agent/core/runner.py:337` 到 `packages/graph-agent/src/graph_agent/core/runner.py:414`：删除 `emit_auto_trace_events` 触发的 fake/batch phase start/end；runner 只发 run start/end。
- Delete:
  - 文件内删除 runner 批量预发所有 phase start/end 的逻辑。
- New:
  - 无强制新增文件。

依赖:

- 依赖 PR1-2 的 event sink/subscriber 基础。

迁移路径:

- 事件消费者仍读 `CallbackEvent`，但 phase lifecycle 来源从 runner/agent 双源迁为 common wrapper 单源。

验收标准:

- logic、agent、subgraph phase 都有 start/end。
- 同一 phase 不重复出现 runner fake 与真实 node lifecycle。
- subgraph 内 phase 事件进入同一 run trace。

### Task PR1-4 [BREAKING] 同 PR 迁移所有 PR-1 受影响 caller，避免 PR-1/PR-2 断档

建议 commit prefix: `feat()!`

Files:

- Modify:
  - `apps/studio/backend/app/services/run_manager.py:91` 到 `apps/studio/backend/app/services/run_manager.py:115`：`StudioQueueCallback(Callback)` 改为普通函数或闭包 subscriber。
  - `apps/studio/backend/app/services/run_manager.py:232` 到 `apps/studio/backend/app/services/run_manager.py:243`：`run_skill(..., callbacks=callbacks)` 改为 `event_subscriber=emit_to_queue`，不再构造 `TracingCallback`。
  - `apps/studio/backend/app/services/run_manager.py:277`：touch `trace.jsonl`。
  - `apps/studio/backend/app/services/run_manager.py:426`：读取 `trace.jsonl`。
  - `apps/studio/backend/app/services/predictor.py:74` 到 `apps/studio/backend/app/services/predictor.py:82`：PR-1 内先把临时 predict `run_skill(..., callbacks=[tracing_callback])` 过渡成 `event_subscriber`；PR-2 再替换为 `predict_skill`。
  - `packages/graph-agent/src/graph_agent/core/skill_tool_factory.py:110`：确认内部 `run_skill` caller 不依赖 public `callbacks`。
  - `packages/graph-agent/src/graph_agent/tools/md_to_json.py:578`：确认内部 `run_skill` caller 不依赖 public `callbacks`。
  - `packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:306` 与 `packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:309`：把 nested `run_skill` 的 `callbacks` 透传迁为 `event_subscriber` 或私有 event sink。
- Delete:
  - 文件内删除生产 caller 的 public `callbacks=` 调用。
- New:
  - 无。

依赖:

- 依赖 PR1-2。
- PR-1 必须独立可绿；若无法在 PR-1 过渡 `apps/studio/backend/app/services/predictor.py:81`，则 PR-1 与 PR-2 必须捆绑合并，不能单独进主干。

迁移路径:

- Studio run queue：`Callback` 子类 -> subscriber 函数。
- Studio predict 临时路径：`PredictTracingCallback` callback list -> subscriber 适配，PR-2 再删除 `_predict_internal` 依赖。
- SDK nested run：确认 `event_subscriber` 是否进入同一条 trace，tasks 阶段记录实现选择。

验收标准:

- `rg -n "run_skill\\(.*callbacks=|callbacks=\\[tracing_callback\\]" apps/studio/backend/app/services packages/graph-agent/src/graph_agent/core packages/graph-agent/src/graph_agent/tools` 不再命中生产 public caller。
- Studio run detail 与 predict endpoint 在 PR-1 后不因 `callbacks` 参数删除而 TypeError。

### Task PR1-5 PR-1 验证与 release notes

Files:

- Modify:
  - `docs/engine/public-api-contract.md:33`：可在 PR-1 先记录 `event_subscriber` 的 run signature，最终术语在 PR-3 收束。
  - `apps/studio/tests-e2e/test_run_flow.py:6`：更新 trace 文件名说明。
  - `packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:22`、`packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:107`：如果 PR-1 改 nested trace 透传，更新注释中的 `tracing.jsonl`。
- Delete:
  - 文件内旧 `tracing.jsonl` 说明。
- New:
  - 无。

依赖:

- 依赖 PR1-1 到 PR1-4。

验收标准:

- `rg -n "tracing\\.jsonl" packages apps` 只允许历史/兼容注释命中，新增 PR-1 改动范围不再使用旧文件名。
- PR-1 测试集合通过：SDK runner tests、Studio backend tests、E2E touched trace tests。

## PR-2: T4 predict_skill / RunResult / cache / Gateway callable

### Task PR2-1 [TESTS-FIRST] 写 predict_skill + RunResult + Gateway callable + input_hash 红灯测试

Files:

- Modify:
  - `packages/graph-agent/tests/test_public_api_contract.py:194` 到 `packages/graph-agent/tests/test_public_api_contract.py:207`：先红要求 `predict_skill(..., event_subscriber=None) -> RunResult`，并要求 public `run_skill` 签名不再包含 `mock_llm`。
  - `packages/graph-agent/tests/test_public_api_contract.py:566`：先红要求 `RunResult` 覆盖旧 `WorkflowResult` 字段并新增 `source/phases/path_diff`。
  - `apps/studio/backend/tests/test_api.py:397`、`apps/studio/backend/tests/test_api.py:763`：补 predict 内部使用 `RunResult(source="predict")`、endpoint 对外仍返回 `PredictDiagnosticExport` JSON 形态、trace 文件路径断言。
- Delete:
  - 文件内旧 `PredictResult` 结果断言。
- New:
  - `packages/graph-agent/tests/predict/test_predict_skill_run_result.py`：覆盖 `predict_skill` 返回 `RunResult(source="predict")`、`RunResult.success` 由 `path_diff.missing/extra/order_mismatch` 派生。
  - `packages/graph-agent/tests/predict/test_input_hash_cache_key.py`：覆盖 `(phase_id, prompt_hash, input_hash)`，且 `input_hash` 只随 phase `io.inputs` 变化。
  - `packages/graph-agent-gateway/tests/test_predict_callable_bridge.py`：覆盖 `resolve(..., predict_context=...)` 返回 predict chat model 并调用 injected callable。
  - `apps/studio/backend/tests/test_predict_skill_integration.py`：覆盖 Studio predictor 调 SDK `predict_skill`，不再 import `_predict_internal`。

依赖:

- 依赖 PR-1 完成，尤其 `event_subscriber` 和 `trace.jsonl` substrate。

验收标准:

- 先红：当前无 `RunResult`、无 `predict_skill`、public `run_skill` 仍含 `mock_llm`、Gateway placeholder 只返回 `"predict mock"`、`input_hash` 缺失。
- 目标绿：新增 SDK/Gateway/Studio predict tests 全部通过。

### Task PR2-2 [BREAKING] 引入 canonical `RunResult` 与 public `predict_skill`

建议 commit prefix: `feat()!`

Files:

- Modify:
  - `packages/graph-agent/src/graph_agent/core/result.py:48` 到 `packages/graph-agent/src/graph_agent/core/result.py:68`：新增 canonical `RunResult`，覆盖旧 `WorkflowResult` 字段并增加 `source/phases/path_diff`。
  - `packages/graph-agent/src/graph_agent/core/runner.py:61` 到 `packages/graph-agent/src/graph_agent/core/runner.py:75`：`run_skill` 返回 `RunResult(source="run")`。
  - `packages/graph-agent/src/graph_agent/core/runner.py:316` 到 `packages/graph-agent/src/graph_agent/core/runner.py:326`：抽出 shared executor 或新增 predict mode。
  - `packages/graph-agent/src/graph_agent/core/runner.py:338` 到 `packages/graph-agent/src/graph_agent/core/runner.py:339`：移除 predict 对 `mock_llm` 的依赖；`mock_llm` 从 public run/predict 签名删除或降级 test-only。
  - `packages/graph-agent/src/graph_agent/__init__.py:55` 到 `packages/graph-agent/src/graph_agent/__init__.py:76`：新增导出 `RunResult` 与 `predict_skill`；`WorkflowResult` 可短期 alias，PR-3 再从 public contract 清掉。
  - `packages/graph-agent/src/graph_agent/core/skill_tool_factory.py:110`、`packages/graph-agent/src/graph_agent/tools/md_to_json.py:578`、`packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:306`：同步 nested `run_skill` 返回类型 `WorkflowResult -> RunResult`，并确认 `event_subscriber` 透传策略。
- Delete:
  - 文件内删除 public predict 路径上的 `mock_llm` 语义。
- New:
  - `predict_skill` public function，可位于 `packages/graph-agent/src/graph_agent/core/runner.py` 或同层新模块后由 `graph_agent.__init__` 导出。

依赖:

- 依赖 PR2-1 红灯测试。
- 依赖 PR-1 的 event substrate。

迁移路径:

- `WorkflowResult` 能力 -> `RunResult`。
- `PredictResult.status/phases/path_diff` 能力 -> `RunResult.success/phases/path_diff`。
- `mock_llm` predict 入口 -> `predict_skill(..., model_resolver=..., copilot_predict=...)`。

验收标准:

- `run_skill` 返回 `RunResult(source="run")`。
- `predict_skill` 返回 `RunResult(source="predict")`。
- predict 路径 `RunResult.success` 与当前 `apps/studio/backend/app/services/predictor.py:99` 到 `apps/studio/backend/app/services/predictor.py:109` 的 path diff 判定一致。

### Task PR2-3 [BREAKING] SDK 接管 predict 编排、cache/ABC 与 input_hash

建议 commit prefix: `feat()!`

Files:

- Modify:
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:10` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:52`：保留或迁移内部模型语义；`PredictResult` 不再作为 public 返回。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py:13` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py:36`：新增 `input_hash`。
  - `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:44` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:60`：复用 phase-local inputs 构造 cache input。
  - `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:94` 到 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:102`：确保上游 output 进入下游 declared inputs 后才影响 `input_hash`。
  - `packages/graph-agent/src/graph_agent/core/manifest.py:31` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:37`：以 `PhaseIOSchema.inputs` 作为 input hash 范围。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/strategy.py:12`：策略继续做 SDK 内部逻辑，不 export。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:7`：phase record assembler 迁入 SDK predict result 聚合。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:139`：删除 predict 专用 tracing callback 对 public callback 继承的依赖，改由 PR-1 event sink 聚合诊断。
- Delete:
  - 文件内删除 `PredictResult` public 返回语义。
  - 文件内删除 `PredictTracingCallback` 作为 public contract 的语义。
- New:
  - 可新增 SDK 内部 predict service/cache module，用于封装 cache lookup/write、ABC 选择、`RunResult` 聚合。

依赖:

- 依赖 PR2-2 的 `RunResult` 与 `predict_skill`。

迁移路径:

- `GoldenCase` 留在 SDK cache/ABC 内部。
- `PhaseRecord` 语义进入 `RunResult.phases`。
- `PathDiff` 语义进入 `RunResult.path_diff`。
- `PredictResult.status` 进入 predict 路径 `RunResult.success`。

验收标准:

- cache key 逻辑为 `(phase_id, prompt_hash, input_hash)`。
- 无关 root inputs 不改变当前 phase `input_hash`。
- cache hit 不调 Copilot callable；cache miss 且需要预测时才通过 Gateway。

### Task PR2-4 [BREAKING] Gateway predict callable bridge 与 resolver typed context

建议 commit prefix: `feat()!`

Files:

- Modify:
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:90` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:100`：`assemble_graph` 接收并透传 `predict_context`。
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:488` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:502`：保留 `chat_model is not None` 短路；predict 路径保证 `chat_model=None`，并把 `predict_context` 传给 resolver。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/__init__.py:15` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/__init__.py:22`：删除 magic attr 协议 `_graph_agent_predict_mock_strategy` / `bind_predictor`。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:29` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:180`：删除 SDK 侧 `PredictGatewayChatModel` 实现或迁出为 Gateway facade。
  - `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:14` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:23`：显式声明 typed `predict_context`。
  - `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:53` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:63`：不再 `del kwargs` 丢弃 predict context。
  - `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:97` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:112`：删除 magic attr 读取，改用 `predict_context` 分支。
  - `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:15` 到 `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:42`：placeholder `_generate` 改为调用 injected Copilot callable。
- Delete:
  - 删除跨包 magic attr 隐式协议。
  - 删除 Gateway placeholder 固定 `"predict mock"` 行为。
- New:
  - 可新增 `PredictContext` / callable payload contract，位置在 Gateway package，不能 import Studio。

依赖:

- 依赖 PR2-2 与 PR2-3。

迁移路径:

- SDK predict business -> SDK 内部 service。
- Gateway 只保留 provider/model/role 与 chat/predict model facade。
- Studio Copilot callable 通过参数注入，不产生 Gateway -> Studio import。

验收标准:

- `resolve(..., predict_context=...)` 返回 Gateway predict chat model。
- predict chat model `_generate` 调 injected callable。
- `predict_context=None` 时普通 `GatewayChatModel` 行为不变。
- `rg -n "_graph_agent_predict_mock_strategy" packages/graph-agent/src packages/graph-agent-gateway/src` 不再命中生产协议。

### Task PR2-5 [BREAKING] Studio predictor 迁移到 SDK `predict_skill`

建议 commit prefix: `feat()!`

Files:

- Modify:
  - `apps/studio/backend/app/services/gateway_resolver.py:15` 到 `apps/studio/backend/app/services/gateway_resolver.py:21`：支持 Copilot callable 注入或 per-call `predict_context`。
  - `apps/studio/backend/app/services/predictor.py:13` 到 `apps/studio/backend/app/services/predictor.py:27`：删除 `_predict_internal` imports。
  - `apps/studio/backend/app/services/predictor.py:66` 到 `apps/studio/backend/app/services/predictor.py:82`：从临时 `run_skill` predict 路径迁到 `predict_skill(...)`。
  - `apps/studio/backend/app/services/predictor.py:99` 到 `apps/studio/backend/app/services/predictor.py:109`：将 status 判定迁到 SDK `RunResult.success`，Studio 不再自行组装 `PredictResult`。
  - `apps/studio/backend/app/services/skills.py:768` 到 `apps/studio/backend/app/services/skills.py:769`：继续由 Studio 提供 `workspace_dir`。
  - `apps/studio/backend/app/models/runs.py:9`：删除对 `_predict_internal.models` 的导入；保留 `apps/studio/backend/app/models/runs.py:8` 的 `CallbackEvent` 导入；`PredictDiagnosticExport.phases/path_diff` 注解改用 PR2-2 新增的 SDK public result/diagnostic schema，即 `RunResult` 的 `phases` / `path_diff` 元素类型，不新增 Studio 私有重复类型。
  - `apps/studio/backend/app/services/diagnostic_export.py:7`：从 `PredictResult` 改为 `RunResult(source="predict")`。
  - `apps/studio/backend/app/services/diagnostic_export.py:13` 到 `apps/studio/backend/app/services/diagnostic_export.py:21`：把 `RunResult(source="predict")` 必须适配为 `PredictDiagnosticExport`，`RunResult.success` 映射到 `status: "success" | "failed"`，`source == "predict"` 映射到 `is_predict=True`。
  - `apps/studio/backend/app/routers/runs.py:32` 到 `apps/studio/backend/app/routers/runs.py:40`：predict endpoint 返回 `export_predict_diagnostics(run_result).model_dump(mode="json")`，不得直出 `RunResult.model_dump(mode="json")`。
- Delete:
  - Studio 侧删除 `_predict_internal` 直接依赖。
- New:
  - 必须保留或新增 Studio backend 保形 adapter；不得重新引入 SDK private model。

依赖:

- 依赖 PR2-2 到 PR2-4。

迁移路径:

- Studio `PredictResult` 消费 -> `RunResult(source="predict")`。
- Studio `_predict_internal` strategy/diff/tracing -> SDK `predict_skill`。
- Studio Copilot -> injected callable，经 Gateway facade 调用。
- Frontend JSON contract 保持不变：`apps/studio/frontend/src/api/client.ts:124` 到 `apps/studio/frontend/src/api/client.ts:127` 和 `apps/studio/frontend/src/api/types.ts:212` 到 `apps/studio/frontend/src/api/types.ts:217` 继续消费 `PredictDiagnosticExport` 的 `is_predict/status/phases/path_diff`；round-32 不改 Studio 前端。

验收标准:

- `rg -n "graph_agent\\.core\\._predict_internal" apps/studio/backend/app` 不再命中。
- predict endpoint 前端 JSON 契约不变：返回 `PredictDiagnosticExport` 形态，包含 `is_predict/status/phases/path_diff`，不要求前端读取 `success` 或 `source`。
- diagnostic export 接受 `RunResult(source="predict")`，并完成 `success(bool) -> status(string)` 与 `source -> is_predict` 映射。
- `apps/studio/frontend/src` 无需为 round-32 predict endpoint JSON 形态做代码修改。

### Task PR2-6 PR-2 集成验证与捆绑边界

Files:

- Modify:
  - `packages/graph-agent/tests/test_public_api_contract.py:906` 到 `packages/graph-agent/tests/test_public_api_contract.py:910`：PR-2 可仅更新必要计数让新增 `RunResult/predict_skill` 测试通过，最终缩减在 PR-3。
  - `apps/studio/backend/tests/test_api.py:397`、`apps/studio/backend/tests/test_api.py:763`：确保 predict 与 run 共享 `trace.jsonl` 读取约定。
- Delete:
  - 无。
- New:
  - 无。

依赖:

- 依赖 PR2-1 到 PR2-5。
- PR-2 依赖 PR-1；不能绕过 PR-1 的 `event_subscriber` substrate。

验收标准:

- SDK predict tests、Gateway predict callable tests、Studio backend predict tests 通过。
- Studio backend predict tests 断言 endpoint 外部响应仍是 `PredictDiagnosticExport`，内部 SDK 结果才是 `RunResult(source="predict")`。
- `rg -n "PredictResult|_graph_agent_predict_mock_strategy|callbacks=\\[tracing_callback\\]" packages/graph-agent/src packages/graph-agent-gateway/src apps/studio/backend/app` 不再命中生产路径；测试 fixture 例外需注释说明。

## PR-3: T2 public API fingerprint cleanup

### Task PR3-1 [TESTS-FIRST] 写最终 public API 指纹红灯测试

Files:

- Modify:
  - `packages/graph-agent/tests/test_public_api_contract.py:16` 到 `packages/graph-agent/tests/test_public_api_contract.py:77`：最终 public symbol 表只保留应公开入口；新增 `RunResult/predict_skill`，删除 `_predict_internal` 与 callback 继承类。
  - `packages/graph-agent/tests/test_public_api_contract.py:101` 到 `packages/graph-agent/tests/test_public_api_contract.py:114`：红灯删除 `EXPECTED_PREDICT_INTERNAL_SYMBOLS`。
  - `packages/graph-agent/tests/test_public_api_contract.py:587` 到 `packages/graph-agent/tests/test_public_api_contract.py:619`：保留 `CallbackEvent` 事件变体契约。
  - `packages/graph-agent/tests/test_public_api_contract.py:621` 到 `packages/graph-agent/tests/test_public_api_contract.py:679`：删除继承式 callback protocol contract。
  - `packages/graph-agent/tests/test_public_api_contract.py:906` 到 `packages/graph-agent/tests/test_public_api_contract.py:910`：更新硬编码 symbol 计数。
  - `packages/graph-agent/tests/test_public_api_contract.py:991` 到 `packages/graph-agent/tests/test_public_api_contract.py:998`：删除 `_predict_internal` import contract 测试。
- Delete:
  - 文件内删除 `_predict_internal` de facto contract 测试。
  - 文件内删除 callback 继承 protocol contract。
- New:
  - 可新增负向测试：`graph_agent.core._predict_internal` 不出现在 public contract map。

依赖:

- 依赖 PR-2 完成 `RunResult/predict_skill` 替代链。

验收标准:

- 先红：旧 contract 仍导出 `WorkflowResult`、`PredictResult`、callback 继承类或 `_predict_internal` 符号。
- 目标绿：public API contract 与 PR-2 实际公共面一致。

### Task PR3-2 [BREAKING] 删除 predict internal public 指纹，清掉 12 个债符号

建议 commit prefix: `refactor()!`

Files:

- Modify:
  - `packages/graph-agent/tests/test_public_api_contract.py:40`、`packages/graph-agent/tests/test_public_api_contract.py:48`、`packages/graph-agent/tests/test_public_api_contract.py:52`、`packages/graph-agent/tests/test_public_api_contract.py:57`：`BaseMockStrategy/GoldenCaseStrategy/HeuristicStubStrategy/MockStrategy` 不再作为 contract symbols。
  - `packages/graph-agent/tests/test_public_api_contract.py:47`、`packages/graph-agent/tests/test_public_api_contract.py:59`、`packages/graph-agent/tests/test_public_api_contract.py:62`、`packages/graph-agent/tests/test_public_api_contract.py:65`：`GoldenCase/PathDiff/PhaseRecord/PredictResult` 不再作为 public symbols。
  - `packages/graph-agent/tests/test_public_api_contract.py:64`、`packages/graph-agent/tests/test_public_api_contract.py:66`：`PredictGatewayChatModel/PredictTracingCallback` 不再作为 contract symbols。
  - `packages/graph-agent/tests/test_public_api_contract.py:77`、`packages/graph-agent/tests/test_public_api_contract.py:78`：`assemble_phase_record/compute_diff` 不再作为 public symbols。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:10` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:52`：模型只保留内部语义，不被 contract map/import guard 保护。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:29` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:180`：SDK 侧 `PredictGatewayChatModel` 不再作为 contract。
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:139`：`PredictTracingCallback` 不再作为 contract。
- Delete:
  - 文件内删除 `EXPECTED_PREDICT_INTERNAL_SYMBOLS` 与对应测试。
- New:
  - 无。

依赖:

- 依赖 PR3-1。
- 依赖 PR-2 已将能力迁入 `RunResult` 与 SDK predict internals。

迁移路径:

- `PredictResult` 删除 -> `RunResult(source="predict")`，`status/phases/path_diff` 分别映射到 `success/phases/path_diff`。
- `PhaseRecord/PathDiff` -> `RunResult` 诊断子模型或 SDK public result 子模型。
- Strategy / GoldenCase / diff helpers -> SDK 内部实现，不再做公共指纹。
- `PredictGatewayChatModel` -> Gateway facade。

验收标准:

- `EXPECTED_PREDICT_INTERNAL_SYMBOLS` 不存在。
- `_predict_internal` 不再被 public API contract 测试 import。
- 12 个债符号不再计入 public contract。

### Task PR3-3 [BREAKING] 收束顶层导出、callback 继承契约与 docs/spec

建议 commit prefix: `refactor()!`

Files:

- Modify:
  - `packages/graph-agent/src/graph_agent/__init__.py:32` 到 `packages/graph-agent/src/graph_agent/__init__.py:35`：移除 callback 类顶层 import/export。
  - `packages/graph-agent/src/graph_agent/__init__.py:55` 到 `packages/graph-agent/src/graph_agent/__init__.py:76`：最终导出 `RunResult/predict_skill/CallbackEvent` 等公共面，不再以 `WorkflowResult` 为 canonical。
  - `docs/engine/public-api-contract.md:33`：`run_skill` 签名改为 `event_subscriber` 与 `RunResult`。
  - `docs/engine/public-api-contract.md:38`：`WorkflowResult` 小节迁移为 `RunResult`。
  - `docs/engine/public-api-contract.md:541`：`PredictResult` 小节迁移或删除。
  - `packages/graph-agent/spec/contract_map.yaml:122`：删除/迁移 `PredictResult` 条目。
  - `packages/graph-agent/spec/contract_map.yaml:164`、`packages/graph-agent/spec/contract_map.yaml:359`：`WorkflowResult` 条目改为 `RunResult`。
  - `packages/graph-agent/README.md:94`、`packages/graph-agent/README.md:125`、`packages/graph-agent/README.md:126`、`packages/graph-agent/README.md:173`、`packages/graph-agent/README.md:177`：README 示例与目录说明改为 `RunResult`。
- Delete:
  - docs/spec 中删除 `PredictResult` 作为 public result 的说明。
  - docs/spec 中删除 callback 继承作为扩展点的说明。
- New:
  - 无。

依赖:

- 依赖 PR3-2。

迁移路径:

- `WorkflowResult` canonical 名称 -> `RunResult`。
- `Callback/LoggingCallback/MetricsCallback/TracingCallback` public extension -> `event_subscriber(CallbackEvent)`。
- `PredictResult` docs -> `RunResult(source="predict")`。

验收标准:

- `rg -n "WorkflowResult|PredictResult|callbacks: list\\[Any\\]|EXPECTED_PREDICT_INTERNAL_SYMBOLS" packages/graph-agent/README.md docs/engine/public-api-contract.md packages/graph-agent/spec/contract_map.yaml packages/graph-agent/tests/test_public_api_contract.py` 不再命中最终 public docs/contract，历史说明例外需显式注释。
- `graph_agent.__all__` 不再把 callback 继承类或 `WorkflowResult` 作为 canonical public API。

### Task PR3-4 最终 repo-wide contract 扫描与 round-32 完成门

Files:

- Modify:
  - `.kiro/specs/engine-mvp0-rebuild-v030/round-32-post-v2-engine-rework/tasks.md`：如实施中发现任务拆分变化，只更新任务状态/备注，不反向修改 design。
- Delete:
  - 无。
- New:
  - 无。

依赖:

- 依赖 PR3-1 到 PR3-3。

验收标准:

- 完成门扫描：
  - `rg -n "EXPECTED_PREDICT_INTERNAL_SYMBOLS|PredictResult|WorkflowResult|tracing\\.jsonl|callbacks=" packages apps docs .kiro/specs/engine-mvp0-rebuild-v030`
  - 只允许历史 round 文档、迁移说明或明确白名单命中。
- `run_skill` 与 `predict_skill` 均返回 `RunResult`。
- Studio backend 不再 import `graph_agent.core._predict_internal`。
- Gateway resolver 不再读取 `_graph_agent_predict_mock_strategy`。
- predict cache key 有测试证明只由 `(phase_id, prompt_hash, input_hash)` 决定。
- trace 文件统一为 `<workspace_dir>/runs/<run_id>/trace.jsonl`。
