---
module: graph-agent-gateway-mvp1
doc: evidence-reference
status: drafted
workflow_axis: N/A（gateway MVP1 是库/公共能力模块,无独立用户旅程 workflow 文档）
binds_design: ../README.md · ../DESIGN_UNITS_INDEX.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py · packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py
units: [route-chat-model-factory, provider-profiles-init-kwargs, chatx-invocation-runtime, credentials-endpoints-canonicalization]
aligns_with: ../README.md（10/11 调用层 scope） · ../10-inv-route-chat-model-factory/mvp1-alignment.md · ../11-inv-provider-profiles/mvp1-alignment.md
---

# ChatX / Provider Profile 参考模式归档

> 本文把本轮临时 spike 和外部范本里已经用于设计的稳定结论归档到 MVP1 正式目录。能力模块可引用本文,不得再把临时目录路径当作正式 SSOT。

## 1. Provider Profile 机制

- `ProviderProfile` 是 provider 或 provider:model 到 ChatX init kwargs 的声明式表。
- 注册支持 provider 级默认和 exact model 覆盖;重复注册应 additive 合并。
- 查找顺序是 exact model 优先,再叠 provider default。
- 应用顺序是 `pre_init` → 静态 `init_kwargs` → 动态 factory 输出 → caller kwargs,其中 caller kwargs 最高优先级。
- gateway 只能借鉴 lookup / merge / pre_init / factory 模式,不能照搬字符串 `provider:model` 输入接口;gateway key 必须从 `ResolvedRoute` 维度派生。

## 2. ChatX 构造期差异

- provider 差异优先收束为 init kwargs,例如 headers、Responses API、base_url 参数名、温度默认、thinking 开关、`stream_usage`。
- OpenAI-compatible ChatX 对 streaming usage 需要显式开关时,由 provider profile 或工厂补默认值。
- thinking / reasoning 的预算、adaptive/manual 约束仍归 capability/lint 层保护;provider profile 只承载构造期开关和默认值。

## 3. Payload Patch 边界

- 只有请求 payload 必须改时,才允许子类覆盖单方法。
- 单方法 patch 不能重新实现整套消息转换、调用和解析。
- DeepSeek reasoning content 多轮保留已按此类边界落地:只覆盖 `_get_request_payload`,用本地 helper 按 assistant message 顺序 replay `reasoning_content`,不重写整套消息转换。

## 4. GenericRouteChatModel 兜底

- 官方 ChatX 优先;没有官方 ChatX 的非标 route 才进入 `GenericRouteChatModel`。
- `GenericRouteChatModel` 仍必须是 LangChain `BaseChatModel` 子类,让 engine 消费面保持一致。
- 通用适配器必须保留 tool call 上下文:不能丢空 content 的 assistant tool-call message,OpenAI tool arguments 必须是 JSON 字符串,`ToolMessage.tool_call_id` 必须与上一轮对齐,Anthropic tool call/result 需按 content block 语义序列化。
- streaming、multimodal、error normalization 尚未由归档证据覆盖,不得宣称 production 完成。

## 5. WaveSpeed / Base URL 结论

- WaveSpeed 同一 endpoint 可表现为 OpenAI-compatible 和 Anthropic Messages 两种调用面,官方 ChatX 可覆盖 native-compatible 路径。
- Anthropic-compatible SDK 会自行拼接 `/v1/messages`;若保存的 base_url 已带 `/v1`,runtime 会形成重复路径并 404。
- 因此 base_url canonical 规则必须按 protocol 固定:保存时 canonical 是主路径,调用时 no-op normalize 是历史数据双保险。
- Studio raw HTTP probe 与 SDK runtime 可能路径语义不同;状态设计必须避免“probe 通过但 SDK runtime 失败”的假阳性。

## 6. Live Smoke 证据边界

- 本轮 live smoke 只证明 ChatX / generic adapter 方向可行,不是 CI 闸。
- 正式实现前仍需确定性单测覆盖:retry 耗尽后的异常分类、tool loop 多轮消息、base_url canonical、usage metadata、payload patch 单方法边界。
