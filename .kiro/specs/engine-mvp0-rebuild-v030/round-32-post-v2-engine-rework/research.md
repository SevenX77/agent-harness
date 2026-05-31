# Round 32 Research: Post-V2 Engine Rework

本文档为 round-31 三个后续任务 (T2, T3, T4) 在当前 V2 基线 (`4d8d678`) 下的现状研究报告。
根据 decisions.md 与 design.md 的契约作为准绳，梳理各目标在真实代码中的实现状态。

## T2: 指纹基线对账

**研究目标**：查明对外 API 指纹守卫是否错误冻结了 V2 及其关联的半成品 / 临时债（尤其 `predict_internal`）。

- **对 API 守卫的审计事实**
  - **状态**：③ 半成品 / 占位 / 重复 / 脏债
  - **证据**：`packages/graph-agent/tests/test_public_api_contract.py:16-82` (符号表 `EXPECTED_CONTRACT_SYMBOLS`) 以及 `:120-300+` (签名断言表)。
  - **结论**：守卫已把 12 个 `_predict_internal` 符号挂账为 `EXPECTED_PREDICT_INTERNAL_SYMBOLS`(de facto contract debt,见 `:101-118` + 测试`:991`)，等 §4 cutover 完成(PredictResult 整合进 RunResult + internal 符号清掉)后，T2 的活 = 把这 12 个从债清单移除 + 缩减计数。
  - **与文档冲突点**：根据 `decisions.md` §4，`PredictResult` 等概念应当被删除并被整合进 `RunResult`，但测试基线现将其硬编码成了需保障的契约债。
- **硬编码计数断言这块 cutover scope**
  - **结论**：T2 cutover 的显式 scope:①缩减 `EXPECTED_PREDICT_INTERNAL_SYMBOLS`(12→N);②同步改 `:906-909` 三个计数断言;③缩减 `EXPECTED_CONTRACT_SYMBOLS` 对应条目。不同步改 = 测试红。

## T3: PR-D tracing 重设计

**研究目标**：查明 runner / graph_assembler 的真实事件流现状，以及批量预发与真实 Agent 事件的双事件源冲突。

- **追踪默认落盘与单一事件源**
  - **状态**：② 设计目标未落地
  - **证据**：`packages/graph-agent/src/graph_agent/core/runner.py:330-340` 附近。`run_skill` (目前实为 `_run_v030_skill_dict`) 依然接受 `callbacks` 数组，未改造成 `event_subscriber: Callable` 形态，也没有实现在 `.workspace/runs/<run_id>/trace.jsonl` 的强制自动落盘功能。
- **双事件源与批量预发冲突**
  - **状态**：③ 半成品 / 重复 / 脏债
  - **证据 1 (假事件源)**：`packages/graph-agent/src/graph_agent/core/runner.py:358-362` 并在 `398-403` 处：在 `graph.invoke()` 真跑前后，`runner` 批量发出了所有 phase 的 `PhaseStartEvent` 和 `PhaseEndEvent`。
  - **证据 2 (真事件源)**：`packages/graph-agent/src/graph_agent/core/graph_assembler.py:389-392` 及 `541-546`：节点内部在执行真实 LLM/Logic 时，再次独立发射了 `PhaseStartEvent` 和 `PhaseEndEvent`。
  - **结论**：完全违背了"真实分阶段流式事件"的初衷，两处源码产生冲突，造成在控制台/日志里看到错误或未对齐的节点时序。注意此双发冲突只在 auto-trace 路径(`callbacks is None`,runner.py:337)显形;用户传 callbacks 时 runner 不批量发,只剩 graph_assembler 真事件。
- **Logic/Subgraph 节点无真实 lifecycle**
  - **结论**：真实 PhaseStart/End 目前只覆盖 Agent 节点;Logic/Subgraph 节点无真实 lifecycle,子图 callbacks 也未透传——PR-D 的'单一真实事件源'需覆盖这两类节点,不只是 Agent。
- **§16.3 callback→callable cutover 现状**
  - **状态**：② 设计目标未落地
  - **证据**：全局 grep `event_subscriber` 在 SDK 内为空（尚未实现）。`callbacks/base.py` 中 `AgentCallback`/`Callback`/`TracingCallback` 继承层级依然存在。`run_skill` 当前签名仍为 `callbacks: list[Any]` (`runner.py:61`)。`test_public_api_contract.py:587` 有 `EXPECTED_CALLBACK_EVENT_VARIANTS`。
  - **结论**：这套 CallbackEvent 契约将随 callback→callable 一起被砍。这块是 T3 设计不能绕过的第三条腿。

## T4: PR-E predict + 缓存

**研究目标**：审查 Predict -> Gateway -> Copilot 的关系契约和链式缓存在真实代码里的落地情况。

- **Predict -> Gateway 链路被物理切断**
  - **状态**：③ 脏债 / ② 设计目标未落地
  - **证据**：`packages/graph-agent/src/graph_agent/core/runner.py:338-339`。源码写着：`active_model_resolver = model_resolver if mock_llm is _NO_MOCK_LLM else None`。当 Studio 传入 predict mock 时，`model_resolver` 直接被置空。
  - **冲突**：这与 `decisions.md` §14 (Gateway 通过 callable 调 Copilot) 严重冲突。Resolver 被禁用后，Predict 请求根本无法进入 Gateway，整个闭环被切断。
- **RunResult + source 替代 PredictResult**
  - **状态**：② 设计目标未落地 / ③ 脏债
  - **证据**：`packages/graph-agent/src/graph_agent/core/result.py:48` 定义了 `WorkflowResult` 但缺失 `source` 字段。同时 `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:47` 中 `PredictResult` 原封不动保留，且 `apps/studio/backend/app/services/predictor.py:65-90` (`assemble_trace`) 仍在强依赖和返回 `PredictResult`。
  - **结论**：decisions.md §4/§7/§10 共 20+ 处用 `RunResult`,但 SDK 代码只有 `WorkflowResult`(grep RunResult packages/graph-agent/src = 空)。research 提了 WorkflowResult 缺 source, 但没 flag 这个命名歧义。T4 design 必须先决定:直接在 WorkflowResult 加 source 字段,还是 rename → RunResult。把这个 flag 写进 T4 节。
- **双层 `PredictGatewayChatModel`**
  - **状态**：③ 半成品 / 重复 / 脏债
  - **证据**：存在两份平行的类。SDK 侧有完整版实现 `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:29-33`，Gateway 侧有一个仅占位的 Mock 版 `packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:15-29`。这与 `decisions.md` §7 (Gateway 仅作为 facade) 形成设计混乱。
- **Magic Attr 跨包隐式契约**
  - **状态**：③ 脏债
  - **证据**：`packages/graph-agent/src/graph_agent/core/_predict_internal/__init__.py:15-18` (定义了 `bind_predictor` 设置 `_graph_agent_predict_mock_strategy` 属性)。随后 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:97-101` 使用 `getattr` 跨包提取此属性，用于拦截。此方式隐晦且破坏包边界，必须依新设计清理。
- **Studio 额外私有依赖 + 边界测试盲点**
  - **结论**：Studio 里不止 `predictor.py` 依赖 `_predict_internal`;`app/models/runs.py` / `diagnostic_export.py` / 相关 tests 也直接 import `PathDiff` / `PhaseRecord` / `PredictResult` / `strategy`。另外 Gateway boundary test 只禁 resolver.py 直接 import SDK private,不拦 magic attr 字符串协议——边界测试对这个跨包隐式契约有盲点。
- **Cache Key: `input_hash` 缺失**
  - **状态**：② 设计目标未落地
  - **证据**：`packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py:13-36` 仅定义了 `prompt_hash` 和 `schema_hash`，并未实现 `input_hash` 相关逻辑，导致 `decisions.md` §7 中说明的"链式失效"无法成立。
- **Copilot Callable 注入**
  - **状态**：② 设计目标未落地
  - **证据**：`apps/studio/backend/app/services/gateway_resolver.py:15-22` `build_gateway_model_resolver()` 负责在 Studio 构建 resolver，但它没有接收、也没有向 Gateway 注入 Copilot callback。

## 总结

**黄金原则结论**：V2 没有降级 T2/T3/T4 scope 内的已有能力(T5 notable-models 降级已划出 scope)。

对真实代码的摸底表明，`decisions.md` / `design.md` 中关于 T3 / T4 的绝大部分机制（尤其是 Copilot 闭环、RunResult 归一、Event 单一源、Input Hash 链式失效）**仍停留在设计目标阶段**，并未落地。同时，V2 前期的实现留下了大量的临时脏债与隐式契约（如跨包 getattr 取 mock 属性、双重 Phase 事件源、公开测试固化了 predict 内部符号），需在下一阶段实施中拔除。