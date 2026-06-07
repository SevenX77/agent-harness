# graph-agent-gateway (engine) — MVP0 Alignment (V0.3.0)

> **归档说明 (2026-06-02)**:本文保留 MVP0 改造记录和 2026-05-25/06-01 审计补注。当前架构目标以 `../mvp1/README.md` 和 `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md` 为准。

> **Status**: Updated by Codex, 2026-05-25 (Provider Intelligence V2 backend/runtime cutover)
> **Scope**: `ModelResolverProtocol` 强 DI、gateway runtime 错误结构化、fallback event 向 V0.3.0 tracing 底座对齐，以及 endpoint/route/runtime-settings registry 后端路径。
> **配套**: [MVP0 Q-R-P0-1](../MVP0-DECISIONS-EXPLAINED-2026-05-21.md#51-q-r-p0-1-modelresolver-放在哪里), [Error Code Spec](../skill-spec/11-error-code-spec.md), [Tracing MVP0 Alignment](../tracing-and-observability/mvp0-alignment.md)。

## V0.3.0 改造完成状态

PR α 已完成以下三项核心改造。Gateway 已作为独立包 `packages/graph-agent-gateway` 发布，Engine 实现了纯粹的 `ModelResolverProtocol` DI，并在 `apps/studio/backend/app/services/run_manager.py` 和 `predictor.py` 中实现了外部注入。

| V2.1 历史 | V0.3.0 完成态 | 改造点 | 错误码 |
|---|---|---|---|
| `get_model_resolver()` singleton | `ModelResolverProtocol` 从 `run_skill` 顶层强制注入，已清除单例。 | GW-1 | `[F-v3-gateway-resolver-missing]` |
| `RuntimeError("All LLM fallback candidates failed ...")` | 结构化的 `AllProvidersFailedError`，payload 含失败候选链。 | GW-2 | `[F-v3-gateway-all-providers-failed]` |
| gateway 直接 emit `LLMFallbackEvent` | fallback 事件通过 V0.3.0 tracing callback adapter 统一发射。 | GW-3 | 复用 tracing error/event contract |

## GW-1: ModelResolverProtocol DI 迁移 (已完成)

### 范围与现状
- 正式 `ModelResolverProtocol` 已在 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py` 定义。
- `run_skill` 入口现在强制要求提供 `model_resolver`（未提供抛 `GatewayResolverMissingError`）。
- 彻底删除了旧版 `get_model_resolver()` 的生产路径，切断了引擎对于配置读取和 provider SDK 的隐式依赖。

### 字段级契约

| 字段 / 参数 | 目标判定逻辑 | 错误码 |
|---|---|---|
| `model_resolver` | 运行入口必须传入，且实现 `resolve()`。未传入阻断运行。 | `[F-v3-gateway-resolver-missing]` |
| `role_name` | 未命中则直接报错，不再 silent fallback。 | `[F-v3-gateway-role-not-configured]` |
| `thinking_enabled` | `bool | None`; `None` 表示 resolver 自动决定。 | 无 |
| `model_override` | 必须是 registry model code; 未命中结构化报错。 | `[F-v3-gateway-role-not-configured]` |

## GW-2: 纯文本 Error 结构化故障码归并 (已完成)

### 范围与现状
- `GatewayChatModel` 在全部 provider 失败时，抛出结构化的 `AllProvidersFailedError` (`packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py`)。
- 移除了 Engine core 遗留的纯文本 `RuntimeError` 以及旧版的 `AllProvidersFailedError`。

### 字段级契约

| 字段 | 目标判定逻辑 | 错误码 |
|---|---|---|
| `code` | 固定为 `[F-v3-gateway-all-providers-failed]` | `[F-v3-gateway-all-providers-failed]` |
| `failed_provider_codes` | 从 `resolved_role.call_chain` 与失败捕获构造，例如 `["openai/gpt-5"]`。 | `[F-v3-gateway-all-providers-failed]` |
| `last_error_chain` | 字典列表，包含每个 provider 的 `error_type` 和 `message`。 | `[F-v3-gateway-all-providers-failed]` |

## GW-3: Fallback 事件统一总线对齐 (已完成)

### 范围与现状
- 保留 `LLMFallbackEvent` 语义，但已重构 `gateway_chat_model.py` 不再直接调用 `on_event`。
- 通过引入 `emit_llm_fallback_event` 方法调用 Engine 的统一 callback adapter。

## MVP0 死代码清退 (已完成)
- 彻底清退 `get_model_resolver()` singleton。
- 清退了 `_fallback_to_minimal_factory()`。
- 清退了旧版异常与平行分发逻辑。

## Provider Intelligence V2 对齐

> 本节承接 `.kiro/specs/llm-provider-intelligence-v2/` 的 Gateway 落点决策。当前分支已落地 registry schema/resolver/client-manager/backend API 的主要硬切路径；frontend 仍按单独 UI guardrail 验证。

### 决策

LLM Provider Intelligence V2 的共享 registry core 应落在独立 Gateway 包内：

```text
packages/graph-agent-gateway/src/graph_agent_gateway/registry/
  __init__.py
  schema.py
  storage.py
  canonical.py
  resolver.py
  lint.py
  capabilities.py
  error_classification.py
  probe_contracts.py
```

不要创建 `packages/graph-agent/src/graph_agent/llm_registry/`。Engine 主包继续只依赖 `ModelResolverProtocol`，不拥有 registry storage、credentials loading、provider SDK cache 或 canonicalization 规则。

### 边界

| Layer | Owns | Must Not Own |
|---|---|---|
| `graph_agent_gateway.registry` | endpoint/route/role/runtime-policy schema, route ID validation, canonical mapping, role-route resolution, capability linting, probe DTOs | FastAPI handlers, React state, LangChain/SDK clients |
| `graph_agent_gateway.resolver` | adapter from registry `ResolvedRole` to `GatewayChatModel` | Studio file write policy, UI DTO formatting |
| `graph_agent_gateway.gateway_chat_model` | deterministic fallback loop, fallback/fail-fast classification, diagnostics, event payloads | dynamic capability-based model selection |
| Studio Backend | credentials file writes, API redaction, endpoint tests, route probes, model profile CRUD/apply, Agent import draft lifecycle, diff/apply workflow | canonicalization rules duplicated outside Gateway |
| Studio Frontend | model profile cards, route grouping UI, lint/probe display, drag/drop of exact `route_id` values | constructing route records from raw model strings |
| Graph Agent Engine | phase execution, protocol-based resolver injection, generic prompt assembly | concrete registry storage, credentials loading, provider SDK cache, role-specific prompt config reads |

### 硬切规则

- Runtime schema 只接受 endpoint/route registry snapshot 和 route-chain roles。
- Import drafts 不进入 active credentials；使用独立 draft store 或 backend job store。
- `model_profiles` 只能作为编辑期 route bundle，不能作为 runtime execution identifier。
- 旧 `models/providers/roles` schema 必须以明确 schema-version 错误失败。
- 不保留旧 Studio LLM Roles / credentials DTO contract。
- 不保留 Engine-owned client manager 的 compatibility wrapper。
- `ModelResolver` 必须从显式 `RegistrySnapshot` 或显式 credentials/roles path 构造，不能静默加载内置模型默认值、旧 role 文件或 `.env` API key。
- `model_override` 必须变成显式 `route_id` override；未知 route ID 抛结构化 gateway 配置错误。
- `system_prompt_prefix` 等 role-specific prompt metadata 由 Gateway resolution 拥有，并通过 `ResolvedRole` 传给 `GatewayChatModel`；Engine 不直接读 role 文件。
- `runtime_policy` 是 registry snapshot 的显式字段；旧 `circuit_breaker`、`peer_model_groups`、`single_model_roles` 不会被解析为 runtime policy。
- `graph_agent_gateway.factory` 不属于 V2 runtime surface；env-reading factory helper 必须删除或降到 test-only 且不从 `graph_agent_gateway.__init__` re-export。
- Gateway 不得 import Graph Agent execution internals。Fallback event DTO、gateway base exception、Predict mock support 必须由 Gateway 自己拥有，Engine/tracing 只做适配。

### 必须迁移到 Gateway 的模块

当前 provider client manager 仍在 `packages/graph-agent/src/graph_agent/models/llm_client_manager.py`，并从环境变量解析 secret。Provider Intelligence V2 要求硬切：

- 将 `LLMClientManager` 移入 `graph_agent_gateway`。
- 删除 Engine-owned client-manager production path。
- Runtime credentials 来自 resolved endpoint，不来自 `.env`。
- Client cache key 必须包含 endpoint ID、protocol、base URL、credential fingerprint/version 以及 timeout/proxy 相关设置。
- Probe down TTL、probe timeout、token escalation rounds 来自 `ResolvedRole.runtime_policy`，不再是 Engine client manager class constants。
- Runtime policy 变化会使 runtime client cache 失效，但不改变 credential fingerprint 或 provider-test cache。
- `packages/graph-agent/src/graph_agent/config/llm_config.py` 从生产 imports 删除；Engine 不再拥有 LLM role schema loader。

### Runtime 行为

Resolver 流程：

1. 读取请求 role。
2. 按声明顺序遍历 `fallback_chain`。
3. 解析每个精确 `route_id`。
4. 通过 `endpoint_id` join route 与 endpoint。
5. 校验 protocol、base URL、route status、credential。
6. 运行 capability lint / fail-fast 检查。
7. 返回包含 role metadata、runtime policy 与有序 routes 的 `ResolvedRole`。

> **修订 (2026-06-01 审计 — studio-llm-gateway-redesign Requirement 2)**：上述步骤 3-5 的当前实现，
> 对 `fallback_chain` 中**第一个**未配置/不可执行路由直接 `raise`（崩在第一个）。在 save 解耦后
> （角色可引用未配置路由），这会让此类角色在执行期硬崩，且无 WARNING。
> **修订**：解析期对未配置 / 非可执行 status / 缺凭证的 chain 条目 **`continue` 跳过 + `logger.warning`**，
> 仅当过滤后**无任何可执行路由**时，`resolve_role` 抛 `RegistryResolutionError`（经 `ModelResolver.resolve`
> 映射为 `GatewayRoleNotConfiguredError`，`resolver.py:99`）。`AllProvidersFailedError`（`resolver.py:104`）
> **只属执行期**——解析出 ≥1 条 route 后运行时全败——不用于解析期空链。
> 此修订**只作用于解析期逐条 chain entry**——执行期（`GatewayChatModel`）的 fail-fast vs fallback
> 错误分类**保持不变**；`model_override` 单点显式指定未命中**仍 fail-fast**。
> 即：恢复旧 `resolve_role` 的 skip 容错，但保留 V2 的执行期 fail-fast 语义。

禁止按 provider、capability、price、latency、availability 搜索替代 route。Capability 只能 lint、warn、block、fail fast，不能驱动动态选型。

Engine 组装 v0.3/v2.1 skill 时必须按 executable phase 的 `llm_role` 调用 resolver。不能在 workflow 级别先 resolve 一个 `role_name=None` 的全局 chat model 再复用到所有 phase；这会绕开 role → model profile → route chain 编排。

Error classifier 归属 Gateway。Network/timeouts/retryable 5xx/classified rate limits/marked-down routes 可 fallback；missing credential、invalid credential、unknown model、bad request、unsupported capability、schema validation failure 必须 fail fast。无法分类的异常默认 fail fast 并带 route context。

Provider SDKs often wrap transport errors. Gateway classification must inspect chained exceptions (`__cause__`/`__context__`) and provider SDK `status_code` attributes so wrapped network failures can fallback while 400/401/403/404/422 fail fast.

Runtime Settings:

- Role/profile route entries own fixed normalized `runtime_settings`.
- Capabilities describe support/default/bounds only; they are not user intent.
- Resolver emits `effective_runtime_settings` with source metadata.
- `GatewayChatModel` includes redacted effective settings in response metadata and fallback events.
- Studio Backend exposes `route_runtime_settings` and `role_effective_runtime_settings` in `GET /api/llm/registry` so frontend controls do not infer provider behavior locally.
- Provider-specific names are confined to adapters: OpenAI-compatible chat args, Anthropic thinking args, Google GenAI generation config, and Ark official SDK chat completions.

Model Profile 处理：

- `model_profiles` 是 Studio/backend 的 authoring abstraction，用于表达 `CLO47T = Claude Opus 4.7 Thinking` 这类复用组合。
- 每个 profile 自身保存显式 `fallback_chain[*].route_id`。
- 将 profile 应用到 role 时，Backend 把 profile 展开成 role 的 `fallback_chain` snapshot。
- Role 可保存 `source_profile_id` 和轻量 snapshot 供 UI 溯源，但 runtime 只执行 role 当前保存的 route chain。
- 修改 profile 不会隐式改变已有 role；用户必须显式重新应用 profile。
- 删除 profile 不会改变 role fallback chain；Backend 可清理 dangling `source_profile_id`，并在 source snapshot 里设置 `deleted_at` / `deleted_marker` 供 UI 溯源。

Fallback 分类：

- 可继续 fallback：network connection errors、timeouts、retryable provider 5xx、classified rate limits、marked-down routes。
- 必须 fail fast：invalid request shape、unsupported capability、unknown model、missing credential、invalid credential when all routes share that credential、schema/config validation errors。
- 无法分类时，带 route context 暴露错误，不把它当作模型选择信号。

### base_url 归一化与真实测试路径（2026-06-01 真机查实修订）

> 来源：`temp/2026-06-01-probe-results.md` 六轮真机实测。决策与原因记录如下。

**决策 1 — base_url 必须按 protocol/SDK 归一化（头号修复）。**
当前 `client_manager`（及 Copilot 的 `claude_agent_sdk`）把用户填写的 `endpoint.base_url` 原样交给 SDK，未归一化。但各 SDK/CLI 的路径拼接习惯不同：openai SDK 请求 `{base}/chat/completions`（base 须以 `/v1` 结尾）；anthropic SDK / claude CLI 请求 `{base}/v1/messages`（base **不能**带 `/v1`，否则拼成 `/v1/v1/messages`）；deepseek 的 anthropic 端点在 `/anthropic`，ark 在 `/api/compatible` 且需 `ANTHROPIC_AUTH_TOKEN`。
- **原因**：实测「第三方测不通 / 红 / Unsupported」（wavespeed、deepseek、ark、qiniu-openai）真因**全部**是 base_url 未归一化（如 wavespeed 配 `.../v1` + anthropic 协议 → `/v1/v1/messages` → 404，被误读为「不支持 tool call / 协议」）。归一化后这 5 个 provider 经 `claude_agent_sdk` 全部跑通。
- **决策**：在 resolver/adapter 层按 protocol 归一化 base_url；且「host 实际支持哪种协议」**必须探测确认，不能靠 `protocol` 字段推断**——wavespeed/openrouter/qiniu 实为「一个 host 双协议」的聚合网关，仅 base_url 后缀因 SDK 而异。

**决策 2 — role test 必须走真实运行路径，禁止替代实现冒充。**
`test_copilot_role_sdk` 当前用 `anthropic.AsyncAnthropic`（messages API）探测，但 Copilot 运行时实际用 `claude_agent_sdk.ClaudeSDKClient`（spawn claude CLI）。**测试 SDK ≠ 运行 SDK = 假测试。**
- **决策**：copilot role test 必须用真实 `claude_agent_sdk`；graph_agent role test 必须用 `GatewayChatModel` + `create_agent` 跑**真实多轮 loop**（给足 recursion budget），不能用单次 tool-call probe 或裸 SDK 代替。

**决策 3 — tool call 是 agent loop 的必要前提，但不是实际筛选门槛。**
graph agent loop 结构上靠 tool call 工作（`tool_call→result` 循环 + `finish_task` 结束）。但真机实测：能用于对话 agent 的模型（deepseek-r1、gemma 等，经主流网关）**普遍支持** tool call，造不出「语言强但无 tool call」的反例（真正无 tool call 的只有 completion/embedding/base 模型，它们不能做对话 agent）。
- **决策**：role「就绪」判定标准 = **真实 agent loop 能否跑通**（base_url 归一化 + 足够 recursion + 多轮收敛），而非单独卡 tool call 能力；**base_url 归一化才是当前实际阻断点**。

### Studio 对齐

Studio Backend import gateway registry，并提供产品 API：

- `GET /api/llm/registry`
- `PUT /api/llm/registry/endpoints`，upsert endpoints，缺失 endpoint 不代表删除
- `DELETE /api/llm/registry/endpoints/{endpoint_id}`
- `POST /api/llm/endpoints/{endpoint_id}/test`
- `POST /api/llm/routes/{route_id}/probe`，可接受 runtime-setting capability metadata 并写入 normalized capability/default/bounds records
- `PUT /api/llm/routes/{route_id}`，只更新 route metadata/display/capability/status，不改变 route identity
- `DELETE /api/llm/routes/{route_id}`
- `GET /api/llm/model-profiles`
- `PUT /api/llm/model-profiles`
- `DELETE /api/llm/model-profiles/{model_profile_id}`
- `POST /api/llm/roles/{role_name}/apply-profile`
- import draft create/read/probe/apply endpoints
- role read/write endpoints using `fallback_chain`; roles-map PUT is upsert, single-role PUT is full replace

Studio Frontend 只消费 Backend DTO。它可以按 `canonical_id` 分组展示，也可以展示 Model Profile cards，但所有 role 编辑必须持久化精确 `route_id`。

Import draft DTO 支持多 endpoint candidate 和多 route candidate；Agent 抓取结果必须先进入 draft store，不能直接写 active endpoints/routes。Draft endpoint ID 如果匹配已有 active endpoint，必须走显式 diff/merge/delete-first 流程，不允许 auto-promote。

旧 provider-oriented API 不再是生产 contract：`providers/test` 被 endpoint test 替代，`providers/test-models` 被 route probe 替代，`providers/notable-models` 改为 import-draft 内部素材来源或删除。

### 实施顺序

1. 添加 gateway registry schema、model profiles、route ID validation、canonical mapper、linter、pure resolver tests。
2. 更新 `ModelResolver` 和 `GatewayChatModel` 消费 resolved routes，并发出 route diagnostics。
3. 将 `LLMClientManager` 移入 `graph_agent_gateway`，让 runtime credentials 来自 resolved endpoints。
4. 更新 Studio Backend storage/API 到 credentials v4 和 roles schema v2。
5. 更新 Studio Frontend，从 Available Models 切到 Available Routes，并增加 Model Profile cards。
6. 在 deterministic registry path 稳定后，再接 Agent import draft workflow。

Agent onboarding 是非可信输入，必须排在 deterministic registry 与 runtime resolver 正确之后。

### Non-Goals

- No dynamic intent routing.
- No capability-based automatic model replacement.
- No fuzzy canonical merging without explicit rules and tests.
- No runtime support for the old short-code config schema.
- No compatibility wrapper for the old Engine-owned client manager.
- No backward-compatible Studio DTO contract for old LLM Roles or credentials payloads.

## 与当前源码的差异

V0.3.0 MVP0 部分无差异：本文件前半部分描述的 PR α 目标状态已在主干代码落地，Gateway 包与核心引擎已实现物理边界隔离与反向控制。

Provider Intelligence V2 backend/runtime 主要路径已在当前分支落地：`graph_agent_gateway.registry`、route-chain runtime schema、credentials-file runtime execution、Gateway-owned `LLMClientManager`、runtime setting descriptors/effective settings、route-level diagnostics、`google_genai` adapter、`ark_runtime` adapter fake-client path。剩余差异集中在 opt-in live provider matrix 扩展、frontend 手工验收和真实 provider 观察表持续补充。
