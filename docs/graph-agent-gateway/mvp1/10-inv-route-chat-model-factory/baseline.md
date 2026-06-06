---
module: 10-inv-route-chat-model-factory
doc: baseline
status: drafted
verified_at: 2026-06-06
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py:RouteChatModelFactory/build · packages/graph-agent-gateway/src/graph_agent_gateway/models.py:GenericRouteChatModel · packages/graph-agent-gateway/src/graph_agent_gateway/provider_profiles.py:ProviderProfile/apply_provider_profile · packages/graph-agent-gateway/src/graph_agent_gateway/registry/base_url.py:canonicalize_base_url · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:Protocol/ResolvedRoute/ResolvedRole · packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel/_dispatch/_invoke_with_token_escalation · packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:LLMClientManager/dispatch_provider_call/_dispatch_provider_call/_call_with_token_escalation
units: [route-chat-model-factory]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 10-inv-route-chat-model-factory - Baseline(现状)

> **Tier**：③b gateway 公共能力（**MVP1 新建**调用层核心；归属表判 10=纯 ③b 新建，见 `module-disposition-revised.md:53`）。**WS-1 后本模块源码已存在**：`RouteChatModelFactory` 负责把一条 `ResolvedRoute` 构造成官方 LangChain ChatX；generic 普通 chat 内核仍未实现，当前 fail-loud。MVP1 目标见同目录 `mvp1-alignment.md`。

## 覆盖代码(含覆盖率)

本模块当前已有独立生产模块。`packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py` 提供 `RouteChatModelFactory.build`；`packages/graph-agent-gateway/src/graph_agent_gateway/models.py` 提供 `GenericRouteChatModel`，但它是 fail-loud shell，不是完整 generic chat 内核。

覆盖率:100%。这里覆盖的是 MVP1 manifest 指定的 factory 职责来源:route 字段到 ChatX init kwargs、base_url 幂等归一、credential 读取、provider profile overlay、generic fail-loud、以及旧 `client_manager` provider-call path 的延期状态。

覆盖代码索引:

| 代码 | 覆盖原因 |
|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py` | `RouteChatModelFactory.build` 是 route -> official ChatX 的生产构造器。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/models.py` | `GenericRouteChatModel` 是 unknown protocol 的 fail-loud shell，防止静默空回复。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/provider_profiles.py` | factory 通过 `apply_provider_profile` 合并 provider/model init kwargs overlay。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/base_url.py` | factory 调用 `canonicalize_base_url` 作为调用侧幂等双保险。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-459` | `ResolvedRoute` 是一条运行期 route 候选，`ResolvedRole` 是带 fallback 顺序的 route 列表；这是当前 factory 的输入数据形状。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py` | `_dispatch` 调用 factory + ChatX invoke，保留 `GatewayChatModel` 编排外壳。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py` | `dispatch_provider_call/_dispatch_provider_call/_call_*` 已无生产活调用方，源码注释标为 legacy/generic 候选内核。 |

## 编号执行流程(现状)

1. `GatewayChatModel._dispatch` 收到一条 `ResolvedRoute`、原始 `BaseMessage` 列表和 runtime kwargs。
2. `_dispatch` 构造 `RouteChatModelFactory(credential_provider=...)`，再进入 `_invoke_with_token_escalation`；`client_manager` 参数在 provider 调用上不再使用。
3. `RouteChatModelFactory.build` 先按 route protocol 调 `canonicalize_base_url`，保证 OpenAI/Ark/Anthropic/Google base_url 规则幂等。
4. factory 用 `credential_provider.get(route.credential_ref)` 解析密钥；没有 credential provider 时 fail-fast。
5. factory 从 `effective_runtime_settings` 和 caller kwargs 提取 `temperature/max_tokens/top_p/stop/seed/reasoning_effort`，再映射到各 ChatX 的 init kwargs。
6. `openai_compatible` 和 `ark_runtime` 构造 `ChatOpenAI`；Ark base_url 归一到 `/api/v3`。
7. `anthropic_compatible` 构造 `ChatAnthropic`，base_url 归一为 provider root。
8. `google_genai` lazy import `langchain_google_genai.ChatGoogleGenerativeAI`；缺 optional extra 时在 build 时抛清晰 `ImportError`。
9. factory 调用 `apply_provider_profile(f"{endpoint_id}:{provider_model_id}", route=route, **kwargs)`，让 caller kwargs 最终优先。
10. 未识别 protocol 返回 `GenericRouteChatModel`，但该模型 `_generate` 会抛 `NotImplementedError`，不再静默吐空 `AIMessage`。

## Baseline / Alignment 差异

`RouteChatModelFactory` 已建并成为 WS-1 主路径。它没有删除 `GatewayChatModel`：resolver 仍返回 gateway 外壳，fallback/probe/usage/metadata 仍在外壳里，只有单 route 的真实 provider 调用换成 ChatX。

alignment 目标不是删除 `GatewayChatModel`。client 层 A' 重设计决策已否决“resolver 直接裸返回 ChatX”的方案（方案 A），要求保留 `GatewayChatModel` 做编排外壳，只把每条 route 的真实调用换成原生 LangChain ChatX(完整决策逻辑 + PM 原话见同目录 `mvp1-alignment.md` §4 D1 / §5 决策 1)。

尚未完成的 alignment 差异：generic 普通 chat 内核未实现；`LLMClientManager` 旧 provider-call helpers 暂留但无生产活调用方；ProviderProfile registry 默认空，只在外部注册 profile 时生效。

## 决策原因

1. 需要拆开“编排”和“调用”（D2 编排/调用分离）。编排输入 = role/model override，输出 = `ResolvedRoute` 链；调用层输入是一条 `ResolvedRoute` 加 messages，输出是 `AIMessage`/结果(完整逻辑 + PM 原话见同目录 `mvp1-alignment.md` §4 D2 / §5 决策 1)。
2. `GatewayChatModel._generate` 仍做 probe、熔断、usage、metadata、异常分类；WS-1 只替换第一个 provider 调用点，不拆 gateway 外壳。
3. 旧 client_manager 调用层问题集中在消息转换和 provider payload；factory + ChatX 让 provider SDK wrapper 不再散落在 `_call_*`。
4. `ProviderProfile` key 当前用 `endpoint_id:provider_model_id`，理由是 endpoint_id 同时代表 credential/base_url/协议边界，provider_model_id 代表精确物理模型；这样避免只按 canonical_id 时跨 endpoint/provider 冲突。但这是 alignment 11 §8 的开放问题，仍待确认。

## 代码索引 clues

- `RouteChatModelFactory`:已存在，一条 `ResolvedRoute` 到官方 ChatX 实例的构造器。
- `GenericRouteChatModel`:已存在，但普通 chat 未实现；fail-loud。
- `GatewayChatModel._dispatch`:ChatX 主路径入口。
- `canonicalize_base_url`:factory 调用侧 base_url 幂等归一共享原语。
- `LLMClientManager.dispatch_provider_call/_dispatch_provider_call/_call_*`:legacy helper，当前无生产活调用方。

## 待办/疑点

1. 待办:实现 `GenericRouteChatModel` 普通 chat 内核，或确认 unknown protocol 永久 fail-loud。
2. 待办:删除旧 `client_manager` provider-call helpers，或把它们收编进 generic 普通 chat 内核。
3. 待办:base_url 保存时归一化属于 03 模块；10 模块只记录调用时幂等双保险，不能替代保存侧修复。
4. 疑点:`ProviderProfile` lookup key 暂用 `endpoint_id:provider_model_id`，需确认是否改成 provider/model/canonical 其他组合。
