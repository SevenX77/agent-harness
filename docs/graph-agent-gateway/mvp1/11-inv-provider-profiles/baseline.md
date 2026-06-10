---
module: 11-inv-provider-profiles
doc: baseline
status: drafted
verified_at: 2026-06-06
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/provider_profiles.py:ProviderProfile/register_provider_profile/get_provider_profile/apply_provider_profile/apply_provider_profile_layers/route_provider_profile_keys · packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py:RouteChatModelFactory/_apply_profiles · packages/graph-agent-gateway/src/graph_agent_gateway/ordinary_chat.py:dispatch_ordinary_chat/_dispatch_provider_call/_call_openai_compatible/_call_openai_responses/_call_google_genai/_call_ark_runtime/_call_anthropic_compatible/_google_thinking_config · packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:ProfileSelectionError/select_verified_profile/_profile_supports_reasoning/_preferred_profile · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:VerifiedProfile/ProviderRoute/ResolvedRoute · packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:RUNTIME_SETTING_DESCRIPTORS/normalize_route_capabilities/build_runtime_setting_descriptors · packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:lint_role_routes/capability_key_for_lint · packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:resolve_role
units: [provider-profiles-init-kwargs]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 11-inv-provider-profiles - Baseline(现状)

> **Tier**：③b gateway 公共能力（MVP1 新增设计单元/调用层 provider 差异表；归属表判 11=纯 ③b，见 `module-disposition-revised.md:54`）。**WS-1 后 `ProviderProfile` 调用层模块已存在**，并 seed 最小 defaults；它与 `registry/profile_selector.py` 的 `VerifiedProfile` 仍是不同层级。MVP1 目标见同目录 `mvp1-alignment.md`。

## 覆盖代码(含覆盖率)

本模块当前已有独立 `ProviderProfile` 调用层模块。`ProviderProfile` 是 provider/model 到 ChatX init kwargs 的声明式配置模式；`VerifiedProfile` 是 registry 里“已验证调用方式”的选择结果，不是 ChatX 构造 profile。

覆盖率:100%。这里覆盖 MVP1 manifest 指定的 profile 职责:ProviderProfile registry、factory overlay、verified profile selection、capability normalization、runtime lint、resolver selected profile 字段，以及 `ordinary_chat.py` 中仍待逐步收束的 ordinary provider thinking/payload 分支。

覆盖代码索引:

| 代码 | 覆盖原因 |
|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/provider_profiles.py` | `ProviderProfile`、注册表、provider/exact-model merge、route key 派生、三层 overlay 与最小 defaults 已落地。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py` | factory 通过 `_apply_profiles` 应用 profile overlay，key 顺序为 `protocol:{protocol}` → `endpoint:{endpoint_id}` → `endpoint:{endpoint_id}:model:{provider_model_id}`。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:14-72` | 现状 `select_verified_profile` 只按 ready/profile capability/input modality/reasoning 选 verified profile。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204` | `VerifiedProfile` 是一条 tested invocation profile，字段是 method/request mapper/status/default/rank，不是 ChatX init kwargs 表。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:20-32` | normalized runtime setting descriptor 列表定义 provider-neutral 设置键。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:35-202` | `normalize_route_capabilities` 把 provider 原始能力变成 normalized capabilities，并把 thinking/tool/structured output 等差异写进 capability。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-80` | `lint_role_routes` 用 capability 做 warn/block，不做 provider 调用构造。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:202-332` | runtime setting lint 检查 reasoning effort、structured output、thinking budget 等 provider 差异。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:72-113` | `resolve_role` 把 selected verified profile 写进 `ResolvedRoute.call_method_id/request_mapper_id`。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/ordinary_chat.py` | generic ordinary-chat provider core；provider 差异/ thinking 分支已从 `client_manager.py` 收编到这里，官方 ChatX 主路径不直接调用。 |

## 编号执行流程(现状)

1. `ProviderProfile` 保存 `init_kwargs`、可选 `pre_init(route)` 和可选 `init_kwargs_factory(route)`。
2. `register_provider_profile(key, profile)` 会按规范化 key 注册 profile；重复注册同 key 时增量 merge，后者覆盖 init kwargs。
3. `get_provider_profile(spec)` 会先取 provider-level key，再取 exact spec key，并把二者 merge；`apply_provider_profile_layers(specs, ...)` 按显式 key 序列逐层 overlay。
4. `apply_provider_profile(spec, route=..., **caller_kwargs)` 与 `apply_provider_profile_layers(...)` 的优先级都是 `pre_init` -> `init_kwargs` -> `init_kwargs_factory` -> caller kwargs，因此 factory 的显式 kwargs 最终优先。
5. `RouteChatModelFactory._apply_profiles` 当前通过 `route_provider_profile_keys(route)` 查三层 profile：`protocol:{protocol}`、`endpoint:{endpoint_id}`、`endpoint:{endpoint_id}:model:{provider_model_id}`。
6. `VerifiedProfile` 仍由 `select_verified_profile` 选择，并写入 `ResolvedRoute.call_method_id/request_mapper_id`；它不生成 ChatX init kwargs。
7. `normalize_route_capabilities` 和 `lint_role_routes` 仍表达“支持什么”和“是否违规”，不是 provider init kwargs overlay。
8. thinking 当前只在 factory runtime kwargs 中映射了部分字段，且 ChatX `AIMessage` 结果桥不拍平 content；DeepSeek 单方法 payload patch 已落地，其它 provider thinking 规则和旧 thinking helper 迁移仍未完成。

## Baseline / Alignment 差异

`ProviderProfile` 已建，包含 registry、merge/apply 原语、route key 派生、factory overlay 与最小 defaults。职责不再完全散在 ordinary provider branches；factory 已能在构造 ChatX 前应用 profile overlay。provider-specific ordinary chat thinking/payload 代码当前位于 `ordinary_chat.py`，已经不是官方 ChatX 生产主调用路径。

alignment 要引入的 `ProviderProfile` 不是现有 `VerifiedProfile`。这一点在代码里已拆开：`ProviderProfile` 位于 `provider_profiles.py`，用于 ChatX 构造；`VerifiedProfile` 仍在 registry schema 中，用 method/request mapper 做运行期选择。

尚未完成的 alignment 差异：thinking 归一化只完成局部映射、结果不拍平和 DeepSeek reasoning-content payload replay；默认表仍保持最小，只 seed OpenAI-compatible/Ark 的 `stream_usage`，不引入大而全 provider 表；其它 provider thinking/payload 差异仍需独立测试。

## 决策原因

1. provider 差异过去太分散。OpenAI-compatible、Google、Ark、Anthropic 分别在 provider-call 函数里组织 kwargs，thinking 也在 provider 分支内处理；WS-1 先把 profile 原语和 factory overlay 落地，ordinary-chat 分支已集中到 `ordinary_chat.py`。
2. capability 是“支持什么”，不是“怎么构造 ChatX”。`capabilities.py` 文件头明确 capabilities 描述 support/bounds，用户 runtime intent 属于 role/profile route entry；这不等于 provider init kwargs profile(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:1-5`)。
3. lint 只能 warn/block，不能变成动态 provider 选择。MVP1 当前权威是 README 的 05 模块边界与 05 文档；当前代码也只在 `lint_role_routes` 里产 warn/block，并由 `resolve_role` 对 blocking lint fail-fast，不会按 capability/price/latency/availability 搜索替代 route(`docs/graph-agent-gateway/mvp1/README.md:58`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-85`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:116-122`)。
4. provider profile 应只处理模型构造差异。client 层 A' 重设计决策（F6）要求用 deepagents `ProviderProfile` 模式承载 headers、Responses API、温度默认、thinking 开关等 init kwargs；只有 payload 差异才子类覆盖单方法，不能重写整套消息转换(完整逻辑 + PM 拍板原话见同目录 `mvp1-alignment.md` §4 F6 / §5 决策 1)。
5. `endpoint_id:provider_model_id` 临时 key 已替换为显式三层 key：`protocol:{protocol}` 承载 provider/protocol 默认，`endpoint:{endpoint_id}` 承载 endpoint 级覆盖，`endpoint:{endpoint_id}:model:{provider_model_id}` 承载 exact-model 覆盖；这样同时保留 endpoint 维度和物理模型维度，且覆盖顺序清楚。

## 代码索引 clues

- `ProviderProfile`:已存在，目标用途是 provider/model 到 ChatX init kwargs、`pre_init`、factory 的声明式配置。
- `_PROVIDER_PROFILES`:包含最小内置 defaults：`protocol:openai_compatible` 与 `protocol:ark_runtime` 默认 `stream_usage=True`。
- `register_provider_profile/get_provider_profile/apply_provider_profile`:已存在的 profile 原语。
- `route_provider_profile_keys/apply_provider_profile_layers`:gateway route key 派生与三层 overlay 入口。
- `RouteChatModelFactory._apply_profiles`:当前按 protocol-level、endpoint-level、exact-model 顺序查 profile。
- `PatchedChatDeepSeek`:DeepSeek OpenAI-compatible/Ark route 的 payload patch，仅覆盖 `_get_request_payload` replay 多轮 assistant `reasoning_content`，不属于 ProviderProfile defaults。
- `VerifiedProfile`:现有 schema 类，表示一条已经验证过的 provider route 调用方式，不是 ChatX 构造配置(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`)。
- `select_verified_profile`:现有选择函数，按 ready 状态、输入模态和 reasoning 需求挑一个 `VerifiedProfile`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/profile_selector.py:14-52`)。
- `normalize_route_capabilities`:现有能力归一化函数，把 provider 原始能力变成 normalized capability records(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:35-202`)。
- `lint_role_routes`:现有 lint 函数，检查 role route 与 runtime settings 是否违反能力约束(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py:27-80`)。
- `ordinary_chat._call_anthropic_compatible`:现有 Anthropic-compatible ordinary provider 调用函数，内部直接写 thinking payload 与 tool choice 等差异。
- `ordinary_chat._google_thinking_config`:现有 Google thinking config helper，把 reasoning effort/budget 映射到 Google config。

## 待办/疑点

1. 待办:thinking 归一化完整迁入 ProviderProfile 或单方法 patch；当前只是局部 runtime kwargs 映射、ChatX result 不拍平和 DeepSeek reasoning-content replay。
2. 待办:`call_method_id` 与 `request_mapper_id` 在 MVP1 后是否继续存在，需要和 `ProviderProfile` 的 init kwargs 表分清层级。
3. 疑点:现有 `_profile_supports_reasoning` 通过字符串包含 thinking/reasoning 判断 profile 是否支持 reasoning，是否足够稳定应在 05 模块继续跟踪；本模块只记录它不是 ChatX provider profile。
