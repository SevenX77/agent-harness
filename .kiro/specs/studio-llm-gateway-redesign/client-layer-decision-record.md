---
status: Decided (架构方向已拍板, 实现任务待据此重写)
created: 2026-06-02
owner: Studio + Engine
supersedes: ../../../temp/2026-06-01-option-a-client-layer-impl-task.md
audit: ../../../temp/2026-06-01-option-a-client-layer-impl-task-audit.md
probe_evidence: ../../../temp/2026-06-01-probe-results.md
---

# LLM Gateway Client 层重设计 — 决策记录(方案 A')

> 本文是 client 层(原生 langchain ChatX 迁移)的**权威决策记录**。每条决策下附调查到的代码证据(`file:line`)作为线索/证明。
> 取代 temp 里的 option-a 实现任务(其方案 A 激进表述已被否决)。
> 与本 spec 的 `design.md` **正交**:`design.md` 管 2026-05-25 回归修复(save 解耦 / resolver 优雅跳过 / 测试 SSOT / 远端形状),本文管 client 层换原生 ChatX。两者可独立推进。

---

## 0. 范围与状态

- **本文范围**:client 层 A' 迁移 + 「编排 / 调用」分离原则。
- **状态**:架构方向已与用户拍板锁定(**A',否决 A**);据此重写实现任务后再交付 codex。
- **关系**:与 `design.md`(回归修复)正交;实现排序在 §6 记录。

---

## 1. 核心架构决策

### D1 — 方案 A'(否决 A)

**决策**:resolver/gateway **不**裸返回原生 ChatX、**不**删 `GatewayChatModel`。保留 `GatewayChatModel` 作为**编排外壳**,只把「每条 route 的实际调用」从自研消息转换换成原生 langchain ChatX。

**否决 A(激进版)的理由**:A = 「resolver 直接产 ChatX + 删 GatewayChatModel + 用 `with_fallbacks()`」。它会回归 fallback / probe / 熔断 / usage / metadata / predict。第八轮真机只验证了「调用层换 ChatX 修掉空-content bug」,**从未验证「删编排层」**。

**证据**:
- bug 在调用层(消息转换):`gateway_chat_model.py:661-692` `_langchain_messages_to_dict` 把带 tool_calls 的 `AIMessage(content="")` → `{"content":""}`;再经 client_manager anthropic dispatch 发出空 content → qiniu-anthropic `400 content must not be empty`。
- 编排层职责坐实(都在 `_generate`):`gateway_chat_model.py:111-271` — 熔断跳过 `:113` / probe `:115` / 分类 `:124,238` / mark-down `:135,249` / fallback event `:136,250` / usage `:227` / metadata `:313-357`。
- 第八轮证据边界:`temp/probe_chatx.py:7-8,55`(用 creds 里**已归一化**的 base_url、**未跑编排**);`temp/2026-06-01-probe-results.md`。
- `with_fallbacks()` 只按异常类型,表达不了「按 HTTP status 分类」(对比 `error_classification.py`,见 M5)。

**用户原话**:
> "不用留A, 这是错误判断, 正确的是A'"

---

### D2 — 编排 / 调用 分离(架构原则)

**决策**:把「编排(orchestration)」与「调用(invocation)」做成两个内聚模块,各有明确 API:

| 层 | 输入 | 输出 | 职责 |
|---|---|---|---|
| **编排层** | role_name / model_override | 解析好的 route(s)(`ResolvedRoute`:protocol / base_url / credential_ref / provider_model_id / runtime settings + fallback 顺序 + 熔断/probe 决策) | **只决定「该用哪条 route」,不负责真正调用** |
| **调用层** | 一条 `ResolvedRoute` + messages (+ runtime params) | `AIMessage` / 结果 | build 原生 ChatX + invoke + 取结果 |

**为什么**(copilot 用例):调用方说「给我 copilot 解析好的 route」,编排层返回 route,**调用方自己调**(copilot 走 `claude_agent_sdk`,不归 gateway 调)。gateway 只输出编排结果,不负责调用。

**现状问题**:`GatewayChatModel._generate` 把编排与调用揉在一起(拆解见 M3);`PredictGatewayChatModel` 还把 mock **业务逻辑**塞进 gateway model(见 M4)。A' 落地时应让「调用」成为清晰的独立模块(`RouteChatModelFactory`,见 M6),编排循环只做决策 + 委派调用。

**证据**:
- 编排输出已有雏形:`registry/resolver.py` 的 `resolve_role` 已产出纯数据 `ResolvedRole`/`ResolvedRoute`;`resolver.py:92-98` 调它。
- 揉合点:`gateway_chat_model.py:190-236`(循环里直接 `_dispatch` + `_build_chat_result`)。

**用户原话**:
> "你只要知道谁跟你说我现在要调copilot, 把copilot解析好的route给我, 你就给他, 就ok了, 这是调copilot的路径,你只负责输出编排结果, 不负责调用. 所以这里还引申出一个问题, 编排和调用是不是应该更模块化更内聚化, API写清楚, 编排输入什么输出什么. 调用输入什么输出什么"

---

### D3 — Gateway = 可复用服务,API 一等公民,前端不归 gateway(2026-06-02)

**决策**:gateway 只提供服务(编排 + 调用),**不含任何前端**。前端是 **studio 的前端**,studio 只是 gateway 的一个**消费方**,不是 gateway 的一部分。gateway 必须设计清晰的**对外 API**,供 studio 及**其他 app 复用**。

**含义**:
- 模块分清 **gateway 核心(可复用,应在 `packages/graph-agent-gateway`)** vs **studio 适配层**:
  - `routers/llm.py`、`routers/copilot.py`(`14-api-router`)= studio 的 HTTP 适配器(消费方),**非 gateway 核心**。
  - `apps/studio/backend/app/services/llm_*`(动脑 services)= **应迁入 gateway 包**(对齐 handover「彻底迁 LLM 后端入 gateway 包」)。
- 对外 API 两级:① 包级 Python API(`ModelResolver.resolve → route`、`RouteChatModelFactory`、invocation);②(远期)服务级 API(REST/gRPC,对齐 `architecture-direction.md` 远端服务化)。
- 文档要写清**「API 怎么提供」**(输入/输出契约),每个模块标注 **core / studio-adapter**。

**用户原话**:
> "前端不归gateway管, 前端是studio的前端, gateway只管提供服务, 所以模块功能分个清楚, API怎么提供要写清楚, 要考虑复用其他app"

**待设计**(见 handoff §4):public API 清单、core/adapter 划分、provider 聚合层、后端迁入边界。

---

## 2. 模块决策(职责 / 决策 / 证据)

### M1 — `ModelResolver`(`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`)

**职责**:role 名 → 装配一个 `BaseChatModel`(正常=`GatewayChatModel`,predict=`PredictGatewayChatModel`);加载 credentials/roles 文件 + schema 校验;手动 `mark_provider_down`。自身**不调任何 LLM**。

**决策**:
- 把「role → `ResolvedRoute`(s)」暴露为**一等编排 API**(供 copilot 等「只要 route」的调用方),对齐 D2。
- A' 下仍返回 `GatewayChatModel`(不裸返回 ChatX)。
- predict 分支理想态见 M4;**A' 本期不动** resolver 的 predict 分支。

**证据**:`resolver.py:73-146`(`resolve`);`:119-134`(predict 分支);`:92-98`(调 `resolve_role`);`:186-261`(加载 + v4/v2 schema 校验)。

---

### M2 — `LLMClientManager`(`client_manager.py`)— 5 件事拆解

| # | 职责 | 代码 | A' 处理 |
|---|---|---|---|
| ① | 原生 SDK 客户端缓存(OpenAI/Anthropic/Google/Ark,连接池) | `_get_*_client` `:144-295` | probe 仍用;真实调用改由 ChatX 自建客户端 |
| ② | **probe 探活**(发 1-token 真请求) | `probe_provider` `:64`, `:371-438` | **保留**(编排) |
| ③ | **熔断 provider-down**(失败后 TTL 跳过) | `is_provider_marked_down`/`mark_provider_down` + `_provider_down_cache` `:340-368` | **保留**(编排) |
| ④ | **usage 统计**(按端点累计 token) | `record_usage`/`get_usage_stats` `:310-333` | **保留**(编排) |
| ⑤ | 消息转换 + provider 调用 + 截断自动加 token 重试 | `dispatch_provider_call`→`_call_*` + 消息 helper + `_call_with_token_escalation` `:78-121`, `:440-1012` | 见下分项 |

**⑤ 拆成三件**(纠正早期「整块替换」的措辞):
- 消息转换 → **ChatX 取代**。
- provider 调用(调 SDK + 解析响应)→ **ChatX 取代**(ChatX.invoke = 转换+调用+解析三合一)。
- 截断 token 升级重试 → **保留**,搬到编排层包在 ChatX invoke 外(见 F3)。

**更正**:早期说「弃用 client_manager」是错的——它扛着 ②③④,**不能整块删**。本期只退役 ⑤ 的「消息转换 + provider 调用」。

---

### M3 — `GatewayChatModel._generate` 流程拆解(用户特别要求)

`gateway_chat_model.py:96-271`,逐步标注「编排 / 调用」与 A' 是否改:

| 步 | 代码 | 内容 | 归属 | A' |
|---|---|---|---|---|
| 1 | `:104-107` `_apply_system_prompt_prefix(_langchain_messages_to_dict(...))` | 消息准备 | 调用层(输入) | **改**:不转 dict,原始 `BaseMessage` 交 ChatX,system prefix → `SystemMessage`(**bug 根源**) |
| 2 | `:111` `for ... candidate in routes` | 遍历 fallback 链 | 编排 | 留 |
| 3 | `:113` `_is_marked_down → continue` | 熔断跳过 | 编排 | 留 |
| 4 | `:115-189` `_probe(...)` + 失败处理 | probe 探活 | 编排 | 留(失败→分类→fallback/raise + event + mark_down) |
| 5 | `:190-226` `_dispatch(...)` | 实际调用 | 调用层 | **改**:build ChatX + `.invoke()` |
| 6 | `:227-235` `_record_usage` | usage 记账 | 编排/观测 | 留(改从 ChatX `usage_metadata` 取,见 F5) |
| 7 | `:236,:313-357` `_build_chat_result` | 构建结果 | 调用→编排桥接 | **改**:augment ChatX `AIMessage` 注入 route metadata(F5)、保留 thinking blocks(F4) |
| 8 | `:237-265` `classify_exception` + 失败处理 | 异常处理 | 编排 | 留(沿用真实分类,见 M5) |
| 9 | `:267-271` `raise AllProvidersFailedError` | 全失败 | 编排 | 留 |

**小结**:改 **1 / 5 / 7**(调用层),留 **2 / 3 / 4 / 6 / 8 / 9**(编排层)。这正是 D2 分离在 `_generate` 内的体现。

---

### M4 — `PredictGatewayChatModel`(`predict_interception.py`)— 是什么 + 架构问题

**是什么**:skill(`graph_agent`)的「干跑模拟」——**不调真 LLM**,用 `predict_context.resolve_generation` 出 mock,产 `predict_trace` + `path_diff`(期望 vs 实际 phase 路径)。**不是 copilot**(copilot = `claude_agent_sdk` 独立运行时,不跑 skill phase 图)。

**架构问题(记录,A' 不处理)**:mock 是**业务逻辑**,不该写在 gateway 的 model 类里。按 D2,gateway 只输出编排结果,mock 应在 predict 流程自己做。**predict 重设计归用户,out of scope**。

**A' 决策**:不碰 predict(其 `_generate` 全自走,不经 dispatch);只需保住 `GatewayChatModel` 类 + 构造器 + `bind_tools`,predict 自动不变。

**证据**:`predict_interception.py:17`(subclass `GatewayChatModel`),`:34-55`(mock `_generate`,不调 provider);`protocol.py:14-21`(`resolve_generation`);`predictor.py:41-128`(`predict_skill` + `mock_llm` + `path_diff` + 死锁守卫)。

**用户原话**:
> "predict完全不调用llm 的话为什么要把逻辑写在gateway呢? 这是业务逻辑, 应该在跑predict流程里面自己mock就好了 ... anyway 这不归你管"

---

### M5 — `error_classification`(真实语义)

**决策**:执行期分类**不变**,沿用 `classify_exception`。

**真实语义**(纠正多处文档的错误简写):

| 状态/情况 | 分类 | decision |
|---|---|---|
| 429 / 500 / 502 / 503 / 504 / 529 | retry/fallback | `fallback_allowed` |
| 网络错误(ConnectError/Timeout) | retry same route | `fallback_allowed` |
| **401 / 402 / 403 / 404** | **fallback**(credential/route scope) | `fallback_allowed`(**不是 fail-fast!**) |
| 400 + capability 标记(unsupported/not supported/invalid model...) | fallback | `fallback_allowed` |
| 400(非 capability)/ 413 / 422 | fail request | `fail_fast` |
| 未知 | fail request | `fail_fast_with_route_context` |

**文档错误(待更正)**:`temp` option-a task 第 44 行、本 spec **`design.md:142`** 都把它写成「`400/401/403/404/422 → fail-fast`」,错(401/403/404 实为 fallback)。`design.md:142` 已在本轮一并更正。

**证据**:`error_classification.py:15-17`(三组状态码常量),`:133-188`(分支),`:83-88`(action → decision 映射)。

---

### M6 — `RouteChatModelFactory`(新建,调用层核心)

**职责**:`ResolvedRoute` → 原生 ChatX(`ChatAnthropic`/`ChatOpenAI`/`ChatGoogleGenerativeAI`)。内部 = base_url 归一化双保险(F1)+ provider profile init-kwargs(F6)+ thinking 归一化(F4)+ stream_usage(F5)+ deepseek patch(借鉴)。

**决策**:这是 D2「调用层」的落点;编排循环第 5 步调它。

**证据(借鉴范本)**:见 §4。

---

## 3. 能力 / 功能决策

### F1 — base_url 归一化

**决策**:
- **主 = credential 保存时归一化**:每 endpoint 存确定的 canonical 格式,从源头保证对(每 protocol 格式固定)。
- **副 = 调用时幂等归一化**做双保险(已 canonical 则 no-op)。
- 锁定前**再做几次真机测试巩固**每 protocol 规则。

**每 protocol 规则**:anthropic 去尾 `/v1`(SDK 自加 `/v1/messages`);openai 保持(含 `/v1` 或 provider 接受无 `/v1`);deepseek-anthropic 去 `/v1` 后 `+/anthropic`;ark openai-compat `.../api/v3`。

**为什么不是「运行时乱归一化」**:之前觉得乱,是因为多次实验用错格式导致失败;规则其实每 protocol 确定统一。存 canonical 最稳。⚠️ deerflow/deepagents **不做**这步(假设 base_url 已对)——这块**没东西可抄,自建**。

**证据**:memory `llm-gateway-core-findings`;probe-results 第三~七轮;`client_manager.py:162,:203`(原样透传 base_url);copilot 的 `_deepseek_anthropic_base_url`/`_ark_anthropic_base_url`。

**用户原话**:
> "base_url 归一化的关键是每个protocol都有确定的统一的规则 ... 如果结果足够确定, 我觉得放在credential保存时归一化是最好的, 每个endpoint都有固定格式, 存这个固定格式保证不会出错"

---

### F2 — retry(撤回「max_retries=0」)

**决策**:**保留 ChatX 的瞬时重试**(有界,如默认 2),**不设 0**。

**理由**:ChatX 只对 429/5xx/连接重试、对 429 尊重 Retry-After、不对 400/401 重试 → 天然是「同 route 防抖动重试」,与网关「跨 route fallback」两层不冲突;当前代码反而**没有同-route 重试**,瞬时 429 会把所有 route 连环跳废。唯一要钉:重试耗尽后异常仍能被 `classify_exception` 正确分类(确定性单测)。

**证据**:`gateway_chat_model.py:237-249`(把 retryable 也当 `fallback_allowed` → 直接跳 route);`client_manager.py:171,:206`(现 SDK `max_retries=0`)。

**用户原话**:
> "和Claude sdk copilot一样的问题, 防抖动重试可以留"

---

### F3 — 截断 token 升级重试(保留,搬家)

**决策**:保留;从 client_manager dispatch 搬到编排层,包在 ChatX invoke 外(ChatX 不做这个,不能随 dispatch 一起删)。

**证据**:`client_manager.py:990-1012` `_call_with_token_escalation`;error-handling 铁律第 7 条(截断必须自动重试)。

---

### F4 — thinking content blocks

**决策**:取最终文本时保留 ChatX 的 content blocks(reasoning/thinking),别用旧 `_coerce_text` 拍平成字符串。

**证据**:`gateway_chat_model.py:645-646` `_coerce_text`;deerflow thinking 处理(§4)。

---

### F5 — usage / metadata

**决策**:从 ChatX `AIMessage.usage_metadata` 取 token 喂 `record_usage`;把 route_id/endpoint_id/canonical_id/protocol 注入 ChatX `AIMessage.response_metadata`(改 `_build_chat_result`)。借 deerflow `stream_usage` 默认开,保证第三方 openai-compat 端点 usage 不为空。

**证据**:`gateway_chat_model.py:313-357`(现 metadata 写法);`client_manager.py:310-333`(usage 累计);deerflow `factory.py:34-47,:154-161`(stream_usage)。

---

### F6 — provider 差异 → init-kwargs profile

**决策**:用 deepagents `ProviderProfile` 模式(provider/model → 一张 init-kwargs 表 + 可选 `pre_init`/factory)装 provider 差异(headers、responses api、温度默认、thinking 开关等);**仅当需改请求 payload 才子类覆盖单方法**(deerflow 范式),绝不重写整套消息转换。

**证据**:deepagents `provider_profiles.py`(整套机制);deerflow `patched_deepseek.py`(子类覆盖 `_get_request_payload`)。

---

## 4. 借鉴 vs 自建(deerflow / deepagents)

**可借鉴(适配层)**:
- deepagents `ProviderProfile` 注册表机制:`_models.py:15-36`(`resolve_model` = `init_chat_model` + `apply_provider_profile`)、`provider_profiles.py`(整文件)。
- deerflow thinking 归一化:`factory.py:94-146`(跨 anthropic 原生 / openai-compat `extra_body` / vLLM / Codex)。
- deerflow `stream_usage` 默认开:`factory.py:34-47`。
- deerflow `PatchedChatDeepSeek` 子类修 reasoning_content 多轮:`patched_deepseek.py`(依赖 `assistant_payload_replay`,要一起搬)。

**自建(它们没有)**:base_url 归一化(F1);role fallback 链 / 熔断 / probe / 我们的 usage 汇总 / predict / route metadata 合约。

**不直接抄文件**:deerflow `create_chat_model` 耦合 `AppConfig`/`resolve_class`/tracing;deepagents 用 `init_chat_model` + 自己的 profile registry,消费 `provider:model` 字符串。都与我们 `ResolvedRoute` 不一样 → **移植模式 + 具体逻辑进吃 `ResolvedRoute` 的 `RouteChatModelFactory`**,不搬文件。

本地路径:`temp/deerflow/backend/packages/harness/deerflow/models/{factory.py,patched_deepseek.py}`、`temp/deepagents/libs/deepagents/deepagents/{_models.py,profiles/provider/provider_profiles.py}`。

---

## 5. 兼容性验证清单(A' 实现必过)+ 确定性单测

1. **异常分类(头号风险)**:fake 401 / 400 / 网络错 喂 `classify_exception` → 分别 fallback / fail-fast / fallback;且 ChatX 瞬时重试耗尽后的异常仍可分类(F2)。
2. **输入**:不转 dict,原始 `BaseMessage` 给 ChatX —— **qiniu-anthropic 多轮 tool loop = 核心回归用例**。
3. **输出 metadata**:成功响应仍带 route_id / endpoint_id / canonical_id / protocol / usage。
4. **thinking blocks** 不被拍平。
5. **截断 token 升级重试**仍生效(F3)。
6. **predict 分支**不回归(返回类型 / 契约不变)。
7. **fallback event** payload 仍带 from/to route 诊断。
- live 冒烟:`temp/probe_chatx.py` 5/5(人工,**非 CI 闸**)。

---

## 6. Out-of-scope / 待用户(记录,A' 不动)

- **predict 重设计**(mock 移出 gateway,gateway 只输出编排结果)—— 归用户,本期不动。
- **编排/调用模块化粒度**(是否把 `_generate` 第 5 步抽成独立 `RouteInvoker` 类的边界)—— A' 至少做到 `RouteChatModelFactory`;更彻底分离可后续。
- **与本 spec `design.md`(回归修复)的合并/排序** —— 两者正交,建议回归先行(已有 tasks),A' 作为后续 Phase。
