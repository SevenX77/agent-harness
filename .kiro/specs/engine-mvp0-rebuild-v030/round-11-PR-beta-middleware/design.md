---
spec: engine-mvp0-rebuild-v030/round-11-PR-beta-middleware
phase: PR β (Middleware Runtime Refactor)
owner: a2 主笔 3 文档 / a1 主笔 tasks.md / 主控复核
工程量: 41h (实施 β1-β7=32.5h + audit/docs/ship buffer β8-β11=8.5h)
依赖: PR γ0 (Contract Patch) 已 ship
后续: γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR β: Middleware Runtime Refactor Design

## §0.5 继承字段表 (PR γ0 锁定的边界)

| 组件 / 契约 | γ0 锁定的状态 | PR β 的行动 |
|---|---|---|
| `AgentNodeAST.validator` | boolean (default `False`) | Middleware 初始化时消费该字段，用于判断是否挂载 Validator |
| `validator` 函数签名 | `def validate(output: dict, state_slice: dict, **kwargs) -> None \| dict` | `CognitiveFlowMiddleware` 中将调用此签名替换原 `business_validator` |
| `MVP0_MIDDLEWARE_ORDER_CONTRACT` | `ProtocolValidation → CognitiveFlow → ExecutionControl → Tracing → ToolError → LoopDetection` |  必须在装配 Pipeline 时严格遵守此顺序实现注册 |
| 异常码占位符 | `[F-v3-*-validator-failed]` | `validator` 函数抛出的异常将被中间件拦截并赋予该错误码反馈 |

## §1 CognitiveFlowMiddleware 全面接管
- **背景**: 遗留架构中，Agent 的 Tool Handling（如 `finish_task`、业务校验）深度耦合在 `graph_assembler.py` 甚至是底层的 LangChain Tool definition 中。
- **设计**: `CognitiveFlowMiddleware` 将取代旧的强耦合逻辑，接管：
  1. `finish_task` 的 JSON Schema 初筛 (依赖底层的 `SchemaEngine`)。
  2. 当 `finish_task` 的格式通过 Schema 后，触发更深层的 Business Validator。
  3. `ask_clarification` 工具的拦截和处理。
- **边界**: 不修改 `SchemaEngine` 的内核，也不触碰 `IOManager` 的底层状态管理。Middleware 仅作流量代理和卡口。

## §2 Business Validator Runtime 签名对齐
- **旧逻辑**: `cognitive_flow.py` 的 `_run_business_validator` 当前期望的签名是 `Callable[[list[dict[str, Any]]], tuple[bool, list[str]]]`，并且返回 `(passed, errors)`。
- **新契约实施**:
  - `CognitiveFlowMiddleware` 需要重构 `_run_business_validator`，以对接 PR γ0 锁定的新签名：`def validate(output: dict, state_slice: dict, **kwargs) -> None | dict`。
  - **异常拦截**: 修改原先纯文本拼接返回 `errors` 的逻辑。如果 validator 抛出特定异常，Middleware 负责捕获，封装带有 `[F-v3-agent-validator-failed]` 的结构化信息，通过 ToolMessage 反馈给 LLM 触发 Nudge (重试)，或者根据重试次数直接阻断图谱执行。PR β runtime 仅实施 `[F-v3-agent-validator-failed]`; `[F-v3-subgraph-validator-failed]` 和 `[F-v3-logic-validator-failed]` 保留 γ0 placeholder, 留 followup (subgraph/logic validator runtime 不在本 PR scope)。

## §3 Middleware 组装工厂实现
- 根据 `MVP0_MIDDLEWARE_ORDER_CONTRACT` 的顺序，在引擎启动的核心位置（如 `graph_assembler.py` 或独立的 factory）实现这 6 个中间件实例的真正组装与挂载。
- 新建或重构确实存在的 `TracingMiddleware`、`ToolErrorHandlingMiddleware` 以及 `LoopDetectionMiddleware` 骨架类，使其符合 LangChain 的 `AgentMiddleware` 协议（即便核心逻辑留空，也需要存在物理类占位，以满足装配）。

## §4 边界防守 (Out of Scope)
- ❌ **Compile Schema / Parser 重构 (PR γ1)**: 不碰 `manifest.py` 和 `loader.py` 的核心逻辑。
- ❌ **DAG 静态阻断 (PR γ1.5)**: Validator 只在 Runtime 运行，不在 Compile 期作预判阻断。
- ❌ **State-IO / Smart Reducer (PR γ2)**: Middleware 可以读取 `state_slice`，但绝不能自己去写降维合并的 `smart_reducer`。
