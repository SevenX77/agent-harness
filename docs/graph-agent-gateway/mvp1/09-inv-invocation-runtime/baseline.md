---
module: 09-inv-invocation-runtime
doc: baseline
status: drafted
verified_at: 2026-06-06
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel/_generate/_dispatch/_invoke_with_token_escalation/_build_chat_result/_build_chat_result_from_ai_message/_usage_from_ai_message/_apply_system_prompt_prefix · packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py:RouteChatModelFactory/build · packages/graph-agent-gateway/src/graph_agent_gateway/ordinary_chat.py:dispatch_ordinary_chat/_dispatch_provider_call/_call_openai_compatible/_call_openai_responses/_call_google_genai/_call_ark_runtime/_call_anthropic_compatible/_call_wavespeed_any_llm/_call_with_token_escalation · packages/graph-agent-gateway/src/graph_agent_gateway/models.py:GenericRouteChatModel · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRoute
units: [chatx-invocation-runtime]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 09-inv-invocation-runtime — Baseline(现状)

> **Tier**：③b gateway 公共能力（纯调用运行时，已在 `packages/graph-agent-gateway` 包内，无判据反转；归属表判 09=纯 ③b，见 `module-disposition-revised.md:52`）。本文描述 **WS-1 后真实源码**；MVP1 目标见同目录 `mvp1-alignment.md`。

本篇只写调用步骤：LangChain message 准备、ChatX 工厂桥接、官方 ChatX invoke、输出解析、截断升级重试、`_build_chat_result`。fallback 遍历、probe、熔断、mark_down、fallback event 和 usage 归属在 [07-orch-fallback-circuit-probe/baseline.md](../07-orch-fallback-circuit-probe/baseline.md) 写。

## 覆盖代码(含覆盖率)

覆盖率：本模块 brief 指定的调用层代码已全部核源码，文档覆盖率 100%。共享文件按 [mvp1 README](../README.md) 第 66 行的边界切分：09 覆盖 `gateway_chat_model.py` 的 ChatX invoke 桥、结果桥和 token escalation；generic ordinary-chat provider core 已从 `client_manager.py` 收编到 `ordinary_chat.py`，仍不是官方 ChatX 生产主调用路径。

| 代码 | 本篇覆盖的用途 |
|---|---|
| `GatewayChatModel._generate` | 保留 07 的 fallback/probe/熔断/异常分类外壳，并把原始 LangChain `BaseMessage` 交给调用桥。 |
| `_apply_system_prompt_prefix` | 用 LangChain `SystemMessage` 方式插入或合并 system prompt prefix，不再把消息先拍成 provider dict。 |
| `_dispatch` | 当前生产调用桥：创建 `RouteChatModelFactory`，再调用 `_invoke_with_token_escalation`；`client_manager` 参数在这里不再参与 provider 调用。 |
| `_invoke_with_token_escalation` | 包住 ChatX `invoke`，当 `finish_reason/stop_reason` 是截断形状时提高 token budget 重试。 |
| `_build_chat_result_from_ai_message` | ChatX 主路径结果桥：保留 `AIMessage.content` / `additional_kwargs`，合并 route metadata，并从 `usage_metadata` 归一 token usage。 |
| `_build_chat_result` 的 dict 分支 | 旧 dict response 兼容桥仍存在，服务历史测试/legacy helper，不是 WS-1 主调用路径。 |
| `PatchedChatDeepSeek` | DeepSeek OpenAI-compatible/Ark route 的 ChatX 子类；只覆盖 `_get_request_payload`，把多轮 assistant `reasoning_content` replay 回 provider payload。 |
| `ordinary_chat.dispatch_ordinary_chat/_dispatch_provider_call/_call_*` | generic ordinary-chat provider core；官方 ChatX 主路径不直接调用，`GenericRouteChatModel` 默认 dispatcher 使用它；完整非标协议支持仍 deferred。 |
| `GenericRouteChatModel` | 已实现最小 ordinary-chat adapter：`bind_tools()`、LangChain `BaseMessage` → OpenAI-style dict 序列化、ordinary dispatcher 调用、dict response → `AIMessage` 桥接。 |

## 编号执行流程

1. `GatewayChatModel._generate` 先调用 `_apply_system_prompt_prefix`，在 LangChain message 层合并/插入 system prompt prefix。

2. fallback loop、probe、provider-down cache、fallback event、异常分类仍留在 `GatewayChatModel._generate` 中；这部分归 07 管。

3. 每条候选 route 调用 `_dispatch`；`_dispatch` 不再转 dict、不再调用 `LLMClientManager.dispatch_provider_call`，而是构造 `RouteChatModelFactory(credential_provider=...)`。

4. `RouteChatModelFactory.build` 按 `ResolvedRoute.protocol` 构造官方 ChatX：`ChatOpenAI`、`ChatAnthropic`、lazy `ChatGoogleGenerativeAI`，或 unknown protocol 的 `GenericRouteChatModel` ordinary-chat adapter。

5. `_invoke_with_token_escalation` 每轮把当前 `max_tokens` 传给 factory；若 route 绑定 tools 且 ChatX 支持 `bind_tools`，先绑定 tools 再 `invoke(messages)`。

6. ChatX 返回 `AIMessage` 后，`_build_chat_result_from_ai_message` 保留原 content/kwargs，补 route metadata、finish reason、effective runtime settings，并从 `usage_metadata` 取 token usage。

7. 如果 manager 侧没有记录 usage，`GatewayChatModel._generate` 会用 `_usage_from_response` 把 ChatX usage 回写到 `LLMClientManager.record_usage`。

8. 旧 `LLMClientManager.dispatch_provider_call/_dispatch_provider_call/_call_*` 已从 `client_manager.py` 删除；generic ordinary adapter 的默认 dispatcher 改为 `ordinary_chat.dispatch_ordinary_chat`。官方 ChatX 主路径仍只走 factory + ChatX invoke。

## Baseline / Alignment 差异

| 主题 | baseline 现状 | MVP1 方向 |
|---|---|---|
| 调用方式 | 生产主路径已改成 `RouteChatModelFactory` + 官方 ChatX `invoke`；generic 分支已有最小 ordinary-chat adapter。 | 与 alignment §3.5/§5 主目标一致；streaming、multimodal、provider-specific error normalization 仍 deferred。 |
| 消息形状 | 主路径把原始 `BaseMessage` 交给 ChatX；旧 `_langchain_messages_to_dict` 不再是主调用入口。 | 继续保留 ChatX 负责消息转换。 |
| thinking content | ChatX `AIMessage` 的 content/kwargs 不被 dict 桥拍平；DeepSeek route 的 `_get_request_payload` 已 replay 多轮 assistant `reasoning_content`。 | 其它 provider thinking 默认和 provider-specific payload 差异仍按独立测试推进。 |
| usage | 主路径从 `AIMessage.usage_metadata` 归一 usage，再注入 route metadata。 | 与 F5 对齐。 |
| 截断升级 | `_invoke_with_token_escalation` 已迁到 gateway ChatX 调用桥；generic ordinary path 的 token escalation 在 `ordinary_chat._call_with_token_escalation` 内，不再挂在 `LLMClientManager`。 | ChatX 主路径和 generic ordinary path 边界已拆开；generic 的完整非标协议支持仍 deferred。 |
| generic | `GenericRouteChatModel` 已能作为 `BaseChatModel` 经 `create_agent` 跑通工具循环；序列化保留空 content assistant tool-call、JSON string arguments 和 `ToolMessage.tool_call_id`。 | 完整非标 provider 支持、streaming、multimodal、provider-specific error normalization 仍 deferred。 |

## 决策原因

当前主路径已按 client 层 A' 重设计决策，把“消息转换 + provider 调用/解析”交给 LangChain ChatX；gateway 只保留 route fallback、probe、异常分类、usage/metadata augment 和 token escalation 这些编排责任。

保留 `GatewayChatModel._build_chat_result` 的原因是 route metadata 仍要贴回 LangChain 结果；WS-1 后它的主输入是 ChatX 返回的 `AIMessage`，dict 分支只是历史兼容。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`：`GatewayChatModel._generate`、`_dispatch`、`_invoke_with_token_escalation`、`_build_chat_result_from_ai_message`。
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py`：`RouteChatModelFactory.build`、DeepSeek `PatchedChatDeepSeek._get_request_payload` 单方法 patch。
- `packages/graph-agent-gateway/src/graph_agent_gateway/ordinary_chat.py`：`dispatch_ordinary_chat/_dispatch_provider_call/_call_*`，从 `client_manager.py` 收编出的 generic ordinary-chat provider core。
- `packages/graph-agent-gateway/src/graph_agent_gateway/models.py`：`GenericRouteChatModel` 最小 ordinary-chat adapter。

## 待办/疑点

1. `GenericRouteChatModel` 已完成 OpenAI-style ordinary-chat 最小 adapter；streaming、multimodal、provider-specific error normalization 和完整非标 protocol dispatcher 支持仍未覆盖，不宣称 production 完整。

2. `LLMClientManager.dispatch_provider_call/_dispatch_provider_call/_call_*` 已清理；行为收编到 `ordinary_chat.py`，测试已覆盖 `client_manager` 不再暴露旧 helper 与 `GenericRouteChatModel` 默认 dispatcher 的新落点。

3. thinking 归一化只完成了 ChatX `AIMessage` 不拍平、部分 runtime kwargs 映射和 DeepSeek 单方法 payload replay；其它 provider thinking defaults / 旧 thinking helper 清理仍延期。
