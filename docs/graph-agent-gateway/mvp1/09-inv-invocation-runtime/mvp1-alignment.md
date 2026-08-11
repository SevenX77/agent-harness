---
module: 09-inv-invocation-runtime
doc: mvp1-alignment
status: drafted
verified_at: 2026-07-05
binds_design: ./baseline.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:GatewayChatModel/_generate/_answer/_dispatch/_build_chat_result/_build_chat_result_from_ai_message/_usage_from_ai_message/_apply_system_prompt_prefix/_Attempt · packages/graph-agent-gateway/src/graph_agent_gateway/call/plain.py:chat_plainly/PlainAnswer · packages/graph-agent-gateway/src/graph_agent_gateway/call/factory.py:RouteChatModelFactory/build · packages/graph-agent-gateway/src/graph_agent_gateway/registry/call_methods.py:call_method_definition/call_method_client_compatibility/apply_call_method_base_url/provider_probe_backend_for_method · packages/graph-agent-gateway/src/graph_agent_gateway/registry/call_methods.json · packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:LLMClientManager/record_usage · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRoute · packages/graph-agent-gateway/src/graph_agent_gateway/registry/bounds.py:provider_temperature_from_authored
units: [chatx-invocation-runtime]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 09-inv-invocation-runtime — MVP1 Alignment(目标设计)

> **Tier**：③b gateway 公共能力（纯调用运行时；已在 `packages/graph-agent-gateway` 包内，无判据反转）
> **Owns**：拿一条已解析 `ResolvedRoute` + 原始 `BaseMessage`，用原生 LangChain ChatX 真正调模型，取回 `AIMessage`，再把 route metadata 注入结果并把 usage 喂给观测层；**不做** fallback 遍历 / probe / 熔断。ChatX 主路径的 token escalation helper 位于 `call/chat_model.py`,策略归 07 编排层,本篇只记录 invoke bridge 如何被包住。
> **Status**：设计定稿（2026-06 判据复核，归属表判 09=纯 ③b 不变）；代码 = ChatX invoke bridge 已落地，`RouteChatModelFactory` 负责 route → ChatX 构造，普通 chat 面由 `call/plain.py:chat_plainly` 在同一条编排上转朴素数据(D10)；thinking blocks / usage metadata / DeepSeek replay 已在主路径覆盖，非标协议完整性仍 deferred。
> **Related**：[[10-inv-route-chat-model-factory]]（`ResolvedRoute`→原生 ChatX 工厂，本模块的 invoke 用它构造模型）· [[11-inv-provider-profiles]]（provider 差异 init-kwargs 表）· [[07-orch-fallback-circuit-probe]]（fallback/probe/熔断/usage 归属/截断升级编排，与本模块共享 `call/chat_model.py`/`call/clients.py` 但各写各的步骤）· [[01-handoff-interface]]（`ResolvedRoute` 契约，调用层唯一输入）· [[04-orch-registry-schema]]（`ResolvedRoute`/`AIMessage` 字段权威源）· `registry/call_methods.json`（call method 运行时 catalog，定义 method 的 wire family/client compatibility/base_url transform）
> **决策日志**：client 层 A' 重设计决策（D1 方案 A' / D2 编排-调用分离 / M2 client_manager 5 件事拆解 / M3 `_generate` 逐步归属 / F3 截断升级 / F4 thinking / F5 usage-metadata）——完整逻辑 + PM 原话已留底于本文 §4（决策基础）/ §5（决策动机）/ §6（兼容性验证清单）；归属判据见 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（§4 判 09 纯 ③b）
> **现状**：见同目录 `baseline.md`

本篇只写调用目标：原生 ChatX invoke、保留 LangChain message 结构、thinking content blocks 不拍平、从 `AIMessage.usage_metadata` 取 usage、把 route metadata 注入 `AIMessage.response_metadata`。fallback/probe/熔断/retry 跨 route/截断升级重试的编排位置在 [07-orch-fallback-circuit-probe/mvp1-alignment.md](../07-orch-fallback-circuit-probe/mvp1-alignment.md) 写。

## 1. 定义

MVP1 目标：把「一条 route 的实际调用」从自研消息转换 + provider payload + 响应解析，换成**原生 LangChain ChatX 的 `.invoke()`**（ChatX.invoke = 转换 + 调用 + 解析三合一）。本模块是 D2「编排 / 调用分离」里的**调用层运行时**：

- **输入**：一条 `ResolvedRoute`（protocol/base_url/credential_ref/provider_model_id/effective runtime settings）+ 原始 `BaseMessage` 列表（不再拍成 dict）。
- **职责**：用 10 的 `RouteChatModelFactory` 把 route 构造成原生 ChatX → 执行 invoke → 拿 `AIMessage` → 桥接成 LangChain `ChatResult` 并注入 route 归属 metadata。
- **输出**：`ChatResult`（content 保留 ChatX 原始 block 结构，含 reasoning/thinking；response_metadata 带 route_id/endpoint_id/canonical_id/protocol/usage）。

本模块**纯 ③b 公共**（换任何调模型的 app 都要"拿一条 route 真正调"），已在 gateway 包内，归属表判定不变（`module-disposition-revised.md:52`）。注意边界:本模块**只写运行时 invoke 和结果桥接**;route→ChatX 工厂细节在 [[10-inv-route-chat-model-factory]] 写,provider 差异 init-kwargs 在 [[11-inv-provider-profiles]] 写,fallback/probe/熔断/usage 归属/截断升级在 [[07-orch-fallback-circuit-probe]] 写。

**Call method catalog（运行时真相源，不在 docs 配置）**：`registry/call_methods.json` 是 gateway 包内随代码发布的调用方式目录，字段包括 `method_id`、`provider_backend`、`wire_family`、`official_probe`、`client_compatibility`、`base_url_transform`、`auth_token_env`。它回答两类公共问题：① 这个 method 应走哪个官方 probe backend；② 某类 client（例如 `anthropic_messages_client`）能否直接驱动这个 method。未知 method 返回 `unknown`，不被默认当成 incompatible；明确列为 `incompatible` 的 method 才可被上层直接过滤。

**Endpoint method candidates（pre-profile method truth）**：同一 catalog 还拥有 `endpoint_method_candidates`：`protocol_defaults` 把 endpoint protocol 映射到默认 method，`host_overrides` 记录已实测的多协议 host（例如 qnaigc / wavespeed / openrouter）还能提供 Anthropic Messages method。这个配置只回答“缺少 verified profile 时应先尝试哪些 method”；最终能否给某个消费方使用仍由 `client_compatibility` 判定。Studio Copilot 因此不再在前端或 router 中硬编码 provider 名单，也不会因为第三方 route 暂无 profile 就把已支持 Anthropic Messages 的 endpoint 隐藏。

## 1.5 格式中立 + 普通 chat 面（gateway 基础调用能力，2026-06-04 PM 确认）

> **§1 的"换成原生 ChatX `.invoke()`"是「ChatX 面」——给 engine 等 LangChain 消费方的路。但 gateway 调用层是格式中立的，不绑死 LangChain。**

**决策（PM 2026-06-04）+ 动机**：gateway 是**可复用网关**（③b，"换个 app 装上就能用"）。**LangChain 不是普世标准**——市面上大量 app 直接用普通 chat 协议（OpenAI `/chat/completions`、Anthropic Messages）调模型，根本不依赖 LangChain。所以 gateway 必须**格式中立**，对外三张脸，业务端按需选：

1. **ChatX 面**：`BaseChatModel`（官方 ChatX，由 [[10-inv-route-chat-model-factory]] 工厂产;原文并列的 generic 兜底 `GenericRouteChatModel` 已删——每个协议都有官方分支，它路由不到），给 engine 的 `create_agent`。
2. **普通 chat 面**：gateway 替消费方调，返回**非-LangChain** 结果，给不想依赖 LangChain 的消费方。入口 `call/plain.py:chat_plainly(resolved_role, messages) -> PlainAnswer`，`call` 域与包根都导出。**决策不变、机制已换**（决议 D10，2026-08-11）：原文写的是它有一个自己的「普通 chat 内核」（`ordinary_chat.dispatch_ordinary_chat`，自己序列化→调 provider→解析）；那套自研序列化已删，今天这张脸**复用 ChatX 主路径同一条编排**，只在边界上把结果转成朴素 dataclass。理由见 D10-1/D10-2：一次调用两条线路会各说各话，探针改走生产同一个工厂就是为了根治这件事。
3. **route handoff**：只给解析好的 route、消费方自调（copilot 走 `claude_agent_sdk`），见 [[01-handoff-interface]]。

**主次关系（已随 D10 更新）**：原文写「普通 chat 内核」是基础能力、`GenericRouteChatModel` 是它的 LangChain 包装、官方 ChatX 优先、无官方才用 generic 兜底。**今天每个协议都有官方 ChatX 分支**，generic 兜底路由不到，`GenericRouteChatModel` 已删（这一半 P3c 删得对）。所以主次反过来了:**基础调用能力 = `RouteChatModelFactory` + `GatewayChatModel` 的编排**，两张脸都长在它上面——ChatX 面把它原样交出去，普通 chat 面在边界上转成朴素数据。原文那句「两张脸共用一个内核、不要两套实现」的**意图完整保留**，只是内核换了个位置。

**handoff consumer 的 method 兼容性**：route handoff 不等于 gateway 知道消费方产品语义。gateway 只声明通用 client compatibility，例如 `anthropic_messages_client=supported/incompatible/unknown`；Studio Copilot 这类消费方把它投影成自己的 `copilot_sdk_compatible` UI/API 字段。这样 DeepSeek/Ark 这类“官方主 method 是 OpenAI shape、但另有 Anthropic Messages special method”的 provider 不需要前端硬编码，也不会把没见过的 method 误杀。

> **原话依据**（PM 2026-06-04）："现在市面上没有用 chat 协议的 app 了？全部都用 chatX 了？"——反诘 = 普通 chat 消费方实打实存在（非-LangChain app 一大把），gateway 不能只给 LangChain 面。（"ChatX 不绑死"完整 PM 原话见 §4 D2/D3 + [[10-inv-route-chat-model-factory]] §3.5。）

**测试关键点**：① 普通 chat 面返回非-LangChain 结果（不强制消费方依赖 LangChain）——`tests/test_plain_chat_face.py::test_plain_chat_face_takes_and_returns_no_langchain_type` 逐字段查`PlainAnswer` 没有一个字段是 LangChain 类型；② **两张脸共用一条编排**（原文写的是共用 `call/dispatch.py` 内核，见上方主次关系）——`::test_plain_chat_face_walks_the_whole_fallback_chain` 证明普通 chat 面照样逐条走 fallback 链，不是一个只会序列化的薄壳。

## 2. 数据流 / 机制(目标设计与流程)

目标覆盖率：本模块 brief 指定的 `_build_chat_result`、调用桥接、旧 `_call_*` 替换范围和 `models.py` 边界全部覆盖，目标文档覆盖率 100%。`RouteChatModelFactory` 的新模块细节在 10 写；09 只定义 invoke runtime 和结果桥接。

**上下游**：① [[07-orch-fallback-circuit-probe]] 编排循环（`_generate` 遍历 fallback 链、probe、熔断决策）→ 选定一条候选 `ResolvedRoute` → **本模块 invoke runtime**（[[10-inv-route-chat-model-factory]] 构造 ChatX → `.invoke(原始 BaseMessage)` → `AIMessage`）→ `_build_chat_result` 注入 route metadata → `ChatResult` 回到 07 编排循环（记 usage、判异常、必要时 fallback 下一条）。

1. `GatewayChatModel._generate`（执行一次模型生成请求的 LangChain 入口）继续保留编排外壳；当前 ChatX 主路径已经不把 LangChain `BaseMessage` 拍成 provider dict，而是把原始 message 交给工厂构造出的 ChatX。

2. `_apply_system_prompt_prefix`（把 role system prompt prefix 合并进消息列表的函数）的目标职责要从“合并 dict content”变成“合并或插入 `SystemMessage`”；现状 dict 合并代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:695-707`，`SystemMessage` 类型已在当前文件导入，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:15`。

3. `_dispatch`（`GatewayChatModel._generate` 的调用桥接函数）当前职责是拿一条 `ResolvedRoute` 调用 10 的 `RouteChatModelFactory`，再执行 ChatX invoke；它不再桥接到 `LLMClientManager` 的旧 provider-call helper。

4. `ResolvedRoute`（一条 runtime-ready route 候选）是调用层的唯一 route 输入；它带 protocol、base_url、credential_ref、provider_model_id、canonical_id、runtime settings、call method 和 request mapper，字段定义在 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`。

5. 旧 `LLMClientManager` provider-call 入口已从 `call/clients.py` 删除；该类只剩熔断标记与用量记账，已按职责改名 `LLMCircuitAndUsageLedger`（`call/clients.py:17`）。

6. **原 6–12 条描述的 `ordinary_chat._dispatch_provider_call` 与六个 `_call_*`（OpenAI-compatible / OpenAI Responses / Google GenAI / Ark runtime / Anthropic-compatible / WaveSpeed Any-LLM）整体已删**（`call/dispatch.py`，1026 行，PR #718）。它们是「普通 chat 面自己那套序列化」，D10-1 明确不恢复:每家 provider 的请求/响应形状今天由 `dialect` 域唯一持有，生产与探针共用，不再有第二份。

7. 普通 chat 面今天的机制只有一句话:`call/plain.py:chat_plainly` 用 `ResolvedRole` 构造 `GatewayChatModel`，把普通字典消息转成 `BaseMessage` 交进去，再把回来的 `AIMessage` 转成 `PlainAnswer`（text / route_id / endpoint_id / model / protocol / usage / finish_reason / reasoning）。**它吃整条 fallback 链而不是单条路由**——旧签名吃一条 `ResolvedRoute`，那样它比第三张脸(handoff)只多做一次序列化，不值得单独存在;不用 LangChain 的 app 装上网关却拿不到 fallback，等于没装(D10-4)。

8. 只给同步版(D10-6):编排一路到底是同步的(`GatewayChatModel._generate`，没有 `_agenerate`)，异步版只能是 `asyncio.to_thread` 的包装，那是消费方一行就能写的东西。

9. 截断 finish reason 后扩大 token budget 的策略不再是包住 invoke 的 helper（原 `_invoke_with_token_escalation` 与 `ordinary_chat._call_with_token_escalation` 都不存在了），现由 `_Attempt` 在 `_answer` 循环里执行（`call/chat_model.py:123-152`、`:401-408`）；重试前 `void()` 作废已吐出的片段，否则流式消费方会把两次尝试拼成一条答案。

10. `GatewayChatModel._build_chat_result`（把 provider response 包成 LangChain `ChatResult` 的函数）当前同时支持 legacy dict response 和 ChatX `AIMessage`;AIMessage 分支委托 `_build_chat_result_from_ai_message`,代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:311-405`。

11. `GatewayChatModel._build_chat_result` 的目标输出仍是 LangChain `ChatResult`；但 message content 应保留 ChatX 原始 content，包括 reasoning/thinking blocks，不能再通过 `_coerce_text`（把任意 content 强制转字符串的函数）强制变字符串，现状拍平点在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:320-323` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:645-646`。

12. `GatewayChatModel._build_chat_result` 要把 `route_id`、`endpoint_id`、`canonical_id`、`protocol`、`provider_model_id` 和 `effective_runtime_settings` 注入 ChatX `AIMessage.response_metadata`；现状 route metadata 写法在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:323-332` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:348-356`。

13. `GatewayChatModel._build_chat_result` 要从 ChatX `AIMessage.usage_metadata` 取 usage，再供 07 的 usage 归属写入 `LLMCircuitAndUsageLedger.record_usage`（按端点累计 token 的记账函数）；现状 `record_usage` 在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:74`（F5 usage/metadata，决策动机见 §5 决策 4）。

14. **原文此条描述的 `models.py`/`GenericRouteChatModel` generic 兜底路径已删**——`Protocol` 是封闭四值、`RouteChatModelFactory.build` 四个分支齐全并以 `assert_never` 收尾,兜底在类型上不可能被走到(见 [[10-inv-route-chat-model-factory]] §3.5)。原生 ChatX 构造由 10 的 `RouteChatModelFactory` 落地，现状见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/factory.py:19-82`。

## 3. 接口契约

> 本模块是 D2「调用层」运行时，跨边界契约只有两条：① 从 07 编排循环接收一条 `ResolvedRoute` + 原始 `BaseMessage`；② 向上回吐一个带 route metadata 的 `ChatResult`。所有 fallback / 熔断 / usage 归属语义不属本模块契约，归 [[07-orch-fallback-circuit-probe]]。

| 边界 | 契约 |
|---|---|
| **07 编排 → 09 调用（invoke 入参）** | 一条已选定的 `ResolvedRoute`（字段权威源 `registry/schema.py:415-439`：protocol/base_url/credential_ref/credential_fingerprint/provider_model_id/canonical_id/timeout_seconds/effective_runtime_settings）+ 原始 `list[BaseMessage]`（**MVP1 不再拍 dict**，由 ChatX 处理 provider-specific serialization）。`system_prompt_prefix` 以 `SystemMessage` 形式合并 / 插入,不再合 dict content。 |
| **09 → 10（构造 ChatX）** | 把 `ResolvedRoute` 交给 [[10-inv-route-chat-model-factory]] 的 `RouteChatModelFactory` → 拿回原生 `ChatAnthropic`/`ChatOpenAI`/`ChatGoogleGenerativeAI` 实例（已带 base_url 双保险、init-kwargs、provider profile、thinking 归一化、stream_usage）。本模块只负责 `.invoke()` 与结果桥接,不负责构造细节。 |
| **09 invoke 输出（ChatX 原生）** | ChatX `.invoke(messages)` → `AIMessage`{ `content`（**保留原始 block 结构**，含 reasoning/thinking blocks，不拍平）, `usage_metadata`（标准 input/output token 维度）, `response_metadata`（provider 自带） }。 |
| **09 → 07（结果桥接输出）** | `ChatResult`（`_build_chat_result` 产出）：`generations[0].message` = augment 后的 `AIMessage`，`response_metadata` 注入 `{route_id, endpoint_id, model=provider_model_id, canonical_id, protocol, finish_reason, usage, effective_runtime_settings}`；`llm_output` 注入 `{token_usage, model_name, route_id, endpoint_id, canonical_id, protocol, effective_runtime_settings}`。当前字段集见 `call/chat_model.py:323-356`，MVP1 **保留同一字段集**，只把"重建全新 `AIMessage`"改成"augment ChatX 返回的 `AIMessage`"（避免覆盖 provider 自带 metadata、避免丢 content blocks）。 |
| **usage 归属（喂观测，非本模块决策）** | 从 `AIMessage.usage_metadata` 取 token → 交 [[07-orch-fallback-circuit-probe]] 的 `LLMCircuitAndUsageLedger.record_usage`（`call/clients.py:74`）按 endpoint 累计。维度对齐见 §8 待办 1。 |
| **错误 / retry（非本模块决策）** | ChatX 自身瞬时重试（429/5xx/连接，有界）保留在 ChatX 内（F2）；跨 route fallback、异常分类、截断升级重试均在 07 编排层。本模块只保证 ChatX 抛出的异常能被 07 的 `classify_exception` 正确分类（见 §6）。 |
| **归属 / 稳定性** | `ResolvedRoute`/`AIMessage` 字段权威源 = [[04-orch-registry-schema]]（`registry/schema.py`）/ LangChain；`call_method_id` 的运行时解释由 `registry/call_methods.json` + `registry/call_methods.py` 负责；`request_mapper_id` 仍是普通 chat/generic path 的请求映射字段。 |

## 4. 设计决策基础(用户原话)

> **D1 方案 A'（否决 A，保留编排外壳）**（PM 原话，verbatim）："不用留A, 这是错误判断, 正确的是A'。" → 调用层换原生 ChatX，但 `GatewayChatModel` 不删；fallback/probe/熔断/usage/metadata 留编排外壳。本模块只动其中的「调用」步（`_generate` 第 1/5/7 步），编排步（2/3/4/6/8/9）不动。**否决的 A**（激进版）= resolver 直接产 ChatX + 删 `GatewayChatModel` + 用 `with_fallbacks()`：会回归 fallback/probe/熔断/usage/metadata/predict，且 `with_fallbacks()` 只按异常类型、表达不了按 HTTP status 分类。第八轮真机只验证了「调用层换 ChatX 修空-content bug」，从未验证「删编排层」（见 §5）。此决策与 [[07-orch-fallback-circuit-probe]]、[[10-inv-route-chat-model-factory]] 共享（重复留底防 drift）。

> **D2 编排 / 调用分离**（PM 原话，verbatim）："你只要知道谁跟你说我现在要调copilot, 把copilot解析好的route给我, 你就给他, 就ok了, 这是调copilot的路径,你只负责输出编排结果, 不负责调用. 所以这里还引申出一个问题, 编排和调用是不是应该更模块化更内聚化, API写清楚, 编排输入什么输出什么. 调用输入什么输出什么" → 本模块就是「调用」端：输入一条 `ResolvedRoute` + messages，输出 `AIMessage` / 结果（copilot 走 `claude_agent_sdk` 自己调，不归 gateway 调；gateway 只输出编排结果）。此决策与 [[07-orch-fallback-circuit-probe]]、[[10-inv-route-chat-model-factory]]、[[11-inv-provider-profiles]] 共享（重复留底防 drift）。

> **F2 防抖动重试保留**（PM 原话，verbatim）："和Claude sdk copilot一样的问题, 防抖动重试可以留" → ChatX 的有界瞬时重试（429/5xx/连接，对 429 尊重 Retry-After、不对 400/401 重试）保留，不设 `max_retries=0`；它天然是「同 route 防抖动重试」，与网关「跨 route fallback」两层不冲突。要钉死的是：重试耗尽后异常仍能被 `classify_exception` 正确分类（确定性单测，见 §6）。

> **通用判据（gateway = 富能力可复用网关）**（README §2）："换一个完全不同的应用装上 gateway，这个能力还原样能用吗？能 → 公共（gateway）。" → "拿一条 route 真正调模型"是任何调模型 app 的刚需，故本模块纯 ③b 公共。

> **格式中立 / 普通 chat 面**（PM 2026-06-04，verbatim）："不管是不是langchain的格式, gateway都得支持, 不是为了wavespeed, 给copilot的也不是langchain的格式. langchain格式是为了适配engine的create_agent, 不是langchain格式无非是engine报错, 报警. 或者studio侧做拦截, 必须支持langchain才会出现在available models. 但是gateway的职责是匹配通用的模式, 不走langchain就走普通的chat, 都提供,业务端想用啥就给啥" → 后续反诘（确认普通 chat 消费方实打实存在）："现在市面上没有用 chat 协议的 app 了？全部都用 chatX 了？" → 支撑 §1.5：gateway 调用层格式中立，普通 chat 面是基础调用能力、不绑死 LangChain；ChatX 面（官方 ChatX / generic 兜底）只是其上的 LangChain 适配层。此决策与 [[10-inv-route-chat-model-factory]] §3.5 共享（重复留底防 drift）。

## 5. 决策 + 动机(决策原因)

**A' vs A（核心架构决策 D1）**：选择 A' 而不是 A 的原因是调用层要换成 ChatX，但 `GatewayChatModel` 不能删——fallback/probe/熔断/usage/event 都是编排职责，它们全部坐落在 `_generate` 内（熔断跳过 `call/chat_model.py:113` / probe `:115` / 异常分类 `:124,:238` / mark-down `:135,:249` / fallback event `:136,:250` / usage `:227` / metadata `:313-357`）。**被否的 A（激进版）**：resolver 直接裸返回原生 ChatX + 删 `GatewayChatModel` + 用 `with_fallbacks()`——会回归 fallback/probe/熔断/usage/metadata/predict，且 `with_fallbacks()` 只按异常类型、表达不了按 HTTP status 分类（对比 [[06-orch-error-classification]] 的真实分类语义）。判据证据：bug 本在调用层（消息转换）`_langchain_messages_to_dict`（`call/chat_model.py:661-692`）把带 tool_calls 的 `AIMessage(content="")` 转成 `{"content":""}` → 发出空 content → qiniu-anthropic `400 content must not be empty`；第八轮真机只用归一化后的 base_url 验证「调用层换 ChatX 修空-content bug」，从未跑编排、从未验证「删编排层」。

把 `_call_*` 替换为 ChatX invoke 的原因（M2 client_manager 5 件事拆解）是旧代码把“消息转换 + provider 调用 + 输出解析”都手写在 client manager 中；A' 只退役其中「消息转换 + provider 调用/解析」两件（由 ChatX.invoke = 转换+调用+解析三合一取代）。**不整块删除 client manager**——`call/clients.py` 仍扛熔断与用量(该类已改名 `LLMCircuitAndUsageLedger`;原文并列的 probe 探活已搬去 `call/pre_call_probe.py` 且换了语义，见 07 F8)（`call/clients.py:316-383`）、熔断 provider-down TTL（`:286-313`）、usage 统计（`:256-268`）三件编排/观测职责(**其中 probe 那件后来又搬去了 `call/pre_call_probe.py`**)；原文接着说 generic ordinary-chat provider core 迁到 `call/dispatch.py`——那一步后来整个被删(决议 D10-1)。早期「弃用 client_manager」的措辞是错的,但今天这个类确实只剩熔断与用量,已改名 `LLMCircuitAndUsageLedger`。

thinking 不拍平的原因（F4）是旧 dict/ordinary 结果桥接会经 `_coerce_text` 把任意 content 拍成字符串（当前 legacy dict 分支仍在 `call/chat_model.py:321-323` / `_coerce_text` 在 `call/chat_model.py:773-775`）；ChatX 主路径已通过 `_build_chat_result_from_ai_message` 使用 `response.model_copy(...)` 保留 ChatX 的 content blocks 与 provider metadata，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:360-405`。

usage metadata 的原因（F5）是 ChatX `AIMessage.usage_metadata` 已携带标准 usage 元数据；Gateway 仍需把 usage 归属到 endpoint/route 观测（喂 `record_usage`），并把 route_id/endpoint_id/canonical_id/protocol 注入 ChatX `AIMessage.response_metadata`（改 `_build_chat_result`，现状写法 `call/chat_model.py:313-357`），而不是重建全新 `AIMessage`（会覆盖 provider 自带 metadata、丢 content blocks）。

截断升级重试搬家不删除的原因（F3）是 ChatX 本身不做截断 token 升级，而 error-handling 铁律第 7 条要求截断必须自动重试；策略成立至今，落点变了:当年的 `_invoke_with_token_escalation` 已不存在，改由 `_Attempt` 在 `_answer` 循环里执行，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:123-152` 与 `:401-408`。原文并列的 generic ordinary path 同类策略(`ordinary_chat._call_with_token_escalation`)已随 `call/dispatch.py` 一并删除。

## 6. 测试关键点

> 来源 = client 层 A' 重设计决策的「兼容性验证清单（A' 实现必过）」，完整 7 项 + live 冒烟在此留底。本模块（调用运行时）对应其中与 invoke / 结果桥接相关的项；异常分类与 fallback event 的编排断言归 [[07-orch-fallback-circuit-probe]]，本模块只验证 ChatX 抛出的异常**形状**仍可被分类。

- **原始 `BaseMessage` 输入（核心回归用例）**：不转 dict，原始 `BaseMessage` 直接交 ChatX —— **qiniu-anthropic 多轮 tool loop = 头号回归**（旧 `_langchain_messages_to_dict` 把带 tool_calls 的 `AIMessage(content="")` 转成空 content dict → anthropic `400 content must not be empty`；ChatX 直接消费 LangChain tool call message 即可消除）。
- **异常分类形状不回归（头号风险）**：ChatX 瞬时重试（F2）耗尽后抛出的异常，仍能被 07 的 `classify_exception` 正确分到 fallback / fail-fast / retry（fake 401 → fallback、fake 400 非 capability → fail-fast、网络错 → fallback）。
- **输出 metadata 完整**：成功响应的 `AIMessage.response_metadata` / `ChatResult.llm_output` 仍带 route_id / endpoint_id / canonical_id / protocol / usage。
- **thinking blocks 不拍平**：reasoning/thinking content blocks 经 `_build_chat_result` 后仍保留 block 结构，不被 `_coerce_text` 压成普通字符串。
- **截断 token 升级重试仍生效**：搬到 07 编排层后，截断 finish reason 仍触发 token budget 翻倍重试，直到 capability cap 或轮数耗尽（F3）。
- **usage 维度对齐**：ChatX `AIMessage.usage_metadata` 的 prompt/completion 维度能正确喂进 `record_usage`，按 endpoint 累计不丢（另见 §8 待办 1）。
- **predict 分支不回归**：保住 `GatewayChatModel` 类 + 构造器 + `bind_tools`，`PredictGatewayChatModel` 的 `_generate` 全自走不经 dispatch，返回类型 / 契约不变。
- **live 冒烟（非 CI 闸）**：[chatx-provider-patterns.md](../references/chatx-provider-patterns.md) 5/5 人工跑通。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`：`call/chat_model.py` 的调用桥接（`_dispatch`/`_build_chat_result`/`_invoke_with_token_escalation`/`_apply_system_prompt_prefix`）、`call/factory.py` 的 `RouteChatModelFactory`、`call/plain.py` 的普通 chat 面(`chat_plainly`/`PlainAnswer`)。原文并列的 `call/dispatch.py` generic core 与 `models.py:GenericRouteChatModel` 已删(D10-1)。
- **③a** `apps/studio/backend`：N/A（本模块纯调用运行时，不含应用加工四件事；copilot 自己的调用方式归 studio copilot 页 ③a）。
- **② Rust**：N/A（调用层不落 Rust）。

## 8. gaps / 待设计(待办/疑点)

1. ✅ 已处理:ChatX 返回的 `AIMessage.usage_metadata` 字段名已和当前 `LLMCircuitAndUsageLedger.record_usage`（按端点累计 token）需要的 prompt/completion 维度对齐；`_usage_from_ai_message` 同时识别 `input_tokens/output_tokens` 与 `prompt_tokens/completion_tokens`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:863-878`。

2. ✅ 已处理:ChatX `AIMessage.response_metadata` 注入 route metadata 时已避免覆盖 provider 自带 metadata；`_build_chat_result_from_ai_message` 复制 provider metadata 后追加 route metadata,再 `model_copy` augment 原消息,见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:360-405`。

3. ✅ 已处理:`call_method_id` 的公共解释入口已收敛到 `registry/call_methods.json` / `registry/call_methods.py`。官方 probe backend、Anthropic Messages client 兼容性、Ark/DeepSeek base_url transform、特殊认证 env 均从同一 catalog 读取；前端和 Studio backend 不再各写 method 名单。`request_mapper_id` 继续作为普通 chat/generic path 的请求映射字段。

4. ✅ **已定（PM 2026-06-04 + 实验）**：WaveSpeed 实测是 **native-compatible**——其 endpoint 同时支持 OpenAI-compatible `/chat/completions` 和 Anthropic Messages，**用官方 ChatX（`ChatOpenAI`/`ChatAnthropic`）就能跑**（实验 6 轮工具循环 PASS，[chatx-provider-patterns.md](../references/chatx-provider-patterns.md)）。原文接着说"真·非标 provider 才走 `GenericRouteChatModel` 兜底"——该兜底与 `call/dispatch.py` 里的 WaveSpeed 分支都已删,今天真走不通四个 protocol 的 endpoint 应在 03 那层被判不可用,而不是包一层 best-effort(见 [[10-inv-route-chat-model-factory]] §3.5)。

## 已实现 / 与 baseline 差异

| 能力 | baseline 已实现 | MVP1 差异 |
|---|---|---|
| LangChain 输入 | 当前先转 dict，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:104-107`。 | 保留 `BaseMessage`，由 ChatX 处理 provider-specific message serialization。 |
| Provider 调用 | 一条线路两张脸:route → ChatX 工厂构造原生 ChatX → `.invoke()`;普通 chat 面 `call/plain.py:chat_plainly` 走同一条，只在边界转 `PlainAnswer`。 | 后续只补非标 protocol 完整性。原文并列的 `ordinary_chat.dispatch_ordinary_chat` 自研内核已删(D10-1)。 |
| Tool loop | 当前 `AIMessage.tool_calls` 转 dict 时 arguments 固定 `"{}"`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:676-687`。 | ChatX 直接消费 LangChain tool call message，避免手写转换丢结构。 |
| Thinking | legacy dict 分支仍会经 `_coerce_text` 拍平成字符串，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:321-323` 和 `call/chat_model.py:773-775`。 | ChatX 主路径已通过 `_build_chat_result_from_ai_message` 保留 `AIMessage.content` block 结构和 provider metadata。 |
| Usage | 当前从旧 response dict 的 `"usage"` 读取，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:515-528`。 | 从 ChatX `AIMessage.usage_metadata` 读取，并注入 response metadata / llm_output。 |
| Route metadata | 当前 `_build_chat_result` 已写 route metadata，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:323-356`。 | 保留并迁移到对 ChatX `AIMessage` 的 augment，而不是重建丢内容的 message。 |
| 截断升级 | 由 `_Attempt` 在 `_answer` 循环里执行，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:123-152` 与 `:401-408`;重试前 `void()` 作废已吐出的片段。 | 策略归 07 编排层；09 只记录 invoke bridge 被包住,不重复定义 fallback/probe/circuit。 |
| SDK client cache | 当前 `_get_*_client` 创建并缓存 SDK client，见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:144-295`。 | probe 可继续用轻量 client path；真实 invoke 的 client 由 ChatX/factory 管。 |

## 覆盖率

本 alignment 覆盖 09 brief 的全部要求：`call/chat_model.py:_dispatch/_answer/_Attempt/_build_chat_result/_build_chat_result_from_ai_message`、普通 chat 面 `call/plain.py:chat_plainly/PlainAnswer` 均已落到真实 `file:line`(2026-08-11 按 D10 改写;原文点名的 `call/dispatch.py`/`models.py` 已删)。07 的 fallback/probe/mark_down/event/usage 归属只交叉引用，不在本篇重复展开。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:105-108`：当前 system prompt prefix 合并入口，已保留 `BaseMessage` 结构。
- `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:311-405`：当前结果桥接点，dict legacy 分支与 ChatX `AIMessage` augment 分支并存。
- `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:789-859`：旧消息 dict 转换 helper，已退出真实 ChatX 主路径。
- `packages/graph-agent-gateway/src/graph_agent_gateway/call/factory.py`：route → ChatX 工厂，官方 ChatX 主路径构造入口。
- `packages/graph-agent-gateway/src/graph_agent_gateway/call/plain.py`：普通 chat 面(`chat_plainly` → `PlainAnswer`)，复用 ChatX 编排、边界转朴素数据。
- `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:522-587`：ChatX invoke bridge 与 ChatX token escalation。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`：调用层输入 `ResolvedRoute` 的字段。
- (已删) `call/models.py:GenericRouteChatModel` 通用 route wrapper——每个协议都有官方 ChatX 分支，兜底路由不到。

## 交叉引用(链接,不复制)

- [[10-inv-route-chat-model-factory]]：`ResolvedRoute`→原生 ChatX 工厂（本模块 invoke 用它构造模型；base_url 双保险 / init-kwargs / thinking 归一化 / stream_usage 在那边写）
- [[11-inv-provider-profiles]]：provider 差异 init-kwargs 表（只管 ChatX 构造差异；`call_method_id` 的 method catalog 不并入 ProviderProfile）
- [[07-orch-fallback-circuit-probe]]：fallback 循环 / probe / 熔断 / mark_down / fallback event / usage 归属 / 截断升级重试（与本模块共享 `call/chat_model.py`/`call/clients.py`，各写各的步骤）
- [[01-handoff-interface]]：`ResolvedRoute` 契约（调用层唯一输入）
- [[04-orch-registry-schema]]：`ResolvedRoute` 字段权威源（本模块只消费）
- client 层 A' 重设计决策（D1/D2/M2/M3/F2-F5）：完整逻辑 + PM 原话留底于本文 §4/§5/§6 / 归属表 `module-disposition-revised.md`（§4 判 09 纯 ③b）

## 2026-07-05 补记: temperature 到 provider 的换算

> **本节曾被编码事故毁掉**:PR #392(2026-07-05)写入时中文全部变成 `?`,整段无法阅读。
> 2026-08-11 按**当时的代码事实重新写出**(不是猜那些丢掉的字):依据是
> `registry/bounds.py` 的 `AUTHORED_TEMPERATURE_MAX`/`_PROTOCOL_TEMPERATURE_MAX`/
> `temperature_ceiling`/`provider_temperature_from_authored`,以及
> `tests/test_route_chat_model_factory.py:251/337` 两条断言。

- **authored 尺度是 provider-neutral 的 0..2**(`AUTHORED_TEMPERATURE_MAX = 2.0`,`bounds_for(route, "temperature")`
  返回 `0.0..2.0`)。Studio 里 role temperature 与 node override temperature 都写在这把尺子上,网关不关心它们谁覆盖谁。
- **`None` 表示"没人选过"**,一路保持 `None` 传到底,不替换成任何默认值——
  `provider_temperature_from_authored` 第一行就是 `if temperature is None: return None`。
- **落到 provider 时按这条路由的上限换算**:`share / 2.0 * temperature_ceiling(route)`。
  上限先看路由自己声明的能力值(`capability temperature.max`),没有才用协议默认:
  `anthropic_compatible` = **1.0**,`openai_compatible` / `ark_runtime` / `google_genai` = **2.0**。
  所以 authored 1.5 到 Anthropic 是 **0.75**,到 OpenAI 仍是 **1.5**(`test_route_chat_model_factory.py:251` 与 `:337`)。
- **换算发生在构造 provider kwargs 的时候**,不在 role 物化时:同一条 role 的 effective runtime settings
  可以喂给上限不同的两条路由,各自换算,互不影响。
- 原文此处还有一句讲 `GenericRouteChatModel` 与 ordinary-chat 分支的换算,两者已删(见 §1 三张脸与决议 D10),不再适用。

