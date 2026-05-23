# graph-agent-gateway (engine) — MVP0 Alignment (V0.3.0 ModelResolverProtocol DI)

> **Status**: Added by a1 (Codex), 2026-05-23
> **Scope**: `ModelResolverProtocol` 强 DI、gateway runtime 错误结构化、fallback event 向 V0.3.0 tracing 底座对齐。
> **配套**: [MVP0 Q-R-P0-1](../MVP0-DECISIONS-EXPLAINED-2026-05-21.md#51-q-r-p0-1-modelresolver-放在哪里), [Error Code Spec](../skill-spec/11-error-code-spec.md), [Tracing MVP0 Alignment](../tracing-and-observability/mvp0-alignment.md)。

## V0.3.0 改造摘要

V0.3.0 对 gateway 的核心判断来自 Q-R-P0-1: 真实大模型能力由外层 Studio 后端注入, Engine 只负责跑图。当前 `ModelResolver` 仍是 Engine 内 singleton, `GatewayChatModel` 仍在全 provider 失败时抛纯文本异常, fallback 事件仍直接走旧 callback loop。MVP0 要把这三件事收拢成可注入、可结构化、可追踪的 gateway 边界。

| V2.1 现状 | V0.3.0 目标 | 改造点 | 错误码 |
|---|---|---|---|
| `get_model_resolver()` singleton | `ModelResolverProtocol` 从 `run_skill` / assembly 顶层强注入 | GW-1 | `[F-v3-gateway-resolver-missing]` |
| `RuntimeError("All LLM fallback candidates failed ...")` | 结构化 gateway failure, payload 含失败候选链 | GW-2 | `[F-v3-gateway-all-providers-failed]` |
| gateway 直接 emit `LLMFallbackEvent` | fallback 事件通过 V0.3.0 tracing callback 底座统一发射 | GW-3 | 复用 tracing error/event contract |

## GW-1: ModelResolverProtocol DI 迁移

### Why

Q-R-P0-1 选择“外层 Studio 注入”。决策文档说明 Studio 后端负责读模型角色配置、密钥和供应商信息, 把可用模型对象传给 Engine; Engine 只负责跑图, `run_skill()` 入口需要接收外部模型解析能力, 见 `docs/engine/MVP0-DECISIONS-EXPLAINED-2026-05-21.md:940` 与 `:951`。

当前 `GraphAgentHarness` 在构造时直接调用 `get_model_resolver()`, 位置是 `packages/graph-agent/src/graph_agent/core/harness.py:373`; singleton 定义在 `packages/graph-agent/src/graph_agent/models/resolver.py:282`. 这会把模型配置读取和 provider 凭证处理留在 Engine 包内, 与 Studio 注入边界冲突。

### 范围

- 新增 / 上移正式 `ModelResolverProtocol`, 风格对齐 `SkillResolverProtocol`。
- `run_skill` / graph assembly / Agent runtime 入口显式接收 `model_resolver`。
- 删除或隔离 `get_model_resolver()` 的生产路径; tests 可以注入 fake resolver。
- `LLMPhaseNode` 当前消费的 `ModelResolverProtocol` 在 `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py:41`, 但签名缺 `thinking_enabled` 和 `**kwargs`; MVP0 要与 `ModelResolver.resolve()` 的真实签名对齐。

### 字段级契约

| 字段 / 参数 | src 依据 | 干什么 | 为何校验 | 目标判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `model_resolver` | `resolver.py:43`, `phase_nodes/base.py:41` | 外部注入的模型解析能力 | 未注入时 Engine 会回退 singleton 或运行期才发现无模型 | 含 LLM/Agent phase 的运行入口必须传入, 且实现 `resolve()` | `[F-v3-gateway-resolver-missing]` |
| `role_name` | `resolver.py:59` | 逻辑角色 / tier | 未配置角色应结构化失败, 不能 silent fallback 到错模型 | `None` 可走默认策略; 非空必须可解析或显式允许 ad-hoc | `[F-v3-gateway-role-not-configured]` |
| `thinking_enabled` | `resolver.py:61` | reasoning 开关 | Studio policy 与 phase override 需要稳定优先级 | `bool | None`; `None` 表示 resolver/model 自动决定 | 协议缺字段时归入 resolver 注入/接口校验, 不新增 gateway code |
| `model_override` | `resolver.py:62` | phase 级 model pin | 未知 model_override 不能静默换模型 | 必须是 registry model code; 未命中结构化报错或显式降级 policy | `[F-v3-gateway-role-not-configured]` / future config code |
| `callbacks` | `resolver.py:63` | trace/event callback 链 | resolver/gateway 事件要进入统一 tracing | tuple callback; 由 runtime 传入统一 V2 tracing callback | tracing contract |
| `phase_name` | `resolver.py:64` | 事件定位 phase | Studio 需要知道哪个 phase 触发模型解析 | LLM/Agent phase 调用时必须传当前 phase name | `[F-v3-runtime-phase-failed]` fallback |
| return `BaseChatModel` | `resolver.py:66` | LangChain runtime model | execution-runtime 只依赖 `BaseChatModel` surface | 返回对象必须支持 `invoke()` 和 `bind_tools()` | resolver 注入/接口校验, 不新增 gateway code |

### Cross-link

- [Execution Runtime MVP0 Alignment](../execution-runtime/mvp0-alignment.md) 中的 DI 注入边界。
- [SkillResolverProtocol Spec](../skill-spec/10-skill-resolver-protocol-spec.md#依赖注入-di-边界) 的单方法 DI 风格可作为 gateway 参照。

## GW-2: 纯文本 Error 结构化故障码归并

### Why

MVP0 决策 Q-R-ERROR 要求运行时错误带 code / metadata, 便于 Studio 解析, 见 `docs/engine/MVP0-DECISIONS-EXPLAINED-2026-05-21.md:93`. 当前 `_generate()` 在所有 provider 都失败后拼接字符串并抛 `RuntimeError`, 位置是 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:189`. 兼容异常 `AllProvidersFailedError` 只有 `tier` 和 `errors`, 位置是 `packages/graph-agent/src/graph_agent/core/exceptions.py:256`.

### 范围

- 将 `_generate()` 的最终 `RuntimeError` 改为结构化 gateway exception。
- 复用或升级 `AllProvidersFailedError`, 增加 `code`, `failed_provider_codes`, `last_error_chain`, `role_name`, `phase_name`。
- 保留原始异常链, 但对 UI 暴露稳定 payload。
- 更新错误码 spec 增加 gateway domain 或确认 gateway code 所属 runtime/gateway domain。

### 字段级契约

| 字段 | src 依据 | 干什么 | 为何校验 | 目标判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `code` | error spec payload 规则 `skill-spec/11-error-code-spec.md:29` | 机器可读错误码 | UI 不应截字符串识别模型用尽 | 固定 `[F-v3-gateway-all-providers-failed]` | `[F-v3-gateway-all-providers-failed]` |
| `role_name` / `tier` | `gateway_chat_model.py:190`, `exceptions.py:261` | 说明哪个角色耗尽候选 | Studio 需要定位配置项 | 来自 `GatewayChatModel.role_name` 或 resolver effective role | `[F-v3-gateway-all-providers-failed]` |
| `phase_name` | `gateway_chat_model.py:63`, `:274` | 说明哪个 phase 调用失败 | Canvas / trace 需要标红 phase | 来自 model `phase_name`; 无则 `<gateway>` | `[F-v3-gateway-all-providers-failed]` |
| `failed_provider_codes` | `gateway_chat_model.py:127` | 失败候选 provider/model 列表 | UI 需要展示 fallback 链和全部失败原因 | 从 `resolved_role.call_chain` 与捕获失败构造, 格式建议 `provider/model` | `[F-v3-gateway-all-providers-failed]` |
| `last_error_chain` | `gateway_chat_model.py:175` | 每个候选的异常类型和消息 | 诊断需要保留 root cause | 捕获 `_RUNTIME_FAILOVER_EXCEPTIONS` 时追加结构化 item | `[F-v3-gateway-all-providers-failed]` |
| `message` | `exceptions.py:270` | 人类可读摘要 | CLI / logs 仍需要可读文本 | 由 payload 渲染, 不作为 UI 判断依据 | `[F-v3-gateway-all-providers-failed]` |
| `context` | `exceptions.py:21` | GraphAgentError 已有结构化上下文 | 不用新增平行字段系统 | exception 初始化时写入 context dict | `[F-v3-gateway-all-providers-failed]` |

### Cross-link

- [Error Code Spec](../skill-spec/11-error-code-spec.md) 需要补 `gateway` domain 或 runtime 下的 gateway code。
- [Tracing MVP0 Alignment](../tracing-and-observability/mvp0-alignment.md) 应消费相同 `code` 和 `context`。

## GW-3: Fallback 事件统一总线对齐

### Why

Q-T-1 选择抽公共 tracing 底座, 主线和 Predict 共享, 见 `docs/engine/MVP0-DECISIONS-EXPLAINED-2026-05-21.md:94`. 当前 gateway 在 `_emit_real_fallback_event()` 里直接构造 `LLMFallbackEvent` 并调用每个 callback 的 `on_event`, 位置是 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:263`. 事件模型本身定义在 `packages/graph-agent/src/graph_agent/callbacks/events.py:240`.

### 范围

- 保留 `LLMFallbackEvent` 语义字段, 但发射路径改为统一 V2 tracing callback 底座。
- `_generate()` 捕获 provider 失败后仍在同一位置触发 fallback event, 但事件 payload 结构与 tracing-and-observability 统一。
- callback 失败仍不能吞掉原模型异常链, 只能记录 tracing failure。
- Predict 模式不打真实 provider, 不应产生真实 fallback event; 它应继续记录 mock source。

### 字段级契约

| 字段 | src 依据 | 干什么 | 为何校验 | 目标判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `phase_name` | `events.py:244`, `gateway_chat_model.py:274` | fallback 所属 phase | trace timeline 需要归属 | 必须是 runtime phase name; fallback `<gateway>` 只允许非 phase 调用 | tracing event validation |
| `from_provider` | `events.py:245`, `gateway_chat_model.py:275` | 失败候选 | Studio 展示 fallback 起点 | 格式 `provider/model`, 来自 `_candidate_id(candidate)` | tracing event validation |
| `to_provider` | `events.py:246`, `gateway_chat_model.py:276` | 下一个候选 | Studio 展示 fallback 终点 | `_next_candidate_id()` 返回下一个未 down candidate 或 `<none>` | tracing event validation |
| `reason` | `events.py:247`, `gateway_chat_model.py:277` | 失败原因摘要 | Debug 需要异常类型和消息 | 当前是 `"Type: message"`; MVP0 可补结构化 error code/context | `[F-v3-gateway-all-providers-failed]` 最终耗尽时 |
| callback sink | `gateway_chat_model.py:279` | 接收事件的 callback 列表 | 新旧 callback 并存会造成 trace 缺失 | 改由统一 V2 tracing callback adapter 分发 | tracing callback error |

### Cross-link

- [Tracing and Observability MVP0 Alignment](../tracing-and-observability/mvp0-alignment.md) 的统一 tracing 底座章节。
- `LLMCallEvent` / `LLMFallbackEvent` 当前 schema 在 `packages/graph-agent/src/graph_agent/callbacks/events.py:73` 和 `:240`。

## MVP0 死代码清退

- 清退生产路径中的 `get_model_resolver()` singleton 自动创建逻辑; 保留测试 helper 时必须标注 test-only。
- 清退 `_fallback_to_minimal_factory()` 作为未配置 role 的隐式生产 fallback, 或把它改为显式 opt-in policy; 默认未命中 role 应结构化报 `[F-v3-gateway-role-not-configured]`。
- 清退 `_generate()` 末尾纯文本 `RuntimeError`, 改 `AllProvidersFailedError` 或新 gateway exception。
- 清退与 V2 tracing 平行的直接 callback 分发路径, 统一进入 tracing-and-observability 的 callback 底座。

## V0.3.0 版本号 cutover

按照 [skill-spec README](../skill-spec/README.md) 的模块级决议引用约定, gateway 的 V0.3.0 cutover 完成条件是:

1. `run_skill` / Agent runtime 不再依赖 Engine 内置 resolver singleton。
2. `ModelResolverProtocol` 的签名与实际 resolver 能力一致, 包含 `thinking_enabled`, `model_override`, `callbacks`, `phase_name`。
3. `[F-v3-gateway-*]` 错误码进入错误码 spec, Studio 不再解析自由文本。
4. fallback 事件通过统一 tracing callback 底座产生, Predict mock 与真实 provider fallback 在 trace 中可区分。

cutover 后, baseline 中描述的 singleton 和纯文本失败只作为 V2.1 历史现状保留, 不再是 Engine 运行路径。
