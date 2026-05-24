# graph-agent-gateway (engine) — MVP0 Alignment (V0.3.0)

> **Status**: Updated by a2, 2026-05-24 (PR α Cutover)
> **Scope**: `ModelResolverProtocol` 强 DI、gateway runtime 错误结构化、fallback event 向 V0.3.0 tracing 底座对齐。目前 PR α 已全面实施完成。
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

## 与当前源码的差异
**无差异**。本文件描述的目标状态已通过 PR α 完全在主干代码落地，Gateway 包与核心引擎完全实现了物理边界隔离与反向控制。
