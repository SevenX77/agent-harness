---
spec: engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch
phase: PR γ0 (契约补丁, PR α 后 PR β 前)
owner: a1 主笔 tasks.md / a2 主笔 3 文档 / 主控复核
工程量: 14h (1.75d) + audit/e2e/CI buffer 1.25d
依赖: PR α (Gateway + llm-roles Phase 1) 已 push (#91 待 review/merge)
后续: PR β (middleware 34h) → γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR γ0: Contract Patch Research

## §1 为什么必须插入 γ0 契约补丁？
PR β (Middleware Runtime Refactor) 的核心工作是重写 Agent 运行时的中间件管线（包含 Schema Validator 和 Business Validator），并且实现动态加载验证逻辑。
如果在 PR β 之前不先修补 `AgentNodeAST` / `SubgraphNodeAST` 的 `validator: bool = False` 字段，以及不移除对旧版 `<exit_contract>` 的强依赖，将会导致：
- PR β 中的 Validator 拦截器缺乏配置驱动字段，只能 hardcode 或者陷入死代码。
- PR β 必须去兼顾已经废弃的旧版退出协议，导致后续 γ1 需要再次对其进行大规模重构。
**结论**: 必须通过 γ0 快速扫清 AST Schema 和 Loader 的底层契约路障，作为 PR β 的前置补丁，防止架构实施过程中的二次返工。

## §2 Validator 统一签名设计调研
当前 V2.1 引擎的业务校验逻辑签名混乱，返回值类型不一。为了配合 PR β 的 `CognitiveFlowMiddleware` 以及保证抛错能够被统一的 `[F-v3-*-validator-failed]` 结构化异常拦截，需要统一所有 `validator.py` 的函数签名。
- γ0 锁定 validator 签名: `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict`
- γ0 锁定 3 个 placeholder 错误码 (具体 code 留 PR β/γ1.5 决定)
- γ0 不实施 runtime 处理 (留 PR β middleware)
- γ0 不要求抛 `GraphAgentValidationError` 类异常 (那是 runtime 行为, 留 PR β)

## §3 Middleware Order 顺序敏感性调研
参考业内成熟的图谱调度器与代理中间件架构（如 Bytedance 的 DeerFlow 洋葱模型）：
- 必须遵循的严格顺序：`ProtocolValidation → CognitiveFlow → ExecutionControl → Tracing → ToolError → LoopDetection`
**结论**: 在 γ0 中，必须通过文档或常量显式定义并固化这一中间件加载顺序契约，为 a1 在 PR β 实施 `factory.py` 时的 `middleware.append()` 提供防偏移的准则。