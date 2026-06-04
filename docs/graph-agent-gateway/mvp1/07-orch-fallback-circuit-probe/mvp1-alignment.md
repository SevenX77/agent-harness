---
module: 07-orch-fallback-circuit-probe
doc: mvp1-alignment
status: drafted
verified_at: 2026-06-02
---

# 07 — Fallback / Circuit / Probe（编排外壳:回退链·熔断·探活）· MVP1 设计

> **组织方式**：**以每个功能为索引** —— 每个功能(F1–F9)一段，把它的机制/数据流·决策+动机·原话·测试点·status·归属(region/platform)**全收在自己段里**；仅「定义」「接口契约」是模块级总览，证据附录(已实现/差异、覆盖代码/覆盖率、代码索引、决策原因反转)挂在文末模块级。现状基线见同目录 `baseline.md`。
> **Tier**：③b gateway 公共能力内核（`gateway_chat_model._generate` 编排外壳 + `client_manager` probe/熔断/usage 已在包内；`llm_health_store` 熔断持久化现散 ③a 待下沉）
> **Owns**：fallback 链遍历 + 熔断跳过 + 1-token probe + 异常分类 + mark_down + fallback event + usage 归属 + 截断升级重试 + 批量探测策略；**每条 route 的真实 ChatX invoke 不在本模块**（归 [[09-inv-invocation-runtime]]）
> **Status**：设计定稿（2026-06 判据第四轮反转）；代码 = `_generate` 编排段保留、调用段换 ChatX(归 09)、`_call_with_token_escalation` 待从调用层搬上编排层、`llm_health_store` 待下沉 ③b
> **Related**：[[06-orch-error-classification]]（`classify_exception` 状态码语义权威源，本模块只消费）· [[09-inv-invocation-runtime]]（真实 invoke / `_call_*` / 消息转换 / F4 thinking / F5 metadata 注入落点）· [[13-x-tracing-events-exceptions]]（`LLMFallbackEvent` / `emit_llm_fallback_event` / `AllProvidersFailedError`）· [[04-orch-registry-schema]]（`RuntimePolicy` / `ProbeResult` 字段权威源）· [[03-orch-credentials-endpoints]]（F1 base_url 归一化共享决策的存写主体，probe 用对 base_url）· [[08-orch-test-status-ssot]]（熔断持久化的另一消费视角 + 6 态投影）· studio copilot（copilot-assist + ux-spec §3.8）（copilot 假测试 `copilot_test` 的应用侧消费方）
> **决策日志**：client 层 A' 重设计决策（D1 A' / D2 编排-调用分离 / M2 client_manager 5 件事 / M3 `_generate` 逐步归属 / F2 retry / F3 截断升级 / F5 usage）的完整逻辑 + PM 原话已就地留底在下文各功能段（F1 收 D1/D2、F3 收 base_url、F4 收 F2 retry、F5 收 F3 截断、F6 收 F5 usage、F8 收批量探测、F9 收熔断持久化反转）；归属反转源 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（07 行三处反转）
> **现状**：见同目录 `baseline.md`

## 定义

MVP1 目标:`GatewayChatModel._generate`（LangChain 调用进入 Gateway 后执行 fallback 链的主循环）继续作为**编排外壳**,只把「每条 route 的实际调用」从自研消息转换换成原生 langchain ChatX,编排语义一条不丢。

本模块按判据全部落在 **③b gateway 公共能力内核**,只有少量明确划归 ③a 的应用加工:

- **fallback 链遍历 / 熔断跳过 / probe / 异常分类 / mark_down / fallback event / usage 归属 / 截断升级重试** = **③b 公共**（gateway 机制本身衍生,任何调模型 app 装上就有,已在 `gateway_chat_model.py` + `client_manager.py`）。
- **熔断持久化 `llm_health_store`(把冷却事实跨进程存起来)** = **③b 公共内核**（**本轮反转**:原 baseline 判它「③a seam / 是否打通是疑点」,现按判据已定 ③b 待下沉;存储介质 SQLite 路径由 ③a 注入）。
- **批量探测策略(对一批 route 编排 probe 的顺序/并发/跳过历史失败)** = **③b 公共**（探测编排是 gateway 机制,现编排住 `routers/llm.py` 的探测段,只有"批量进度 UI"留 ③a）。
- **`copilot_test`(copilot 假测试探针)** = **③a 应用**（copilot 专属,与 ③b 通用 route probe 不同源,留 studio;详见 F9 归属 + F8 边界 + 文末决策原因，应用侧消费方 = studio copilot（copilot-assist + ux-spec §3.8））。

不调真实模型(真实 invoke 归 [[09-inv-invocation-runtime]]);probe 例外——它是**编排层自己**发的 1-token 真请求,用 client manager 的轻量 SDK client,不走 ChatX。本文只写文档目标,不改代码。

**上下游(全模块总览)**:① resolver 输出 `ResolvedRole`(有序 `ResolvedRoute` + `runtime_policy`)→ **`_generate`(③b 编排外壳)** 按 routes 顺序遍历 → 每条候选先 熔断跳过 / probe → 选中后委派 **[[09-inv-invocation-runtime]] 的 ChatX invoke(③b 调用层)** 真调 → 成功则归 usage + 注 route metadata 返回;失败则 `classify_exception`(③b 错误分类,归 06)决定 fallback / fail-fast,fallback 则 mark_down + 发 fallback event + 继续下一条 → 全失败抛 `AllProvidersFailedError`。

**状态机（route 进入实际调用的判定,目标语义）**:候选 →〔熔断查询:`is_provider_marked_down`==true → `continue` 跳过〕→〔`probe_before_call`==true → 1-token 探活:`classify_exception` 不可 fallback → 抛;probe 失败可 fallback → mark_down + event + 继续;probe 通过 → 进调用〕→〔ChatX invoke:成功 → 归 usage + metadata 返回;异常 → `classify_exception`:fail-fast → 抛;可 fallback → mark_down + event + 继续〕→ 遍历尽 → `AllProvidersFailedError`。

**编排 / 调用边界（M3 `_generate` 9 步逐步归属,逐步表见 F1 与 F1 D2 决策)**:留编排(2/3/4/6/8/9 步)= 遍历 / 熔断跳过 / probe / usage 记账 / 异常处理 / 全失败;改调用(1/5/7 步)= 消息准备(不再拍 dict)/ 实际调用(build ChatX + invoke)/ 构建结果(augment ChatX `AIMessage`),改的三步归 09。

## 接口契约

> 跨边界签名 / 输入输出 / 错误 / 归属（模块级，跨功能共享）。`_generate` 内部各桥接函数(`_is_marked_down`/`_probe`/`_mark_down`)是同进程编排细节,不在此列;此处只钉编排外壳对上(resolver)、对下(09 调用层 / `client_manager` 健康接口)、对侧(tracing / health store)的契约。

| 边界 | 契约 |
|---|---|
| **resolver → `_generate`（入参）** | `ResolvedRole`{ `routes`: `ResolvedRoute[]`（有序 fallback 链）, `runtime_policy`: `RuntimePolicy`（down TTL / probe timeout / `token_escalation_rounds`,字段权威源 `registry/schema.py:88-98`）}。`_generate` **看得到**"有序候选 + 运行时策略"(通用编排概念),**看不到**"角色怎么被 UI 编辑 / 怎么排序出来"(③a 应用加工 + 02 materialize)。 |
| **`_generate` → 09 调用层（每条 route）** | 入:一条 `ResolvedRoute` + 原始 `BaseMessage[]`(不拍 dict) + runtime params;出:ChatX `AIMessage`(含 `usage_metadata` + 注入的 route metadata) 或抛异常。**契约要求**:① 抛出的异常形状能被 `classify_exception` 沿异常链找到 `status_code`/`response.status_code`;② 成功 `AIMessage.usage_metadata` 非空可喂 usage 归属;③ thinking content blocks 不被拍平(归 09 F4)。 |
| **`_generate` → `client_manager`（健康/probe/usage,③b 公共接口）** | `is_provider_marked_down(endpoint_id, provider_model_id) → bool`、`probe_provider(...) → bool`(可选带 `credential_provider`)、`mark_provider_down(..., runtime_policy)`、`record_usage(endpoint_id, prompt/completion/total tokens)`。这四个是 M2 拆解里**保留的**②③④(probe / 熔断 / usage),签名见 `client_manager.py:53-132,:310-323`。 |
| **熔断持久化（③b 公共,现 ③a 待下沉）** | `SqliteLlmHealthStore.open_circuit(scope, scope_id, retry_at, reason_code, ...)` 写、`get_active_circuits(route_id, endpoint_id, rate_limit_bucket) → RuntimeCircuit[]`(只返回 `retry_at` 未过的)读;`RuntimeCircuit` DTO 字段 `scope/scope_id/opened_at/retry_at/ttl_seconds/reason_code/failure_count/message`,见 `apps/studio/backend/app/services/llm_health_store.py:14-101`。**存储介质 SQLite 路径由 ③a 注入**,store 逻辑本身 ③b。 |
| **probe 结果 DTO（③b 公共契约）** | `ProbeResult`(1-token 探测结果契约,字段权威源 `registry/schema.py:320-329`,经 `registry/probe_contracts.py` 重导出给诊断/SSOT 侧)。执行期 `_generate` 只消费 boolean probe/fallback 结果;探测结果作为诊断/证据流的一部分进 [[08-orch-test-status-ssot]]。 |
| **fallback event（③b 公共,归 13）** | `emit_llm_fallback_event` 入 `LLMFallbackEvent`{ `phase_name`, from/to provider, reason, code, context(含 from/to route 诊断 + fallback decision + provider status code + runtime settings) }。callback 异常被吞,不掩盖运行时错误。 |
| **错误** | route 全失败 → `AllProvidersFailedError`(payload 来自累积的 failure records,异常类归 13,`exceptions.py:33-60`);probe 不可 fallback 异常 / invoke fail-fast 异常 → 透传抛出。 |
| **归属 / 稳定性** | `RuntimePolicy`/`ProbeResult` 字段权威源 = [[04-orch-registry-schema]](`registry/schema.py`);`classify_exception` 状态码语义权威源 = [[06-orch-error-classification]];本模块**只链接不复制**,防 drift。 |

---

## 功能逐项（每个功能为索引）

### F1 fallback 循环（`_generate` 编排外壳 + 异常分类驱动 + 编排/调用分离）

- **机制/数据流**：
  - `GatewayChatModel._generate`（③b 编排外壳,fallback 链主循环）是保留的编排外壳;MVP1 不删除它,因为它承载 fallback/probe/熔断/usage/event,现状入口在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:96-271`,决策 D1（否决 A、保留 `GatewayChatModel`)的完整理由 + PM 原话见本段下方决策。
  - `GatewayChatModel._generate` 的输入准备要交给调用层保真处理;MVP1 不再把 `BaseMessage` 先拍成 dict,因为现状 `_langchain_messages_to_dict`(把 LangChain 消息转成 provider dict 的函数)位于 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:661-692`,它属于 09 的调用层问题(也是空-content bug 根源)。
  - `GatewayChatModel._generate` 继续按 `ResolvedRole.routes` 顺序遍历 fallback 链;`ResolvedRole`(resolver 输出的角色运行时结构)字段定义在 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-456`。
  - `classify_exception`（运行时异常分类入口,把 HTTP 状态码/异常映射成 fallback / fail-fast / retry）继续作为执行期错误分类入口;它把 retry/fallback 类 action 映射为 `fallback_allowed`,代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/error_classification.py:75-98`,真实状态码语义见 [[06-orch-error-classification]](本模块只消费结果,不复制状态码表)。这是 fallback 循环对每条 route 失败(probe-fail / invoke-fail)做"fallback 还是 fail-fast"分流的决策引擎。
  - Route invoke 步骤改成调用 09 的 ChatX 调用层;07 只要求它抛出的异常仍能进入 `classify_exception`,成功返回的 `AIMessage.usage_metadata`(ChatX 返回的 token 用量)能供 usage 归属使用(usage 归属落 F6),现状 usage 补记点在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:227-235`。
  - **编排 / 调用边界（M3 `_generate` 9 步逐步归属）**:留编排(2/3/4/6/8/9 步)= 遍历 / 熔断跳过 / probe / usage 记账 / 异常处理 / 全失败;改调用(1/5/7 步)= 消息准备(不再拍 dict)/ 实际调用(build ChatX + invoke)/ 构建结果(augment ChatX `AIMessage`),改的三步归 09。
- **决策 + 动机**：
  - **D1 — A' 保留 `GatewayChatModel`(否决激进版 A)**:`_generate` 里的 fallback、probe、熔断、异常分类、event 和 usage 都是 Gateway 自有语义;裸返回 ChatX 或 LangChain `with_fallbacks()` 不能表达按 route 状态码分类、probe、down TTL、usage 归属和 fallback event。**被否决的方案 A(激进版)**= "resolver 直接产原生 ChatX + 删 `GatewayChatModel` + 用 `with_fallbacks()`",它会回归 fallback / probe / 熔断 / usage / metadata / predict 全套能力;真机第八轮只验证了"调用层换 ChatX 修掉空-content bug",**从未验证"删编排层"**,且 `with_fallbacks()` 只能按异常类型分流、表达不了"按 HTTP status 分类"(对比 `error_classification.py`,状态码语义归 [[06-orch-error-classification]])。因此 A' = 不删编排外壳、不裸返回 ChatX,只把"每条 route 的实际调用"从自研消息转换换成原生 ChatX。**bug 根源在调用层(消息转换),不在编排层**:`_langchain_messages_to_dict`(把带 `tool_calls` 的 `AIMessage(content="")` 转成 `{"content":""}`)在 `gateway_chat_model.py:661-692`,再经 anthropic dispatch 发出空 content → qiniu-anthropic `400 content must not be empty`(改在调用层,归 [[09-inv-invocation-runtime]])。**PM 原话见本段下方**:"不用留A, 这是错误判断, 正确的是A'"。
  - **D2 — 编排 / 调用分离**:同一个 route 既可被 graph-agent 的 ChatX 调用层消费,也可被 copilot 的独立运行时消费(copilot 走 `claude_agent_sdk`,**不归 gateway 调**);编排层应该输出"该用哪条 route"的决策(`ResolvedRoute`:protocol / base_url / credential_ref / provider_model_id / runtime settings + fallback 顺序 + 熔断/probe 决策),调用层才负责真正 invoke(吃一条 `ResolvedRoute` + messages → 出 `AIMessage`)。落到 `_generate` 内即 M3 九步归属:留编排(遍历 / 熔断跳过 / probe / usage 记账 / 异常处理 / 全失败),改调用(消息准备 / 实际调用 / 构建结果,归 09)。**PM 原话见本段下方**:"你只要知道谁跟你说我现在要调copilot, 把copilot解析好的route给我, 你就给他, 就ok了...编排和调用是不是应该更模块化更内聚化, API写清楚"。
- **原话**：
  > **D1 否决 A、保留 `GatewayChatModel`**："不用留A, 这是错误判断, 正确的是A'。" → 不裸返回 ChatX、不删编排外壳,只换每条 route 的实际调用。
  > **D2 编排 / 调用分离**："你只要知道谁跟你说我现在要调copilot, 把copilot解析好的route给我, 你就给他, 就ok了, 这是调copilot的路径,你只负责输出编排结果, 不负责调用. 所以这里还引申出一个问题, 编排和调用是不是应该更模块化更内聚化, API写清楚, 编排输入什么输出什么. 调用输入什么输出什么"
- **测试点**：全失败 — 遍历尽所有 route → `AllProvidersFailedError`,payload 含累积 failure records。(异常分类的分类正确性单测见 F4 — 同 route 重试耗尽后的异常喂分类器 → fallback / fail-fast。)
- **status**：`_generate` 编排段已在(`gateway_chat_model.py:96-271`);MVP1 = 保留编排外壳、调用段换 ChatX(归 09)。
- **归属**：③b `packages/graph-agent-gateway`(`gateway_chat_model._generate` 编排段)；改的 1/5/7 三步(消息准备 / 实际调用 / 构建结果)跨 [[09-inv-invocation-runtime]];异常分类状态码语义跨 [[06-orch-error-classification]]。

### F2 circuit 熔断 TTL（mark_down + is_marked_down + 跳过）

- **机制/数据流**：
  - `_is_marked_down`（`_generate` 到健康状态管理器判断 route 是否仍在 down TTL 内的桥接函数）继续在每条 route 调用前跳过 down TTL 内的候选;现状代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:446-452`。
  - `LLMClientManager.is_provider_marked_down`（对外判断 route down TTL 的方法）继续保留为编排层接口;它当前委托 `_is_provider_marked_down` 检查进程内 `_provider_down_cache`(执行期 TTL 缓存),代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:53-61` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:340-350`。
  - `_mark_down`（`_generate` 到 `LLMClientManager.mark_provider_down` 的桥接函数）继续只在 fallback-eligible 失败后写 down 状态;现状代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:505-512`。
  - `LLMClientManager.mark_provider_down`（对外写入 route 熔断状态的方法）继续保留为编排层接口;它当前委托 `_mark_provider_down`,按 `RuntimePolicy.provider_down_ttl_seconds`(熔断窗口秒数)写过期时间,代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:123-132` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:352-368`。
- **决策 + 动机**：熔断态 route 在 invoke 前被 `continue` 跳过,不发起调用;mark_down 只在 fallback-eligible 失败后写,按 `RuntimePolicy.provider_down_ttl_seconds` 控制窗口。熔断持久化(跨进程)归 F9(本轮反转 ③b);此处是执行期 TTL 缓存层。
- **测试点**：**熔断跳过** — `is_provider_marked_down`==true 的 route → 在 invoke 前被 `continue` 跳过,**不发起调用**(回归点:熔断态 route 不应进 ChatX invoke)。
- **status**：`_is_marked_down` / `_mark_down` / 对应 client_manager 接口已在;保留为编排层接口。
- **归属**：③b `packages/graph-agent-gateway`(`client_manager` 的熔断,已在)。

### F3 probe（1-token 真请求 + base_url 归一化消费）

- **机制/数据流**：
  - `_probe`（`_generate` 到 `LLMClientManager.probe_provider` 的桥接函数）继续在真实 invoke 前按 policy 做 1-token 探活;现状代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:455-472`。
  - `LLMClientManager.probe_provider`（对外执行 route 探活的方法）继续保留为编排层接口;它当前委托 `_probe_provider`,后者对 OpenAI-compatible 发 `chat.completions.create(..., max_tokens=1, temperature=0)`、对 Anthropic-compatible 发 `messages.create(..., max_tokens=1)`,代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:63-76` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:370-438`。
  - probe 是**编排层自己**发的 1-token 真请求,用 client manager 的轻量 SDK client,不走 ChatX。
- **决策 + 动机**：
  - **F1 — base_url 归一化(与 [[03-orch-credentials-endpoints]] 共享决策,重复留底防 drift)**:**决策 = 主路径在 credential 保存时归一化(每 endpoint 存确定的 canonical 格式,从源头保证对),副路径在调用时做幂等归一化双保险(已 canonical 则 no-op)**。每 protocol 规则确定统一:anthropic 去尾 `/v1`(SDK 自加 `/v1/messages`)、openai 保持、deepseek-anthropic 去 `/v1` 后 `+/anthropic`、ark openai-compat `.../api/v3`。本模块只在 **probe 用对 base_url** 上消费它(`_probe` 发 1-token 请求要打到正确端点);归一化的存写主体归 [[03-orch-credentials-endpoints]]、调用时双保险归 [[09-inv-invocation-runtime]] 的 `RouteChatModelFactory`。**重复 OK**:F1 是 03 / 07 / 09 共享决策,各模块都写、用 `[[link]]` 双向索引防 drift。**PM 原话见本段下方**:"base_url 归一化的关键是每个protocol都有确定的统一的规则 ... 放在credential保存时归一化是最好的, 每个endpoint都有固定格式, 存这个固定格式保证不会出错"。
- **原话**：
  > **F1 base_url 归一化**(本模块关联 probe 用对 base_url;归一化主体见 [[03-orch-credentials-endpoints]])："base_url 归一化的关键是每个protocol都有确定的统一的规则 ... 如果结果足够确定, 我觉得放在credential保存时归一化是最好的, 每个endpoint都有固定格式, 存这个固定格式保证不会出错"
- **测试点**：
  - **probe 失败 → fallback**:`probe_before_call`==true 且 probe 抛可 fallback 异常 → mark_down + 发 fallback event + 继续下一条 route(不崩在 probe 上)。
  - **probe 不可 fallback → 抛**:probe 异常经 `classify_exception` 判 fail-fast → 立即抛 `AllProvidersFailedError`,不继续遍历。
- **status**：`_probe` / `probe_provider` 已在 invoke 前执行,对 probe 失败发 fallback event;保留,probe 仍用 client manager 的轻量 SDK/client path,不跟真实 ChatX invoke 绑定。
- **归属**：③b `packages/graph-agent-gateway`(`client_manager` 的 probe,已在)；base_url 归一化存写主体跨 [[03-orch-credentials-endpoints]]、调用时双保险跨 [[09-inv-invocation-runtime]]。

### F4 retry（保留 ChatX 瞬时重试，撤回 `max_retries=0`）

- **机制/数据流**：ChatX 瞬时重试保留在同 route invoke 内;`GatewayChatModel._generate` 只在 ChatX 重试耗尽后接收最终异常并决定跨 route fallback。**注**(F2 撤回 `max_retries=0`):ChatX 只对 429/5xx/连接重试、对 429 尊重 Retry-After、不对 400/401 重试,天然是"同 route 防抖动重试";现状 SDK `max_retries=0`(`client_manager.py:171,:206`)反而会把瞬时 429 直接升级成跨 route 跳转。
- **决策 + 动机**：
  - **F2 — 保留 ChatX 瞬时重试(撤回 `max_retries=0`)**:**决策 = 保留 ChatX 的瞬时重试(有界,如默认 2),不设 0**。理由:ChatX 只对 429/5xx/连接重试、对 429 尊重 `Retry-After`、不对 400/401 重试 → 天然就是"同 route 防抖动重试",与网关"跨 route fallback"是**两层、不冲突**;当前代码反而**没有同-route 重试**(SDK 显式 `max_retries=0`,`client_manager.py:171,:206`),一次瞬时 429 会被 `_generate` 当 `fallback_allowed`(`gateway_chat_model.py:237-249`)直接跳 route,把所有 route 连环跳废。唯一要钉死的不变量:ChatX 重试**耗尽后**抛出的异常仍能被 `classify_exception` 正确分类(确定性单测)。**PM 原话见本段下方**:"和Claude sdk copilot一样的问题, 防抖动重试可以留"。
- **原话**：
  > **F2 保留瞬时重试**："和Claude sdk copilot一样的问题, 防抖动重试可以留"
- **测试点**：**ChatX 瞬时重试(F2)** — 同 route 瞬时 429/5xx → ChatX 内重试(有界,非 0),**重试耗尽后**的异常才进 `classify_exception` 决定跨 route fallback;关键确定性单测:fake 401 / 400 / 网络错喂分类器 → 分别 fallback / fail-fast / fallback(状态码语义见 06)。
- **status**：现 OpenAI/Anthropic client `max_retries=0`(`client_manager.py:171`,`:205`)= target；改为保留 ChatX 默认有界瞬时重试,跨 route fallback 仍由 `_generate` 管。
- **归属**：③b `packages/graph-agent-gateway`(调用细节归 [[09-inv-invocation-runtime]])。

### F5 截断升级重试（`_call_with_token_escalation` 搬到编排层）

- **机制/数据流**：
  - `_call_with_token_escalation`（遇到截断 finish reason 时扩大 token budget 重试的函数）的策略要从旧调用层搬到编排层;它的用途是遇到截断 finish reason 时扩大 token budget 重试,现状代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:990-1012`,搬家原因:它是跨调用的运行时策略(对应 error-handling 铁律第 7 条"截断必须自动重试"),不是某个 SDK 的消息转换,ChatX 自身不做这件事,不能随 `_call_*` 一起删。
  - `RuntimePolicy.token_escalation_rounds`（控制截断升级轮数的字段）继续控制截断升级轮数;该字段定义在 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:93-98`,MVP1 只是把消费位置从 client manager dispatch 外移到 `_generate` 的 route invoke 包装层。
- **决策 + 动机**：
  - **F3 — 截断升级重试保留 + 搬到编排层**:**决策 = 保留 `_call_with_token_escalation`,但从 client_manager dispatch 搬到编排层,包在 ChatX invoke 外**。它不是某个 SDK 的消息转换能力,而是 Gateway 对"输出被截断"的运行时策略(error-handling 铁律第 7 条要求"截断必须自动重试");ChatX 自身不做这件事,所以它**不能随 `_call_*` 消息转换一起被删**——必须显式搬家。现状函数在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:990-1012`,消费的轮数字段 `RuntimePolicy.token_escalation_rounds` 在 `registry/schema.py:93-98`(字段权威源归 [[04-orch-registry-schema]])。
- **测试点**：**截断升级重试(F3)** — 遇截断 finish reason → 按 `token_escalation_rounds` 扩大 token budget 重试,且发生在**编排层**(包住 ChatX invoke),不随旧 `_call_*` 删除。
- **status**：现 `_call_with_token_escalation` 在 client manager dispatch 内部(`client_manager.py:983-1012`)= target；移到编排层,包住每条 ChatX invoke,避免随 `_call_*` 一起删除。
- **归属**：③b `packages/graph-agent-gateway`;轮数字段权威源归 [[04-orch-registry-schema]]。

### F6 usage 归属（`record_usage` + metadata 注入）

- **机制/数据流**：`LLMClientManager.record_usage`（按 endpoint/provider 字符串累计 token 的方法）继续保留为编排/观测接口。现状累计函数在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:310-323`;其中 `AIMessage` 的 metadata 注入与 `_build_chat_result` 改动属调用层,落点归 [[09-inv-invocation-runtime]] F4/F5,本模块只负责把读到的 token 写进 `record_usage`。成功返回的 `AIMessage.usage_metadata`(ChatX 返回的 token 用量)供 usage 归属,现状 usage 补记点在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:227-235`。
- **决策 + 动机**：
  - **F5(usage / metadata)决策**:MVP1 的 usage 来源从旧 dict response 改为从 ChatX `AIMessage.usage_metadata` 取 token 喂 `record_usage`;并把 route_id / endpoint_id / canonical_id / protocol 注入 ChatX `AIMessage.response_metadata`(改 `_build_chat_result`);同时借 deerflow `stream_usage` 默认开,保证第三方 openai-compat 端点 usage 不为空。
- **测试点**：**usage 归属(F5)** — 成功响应从 ChatX `AIMessage.usage_metadata` 取 token 喂 `record_usage`;第三方 openai-compat 端点(借 `stream_usage` 默认开)usage 不为空。
- **status**：现先看 client manager 是否已记账、未记账再从 response dict 补记(`gateway_chat_model.py:191-235`)= target；改从 ChatX `AIMessage.usage_metadata` 取 usage,然后仍写入 `LLMClientManager.record_usage`。
- **归属**：③b `packages/graph-agent-gateway`(`record_usage` 累计)；`AIMessage` metadata 注入与 `_build_chat_result` 改动跨 [[09-inv-invocation-runtime]] F4/F5。

### F7 fallback event（`emit_llm_fallback_event` + `LLMFallbackEvent`）

- **机制/数据流**：
  - `emit_llm_fallback_event`（构造 fallback 事件并逐个 callback 发送的函数）继续由 `_generate` 在 fallback 分支调用;它会构造 `LLMFallbackEvent` 并逐个 callback 发送,且 callback 异常不掩盖运行时错误,代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:33-59`(事件 DTO/异常归 [[13-x-tracing-events-exceptions]])。
  - `LLMFallbackEvent`（fallback 事件 DTO,承载 from/to provider 诊断）继续承载 `phase_name`、from/to provider、reason、code 和 context;这个事件 DTO 定义在 `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:9-33`,`_generate` 当前填充 route diagnostics 的位置在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:373-392`。
- **决策 + 动机**：fallback 分支发 event,event context 继续含 route diagnostics 和 runtime settings;callback 异常被吞,不掩盖运行时错误。事件 DTO / 异常类归 [[13-x-tracing-events-exceptions]],本模块只负责在 fallback 分支填充并发出。
- **测试点**：**fallback event payload** — event context 仍带 from/to route 诊断 + fallback decision + provider status code + runtime settings;callback 抛异常**不掩盖**运行时错误。
- **status**：`_generate` 已在 probe 和 invoke fallback 分支发 event(`gateway_chat_model.py:136-151`,`:250-265`)；保留,event context 继续含 route diagnostics 和 runtime settings。
- **归属**：③b `packages/graph-agent-gateway`(归 [[13-x-tracing-events-exceptions]])。

### F8 批量探测策略（多条 route 编排 probe）

- **机制/数据流**：对一批 route 编排 probe 的顺序 / 并发 / 跳过历史失败 / 优先历史成功,是 gateway 探测机制衍生的能力;现编排住 `routers/llm.py` 的探测段。执行期 fallback 链 probe(`_generate` 单条,见 F3)与批量探测编排(多条 job)是同一探测能力的两个入口。
- **决策 + 动机**：
  - **批量探测策略 = ③b 公共(边界说明)**:对一批 route 编排 probe 的顺序 / 并发 / 跳过历史失败 / 优先历史成功,是 gateway 探测机制衍生的能力,任何 app 都要;`module-disposition-revised.md:66` 下沉清单列"list-models 解析 + 批量探测编排"(现 `routers/llm.py` 探测编排)= ③b,只有"批量进度的 UI"留 ③a;ux-spec §6.4 横切表(`00_settings-ux-spec.md:452`)也把"批量探测策略"列入 ③b 公共列。本模块 brief 已含 probe;此处补一句边界:执行期 fallback 链 probe(`_generate` 单条)与批量探测编排(多条 job)是同一探测能力的两个入口,都 ③b,UI/进度留 ③a。
  - 批量探测策略要把历史失败喂进下次编排(跳过历史失败、优先历史成功),这是 ③b 编排能力。
- **原话**：
  > **PM 探测结果全进 draft / 失败也是历史**(ux-spec §1.4 #2.4,`00_settings-ux-spec.md:70`)："这几次的 endpoint / 模型探测结果(含失败)都要写进 draft / 证据库,不浪费(失败也是历史:哪些模型抖动 / 超时 / 不可用;下次免重探、喂蓝态)。" → 批量探测策略要把历史失败喂进下次编排(跳过历史失败、优先历史成功),这是 ③b 编排能力。
- **status**：现批量探测编排住 `routers/llm.py` 探测段(③a 位置)= target，**待下沉** ③b(进度 UI 留 ③a)。
- **归属**：③b 批量探测编排(现 `routers/llm.py` 探测段,**待下沉** ③b)；批量探测进度 UI / HTTP 包装(适配壳)留 ③a `apps/studio/backend`。

### F9 `health_store` 熔断持久化（本轮反转 ③b）

- **机制/数据流**：`SqliteLlmHealthStore` 把冷却事实跨进程存起来复用,`open_circuit` 写、`get_active_circuits` 读(只返回 `retry_at` 未过的),`RuntimeCircuit` DTO 字段见 `apps/studio/backend/app/services/llm_health_store.py:14-101`(契约详见模块级接口契约「熔断持久化」一行)。store 现状见 `apps/studio/backend/app/services/llm_health_store.py:26-124`。
- **决策 + 动机**：
  - **`llm_health_store`(熔断持久化)= ③b 公共内核(本轮反转)**:把冷却事实跨进程存起来复用,是 fallback/熔断机制的内在延伸,换 app 还要;**判据**:"换个 app 还原样能用吗?能=③b"(`module-disposition-revised.md:38` 07 行新判定 = **③b 公共,下沉 gateway;存储介质留注入**)。**被反转**:原 baseline `Baseline/Alignment 差异` 与 `待办/疑点 #3` 把它判作"③a seam / 执行期 down-cache 与该 store 是否合并是疑点"(`07/baseline.md:75,:100`)。现按判据已定 ③b 待下沉,SQLite 路径(存储介质,四件事之④)由 ③a 注入。
  - **`copilot_test`(copilot 假测试)= ③a 应用(copilot 专属)**:它用 `AsyncAnthropic`(裸 Anthropic HTTP 客户端)发探测,而真实 copilot 跑 `ClaudeSDKClient`,绑死的是 copilot 的实际调用方式(四件事之③),不是通用 route probe;`module-disposition-revised.md:39` 07 行明确"③a 应用(copilot 专属),留 studio"。它与 ③b 的 `LLMClientManager.probe_provider`(通用 1-token route probe)**不同源**:前者是 copilot 接线工程的对象(假测试要改走真 `ClaudeSDKClient`,见 studio copilot 页 / ux-spec §3.4),后者是 fallback 链里的执行期探活。baseline 覆盖代码表已含 `copilot_test` 三个对象,本轮只**补归属标注**,内容不删。
- **原话**：
  > **判据（本轮反转 `llm_health_store` 归属 + 钉死 `copilot_test` 留 ③a）**："换个 app 还原样能用吗?能=③b,不能=③a。"(ux-spec §6.0 判据铁律,`00_settings-ux-spec.md:334`) → 熔断持久化是 fallback/熔断机制的跨进程延伸,任何调模型 app 都要 → **③b 公共**(原误判 ③a seam);`copilot_test` 绑死 copilot SDK 调用方式(四件事之③) → **③a 应用**。
- **测试点**：（熔断态 route 不进 ChatX invoke 的执行期回归在 F2；本段持久化层无独立执行期断言，验证落"下沉后与执行期 TTL 缓存合并为同一健康源"的工程任务，见 gaps。）
- **status**：`SqliteLlmHealthStore` 已能持久化 circuit(`apps/studio/backend/app/services/llm_health_store.py:26-124`)；**本轮反转**:从"③a seam / 是否打通是疑点"改判 **③b 公共,待下沉**;SQLite 路径留 ③a 注入。
- **归属**：③b(现 ③a 待下沉) — 熔断持久化内核 → gateway 包；存储介质 SQLite 路径注入留 ③a `apps/studio/backend`。

---

## gaps / 待设计

- **代码下沉**(后续工程,非本轮):`llm_health_store` 熔断持久化内核 → gateway 包(SQLite 路径留 ③a 注入);批量探测编排 → gateway 包(进度 UI 留 ③a)。
- **待办**:ChatX 重试耗尽后抛出的异常形状必须用确定性测试喂给 `classify_exception`;分类器当前会沿异常链找 `status_code` 和 `response.status_code`,代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/error_classification.py:223-239`。
- **待办**:截断升级重试搬到 `_generate` 后,需要定义它包住的是"ChatX invoke + usage 读取"还是只包住 invoke;现状 `_call_with_token_escalation` 每轮都会 `_record_usage_from_result`(每轮记一次账),代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:1003-1006`。
- **待办 / 反转后定调**:Studio 的 `SqliteLlmHealthStore` 与执行期 `LLMClientManager._provider_down_cache` 的关系——**判据已定二者都属 ③b**(一个是持久化、一个是执行期 TTL 缓存),下沉后应在 gateway 包内统一为同一运行时健康源;当前无源码连接,现状分别在 `apps/studio/backend/app/services/llm_health_store.py:26-124` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:49-52`。**注**:此项原 baseline 记作"疑点:二者是否合并",反转后已不是归属疑点(都 ③b),只剩"下沉后如何合并"的工程问题。
- **疑点(去重,实现期定)**:`_probe_provider` 在可 fallback 异常时已经 `_mark_provider_down` 并返回 false,`_generate` 的 `probe_ok=False` 分支又 `_mark_down` 一次;当前只是覆盖同一个 TTL key,是否需要去重由实现任务决定,证据见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:407-410` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:168-173`。
- **疑点**:`LLMClientManager.is_provider_marked_down` 接收 `runtime_policy` 但当前立即 `del runtime_policy`,实际 TTL 判断只看已写入的过期时间;如果 MVP1 要让查询逻辑也感知 policy,需要实现任务另行处理,证据见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:53-61`。

## 交叉引用（双向 [[link]]，不复制）

- [[06-orch-error-classification]]:`classify_exception` 状态码语义权威源(本模块只消费 fallback/fail-fast/retry 结果)
- [[09-inv-invocation-runtime]]:真实 ChatX invoke / `_call_*` / 消息转换 / `_build_chat_result`(M3 第 1/5/7 步改动落点)
- [[13-x-tracing-events-exceptions]]:`LLMFallbackEvent` / `emit_llm_fallback_event` / `AllProvidersFailedError` payload
- [[04-orch-registry-schema]]:`RuntimePolicy` / `ProbeResult` 字段权威源(本模块只链接)
- [[08-orch-test-status-ssot]]:熔断持久化的 SSOT/投影视角 + 6 态(probe 结果作证据流)
- studio copilot（copilot-assist + ux-spec §3.8）:`copilot_test` 假测试的应用侧消费方 + 真 `ClaudeSDKClient` 测试接线
- [[03-orch-credentials-endpoints]]:F1 base_url 归一化的存写主体(本模块只在 probe 用对 base_url 上共享该决策,双向索引防 drift)
- client 层 A' 重设计决策(D1/D2/M2/M3/F2/F3/F5)完整逻辑 + PM 原话已逐功能留底(F1/F3/F4/F5/F6/F8/F9) · 归属反转源 `module-disposition-revised.md`(07 行三处反转)

---

## 模块级证据附录

> 以下为模块级证据/索引(已实现 vs baseline 差异、覆盖代码、覆盖率、代码索引、决策原因反转留底),挂文末。逐功能的机制/决策/原话/测试已在「功能逐项」就地收齐,本附录只作整篇的证据汇总与 baseline 对账。

### 涉及 region / platform（整篇汇总；逐功能归属见各 F 段）

- **③b** `packages/graph-agent-gateway`:`gateway_chat_model._generate` 编排段(已在)、`client_manager` 的 probe/熔断/usage(已在)、`error_classification`(已在,归 06)、`tracing`/`events`/`exceptions`(已在,归 13)、`RuntimePolicy`/`ProbeResult` 契约(已在,归 04);`llm_health_store` 熔断持久化(**待下沉** ③b)、批量探测编排(现 `routers/llm.py` 探测段,**待下沉** ③b)。
- **③a** `apps/studio/backend`:`copilot_test`(copilot 假测试,**留 ③a** 应用,copilot 接线工程对象)、`llm_health_store` 的 SQLite 路径注入(存储介质)、批量探测进度 UI / HTTP 包装(适配壳)。
- **② Rust**:N/A(凭证/角色/健康数据永不 Rust)。

### 已实现 / 与 baseline 差异

| 能力 | baseline 已实现 | MVP1 差异 | 归属 |
|---|---|---|---|
| fallback 链 | `GatewayChatModel._generate` 已按 `resolved_role.routes` 遍历,见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:111-112`。 | 保留;只是把循环里的 `_dispatch` 换成 09 的 ChatX invoke。 | ③b |
| 熔断跳过 | `_is_marked_down` 已在每条 route 前执行,见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:113-114`。 | 保留;**接入 `SqliteLlmHealthStore` 不再是"是否打通"疑点——判据已定 store 属 ③b,下沉后统一健康源**,store 现状见 `apps/studio/backend/app/services/llm_health_store.py:26-124`。 | ③b(含 store) |
| probe | `_probe` 已在 invoke 前执行,并对 probe 失败发 fallback event,见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:115-189`。 | 保留;probe 仍用 client manager 的轻量 SDK/client path,不跟真实 ChatX invoke 绑定。 | ③b |
| 异常分类 | 调用前 probe 异常和真实调用异常都走 `classify_exception`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:124` 和 `:238`。 | 保留;ChatX 抛出的 provider/HTTP 异常要继续被分类器识别(状态码语义归 06)。 | ③b |
| fallback event | `_generate` 已在 probe 和 invoke fallback 分支发 event,见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:136-151` 和 `:250-265`。 | 保留;event context 继续含 route diagnostics 和 runtime settings。 | ③b(归 13) |
| 同 route retry | 当前 OpenAI/Anthropic client `max_retries=0`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:171` 和 `:205`。 | 改为保留 ChatX 默认有界瞬时重试;跨 route fallback 仍由 `_generate` 管。 | ③b(调用细节归 09) |
| 截断升级 | 当前 `_call_with_token_escalation` 在 client manager dispatch 内部,见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:983-1012`。 | 移到编排层,包住每条 ChatX invoke,避免随 `_call_*` 一起删除。 | ③b |
| usage 归属 | 当前先看 client manager 是否已记账,未记账再从 response dict 补记,见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:191-235`。 | 改从 ChatX `AIMessage.usage_metadata` 取 usage,然后仍写入 `LLMClientManager.record_usage`。 | ③b |
| 熔断持久化 | `SqliteLlmHealthStore` 已能持久化 circuit,见 `apps/studio/backend/app/services/llm_health_store.py:26-124`。 | **本轮反转**:从"③a seam / 是否打通是疑点"改判 **③b 公共,待下沉**;SQLite 路径留 ③a 注入。 | ③b(现 ③a 待下沉) |
| copilot 假测试 | `ModelProbeResult`/`_probe_model`/`_probe_official_call_method` 在 `copilot_test.py`,见 `apps/studio/backend/app/services/copilot_test.py:47-204`。 | **补归属标注**:= ③a 应用(copilot 专属,绑 SDK 调用方式),与 ③b route probe 不同源;接线工程改走真 `ClaudeSDKClient`(见 12)。 | ③a |

### 决策原因（保留 baseline 原文,补反转）

client 层 A' 重设计的四条决策(D1 保留 `GatewayChatModel`、D2 编排/调用分离、F2 保留 ChatX 瞬时重试、F3 截断升级重试搬家)的**完整逻辑 + PM 原话**已就地留底在「功能逐项」(F1 收 D1/D2、F4 收 F2、F5 收 F3),不再外链——A' 否决激进版 A、编排与调用分离、撤回 `max_retries=0`、截断升级重试从 client_manager dispatch 搬到编排层包住 ChatX invoke,逐条理由与 PM verbatim 见对应功能段。

**判据反转(2026-06 第四轮)**:`llm_health_store` 从"③a seam / 合并是疑点"反转为"③b 公共内核 / 待下沉",`copilot_test` 钉死"③a 应用 / 留 studio",批量探测策略明确"③b 公共 / UI 进度留 ③a";权威源 ux-spec §6.0 + 归属表 `module-disposition-revised.md:37-39,:66`。

### 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:111-189`:MVP1 保留的 route 遍历、熔断跳过、probe 和 probe fallback 分支(③b)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:237-265`:MVP1 保留的 invoke 异常分类、mark_down 和 fallback event 分支(③b)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:53-76`:MVP1 保留的 health/probe 对外接口(③b)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:123-132`:MVP1 保留的 mark_down 对外接口(③b)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:990-1012`:MVP1 要搬家到编排层的截断升级重试函数(③b)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:88-98`:MVP1 继续消费的 `RuntimePolicy`(字段权威源归 04)。
- `apps/studio/backend/app/services/llm_health_store.py:26-124`:熔断持久化 SQLite store——**本轮反转判 ③b 待下沉**(存储介质 SQLite 路径留 ③a 注入)。
- `apps/studio/backend/app/services/copilot_test.py:47-204`:Studio copilot 假测试探针(`ModelProbeResult`/`_probe_model`/`_probe_official_call_method`)——**= ③a 应用**(copilot 专属,绑 SDK 调用方式),不是 `_generate` 的执行期 fallback loop。

### 覆盖率

本 alignment 覆盖 07 brief 的全部要求:`GatewayChatModel._generate` 的编排步骤、`LLMClientManager` 的 `probe_provider` / `is_provider_marked_down` / `mark_provider_down`、`registry/probe_contracts.py`、`services/copilot_test.py`、`services/llm_health_store.py` 均已落到真实 `file:line`,并补齐三处判据归属(health_store 反转 ③b、copilot_test 钉 ③a、批量探测 ③b)。调用层 `_call_*`、消息转换和 `_build_chat_result` 不在本篇展开,交给 [[09-inv-invocation-runtime]]。
