---
spec: engine-mvp0-rebuild-v030/round-9-PR-alpha-gateway-llm-roles
phase: PR α (Gateway + llm-roles Phase 1)
owner: a2 主笔 / a1 audit / 主控复核
依赖: PR #90 已 close, 新 branch feat/pr-alpha-gateway-llm-roles-phase1
后续: γ0 (契约补丁 14h) → PR β (middleware 34h) → γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR α: Gateway & LLM-Roles Phase 1 Requirements

## §1 业务需求 (PM 视角)
- **解耦核心引擎**：实现 `graph-agent` 和 `graph-agent-gateway` 两个包在物理层面的完全分离。引擎侧不再直接依赖任何第三方大模型 SDK（如 OpenAI / Anthropic），纯粹通过依赖注入的方式消费统一的模型解析服务。
- **结构化错误透传**：当所有的 Provider 都 Fallback 失败时，返回给 Studio 的错误不再是模糊的字符串，而是包含每一个 Provider 详细失败原因（如 rate limit、insufficient funds）的结构化 JSON Payload，以便于在 UI 上呈现诊断信息。
- **细粒度大模型控制**：在 Studio 设置 LLM Roles 时，允许对某一个具体 Role 的特定模型配置单独的 `temperature` 和 `max_tokens`，而不是全系统共用同一个温度值。旧有配置文件需做到无损向后兼容并自动热迁移。

## §2 与 MVP0 R1-R12 的映射关系
PR α 承接并完整交付以下 MVP0 R 级需求：
- **R1**: 实现 `ModelResolverProtocol` DI 与 Engine Runtime 的贯通（注：原 R1 包含 SkillResolverProtocol，此处仅交付 Model 相关的部分，SkillResolver 留给后续）。

## §3 PR α 独有需求 [NEW]
- **R[NEW]-Gateway-01 (独立包结构)**: 创建 `packages/graph-agent-gateway`，包含自己的 `pyproject.toml` 和依赖隔离。
- **R[NEW]-Gateway-02 (Payload Spec)**: 实现 `AllProvidersFailedError` 的结构化 Provider Error Payload，格式需由 a1 确认并在 schema 中锁死。
- **R[NEW]-Roles-01 (温度下推)**: Studio backend `llm_roles.yaml` 解析器需执行自动迁移：将顶层 `temperature` 移除并分发到每个 `RoleModelEntry` 中。
- **R[NEW]-Roles-02 (参数透传)**: Gateway Resolver 在实例化具体 LangChain 模型时，必须优先读取并应用传入 `RoleModelEntry` 级的 `temperature` 和 `max_tokens`。

## §4 验收标准 (Acceptance Criteria)

### 4.1 功能验收 (Functional)
1. 引擎执行包含 Agent 的测试 Graph 时，通过注入 Mock Model Resolver 可以成功走通 ReAct Loop，且不产生任何关于 OpenAI/Anthropic SDK 缺失的 Import Error。
2. 触发一次必然导致全部 Provider Fallback 失败的请求（如挂载无效的假 API Key），断言抛出的 `AllProvidersFailedError` 包含正确的结构化字典。
3. 提供一份带有顶层 `temperature: 0.7` 的遗留 `llm_roles.yaml` 文件，后端启动后，该文件被自动改写为不含顶层 `temperature` 且所有模型 Entry 内增加 `temperature: 0.7`。

### 4.2 测试验收 (Testing)
1. `graph-agent` 自身的 tests 中，所有隐式依赖 `ChatOpenAI` 等实体的测试用例全部重构为依赖 Dummy / Mock Resolver。
2. 新增 `packages/graph-agent-gateway/tests/` 目录，且单元测试覆盖率需达到基准线（验证 fallback 逻辑和温度透传）。

### 4.3 文档验收 (Documentation)
1. Gateway 独立 Package 的 README.md 就绪。
2. Studio API Spec 文档更新关于 LLM Roles 数据结构变更的内容（移除了顶层 temp，增加了底层 temp/max_tokens）。
3. **Gateway 架构文档同步验收**: 必须同步更新 `docs/graph-agent-gateway/mvp0/mvp0-alignment.md` 与 `docs/graph-agent-gateway/mvp0/logic-explained.md`。所有隐式依赖 `ChatOpenAI` 等实体的测试用例全部重构为依赖 Dummy / Mock Resolver。
2. 新增 `packages/graph-agent-gateway/tests/` 目录，且单元测试覆盖率需达到基准线（验证 fallback 逻辑和温度透传）。

### 4.3 文档验收 (Documentation)
1. Gateway 独立 Package 的 README.md 就绪。
2. Studio API Spec 文档更新关于 LLM Roles 数据结构变更的内容（移除了顶层 temp，增加了底层 temp/max_tokens）。
