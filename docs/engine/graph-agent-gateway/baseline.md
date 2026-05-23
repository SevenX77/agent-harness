# graph-agent-gateway (engine) — Baseline (当下代码实现逻辑)

> **Status**: Added by a1 (Codex), 2026-05-23
> **Scope**: V2.1 `llm_role` / tier 到 LangChain `BaseChatModel` 的解析、`GatewayChatModel` runtime fallback、`llm_roles.yaml` 解析产物、Predict mock 短路、gateway 与 execution-runtime / tracing 的边界。
> **配套**: 见 [MVP0 决策 Q-R-P0-1](../MVP0-DECISIONS-EXPLAINED-2026-05-21.md#51-q-r-p0-1-modelresolver-放在哪里) 与 [mvp0-alignment.md](./mvp0-alignment.md)。

## 子模块职责

`graph-agent-gateway` 是 Engine 连接外部大模型的适配层。它把业务侧的逻辑角色或 tier, 例如 `phase.tier` / `llm_role`, 解析成 LangChain 兼容的 `BaseChatModel`, 并在真实调用时按 provider/model 候选链做 probe、mark-down、fallback、usage 记录和 fallback 事件发射。

它不负责 `GRAPH.md` / `SKILL.md` 编译, 不负责 state 黑板切片, 不负责 Studio 前端如何配置模型角色, 也不直接拥有 trace 文件格式。当前实现仍有 Engine 内置 singleton resolver, 这是 V0.3.0 需要改掉的边界。

## V2.1 src 文件清单

| 文件 | 当前职责 | 关键入口 |
|---|---|---|
| `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:54` | LangChain `BaseChatModel` adapter, provider fallback runtime loop, tool binding clone | `GatewayChatModel`, `_generate()`, `bind_tools()` |
| `packages/graph-agent/src/graph_agent/models/resolver.py:43` | 读取 `llm_roles.yaml` 的解析结果, 返回 `GatewayChatModel` 或 Predict mock model | `ModelResolver.resolve()` |
| `packages/graph-agent/src/graph_agent/config/llm_config.py:90` | `llm_roles.yaml` dataclass schema 与热加载 | `ResolvedProvider`, `ResolvedRole`, `RoleConfigData` |
| `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:29` | Predict 模式 gateway subclass, 不打真实 provider | `PredictGatewayChatModel` |
| `packages/graph-agent/src/graph_agent/core/exceptions.py:256` | provider 全部失败的兼容异常类 | `AllProvidersFailedError` |
| `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py:41` | execution-runtime 当前消费的最小 `ModelResolverProtocol` | `resolve(...) -> BaseChatModel` |

## LLM 角色注册表与解析产物

配置加载器从 `llm_roles.yaml` 解析出 `ModelDef`, `ProviderDef`, `RoleDef`, 再展开为 runtime 直接消费的 `ResolvedRole` / `ResolvedProvider`。解析入口包括 `_parse_models()`、`_parse_providers()`、`_parse_roles()` 和 `_validate_cross_references()`, 分别在 `packages/graph-agent/src/graph_agent/config/llm_config.py:256`, `:279`, `:301`, `:330`。

### ResolvedRole 字段

| 字段 | src | 干什么 | 为何校验 | 当前判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `role_name` | `llm_config.py:105` | 保存解析后的角色名, 例如 `balanced` 或 synthetic `_model_override::<code>` | execution-runtime 事件和 Studio 模型解释面板需要知道这次按哪个角色解析 | `resolve_role()` 找不到 role 时抛 `KeyError`; `resolve_model()` 构造 `_model_override::<model_code>` | 当前无 `[F-v3-*]`; MVP0 候选 `[F-v3-gateway-role-not-configured]` |
| `temperature` | `llm_config.py:106` | 传给 `GatewayChatModel.temperature`, 作为 provider 调用默认温度 | 非数字会让真实 SDK 参数非法 | role 配置用 `float(data.get("temperature", 0.7))`; model override 默认 `0.7` | 当前 `ValueError`; MVP0 归并 gateway config code |
| `system_prompt_prefix` | `llm_config.py:107` | 给 cognitive prompt 的 role-level 前缀 | prompt 组装需要稳定字符串, 不能保留 `None` | `resolve_role()` 对原值做 `(prefix or "").strip()`; model override 为空字符串 | 无 |
| `active_model_code` | `llm_config.py:108` | 标记首选 model code, 用于展示和 peer fallback 查组 | active model 不存在会造成 call chain 缺主候选 | `_validate_cross_references()` 检查 `role.active_model in models`; `resolve_role()` 按 active model 优先排序 | 当前 config load `ValueError`; MVP0 归并 gateway config code |
| `model_fallback` | `llm_config.py:109` | 决定是否在 role 内追加其他 model 候选 | 如果没校验, fallback 行为会和作者预期不一致 | `_parse_roles()` 用 `bool(data.get("model_fallback", False))`; `resolve_role()` 为 false 时 active model 后 break | 无 |
| `call_chain` | `llm_config.py:111` | 按优先级排列的 `ResolvedProvider` 候选链 | 空链会导致没有任何真实 provider 可调用 | `resolve_role()` / `resolve_model()` 只加入 provider/model cross reference 都存在的候选; `ModelResolver.resolve()` 空链抛 `AllProvidersFailedError` | 当前 `AllProvidersFailedError`; MVP0 `[F-v3-gateway-all-providers-failed]` |

### ResolvedProvider 字段

| 字段 | src | 干什么 | 为何校验 | 当前判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `provider_code` | `llm_config.py:94` | provider 注册表 key, 也是 fallback/usage/mark-down 的维度 | provider code 错会导致健康状态和 usage 记错桶 | `_validate_cross_references()` 要求 role/model 引用的 provider 存在 | 当前 config load `ValueError`; MVP0 gateway config code |
| `provider_def` | `llm_config.py:95` | 保存 provider 类型、URL、密钥环境变量、timeout 等定义 | 真实调用必须知道用哪类 provider adapter 和连接参数 | `_parse_providers()` 构造 `ProviderDef`; 缺 provider 时不加入 call chain | 当前 config load `ValueError`; MVP0 gateway config code |
| `model_name` | `llm_config.py:96` | provider 下真实模型名, 传给 SDK | model code 与 provider-specific name 不是同一个字段 | `model_def.providers.get(provider_code)` 必须存在 | 当前 config load `ValueError`; MVP0 gateway config code |
| `model_def` | `llm_config.py:97` | 保存 model 的 reasoning、token、function-call 支持等能力 | gateway 需要默认 reasoning 和 token 上限 | `model_code` 必须在 `models` 注册; `_default_max_tokens()` 读取 `model_def.min_max_tokens` | 当前 config load `ValueError`; MVP0 gateway config code |
| `provider_options` | `llm_config.py:98` | provider/model 组合的局部参数, 例如 `max_max_tokens` | 同一 model 在不同 provider 下可能有不同上限 | 来自 `model_def.provider_options.get(pc, {})`, 默认 `{}` | 无 |

## ModelResolver 当前接口

当前实现有两个层次。`ModelResolver.resolve()` 是真实实现签名, 位于 `packages/graph-agent/src/graph_agent/models/resolver.py:57`; execution-runtime 的旧 `ModelResolverProtocol` 只声明 `role_name`, `model_override`, `callbacks`, `phase_name`, 位于 `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py:41`, 尚未覆盖 `thinking_enabled` / `**kwargs`。

### `ModelResolver.resolve(...)` 字段

| 字段 | src | 干什么 | 为何校验 | 当前判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `role_name` | `resolver.py:59` | 调用方传入的逻辑角色 / tier | 未配置角色需要明确 fallback 或报错 | `None` 时用 `GRAPH_AGENT_DEFAULT_ROLE` 或 `balanced`; 未命中时走 minimal factory | 当前无结构化 code; MVP0 `[F-v3-gateway-role-not-configured]` |
| `thinking_enabled` | `resolver.py:61` | 覆盖模型 reasoning 开关 | reasoning 参数影响 provider 请求体, 错传会改变模型能力 | 传给 `GatewayChatModel.thinking_enabled`; `None` 时 `_generate()` 用 `candidate.model_def.reasoning` | 无 |
| `model_override` | `resolver.py:62` | 让 phase 直接指定 model code, 绕过 role -> model | phase 级 pin model 不能误走默认角色 | 先尝试 `cfg.resolve_model(model_override)`; KeyError 时 warning 后回 role resolution | 当前 warning; MVP0 gateway config code |
| `callbacks` | `resolver.py:63` | 注入事件 callback 给 gateway | fallback 事件和模型解析事件需要同一 callback 链 | tuple, 默认空; 传给 model `callbacks` | 无 |
| `phase_name` | `resolver.py:64` | fallback event 的 phase 标识 | 没有 phase 名, trace 只能显示 gateway 默认 | 传给 `GatewayChatModel.phase_name`; 空时 event 用 `<gateway>` | 无 |
| `**kwargs` | `resolver.py:65` | minimal factory 兼容扩展参数 | 未配置 role 时仍可创建 ad-hoc model | 只在 `_fallback_to_minimal_factory()` 中透传 | factory 原生异常; MVP0 应归并 gateway code |
| return `BaseChatModel` | `resolver.py:66` | 返回 LangChain 兼容模型给 execution-runtime | runtime 只认 `invoke/bind_tools` 等 LangChain surface | 正常返回 `GatewayChatModel` 或 `PredictGatewayChatModel`; role 未命中返回 minimal factory model | `[F-v3-gateway-resolver-missing]` 用于未来 DI 缺失, 非当前 resolve 返回 |

### ModelResolverStats 字段

| 字段 | src | 干什么 | 为何校验 | 当前判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `total_resolves` | `resolver.py:37` | 统计 resolver 被调用次数 | 运行诊断需要知道是否重复解析 | `_bump_stat("total_resolves")` 每次 resolve +1 | 无 |
| `cache_hits` | `resolver.py:38` | 预留缓存命中统计 | 当前 resolver 没有实际 model cache, 字段容易误导 | dataclass 默认 0, 当前未 bump | 无 |
| `provider_failures` | `resolver.py:39` | 预留 provider 失败统计 | 当前失败主要由 `GatewayChatModel._generate()` 和 `LLMClientManager` 记录 | dataclass 默认 0, 当前未 bump | 无 |
| `circuit_breaks` | `resolver.py:40` | 预留 circuit breaker 统计 | 未来可反映 provider mark-down 决策 | dataclass 默认 0, 当前未 bump | 无 |

## GatewayChatModel 现状

`GatewayChatModel` 继承 LangChain `BaseChatModel`, 字段定义在 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:54`. 它的 `_generate()` 按 `resolved_role.call_chain` 逐个 provider 尝试: 跳过已 mark-down 候选, 可选 probe, dispatch 真实 provider call, 成功时构造 `ChatResult`, 失败时 mark-down 并 emit `LLMFallbackEvent`; 全部失败时抛纯文本 `RuntimeError`: `gateway_chat_model.py:115`.

### 初始化 / Pydantic 字段

| 字段 | src | 干什么 | 为何校验 | 当前判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `role_name` | `gateway_chat_model.py:59` | 当前模型对应的逻辑角色名 | trace、错误、identifying params 都依赖它 | `__init__` 必传 string | MVP0 `[F-v3-gateway-role-not-configured]` / 当前 Pydantic error |
| `resolved_role` | `gateway_chat_model.py:60` | 完整候选链和角色配置 | `_generate()` 没有它无法 fallback | `__init__` 必传 `ResolvedRole` | 当前 Pydantic error |
| `max_tokens` | `gateway_chat_model.py:61` | provider 调用默认输出 token 上限 | 非正数应回退默认, 避免 SDK 参数非法 | 默认 `4096`; `_int_kwarg()` 只接受正数, 否则用默认 | 无 |
| `temperature` | `gateway_chat_model.py:62` | provider 调用默认 temperature | 非数值会让 SDK 参数非法 | 默认 `0.7`; `_float_kwarg()` 解析失败用默认 | 无 |
| `phase_name` | `gateway_chat_model.py:63` | fallback event 所属 phase | Studio trace 需要定位 phase | 可选; event 缺省 `<gateway>` | 无 |
| `event_callbacks` | `gateway_chat_model.py:64` | gateway 自己发事件的 callback 列表 | 没 callback 时不能尝试发事件 | `__init__` 把 `callbacks` 转 tuple | 无 |
| `probe_before_call` | `gateway_chat_model.py:65` | 真实调用前是否 probe provider | probe 可提前避开不可用 provider | 默认 `True`; false 时直接 dispatch | 无 |
| `thinking_enabled` | `gateway_chat_model.py:66` | reasoning 开关覆盖 | 区分显式 false 和自动读取 model_def | `None` 时用 `candidate.model_def.reasoning` | 无 |
| `bound_tools` | `gateway_chat_model.py:67` | 已转换成 OpenAI tool schema 的工具列表 | Agent ReAct 必须把工具传给 provider | 默认空 tuple; `bind_tools()` 通过 `_normalise_tool()` 生成 | `[F-v3-tool-argument-invalid]` 若未来结构化 |
| `tool_choice` | `gateway_chat_model.py:68` | LangChain tool choice 透传 | 错误 tool_choice 会改变模型调用策略 | 可选 string, 传给 dispatch | provider 原生异常 |
| `tool_kwargs` | `gateway_chat_model.py:69` | 保存 bind_tools 的额外 kwargs | clone 后不能丢 LangChain 绑定参数 | 默认 `{}`; `bind_tools()` 保存但当前 `_generate()` 不直接用 | 无 |

### `bind_tools()` 字段

| 字段 | src | 干什么 | 为何校验 | 当前判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `tools` | `gateway_chat_model.py:196` | LangChain 工具定义输入 | provider call 需要 OpenAI-compatible tool schema | `Sequence[ToolSpec]`; 每项由 `_normalise_tool()` 转换 | `[F-v3-tool-argument-invalid]` 候选 |
| `tool_choice` | `gateway_chat_model.py:198` | 绑定后的工具选择策略 | clone 后需要保留调用方策略 | 可选 string, 传入新 `GatewayChatModel` | provider 原生异常 |
| `**kwargs` | `gateway_chat_model.py:199` | LangChain tool binding 额外参数 | clone 时不能吞掉 caller metadata | 转成 `tool_kwargs={key: value}` | 无 |
| return `Runnable[LanguageModelInput, AIMessage]` | `gateway_chat_model.py:200` | 满足 LangChain `bind_tools` surface | Agent runtime 依赖 runnable model | 返回携带同一 role/config/tool metadata 的 clone | 无 |

### `_generate()` fallback 字段

| 字段 / 变量 | src | 干什么 | 为何校验 | 当前判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `messages` | `gateway_chat_model.py:117` | LangChain 消息输入 | provider manager 需要 dict message shape | `_langchain_messages_to_dict()` 转换 role/content/tool_calls | provider 原生异常 |
| `kwargs.max_tokens` | `gateway_chat_model.py:154` | per-call token override | 非正数不能透传 | `_int_kwarg()` 解析正数, 否则用 `self.max_tokens` | 无 |
| `kwargs.temperature` | `gateway_chat_model.py:155` | per-call temperature override | 非数值不能透传 | `_float_kwarg()` 解析, 否则用 `self.temperature` | 无 |
| `kwargs.reasoning` | `gateway_chat_model.py:156` | per-call reasoning override | reasoning 默认来源有三层, 需要优先级明确 | `_bool_kwarg(kwargs.reasoning, self.thinking_enabled or candidate.model_def.reasoning)` | 无 |
| `candidate` | `gateway_chat_model.py:127` | 当前尝试的 provider/model | fallback 必须按 call_chain 顺序 | 遍历 `resolved_role.call_chain` | `[F-v3-gateway-all-providers-failed]` 全部失败 |
| provider mark-down | `gateway_chat_model.py:129` | 跳过短期已不可用 provider | 避免重复打已失败 provider | `LLMClientManager._is_provider_marked_down()` 为 true 时 continue | 无 |
| probe result | `gateway_chat_model.py:140` | 调用前健康检查 | probe 失败不应进入真实请求 | `probe_before_call` 且 `_probe_provider()` false 时 mark down + continue | 无 |
| dispatch response | `gateway_chat_model.py:151` | 真实 provider 返回 | 成功后要转换 LangChain `ChatResult` | `_dispatch_provider_call()` 成功后 `_build_chat_result()` | provider 原生异常 |
| `failures` | `gateway_chat_model.py:125` | 收集失败链文本 | 当前最终异常只有字符串, Studio 不好解析 | 每次 failover exception 追加 `"candidate: type: msg"` | MVP0 `[F-v3-gateway-all-providers-failed]` payload |
| fallback event | `gateway_chat_model.py:177` | 向 callbacks 发 `LLMFallbackEvent` | tracing 需要知道从哪个 candidate 降到哪个 candidate | `_emit_real_fallback_event(exc, candidate, to_provider=...)` | 当前 callback 异常只 log |
| final RuntimeError | `gateway_chat_model.py:190` | 所有候选失败后终止调用 | 纯文本无法稳定驱动 Studio UI | `failures` 空则 `no available candidates`, 否则拼接字符串 | MVP0 `[F-v3-gateway-all-providers-failed]` |

## PredictGatewayChatModel mock 短路

Predict 模式在 `ModelResolver.resolve()` 检测 `_graph_agent_predict_mock_strategy` 后返回 `PredictGatewayChatModel`: `packages/graph-agent/src/graph_agent/models/resolver.py:100`. 该 subclass 继承 gateway surface, 但 `_generate()` 不访问 provider, 直接从 mock strategy 选择 payload: `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:61`.

| 字段 / 方法 | src | 干什么 | 为何校验 | 当前判定逻辑 | 错误码 |
|---|---|---|---|---|---|
| `mock_strategy` | `interception.py:32` | Predict 数据源策略 | 没有策略就无法决定 golden/manual/heuristic | `__init__` 必传并写入 kwargs | 当前 Pydantic error |
| `_generate(messages, stop, run_manager, **kwargs)` | `interception.py:61` | 同步 mock 响应 | Predict 不能误打真实 provider | 丢弃输入消息, 调 `_select_mock_payload()` | 无 |
| `_agenerate(...)` | `interception.py:73` | async mock 响应 | async consumer 也必须短路 | 调同步 `_generate()` | 无 |
| `_astream(...)` | `interception.py:84` | streaming mock chunk | 流式预测不能访问 provider | yield 一个完整 fake chunk | 无 |
| `bind_tools()` | `interception.py:107` | 工具绑定后保持 Predict subclass | 如果返回父类 clone, mock 短路会丢失 | 返回新的 `PredictGatewayChatModel` 并保留 `mock_strategy` | 无 |
| `_select_mock_payload()` | `interception.py:142` | 选择 golden/manual/heuristic payload | mock source 需要可追踪 | 优先 golden, 再 manual/copilot, 最后 heuristic stub | 无 |

## 跟其他子模块关系

| 子模块 | gateway 提供什么 | 对方负责什么 | 边界 |
|---|---|---|---|
| skill-resolution | 平行概念: gateway 解析 `llm_role -> BaseChatModel`; skill-resolution 解析 `target_skill -> Path` | SkillResolverProtocol 和 registry skill root 校验 | 两者都应变成外部 DI, 但解析对象不同 |
| skill-compilation | 提供运行期可用的模型解析能力 | 编译 `GRAPH.md` / Agent `llm_role` 字段, 静态检查 role 是否存在 | gateway 不解析 Markdown, 不做 AST |
| execution-runtime | 返回 LangChain model, 支持 `bind_tools()` 和 `invoke()` | 在 LLM phase / Agent phase 调 resolver, 编排 ReAct、StateMapper、finish_task | gateway 不决定 phase 顺序和 state merge |
| tracing-and-observability | 发 `LLMFallbackEvent`, 提供 provider/model metadata | 定义事件 schema、写 trace、统一 callback 底座 | gateway 不自定义 trace 文件格式 |
| state-and-io-contract | 不直接提供 state 能力 | phase input/output 切片与回写 | gateway 只消费 prompt messages 和 tools |
| Studio backend | 当前 Engine 内置 resolver 读取配置; MVP0 后应由 Studio 注入 resolver | 管理凭证、provider 配置、角色 registry | Engine 不应直接读取 Studio settings |

## 当前主要缺口

- `ModelResolver` 仍通过 `get_model_resolver()` singleton 进入旧 harness, 代码在 `packages/graph-agent/src/graph_agent/models/resolver.py:286` 和 `packages/graph-agent/src/graph_agent/core/harness.py:373`; 这和 Q-R-P0-1 的“外层 Studio 注入”方向不一致。
- `GatewayChatModel._generate()` 全候选失败时抛 `RuntimeError` 字符串, 而 `AllProvidersFailedError` 也只是兼容异常, 尚未携带稳定 `[F-v3-gateway-*]` code。
- `LLMFallbackEvent` 当前直接从 gateway callback loop 发出, 需要和 V0.3.0 tracing 统一底座对齐。
