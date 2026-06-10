---
module: 11-inv-provider-profiles
doc: mvp1-alignment
status: drafted
verified_at: 2026-06-02
binds_design: ./baseline.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/provider_profiles.py:ProviderProfile/register_provider_profile/get_provider_profile/apply_provider_profile/apply_provider_profile_layers/route_provider_profile_keys · packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py:RouteChatModelFactory/_apply_profiles · packages/graph-agent-gateway/src/graph_agent_gateway/ordinary_chat.py:dispatch_ordinary_chat/_dispatch_provider_call/_call_openai_compatible/_call_openai_responses/_call_google_genai/_call_ark_runtime/_call_anthropic_compatible/_google_thinking_config · packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:ProfileSelectionError/select_verified_profile/_profile_supports_reasoning/_preferred_profile · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:VerifiedProfile/ProviderRoute/ResolvedRoute · packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:RUNTIME_SETTING_DESCRIPTORS/normalize_route_capabilities/build_runtime_setting_descriptors · packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:lint_role_routes/capability_key_for_lint · packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:resolve_role · packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel/_generate
units: [provider-profiles-init-kwargs]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 11-inv-provider-profiles - MVP1 Alignment(目标设计)

> **Tier**：③b gateway 公共能力（MVP1 新增设计单元/调用层 provider 差异表；WS-1 后源码已存在，ordinary provider/thinking 分支已迁到 `ordinary_chat.py`，后续只按需收束进 ProviderProfile 或 payload patch）
> **Owns**：`ProviderProfile` = route 派生 key → ChatX init-kwargs（+ 可选 `pre_init` / 动态 `init_kwargs_factory`）的声明式表；gateway 工厂按 `protocol:{route.protocol}` → `endpoint:{route.endpoint_id}` → `endpoint:{route.endpoint_id}:model:{route.provider_model_id}` 叠加。把 headers / Responses API / 温度默认 / stream_usage / thinking 开关等**构造期差异**收束到 init-kwargs 层。仅当请求 payload 必须改才子类覆盖单方法（deerflow 范式），**绝不重写整套消息转换**。**只描述怎么构造 ChatX，不做运行时动态选型**。
> **Status**：设计定稿（2026-06 判据复核，归属表判 11=纯 ③b 不变）；代码 = `ProviderProfile` 注册表、route key 派生、factory overlay、最小 `stream_usage` defaults 与 DeepSeek payload patch 已落地；其它 provider thinking 完整归一化仍 deferred。
> **Related**：[[10-inv-route-chat-model-factory]]（本表被工厂第 6 步调用，合成 ChatX init-kwargs）· [[05-orch-capabilities-and-models]]（capability/lint/`select_verified_profile` 留编排前置校验，与本表划清层级）· [[09-inv-invocation-runtime]]（invoke 运行时；`call_method_id`/`request_mapper_id` 归属悬案共享）· [[04-orch-registry-schema]]（`VerifiedProfile` 字段权威源，**不**与 `ProviderProfile` 合并）
> **决策日志**：client 层 A' 重设计决策（F6 provider 差异 → init-kwargs profile / M6 `RouteChatModelFactory` / D1 方案 A' / 借鉴 vs 自建）——完整逻辑 + PM 拍板原话已留底于本文 §4（决策基础）/ §5（决策动机）/ §6（兼容性验证清单）；归属判据见 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（§4 判 11 纯 ③b）
> **现状**：见同目录 `baseline.md`（WS-1 后 `ProviderProfile` 调用层模块已存在；它与 `registry/profile_selector.py` 的 verified profile 选择器是不同层级）

## 1. 定义

MVP1 目标：`ProviderProfile` 模式（用 provider 或 route 派生 key 映射到 ChatX 静态 init kwargs + 可选 `pre_init` + 可选动态 `init_kwargs_factory` 的声明式构造配置）。它解决「同样换原生 ChatX，但各 provider 构造参数有差异」的问题——把官方 ChatX 构造差异放进一张表，而不是散落在 ordinary provider-call 分支里。

**与现有 `VerifiedProfile` 划清层级**（命名易混，是头号待办）：
- `ProviderProfile`（**本模块新建**）= **怎么构造 ChatX**：provider/model → init kwargs。属调用层。
- `VerifiedProfile`（**现有 schema 类**，`registry/schema.py:189-204`）= **这条 route 哪种调用方式验证过**：`method_id`/`request_mapper_id`/status/default/rank。属编排/解析层（[[05-orch-capabilities-and-models]]），用于 `select_verified_profile` 运行期选一个已验证调用方式。两者**不合并**。

本模块**纯 ③b 公共**（provider 构造差异是 gateway 机制内在的，任何调模型 app 都要），归属表判 11=纯 ③b 新建（`module-disposition-revised.md:54`）。注意边界:capability/lint 继续留编排前置校验（描述"支持什么"，不是"怎么构造"），不变成运行时动态选型或 ChatX 构造 profile。

> **与通用适配器的边界（2026-06-04）**：`ProviderProfile`（init-kwargs 表）服务 **ChatX 面的「官方 ChatX」分支**（给 `ChatAnthropic`/`ChatOpenAI` 等叠构造参数）。**generic 分支**（`GenericRouteChatModel`，无官方 ChatX 的真·非标 route）的 provider 差异体现在它**自己的消息序列化**（见 [[10-inv-route-chat-model-factory]] §3.5 的 5 条序列化规则），不走本表的 init-kwargs。两者都属"怎么构造/怎么调"，但落点不同：官方 ChatX → 本表 init-kwargs；generic → 自有序列化内核。

## 2. 数据流 / 机制(目标设计与编号流程)

覆盖率:100%。本文件覆盖 `ProviderProfile` 目标模式、它和现有 `VerifiedProfile`/capability/lint 的边界，以及 deerflow/deepagents 参考实现。`ProviderProfile` 是拟新建的 provider/model 到 ChatX init kwargs 的构造配置，不是 registry 里的 verified route profile。

目标覆盖:

| 范围 | 目标关系 |
|---|---|
| [chatx-provider-patterns.md](../references/chatx-provider-patterns.md) | `ProviderProfile` dataclass 定义 init kwargs、`pre_init`、`init_kwargs_factory`。 |
| [chatx-provider-patterns.md](../references/chatx-provider-patterns.md) | `register_provider_profile` 展示 provider 或 provider:model key 注册。 |
| [chatx-provider-patterns.md](../references/chatx-provider-patterns.md) | `get_provider_profile` 展示 exact model 优先、provider fallback 的查找顺序。 |
| [chatx-provider-patterns.md](../references/chatx-provider-patterns.md) | `apply_provider_profile` 展示 lookup、pre_init、factory、caller kwargs 合并。 |
| [chatx-provider-patterns.md](../references/chatx-provider-patterns.md) | `resolve_model` 展示 `init_chat_model(model, **apply_provider_profile(model))` 的组合。 |
| [chatx-provider-patterns.md](../references/chatx-provider-patterns.md) | `PatchedChatDeepSeek` 展示只覆盖 `_get_request_payload` 的 payload patch 范式。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204` | 现有 `VerifiedProfile` 要继续作为 probe/verified 调用方式，不和 `ProviderProfile` 合并。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/ordinary_chat.py` | generic ordinary-chat provider core；其中的 provider kwargs / thinking 分支是后续按需收束进 `ProviderProfile` 或 payload patch 的差异来源。 |

**上下游**：[[10-inv-route-chat-model-factory]] 工厂第 6 步从 `ResolvedRoute` 生成基础 kwargs → **调本模块 `ProviderProfile` 表**（按 protocol-level → endpoint-level → exact-model 叠 defaults / pre_init / factory）→ 叠 route runtime settings（caller-wins）→ 工厂用合成后的 init-kwargs 构造 ChatX。

1. 新建 `ProviderProfile` 模式。`ProviderProfile`(ChatX 构造 profile)用 provider 或 provider:model key 映射到静态 init kwargs、可选 `pre_init`、可选动态 `init_kwargs_factory`([chatx-provider-patterns.md](../references/chatx-provider-patterns.md))。
2. 注册 key 支持 provider 级和 model 级；gateway 工厂消费的正式 key 为 `protocol:{route.protocol}`、`endpoint:{route.endpoint_id}`、`endpoint:{route.endpoint_id}:model:{route.provider_model_id}`。`register_provider_profile`(注册函数)重复注册时合并而不是粗暴覆盖([chatx-provider-patterns.md](../references/chatx-provider-patterns.md))。
3. 查找时 exact model 覆盖 endpoint default，endpoint 覆盖 protocol default。`route_provider_profile_keys` 从 `ResolvedRoute` 派生三层 key，`apply_provider_profile_layers` 按 protocol-level → endpoint-level → exact-model 顺序叠加。
4. 应用时 caller kwargs 最高优先级。`apply_provider_profile` / `apply_provider_profile_layers` 运行 `pre_init`，合并 `init_kwargs`、factory 输出和调用方 kwargs，调用方显式传入的值最终胜出([chatx-provider-patterns.md](../references/chatx-provider-patterns.md))。
5. `RouteChatModelFactory` 调用 `ProviderProfile`。`RouteChatModelFactory`(route 到 ChatX 的构造器,归 [[10-inv-route-chat-model-factory]])先从 `ResolvedRoute` 生成基础 kwargs，再叠加 provider/profile defaults，最后叠加 route runtime settings，形成 `ChatAnthropic`/`ChatOpenAI`/`ChatGoogleGenerativeAI` 的 init kwargs(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`；M6 工厂调用本表的契约见 [[10-inv-route-chat-model-factory]] §3，F6 共享)。
6. provider 差异优先写进 init kwargs 表（F6）。headers、Responses API、base_url 参数名、温度默认、stream_usage、thinking 开关等构造期差异应通过 profile 解决，而不是复制 ordinary-chat 的消息转换([chatx-provider-patterns.md](../references/chatx-provider-patterns.md); [chatx-provider-patterns.md](../references/chatx-provider-patterns.md)；F6 完整逻辑见 §4 F6 / §5 决策 1)。
7. 只有 payload 差异才子类覆盖单方法。`PatchedChatDeepSeek`(deerflow 参考子类)继承 `ChatDeepSeek`，只覆盖 `_get_request_payload`，在 parent payload 上恢复 reasoning_content，没有重写整套消息转换([chatx-provider-patterns.md](../references/chatx-provider-patterns.md))。
8. 继续保留 `VerifiedProfile` 的 probe 语义。`VerifiedProfile`(tested invocation profile)用 `method_id/request_mapper_id` 表示某条 route 已验证的调用方式；它不应被 provider init kwargs profile 吞掉(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:94-103`)。
9. capability/lint 继续留在编排前置校验。`normalize_route_capabilities`(把 provider 原始能力归一成 normalized capability)描述支持和边界，`lint_role_routes`(对 role route 链做 capability lint)负责 warn/block；它们不变成运行时动态选型或 ChatX 构造 profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:1-5`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-85`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:116-122`; `docs/graph-agent-gateway/mvp1/README.md:58`)。

## 3. 接口契约

> 本模块是一张**声明式 init-kwargs 表 + lookup/merge 入口**，跨边界契约只有一条主线：被 [[10-inv-route-chat-model-factory]] 的工厂调用，吃 provider/model key + caller kwargs，吐合并后的 ChatX init kwargs。它**不接 `ResolvedRoute`**（工厂负责从 route 抽 key 与基础 kwargs）、**不 invoke**、**不做选型**。

| 边界 | 契约 |
|---|---|
| **注册（写入表）** | `register_provider_profile(key, ProviderProfile)`：`key` 可为 deepagents 风格 provider/exact key，也可为 gateway route key；gateway 工厂正式消费 `protocol:{route.protocol}`、`endpoint:{route.endpoint_id}`、`endpoint:{route.endpoint_id}:model:{route.provider_model_id}`。`ProviderProfile`{ `init_kwargs`（静态 dict）, `pre_init`（可选，构造前 hook）, `init_kwargs_factory`（可选，动态算 kwargs） }。重复注册 **additive 合并**，非粗暴覆盖。 |
| **查找（读表）** | `get_provider_profile(spec)` 保留 provider/exact merge 原语；gateway 工厂使用 `route_provider_profile_keys(route)` 派生三层 key，并由 `apply_provider_profile_layers(...)` 按 protocol-level → endpoint-level → exact-model 叠加。 |
| **应用（10 工厂调用入口）** | `apply_provider_profile_layers(route_provider_profile_keys(route), **caller_kwargs)` → 合并后的 init-kwargs dict。合并顺序：`pre_init` → `init_kwargs` → `init_kwargs_factory` 输出 → **caller kwargs（最高优先级，caller-wins）**。工厂把 route runtime settings 作为 caller kwargs 传入，确保用户 route 设置压过 profile default。 |
| **gateway key 维度（已定）** | gateway 从 `ResolvedRoute` 派生 key：provider/protocol default = `protocol:{route.protocol}`；endpoint override = `endpoint:{route.endpoint_id}`；exact-model override = `endpoint:{route.endpoint_id}:model:{route.provider_model_id}`。这避免 `endpoint_id:provider_model_id` 临时规则长期悬挂，也避免照搬 deepagents 的单字符串接口。 |
| **与 `VerifiedProfile` 边界（不合并）** | `ProviderProfile`（构造 ChatX 的 init-kwargs）≠ `VerifiedProfile`（route 已验证调用方式 `method_id`/`request_mapper_id`，权威源 `registry/schema.py:189-204`）。后者留编排/解析层由 `select_verified_profile` 消费，**不被前者吞掉**。 |
| **与 capability/lint 边界（不混）** | `ProviderProfile` 说"怎么构造"；`normalize_route_capabilities`/`lint_role_routes` 说"支持什么 + warn/block"。capability **不驱动**动态 provider 选型，当前权威是 mvp1 README 的 05 模块边界和 05 文档；代码侧只产 lint/fail-fast，不做替代 route 搜索。 |
| **payload patch 边界** | 仅当请求 payload 必须改，才子类覆盖**单方法**（如 `PatchedChatDeepSeek` 只覆盖 `_get_request_payload`）；**绝不重写整套消息转换**（A' 核心，详见 §4 F6 / §5 决策 1）。 |
| **归属 / 稳定性** | `VerifiedProfile` 字段权威源 = [[04-orch-registry-schema]]；capability/lint 归 [[05-orch-capabilities-and-models]]；本模块**只新增 init-kwargs 表，不改 schema**，防 drift。 |

## 4. 设计决策基础(用户原话)

> **F6 provider 差异 → init-kwargs profile**（PM 拍板方案，verbatim 决策文）："用 deepagents `ProviderProfile` 模式（provider/model → 一张 init-kwargs 表 + 可选 `pre_init`/factory）装 provider 差异（headers、responses api、温度默认、thinking 开关等）；仅当需改请求 payload 才子类覆盖单方法（deerflow 范式），绝不重写整套消息转换。" → 本模块即 F6 的落点。此决策与 [[10-inv-route-chat-model-factory]] 共享（工厂第 6 步调本表合 init-kwargs；重复留底防 drift）。

> **D1 方案 A'（不重写整套消息转换）**（PM 原话，verbatim）："不用留A, 这是错误判断, 正确的是A'。" → A' 用原生 ChatX 接管消息转换/调用/解析；provider profile 只能影响构造参数，不能回到自研 dict payload 大锅。此决策与 [[09-inv-invocation-runtime]]、[[10-inv-route-chat-model-factory]]、[[07-orch-fallback-circuit-probe]] 共享（重复留底防 drift）。

> **通用判据（gateway = 富能力可复用网关）**（README §2）："换一个完全不同的应用装上 gateway，这个能力还原样能用吗？能 → 公共（gateway）。" → provider 构造差异是 gateway 机制内在的（任何调模型 app 接多 provider 都要），故本模块纯 ③b 公共（新建）。

## 5. 决策 + 动机(决策原因)

1. 不重写整套消息转换（F6 + D1 A' 边界）。A' 的核心是用原生 ChatX 接管官方 ChatX 主路径的消息转换、调用、解析；generic ordinary-chat 的 provider-call core 已集中到 `ordinary_chat.py`。provider profile 只能影响构造参数（headers / Responses API / 温度默认 / stream_usage / thinking 开关等 init-kwargs），不能回到自研 dict payload 大锅。仅当请求 payload 必须改，才子类覆盖单方法（如 `PatchedChatDeepSeek` 只覆盖 `_get_request_payload`），绝不重写整套消息转换。
2. 借 deepagents 的 profile 机制，不借它的输入接口。deepagents `resolve_model`(用字符串 spec 调 `init_chat_model` 的 helper)，而 gateway 必须从 `ResolvedRoute` 取 route metadata、凭证、runtime settings，因此只能借鉴 lookup/merge/pre_init/factory 模式([chatx-provider-patterns.md](../references/chatx-provider-patterns.md); `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`)。
3. 借 deerflow 的 thinking/stream_usage 经验，不借它的 AppConfig 工厂。deerflow `create_chat_model`(deerflow 模型创建函数)依赖 app config、resolve_class、tracing callbacks；gateway 工厂应只吃 `ResolvedRoute` 和显式调用上下文([chatx-provider-patterns.md](../references/chatx-provider-patterns.md)；借鉴 vs 自建边界详见 [[10-inv-route-chat-model-factory]] §5 决策 5)。
4. 保持职责边界。capability/lint 说明 route 能不能用，`ProviderProfile` 说明怎么构造 ChatX，`GatewayChatModel` 说明如何 fallback/probe/记录 usage；三者分开才能避免 provider 差异再次散落(`docs/graph-agent-gateway/mvp1/README.md:24-30`; `docs/graph-agent-gateway/mvp1/README.md:34-45`; `docs/graph-agent-gateway/mvp1/README.md:58`; `docs/graph-agent-gateway/mvp1/README.md:66-68`)。**被否的做法**：把官方 ChatX 构造差异继续散在 ordinary provider-call 分支里，换 ChatX 后会让差异再次绑死在自研调用代码里。
5. capability 不能变成动态 provider 选择。`capabilities.py` 文件头明确 capabilities 描述 support/bounds（用户 runtime intent 属 role/profile route entry，不是 provider init kwargs profile）；MVP1 当前权威是 README 的 05 模块边界与 05 文档，代码事实是 `lint_role_routes` 只产 warn/block、`resolve_role` 只对 blocking lint fail-fast，不搜索替代 route(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:1-5`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-85`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:116-122`; `docs/graph-agent-gateway/mvp1/README.md:58`)。

## 6. 测试关键点

> 来源 = client 层 A' 重设计决策的「兼容性验证清单（A' 实现必过）」（完整 7 项 + live 冒烟留底于 [[09-inv-invocation-runtime]] §6）。本模块（provider 构造差异表）对应其中与 init-kwargs 合并 / thinking / stream_usage / payload patch / 边界不混相关的项。

- **lookup 顺序 + caller-wins**：gateway factory 按 `protocol:{route.protocol}` → `endpoint:{route.endpoint_id}` → `endpoint:{route.endpoint_id}:model:{route.provider_model_id}` 叠加；caller kwargs（route runtime settings）压过 profile default（合并优先级 `pre_init`→`init_kwargs`→factory→caller）。
- **thinking 归一化进 init-kwargs**：把 thinking 规则从 `ordinary_chat.py` 的 provider 分支提炼成 profile/init kwargs 前，需保留 lint 里的预算校验和 Anthropic manual/adaptive 约束（`registry/lint.py:242-332`）；profile 只承载构造期开关，约束仍在 lint。
- **stream_usage 默认开**：OpenAI-compatible profile 默认带 `stream_usage`，保证第三方 base_url 下 streaming 响应不丢 usage（deerflow 经验，F5/F6）。
- **payload patch 仅单方法**：`PatchedChatDeepSeek` 已移植，仅覆盖 `_get_request_payload` 恢复多轮 assistant `reasoning_content`，**不重写整套消息转换**（A' 边界，见 §4 F6 / §5 决策 1）；已用 gateway 本地 helper 按 assistant message 顺序 replay，不搬 deerflow 文件。
- **`VerifiedProfile` 不被吞**：`ProviderProfile`（构造）与 `VerifiedProfile`（已验证调用方式）层级分明，`select_verified_profile` 仍在编排/解析层正常选 profile，不被 init-kwargs 表替代。
- **capability 不动态选型**：profile 表不引入按 capability/price/latency 搜索替代 route 的逻辑；capability 仍只 lint/warn/block/fail-fast（当前代码依据 `lint_role_routes` + `resolve_role`）。
- **异常分类形状不回归**（关联项）：用 profile 构造的 ChatX，其 retry 耗尽异常仍能被 07 `classify_exception` 正确分类（兼容性验证清单头号风险，见 [[09-inv-invocation-runtime]] §6）。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`：`ProviderProfile` 注册表已存在；现差异来源点 = `registry/profile_selector.py`（verified profile 选择，**保留在解析层**）、`registry/capabilities.py`（能力归一化，**保留在能力层**）、`registry/lint.py`（lint，**保留在校验层**）、`ordinary_chat.py`（generic ordinary-chat provider kwargs / thinking 分支，后续按需收束）。
- **③a** `apps/studio/backend`：N/A（本模块纯 provider 构造差异表，不含应用加工四件事）。
- **② Rust**：N/A。
- **范本（正式归档，仅借鉴，不搬文件）**：[chatx-provider-patterns.md](../references/chatx-provider-patterns.md)（整套机制）、[chatx-provider-patterns.md](../references/chatx-provider-patterns.md)（单方法覆盖）。

## 8. gaps / 待设计(待办/疑点)

1. 已处理:`ProviderProfile` gateway key 规则已定为 `protocol:{route.protocol}` → `endpoint:{route.endpoint_id}` → `endpoint:{route.endpoint_id}:model:{route.provider_model_id}`；deepagents 的 `provider:model` 字符串只作为参考模式，不作为 gateway 工厂输入。
2. 待办:把 thinking 规则从 `ordinary_chat.py` provider 分支提炼成 profile/init kwargs 前，需要保留 lint 里的预算校验和 Anthropic manual/adaptive 约束(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:242-332`)。
3. 已处理:`PatchedChatDeepSeek` 已在 gateway factory 落地为单方法 `_get_request_payload` 覆盖；本地 replay helper 按原始 `AIMessage` 顺序把 `additional_kwargs["reasoning_content"]` 写回 payload，不搬 deerflow 文件。
4. 待办(跨模块协调,命名易混):`call_method_id` / `request_mapper_id` 在 MVP1 后是否继续存在、由谁消费,需要和 `ProviderProfile` 的 init kwargs 表分清层级;现状它们由 selected verified profile 写入 route(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:94-103`)。与 [[10-inv-route-chat-model-factory]] §8 待办 4、[[09-inv-invocation-runtime]] §8 待办 3 为同一悬案。
5. 疑点:现有 `_profile_supports_reasoning`(靠字符串包含 thinking/reasoning 判断 profile 是否支持 reasoning 的 helper)是否足够稳定应在 [[05-orch-capabilities-and-models]] 继续跟踪;本模块只记录它不是 ChatX provider profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:55-66`)。

## 已实现 / 与 baseline 差异

已实现:

1. registry 已经有 `VerifiedProfile`、`selected_profile_id`、`call_method_id`、`request_mapper_id`，能表达“这条 route 哪种调用方式验证过”(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:432-435`)。
2. capabilities/lint 已经能表达 thinking、structured output、tool calling、reasoning effort/budget 等支持与限制(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:20-32`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:202-332`)。
3. `ordinary_chat.py` 已集中 generic ordinary-chat provider 差异来源，便于后续把官方 ChatX 构造 kwargs 提炼进 profile 表。
4. `ProviderProfile` 调用层注册表、route key 派生、factory overlay 与最小 defaults 已落地；默认表只 seed `protocol:openai_compatible` / `protocol:ark_runtime` 的 `stream_usage=True`。

未实现:

1. thinking 归一化还未完整迁入 ProviderProfile 或单方法 patch；现状仍只是局部 runtime kwargs 映射、ChatX result 不拍平和 DeepSeek reasoning-content replay。
2. DeepSeek payload patch 已落地；其它 provider-specific payload/thinking 差异仍需独立失败测试后再迁移。

## 代码索引 clues

- `ProviderProfile`:目标 provider/model 构造 profile，保存 init kwargs、`pre_init` 和动态 factory([chatx-provider-patterns.md](../references/chatx-provider-patterns.md))。
- `register_provider_profile`:deepagents 的注册函数，展示 provider 或 exact model key 的 additive registration([chatx-provider-patterns.md](../references/chatx-provider-patterns.md))。
- `get_provider_profile`:deepagents 的查找函数，展示 exact model profile 覆盖 provider profile 的顺序([chatx-provider-patterns.md](../references/chatx-provider-patterns.md))。
- `route_provider_profile_keys` / `apply_provider_profile_layers`:gateway route key 派生与三层 overlay 入口。
- `apply_provider_profile`:deepagents 风格单 spec 应用函数，展示 `pre_init`、factory 和 caller kwargs 的合并优先级([chatx-provider-patterns.md](../references/chatx-provider-patterns.md))。
- `PatchedChatDeepSeek`:deerflow 的 DeepSeek ChatX 子类，只覆盖 `_get_request_payload` 来恢复 reasoning_content([chatx-provider-patterns.md](../references/chatx-provider-patterns.md))。
- `VerifiedProfile`:gateway 当前 schema 类，表示 verified invocation method，不是 ChatX init profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`)。
- `select_verified_profile`:gateway 当前 verified profile 选择函数，保留在编排/解析层(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:14-72`)。
- `normalize_route_capabilities`:gateway 当前 capability 归一化函数，保留在能力/探测层(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:35-202`)。

## 交叉引用(链接,不复制)

- [[10-inv-route-chat-model-factory]]：`RouteChatModelFactory` 工厂（第 6 步调本表合 init-kwargs；`call_method_id`/`request_mapper_id` 归属悬案共享）
- [[05-orch-capabilities-and-models]]：capability / lint / `select_verified_profile`（留编排前置校验，与本表划清层级，不混不动态选型）
- [[09-inv-invocation-runtime]]：invoke 运行时（profile 构造的 ChatX 在那边被 `.invoke()`）
- [[04-orch-registry-schema]]：`VerifiedProfile` 字段权威源（**不**与 `ProviderProfile` 合并）
- client 层 A' 重设计决策（F6/M6/D1/借鉴 vs 自建）：完整逻辑 + PM 拍板原话留底于本文 §4/§5/§6 / 归属表 `module-disposition-revised.md`（§4 判 11 纯 ③b 新建）
