---
module: 07-orch-fallback-circuit-probe
doc: mvp1-alignment
status: drafted
verified_at: 2026-06-02
binds_design: ./baseline.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:GatewayChatModel/_generate/_answer/_decided/_said_what_happened/_next_candidate/_build_chat_result/_is_marked_down/_mark_down/_usage_total_calls/_record_usage · packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:LLMCircuitAndUsageLedger/is_provider_marked_down/mark_provider_down/record_usage/usage_total_calls · packages/graph-agent-gateway/src/graph_agent_gateway/call/pre_call_probe.py:build_probe_model/probe_call_settings · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:RuntimePolicy/ProbeResult · apps/studio/backend/app/services/model_probe.py:ModelProbeResult · apps/studio/backend/app/routers/llm.py:_probe_official_call_method · apps/studio/backend/app/services/llm_health_store.py:RuntimeCircuit/SqliteLlmHealthStore
units: [fallback-circuit-probe-health]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 07 — Fallback / Circuit / Probe（编排外壳:回退链·熔断·前置探问）· MVP1 设计

> **组织方式**：**以每个功能为索引** —— 每个功能(F1–F9)一段，把它的机制/数据流·决策+动机·原话·测试点·status·归属(region/platform)**全收在自己段里**；仅「定义」「接口契约」是模块级总览，证据附录(已实现/差异、覆盖代码/覆盖率、代码索引、决策原因反转)挂在文末模块级。现状基线见同目录 `baseline.md`。
> **Tier**：③b gateway 公共能力内核（`gateway_chat_model._generate` 编排外壳 + `call/pre_call_probe.py` 前置探问 + `LLMCircuitAndUsageLedger` 熔断/usage 已在包内；`llm_health_store` 熔断持久化现散 ③a 待下沉）
> **Owns**：fallback 链遍历 + 熔断跳过 + 1-token 前置探问(问设置,不是探活,见 F3) + 异常分类 + mark_down + fallback event + usage 归属 + 截断升级重试 + 批量探测策略；**每条 route 的真实 ChatX invoke 不在本模块**（归 [[09-inv-invocation-runtime]]）
> **Status**：设计定稿（2026-06 判据第四轮反转）；代码 = `_generate` 编排段保留、调用段换 ChatX(归 09)、token escalation 已落地(现由 `call/chat_model.py:123-152` 的 `_Attempt` 承担)、`llm_health_store` 待下沉 ③b
> **Related**：[[06-orch-error-classification]]（`classify_exception` 状态码语义权威源，本模块只消费）· [[09-inv-invocation-runtime]]（真实 invoke / ChatX bridge / ordinary-chat generic core / 消息转换 / F4 thinking / F5 metadata 注入落点）· [[13-x-tracing-events-exceptions]]（`LLMFallbackEvent` / `emit_llm_fallback_event` / `AllProvidersFailedError`）· [[04-orch-registry-schema]]（`RuntimePolicy` / `ProbeResult` 字段权威源）· [[03-orch-credentials-endpoints]]（F1 base_url 归一化共享决策的存写主体，前置探问要打对 base_url）· [[08-orch-test-status-ssot]]（熔断持久化的另一消费视角 + 6 态投影）· studio copilot（copilot-assist + ux-spec §3.8）（copilot 测试的应用侧消费方;`copilot_test.py` 已拆解,见 F9 归属）
> **决策日志**：client 层 A' 重设计决策（D1 A' / D2 编排-调用分离 / M2 client_manager 5 件事 / M3 `_generate` 逐步归属 / F2 retry / F3 截断升级 / F5 usage）的完整逻辑 + PM 原话已就地留底在下文各功能段（F1 收 D1/D2、F3 收 base_url、F4 收 F2 retry、F5 收 F3 截断、F6 收 F5 usage、F8 收批量探测、F9 收熔断持久化反转）；归属反转源 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md` 第 47-49 行
> **现状**：见同目录 `baseline.md`

## 定义

MVP1 目标:`GatewayChatModel._generate`（LangChain 调用进入 Gateway 后执行 fallback 链的主循环）继续作为**编排外壳**,只把「每条 route 的实际调用」从自研消息转换换成原生 langchain ChatX,编排语义一条不丢。

本模块按判据全部落在 **③b gateway 公共能力内核**,只有少量明确划归 ③a 的应用加工:

- **fallback 链遍历 / 熔断跳过 / probe / 异常分类 / mark_down / fallback event / usage 归属 / 截断升级重试** = **③b 公共**（gateway 机制本身衍生,任何调模型 app 装上就有,已在 `call/chat_model.py` + `call/clients.py`）。
- **熔断持久化 `llm_health_store`(把冷却事实跨进程存起来)** = **③b 公共内核**（**本轮反转**:原 baseline 判它「③a seam / 是否打通是疑点」,现按判据已定 ③b 待下沉;存储介质 SQLite 路径由 ③a 注入）。
- **批量探测策略(对一批 route 编排 probe 的顺序/并发/跳过历史失败)** = **③b 公共**（探测编排是 gateway 机制,现编排住 `routers/llm.py` 的探测段,只有"批量进度 UI"留 ③a）。
- **copilot 测试探针** = **③a 应用**（copilot 专属,与 ③b 通用 route probe 不同源,留 studio;详见 F9 归属 + F8 边界 + 文末决策原因，应用侧消费方 = studio copilot（copilot-assist + ux-spec §3.8））。**接线工程已完工**:走真 `ClaudeSDKClient`(`apps/studio/backend/app/routers/llm.py:2052`),`copilot_test.py` 文件已拆解。

不调真实模型(真实 invoke 归 [[09-inv-invocation-runtime]]);前置探问例外——它是**编排层自己**发的 1-token 真请求。**注意与原文的差别**:原设计写"用 client manager 的轻量 SDK client,不走 ChatX",今天恰恰相反——`call/pre_call_probe.py:63-81` 的 `build_probe_model` **刻意复用生产同一个 `RouteChatModelFactory`**,好让"探得通"和"跑得起来"不会各说各话;探问的问题也从"活着吗"换成了"收不收这些设置"(见 F3)。

**上下游(全模块总览)**:① resolver 输出 `ResolvedRole`(有序 `ResolvedRoute` + `runtime_policy`)→ **`_generate`(③b 编排外壳)** 按 routes 顺序遍历 → 每条候选先 熔断跳过 / probe → 选中后委派 **[[09-inv-invocation-runtime]] 的 ChatX invoke(③b 调用层)** 真调 → 成功则归 usage + 注 route metadata 返回;失败则 `classify_exception`(③b 错误分类,归 06)决定 fallback / fail-fast,fallback 则 mark_down + 发 fallback event + 继续下一条 → 全失败抛 `AllProvidersFailedError`。

**状态机（route 进入实际调用的判定,目标语义）**:候选 →〔熔断查询:`is_provider_marked_down`==true → `continue` 跳过〕→〔`probe_before_call`==true → 1-token 前置探问(**今天问的是设置收不收,不是路由死没死**,见 F3):被拒 → 去掉被拒的偏好重问,而**不是** mark_down;答得上 → 进调用〕→〔ChatX invoke:成功 → 归 usage + metadata 返回;异常 → `classify_exception`:fail-fast → 抛;可 fallback → mark_down + event + 继续〕→ 遍历尽 → `AllProvidersFailedError`。

**编排 / 调用边界（M3 `_generate` 9 步逐步归属,逐步表见 F1 与 F1 D2 决策)**:留编排(2/3/4/6/8/9 步)= 遍历 / 熔断跳过 / probe / usage 记账 / 异常处理 / 全失败;改调用(1/5/7 步)= 消息准备(不再拍 dict)/ 实际调用(build ChatX + invoke)/ 构建结果(augment ChatX `AIMessage`),改的三步归 09。

## 接口契约

> 跨边界签名 / 输入输出 / 错误 / 归属（模块级，跨功能共享）。`_generate` 内部各桥接函数(`_is_marked_down`/`_mark_down`,均为 `call/chat_model.py` 模块级函数)是同进程编排细节,不在此列;此处只钉编排外壳对上(resolver)、对下(09 调用层 / `client_manager` 健康接口)、对侧(tracing / health store)的契约。

| 边界 | 契约 |
|---|---|
| **resolver → `_generate`（入参）** | `ResolvedRole`{ `routes`: `ResolvedRoute[]`（有序 fallback 链）, `runtime_policy`: `RuntimePolicy`（down TTL / probe timeout / `token_escalation_rounds`,字段权威源 `registry/schema.py:88-98`）}。`_generate` **看得到**"有序候选 + 运行时策略"(通用编排概念),**看不到**"角色怎么被 UI 编辑 / 怎么排序出来"(③a 应用加工 + 02 materialize)。 |
| **`_generate` → 09 调用层（每条 route）** | 入:一条 `ResolvedRoute` + 原始 `BaseMessage[]`(不拍 dict) + runtime params;出:ChatX `AIMessage`(含 `usage_metadata` + 注入的 route metadata) 或抛异常。**契约要求**:① 抛出的异常形状能被 `classify_exception` 沿异常链找到 `status_code`/`response.status_code`;② 成功 `AIMessage.usage_metadata` 非空可喂 usage 归属;③ thinking content blocks 不被拍平(归 09 F4)。 |
| **`_generate` → `ledger`（健康/usage,③b 公共接口）** | 注入形参今为 `ledger`,类名今为 `LLMCircuitAndUsageLedger`(`call/clients.py:17`)。`is_provider_marked_down(...) → bool`(`:31`)、`mark_provider_down(..., runtime_policy)`(`:42`)、`record_usage(...)`(`:74`)、`usage_total_calls(route) → int`(`:53`)。**M2 拆解里的 ②probe 已不在这个接口上**:前置探问搬去 `call/pre_call_probe.py:probe_call_settings`,由 `call/chat_model.py:309-320` 直接调,而且语义换了(见 F3)。 |
| **熔断持久化（③b 公共,现 ③a 待下沉）** | `SqliteLlmHealthStore.open_circuit(circuit: RuntimeCircuit)` 写、`get_active_circuits(route_id, endpoint_id, rate_limit_bucket) → RuntimeCircuit[]`(只返回 `retry_at` 未过的)读;`RuntimeCircuit` DTO 字段 `scope/scope_id/opened_at/retry_at/ttl_seconds/reason_code/failure_count/message`,见 `apps/studio/backend/app/services/llm_health_store.py:14-101`。**存储介质 SQLite 路径由 ③a 注入**,store 逻辑本身 ③b。 |
| **probe 结果 DTO（③b 公共契约）** | `ProbeResult`(探测结果契约,字段权威源 `registry/schema.py:386`,经 `registry/__init__.py:170` 导出给诊断/SSOT 侧)。执行期 `_generate` 消费的是前置探问的裁决 `probe_call_settings(...)`(`call/pre_call_probe.py:84`);对外发起的**独立**探测(端点/路由/问题集)住 gateway `probing` 域,结果作为诊断/证据流进 [[08-orch-test-status-ssot]]。 |
| **fallback event（③b 公共,归 13）** | `emit_llm_fallback_event` 入 `LLMFallbackEvent`{ `phase_name`, from/to provider, reason, code, context(含 from/to route 诊断 + fallback decision + provider status code + runtime settings) }。callback 异常被吞,不掩盖运行时错误。 |
| **错误** | route 全失败 → `AllProvidersFailedError`(payload 来自累积的 failure records,异常类归 13,`exceptions.py:33-60`);invoke fail-fast 异常 → 透传抛出(前置探问的拒绝不再走这条路,它是问题不是故障,见 F3)。 |
| **归属 / 稳定性** | `RuntimePolicy`/`ProbeResult` 字段权威源 = [[04-orch-registry-schema]](`registry/schema.py`);`classify_exception` 状态码语义权威源 = [[06-orch-error-classification]];本模块**只链接不复制**,防 drift。 |

---

## 功能逐项（每个功能为索引）

### F1 fallback 循环（`_generate` 编排外壳 + 异常分类驱动 + 编排/调用分离）

- **机制/数据流**：
  - `GatewayChatModel._generate`（③b 编排外壳,fallback 链主循环）是保留的编排外壳;MVP1 不删除它,因为它承载 fallback/probe/熔断/usage/event,现状入口在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:96-271`,决策 D1（否决 A、保留 `GatewayChatModel`)的完整理由 + PM 原话见本段下方决策。
  - `GatewayChatModel._generate` 的输入准备要交给调用层保真处理;MVP1 不再把 `BaseMessage` 先拍成 dict,因为现状 `_langchain_messages_to_dict`(把 LangChain 消息转成 provider dict 的函数)位于 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:661-692`,它属于 09 的调用层问题(也是空-content bug 根源)。
  - `GatewayChatModel._generate` 继续按 `ResolvedRole.routes` 顺序遍历 fallback 链;`ResolvedRole`(resolver 输出的角色运行时结构)字段定义在 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-456`。
  - `classify_exception`（运行时异常分类入口,把 HTTP 状态码/异常映射成 fallback / fail-fast / retry）继续作为执行期错误分类入口;它把 retry/fallback 类 action 映射为 `fallback_allowed`,代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/resolve/error_classification.py:75-98`,真实状态码语义见 [[06-orch-error-classification]](本模块只消费结果,不复制状态码表)。这是 fallback 循环对每条 route 失败(probe-fail / invoke-fail)做"fallback 还是 fail-fast"分流的决策引擎。
  - Route invoke 步骤改成调用 09 的 ChatX 调用层;07 只要求它抛出的异常仍能进入 `classify_exception`,成功返回的 `AIMessage.usage_metadata`(ChatX 返回的 token 用量)能供 usage 归属使用(usage 归属落 F6),现状 usage 补记点在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:227-235`。
  - **编排 / 调用边界（M3 `_generate` 9 步逐步归属）**:留编排(2/3/4/6/8/9 步)= 遍历 / 熔断跳过 / probe / usage 记账 / 异常处理 / 全失败;改调用(1/5/7 步)= 消息准备(不再拍 dict)/ 实际调用(build ChatX + invoke)/ 构建结果(augment ChatX `AIMessage`),改的三步归 09。
- **决策 + 动机**：
  - **D1 — A' 保留 `GatewayChatModel`(否决激进版 A)**:`_generate` 里的 fallback、probe、熔断、异常分类、event 和 usage 都是 Gateway 自有语义;裸返回 ChatX 或 LangChain `with_fallbacks()` 不能表达按 route 状态码分类、probe、down TTL、usage 归属和 fallback event。**被否决的方案 A(激进版)**= "resolver 直接产原生 ChatX + 删 `GatewayChatModel` + 用 `with_fallbacks()`",它会回归 fallback / probe / 熔断 / usage / metadata / predict 全套能力;真机第八轮只验证了"调用层换 ChatX 修掉空-content bug",**从未验证"删编排层"**,且 `with_fallbacks()` 只能按异常类型分流、表达不了"按 HTTP status 分类"(对比 `error_classification.py`,状态码语义归 [[06-orch-error-classification]])。因此 A' = 不删编排外壳、不裸返回 ChatX,只把"每条 route 的实际调用"从自研消息转换换成原生 ChatX。**bug 根源在调用层(消息转换),不在编排层**:`_langchain_messages_to_dict`(把带 `tool_calls` 的 `AIMessage(content="")` 转成 `{"content":""}`)在 `call/chat_model.py:661-692`,再经 anthropic dispatch 发出空 content → qiniu-anthropic `400 content must not be empty`(改在调用层,归 [[09-inv-invocation-runtime]])。**PM 原话见本段下方**:"不用留A, 这是错误判断, 正确的是A'"。
  - **D2 — 编排 / 调用分离**:同一个 route 既可被 graph-agent 的 ChatX 调用层消费,也可被 copilot 的独立运行时消费(copilot 走 `claude_agent_sdk`,**不归 gateway 调**);编排层应该输出"该用哪条 route"的决策(`ResolvedRoute`:protocol / base_url / credential_ref / provider_model_id / runtime settings + fallback 顺序 + 熔断/probe 决策),调用层才负责真正 invoke(吃一条 `ResolvedRoute` + messages → 出 `AIMessage`)。落到 `_generate` 内即 M3 九步归属:留编排(遍历 / 熔断跳过 / probe / usage 记账 / 异常处理 / 全失败),改调用(消息准备 / 实际调用 / 构建结果,归 09)。**PM 原话见本段下方**:"你只要知道谁跟你说我现在要调copilot, 把copilot解析好的route给我, 你就给他, 就ok了...编排和调用是不是应该更模块化更内聚化, API写清楚"。
- **原话**：
  > **D1 否决 A、保留 `GatewayChatModel`**："不用留A, 这是错误判断, 正确的是A'。" → 不裸返回 ChatX、不删编排外壳,只换每条 route 的实际调用。
  > **D2 编排 / 调用分离**："你只要知道谁跟你说我现在要调copilot, 把copilot解析好的route给我, 你就给他, 就ok了, 这是调copilot的路径,你只负责输出编排结果, 不负责调用. 所以这里还引申出一个问题, 编排和调用是不是应该更模块化更内聚化, API写清楚, 编排输入什么输出什么. 调用输入什么输出什么"
- **测试点**：全失败 — 遍历尽所有 route → `AllProvidersFailedError`,payload 含累积 failure records。(异常分类的分类正确性单测见 F4 — 同 route 重试耗尽后的异常喂分类器 → fallback / fail-fast。)
- **status**：`_generate` 编排段已在(`call/chat_model.py:96-271`);MVP1 = 保留编排外壳、调用段换 ChatX(归 09)。
- **归属**：③b `packages/graph-agent-gateway`(`gateway_chat_model._generate` 编排段)；改的 1/5/7 三步(消息准备 / 实际调用 / 构建结果)跨 [[09-inv-invocation-runtime]];异常分类状态码语义跨 [[06-orch-error-classification]]。

### F2 circuit 熔断 TTL（mark_down + is_marked_down + 跳过）

- **机制/数据流**：
  - `_is_marked_down`（`_generate` 到健康状态管理器判断 route 是否仍在 down TTL 内的桥接函数）继续在每条 route 调用前跳过 down TTL 内的候选;现状代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:446-452`。
  - `LLMCircuitAndUsageLedger.is_provider_marked_down`（对外判断 route down TTL 的方法）继续保留为编排层接口;它当前委托 `_is_provider_marked_down` 检查进程内 `_provider_down_cache`(执行期 TTL 缓存),代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:53-61` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:340-350`。
  - `_mark_down`（`_generate` 到 `LLMCircuitAndUsageLedger.mark_provider_down` 的桥接函数）继续只在 fallback-eligible 失败后写 down 状态;现状代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:505-512`。
  - `LLMCircuitAndUsageLedger.mark_provider_down`（对外写入 route 熔断状态的方法）继续保留为编排层接口;它当前委托 `_mark_provider_down`,按 `RuntimePolicy.provider_down_ttl_seconds`(熔断窗口秒数)写过期时间,代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:123-132` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:352-368`。
- **决策 + 动机**：熔断态 route 在 invoke 前被 `continue` 跳过,不发起调用;mark_down 只在 fallback-eligible 失败后写,按 `RuntimePolicy.provider_down_ttl_seconds` 控制窗口。熔断持久化(跨进程)归 F9(本轮反转 ③b);此处是执行期 TTL 缓存层。
- **测试点**：**熔断跳过** — `is_provider_marked_down`==true 的 route → 在 invoke 前被 `continue` 跳过,**不发起调用**(回归点:熔断态 route 不应进 ChatX invoke)。
- **status**：`_is_marked_down` / `_mark_down` / 对应 client_manager 接口已在;保留为编排层接口。
- **归属**：③b `packages/graph-agent-gateway`(`ledger` 的熔断,已在)。

### F3 前置探问（正式请求构造器 + 1 token 预算 + base_url 归一化消费）

> **本节 2026-08-11 按新语义整体重写(台账 P6d)。** 旧标题是「F3 probe(1-token 真请求 + base_url 归一化消费)」,正文讲的是**探活**。改写不是换个名:探问的**问题本身**换了,连带判据、失败处理和归属都跟着换。旧文照录在本节末尾「原文与今天的差别」,不假装那段设计从来不存在。

- **机制/数据流**：
  - **问的是什么**:正式调用发出去之前,先用**这次调用自己的设置**朝同一条 route 问一句,只要 1 个 token,问「这条 route 收不收这些设置」。桥接住 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:309-320`:`probe_before_call`(默认 `True`,`call/chat_model.py:166`)为真时调 `call/pre_call_probe.py:probe_call_settings`。
  - **用什么问**:**探针 = 正式请求构造器 + 1 token 预算**。`CallSettings.as_cheap_question()`(`call/settings.py:133-144`)产出同一份设置、把预算换成 1、并摘掉 tools(工具不是设置,带上它问的是另一个问题,而这个问题的答案不该由工具背锅);模型仍由 `RouteChatModelFactory` 造,且**构造器由调用方注入**(`call/pre_call_probe.py:63-81` 的 `build_probe_model`,原文"The builder is handed in rather than made here: the probe and the call it precedes have to come off the same one")。因此探针发出去的那条请求,与紧随其后的正式调用**同源**——判据不是「代码里把设置传给了探针」,而是**成品 payload 同源**(决议判据 2)。
  - **拒绝意味着什么**:`packages/graph-agent-gateway/src/graph_agent_gateway/call/pre_call_probe.py:8-11` 原文——"A refusal here is not a route that is down. It is a question with a follow-up: ask again with the preferences dropped"。**被拒不写熔断、不换路、不判全体 provider 失败**;摘掉被拒的偏好继续用这条 route(决议 D2)。
  - **追问的阶梯(只在该追问时发生)**:第一问被拒 → 先看 `classify_exception(...).scope`(`call/pre_call_probe.py:100-105`),**不是 `request`**(凭据、模型不存在、限流、连不上)就直接收工——route 根本没读到设置,再问一遍是白花钱;**是 `request`** 才把偏好整层摘掉再问一次(`:109-113`),若还是被拒,说明这条 route 无论如何都拒,与设置无关,交回调用方自己的 route 处理;若摘掉后能答,才**一次只带一项**逐项点名(`:118-124`),且只问**这个协议的请求体里真的带得动**的项(`provider_request_keys`)——请求体里没位置的项,问出来的请求跟刚被接受的那条一模一样,答案也会一模一样。常规情况(全都接受)永远只有一问。
  - **超时不跟正式调用走**:`RuntimePolicy.probe_timeout_seconds`(默认 5s)按 `call/chat_model.py:318` 传进去——为省一次长调用而问的问题,不能自己耗得跟长调用一样久。
  - **它看不见什么**:1 个 token 的回答不足以观察「收下了但没照做」。那一档(`ignored`)归**答案收口时刻**判,不归探问(决议 D5,`call/pre_call_probe.py:14-16`)。
- **决策 + 动机**：
  - **前置探问的语义 = 问设置,不是探活**(决议 `docs/design/2026-08-10-runtime-settings-are-preferences-decision.md` D1/D2/D5)。动机是该决议 B2 的实测:一个参数写错,报出来的结论是「所有 provider 都失败了」——**它伪装成路由故障**,看报错的人根本不会想到去检查设置。路由健康与参数可接受性是两个维度,必须分开判。
  - **F1 — base_url 归一化(与 [[03-orch-credentials-endpoints]] 共享决策,重复留底防 drift)**:**决策 = 主路径在 credential 保存时归一化(每 endpoint 存确定的 canonical 格式,从源头保证对),副路径在调用时做幂等归一化双保险(已 canonical 则 no-op)**。每 protocol 规则确定统一:anthropic 去尾 `/v1`(SDK 自加 `/v1/messages`)、openai 保持、deepseek-anthropic 去 `/v1` 后 `+/anthropic`、ark openai-compat `.../api/v3`。本模块只在**前置探问要打到正确端点**上消费它;归一化的存写主体归 [[03-orch-credentials-endpoints]]、调用时双保险归 [[09-inv-invocation-runtime]] 的 `RouteChatModelFactory`。**重复 OK**:F1 是 03 / 07 / 09 共享决策,各模块都写、用双向模块链接防 drift。**PM 原话见本段下方**:"base_url 归一化的关键是每个protocol都有确定的统一的规则 ... 放在credential保存时归一化是最好的, 每个endpoint都有固定格式, 存这个固定格式保证不会出错"。
- **原话**：
  > **F1 base_url 归一化**(本模块关联前置探问要打对 base_url;归一化主体见 [[03-orch-credentials-endpoints]])："base_url 归一化的关键是每个protocol都有确定的统一的规则 ... 如果结果足够确定, 我觉得放在credential保存时归一化是最好的, 每个endpoint都有固定格式, 存这个固定格式保证不会出错"
- **测试点**：
  - **全都接受 → 只有一问**:route 收下这次调用的全部设置 → `ProbeVerdict(answers_without_them=True, refused=())`,不追问、不摘任何项。
  - **被拒且 scope 非 `request` → 不追问**:凭据/模型不存在/限流/连不上导致的拒绝,`answers_without_them=False` 且 `refused=()`,**只发出一问**;后续如何处置这条 route 交由调用方的 `classify_exception` 决定(`call/chat_model.py:320-330`)。
  - **被拒且摘掉偏好后能答 → 逐项点名**:`refused` 精确列出被拒的设置名,且只覆盖 `provider_request_keys(protocol)` 里带得动的项;调用**照常用这条 route 继续**,不 mark_down、不换路。
  - **摘掉偏好仍被拒 → 与设置无关**:`refused=()` 且带回 provider 原始异常(`refusal`),不把这笔账记到某个设置头上。
  - **探问超时独立**:探问用 `RuntimePolicy.probe_timeout_seconds`,不继承正式调用的超时。
- **status**：已落地并与本节一致。`probe_before_call` 默认 `True`(`call/chat_model.py:166`),前置探问仍在 invoke 前执行(`:309-320`),但走 `call/pre_call_probe.py`,与 `LLMCircuitAndUsageLedger` 无关——该类今天只剩熔断与 usage 两件事(`call/clients.py:17-126`,全类无 probe)。
- **原文与今天的差别(保留旧文,便于对照)**：
  - 旧文写「probe 是编排层自己发的 1-token 真请求,**用 client manager 的轻量 SDK client,不走 ChatX**」——**今天恰恰相反**:探针刻意复用生产同一个 `RouteChatModelFactory`,好让「探得通」和「跑得起来」不会各说各话;client manager 里那两份手搓请求构造器(openai 一份、anthropic 一份,写死 `max_tokens=1` 且不带用户任何设置)已删除。
  - 旧 `probe_provider`(及它委托的 `_probe_provider`)问的是「这条 route 活着吗」,失败即 `mark_provider_down`;**两个方法今天都不存在**。
  - 旧测试点写「probe 失败 → mark_down + 发 fallback event + 继续下一条 route」「probe 不可 fallback → 抛 `AllProvidersFailedError`」——**这两条按新语义都不成立**:拒绝不写熔断;是否换路、是否终止,由调用方拿 `classify_exception` 的结论决定,而不是由「探问失败」本身决定。
- **归属**：③b `packages/graph-agent-gateway`(前置探问住 `call/pre_call_probe.py`)；base_url 归一化存写主体跨 [[03-orch-credentials-endpoints]]、调用时双保险跨 [[09-inv-invocation-runtime]]。

### F4 retry（防抖动重试保留，由网关自己做并入账）

- **机制/数据流**：同 route 的防抖动重试由 `GatewayChatModel` 在它自己的 route 循环里做,
  次数与等待读 `RuntimePolicy.terminal_retry_policy.standard_runtime`
  (`max_attempts` 数的是**问了几次**,所以 2 次 = 允许重试一次;`backoff_ms` 是每两次之间的
  间隔,一格一个)。每重试一次发一条 `retried_same_route`;重试预算用尽后的异常才进
  `classify_exception` 决定跨 route fallback。**传输层一律 `max_retries=0`**
  (`call/factory.py` 的 `_TRANSPORT_RETRIES`,四种 protocol 都传)。
- **决策 + 动机**：
  - **F2 — 防抖动重试保留(PM 裁决,不变);2026-08-22 换层:由网关做,不由 ChatX 做。**
    PM 的要求是"防抖动重试可以留"(原话见下),这一条**没有改**:重试仍然有界、仍然只对
    429/5xx/连接、仍然尊重 `Retry-After`,一次瞬时 429 仍然不会把所有 route 连环跳废。
    改的是**谁来做**。F2 当年选择留在 ChatX 内,写下的理由是「**当前代码反而没有同-route
    重试**(SDK 显式 `max_retries=0`)」——**这个前提已经不成立**:`call/chat_model.py` 的
    route 循环在 `classification.action == "retry_same_route"` 时就会重试同一条路由,
    并且发 `retried_same_route`。于是留在 ChatX 内的那一层不再是"唯一的重试",而是
    **第二层看不见的重试**。
  - **换层的理由是「账」,不是"重试不好"。**(问题台账 E22,2026-08-22 实测)网关记的是
    **决定**;SDK 内部的重试不是它做的决定,所以记不下来。实测:假 provider 每组消息先答
    一次 500 再成功,wire 上五次 500 五次成功,而 run 的 `trace.jsonl` 里五条
    `llm_route_decision` **全是 `answered`**——读的人看到"这次很顺利",实际每次调用发了
    三个请求。根因是 `langchain_openai.ChatOpenAI` 的 `max_retries` 默认 `None`,不设就
    落到 openai SDK 的 `DEFAULT_MAX_RETRIES = 2`。**没人选过这个数**:网关自己的契约从写
    下那天起就说 `standard_runtime.max_attempts = 2`(= 只重试一次),而在跑的是 3;叠上
    网关自己那一次,一次调用最多可以发 6 个请求。挪到网关之后,"这条路由被问了几次"与
    "trace 上有几条 `retried_same_route`"**在构造上是同一个数**,这是两者唯一不会漂的
    办法。
  - **拿回来的时候要连 `Retry-After` 一起拿。** 那是 SDK 那一层做得比固定 backoff 好的
    地方——429 说了什么时候回来,只有 provider 知道桶什么时候满。所以
    `classify_exception` 顺手把它读出来(`retry_after_seconds`,只认秒数不认 HTTP 日期:
    日期要减本机时钟,时钟一偏"等 3 秒"就变成"等一小时"或"不等"),重试时取它与策略
    backoff 的**较大者**——provider 说 0 也不至于砸上去。
  - **「哪些失败可以重试」不进策略字段。** `StandardTerminalRetrySettings` 原本还有一个
    `retryable_status_codes`,与 `classify_exception` 的判断重复,而后者判得更多(连都没连
    上的失败根本没有状态码)。同一个问题两个答案必然漂,所以删掉字段、由分类器单独负责
    (SSOT)。同时删掉 `RuntimePolicy.terminal_retry_enabled`:开关与预算是同一件事的两种
    说法,而预算已经说了——`max_attempts=1` 就是"不重试";它此前默认 `false`、全仓无人读,
    真正在重试的是 SDK。
  - **没有跟着改的**:`sdk_runtime` / `sdk_probe` 的 `claude_code_max_retries` 仍然没有
    读它的地方。那是 SDK 终端(claude-code)的预算,与本条的标准终端是两种终端,单独处置。
- **原话**：
  > **F2 保留瞬时重试**："和Claude sdk copilot一样的问题, 防抖动重试可以留"
- **测试点**：`packages/graph-agent-gateway/tests/test_every_retry_is_on_the_books.py`
  ——trace 上的重试条数 == 路由被问的次数、预算来自策略而不是写死的一次、重试按
  `backoff_ms` 等待、provider 的 `Retry-After` 压过策略 backoff、`Retry-After` 是日期时
  退回策略 backoff、四种 protocol 建出来的 client 都是 `max_retries=0`。仍然钉死的老不变
  量:重试**耗尽后**抛出的异常仍能被 `classify_exception` 正确分类
  (`test_chatx_invocation_runtime.py`)。
- **status**：done(2026-08-22)。
- **归属**：③b `packages/graph-agent-gateway`(调用细节归 [[09-inv-invocation-runtime]])。

### F5 截断升级重试（`_call_with_token_escalation` 搬到编排层）

- **机制/数据流**：
  - 截断升级重试现由 **`_Attempt`（"One try at one route, and what is left to try with it"）** 承担,不再是一个包住 invoke 的 helper 函数:`packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:123-152` 定义 `budget`/`cap`/`escalations_left` 与 `can_escalate()`/`escalate()`,`_answer` 在 `:401-408` 判 `_is_truncated_response(response) and attempt.can_escalate()` 后升 budget 重试。**新增语义**:重试是**替换**而不是接续,所以重试前先 `attempt.void()`(`:139-148`)吐一个 `ANSWER_RESTARTED` 标记,否则流式消费方会把两次尝试拼成一条答案。budget 的初值与上限由 `call/settings.py` 的 `initial_budget`/`budget_cap`/`token_budget` 给(`:305-306`)。
  - `RuntimePolicy.token_escalation_rounds`（控制截断升级轮数的字段）继续控制截断升级轮数;该字段定义在 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:93-98`,MVP1 只是把消费位置从 client manager dispatch 外移到 `_generate` 的 route invoke 包装层。
- **决策 + 动机**：
  - **F3 — 截断升级重试保留 + 搬到编排层**:**决策 = 保留 token escalation,由编排层承担**。它不是某个 SDK 的消息转换能力,而是 Gateway 对"输出被截断"的运行时策略(error-handling 铁律第 7 条要求"截断必须自动重试");ChatX 自身不做这件事,所以它**不能随 `_call_*` 消息转换一起被删**。决策成立至今,只是落点变了:当年的 `_invoke_with_token_escalation` 已不存在,同一策略现由 `_Attempt` 在 `_answer` 循环里执行(`packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:123-152`、`:401-408`);消费的轮数字段 `RuntimePolicy.token_escalation_rounds` 在 `registry/schema.py:93-98`(字段权威源归 [[04-orch-registry-schema]])。
- **测试点**：**截断升级重试(F3)** — 遇截断 finish reason → 按 `token_escalation_rounds` 扩大 token budget 重试,且发生在**编排层**(包住 ChatX invoke),不随旧 `_call_*` 删除。
- **status**：截断升级已落地,现由 `_Attempt` 在 `_answer` 循环里执行(`call/chat_model.py:123-152`、`:401-408`;原文写的 `_invoke_with_token_escalation` 已不存在)。原文并列的 generic ordinary path `_call_with_token_escalation` 随 `call/dispatch.py` 一并已删(决议 D10-1);不用 LangChain 的消费方今天走 `call/plain.py:chat_plainly`,它复用同一条编排,因此也复用同一套截断升级。
- **归属**：③b `packages/graph-agent-gateway`;轮数字段权威源归 [[04-orch-registry-schema]]。

### F6 usage 归属（`record_usage` + metadata 注入）

- **机制/数据流**：`LLMCircuitAndUsageLedger.record_usage`（按 endpoint/provider 字符串累计 token 的方法）继续保留为编排/观测接口。现状累计函数在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:310-323`;其中 `AIMessage` 的 metadata 注入与 `_build_chat_result` 改动属调用层,落点归 [[09-inv-invocation-runtime]] F4/F5,本模块只负责把读到的 token 写进 `record_usage`。成功返回的 `AIMessage.usage_metadata`(ChatX 返回的 token 用量)供 usage 归属,现状 usage 补记点在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:227-235`。
- **决策 + 动机**：
  - **F5(usage / metadata)决策**:MVP1 的 usage 来源从旧 dict response 改为从 ChatX `AIMessage.usage_metadata` 取 token 喂 `record_usage`;并把 route_id / endpoint_id / canonical_id / protocol 注入 ChatX `AIMessage.response_metadata`(改 `_build_chat_result`);同时借 deerflow `stream_usage` 默认开,保证第三方 openai-compat 端点 usage 不为空。
- **测试点**：**usage 归属(F5)** — 成功响应从 ChatX `AIMessage.usage_metadata` 取 token 喂 `record_usage`;第三方 openai-compat 端点(借 `stream_usage` 默认开)usage 不为空。
- **status**：现先看 client manager 是否已记账、未记账再从 response dict 补记(`call/chat_model.py:191-235`)= target；改从 ChatX `AIMessage.usage_metadata` 取 usage,然后仍写入 `LLMCircuitAndUsageLedger.record_usage`。
- **归属**：③b `packages/graph-agent-gateway`(`record_usage` 累计)；`AIMessage` metadata 注入与 `_build_chat_result` 改动跨 [[09-inv-invocation-runtime]] F4/F5。

### F7 fallback event（`emit_llm_fallback_event` + `LLMFallbackEvent`）

- **机制/数据流**：
  - `emit_llm_fallback_event`（构造 fallback 事件并逐个 callback 发送的函数）继续由 `_generate` 在 fallback 分支调用;它会构造 `LLMFallbackEvent` 并逐个 callback 发送,且 callback 异常不掩盖运行时错误,代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/tracing.py:31-55`(事件 DTO/异常归 [[13-x-tracing-events-exceptions]])。
  - `LLMFallbackEvent`（fallback 事件 DTO,承载 from/to provider 诊断）继续承载 `phase_name`、from/to provider、reason、code 和 context;这个事件 DTO 定义在 `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:9-33`,`_generate` 当前填充 route diagnostics 的位置在 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:373-392`。
- **决策 + 动机**：fallback 分支发 event,event context 继续含 route diagnostics 和 runtime settings;callback 异常被吞,不掩盖运行时错误。事件 DTO / 异常类归 [[13-x-tracing-events-exceptions]],本模块只负责在 fallback 分支填充并发出。
- **测试点**：**fallback event payload** — event context 仍带 from/to route 诊断 + fallback decision + provider status code + runtime settings;callback 抛异常**不掩盖**运行时错误。
- **status**：`_generate` 已在 probe 和 invoke fallback 分支发 event(`call/chat_model.py:136-151`,`:250-265`)；保留,event context 继续含 route diagnostics 和 runtime settings。
- **归属**：③b `packages/graph-agent-gateway`(归 [[13-x-tracing-events-exceptions]])。

### F8 批量探测策略（多条 route 编排 probe）

- **机制/数据流**：对一批 route 编排 probe 的顺序 / 并发 / 跳过历史失败 / 优先历史成功,是 gateway 探测机制衍生的能力;现编排住 `routers/llm.py` 的探测段。执行期 fallback 链 probe(`_generate` 单条,见 F3)与批量探测编排(多条 job)是同一探测能力的两个入口。
- **决策 + 动机**：
  - **批量探测策略 = ③b 公共(边界说明)**:对一批 route 编排 probe 的顺序 / 并发 / 跳过历史失败 / 优先历史成功,是 gateway 探测机制衍生的能力,任何 app 都要;`module-disposition-revised.md:76` 下沉清单列"list-models 解析 + 批量探测编排"(现 `routers/llm.py` 探测编排)= ③b,只有"批量进度的 UI"留 ③a;ux-spec §6.0/§6.1 把"批量探测策略"列入 ③b 公共列(`00_settings-ux-spec.md:362`, `00_settings-ux-spec.md:370`, `00_settings-ux-spec.md:384`)。本模块 brief 已含 probe;此处补一句边界:执行期 fallback 链 probe(`_generate` 单条)与批量探测编排(多条 job)是同一探测能力的两个入口,都 ③b,UI/进度留 ③a。
  - 批量探测策略要把历史失败喂进下次编排(跳过历史失败、优先历史成功),这是 ③b 编排能力。
- **原话**：
  > **PM 探测结果全进 draft / 失败也是历史**(ux-spec §1.4,`00_settings-ux-spec.md:259`)："这几次的 endpoint / 模型探测结果(含失败)都要写进 draft / 证据库,不浪费(失败也是历史:哪些模型抖动 / 超时 / 不可用;下次免重探、喂蓝态)。" → 批量探测策略要把历史失败喂进下次编排(跳过历史失败、优先历史成功),这是 ③b 编排能力。
- **status**：现批量探测编排住 `routers/llm.py` 探测段(③a 位置)= target，**待下沉** ③b(进度 UI 留 ③a)。
- **归属**：③b 批量探测编排(现 `routers/llm.py` 探测段,**待下沉** ③b)；批量探测进度 UI / HTTP 包装(适配壳)留 ③a `apps/studio/backend`。

### F9 `health_store` 熔断持久化（本轮反转 ③b）

- **机制/数据流**：`SqliteLlmHealthStore` 把冷却事实跨进程存起来复用,`open_circuit` 写、`get_active_circuits` 读(只返回 `retry_at` 未过的),`RuntimeCircuit` DTO 字段见 `apps/studio/backend/app/services/llm_health_store.py:14-101`(契约详见模块级接口契约「熔断持久化」一行)。store 现状见 `apps/studio/backend/app/services/llm_health_store.py:26-124`。
- **决策 + 动机**：
  - **`llm_health_store`(熔断持久化)= ③b 公共内核(本轮反转)**:把冷却事实跨进程存起来复用,是 fallback/熔断机制的内在延伸,换 app 还要;**判据**:"换个 app 还原样能用吗?能=③b"(`module-disposition-revised.md:48` 07 health_store 新判定 = **③b 公共,下沉 gateway;存储介质留注入**)。**被反转**:原 baseline 的差异表与待办/疑点 #3 把它判作"③a seam / 执行期 down-cache 与该 store 是否合并是疑点"。现按判据已定 ③b 待下沉,SQLite 路径(存储介质,四件事之④)由 ③a 注入。
  - **`copilot_test`(copilot 假测试)= ③a 应用(copilot 专属)——这条判据当年是对的,而它要求的接线工程现已完工。** 原文记的状态是:它用 `AsyncAnthropic`(裸 Anthropic HTTP 客户端)发探测,而真实 copilot 跑 `ClaudeSDKClient`,绑死 copilot 的实际调用方式(四件事之③),不是通用 route probe;`module-disposition-revised.md:49` 07 行明确"③a 应用(copilot 专属),留 studio"。**今天 copilot 测试已按该判据改走真 SDK**:`apps/studio/backend/app/routers/llm.py:1734-1737` 注释"copilot's test走 copilot 自己的真实 ClaudeSDKClient 调用",入口 `_start_copilot_sdk_test_job`(`:2052`)。`copilot_test.py` 这个文件不在了,它自己的注释记着去向:`apps/studio/backend/app/services/model_probe.py:3-8`——"formerly named ``copilot_test``; provider probing has since moved to the gateway (``graph_agent_gateway.probing``)",只剩 `ModelProbeResult` 这个结果类型留在 studio。所以"与通用 route probe 不同源"今天以更彻底的方式成立:通用探测整个进了 gateway `probing` 域,copilot 测试走它自己的 SDK。
- **原话**：
  > **判据（本轮反转 `llm_health_store` 归属 + 钉死 `copilot_test` 留 ③a）**："换个 app 还原样能用吗?能=③b,不能=③a。"(ux-spec §6.0 判据铁律,`00_settings-ux-spec.md:342`, `00_settings-ux-spec.md:352`) → 熔断持久化是 fallback/熔断机制的跨进程延伸,任何调模型 app 都要 → **③b 公共**(原误判 ③a seam);`copilot_test` 绑死 copilot SDK 调用方式(四件事之③) → **③a 应用**。
- **测试点**：（熔断态 route 不进 ChatX invoke 的执行期回归在 F2；本段持久化层无独立执行期断言，验证落"下沉后与执行期 TTL 缓存合并为同一健康源"的工程任务，见 gaps。）
- **status**：`SqliteLlmHealthStore` 已能持久化 circuit(`apps/studio/backend/app/services/llm_health_store.py:26-124`)；**本轮反转**:从"③a seam / 是否打通是疑点"改判 **③b 公共,待下沉**;SQLite 路径留 ③a 注入。
- **归属**：③b(现 ③a 待下沉) — 熔断持久化内核 → gateway 包；存储介质 SQLite 路径注入留 ③a `apps/studio/backend`。

---

## gaps / 待设计

- **代码下沉**(后续工程,非本轮):`llm_health_store` 熔断持久化内核 → gateway 包(SQLite 路径留 ③a 注入);批量探测编排 → gateway 包(进度 UI 留 ③a)。
- **已落地**:ChatX 重试耗尽后抛出的核心异常形状已用确定性测试喂给 fallback loop / `classify_exception` 路径,覆盖 fake 401、wrapped network、400 non-capability 与真实 OpenAI SDK 401/400 error shape;分类器当前会沿异常链找 `status_code` 和 `response.status_code`,代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/resolve/error_classification.py:223-239`，测试见 `packages/graph-agent-gateway/tests/test_chatx_invocation_runtime.py`。
- **疑点(已不成立)**:原疑点记的是——ChatX 主路径 token escalation 包住 factory build + invoke、usage 在收到最终 `AIMessage` 后读一次;而 generic ordinary path 的 `_call_with_token_escalation` 每轮都 `_record_usage_from_result`(该文件已删)。**这条疑点已不成立**:原疑点问的是"ChatX 主路径与 generic ordinary path 两条路径的中间轮 usage 记账策略是否需要完全一致";今天只有一条路径,普通 chat 面复用它(决议 D10),留实现期定。
- **待办 / 反转后定调**:Studio 的 `SqliteLlmHealthStore` 与执行期 `LLMCircuitAndUsageLedger._provider_down_cache` 的关系——**判据已定二者都属 ③b**(一个是持久化、一个是执行期 TTL 缓存),下沉后应在 gateway 包内统一为同一运行时健康源;当前无源码连接,现状分别在 `apps/studio/backend/app/services/llm_health_store.py:26-124` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:49-52`。**注**:此项原 baseline 记作"疑点:二者是否合并",反转后已不是归属疑点(都 ③b),只剩"下沉后如何合并"的工程问题。
- **疑点(去重)已随代码消失**:原疑点是「`_probe_provider` 已 `_mark_provider_down`,`_generate` 的 `probe_ok=False` 分支又 `_mark_down` 一次」。两个探活函数都不存在了,现在的前置探问根本不写熔断状态(拒绝≠路由挂,见 F3),所以没有第二次 mark_down 可去重。熔断只由真实调用失败后的 `_mark_down` 写入(`packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:835-844`)。
- **疑点**:`LLMCircuitAndUsageLedger.is_provider_marked_down` 接收 `runtime_policy` 但当前立即 `del runtime_policy`,实际 TTL 判断只看已写入的过期时间;如果 MVP1 要让查询逻辑也感知 policy,需要实现任务另行处理,证据见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:53-61`。

## 交叉引用（双向链接，不复制）

- [[06-orch-error-classification]]:`classify_exception` 状态码语义权威源(本模块只消费 fallback/fail-fast/retry 结果)
- [[09-inv-invocation-runtime]]:真实 ChatX invoke / `_call_*` / 消息转换 / `_build_chat_result`(M3 第 1/5/7 步改动落点)
- [[13-x-tracing-events-exceptions]]:`LLMFallbackEvent` / `emit_llm_fallback_event` / `AllProvidersFailedError` payload
- [[04-orch-registry-schema]]:`RuntimePolicy` / `ProbeResult` 字段权威源(本模块只链接)
- [[08-orch-test-status-ssot]]:熔断持久化的 SSOT/投影视角 + 6 态(probe 结果作证据流)
- studio copilot（copilot-assist + ux-spec §3.8）:copilot 测试的应用侧消费方;真 `ClaudeSDKClient` 测试接线**已完工**(`apps/studio/backend/app/routers/llm.py:1734-1737`、`:2052`)
- [[03-orch-credentials-endpoints]]:F1 base_url 归一化的存写主体(本模块只在 probe 用对 base_url 上共享该决策,双向索引防 drift)
- client 层 A' 重设计决策(D1/D2/M2/M3/F2/F3/F5)完整逻辑 + PM 原话已逐功能留底(F1/F3/F4/F5/F6/F8/F9) · 归属反转源 `module-disposition-revised.md` 第 47-49 行

---

## 模块级证据附录

> 以下为模块级证据/索引(已实现 vs baseline 差异、覆盖代码、覆盖率、代码索引、决策原因反转留底),挂文末。逐功能的机制/决策/原话/测试已在「功能逐项」就地收齐,本附录只作整篇的证据汇总与 baseline 对账。

### 涉及 region / platform（整篇汇总；逐功能归属见各 F 段）

- **③b** `packages/graph-agent-gateway`:`gateway_chat_model._generate` 编排段(已在)、`client_manager` 的 probe/熔断/usage(已在)、`error_classification`(已在,归 06)、`tracing`/`events`/`exceptions`(已在,归 13)、`RuntimePolicy`/`ProbeResult` 契约(已在,归 04);`llm_health_store` 熔断持久化(**待下沉** ③b)、批量探测编排(现 `routers/llm.py` 探测段,**待下沉** ③b)。
- **③a** `apps/studio/backend`:copilot 测试(**留 ③a** 应用;接线工程已完工,现走真 `ClaudeSDKClient`,`routers/llm.py:2052`)、`llm_health_store` 的 SQLite 路径注入(存储介质)、批量探测进度 UI / HTTP 包装(适配壳)。
- **② Rust**:N/A(凭证/角色/健康数据永不 Rust)。

### 已实现 / 与 baseline 差异

| 能力 | baseline 已实现 | MVP1 差异 | 归属 |
|---|---|---|---|
| fallback 链 | `GatewayChatModel._generate` 已按 `resolved_role.routes` 遍历,见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:111-112`。 | 保留;只是把循环里的 `_dispatch` 换成 09 的 ChatX invoke。 | ③b |
| 熔断跳过 | `_is_marked_down` 已在每条 route 前执行,见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:113-114`。 | 保留;**接入 `SqliteLlmHealthStore` 不再是"是否打通"疑点——判据已定 store 属 ③b,下沉后统一健康源**,store 现状见 `apps/studio/backend/app/services/llm_health_store.py:26-124`。 | ③b(含 store) |
| probe | `_probe` 已在 invoke 前执行,并对 probe 失败发 fallback event,见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:115-189`。 | 保留;probe 仍用 client manager 的轻量 SDK/client path,不跟真实 ChatX invoke 绑定。 | ③b |
| 异常分类 | 调用前 probe 异常和真实调用异常都走 `classify_exception`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:124` 和 `:238`。 | 保留;ChatX 抛出的 provider/HTTP 异常要继续被分类器识别(状态码语义归 06)。 | ③b |
| fallback event | `_generate` 已在 probe 和 invoke fallback 分支发 event,见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:136-151` 和 `:250-265`。 | 保留;event context 继续含 route diagnostics 和 runtime settings。 | ③b(归 13) |
| 同 route retry | (2026-08-22 起 = target)网关自己重试:`call/chat_model.py` 的 `_RetryBudget` 读 `terminal_retry_policy.standard_runtime`,每次重试发一条 `retried_same_route`;传输层四种 protocol 一律 `max_retries=0`(`call/factory.py` 的 `_TRANSPORT_RETRIES`)。 | 保留(见 F4);跨 route fallback 仍由 route 循环管。 | ③b(调用细节归 09) |
| 截断升级 | 由 `_Attempt` 在 `_answer` 循环里执行,见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:123-152` 与 `:401-408`;重试前 `void()` 作废已吐出的片段。 | 决策(保留该策略、归编排层)不变;当年那两个 helper 函数已不存在。 | ③b |
| usage 归属 | 当前先看 client manager 是否已记账,未记账再从 response dict 补记,见 `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:191-235`。 | 改从 ChatX `AIMessage.usage_metadata` 取 usage,然后仍写入 `LLMCircuitAndUsageLedger.record_usage`。 | ③b |
| 熔断持久化 | `SqliteLlmHealthStore` 已能持久化 circuit,见 `apps/studio/backend/app/services/llm_health_store.py:26-124`。 | **本轮反转**:从"③a seam / 是否打通是疑点"改判 **③b 公共,待下沉**;SQLite 路径留 ③a 注入。 | ③b(现 ③a 待下沉) |
| copilot 假测试 | `copilot_test.py` 已不存在。判据要求的接线工程已完工:copilot 测试走真 `ClaudeSDKClient`(`apps/studio/backend/app/routers/llm.py:1734-1737`、`:2052`);通用探测进了 gateway `probing` 域;studio 只留结果类型 `ModelProbeResult`(`apps/studio/backend/app/services/model_probe.py:18`)与官方 call-method 探测 `_probe_official_call_method`(`apps/studio/backend/app/routers/llm.py:1490`)。 | 判据不变(③a 应用,绑 SDK 调用方式),**状态由「待接线」改「已接线」**。 | ③a |

### 决策原因（保留 baseline 原文,补反转）

client 层 A' 重设计的四条决策(D1 保留 `GatewayChatModel`、D2 编排/调用分离、F2 保留 ChatX 瞬时重试、F3 截断升级重试搬家)的**完整逻辑 + PM 原话**已就地留底在「功能逐项」(F1 收 D1/D2、F4 收 F2、F5 收 F3),不再外链——A' 否决激进版 A、编排与调用分离、撤回 `max_retries=0`、截断升级重试从 client_manager dispatch 搬到编排层包住 ChatX invoke,逐条理由与 PM verbatim 见对应功能段。

**判据反转(2026-06 第四轮)**:`llm_health_store` 从"③a seam / 合并是疑点"反转为"③b 公共内核 / 待下沉",`copilot_test` 钉死"③a 应用 / 留 studio",批量探测策略明确"③b 公共 / UI 进度留 ③a";权威源 ux-spec §6.0 + 归属表 `module-disposition-revised.md:47-49` 与 `module-disposition-revised.md:76`。

### 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:111-189`:MVP1 保留的 route 遍历、熔断跳过、probe 和 probe fallback 分支(③b)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:237-265`:MVP1 保留的 invoke 异常分类、mark_down 和 fallback event 分支(③b)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:53-76`:MVP1 保留的 health/probe 对外接口(③b)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py:68-77`:MVP1 保留的 mark_down 对外接口(③b)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py:545-587`:ChatX 主路径的截断升级重试 helper(③b)。
- (已删) `call/dispatch.py:_call_with_token_escalation`:原 generic ordinary path 的截断升级重试 helper(③b,调用层兜底路径)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:88-98`:MVP1 继续消费的 `RuntimePolicy`(字段权威源归 04)。
- `apps/studio/backend/app/services/llm_health_store.py:26-124`:熔断持久化 SQLite store——**本轮反转判 ③b 待下沉**(存储介质 SQLite 路径留 ③a 注入)。
- `apps/studio/backend/app/services/model_probe.py:18`(`ModelProbeResult`)+ `apps/studio/backend/app/routers/llm.py:1490`(`_probe_official_call_method`):`copilot_test.py` 拆解后留在 studio 的两块——**= ③a 应用**(绑 SDK 调用方式),不是 `_generate` 的执行期 fallback loop。`_probe_model` 已随通用探测一起进 gateway `probing` 域。

### 覆盖率

本 alignment 覆盖 07 brief 的全部要求:`GatewayChatModel._generate` 的编排步骤、截断升级重试、`LLMCircuitAndUsageLedger` 的 `is_provider_marked_down` / `mark_provider_down` / `record_usage`、`registry/schema.py` 的 `ProbeResult`、copilot 测试留在 studio 的两块、`services/llm_health_store.py` 均已落到真实 `file:line`(2026-08-11 路径回写:`probe_provider`/`_probe`/`_invoke_with_token_escalation`/`copilot_test.py` 已不存在,相应段落改写并标注取代关系),并补齐三处判据归属(health_store 反转 ③b、copilot_test 钉 ③a、批量探测 ③b)。调用层 ordinary `_call_*`、消息转换和 `_build_chat_result` 不在本篇展开,交给 [[09-inv-invocation-runtime]]。
