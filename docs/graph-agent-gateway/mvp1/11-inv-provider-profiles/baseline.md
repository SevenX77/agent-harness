---
module: 11-inv-provider-profiles
doc: baseline
status: drafted
verified_at: 2026-06-06
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/provider_profiles.py:ProviderProfile/register_provider_profile/get_provider_profile/apply_provider_profile · packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py:RouteChatModelFactory/_apply_profiles · packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:ProfileSelectionError/select_verified_profile/_profile_supports_reasoning/_preferred_profile · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:VerifiedProfile/ProviderRoute/ResolvedRoute · packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:RUNTIME_SETTING_DESCRIPTORS/normalize_route_capabilities/build_runtime_setting_descriptors · packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:lint_role_routes/capability_key_for_lint · packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:resolve_role · packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:LLMClientManager/_dispatch_provider_call/_call_openai_compatible/_call_openai_responses/_call_google_genai/_call_ark_runtime/_call_anthropic_compatible/_google_thinking_config
units: [provider-profiles-init-kwargs]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 11-inv-provider-profiles - Baseline(现状)

> **Tier**：③b gateway 公共能力（**MVP1 新建**调用层 provider 差异表；归属表判 11=纯 ③b 新建，见 `module-disposition-revised.md:54`）。**WS-1 后 `ProviderProfile` 调用层模块已存在**，但默认 registry 为空；它与 `registry/profile_selector.py` 的 `VerifiedProfile` 仍是不同层级。MVP1 目标见同目录 `mvp1-alignment.md`。

## 覆盖代码(含覆盖率)

本模块当前已有独立 `ProviderProfile` 调用层模块。`ProviderProfile` 是 provider/model 到 ChatX init kwargs 的声明式配置模式；`VerifiedProfile` 是 registry 里“已验证调用方式”的选择结果，不是 ChatX 构造 profile。

覆盖率:100%。这里覆盖 MVP1 manifest 指定的 profile 职责:ProviderProfile registry、factory overlay、verified profile selection、capability normalization、runtime lint、resolver selected profile 字段，以及 legacy client_manager thinking/provider 分支的延期状态。

覆盖代码索引:

| 代码 | 覆盖原因 |
|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/provider_profiles.py` | `ProviderProfile`、注册表、provider/exact-model merge、`apply_provider_profile` 已落地；默认注册表为空。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py` | factory 通过 `_apply_profiles` 应用 profile overlay，当前 key 为 `endpoint_id:provider_model_id`。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:14-72` | 现状 `select_verified_profile` 只按 ready/profile capability/input modality/reasoning 选 verified profile。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204` | `VerifiedProfile` 是一条 tested invocation profile，字段是 method/request mapper/status/default/rank，不是 ChatX init kwargs 表。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:20-32` | normalized runtime setting descriptor 列表定义 provider-neutral 设置键。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:35-202` | `normalize_route_capabilities` 把 provider 原始能力变成 normalized capabilities，并把 thinking/tool/structured output 等差异写进 capability。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-80` | `lint_role_routes` 用 capability 做 warn/block，不做 provider 调用构造。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:202-332` | runtime setting lint 检查 reasoning effort、structured output、thinking budget 等 provider 差异。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:72-113` | `resolve_role` 把 selected verified profile 写进 `ResolvedRoute.call_method_id/request_mapper_id`。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-1012` | 旧 provider 差异/ thinking 分支仍在 legacy helper 中，但 WS-1 主路径不再调用这些 `_call_*`。 |

## 编号执行流程(现状)

1. `ProviderProfile` 保存 `init_kwargs`、可选 `pre_init(route)` 和可选 `init_kwargs_factory(route)`。
2. `register_provider_profile(key, profile)` 会按规范化 key 注册 profile；重复注册同 key 时增量 merge，后者覆盖 init kwargs。
3. `get_provider_profile(spec)` 会先取 provider-level key，再取 exact spec key，并把二者 merge。当前没有内置默认注册，registry 初始为空。
4. `apply_provider_profile(spec, route=..., **caller_kwargs)` 的优先级是 `pre_init` -> `init_kwargs` -> `init_kwargs_factory` -> caller kwargs，因此 factory 的显式 kwargs 最终优先。
5. `RouteChatModelFactory._apply_profiles` 当前使用 `f"{route.endpoint_id}:{route.provider_model_id}"` 查 profile；这等于把 endpoint 维度纳入 provider/model key。
6. `VerifiedProfile` 仍由 `select_verified_profile` 选择，并写入 `ResolvedRoute.call_method_id/request_mapper_id`；它不生成 ChatX init kwargs。
7. `normalize_route_capabilities` 和 `lint_role_routes` 仍表达“支持什么”和“是否违规”，不是 provider init kwargs overlay。
8. thinking 当前只在 factory runtime kwargs 中映射了部分字段，且 ChatX `AIMessage` 结果桥不拍平 content；完整 provider profile defaults、DeepSeek 单方法 payload patch 和旧 thinking helper 迁移仍未完成。

## Baseline / Alignment 差异

`ProviderProfile` 已建，但只是空 registry + merge/apply 原语。职责不再完全散在 client_manager；factory 已能在构造 ChatX 前应用 profile overlay。旧 client_manager `_call_*` 仍保留 provider-specific thinking/payload 代码，但已经不是生产主调用路径。

alignment 要引入的 `ProviderProfile` 不是现有 `VerifiedProfile`。这一点在代码里已拆开：`ProviderProfile` 位于 `provider_profiles.py`，用于 ChatX 构造；`VerifiedProfile` 仍在 registry schema 中，用 method/request mapper 做运行期选择。

尚未完成的 alignment 差异：registry 默认空，未 seed OpenAI/Ark/Anthropic/Google provider defaults；thinking 归一化只完成局部映射和结果不拍平；DeepSeek reasoning-content 单方法 patch 未移植；key 规则 `endpoint_id:provider_model_id` 仍是待确认选择。

## 决策原因

1. provider 差异过去太分散。OpenAI-compatible、Google、Ark、Anthropic 分别在 `_call_*` 函数里组织 kwargs，thinking 也在 provider 分支内处理；WS-1 先把 profile 原语和 factory overlay 落地。
2. capability 是“支持什么”，不是“怎么构造 ChatX”。`capabilities.py` 文件头明确 capabilities 描述 support/bounds，用户 runtime intent 属于 role/profile route entry；这不等于 provider init kwargs profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:1-5`)。
3. lint 只能 warn/block，不能变成动态 provider 选择。MVP1 当前权威是 README 的 05 模块边界与 05 文档；当前代码也只在 `lint_role_routes` 里产 warn/block，并由 `resolve_role` 对 blocking lint fail-fast，不会按 capability/price/latency/availability 搜索替代 route(`docs/graph-agent-gateway/mvp1/README.md:58`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-85`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:116-122`)。
4. provider profile 应只处理模型构造差异。client 层 A' 重设计决策（F6）要求用 deepagents `ProviderProfile` 模式承载 headers、Responses API、温度默认、thinking 开关等 init kwargs；只有 payload 差异才子类覆盖单方法，不能重写整套消息转换(完整逻辑 + PM 拍板原话见同目录 `mvp1-alignment.md` §4 F6 / §5 决策 1)。
5. `endpoint_id:provider_model_id` 的临时 key 选择是为了同时区分 endpoint 级 base_url/credential/protocol 差异和物理模型差异；这避免同一 canonical model 在不同 endpoint/provider 下互相覆盖。但 alignment 11 §8 把 key 规则列为开放问题，所以这里仅记录理由，待最终确认。

## 代码索引 clues

- `ProviderProfile`:已存在，目标用途是 provider/model 到 ChatX init kwargs、`pre_init`、factory 的声明式配置。
- `_PROVIDER_PROFILES`:默认空 registry；没有内置 provider defaults。
- `register_provider_profile/get_provider_profile/apply_provider_profile`:已存在的 profile 原语。
- `RouteChatModelFactory._apply_profiles`:当前用 `endpoint_id:provider_model_id` 查 profile。
- `VerifiedProfile`:现有 schema 类，表示一条已经验证过的 provider route 调用方式，不是 ChatX 构造配置(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`)。
- `select_verified_profile`:现有选择函数，按 ready 状态、输入模态和 reasoning 需求挑一个 `VerifiedProfile`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:14-52`)。
- `normalize_route_capabilities`:现有能力归一化函数，把 provider 原始能力变成 normalized capability records(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:35-202`)。
- `lint_role_routes`:现有 lint 函数，检查 role route 与 runtime settings 是否违反能力约束(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-80`)。
- `LLMClientManager._call_anthropic_compatible`:现有 Anthropic-compatible provider 调用函数，内部直接写 thinking payload 与 tool choice 等差异(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:672-769`)。
- `_google_thinking_config`:现有 Google thinking config helper，把 reasoning effort/budget 映射到 Google config(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:1119-1131`)。

## 待办/疑点

1. 待办:seed ProviderProfile 默认表，至少覆盖本轮 official ChatX 主路径需要的 provider/model defaults。
2. 待办:thinking 归一化完整迁入 ProviderProfile 或单方法 patch；当前只是局部 runtime kwargs 映射和 ChatX result 不拍平。
3. 待办:`call_method_id` 与 `request_mapper_id` 在 MVP1 后是否继续存在，需要和 `ProviderProfile` 的 init kwargs 表分清层级。
4. 疑点:ProviderProfile key 暂用 `endpoint_id:provider_model_id`，待 alignment 11 §8 确认。
5. 疑点:现有 `_profile_supports_reasoning` 通过字符串包含 thinking/reasoning 判断 profile 是否支持 reasoning，是否足够稳定应在 05 模块继续跟踪；本模块只记录它不是 ChatX provider profile。
