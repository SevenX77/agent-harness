---
module: 09-inv-invocation-runtime
doc: baseline
status: drafted
verified_at: 2026-06-02
---

# 09-inv-invocation-runtime — Baseline(现状)

> **Tier**：③b gateway 公共能力（纯调用运行时，已在 `packages/graph-agent-gateway` 包内，无判据反转；归属表判 09=纯 ③b，见 `module-disposition-revised.md:42,84`）。本文只描述当前源码；MVP1 目标见同目录 `mvp1-alignment.md`。

本篇只写调用步骤：消息转换、调用桥接、按 protocol 调 SDK、输出解析、截断升级重试、`_build_chat_result`。fallback 遍历、probe、熔断、mark_down、fallback event 和 usage 归属在 [07-orch-fallback-circuit-probe/baseline.md](../07-orch-fallback-circuit-probe/baseline.md) 写。

## 覆盖代码(含覆盖率)

覆盖率：本模块 brief 指定的调用层代码已全部核源码，文档覆盖率 100%。共享文件按 [mvp1 README](../README.md:38) 的边界切分：09 覆盖 `gateway_chat_model.py` 的调用桥接和 `client_manager.py` 的 `_call_*`，不重复 07 的 fallback/probe 编排。

| 代码 | 本篇覆盖的用途 |
|---|---|
| `_langchain_messages_to_dict` 是当前把 LangChain `BaseMessage` 转成 provider dict 的消息转换函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:661-692`。 |
| `_apply_system_prompt_prefix` 是当前把 role system prompt prefix 合并进 dict 消息列表的函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:695-707`。 |
| `_dispatch` 是 `GatewayChatModel._generate` 到 `LLMClientManager.dispatch_provider_call` 的调用桥接函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:474-495`。 |
| `GatewayChatModel._build_chat_result` 是把 client manager 的 dict response 包装成 LangChain `ChatResult` 的函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:313-357`。 |
| `_additional_kwargs_from_response` 是把旧 dict response 里的 tool calls / reasoning content 放进 `AIMessage.additional_kwargs` 的函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:649-658`。 |
| `_coerce_text` 是把任意 content 强制转字符串的函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:645-646`。 |
| `LLMClientManager.dispatch_provider_call` 是当前对外的一条 route 调用入口，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:78-121`。 |
| `LLMClientManager._dispatch_provider_call` 是按 `ResolvedRoute.protocol` 选择具体 `_call_*` 的内部路由函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:865-988`。 |
| `LLMClientManager._call_openai_compatible` 是 OpenAI-compatible Chat Completions 调用和响应解析函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-504`。 |
| `LLMClientManager._call_openai_responses` 是 OpenAI Responses API 调用和响应解析函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:506-547`。 |
| `LLMClientManager._call_google_genai` 是 Google GenAI `generate_content` 调用和响应解析函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:549-611`。 |
| `LLMClientManager._call_ark_runtime` 是 Volcengine Ark official SDK chat completions 调用和响应解析函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:613-670`。 |
| `LLMClientManager._call_anthropic_compatible` 是 Anthropic-compatible Messages API 调用和响应解析函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:672-769`。 |
| `LLMClientManager._call_wavespeed_any_llm` 是 WaveSpeed Any-LLM HTTP 调用和响应解析函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:771-863`。 |
| `LLMClientManager._call_with_token_escalation` 是截断 finish reason 后扩大 token budget 重试的函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:990-1012`。 |
| `models.py` 是 Gateway 预留的 provider SDK wrapper 边界；当前没有导出真实 wrapper，见 `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9`。 |

## 编号执行流程

1. `GatewayChatModel._generate` 先调用 `_langchain_messages_to_dict`，把 `SystemMessage`、`HumanMessage`、`AIMessage` 和 `ToolMessage` 映射成 `role/content/tool_call_id/tool_calls` 等 dict 字段，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:104-107` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:661-692`。

2. `_langchain_messages_to_dict` 对 `LangChainAIMessage.tool_calls` 会重建 OpenAI-shaped `tool_calls`，但 arguments 固定写成 `"{}"`；这说明当前转换会丢失 LangChain tool call 的部分原始结构，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:676-687`。

3. `_apply_system_prompt_prefix` 在已有 system 消息时合并 content，没有 system 消息时插入新的 system dict；这一步仍在 dict 世界里操作，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:695-707`。

4. `GatewayChatModel._generate` 在通过 07 的 probe/熔断编排后调用 `_dispatch`；`_dispatch` 会根据 manager 是否支持 `credential_provider` 参数决定是否透传凭证读取器，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:190-226` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:474-495`。

5. `LLMClientManager.dispatch_provider_call` 对外接收一条 `ResolvedRoute`、dict messages、runtime params、tool params 和 credential provider，然后委托 `_dispatch_provider_call`，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:78-121`。

6. `LLMClientManager._dispatch_provider_call` 定义局部 `invoke(token_budget)`，再按 `route.protocol` 分派到 OpenAI-compatible、Anthropic-compatible、Google GenAI 或 Ark runtime；未知 protocol 抛 `ValueError`，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:890-981`。

7. `LLMClientManager._get_openai_client` 是 OpenAI-compatible SDK client 工厂；它用 route 的 base_url、timeout、trust_env 和 credential 创建 `OpenAI` client，并显式 `max_retries=0`，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-184`。

8. `LLMClientManager._get_anthropic_client` 是 Anthropic-compatible SDK client 工厂；它用 route 的 base_url、timeout 和 credential 创建 `Anthropic` client，并显式 `max_retries=0`，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:186-216`。

9. `LLMClientManager._call_openai_compatible` 手写 Chat Completions kwargs，包括 `max_tokens`、temperature、top_p、stop、seed、parallel tool calls、reasoning effort、response format 和 tools，然后从 response 里解析 content、usage、finish reason 和 tool calls，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-504`。

10. `LLMClientManager._call_openai_responses` 手写 Responses API kwargs，把 messages 放到 `input`，把 token cap 写成 `max_output_tokens`，再解析 input/output tokens 和 `output_text`，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:506-547`。

11. `LLMClientManager._call_google_genai` 先用 `_google_contents` 把 dict messages 转成 Gemini contents，再拼 generation config、structured output 和 thinking config，最后从 `usage_metadata` 和 candidates 解析文本与 usage，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:549-611` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:1083-1101`。

12. `LLMClientManager._call_ark_runtime` 手写 Ark official SDK chat completions kwargs，再按 OpenAI-shaped response 解析 usage、choice、message 和 finish reason，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:613-670`。

13. `LLMClientManager._call_anthropic_compatible` 先用 `_split_anthropic_messages` 拆 system 和 messages，再处理 tools、tool choice、thinking/adaptive/manual thinking，最后只抽取 text blocks 和 tool_use blocks，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:672-769` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:1151-1163`。

14. `_anthropic_content_text` 只拼接 Anthropic content blocks 中 `type == "text"` 的文本；thinking/reasoning blocks 不会作为结构化 content 保留下来，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:1296-1304`。

15. `LLMClientManager._call_wavespeed_any_llm` 是独立 HTTP path；它把多轮 messages 拍成 prompt string，自己做 502/503/504 backoff retry，再解析 WaveSpeed task output，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:771-863`。

16. `LLMClientManager._call_with_token_escalation` 包住每次 provider invoke；如果 finish reason 是截断类型，就把 token budget 翻倍直到 capability cap 或轮数耗尽，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:990-1012`。

17. `GatewayChatModel._build_chat_result` 从 dict response 里取 usage、finish reason、content、additional kwargs，再构造 `AIMessage`、`ChatGeneration`、`ChatResult.llm_output`，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:313-357`。

18. `GatewayChatModel._build_chat_result` 当前用 `_coerce_text` 把 response content 转成字符串；这会把非字符串 content blocks 拍平，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:320-323` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:645-646`。

19. `GatewayChatModel._build_chat_result` 当前把 route_id、endpoint_id、provider model、canonical_id、protocol、finish_reason、usage 和 effective runtime settings 注入 `AIMessage.response_metadata`，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:323-332`。

20. `models.py` 当前只是声明 provider SDK wrapper 的包内边界，没有实际 wrapper class/function，也没有导出内容，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9`。

## Baseline / Alignment 差异

| 主题 | baseline 现状 | MVP1 方向 |
|---|---|---|
| 调用方式 | `LLMClientManager._call_*` 手写每个 provider 的请求 payload 和响应解析，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-988`。 | 改成原生 LangChain ChatX invoke；ChatX 负责消息转换、调用和输出解析。决策依据见同目录 `mvp1-alignment.md` §4/§5（client 层 A' 重设计决策：M2 把 client_manager 5 件事拆开，只退役"消息转换 + provider 调用"，换 ChatX）。 |
| 消息形状 | `_langchain_messages_to_dict` 把 LangChain message 拍成 dict，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:661-692`。 | 原始 `BaseMessage` 交给 ChatX，system prefix 以 LangChain message 方式插入或合并。决策依据见同目录 `mvp1-alignment.md` §4/§5（A' 调用层只改 `_generate` 第 1/5/7 步，把消息准备从拍 dict 换成原始 `BaseMessage` 交 ChatX）。 |
| thinking content | `_anthropic_content_text` 和 `_coerce_text` 都会把输出收敛成字符串，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:1296-1304` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:645-646`。 | 保留 ChatX 的 content blocks，不用旧 `_coerce_text` 拍平。决策依据见同目录 `mvp1-alignment.md` §4/§5（F4 thinking blocks 不拍平）。 |
| usage | 旧 dict response 带 `"usage"`，`_build_chat_result` 把它写入 metadata 和 llm_output，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:318-356`。 | 从 ChatX `AIMessage.usage_metadata` 取 usage，再注入 route metadata。决策依据见同目录 `mvp1-alignment.md` §4/§5（F5 usage/metadata：从 `usage_metadata` 取 token 喂观测，route metadata augment 进 `AIMessage`）。 |
| 截断升级 | `_call_with_token_escalation` 在 client manager 内部，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:990-1012`。 | 保留策略但搬到 07 编排层，09 不再把它当 provider SDK wrapper 的一部分。 |
| SDK wrapper 边界 | `models.py` 是空边界，真实 wrapper 逻辑散在 `client_manager.py`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9`。 | 新的 route → ChatX 工厂和 provider profile 在 10/11 写，09 只写运行时 invoke 和结果桥接。 |

## 决策原因

当前自研调用层的问题不是“不能调用”，而是它重复实现了 LangChain ChatX 已经稳定处理的消息转换、provider payload 和响应解析；client 层 A' 重设计决策把这部分拆成“消息转换 → ChatX 取代、provider 调用/解析 → ChatX 取代、截断升级 → 保留搬家”（M2 拆解，完整逻辑见同目录 `mvp1-alignment.md` §5 决策 2 + §2 第 5/6 步）。

保留 `GatewayChatModel._build_chat_result` 的原因是 route metadata 仍要贴回 LangChain 结果；但它的输入不应再是旧 dict response，而应是 ChatX 返回的 `AIMessage`（F5 usage/metadata，完整逻辑见同目录 `mvp1-alignment.md` §4 / §5 决策 4）。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:104-107`：旧调用层输入准备入口。
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:474-495`：`_dispatch` 调用桥接。
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:313-357`：`_build_chat_result` 结果桥接。
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:661-707`：LangChain messages 到 dict 的转换和 system prefix 合并。
- `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-988`：旧 `_call_*` 和 protocol dispatch。
- `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:990-1012`：截断升级重试。
- `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9`：当前空的 provider wrapper 边界。

## 待办/疑点

1. `_langchain_messages_to_dict` 当前把 `AIMessage.tool_calls[*].args` 简化成 `"{}"`；迁移 ChatX 后应以回归测试覆盖多轮 tool loop，证据见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:676-687`。

2. `_anthropic_content_text` 只保留 text blocks；MVP1 若要保留 thinking/reasoning blocks，需要让 ChatX `AIMessage.content` 原样穿过结果桥接，证据见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:1296-1304`。

3. WaveSpeed Any-LLM 是旧调用层里独立 HTTP path，不属于标准 ChatX provider；MVP1 是否继续支持该 route 需要在 10/11 的 factory/profile 设计里单独定，证据见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:771-863`。
