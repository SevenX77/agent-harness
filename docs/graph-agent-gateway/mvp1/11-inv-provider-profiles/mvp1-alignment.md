---
module: 11-inv-provider-profiles
doc: mvp1-alignment
status: written
last_verified: 2026-06-02
---

# 11-inv-provider-profiles - MVP1 Alignment(目标设计)

> **Tier**：③b gateway 公共能力（**MVP1 新建**调用层 provider 差异表；现源码不存在，差异散在 `profile_selector`+`capabilities`+`client_manager` thinking 分支）
> **Owns**：`ProviderProfile` = provider / provider:model → ChatX init-kwargs（+ 可选 `pre_init` / 动态 `init_kwargs_factory`）的声明式表；把 headers / Responses API / 温度默认 / stream_usage / thinking 开关等**构造期差异**收束到 init-kwargs 层。仅当请求 payload 必须改才子类覆盖单方法（deerflow 范式），**绝不重写整套消息转换**。**只描述怎么构造 ChatX，不做运行时动态选型**。
> **Status**：设计定稿（2026-06 判据复核，归属表判 11=纯 ③b 新建不变）；代码 = `ProviderProfile` 注册表待新建，现 provider kwargs 仍由各 `_call_*` 函数自建。
> **Related**：[[10-inv-route-chat-model-factory]]（本表被工厂第 6 步调用，合成 ChatX init-kwargs）· [[05-orch-capabilities-and-models]]（capability/lint/`select_verified_profile` 留编排前置校验，与本表划清层级）· [[09-inv-invocation-runtime]]（invoke 运行时；`call_method_id`/`request_mapper_id` 归属悬案共享）· [[04-orch-registry-schema]]（`VerifiedProfile` 字段权威源，**不**与 `ProviderProfile` 合并）
> **决策日志**：client 层 A' 重设计决策（F6 provider 差异 → init-kwargs profile / M6 `RouteChatModelFactory` / D1 方案 A' / 借鉴 vs 自建）——完整逻辑 + PM 拍板原话已留底于本文 §4（决策基础）/ §5（决策动机）/ §6（兼容性验证清单）；归属判据见 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（§4 判 11 纯 ③b 新建）
> **现状**：见同目录 `baseline.md`（诚实声明现源码无 `ProviderProfile` 调用层模块，只有 `registry/profile_selector.py` 的 verified profile 选择器）

## 1. 定义

MVP1 目标：新建 `ProviderProfile` 模式（用 provider 或 `provider:model` key 映射到 ChatX 静态 init kwargs + 可选 `pre_init` + 可选动态 `init_kwargs_factory` 的声明式构造配置）。它解决「同样换原生 ChatX，但各 provider 构造参数有差异」的问题——把差异放进一张表，而不是再次散落到各 `_call_*` 分支。

**与现有 `VerifiedProfile` 划清层级**（命名易混，是头号待办）：
- `ProviderProfile`（**本模块新建**）= **怎么构造 ChatX**：provider/model → init kwargs。属调用层。
- `VerifiedProfile`（**现有 schema 类**，`registry/schema.py:189-204`）= **这条 route 哪种调用方式验证过**：`method_id`/`request_mapper_id`/status/default/rank。属编排/解析层（[[05-orch-capabilities-and-models]]），用于 `select_verified_profile` 运行期选一个已验证调用方式。两者**不合并**。

本模块**纯 ③b 公共**（provider 构造差异是 gateway 机制内在的，任何调模型 app 都要），归属表判 11=纯 ③b 新建（`module-disposition-revised.md:44,84`）。注意边界:capability/lint 继续留编排前置校验（描述"支持什么"，不是"怎么构造"），不变成运行时动态选型或 ChatX 构造 profile。

## 2. 数据流 / 机制(目标设计与编号流程)

覆盖率:100%。本文件覆盖 `ProviderProfile` 目标模式、它和现有 `VerifiedProfile`/capability/lint 的边界，以及 deerflow/deepagents 参考实现。`ProviderProfile` 是拟新建的 provider/model 到 ChatX init kwargs 的构造配置，不是 registry 里的 verified route profile。

目标覆盖:

| 范围 | 目标关系 |
|---|---|
| `temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:36-90` | `ProviderProfile` dataclass 定义 init kwargs、`pre_init`、`init_kwargs_factory`。 |
| `temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:194-246` | `register_provider_profile` 展示 provider 或 provider:model key 注册。 |
| `temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:249-314` | `get_provider_profile` 展示 exact model 优先、provider fallback 的查找顺序。 |
| `temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:317-379` | `apply_provider_profile` 展示 lookup、pre_init、factory、caller kwargs 合并。 |
| `temp/deepagents/libs/deepagents/deepagents/_models.py:15-36` | `resolve_model` 展示 `init_chat_model(model, **apply_provider_profile(model))` 的组合。 |
| `temp/deerflow/backend/packages/harness/deerflow/models/patched_deepseek.py:18-59` | `PatchedChatDeepSeek` 展示只覆盖 `_get_request_payload` 的 payload patch 范式。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204` | 现有 `VerifiedProfile` 要继续作为 probe/verified 调用方式，不和 `ProviderProfile` 合并。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-1012` | 现有 provider kwargs 分支是 `ProviderProfile` 要收束的 baseline 差异来源。 |

**上下游**：[[10-inv-route-chat-model-factory]] 工厂第 6 步从 `ResolvedRoute` 生成基础 kwargs → **调本模块 `ProviderProfile` 表**（lookup provider/model → 叠 defaults / pre_init / factory）→ 叠 route runtime settings（caller-wins）→ 工厂用合成后的 init-kwargs 构造 ChatX。

1. 新建 `ProviderProfile` 模式。`ProviderProfile`(ChatX 构造 profile)用 provider 或 provider:model key 映射到静态 init kwargs、可选 `pre_init`、可选动态 `init_kwargs_factory`(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:36-90`)。
2. 注册 key 支持 provider 级和 model 级。`register_provider_profile`(注册函数)允许 `"openai"` 这种 provider key，也允许 `"openai:gpt-5.4"` 这种 exact model key，并在重复注册时合并而不是粗暴覆盖(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:194-246`)。
3. 查找时 exact model 覆盖 provider default。`get_provider_profile`(查找函数)先查完整 spec，再查 provider prefix，两者都有时把 exact model profile 叠到 provider profile 上(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:249-314`)。
4. 应用时 caller kwargs 最高优先级。`apply_provider_profile`(构造 kwargs 的入口)运行 `pre_init`，合并 `init_kwargs`、factory 输出和调用方 kwargs，调用方显式传入的值最终胜出(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:317-379`)。
5. `RouteChatModelFactory` 调用 `ProviderProfile`。`RouteChatModelFactory`(route 到 ChatX 的构造器,归 [[10-inv-route-chat-model-factory]])应先从 `ResolvedRoute` 生成基础 kwargs，再叠加 provider/profile defaults，最后叠加 route runtime settings，形成 `ChatAnthropic`/`ChatOpenAI`/`ChatGoogleGenerativeAI` 的 init kwargs(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`；M6 工厂调用本表的契约见 [[10-inv-route-chat-model-factory]] §3，F6 共享)。
6. provider 差异优先写进 init kwargs 表（F6）。headers、Responses API、base_url 参数名、温度默认、stream_usage、thinking 开关等构造期差异应通过 profile 解决，而不是复制 `_call_*` 的消息转换(`temp/deerflow/backend/packages/harness/deerflow/models/factory.py:34-47`; `temp/deerflow/backend/packages/harness/deerflow/models/factory.py:94-146`；F6 完整逻辑见 §4 F6 / §5 决策 1)。
7. 只有 payload 差异才子类覆盖单方法。`PatchedChatDeepSeek`(deerflow 参考子类)继承 `ChatDeepSeek`，只覆盖 `_get_request_payload`，在 parent payload 上恢复 reasoning_content，没有重写整套消息转换(`temp/deerflow/backend/packages/harness/deerflow/models/patched_deepseek.py:18-59`)。
8. 继续保留 `VerifiedProfile` 的 probe 语义。`VerifiedProfile`(tested invocation profile)用 `method_id/request_mapper_id` 表示某条 route 已验证的调用方式；它不应被 provider init kwargs profile 吞掉(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:94-103`)。
9. capability/lint 继续留在编排前置校验。`normalize_route_capabilities`(把 provider 原始能力归一成 normalized capability)描述支持和边界，`lint_role_routes`(对 role route 链做 capability lint)负责 warn/block；它们不变成运行时动态选型或 ChatX 构造 profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:1-5`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-80`; `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:142-146`)。

## 3. 接口契约

> 本模块是一张**声明式 init-kwargs 表 + lookup/merge 入口**，跨边界契约只有一条主线：被 [[10-inv-route-chat-model-factory]] 的工厂调用，吃 provider/model key + caller kwargs，吐合并后的 ChatX init kwargs。它**不接 `ResolvedRoute`**（工厂负责从 route 抽 key 与基础 kwargs）、**不 invoke**、**不做选型**。

| 边界 | 契约 |
|---|---|
| **注册（写入表）** | `register_provider_profile(key, ProviderProfile)`：`key` = provider 级（`"openai"`）或 exact model 级（`"openai:gpt-5.4"`）；`ProviderProfile`{ `init_kwargs`（静态 dict）, `pre_init`（可选，构造前 hook）, `init_kwargs_factory`（可选，动态算 kwargs） }。重复注册 **additive 合并**，非粗暴覆盖。 |
| **查找（读表）** | `get_provider_profile(spec)`：先查完整 `provider:model`，再查 `provider` prefix；两者都命中时 **exact model profile 叠加在 provider profile 之上**（model 覆盖 provider default）。 |
| **应用（10 工厂调用入口）** | `apply_provider_profile(spec, **caller_kwargs)` → 合并后的 init-kwargs dict。合并顺序：`pre_init` → `init_kwargs` → `init_kwargs_factory` 输出 → **caller kwargs（最高优先级，caller-wins）**。工厂把 route runtime settings 作为 caller kwargs 传入，确保用户 route 设置压过 profile default。 |
| **gateway key 维度（待定）** | gateway 必须从 `ResolvedRoute` 维度（`route.protocol` / endpoint/provider id / `provider_model_id`）派生 key，**不能照搬** deepagents 的 `provider:model` 字符串接口（§8 待办 1）。 |
| **与 `VerifiedProfile` 边界（不合并）** | `ProviderProfile`（构造 ChatX 的 init-kwargs）≠ `VerifiedProfile`（route 已验证调用方式 `method_id`/`request_mapper_id`，权威源 `registry/schema.py:189-204`）。后者留编排/解析层由 `select_verified_profile` 消费，**不被前者吞掉**。 |
| **与 capability/lint 边界（不混）** | `ProviderProfile` 说"怎么构造"；`normalize_route_capabilities`/`lint_role_routes` 说"支持什么 + warn/block"。capability **不驱动**动态 provider 选型（MVP0 alignment 明令，`mvp0-alignment.md:142-146`）。 |
| **payload patch 边界** | 仅当请求 payload 必须改，才子类覆盖**单方法**（如 `PatchedChatDeepSeek` 只覆盖 `_get_request_payload`）；**绝不重写整套消息转换**（A' 核心，详见 §4 F6 / §5 决策 1）。 |
| **归属 / 稳定性** | `VerifiedProfile` 字段权威源 = [[04-orch-registry-schema]]；capability/lint 归 [[05-orch-capabilities-and-models]]；本模块**只新增 init-kwargs 表，不改 schema**，防 drift。 |

## 4. 设计决策基础(用户原话)

> **F6 provider 差异 → init-kwargs profile**（PM 拍板方案，verbatim 决策文）："用 deepagents `ProviderProfile` 模式（provider/model → 一张 init-kwargs 表 + 可选 `pre_init`/factory）装 provider 差异（headers、responses api、温度默认、thinking 开关等）；仅当需改请求 payload 才子类覆盖单方法（deerflow 范式），绝不重写整套消息转换。" → 本模块即 F6 的落点。此决策与 [[10-inv-route-chat-model-factory]] 共享（工厂第 6 步调本表合 init-kwargs；重复留底防 drift）。

> **D1 方案 A'（不重写整套消息转换）**（PM 原话，verbatim）："不用留A, 这是错误判断, 正确的是A'。" → A' 用原生 ChatX 接管消息转换/调用/解析；provider profile 只能影响构造参数，不能回到自研 dict payload 大锅。此决策与 [[09-inv-invocation-runtime]]、[[10-inv-route-chat-model-factory]]、[[07-orch-fallback-circuit-probe]] 共享（重复留底防 drift）。

> **通用判据（gateway = 富能力可复用网关）**（README §2）："换一个完全不同的应用装上 gateway，这个能力还原样能用吗？能 → 公共（gateway）。" → provider 构造差异是 gateway 机制内在的（任何调模型 app 接多 provider 都要），故本模块纯 ③b 公共（新建）。

## 5. 决策 + 动机(决策原因)

1. 不重写整套消息转换（F6 + D1 A' 边界）。A' 的核心是用原生 ChatX 接管消息转换、调用、解析（M2 只退役 client_manager 的「消息转换 + provider 调用/解析」两件，留底于 [[09-inv-invocation-runtime]] §5）；provider profile 只能影响构造参数（headers / Responses API / 温度默认 / stream_usage / thinking 开关等 init-kwargs），不能回到自研 dict payload 大锅。仅当请求 payload 必须改，才子类覆盖单方法（如 `PatchedChatDeepSeek` 只覆盖 `_get_request_payload`），绝不重写整套消息转换。
2. 借 deepagents 的 profile 机制，不借它的输入接口。deepagents `resolve_model`(用字符串 spec 调 `init_chat_model` 的 helper)，而 gateway 必须从 `ResolvedRoute` 取 route metadata、凭证、runtime settings，因此只能借鉴 lookup/merge/pre_init/factory 模式(`temp/deepagents/libs/deepagents/deepagents/_models.py:15-36`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`)。
3. 借 deerflow 的 thinking/stream_usage 经验，不借它的 AppConfig 工厂。deerflow `create_chat_model`(deerflow 模型创建函数)依赖 app config、resolve_class、tracing callbacks；gateway 工厂应只吃 `ResolvedRoute` 和显式调用上下文(`temp/deerflow/backend/packages/harness/deerflow/models/factory.py:50-171`；借鉴 vs 自建边界详见 [[10-inv-route-chat-model-factory]] §5 决策 5)。
4. 保持职责边界。capability/lint 说明 route 能不能用，`ProviderProfile` 说明怎么构造 ChatX，`GatewayChatModel` 说明如何 fallback/probe/记录 usage；三者分开才能避免 provider 差异再次散落(`docs/graph-agent-gateway/mvp1/README.md:13-18`; `docs/graph-agent-gateway/mvp1/README.md:35-40`)。**被否的做法**：把 provider 差异继续散在各 `_call_*` 分支（现状），换 ChatX 后会让差异再次绑死在自研调用代码里。
5. capability 不能变成动态 provider 选择。`capabilities.py` 文件头明确 capabilities 描述 support/bounds（用户 runtime intent 属 role/profile route entry，不是 provider init kwargs profile）；MVP0 alignment 明令禁止按 provider/capability/price/latency/availability 搜索替代 route，capability 只能 lint/warn/block/fail-fast(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:1-5`; `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:142-146`)。

## 6. 测试关键点

> 来源 = client 层 A' 重设计决策的「兼容性验证清单（A' 实现必过）」（完整 7 项 + live 冒烟留底于 [[09-inv-invocation-runtime]] §6）。本模块（provider 构造差异表）对应其中与 init-kwargs 合并 / thinking / stream_usage / payload patch / 边界不混相关的项。

- **lookup 顺序 + caller-wins**：exact `provider:model` profile 叠在 `provider` profile 之上；caller kwargs（route runtime settings）压过 profile default（合并优先级 `pre_init`→`init_kwargs`→factory→caller）。
- **thinking 归一化进 init-kwargs**：把 thinking 规则从 client_manager 分支（`client_manager.py:709-752`）提炼成 profile/init kwargs 前，需保留 lint 里的预算校验和 Anthropic manual/adaptive 约束（`lint.py:242-332`）；profile 只承载构造期开关，约束仍在 lint。
- **stream_usage 默认开**：OpenAI-compatible profile 默认带 `stream_usage`，保证第三方 base_url 下 streaming 响应不丢 usage（deerflow 经验，F5/F6）。
- **payload patch 仅单方法**：若移植 `PatchedChatDeepSeek`，仅覆盖 `_get_request_payload` 恢复多轮 reasoning_content，**不重写整套消息转换**（A' 边界，见 §4 F6 / §5 决策 1）；移植时一并核对 deerflow 依赖的 `assistant_payload_replay` helper（另见 §8 待办 3）。
- **`VerifiedProfile` 不被吞**：`ProviderProfile`（构造）与 `VerifiedProfile`（已验证调用方式）层级分明，`select_verified_profile` 仍在编排/解析层正常选 profile，不被 init-kwargs 表替代。
- **capability 不动态选型**：profile 表不引入按 capability/price/latency 搜索替代 route 的逻辑；capability 仍只 lint/warn/block（`docs/graph-agent-gateway/mvp0/mvp0-alignment.md:142-146`）。
- **异常分类形状不回归**（关联项）：用 profile 构造的 ChatX，其 retry 耗尽异常仍能被 07 `classify_exception` 正确分类（兼容性验证清单头号风险，见 [[09-inv-invocation-runtime]] §6）。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`：`ProviderProfile` 注册表（**待新建**）；现差异来源点 = `registry/profile_selector.py`（verified profile 选择，**保留在解析层**）、`registry/capabilities.py`（能力归一化，**保留在能力层**）、`registry/lint.py`（lint，**保留在校验层**）、`client_manager.py:440-1012`（provider kwargs 分支，**待收束进 profile**）、`client_manager.py:1119-1131`（`_google_thinking_config`）。
- **③a** `apps/studio/backend`：N/A（本模块纯 provider 构造差异表，不含应用加工四件事）。
- **② Rust**：N/A。
- **范本（temp，仅借鉴，不搬文件）**：`temp/deepagents/.../profiles/provider/provider_profiles.py`（整套机制）、`temp/deerflow/.../models/patched_deepseek.py`（单方法覆盖）。

## 8. gaps / 待设计(待办/疑点)

1. 待办:设计 `ProviderProfile` key 规则时，要决定使用 `route.protocol`、endpoint/provider id、还是 `provider_model_id` 组合；deepagents 的 `provider:model` 字符串不能原样覆盖 gateway route 维度(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:249-314`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:420-435`)。
2. 待办:把 thinking 规则从 client_manager 分支提炼成 profile/init kwargs 前，需要保留 lint 里的预算校验和 Anthropic manual/adaptive 约束(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:242-332`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:709-752`)。
3. 待办:如果移植 `PatchedChatDeepSeek`，要一起核对 deerflow 依赖的 `assistant_payload_replay` helper；当前只核到 `patched_deepseek.py` 本体存在并按单方法覆盖(`temp/deerflow/backend/packages/harness/deerflow/models/patched_deepseek.py:15-59`)。
4. 待办(跨模块协调,命名易混):`call_method_id` / `request_mapper_id` 在 MVP1 后是否继续存在、由谁消费,需要和 `ProviderProfile` 的 init kwargs 表分清层级;现状它们由 selected verified profile 写入 route(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:94-103`)。与 [[10-inv-route-chat-model-factory]] §8 待办 4、[[09-inv-invocation-runtime]] §8 待办 3 为同一悬案。
5. 疑点:现有 `_profile_supports_reasoning`(靠字符串包含 thinking/reasoning 判断 profile 是否支持 reasoning 的 helper)是否足够稳定应在 [[05-orch-capabilities-and-models]] 继续跟踪;本模块只记录它不是 ChatX provider profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:55-66`)。

## 已实现 / 与 baseline 差异

已实现:

1. registry 已经有 `VerifiedProfile`、`selected_profile_id`、`call_method_id`、`request_mapper_id`，能表达“这条 route 哪种调用方式验证过”(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:432-435`)。
2. capabilities/lint 已经能表达 thinking、structured output、tool calling、reasoning effort/budget 等支持与限制(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:20-32`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:202-332`)。
3. client_manager 已经暴露了 provider 差异来源，便于后续把 kwargs 提炼进 profile 表(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-1012`)。

未实现:

1. gateway 源码没有 `ProviderProfile` 调用层注册表；当前只有 `registry/profile_selector.py`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:1-72`)。
2. provider/model 到 init kwargs 的表还不存在；现状 kwargs 仍由 `_call_*` 函数各自构造(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:459-482`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:630-653`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:691-752`)。
3. payload patch 机制还不存在；deepseek reasoning_content 多轮保留只能作为参考文件，尚未移植(`temp/deerflow/backend/packages/harness/deerflow/models/patched_deepseek.py:18-59`)。

## 代码索引 clues

- `ProviderProfile`:目标 provider/model 构造 profile，保存 init kwargs、`pre_init` 和动态 factory(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:36-90`)。
- `register_provider_profile`:deepagents 的注册函数，展示 provider 或 exact model key 的 additive registration(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:194-246`)。
- `get_provider_profile`:deepagents 的查找函数，展示 exact model profile 覆盖 provider profile 的顺序(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:249-314`)。
- `apply_provider_profile`:deepagents 的应用函数，展示 `pre_init`、factory 和 caller kwargs 的合并优先级(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:317-379`)。
- `PatchedChatDeepSeek`:deerflow 的 DeepSeek ChatX 子类，只覆盖 `_get_request_payload` 来恢复 reasoning_content(`temp/deerflow/backend/packages/harness/deerflow/models/patched_deepseek.py:18-59`)。
- `VerifiedProfile`:gateway 当前 schema 类，表示 verified invocation method，不是 ChatX init profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`)。
- `select_verified_profile`:gateway 当前 verified profile 选择函数，保留在编排/解析层(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:14-72`)。
- `normalize_route_capabilities`:gateway 当前 capability 归一化函数，保留在能力/探测层(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:35-202`)。

## 交叉引用(链接,不复制)

- [[10-inv-route-chat-model-factory]]：`RouteChatModelFactory` 工厂（第 6 步调本表合 init-kwargs；`call_method_id`/`request_mapper_id` 归属悬案共享）
- [[05-orch-capabilities-and-models]]：capability / lint / `select_verified_profile`（留编排前置校验，与本表划清层级，不混不动态选型）
- [[09-inv-invocation-runtime]]：invoke 运行时（profile 构造的 ChatX 在那边被 `.invoke()`）
- [[04-orch-registry-schema]]：`VerifiedProfile` 字段权威源（**不**与 `ProviderProfile` 合并）
- client 层 A' 重设计决策（F6/M6/D1/借鉴 vs 自建）：完整逻辑 + PM 拍板原话留底于本文 §4/§5/§6 / 归属表 `module-disposition-revised.md`（§4 判 11 纯 ③b 新建）/ `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:142-146`（capability 不驱动选型）
