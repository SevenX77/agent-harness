---
spec: engine-mvp0-rebuild-v030/round-11-PR-beta-middleware
phase: PR β (Middleware Runtime Refactor)
owner: a2 主笔 3 文档 / a1 主笔 tasks.md / 主控复核
工程量: 41h (实施 β1-β7=32.5h + audit/docs/ship buffer β8-β11=8.5h)
依赖: PR γ0 (Contract Patch) 已 ship
后续: γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR β: Middleware Runtime Refactor Requirements

## §1 业务需求 (与 MVP0 R1-R12 映射)
PR β 承接并完整交付以下 MVP0 运行时基础设施构建工作：
- **实施统一 Middleware 洋葱模型**：将原先散落在核心运行时、Harness 以及 Node 内部的错误拦截、循环检测、协议验证逻辑统一抽离收敛为 Middleware Chain。

## §2 PR β 独有需求
- **R-β-01 (CognitiveFlow 接管)**: `CognitiveFlowMiddleware` 必须完整接管 `finish_task` 与 `ask_clarification` 工具的调度和验证。必须替代旧私有 ReAct loop 的运行时控制职责 (finish_task 成败 / SchemaEngine gate / business validator / ask_clarification 调度), 保留 LangGraph node shell 作为装配边界, 见 tasks.md §0.1。
- **R-β-02 (Validator 运行时接入)**: 中间件在拦截到 `finish_task` 时，必须调用我们在 γ0 中锁定的签名 `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict`。并且能够安全捕获业务验证异常。
- **R-β-03 (Middleware Factory 挂载)**: 引擎启动时，必须按照 γ0 锁定的常量 `MVP0_MIDDLEWARE_ORDER_CONTRACT` 的严格顺序，将全部 6 个 Middleware 类实例化并挂载到 LangChain Agent 上。
- **R-β-04 (SchemaEngine io.outputs Strict Gate)**: CognitiveFlowMiddleware 拦截 finish_task 时, 必须先用 SchemaEngine 对编译后的 io.outputs schema 做 strict 校验; schema 失败时不得调用 business validator, 必须拒绝并触发 retry; schema 缺失视为编译错误 (fatal, 不 silent pass)。schema 失败时 dispatch `[F-v3-agent-output-schema-invalid]` (schema 不匹配 / 校验失败), schema 缺失时 dispatch `[F-v3-agent-output-schema-missing]` (fatal, 不 silent pass)。**Why**: γ0 已退役 `AgentNodeAST.exit_contract` 用户自定义文案, 输出约束降维为系统默认 V030_AGENT_EXIT_CONTRACT_TEXT + io.outputs schema, runtime 必须补强结构化校验。

## §3 验收标准 (Acceptance Criteria)

### 3.1 功能验收 (Functional)
1. 配置一个包含特定 Validator 的 Agent Phase，触发一次一定会失败的业务规则。断言引擎能优雅捕获该 Validator 异常，将其包装为 `[F-v3-agent-validator-failed]` 错误码并作为 ToolMessage 返给大模型，模型进而发生重试（Nudge 循环）。
2. (R-β-04 验收) SchemaEngine 失败时 validator 未被调用 + retry 触发。
3. 在核心代码中验证：中间件工厂完全移除了硬编码的旧版 Middleware 列表，严格按照 `ProtocolValidation → CognitiveFlow → ExecutionControl → Tracing → ToolError → LoopDetection` 的顺序初始化并串联。

### 3.2 架构测试验收 (Testing)
1. 保证集成测试中，所有的 Middleware 类在装配后都能被正确初始化（包括那些仅作为占位符的新中间件如 `ToolErrorHandlingMiddleware`）。

### 3.3 Ship Gate (要全过才能 ship PR β)
- `uvx ruff check packages/graph-agent` 和 `uvx mypy packages/graph-agent`: 全绿无错。
- `pytest packages/graph-agent/tests/middleware`: Middleware 的全系核心单元测试 100% PASS。
- 验证原 `graph_assembler.py` 中遗留的手写 Agent ReAct loop 逻辑（如果在替换范围内）已干净剥离。

### 3.4 Out of Scope (PR β 不做，留给后续)
- ❌ Compile Schema AST 更新 (例如 `GRAPH.md` body XML 回归) → 留给 γ1。
- ❌ Compile 期 / Predict 期的静态 Validator 阻断 → 留给 γ1.5。
- ❌ 状态树降维与 StateMapper 数据重构 (例如隔离 Subgraph) → 留给 γ2。
