# graph-agent-gateway V0.3.0 代码逻辑翻译

本文解释 V0.3.0 完成态下 `graph-agent-gateway` 子模块的代码逻辑: 它如何把 `llm_role` / tier 解析成 LangChain 兼容的 `BaseChatModel`, 如何携带 provider fallback chain, 如何在真实 provider 失败时发出 fallback 事件, 以及 Predict 模式如何短路真实模型调用。它不是 baseline 的现状盘点, 也不是 mvp0-alignment 的任务清单; 它把 gateway 的字段、校验理由和跨模块边界翻译成自然语言。

核心源码锚点:

- `GatewayChatModel` 是 LangChain `BaseChatModel` adapter, 字段定义和 `_generate()` fallback loop 在 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:54`, `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:115`。
- `ModelResolver.resolve()` 读取 `llm_roles.yaml` 解析产物, 返回 `GatewayChatModel` 或 `PredictGatewayChatModel`: `packages/graph-agent/src/graph_agent/models/resolver.py:57`。
- `ResolvedProvider` / `ResolvedRole` 是 gateway runtime 实际消费的候选链结构: `packages/graph-agent/src/graph_agent/config/llm_config.py:90`, `packages/graph-agent/src/graph_agent/config/llm_config.py:101`。
- 当前旧 `ModelResolverProtocol` 只存在于 legacy phase node 容器, 签名还没覆盖 `thinking_enabled`: `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py:41`。
- Predict 模式由 `PredictGatewayChatModel` 继承 gateway surface 并覆盖 `_generate()` / `bind_tools()`: `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:29`。
- provider 全部失败的兼容异常是 `AllProvidersFailedError`, 当前只有 `tier`, `errors`, `context`: `packages/graph-agent/src/graph_agent/core/exceptions.py:256`。
- fallback 事件模型是 `LLMFallbackEvent`, 真实 emit 点在 gateway `_emit_real_fallback_event()`: `packages/graph-agent/src/graph_agent/callbacks/events.py:240`, `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py:263`。

## 这个模块只管模型网关

`graph-agent-gateway` 的职责是把业务侧的逻辑模型角色解析成可调用模型对象, 并在模型对象内部处理 provider/model 候选链。它不解析 `GRAPH.md`, 不决定 phase 执行顺序, 不做 state 切片, 不拥有 Studio registry, 也不定义 trace 文件格式。

| 事项 | 归属 | 说明 |
|---|---|---|
| `llm_role -> BaseChatModel` | graph-agent-gateway | `ModelResolver.resolve()` 返回 LangChain-compatible model |
| `target_skill -> Path` | skill-resolution | 平行 DI 模块, 由 `SkillResolverProtocol` 处理 |
| Agent / LOGIC / SUBGRAPH 调度 | execution-runtime | 拿到 model 后决定何时 `invoke()` |
| `data/flow/messages/run_id` | state-and-io-contract | gateway 只消费 messages, 不管理黑板 |
| `LLMCallEvent` / `LLMFallbackEvent` schema | tracing-and-observability | gateway 只负责在真实 fallback 点 emit |

难点 1: **候选链**。resolver 只组装候选链, gateway runtime 才真正接力调用 provider。把这两步混在一起, trace 会把"可能 fallback"误记成"已经 fallback"。

## llm_roles.yaml 解析入口

配置层把 YAML 拆成 `ModelDef`, `ProviderDef`, `RoleDef`, 再展开为 `ResolvedRole` 和 `ResolvedProvider`。文件路径解析顺序是显式参数、`GRAPH_AGENT_ROLES_PATH`、向上搜索 `config/llm_roles.yaml`、内置最小默认配置: `packages/graph-agent/src/graph_agent/config/llm_config.py:570`。

### ModelDef 字段

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `code` | 模型代号, 被 role、peer group、model override 引用 | 代号错会让 resolver 找不到模型或走错 provider chain | `_parse_models()` 用 YAML key 作为 `code`: `llm_config.py:263` | 当前 `ValueError` / V0.3.0 候选 `[F-v3-gateway-role-not-configured]` |
| `name` | 人类可读模型名 | Studio 展示和日志需要可读名 | 缺省为 `code`: `llm_config.py:264` | 无 |
| `reasoning` | 模型默认 reasoning 开关 | gateway `_generate()` 在未显式覆盖时要用它决定请求参数 | `bool(data.get("reasoning", False))`: `llm_config.py:265` | 无 |
| `min_max_tokens` | 默认输出 token 上限 | provider 调用必须有正数 token 上限 | `int(data.get("min_max_tokens", 4096))`: `llm_config.py:266` | 当前 `ValueError`; V0.3.0 gateway config code |
| `max_input_tokens` | 模型输入窗口上限 | resolver profile 和 Studio 预算需要知道输入容量 | 只有 YAML 值是 `int` 时保留, 否则 `None`: `llm_config.py:267` | 无 |
| `fc_supported` | function calling 支持标记 | 工具绑定前需要知道模型能力 | `bool(data.get("fc_supported", False))`: `llm_config.py:272` | 无 |
| `providers` | provider_code 到真实 model name 的映射 | 没有映射就无法调用该 provider 下的模型 | `dict(data.get("providers", {}))`: `llm_config.py:273`; cross reference 再校验 provider 是否存在 | 当前 `ValueError`; V0.3.0 gateway config code |
| `provider_options` | provider/model 组合参数 | 同一模型在不同 provider 下的 token 或能力上限可能不同 | 每个 value 转 dict: `llm_config.py:274` | 无 |

### ProviderDef 字段

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `code` | provider 注册 key | fallback、usage、mark-down 都按 provider code 聚合 | `_parse_providers()` 用 YAML key: `llm_config.py:286` | 当前 `ValueError`; V0.3.0 gateway config code |
| `name` | provider 展示名 | UI 和日志需要可读名称 | 缺省为 `code`: `llm_config.py:287` | 无 |
| `type` | provider adapter 类型 | dispatch 必须知道走 OpenAI compatible、Gemini、Anthropic 等哪条路径 | 缺省 `"openai_compatible"`: `llm_config.py:288` | provider 原生异常 / V0.3.0 gateway config code |
| `api_key_env` | 主 API key 环境变量 | provider 调用需要凭证来源 | 缺省空字符串: `llm_config.py:289` | provider 原生异常 |
| `api_key_env_fallback` | 备用 API key 环境变量 | 支持平滑切换凭证 | 缺省空字符串: `llm_config.py:290` | provider 原生异常 |
| `base_url` | provider 基础 URL | OpenAI compatible 请求需要 endpoint | 缺省空字符串: `llm_config.py:291` | provider 原生异常 |
| `llm_base_url` | WaveSpeed LLM 专用 endpoint | 同一 provider 可能区分图片/LLM endpoint | 缺省空字符串: `llm_config.py:292` | provider 原生异常 |
| `proxy_env` | 代理环境变量名 | 网络路径可能由部署环境控制 | 缺省空字符串: `llm_config.py:293` | provider 原生异常 |
| `timeout` | provider 请求超时秒数 | 不校验会导致永久等待或过早失败 | `int(data.get("timeout", 120))`: `llm_config.py:294` | 当前 `ValueError`; V0.3.0 gateway config code |
| `trust_env` | HTTP client 是否信任环境代理 | 部署环境下代理行为需要显式控制 | `bool(data.get("trust_env", False))`: `llm_config.py:295` | 无 |
| `retry_strategy` | provider 内部重试策略名 | retry 行为不能靠代码猜 | 缺省空字符串: `llm_config.py:296` | provider 原生异常 |

### RoleDef 与 RoleModelEntry 字段

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `RoleDef.name` | role 注册名 | `llm_role` / tier 用它查询 | `_parse_roles()` 用 YAML key: `llm_config.py:320` | `[F-v3-gateway-role-not-configured]` 目标 |
| `temperature` | role 默认温度 | 解析出的 model 要有稳定默认采样参数 | `float(data.get("temperature", 0.7))`: `llm_config.py:321` | 当前 `ValueError`; V0.3.0 gateway config code |
| `model_fallback` | 是否允许 role 内多模型 fallback | 不校验会误把单模型 role 扩成多模型 | `bool(data.get("model_fallback", False))`: `llm_config.py:322` | 无 |
| `active_model` | 首选 model code | fallback chain 的第一段从这里开始 | `data.get("active_model", "")`: `llm_config.py:323`; cross reference 校验存在 | 当前 `ValueError`; V0.3.0 gateway config code |
| `system_prompt_prefix` | role 级 prompt 前缀 | cognitive prompt 需要拿到模型/角色方法论前缀 | 缺省空字符串: `llm_config.py:324`; resolve 时 `.strip()` | 无 |
| `models` | role 可用模型集合 | role 的 call chain 只能从这里展开 | `_parse_roles()` 遍历 `data.get("models")`: `llm_config.py:312` | 当前 `ValueError`; V0.3.0 gateway config code |
| `RoleModelEntry.model_code` | role 内模型 key | 与 `ModelDef.code` 对齐 | `_parse_roles()` 用 models map key: `llm_config.py:315` | 当前 `ValueError`; V0.3.0 gateway config code |
| `RoleModelEntry.provider_codes` | 该模型在 role 中允许的 provider 顺序 | provider 顺序就是调用优先级 | list 化 `providers`: `llm_config.py:316` | 当前 `ValueError`; V0.3.0 gateway config code |

## ResolvedRole / ResolvedProvider

`ResolvedRole` 是 resolver 交给 gateway 的完整调用计划, `ResolvedProvider` 是其中一个具体 provider/model 候选。

### ResolvedProvider 字段

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `provider_code` | provider key, 也是 usage 和 mark-down 维度 | code 错会把健康状态记到错误桶 | `resolve_role()` 从 `entry.provider_codes` 取值并要求 provider 存在: `llm_config.py:169` | 当前 config `ValueError`; V0.3.0 gateway config code |
| `provider_def` | provider 连接定义 | gateway dispatch 需要 endpoint、key、timeout 等信息 | `self.providers.get(pc)` 必须存在: `llm_config.py:170` | 同上 |
| `model_name` | provider 下真实模型名 | model code 不是真实 SDK model name | `model_def.providers.get(pc)` 必须存在: `llm_config.py:174` | 同上 |
| `model_def` | 模型能力定义 | gateway 读取 reasoning、token、profile | `self.models.get(model_code)` 必须存在: `llm_config.py:164` | 同上 |
| `provider_options` | 当前 provider/model 的局部参数 | `_default_max_tokens()` 会读取 `max_max_tokens` | `model_def.provider_options.get(pc, {})`: `llm_config.py:182` | 无 |

### ResolvedRole 字段

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `role_name` | 解析后的 role 名或 `_model_override::<code>` | trace 和错误需要定位 role | `resolve_role()` 返回入参 role name: `llm_config.py:198`; `resolve_model()` 构造 synthetic role: `llm_config.py:244` | `[F-v3-gateway-role-not-configured]` 目标 |
| `temperature` | 传给 `GatewayChatModel.temperature` | provider 请求需要默认温度 | role resolution 用 `role.temperature`: `llm_config.py:199`; model override 用 `0.7`: `llm_config.py:245` | 当前 `ValueError`; V0.3.0 gateway config code |
| `system_prompt_prefix` | role 级 prompt 前缀 | cognitive prompt 需要稳定字符串 | `(role.system_prompt_prefix or "").strip()`: `llm_config.py:200`; override 为空 | 无 |
| `active_model_code` | 首选模型代号 | peer fallback 需要知道 active model 所属组 | role resolution 用 `role.active_model`: `llm_config.py:201`; override 用 model_code | `[F-v3-gateway-role-not-configured]` 目标 |
| `model_fallback` | 标记 role 内是否允许多模型 | gateway 不自己解释 YAML, 只消费展开结果 | role resolution 复制 `role.model_fallback`: `llm_config.py:202`; override 为 `False` | 无 |
| `call_chain` | 按优先级排列的候选列表 | 空链意味着没有任何 provider 可调用 | `resolve_role()` 逐模型/逐 provider append: `llm_config.py:183`; resolver 空链抛 `AllProvidersFailedError` | `[F-v3-gateway-all-providers-failed]` 目标 |

## RoleConfigData 热加载与交叉校验

`RoleConfigData` 持有解析后的全量 registry。`_RoleConfigHolder.get()` 负责按路径和 mtime 热加载, 失败时如果已有旧配置就回退旧配置: `packages/graph-agent/src/graph_agent/config/llm_config.py:624`, `packages/graph-agent/src/graph_agent/config/llm_config.py:658`。

| 字段 / 函数 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `models` | model registry | role 和 override 都引用它 | `RoleConfigData.models` 默认 `{}`: `llm_config.py:128` | gateway config code |
| `providers` | provider registry | model provider mapping 依赖它 | `RoleConfigData.providers` 默认 `{}`: `llm_config.py:129` | gateway config code |
| `roles` | role registry | `llm_role` 查询入口 | `RoleConfigData.roles` 默认 `{}`: `llm_config.py:130` | `[F-v3-gateway-role-not-configured]` 目标 |
| `peer_model_groups` | 同类模型备用组 | role 自己链耗尽后可追加 peer 模型 | `_parse_peer_model_groups()` 过滤未知 model: `llm_config.py:488` | warning; V0.3.0 gateway config code |
| `circuit_breaker` | provider 熔断阈值配置 | mark-down 策略需要配置来源 | `_parse_circuit_breaker()` 非 dict 回默认: `llm_config.py:529` | warning |
| `single_model_roles` | 禁止 peer fallback 的 role | 某些 phase 必须固定模型失败即失败 | `_parse_single_model_roles()` 只保留已知 role: `llm_config.py:555` | warning |
| `_validate_cross_references()` | 检查 model/provider/role 链路完整 | 交叉引用错会在运行时才发现无候选 | 收集错误并让 `_load_config_file()` 抛 `ValueError`: `llm_config.py:330`, `llm_config.py:458` | gateway config code |
| `get_role_config()` | 取得热加载配置 | resolver 不直接读 YAML 文件 | 调 `_holder.get()`: `llm_config.py:678` | config load exception |

## ModelResolverProtocol DI

V0.3.0 的 GW-1 决策是: Engine 不应在生产路径自己创建模型 resolver, 而是由外层注入 `ModelResolverProtocol`。当前源码已有 legacy protocol, 但它位于 `core/phase_nodes/base.py`, 且签名还缺 `thinking_enabled` 和 `**kwargs`: `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py:41`。

### 目标协议字段

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前 / 目标判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `model_resolver` | 外部注入模型解析能力 | 未注入时 Engine 会回退 singleton 或运行到缺模型才失败 | 目标: 含 LLM/Agent phase 的入口必须传入, 实现 `resolve()` | `[F-v3-gateway-resolver-missing]` |
| `resolve()` | 把 role/override 解析成 `BaseChatModel` | execution-runtime 只应依赖 LangChain surface | 当前 legacy protocol 返回 `BaseChatModel`: `phase_nodes/base.py:44`; 目标签名对齐真实 resolver | `[F-v3-gateway-resolver-missing]` / interface validation |
| `role_name` | 逻辑角色 / tier | 角色未配置不能默默走错模型 | 当前 `ModelResolver.resolve()` 接收可空 role: `resolver.py:59` | `[F-v3-gateway-role-not-configured]` |
| `thinking_enabled` | reasoning override | Studio policy、phase override、model default 要有清晰优先级 | 当前真实 resolver 有字段: `resolver.py:61`; legacy protocol 缺字段 | resolver interface validation |
| `model_override` | phase 级 model pin | 未知 override 不应静默换成默认 role | 当前先 `cfg.resolve_model()` 失败再 warning fallback: `resolver.py:140` | `[F-v3-gateway-role-not-configured]` 或 future config code |
| `callbacks` | callback 链 | fallback event 要进入统一 tracing | 当前真实 resolver 传给 gateway: `resolver.py:122` | tracing contract |
| `phase_name` | 事件所属 phase | fallback event 和 ModelResolved event 需要定位节点 | 当前真实 resolver 传给 gateway: `resolver.py:123` | `[F-v3-runtime-phase-failed]` fallback |
| return `BaseChatModel` | LangChain runtime object | Agent runtime 依赖 `invoke()` / `bind_tools()` | 当前返回 `GatewayChatModel` 或 `PredictGatewayChatModel`: `resolver.py:104`, `resolver.py:117` | interface validation |

## ModelResolver.resolve()

`ModelResolver.resolve()` 不做 provider health check。它只读取 role config, 展开/追加候选链, 然后创建模型对象。真实 provider 是否可用, 要等 `GatewayChatModel._generate()` 调用时才知道。

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `stats.total_resolves` | 统计解析次数 | 诊断重复解析和 cache 行为 | 每次 `_bump_stat("total_resolves")`: `resolver.py:68` | 无 |
| `cfg` | 当前 role config | resolver 不能绕过热加载配置 | `get_role_config()`: `resolver.py:70` | config load exception |
| `_resolve_configured_role()` | 解析 role 或 model override | 先处理显式 override, 再走 role | `model_override` 命中返回 synthetic `ResolvedRole`; role 不存在返回 `None`: `resolver.py:133` | `[F-v3-gateway-role-not-configured]` 目标 |
| `_fallback_to_minimal_factory()` | 未配置 role 的兼容 fallback | 当前可运行 ad-hoc model, 但生产路径容易隐藏配置错误 | `resolved is None` 时调用: `resolver.py:76` | V0.3.0 默认应改结构化 role-not-configured |
| `_append_peer_model_fallbacks()` | 追加 peer group 候选 | 同级模型备用不能在 YAML 展开时丢失 | 有 peer group、非 override、非 single role 时追加: `resolver.py:164` | 无 |
| empty `call_chain` | 检测没有任何候选 | 空链不能交给 gateway runtime | `if not resolved.call_chain` 抛 `AllProvidersFailedError`: `resolver.py:90` | `[F-v3-gateway-all-providers-failed]` 目标 |
| Predict branch | 走 mock subclass | Predict 不能打真实 provider | resolver 带 `_graph_agent_predict_mock_strategy` 时返回 Predict model: `resolver.py:100` | 无 |
| live branch | 走真实 gateway | 正常运行要调用 provider chain | 返回 `GatewayChatModel`: `resolver.py:117` | provider runtime errors |

`ModelResolverStats` 目前有四个字段: `total_resolves`, `cache_hits`, `provider_failures`, `circuit_breaks`: `packages/graph-agent/src/graph_agent/models/resolver.py:33`. 当前只有 `total_resolves` 被更新; 其它三个是诊断预留字段。

## GatewayChatModel 初始化字段

`GatewayChatModel` 是 Pydantic model + LangChain chat model adapter。它的字段既要满足 LangChain surface, 又要保存 gateway 自己的候选链和事件回调。

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `role_name` | 当前模型对应的逻辑 role | trace、错误和 identifying params 都依赖它 | `__init__` 必传并写入 Pydantic 字段: `gateway_chat_model.py:73` | `[F-v3-gateway-role-not-configured]` 目标 / Pydantic error |
| `resolved_role` | 完整 `ResolvedRole` 候选链 | `_generate()` 没有它无法遍历 provider | `__init__` 必传: `gateway_chat_model.py:74` | Pydantic error |
| `max_tokens` | 默认输出 token 上限 | 非正数不能传给 provider | 默认 `4096`; per-call `_int_kwarg()` 只接受正数: `gateway_chat_model.py:76`, `gateway_chat_model.py:464` | 无 |
| `temperature` | 默认采样温度 | 非数值会让 provider 请求非法 | 默认 `0.7`; per-call `_float_kwarg()` 解析: `gateway_chat_model.py:77`, `gateway_chat_model.py:469` | provider 原生异常 |
| `callbacks` / `event_callbacks` | fallback event sink | 没有 callback 就不能发 trace event | `__init__` 转 tuple: `gateway_chat_model.py:78`, `gateway_chat_model.py:93` | 无 |
| `phase_name` | 当前 phase 名 | fallback event 需要归属 phase | 可选; event 缺省 `<gateway>`: `gateway_chat_model.py:79`, `gateway_chat_model.py:274` | tracing event validation |
| `probe_before_call` | 调用前是否 probe provider | 可提前避开明显不可用 provider | 默认 `True`: `gateway_chat_model.py:80` | 无 |
| `thinking_enabled` | reasoning override | 区分显式 false 和模型默认 | 可选; `_generate()` 中 `None` 时用 `candidate.model_def.reasoning`: `gateway_chat_model.py:156` | 无 |
| `bound_tools` | OpenAI-compatible tool schema tuple | Agent ReAct 需要工具透传给 provider | `bind_tools()` 归一化后写入 clone: `gateway_chat_model.py:211` | tool schema validation / provider 原生异常 |
| `tool_choice` | provider tool_choice 策略 | 错误策略会改变模型选工具方式 | 可选 string, `_generate()` 透传: `gateway_chat_model.py:165` | provider 原生异常 |
| `tool_kwargs` | 保存 bind_tools 额外参数 | clone 不能丢 LangChain metadata | dict 化保存: `gateway_chat_model.py:98`, `gateway_chat_model.py:213` | 无 |

## GatewayChatModel._generate() fallback loop

`_generate()` 是 gateway 真正调用 provider 的地方。它先把 LangChain messages 转成 provider manager 能识别的 dict, 再按 `resolved_role.call_chain` 顺序尝试候选。

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `messages` | LangChain 输入消息 | provider dispatch 需要统一 role/content/tool_calls 形状 | `_langchain_messages_to_dict(messages)`: `gateway_chat_model.py:124` | provider 原生异常 |
| `failures` | 收集失败链文本 | 全部失败后要解释候选为何耗尽 | 每次捕获异常 append `"candidate: Type: msg"`: `gateway_chat_model.py:175` | `[F-v3-gateway-all-providers-failed]` 目标 payload |
| `candidate` | 当前 `ResolvedProvider` | fallback 必须按配置顺序 | `enumerate(self.resolved_role.call_chain)`: `gateway_chat_model.py:127` | 空链由 resolver 拦截 |
| mark-down skip | 跳过已短期失败的 provider/model | 避免重复打已知不可用候选 | `_is_provider_marked_down()` 为真时 continue: `gateway_chat_model.py:129` | 无 |
| probe | 调用前健康检查 | probe 失败时不应进入真实请求 | `probe_before_call` 且 `_probe_provider()` false 时 mark down: `gateway_chat_model.py:140` | 无 |
| `before_calls` | usage 记录前的调用数 | 防止重复记录 usage | `_usage_total_calls(candidate.provider_code)`: `gateway_chat_model.py:150` | 无 |
| `_dispatch_provider_call()` | 真实 provider 请求 | gateway 的核心外部调用点 | 传入 candidate、messages、tokens、temperature、reasoning、tools、tool_choice: `gateway_chat_model.py:151` | provider 原生异常 |
| `max_tokens` override | 单次调用 token 覆盖 | 非正数不能覆盖默认 | `_int_kwarg(kwargs.get("max_tokens"), self.max_tokens)`: `gateway_chat_model.py:154` | 无 |
| `temperature` override | 单次调用温度覆盖 | 非数值不能覆盖默认 | `_float_kwarg(kwargs.get("temperature"), self.temperature)`: `gateway_chat_model.py:155` | 无 |
| `reasoning` override | 单次 reasoning 覆盖 | 优先级必须明确 | `kwargs.reasoning` > `thinking_enabled` > `candidate.model_def.reasoning`: `gateway_chat_model.py:156` | 无 |
| `tools` | provider tool schema | 没有工具时应传 `None`, 不是空列表语义 | `list(self.bound_tools) or None`: `gateway_chat_model.py:164` | provider 原生异常 |
| success result | LangChain `ChatResult` | runtime 只理解 LangChain 返回 | 成功后 `_record_usage_if_needed()` 再 `_build_chat_result()`: `gateway_chat_model.py:167`, `gateway_chat_model.py:173` | 无 |
| failover exceptions | 可 fallback 的异常集合 | 只有网络、timeout、provider runtime 等错误才进 fallback | 捕获 `_RUNTIME_FAILOVER_EXCEPTIONS`: `gateway_chat_model.py:36`, `gateway_chat_model.py:174` | `[F-v3-gateway-all-providers-failed]` 目标 |
| fallback event | 记录真实 provider 切换 | tracing 需要知道谁失败、切到谁 | 捕获异常后 `_emit_real_fallback_event()`: `gateway_chat_model.py:177` | tracing event validation |
| final error | 全候选失败 | UI 需要结构化 code 和候选链 | 当前抛纯文本 `RuntimeError`: `gateway_chat_model.py:190` | 目标 `[F-v3-gateway-all-providers-failed]` |

GW-2 的结构化错误码应落在 final error 上: 当前 `RuntimeError` 的 `detail` 字符串需要升级为 payload, 至少包括 `code`, `role_name`, `phase_name`, `failed_provider_codes`, `last_error_chain`, `message`, `context`。

## Tool Binding And Message Conversion

Agent runtime 会调用 `chat_model.bind_tools(all_tools)`, gateway 必须返回仍然可 invoke 的 clone, 并保留原 role、候选链、callbacks 和 LangChain 参数。

| 字段 / 函数 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `bind_tools.tools` | LangChain 工具定义输入 | provider 需要 OpenAI-compatible tool schema | 每项经 `_normalise_tool()`: `gateway_chat_model.py:196`, `gateway_chat_model.py:211` | tool schema validation / provider 原生异常 |
| `tool_choice` | 绑定后的工具选择策略 | clone 后要保留 caller 策略 | 写入新 `GatewayChatModel.tool_choice`: `gateway_chat_model.py:212` | provider 原生异常 |
| `**kwargs` | LangChain binding 扩展参数 | 不能吞掉 caller metadata | 保存为 `tool_kwargs`: `gateway_chat_model.py:213` | 无 |
| clone inherited fields | 保持原模型行为 | 绑定工具不应改变 role、候选链、callbacks、profile | clone 显式复制 name/cache/tags/profile 等字段: `gateway_chat_model.py:214` | 无 |
| `_normalise_tool()` | 把工具变成 OpenAI tool schema | provider dispatch 需要统一 schema | 已是 `type:function` 直接保留; 有 `name` 的 mapping 包成 function; 其它走 `convert_to_openai_tool()`: `gateway_chat_model.py:355` | tool schema validation |
| `_langchain_messages_to_dict()` | LangChain message 转 provider message | provider manager 不直接消费 LangChain message 对象 | 写 `role`, `content`, 可选 `name`, `tool_call_id`, `reasoning_content`, `tool_calls`: `gateway_chat_model.py:371` | provider 原生异常 |
| `_message_role()` | 映射 human/ai/system/tool role | role 错会改变 provider 语义 | human->user, ai->assistant, system/tool 保留, 其它 user: `gateway_chat_model.py:423` | 无 |
| `_langchain_tool_calls_to_openai()` | AIMessage tool_calls 转 OpenAI 形状 | 多轮工具调用需要带 id/name/arguments | 只转换有 string name 的 mapping: `gateway_chat_model.py:401` | 无 |

## ChatResult And Usage

provider response 需要被收口成 LangChain `ChatResult`, 同时携带 provider/model/usage metadata。

| 字段 / 函数 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `_usage_from_response()` | 提取 token usage | 成本统计和 trace 依赖 token 数 | 缺 usage 时返回 0; total 为 0 时用 prompt+completion: `gateway_chat_model.py:324` | 无 |
| `_additional_kwargs_from_response()` | 保留 tool_calls / reasoning_content | Agent loop 需要 tool_calls, debug 需要 reasoning | mapping 追加原 additional kwargs, 再补指定 key: `gateway_chat_model.py:341` | 无 |
| `finish_reason` | 模型停止原因 | Studio 和 retry 判断需要知道停止类型 | `_optional_text(response.get("finish_reason"))`: `gateway_chat_model.py:233` | 无 |
| `response_metadata` | AIMessage 元数据 | downstream 能定位 provider/model/usage | 包含 provider, model, finish_reason, usage: `gateway_chat_model.py:235` | 无 |
| `llm_output.token_usage` | LangChain 输出统计 | legacy callback 和 tracing 读取这里 | 写入 `ChatResult.llm_output`: `gateway_chat_model.py:256` | 无 |
| `_record_usage_if_needed()` | 补记 provider usage | dispatch 可能已记录, gateway 只在需要时补记 | 如果 total_calls 已变则跳过; 否则 `record_usage()`: `gateway_chat_model.py:297` | 无 |

## LLMFallbackEvent Emit 链路

GW-3 的关键点是 fallback event 必须在真实 fallback 发生时发出。当前 emit 点已经在 gateway runtime catch block 之后, 但 callback 分发仍是 gateway 自己循环。

| 字段 / 链路 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `phase_name` | fallback 所属 phase | trace timeline 要标到具体节点 | `self.phase_name or "<gateway>"`: `gateway_chat_model.py:274` | tracing event validation |
| `from_provider` | 失败的 provider/model | UI 展示 fallback 起点 | `_candidate_id(candidate)`: `gateway_chat_model.py:275` | tracing event validation |
| `to_provider` | 下一个候选 | UI 展示 fallback 终点 | `_next_candidate_id(index + 1)`, 无可用则 `<none>`: `gateway_chat_model.py:180`, `gateway_chat_model.py:288` | tracing event validation |
| `reason` | 异常类型和消息 | debug 需要知道为什么 fallback | `f"{type(exc).__name__}: {exc}"`: `gateway_chat_model.py:277` | 最终耗尽归 `[F-v3-gateway-all-providers-failed]` |
| callback sink | 事件接收方 | 一个坏 callback 不能打断 provider failure 处理 | 遍历 `event_callbacks`, 异常只 log: `gateway_chat_model.py:279` | callback error 不覆盖原异常链 |
| event schema | typed event 定义 | tracing 不应解析自由文本 | `LLMFallbackEvent` 字段定义在 `events.py:240` | tracing event validation |

`LLMCallEvent` 是另一条链路: `TracingCallback.on_llm_call()` 构造 typed `LLMCallEvent`: `packages/graph-agent/src/graph_agent/callbacks/tracing.py:219`。gateway 本身只直接 emit fallback event, 不直接写 trace 文件。

## PredictGatewayChatModel

Predict 模式要求保留 gateway 的 LangChain surface, 但绝不能访问真实 provider。resolver 在检测到 `_graph_agent_predict_mock_strategy` 时返回 `PredictGatewayChatModel`: `packages/graph-agent/src/graph_agent/models/resolver.py:100`。

| 字段 / 方法 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `mock_strategy` | Predict 数据源策略 | 没有策略无法选择 golden/manual/heuristic 输出 | `__init__` 必传并塞入 kwargs: `interception.py:39`, `interception.py:48` | Pydantic error |
| `_generate()` | 同步 mock 输出 | Predict 不应触发 provider probe/dispatch/fallback | 丢弃真实 messages/kwargs, 调 `_select_mock_payload()`: `interception.py:61` | 无 |
| `_agenerate()` | async mock 输出 | async consumer 也不能打 provider | 调同步 `_generate()`: `interception.py:73` | 无 |
| `_astream()` | stream mock chunk | streaming Predict 也要短路 | yield 一个完整 `AIMessageChunk`: `interception.py:84` | 无 |
| `bind_tools()` | 工具绑定后保留 Predict subclass | 如果返回父类 clone, mock 短路会丢失 | 返回新的 `PredictGatewayChatModel`: `interception.py:107` | 无 |
| `_select_mock_payload()` | 选择 mock 数据源 | Predict 输出来源要可解释 | 优先 golden, 再 manual/copilot, 最后 heuristic stub: `interception.py:142` | 无 |
| `_mock_metadata()` | 写 mock 元数据 | trace 要能区分 mock 来源 | 调 `record_mock_source()`, 返回 `mocked_source`, `phase_name`, zero usage: `interception.py:187` | 无 |
| provider field | 标记 mock provider | 下游不应误以为是真 provider | `llm_output.provider = "predict_mock"`: `interception.py:179` | 无 |

Predict 模式不会产生真实 `LLMFallbackEvent`; 它没有真实 provider failure, 只记录 mock source。

## AllProvidersFailedError And Gateway Error Codes

当前源码有 `AllProvidersFailedError`, 但结构还不够 V0.3.0。它继承 `ExecutionError`, 保存 `tier` 和 `errors`, 最终 message 是 `"All providers failed for tier ..."`: `packages/graph-agent/src/graph_agent/core/exceptions.py:256`。

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 当前 / 目标判定逻辑 | (d) 错误码 |
|---|---|---|---|---|
| `tier` | 标识失败的 role/tier | Studio 需要定位模型配置项 | 当前构造参数名是 `tier`: `exceptions.py:261`; gateway 目标应统一为 `role_name` | `[F-v3-gateway-all-providers-failed]` |
| `errors` | per-provider 异常列表 | 需要保留每个候选失败原因 | 当前是 `list[tuple[str, Exception]]`: `exceptions.py:262` | 同上 |
| `context` | 结构化上下文 | UI 不应解析 message 字符串 | 继承 `GraphAgentError.context`: `exceptions.py:21`, `exceptions.py:264` | 同上 |
| `message` | 人类可读摘要 | CLI/log 仍需要可读文本 | 当前拼接 `details`: `exceptions.py:269` | 同上 |
| `code` | 机器可读错误码 | Studio 要稳定识别 gateway 错误 | 当前没有字段; V0.3.0 目标固定 code | `[F-v3-gateway-all-providers-failed]` |
| `phase_name` | 失败发生的 phase | Canvas 需要标红节点 | 当前没有字段; 可来自 `GatewayChatModel.phase_name` | 同上 |
| `failed_provider_codes` | 候选链列表 | UI 要展示全部候选耗尽 | 当前 `_generate()` 只有 strings; 目标结构化 item | 同上 |
| `last_error_chain` | 异常类型和消息链 | 工程排查需要 root cause | 当前 strings 在 `failures`; 目标 list[dict] | 同上 |

当前 `docs/engine/skill-spec/11-error-code-spec.md` 里还没有 `F-v3-gateway` 条目。V0.3.0 gateway 完成态需要补入 `[F-v3-gateway-resolver-missing]`, `[F-v3-gateway-role-not-configured]`, `[F-v3-gateway-all-providers-failed]`。

## Error Code 清单

| 错误码 | 阶段 | 当前源码状态 | 触发条件 |
|---|---|---|---|
| `[F-v3-gateway-resolver-missing]` | 装配 / 运行入口 | spec 尚未落地, alignment 目标 | 含 LLM/Agent phase 但未注入 `ModelResolverProtocol` |
| `[F-v3-gateway-role-not-configured]` | resolver | spec 尚未落地, alignment 目标 | `role_name` 或 `model_override` 未在 `llm_roles.yaml` 注册 |
| `[F-v3-gateway-all-providers-failed]` | provider runtime | spec 尚未落地, alignment 目标 | `call_chain` 为空或所有候选失败 |
| `RuntimeError("All LLM fallback candidates failed ...")` | provider runtime | 当前真实行为: `gateway_chat_model.py:190` | `_generate()` 遍历所有候选后没有成功 |
| `AllProvidersFailedError` | resolver / execution | 当前兼容异常: `exceptions.py:256` | resolver 发现 `resolved.call_chain` 为空 |
| config `ValueError` | config load | 当前真实行为: `llm_config.py:462` | YAML 顶层或 cross reference 校验失败 |
| provider 原生异常 | provider runtime | 当前被 fallback 捕获或冒泡 | SDK/network/provider 参数错误 |

## 跨模块接线

| 模块 | gateway 提供什么 | 对方提供什么 | 边界判断 |
|---|---|---|---|
| skill-compilation | 不参与 Markdown 编译 | 编译 `llm_role` 字段并做静态可达性目标 | gateway 不读 `GRAPH.md` |
| execution-runtime | `BaseChatModel`, `bind_tools()`, `invoke()` | phase loop、ReAct、finish_task、StateMapper | runtime 决定何时调用模型 |
| tracing-and-observability | `LLMFallbackEvent` emit 点和 model metadata | event schema、callback sink、trace 写盘 | gateway 不定义 trace 文件格式 |
| skill-resolution | 平行 DI 设计参考 | `SkillResolverProtocol` 和 target skill root 校验 | 一个解析模型, 一个解析 skill |
| Studio backend | 目标提供 `ModelResolverProtocol` 实现 | 模型配置、凭证、provider registry | Engine 不应生产路径读 Studio settings |
| Predict | 复用 GatewayChatModel surface | mock strategy、golden/manual/heuristic payload | Predict 不触发真实 provider fallback |

## V0.3.0 三个决策如何落地

| 决策 | 完成态代码语义 |
|---|---|
| GW-1 ModelResolverProtocol DI | `run_skill` / graph assembly / Agent runtime 顶层显式接收 `model_resolver`; Engine 不用 `get_model_resolver()` singleton 创建生产 resolver; 协议签名对齐 `ModelResolver.resolve()` 的 `thinking_enabled`, `model_override`, `callbacks`, `phase_name`。 |
| GW-2 结构化错误码 | `_generate()` 全候选失败和 resolver 空链统一抛结构化 gateway exception; payload 含 `code`, `role_name`, `phase_name`, `failed_provider_codes`, `last_error_chain`, `context`; Studio 不解析自由文本。 |
| GW-3 LLMFallbackEvent emit | fallback event 仍在真实 provider failure 后 emit, 但经统一 tracing callback 底座分发; callback 失败只影响 tracing, 不覆盖原 provider failure chain。 |

读代码时建议顺序是: 先看 `llm_config.py` 的配置结构和 `ResolvedRole`, 再看 `resolver.py` 如何返回 Gateway/Predict model, 然后看 `gateway_chat_model.py` 的 `_generate()` fallback loop, 最后看 `events.py` / `tracing.py` 如何消费 LLM call 与 fallback 事件。
