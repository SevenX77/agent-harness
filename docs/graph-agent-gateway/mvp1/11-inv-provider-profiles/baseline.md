---
module: 11-inv-provider-profiles
doc: baseline
status: written
last_verified: 2026-06-02
---

# 11-inv-provider-profiles - Baseline(现状)

> **Tier**：③b gateway 公共能力（**MVP1 新建**调用层 provider 差异表；归属表判 11=纯 ③b 新建，见 `module-disposition-revised.md:44,84`）。**本模块现源码不存在**——下文诚实记录"没有 `ProviderProfile` 调用层模块"这一现状（只有 `registry/profile_selector.py` 的 verified profile 选择器，与拟新建的 `ProviderProfile` 是不同层级），以及 provider 差异现散在 `profile_selector`+`capabilities`+`client_manager` thinking 分支。MVP1 目标见同目录 `mvp1-alignment.md`。

## 覆盖代码(含覆盖率)

本模块当前没有独立 `ProviderProfile` 调用层模块。`ProviderProfile` 是拟新建的 provider/model 到 ChatX init kwargs 的声明式配置模式；现状源码只有 `registry/profile_selector.py` 里的 verified profile 选择器，它选择“已验证调用方式”，不是 ChatX 构造 profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:1-23`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`)。

覆盖率:100%。这里覆盖 MVP1 manifest 指定的散落职责:profile selection、capability normalization、runtime lint、resolver selected profile 字段、client_manager thinking/provider 分支(`docs/graph-agent-gateway/mvp1/README.md:39-40`)。

覆盖代码索引:

| 代码 | 覆盖原因 |
|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:14-72` | 现状 `select_verified_profile` 只按 ready/profile capability/input modality/reasoning 选 verified profile。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204` | `VerifiedProfile` 是一条 tested invocation profile，字段是 method/request mapper/status/default/rank，不是 ChatX init kwargs 表。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:20-32` | normalized runtime setting descriptor 列表定义 provider-neutral 设置键。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:35-202` | `normalize_route_capabilities` 把 provider 原始能力变成 normalized capabilities，并把 thinking/tool/structured output 等差异写进 capability。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-80` | `lint_role_routes` 用 capability 做 warn/block，不做 provider 调用构造。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:202-332` | runtime setting lint 检查 reasoning effort、structured output、thinking budget 等 provider 差异。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:72-113` | `resolve_role` 把 selected verified profile 写进 `ResolvedRoute.call_method_id/request_mapper_id`。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-1012` | provider 差异最终仍落在 `_call_*` kwargs 和 thinking 分支里。 |

## 编号执行流程(现状)

1. `ProviderRoute` 是一个 endpoint 上的物理模型 route；它保存 `provider_model_id`、`canonical_id`、capabilities 和 `verified_profiles`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-220`)。
2. `VerifiedProfile` 是一种已验证调用方式；它记录 `profile_id`、`capability`、`method_id`、`request_mapper_id`、状态、默认标记和排序，用于从多个调用方式中选一个(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`)。
3. `select_verified_profile` 是 verified profile 选择函数；它先过滤 status 为 ready 的 profile，再按输入模态和 reasoning 需求筛选(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:14-52`)。
4. `_profile_supports_reasoning` 是 reasoning profile 判定 helper；它靠 `capability`、`profile_id`、`request_mapper_id` 文本里是否包含 thinking/reasoning 来判断，不生成 ChatX kwargs(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:55-66`)。
5. `_preferred_profile` 是排序 helper；它按 default、fallback_rank、profile_id 选最优 ready profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:69-72`)。
6. `normalize_route_capabilities` 是 capability 归一化函数；它把 provider 原始 metadata 归一成 `CapabilityValue`，并为 Anthropic-compatible thinking 写入 `thinking_protocol`、`adaptive_thinking`、`manual_thinking_budget_supported` 等能力(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:35-202`)。
7. `lint_role_routes` 是 role route lint 函数；它根据 role 要求和 runtime settings 产 warn/error，blocking 时阻止解析，但不构造 provider client(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-80`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:116-122`)。
8. `resolve_role` 是 registry resolver；它调用 `select_verified_profile`，再把 selected profile 的 `profile_id`、`capability`、`method_id`、`request_mapper_id` 写入 `ResolvedRoute`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:72-113`)。
9. `GatewayChatModel._generate` 读取 `reasoning.enabled`、`reasoning.budget_tokens`、`reasoning.effort` 等 effective runtime settings 后传给 `_dispatch`(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:205-224`)。
10. `LLMClientManager._dispatch_provider_call` 按 protocol 分支把这些值传给 provider-specific `_call_*`；provider 差异最终散在 OpenAI Responses、Google thinking config、Anthropic thinking、Ark/OpenAI-compatible kwargs 中(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:866-988`)。

## Baseline / Alignment 差异

baseline 当前无独立 provider profile 模块。职责散在三层:registry 层选择 verified profile 和 capability/lint，resolver 把 method/request mapper 贴到 route，client_manager 在 provider 分支里写 kwargs 和 thinking payload(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:14-72`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:35-202`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-1012`)。

alignment 要引入的 `ProviderProfile` 不是现有 `VerifiedProfile`。`ProviderProfile` 是 ChatX 构造 profile，用 provider/model key 映射到 init kwargs、可选 `pre_init` 和动态 factory；`VerifiedProfile` 是 route 已验证调用方式，用 method/request mapper 做运行期选择(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:36-90`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`)。

## 决策原因

1. 现状 provider 差异太分散。OpenAI-compatible、Google、Ark、Anthropic 分别在 `_call_*` 函数里组织 kwargs，thinking 也在 provider 分支内处理(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:459-482`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:581-587`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:709-752`)。
2. capability 是“支持什么”，不是“怎么构造 ChatX”。`capabilities.py` 文件头明确 capabilities 描述 support/bounds，用户 runtime intent 属于 role/profile route entry；这不等于 provider init kwargs profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:1-5`)。
3. lint 只能 warn/block，不能变成动态 provider 选择。MVP0 alignment 明确禁止按 provider/capability/price/latency/availability 搜索替代 route，capability 只能 lint/warn/block/fail-fast(`docs/graph-agent-gateway/mvp0/mvp0-alignment.md:142-146`)。
4. provider profile 应只处理模型构造差异。权威记录要求用 deepagents `ProviderProfile` 模式承载 headers、Responses API、温度默认、thinking 开关等 init kwargs；只有 payload 差异才子类覆盖单方法，不能重写整套消息转换(`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:224-228`)。

## 代码索引 clues

- `ProviderProfile`:当前 gateway 源码没有该调用层类；目标用途是 provider/model 到 ChatX init kwargs、`pre_init`、factory 的声明式配置(`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:224-228`)。
- `VerifiedProfile`:现有 schema 类，表示一条已经验证过的 provider route 调用方式，不是 ChatX 构造配置(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`)。
- `select_verified_profile`:现有选择函数，按 ready 状态、输入模态和 reasoning 需求挑一个 `VerifiedProfile`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:14-52`)。
- `normalize_route_capabilities`:现有能力归一化函数，把 provider 原始能力变成 normalized capability records(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:35-202`)。
- `lint_role_routes`:现有 lint 函数，检查 role route 与 runtime settings 是否违反能力约束(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-80`)。
- `LLMClientManager._call_anthropic_compatible`:现有 Anthropic-compatible provider 调用函数，内部直接写 thinking payload 与 tool choice 等差异(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:672-769`)。
- `_google_thinking_config`:现有 Google thinking config helper，把 reasoning effort/budget 映射到 Google config(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:1119-1131`)。

## 待办/疑点

1. 待办:命名上需要避免 `ProviderProfile` 与现有 `VerifiedProfile` 混淆；前者是 ChatX 构造 profile，后者是 route probe/verified 调用方式。
2. 待办:`call_method_id` 与 `request_mapper_id` 在 MVP1 后是否继续存在，需要和 `ProviderProfile` 的 init kwargs 表分清层级；现状它们由 selected verified profile 写入 route(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:94-103`)。
3. 疑点:现有 `_profile_supports_reasoning` 通过字符串包含 thinking/reasoning 判断 profile 是否支持 reasoning，是否足够稳定应在 05 模块继续跟踪；本模块只记录它不是 ChatX provider profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:55-66`)。
