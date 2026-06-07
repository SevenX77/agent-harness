# graph-agent-gateway (engine) — Baseline (V0.3.0)

> **归档说明 (2026-06-02)**:MVP0 文档保留 PR α / Provider Intelligence V2 的历史快照。当前 42 文件覆盖和 MVP1 目标说明已迁移到 `../mvp1/README.md` 及 14 个模块文档;本文不再作为当前代码的完整 baseline。

> **Status**: Updated by a2, 2026-05-24 (PR α Cutover)
> **Scope**: Gateway 独立 package 边界、`ModelResolverProtocol` DI 注入、`GatewayChatModel` runtime fallback、`llm_roles.yaml` 解析产物与热迁移、Predict mock 短路、以及与 execution-runtime / tracing 的边界。
> **配套**: 见 [mvp0-alignment.md](./mvp0-alignment.md)。
>
> ⚠️ **已过时 (2026-06-01 审计补注)**：本文档下文描述的 resolver 数据模型
> （`ResolvedRole.call_chain` / `model_fallback` / `active_model_code`、`ResolvedProvider`、
> `RoleConfigData`、`src/.../llm_config.py`）是 **PR α 时点的旧模型，已在 2026-05-25 hard cutover
> (`ecab5fe1`) 删除**，替换为 registry resolver（`registry/resolver.py` + `RegistrySnapshot` +
> `fallback_chain`/`route_id`）。当前实际 resolver 见 `mvp0-alignment.md` 的 registry 小节。
> 另注：旧 `resolve_role` 用 `continue`+`logger.warning` **跳过**未注册 model/provider；新 registry
> resolver 改为对未配置 route 直接 `raise`（这是一处回归）。修复方向见
> `.kiro/specs/studio-llm-gateway-redesign/`。下文保留作历史快照。

## 子模块职责

`graph-agent-gateway` 是 Engine 连接外部大模型的适配层，现已作为独立 Python package (`packages/graph-agent-gateway/`) 被剥离。它把业务侧的逻辑角色或 tier, 例如 `phase.tier` / `llm_role`, 解析成 LangChain 兼容的 `BaseChatModel`, 并在真实调用时按 provider/model 候选链做 probe、mark-down、fallback、usage 记录和 fallback 事件发射。

它不负责 `GRAPH.md` / `SKILL.md` 编译, 不负责 state 黑板切片, 不负责 Studio 前端如何配置模型角色, 也不直接拥有 trace 文件格式。Engine 核心运行时不再包含内置的 resolver 单例，而是通过 `ModelResolverProtocol` 强依赖外部注入（由 Studio 注入）。

## V0.3.0 src 文件清单 (packages/graph-agent-gateway/)

| 文件 | 当前职责 | 关键入口 |
|---|---|---|
| `src/graph_agent_gateway/gateway_chat_model.py` | LangChain `BaseChatModel` adapter, provider fallback runtime loop, tool binding clone | `GatewayChatModel`, `_generate()`, `bind_tools()` |
| `src/graph_agent_gateway/resolver.py` | 读取 `llm_roles.yaml` 的解析结果, 返回 `GatewayChatModel` 或 Predict mock model | `ModelResolver.resolve()` |
| `src/graph_agent_gateway/protocol.py` | Engine 消费的 DI 协议定义 | `ModelResolverProtocol` |
| `src/graph_agent_gateway/llm_config.py` | `llm_roles.yaml` dataclass schema 与热加载 | `ResolvedProvider`, `ResolvedRole`, `RoleConfigData` |
| `src/graph_agent_gateway/predict_interception.py` | Predict 模式 gateway subclass, 不打真实 provider | `PredictGatewayChatModel` |
| `src/graph_agent_gateway/exceptions.py` | provider 全部失败的结构化异常类及其他网关异常 | `AllProvidersFailedError`, `GatewayResolverMissingError` |
| `src/graph_agent_gateway/tracing.py` | 发射 `LLMFallbackEvent` 事件到统一 tracing 底座 | `emit_llm_fallback_event()` |
| `src/graph_agent_gateway/models.py` | Provider SDK wrappers / LangChain imports 归口 | `ChatOpenAI`, `ChatAnthropic` |

## LLM 角色注册表与解析产物

配置加载器从 `llm_roles.yaml` 解析出 `ModelDef`, `ProviderDef`, `RoleDef`, 再展开为 runtime 直接消费的 `ResolvedRole` / `ResolvedProvider`。

**V0.3.0 数据层变更 (LLM Roles Phase 1)**: 废除了 `RoleEntry` 的顶层 `temperature` 字段。加载时会执行 **load-time in-memory 热迁移**，将旧版的顶层 `temperature` 下推到所有 `RoleModelEntry.temperature` 中，以支持模型级别的细粒度参数控制。

### ResolvedRole 字段

| 字段 | 干什么 | 为何校验 | 判定逻辑 | 错误码 |
|---|---|---|---|---|
| `role_name` | 保存解析后的角色名 | 需要知道这次按哪个角色解析 | `resolve_role()` 找不到 role 时抛错 | `[F-v3-gateway-role-not-configured]` |
| `temperature` | 被下推至 model 级别，传给 `GatewayChatModel` | 非数字会让真实 SDK 参数非法 | model entry 中读取，默认 `0.7` | `ValueError` / gateway config code |
| `system_prompt_prefix` | 给 cognitive prompt 的 role-level 前缀 | prompt 组装需要稳定字符串 | `resolve_role()` 对原值做 `(prefix or "").strip()` | 无 |
| `active_model_code` | 标记首选 model code, 用于展示和 peer fallback 查组 | 缺主候选会导致错误 | `resolve_role()` 按 active model 优先排序 | gateway config code |
| `model_fallback` | 决定是否在 role 内追加其他 model 候选 | 若不校验 fallback 行为会违背预期 | false 时 active model 后 break | 无 |
| `call_chain` | 按优先级排列的 `ResolvedProvider` 候选链 | 空链会导致无法调用 | 空链抛 `AllProvidersFailedError` | `[F-v3-gateway-all-providers-failed]` |

### ResolvedProvider 字段

| 字段 | 干什么 | 为何校验 | 判定逻辑 | 错误码 |
|---|---|---|---|---|
| `provider_code` | provider 注册表 key, 也是 fallback/usage 的维度 | code 错会导致健康状态和 usage 错桶 | 引用必须存在 | gateway config code |
| `provider_def` | 保存 provider 类型、URL、密钥等定义 | 真实调用必须知道用哪类 adapter | 缺 provider 时不加入 call chain | gateway config code |
| `model_name` | provider 下真实模型名, 传给 SDK | code 与 provider-specific name 不是同一个字段 | model_def.providers.get() 必须存在 | gateway config code |
| `model_def` | 保存 model 的 reasoning、token 等能力 | 需要默认 reasoning 和 token 上限 | 读取 `min_max_tokens` 等 | gateway config code |
| `provider_options` | provider/model 组合的局部参数 | 同一 model 可能有不同上限 | 默认 `{}` | 无 |

## ModelResolverProtocol DI 接口

Engine 通过 `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py` 消费外部注入的 `ModelResolverProtocol`。单例已被清退。

### `ModelResolverProtocol.resolve(...)` 签名与字段

| 字段 | 干什么 | 为何校验 | 当前判定逻辑 | 错误码 |
|---|---|---|---|---|
| `role_name` | 调用方传入的逻辑角色 | 未配置角色需要明确 fallback 或报错 | 未命中时不再 fallback，直接报错 | `[F-v3-gateway-role-not-configured]` |
| `thinking_enabled` | 覆盖模型 reasoning 开关 | 参数影响 provider 请求体 | 传给 `GatewayChatModel.thinking_enabled` | 无 |
| `model_override` | 让 phase 直接指定 model code | phase 级 pin model 不能误走默认角色 | 未命中抛错 | `[F-v3-gateway-role-not-configured]` |
| `callbacks` | 注入事件 callback 给 gateway | fallback 事件需要进入统一 tracing | 传给 model `callbacks` | 无 |
| `phase_name` | fallback event 的 phase 标识 | trace 需要定位 phase | 传给 `GatewayChatModel.phase_name` | 无 |
| `**kwargs` | ad-hoc 扩展参数 | 透传给底层 | 额外扩展 | 无 |
| return `BaseChatModel` | 返回 LangChain 兼容模型给 runtime | runtime 只认 `invoke/bind_tools` 等 | 返回 `GatewayChatModel` 或 Predict mock | `[F-v3-gateway-resolver-missing]` 若未注入 DI |

## GatewayChatModel 与错误结构化

`GatewayChatModel._generate()` 按 `resolved_role.call_chain` 逐个 provider 尝试。
全部失败时，抛出结构化的 `AllProvidersFailedError`，包含三大错误码：
1. `[F-v3-gateway-all-providers-failed]`
2. `[F-v3-gateway-resolver-missing]`
3. `[F-v3-gateway-role-not-configured]`

### 结构化错误 Payload

| 字段 | 干什么 |
|---|---|
| `code` | 机器可读错误码 (如 `[F-v3-gateway-all-providers-failed]`) |
| `failed_provider_codes` | 失败候选 provider/model 列表 |
| `last_error_chain` | 每个候选的具体异常类型和消息的字典数组 |
| `role_name` / `phase_name`| 定位出处的元数据上下文 |

## Fallback Tracing 事件

`LLMFallbackEvent` 不再由 Gateway 内部直接处理 callback 循环，而是统一归口到 `emit_llm_fallback_event()`，通过 Engine 统一的 V2 tracing callback adapter 发送，完全对齐了 tracing-and-observability 模块的标准。
