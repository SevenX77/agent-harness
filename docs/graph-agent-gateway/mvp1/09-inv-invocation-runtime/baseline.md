---
module: 09-inv-invocation-runtime
doc: baseline
status: drafted
verified_at: 2026-06-06
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel/_generate/_dispatch/_invoke_with_token_escalation/_build_chat_result/_build_chat_result_from_ai_message/_usage_from_ai_message/_apply_system_prompt_prefix · packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py:RouteChatModelFactory/build · packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:LLMClientManager/dispatch_provider_call/_dispatch_provider_call/_call_openai_compatible/_call_openai_responses/_call_google_genai/_call_ark_runtime/_call_anthropic_compatible/_call_wavespeed_any_llm/_call_with_token_escalation · packages/graph-agent-gateway/src/graph_agent_gateway/models.py:GenericRouteChatModel · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRoute
units: [chatx-invocation-runtime]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 09-inv-invocation-runtime — Baseline(现状)

> **Tier**：③b gateway 公共能力（纯调用运行时，已在 `packages/graph-agent-gateway` 包内，无判据反转；归属表判 09=纯 ③b，见 `module-disposition-revised.md:52`）。本文描述 **WS-1 后真实源码**；MVP1 目标见同目录 `mvp1-alignment.md`。

本篇只写调用步骤：LangChain message 准备、ChatX 工厂桥接、官方 ChatX invoke、输出解析、截断升级重试、`_build_chat_result`。fallback 遍历、probe、熔断、mark_down、fallback event 和 usage 归属在 [07-orch-fallback-circuit-probe/baseline.md](../07-orch-fallback-circuit-probe/baseline.md) 写。

## 覆盖代码(含覆盖率)

覆盖率：本模块 brief 指定的调用层代码已全部核源码，文档覆盖率 100%。共享文件按 [mvp1 README](../README.md) 第 66 行的边界切分：09 覆盖 `gateway_chat_model.py` 的 ChatX invoke 桥、结果桥和 token escalation；`client_manager.py` 的 `_call_*` 现在是 legacy/generic 候选内核，不再是生产主调用路径。

| 代码 | 本篇覆盖的用途 |
|---|---|
| `GatewayChatModel._generate` | 保留 07 的 fallback/probe/熔断/异常分类外壳，并把原始 LangChain `BaseMessage` 交给调用桥。 |
| `_apply_system_prompt_prefix` | 用 LangChain `SystemMessage` 方式插入或合并 system prompt prefix，不再把消息先拍成 provider dict。 |
| `_dispatch` | 当前生产调用桥：创建 `RouteChatModelFactory`，再调用 `_invoke_with_token_escalation`；`client_manager` 参数在这里不再参与 provider 调用。 |
| `_invoke_with_token_escalation` | 包住 ChatX `invoke`，当 `finish_reason/stop_reason` 是截断形状时提高 token budget 重试。 |
| `_build_chat_result_from_ai_message` | ChatX 主路径结果桥：保留 `AIMessage.content` / `additional_kwargs`，合并 route metadata，并从 `usage_metadata` 归一 token usage。 |
| `_build_chat_result` 的 dict 分支 | 旧 dict response 兼容桥仍存在，服务历史测试/legacy helper，不是 WS-1 主调用路径。 |
| `LLMClientManager.dispatch_provider_call/_dispatch_provider_call/_call_*` | 无生产活调用方；源码已标注为 legacy ordinary-chat helper，后续要么迁入 `GenericRouteChatModel` 普通 chat 内核，要么删除。 |
| `GenericRouteChatModel` | 未实现普通 chat 内核，当前 fail-loud 抛 `NotImplementedError`，避免静默返回空内容。 |

## 编号执行流程

1. `GatewayChatModel._generate` 先调用 `_apply_system_prompt_prefix`，在 LangChain message 层合并/插入 system prompt prefix。

2. fallback loop、probe、provider-down cache、fallback event、异常分类仍留在 `GatewayChatModel._generate` 中；这部分归 07 管。

3. 每条候选 route 调用 `_dispatch`；`_dispatch` 不再转 dict、不再调用 `LLMClientManager.dispatch_provider_call`，而是构造 `RouteChatModelFactory(credential_provider=...)`。

4. `RouteChatModelFactory.build` 按 `ResolvedRoute.protocol` 构造官方 ChatX：`ChatOpenAI`、`ChatAnthropic`、lazy `ChatGoogleGenerativeAI`，或 unknown protocol 的 `GenericRouteChatModel` fail-loud 外壳。

5. `_invoke_with_token_escalation` 每轮把当前 `max_tokens` 传给 factory；若 route 绑定 tools 且 ChatX 支持 `bind_tools`，先绑定 tools 再 `invoke(messages)`。

6. ChatX 返回 `AIMessage` 后，`_build_chat_result_from_ai_message` 保留原 content/kwargs，补 route metadata、finish reason、effective runtime settings，并从 `usage_metadata` 取 token usage。

7. 如果 manager 侧没有记录 usage，`GatewayChatModel._generate` 会用 `_usage_from_response` 把 ChatX usage 回写到 `LLMClientManager.record_usage`。

8. 旧 `LLMClientManager.dispatch_provider_call/_dispatch_provider_call/_call_*` 仍在文件内，但没有生产活调用方；这是有标记的 deferred，不是当前主路径。

## Baseline / Alignment 差异

| 主题 | baseline 现状 | MVP1 方向 |
|---|---|---|
| 调用方式 | 生产主路径已改成 `RouteChatModelFactory` + 官方 ChatX `invoke`。 | 与 alignment §3.5/§5 主目标一致；generic 普通 chat 内核仍延期。 |
| 消息形状 | 主路径把原始 `BaseMessage` 交给 ChatX；旧 `_langchain_messages_to_dict` 不再是主调用入口。 | 继续保留 ChatX 负责消息转换。 |
| thinking content | ChatX `AIMessage` 的 content/kwargs 不被 dict 桥拍平；但 provider profile 对 thinking 的声明式归一仍未完整 seeded。 | thinking 默认、DeepSeek reasoning-content patch 和 provider-specific payload 差异记入 deferred。 |
| usage | 主路径从 `AIMessage.usage_metadata` 归一 usage，再注入 route metadata。 | 与 F5 对齐。 |
| 截断升级 | `_invoke_with_token_escalation` 已迁到 gateway ChatX 调用桥；client_manager 旧 `_call_with_token_escalation` 仅 legacy。 | 后续清理旧 helper 或搬进 generic 普通 chat 内核。 |
| generic | `GenericRouteChatModel` 当前 fail-loud，不再静默返回空 `AIMessage`。 | 普通 chat 内核未实现，见 deferred。 |

## 决策原因

当前主路径已按 client 层 A' 重设计决策，把“消息转换 + provider 调用/解析”交给 LangChain ChatX；gateway 只保留 route fallback、probe、异常分类、usage/metadata augment 和 token escalation 这些编排责任。

保留 `GatewayChatModel._build_chat_result` 的原因是 route metadata 仍要贴回 LangChain 结果；WS-1 后它的主输入是 ChatX 返回的 `AIMessage`，dict 分支只是历史兼容。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`：`GatewayChatModel._generate`、`_dispatch`、`_invoke_with_token_escalation`、`_build_chat_result_from_ai_message`。
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py`：`RouteChatModelFactory.build`。
- `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py`：legacy `dispatch_provider_call/_dispatch_provider_call/_call_*`，源码注释已标出延期清理。
- `packages/graph-agent-gateway/src/graph_agent_gateway/models.py`：`GenericRouteChatModel` fail-loud shell。

## 待办/疑点

1. `GenericRouteChatModel` 的普通 chat 内核未实现；当前选择 fail-loud，避免未知 protocol 静默成功。

2. `LLMClientManager.dispatch_provider_call/_dispatch_provider_call/_call_*` 是无生产活调用方的 legacy helper；后续要删除或迁入 generic 普通 chat 内核。

3. thinking 归一化只完成了 ChatX `AIMessage` 不拍平和部分 runtime kwargs 映射；ProviderProfile defaults、DeepSeek 单方法 payload patch、旧 thinking helper 清理仍延期。
