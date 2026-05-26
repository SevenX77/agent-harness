---
spec: engine-mvp0-rebuild-v030/round-11-PR-beta-middleware
phase: PR β (Middleware Runtime Refactor)
owner: a2 主笔 3 文档 / a1 主笔 tasks.md / 主控复核
工程量: 41h (实施 β1-β7=32.5h + audit/docs/ship buffer β8-β11=8.5h)
依赖: PR γ0 (Contract Patch) 已 ship
后续: γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR β: Middleware Runtime Refactor Research

## §1 为什么 Middleware Refactor 是第一要务？
在剥离了 Gateway 并且打好 γ0 契约补丁后，引擎最深的痛点暴露无遗：运行时的控制流被散落在各个组装文件和装饰器中。
通过集中重构 Middleware 层：
- 可以将原先耦合在 Agent Node 里的 `finish_task`、业务重试、甚至未来的 Tracing 都抽离为纯粹的管道（Pipeline）处理。
- 这是实现真正的状态与 IO 隔离（PR γ2）以及彻底推翻旧 AST（PR γ1）的**执行层地基**。没有一个标准的运行时管道，改动 AST 带来的后果是不可控的。

## §2 CognitiveFlowMiddleware 职责调研
当前 `CognitiveFlowMiddleware` (`packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py`) 已经承载了大量职责，如 `finish_task` 的 JSON Schema 初步清洗，并调用了旧的 `business_validator` 签名。
在此次重构中，需要将其打造为真正的“认知流代理”：
- 它必须能优雅捕获 Validator 抛出的新版结构化异常。
- 它必须决定是将错误反馈给大模型进行重试（Nudge），还是向上传递导致 Agent 退出。
**架构抉择**: Middleware 应只负责**拦截和转换**，任何对 `state` 或 `output` 的底层深度校验，都应通过调用外部注入的 Validator 函数完成，保持内聚性。

## §3 Middleware Factory / 顺序敏感性调研
在 γ0 中我们制定了 6 层的洋葱模型：`ProtocolValidation → CognitiveFlow → ExecutionControl → Tracing → ToolError → LoopDetection`。
目前这 6 个中间件有些并不存在，有些类名不匹配。
- **调研结果**: PR β 必须在 `packages/graph-agent/src/graph_agent/middleware/` 或 `factory.py` 中建立一个真实的类列表。即使 `LoopDetection` 在此阶段只是一个空壳子类，也必须按照顺序加入执行链。这不仅是为了通过契约测试，更是为了防止以后插入业务逻辑时丢失切面。
