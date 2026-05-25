---
spec: engine-mvp0-rebuild-v030/round-9-PR-alpha-gateway-llm-roles
phase: PR α (Gateway + llm-roles Phase 1)
owner: a2 主笔 / a1 audit / 主控复核
依赖: PR #90 已 close, 新 branch feat/pr-alpha-gateway-llm-roles-phase1
后续: γ0 (契约补丁 14h) → PR β (middleware 34h) → γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR α: Gateway & LLM-Roles Phase 1 Research

## §1 立项调研：Gateway 独立 Package 剥离

### 1.1 背景与痛点
当前 `graph-agent` 引擎层与模型提供商网关（Gateway）代码深度耦合。`Gateway` 相关的 API Keys 管理、Provider 配置、Token Tracking、以及 `AllProvidersFailedError` 降级逻辑等，全部混杂在 `graph_agent.models` 中。
- **痛点 1 (职责不清)**：引擎侧（graph-agent）关注认知图谱执行、状态机流转；Gateway 侧（graph-agent-gateway）关注网络请求、API Key 挂载、重试与 Provider Fallback。二者更新频率和依赖库（如各大 LLM SDK）完全不同。
- **痛点 2 (循环依赖)**：Studio 后端既需要调 Engine 执行 Graph，又需要调 Gateway 暴露模型列表。放在一个包内导致 Studio 无法做到隔离引用。

### 1.2 业内方案对比 (DeerFlow vs LangGraph)
- **DeerFlow**: 内部将 `ModelFactory` 和 `AgentRuntime` 做了严格模块化切割，Provider 配置被下推到了专门的 Model Gateway 内部服务，Agent Runtime 只消费一个统一签名的 `ChatModel` 实例。
- **LangGraph**: 核心引擎 `langgraph` 极度纯粹，而具体的模型交互由 `langchain_openai`, `langchain_anthropic` 等独立 package 承担。
- **结论**: 将 Gateway 抽离为 `packages/graph-agent-gateway/`，提供 `ModelResolverProtocol` 给 Engine 消费，是业界公认的解耦最佳实践。

## §2 架构聚合调研：为什么与 LLM-Roles Phase 1 合并？

### 2.1 数据依赖倒置问题
- **LLM-Roles Phase 1 (Data Layer)** 的核心是重构模型配置结构（去掉顶层冗余的 `temperature`，将 `temperature` 和 `max_tokens` 下推到 `RoleModelEntry` 级），并实现前后端能力的对齐。
- **Gateway** 的模型解析逻辑（即 `ModelResolverProtocol`）强依赖于 `RoleEntry` 和 `RoleModelEntry` 的具体数据结构。
- **合并理由**: 虽然二者同 PR 强耦合，但在实施时可并行。Gateway package skeleton 和 protocol 接口可以优先抽离，此时 LLM Roles Phase 1 的 Data 层重构可同步进行，只要在最终 `resolver` 实例化合流前，保证 `temperature/max_tokens` 正确透传即可。

## §3 风险调研：历史包袱与移植难度

### 3.1 PR #90 历史包袱分析
PR #90 中包含了长达 44 个 commit 的复杂修改，其中关于 Gateway 的重构（如结构化 gateway failure 升级 `AllProvidersFailedError`）有部分正确的尝试。
- **风险**: 由于 PR #90 中 Engine 和 Studio 提交相互交织，Gateway 的 `models/` 目录被多处不规范 import 污染，强行 cherry-pick Gateway 相关提交容易带入违背 MVP0 契约的幽灵代码（如自创的 `vendor` 字段和 `ModelInfo[]` 结构）。
- **缓解策略 (a1/a2 共识)**: **放弃 cherry-pick，采用手工安全移植 (Clean Port)**。基于最新的干净 `main` 重新创建 `packages/graph-agent-gateway/`，只提取 PR #90 中符合 `AllProvidersFailedError` Payload Spec 的核心逻辑，放弃所有带有争议的自创 Schema。
- **工程量预期**: Gateway 重构与物理隔离约 40h（含 DI 改造、failure payloads、tracing 对齐与测试），LLM-Roles Data 层重构约 14h。二者合计 54h，在安全预估工时控制范围内，无重基地狱风险。
