---
module: 10-inv-route-chat-model-factory
doc: baseline
status: written
last_verified: 2026-06-02
---

# 10-inv-route-chat-model-factory - Baseline(现状)

> **Tier**：③b gateway 公共能力（**MVP1 新建**调用层核心；归属表判 10=纯 ③b 新建，见 `module-disposition-revised.md:43,84`）。**本模块现源码不存在**——下文诚实记录"没有 `RouteChatModelFactory` 源文件"这一现状，以及职责暂由 resolver 实例化 + client_manager SDK 工厂代管。MVP1 目标见同目录 `mvp1-alignment.md`。

## 覆盖代码(含覆盖率)

本模块当前没有独立生产模块。源码树里没有 `RouteChatModelFactory` 源文件；`packages/graph-agent-gateway/src/graph_agent_gateway/models.py` 也只是未来 provider wrapper 边界，当前 `__all__` 为空，说明它没有承载真实 ChatX 工厂逻辑(`packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9`)。

覆盖率:100%。这里覆盖的是 MVP1 manifest 指定的现状职责来源:resolver 实例化 `GatewayChatModel`、`GatewayChatModel._generate` 委派 `_dispatch`、`LLMClientManager` 自建 SDK client 与按 protocol 调用 provider(`docs/graph-agent-gateway/mvp1/README.md:38-40`)。

覆盖代码索引:

| 代码 | 覆盖原因 |
|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9` | 证明当前没有独立 provider wrapper / ChatX factory。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:73-146` | `ModelResolver.resolve` 把 role 解析结果包成 `GatewayChatModel` 或 predict mock；它不返回原生 ChatX。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-459` | `ResolvedRoute` 是一条运行期 route 候选，`ResolvedRole` 是带 fallback 顺序的 route 列表；这是未来工厂的输入数据形状。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:96-236` | `GatewayChatModel._generate` 同时做编排与真实调用委派；第 190-236 行是现状调用入口。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-295` | `LLMClientManager._get_openai_client/_get_anthropic_client/_get_google_client/_get_ark_client` 自建并缓存各 provider SDK client。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-1012` | `LLMClientManager._call_*` 与 `_dispatch_provider_call` 负责消息 payload、provider 调用、响应归一化和截断 token 升级。 |

## 编号执行流程(现状)

1. `ModelResolver.resolve` 负责把 Studio registry 的 role 解析成 LangChain 可消费模型；它先调用 `resolve_role` 得到纯数据 `ResolvedRole`，再读取首条 route 的 `max_output_tokens`、`temperature`、`reasoning.enabled`(`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:92-118`)。
2. `ResolvedRoute` 表示一条可执行 route，字段包括 `protocol`、`base_url`、`credential_ref`、`provider_model_id`、`call_method_id`、`request_mapper_id`、runtime settings 等；这些字段已经足够作为未来 ChatX 工厂输入(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`)。
3. `ResolvedRole` 表示一个 role 的有序 route 链；它携带 `system_prompt_prefix`、`runtime_policy`、`routes` 和 lint 结果，是编排层交给调用层的容器(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-459`)。
4. `ModelResolver.resolve` 当前正常分支直接返回 `GatewayChatModel`；`GatewayChatModel` 是 LangChain `BaseChatModel` 外壳，用来保留 fallback、probe、熔断、usage 和 metadata 编排行为(`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:135-146`；A' 决策保留此外壳的逻辑见同目录 `mvp1-alignment.md` §4 D1 / §5 决策 1)。
5. `GatewayChatModel._generate` 先把 LangChain `BaseMessage` 转成 dict，再把 system prompt prefix 合进去；`_langchain_messages_to_dict` 是旧消息转换入口，当前会把 `AIMessage` 和 tool calls 重新组装成 provider payload(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:104-107`; `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:661-692`)。
6. `GatewayChatModel._generate` 在 fallback loop 内调用 `_dispatch`；`_dispatch` 是现状“调用层”委派点，实际落到 `LLMClientManager.dispatch_provider_call`(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:190-226`)。
7. `LLMClientManager` 是共享 native SDK client 缓存和 provider call helper；它用 `_get_openai_client`、`_get_anthropic_client`、`_get_google_client`、`_get_ark_client` 分别创建 OpenAI、Anthropic、Google GenAI、Ark SDK client(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:40-47`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-295`)。
8. `LLMClientManager._dispatch_provider_call` 按 `route.protocol` 分支选择 `_call_openai_compatible`、`_call_openai_responses`、`_call_anthropic_compatible`、`_call_google_genai`、`_call_ark_runtime`；这些函数各自负责 provider 请求参数和响应解析(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:866-988`)。
9. `LLMClientManager._call_with_token_escalation` 在 provider 返回截断 finish reason 时提高 token budget 重试；它是现状真实调用路径的一部分，MVP1 不能随 `_call_*` 一起丢掉(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:990-1012`；F3 截断升级搬家逻辑见同目录 `mvp1-alignment.md` §5 决策 10)。

## Baseline / Alignment 差异

baseline 当前无 `RouteChatModelFactory`。`RouteChatModelFactory` 是拟新建的 route 到原生 ChatX 构造器，职责现在由两块代码临时代管:resolver 负责创建 `GatewayChatModel`，client_manager 负责 SDK client 工厂与 provider 调用(`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:135-146`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-295`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:866-988`)。

alignment 目标不是删除 `GatewayChatModel`。client 层 A' 重设计决策已否决“resolver 直接裸返回 ChatX”的方案（方案 A），要求保留 `GatewayChatModel` 做编排外壳，只把每条 route 的真实调用换成原生 LangChain ChatX(完整决策逻辑 + PM 原话见同目录 `mvp1-alignment.md` §4 D1 / §5 决策 1)。

## 决策原因

1. 需要拆开“编排”和“调用”（D2 编排/调用分离）。编排输入 = role/model override，输出 = `ResolvedRoute` 链；调用层输入是一条 `ResolvedRoute` 加 messages，输出是 `AIMessage`/结果(完整逻辑 + PM 原话见同目录 `mvp1-alignment.md` §4 D2 / §5 决策 1)。
2. 现状把调用揉在 fallback loop 里。`GatewayChatModel._generate` 在同一个函数里做 probe、熔断、调用、usage、metadata、异常分类，导致 ChatX 替换很难只改调用层(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:111-271`；M3 `_generate` 逐步归属（哪步留编排、哪步换调用）留底于 [[09-inv-invocation-runtime]] §5)。
3. 旧 client_manager 调用层问题集中在消息转换和 provider payload。`_langchain_messages_to_dict` 会把带 tool calls 的空内容 `AIMessage` 转成空 content dict，这是这轮迁移要修的调用层根因(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:661-692`；根因证据链留底于 [[09-inv-invocation-runtime]] §5)。
4. client_manager 不能整块删。它仍承载 probe、provider-down TTL、usage 统计等编排/观测职责；MVP1 只退役消息转换和 provider 调用部分(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:53-132`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:310-368`；M2 5 件事拆解留底于 [[09-inv-invocation-runtime]] §5)。

## 代码索引 clues

- `RouteChatModelFactory`:当前不存在；用途应是一条 `ResolvedRoute` 到原生 ChatX 实例的构造器，client 层 A' 重设计决策把它定义为调用层核心（M6，完整职责见同目录 `mvp1-alignment.md` §1 / §2 / §5 决策 2-5）。
- `GatewayChatModel`:LangChain `BaseChatModel` 外壳，用来保留 gateway fallback/probe/metadata 等编排行为(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:31-49`)。
- `GatewayChatModel._generate`:执行一次模型生成请求，并在 route 链上做 probe、fallback、真实调用、usage 与异常分类(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:96-271`)。
- `LLMClientManager`:共享 SDK client 缓存、probe、熔断、usage 和 provider 调用 helper(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:40-47`)。
- `LLMClientManager.dispatch_provider_call`:对外的单 route 调用入口，当前仍吃 dict messages 并返回归一化 dict 结果(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:78-121`)。
- `LLMClientManager._dispatch_provider_call`:按 endpoint protocol 分发到各 provider 调用函数(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:866-988`)。
- `LLMClientManager._call_with_token_escalation`:截断时放大 token budget 重新调用，后续应迁到编排层包住 ChatX invoke(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:990-1012`)。

## 待办/疑点

1. 待办:实现时新建 `RouteChatModelFactory`，但本文档不新增生产代码；MVP1 目标见同目录 `mvp1-alignment.md`。
2. 待办:base_url 保存时归一化属于 03 模块；10 模块只记录调用时幂等双保险，不能在工厂里替代保存侧修复(F1 base_url 归一化的主/副分工见同目录 `mvp1-alignment.md` §4 F1 / §5 决策 3；与 [[03-orch-credentials-endpoints]] 共享)。
3. 疑点:源码目录没有 `RouteChatModelFactory` 源文件，但存在历史 `__pycache__/factory.*.pyc`；以 `git ls-files` 和当前 `.py` 源文件为准，不把 pycache 当现状模块。
