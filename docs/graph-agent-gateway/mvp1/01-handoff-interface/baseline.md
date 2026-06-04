---
module: 01-handoff-interface
doc: baseline
status: drafted
verified_at: 2026-06-02
---

# 01-handoff-interface — Baseline(现状)

> 本文只写当前代码事实。MVP0 文档已标注旧 `ResolvedProvider/call_chain` 模型过时，应以 registry 里的 `ResolvedRoute/ResolvedRole` 为准；见 `docs/graph-agent-gateway/mvp0/baseline.md:8` 和 `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:64`。

## 覆盖代码(含覆盖率)

覆盖率：本模块 brief 要求的 handoff 入口已核实 100%，但有 1 个路径命名偏差需要主控确认。

| 覆盖项 | 覆盖状态 | 现状说明 |
|---|---:|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:ModelResolverProtocol` | 100% | `ModelResolverProtocol` 是 Engine 侧依赖注入协议：调用方只拿 LangChain chat model，不直接拿 route。**判据:③b 公共;MVP1 应补 route 级直调 public API,详见 `mvp1-alignment.md` §3。** |
| `packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py` | 100% | `__init__.py` 是 Gateway 包公开门面：导出 resolver、chat model、异常和 fallback event。**判据:③b 公共。** |
| `apps/studio/backend/app/models/copilot.py` | 100% | `CopilotWsRequestPayload` 和 `CopilotEvent*` 是 Studio Copilot WebSocket 输入/输出事件模型。manifest 已按实际路径登记。**判据:③a 应用契约——这是 Studio copilot 应用自己的 WS 契约,引用 route(经 ③b 取得)≠ ③b 泄漏;详见 `mvp1-alignment.md` §3/§4。** |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRoute` | 100% | `ResolvedRoute` 是当前 registry resolver 产出的单条可执行 route 数据：它把 endpoint、protocol、credential、模型和 runtime settings 合并成一条候选。**判据:③b 公共(权威源)。** |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRole` | 100% | `ResolvedRole` 是当前 registry resolver 产出的 role 解析结果：它保存 role 元数据、runtime policy 和有序 `routes`。**判据:③b 公共(权威源)。** |

## route 契约字段(现状)

`ResolvedRoute` 是当前 route 数据契约：字段定义位于 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415`。

| 字段 | 当前用途 | 代码依据 |
|---|---|---|
| `role_name` | 标记本 route 来自哪个逻辑 role，fallback event 和 metadata 用它定位业务上下文。 | `registry/schema.py:420`、`gateway_chat_model.py:383` |
| `route_id` | route 的唯一执行标识，当前也是 candidate id。 | `registry/schema.py:421`、`gateway_chat_model.py:395` |
| `endpoint_id` | 指向 endpoint，用于 credential、usage、Copilot session provider key。 | `registry/schema.py:422`、`gateway_chat_model.py:324`、`copilot.py:245` |
| `protocol` | 决定调用协议，如 `openai_compatible`、`anthropic_compatible`。 | `registry/schema.py:423`、`registry/schema.py:19` |
| `base_url` | 传给调用层或 Copilot SDK 的 endpoint URL；现状仍由调用方局部处理特殊 protocol。 | `registry/schema.py:424`、`copilot.py:460` |
| `credential_ref` | 指向密钥引用；`ResolvedRoute` 校验它不能为空。 | `registry/schema.py:425`、`registry/schema.py:441` |
| `credential_fingerprint` | 表示密钥版本/指纹，用于缓存和诊断，不暴露明文。 | `registry/schema.py:426`、`registry/resolver.py:85` |
| `timeout_seconds` / `trust_env` / `proxy_env` | endpoint 级运行环境参数。 | `registry/schema.py:427`、`registry/schema.py:428`、`registry/schema.py:429` |
| `provider_model_id` | provider 侧真实模型名，传给 SDK 或写入 response metadata。 | `registry/schema.py:430`、`gateway_chat_model.py:326`、`copilot.py:244` |
| `canonical_id` | 归一化模型身份，用于展示、分组和诊断。 | `registry/schema.py:431`、`gateway_chat_model.py:327` |
| `selected_profile_id` / `selected_profile_capability` | 表示 resolver 选中的 verified profile，现状作为 route 诊断信息保留。 | `registry/schema.py:432`、`registry/schema.py:433` |
| `call_method_id` / `request_mapper_id` | 表示 provider 调用方法和请求映射器；Copilot 用它识别 Ark/DeepSeek 的 Anthropic 兼容路径。 | `registry/schema.py:434`、`registry/schema.py:435`、`copilot.py:462` |
| `capabilities` | route 能力描述，resolver 用它计算默认 runtime settings。 | `registry/schema.py:436`、`registry/resolver.py:104` |
| `runtime_settings` | role/profile route entry 上用户保存的 normalized settings。 | `registry/schema.py:437`、`registry/resolver.py:105` |
| `effective_runtime_settings` | resolver 合成后的实际调用参数及来源，写入 response metadata 和 fallback event。 | `registry/schema.py:438`、`gateway_chat_model.py:331`、`gateway_chat_model.py:391` |
| `snapshot_version` | 可选快照版本字段；当前 `resolve_role` 构造 route 时未显式填入。 | `registry/schema.py:439`、`registry/resolver.py:78` |

`ResolvedRole` 是当前 role 解析结果：字段定义位于 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448`。

| 字段 | 当前用途 | 代码依据 |
|---|---|---|
| `role_name` | role 名称，传给 `GatewayChatModel` 和异常 payload。 | `registry/schema.py:453`、`resolver.py:135` |
| `system_prompt_prefix` | role 级系统提示前缀，现状在 gateway 调用前拼到 messages。 | `registry/schema.py:454`、`gateway_chat_model.py:104` |
| `runtime_policy` | provider down TTL、probe timeout、token escalation 等运行策略。 | `registry/schema.py:455`、`gateway_chat_model.py:109` |
| `routes` | 有序 fallback route 列表，是当前执行循环的候选来源。 | `registry/schema.py:456`、`gateway_chat_model.py:111` |
| `lint_results` | resolver 对 role-route 能力 lint 的结果。 | `registry/schema.py:457`、`registry/resolver.py:116` |
| `source_profile_id` / `source_profile_snapshot` | 记录 role 是否来自 model profile，供 UI 溯源。 | `registry/schema.py:458`、`registry/schema.py:459` |

## resolve API 契约(现状)

`ModelResolverProtocol` 是 Engine 认识模型解析器的接口：它定义 `resolve()` 并返回 `BaseChatModel`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:24` 和 `protocol.py:28`。

1. 调用方传 `role_name`，表示当前 phase 要用的逻辑角色；协议允许 `None`，但当前 `ModelResolver.resolve()` 对 `None` 直接抛 `GatewayRoleNotConfiguredError`，见 `protocol.py:30` 和 `resolver.py:87`。
2. 调用方可传 `thinking_enabled`，表示是否覆盖 reasoning/thinking 开关；当前 resolver 在未传时从首条 route 的 `reasoning.enabled` effective setting 计算，见 `protocol.py:32` 和 `resolver.py:114`。
3. 调用方可传 `model_override`，现状语义实际是 route override；`resolve_role()` 用它替换 role 的 fallback chain，见 `protocol.py:33` 和 `registry/resolver.py:45`。
4. 调用方传 `callbacks` 和 `phase_name`，用于 fallback event 和 tracing 定位，见 `protocol.py:34`、`protocol.py:35`、`resolver.py:140`。
5. 调用方可传 `predict_context`，让 resolver 返回 `PredictGatewayChatModel` 而非真实调用模型，见 `protocol.py:36` 和 `resolver.py:119`。
6. 返回值是 `BaseChatModel`，所以 route 仍被包在模型对象内部，而不是作为公开 API 输出，见 `protocol.py:38` 和 `resolver.py:135`。

`__init__.py` 是 Gateway 公共导出边界：它把 `ModelResolverProtocol`、`ModelResolver`、`GatewayChatModel`、结构化异常和 `LLMFallbackEvent` 暴露给外部包，见 `packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py:5` 和 `__init__.py:15`。

## 两个消费方各取什么(现状)

1. Graph Agent phase 消费方只取 LangChain 模型。`LlmPhaseNode._resolved_tracing_model` 是 phase 侧解析入口：它调用 `resolver.resolve(phase.tier, model_override=..., callbacks=..., phase_name=...)`，随后把返回模型包进 `TracingClientProxy`，见 `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:167`、`llm_phase_node.py:173`、`llm_phase_node.py:193`。它没有直接读取 `ResolvedRoute`。
2. Gateway runtime 消费方在模型内部读取 route。`GatewayChatModel._generate` 是当前 fallback 执行循环：它遍历 `self.resolved_role.routes`，做 marked-down、probe、dispatch、usage 和 fallback event，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:96`、`gateway_chat_model.py:111`、`gateway_chat_model.py:190`。
3. Studio Copilot 消费方已经直接取 route 列表，但这是 service 内部 helper，不是 Gateway 公共 handoff API。`stream_query` 是 Copilot WebSocket 业务入口：它调用 `_resolve_copilot_runtime()` 得到 `routes` 和 `credential_provider`，再自己用 `ClaudeSDKClient` 调用，见 `apps/studio/backend/app/services/copilot.py:201`、`copilot.py:210`、`copilot.py:242`。
4. `CopilotWsRequestPayload` 是 Copilot WS 请求体：它只含 `user_message` 和 `model_override`，没有 route payload，见 `apps/studio/backend/app/models/copilot.py:21`。
5. `CopilotEvent` 是 Copilot WS 输出联合类型：它只表达文本、工具开始/结果、done/error，不携带 route diagnostics，见 `apps/studio/backend/app/models/copilot.py:63`。

## 编号执行流程(现状)

1. Graph Agent phase 准备 runtime；如果 resolver 缺失，`GatewayResolverMissingError` 表示 LLM phase 缺少解析器依赖，见 `llm_phase_node.py:133` 和 `llm_phase_node.py:137`。
2. Phase 调用 `ModelResolverProtocol.resolve()`，期望拿到 `BaseChatModel`，见 `protocol.py:28` 和 `llm_phase_node.py:173`。
3. 当前 `ModelResolver.resolve()` 调 `registry.resolve_role()` 得到 `ResolvedRole`，见 `resolver.py:92`。
4. `registry.resolve_role()` 遍历 role 的 `fallback_chain` 或 override route，逐条 join route、endpoint、credential、profile 和 runtime settings，见 `registry/resolver.py:45`、`registry/resolver.py:55`、`registry/resolver.py:77`。
5. `ModelResolver.resolve()` 把 `ResolvedRole` 塞进 `GatewayChatModel`，而不是返回 route，见 `resolver.py:135`。
6. LangChain/agent loop 真正调用模型时，`GatewayChatModel._generate()` 才消费 `resolved_role.routes`，见 `gateway_chat_model.py:111`。
7. Copilot 另走 Studio service：`_resolve_copilot_runtime()` 直接调用 registry `resolve_role()` 取 `ResolvedRoute` 列表，再把每条 route 变成 Claude Agent SDK 的 env/base_url/session，见 `copilot.py:419`、`copilot.py:429`、`copilot.py:449`。

## baseline/alignment 差异

baseline 当前事实：route 已存在于 `ResolvedRole.routes`，但不是 Gateway 公共 `resolve()` 的一等输出；Graph Agent 只看 `BaseChatModel`，Copilot service 自己绕到 registry resolver 取 route。

MVP1 目标差异：route 应成为编排和调用之间唯一交接物；Graph Agent 调用层和 Copilot 调用层都应从同一个 handoff API 取得 `ResolvedRoute/ResolvedRole`，而不是一个拿 model、一个手写 `_resolve_copilot_runtime()`。**判据标注:「route 级直调 public API」按 D3 + 判据已定为 ③b 公共能力(本轮反转,从「形状待主控确认」升为「已定 ③b 新增要求」,只剩签名取舍);两级接口(role 级已有 / route 级待补)详见 `mvp1-alignment.md` §1/§3/§5。**

## 决策原因

1. 保留 `GatewayChatModel`(用途:把 `ResolvedRole` 包成 LangChain chat model 并在内部跑 fallback/熔断/probe/usage 的编排外壳)作为编排外壳，不裸返回 ChatX。来源:client 层 A' 重设计决策(完整逻辑 + PM 原话见同目录 `mvp1-alignment.md` §4/§5 留底）。A' 否决了「resolver 直接产 ChatX + 删 `GatewayChatModel`」的激进版,理由是 fallback、probe、熔断、usage、metadata 这些编排职责全在 `_generate`(用途:`GatewayChatModel` 的 fallback 执行循环,逐条遍历 routes 做熔断跳过/probe/dispatch/usage/event)里;裸返回 ChatX 会把这些能力全丢掉。
2. route 作为唯一交接物，是因为 Copilot 用 `claude_agent_sdk`(用途:Claude Agent 独立运行时 SDK,Copilot 自己拿它调模型,不经 gateway 调用层)自己调用，Gateway 只应输出编排结果;这条出自 client 层 A' 重设计「编排 / 调用分离」决策——编排只负责「该用哪条 route」,把解析好的 route 交回调用方,调用方自己调(完整逻辑 + PM 原话「编排输入什么输出什么、调用输入什么输出什么」见 `mvp1-alignment.md` §4/§5 留底,另见 [[02-orch-role-resolution]] 解析产出 route、[[09-inv-invocation-runtime]] 调用层消费 route)。
3. MVP0 旧 `ResolvedProvider/call_chain` 叙述不可照抄，因为当前源码已切到 registry `ResolvedRoute/ResolvedRole`，见 `docs/graph-agent-gateway/mvp0/baseline.md:8` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415`。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:ModelResolverProtocol`：Engine resolver 协议，当前返回 `BaseChatModel`。
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:ModelResolver.resolve`：把 registry `ResolvedRole` 包装成 `GatewayChatModel` 或 `PredictGatewayChatModel`。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:resolve_role`：把 role/override 解析成有序 `ResolvedRoute` 列表。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRoute`：单条可执行 route 数据契约。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRole`：role 解析后的 metadata + routes 契约。
- `packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py`：Gateway 公共导出边界。
- `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:LlmPhaseNode._resolved_tracing_model`：Graph Agent 消费 resolver 的入口。
- `apps/studio/backend/app/services/copilot.py:stream_query`：Copilot WebSocket 查询入口，当前自己取 route 并调用 SDK。
- `apps/studio/backend/app/models/copilot.py:CopilotEvent`：Copilot WebSocket 输出事件联合类型。

## 待办/疑点

1. 已核实 Copilot WS 事件模型实际路径为 `apps/studio/backend/app/models/copilot.py`,manifest 已同步修正;后续若新增 gateway-side Copilot DTO,需另开模块登记。
2. `ModelResolverProtocol.resolve()` 仍返回 `BaseChatModel`，MVP1 若要 route 成为一等输出，需要新增或调整协议；本任务只记录，不改代码。**判据更新:route 级直调 public API 的归属已定 ③b 公共(非疑点),仅 API 签名形状待主控拍板;见 `mvp1-alignment.md` §8。**
3. `model_override` 在协议名上像 model code，但 registry resolver 里作为 `route_override` 使用，见 `protocol.py:33` 和 `registry/resolver.py:37`；实现阶段需要做 API 命名决策,决定是否迁移为 `route_override`。
4. `CopilotEvent` 当前不带 route diagnostics；MVP1 是否要把 route_id/endpoint_id 暴露到 WS 事件，需要产品判断。
