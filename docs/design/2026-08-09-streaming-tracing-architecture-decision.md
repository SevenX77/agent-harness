# 流式 tracing 架构(决议)

- 日期:2026-08-09
- 状态:已批准。PM 对本文件 §2 的 D1–D8 八条逐条答复「全部接受」。交付闸门:S1 与 S2 完成后由实施者自评效果,无问题则直接推进 S3–S5,不需再次审批。
- 权威设计源:`packages/graph-agent/src/graph_agent/callbacks/events.py`(引擎事件契约)、
  `packages/graph-agent/src/graph_agent/core/llm_provider.py`(引擎 LLM Port 契约)、
  `docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md`、
  `docs/studio/mvp1/01_workflows/04_run-and-verify.md` §C/§D、
  `AGENTS.md` 的「Three-Module Architecture」「Development Principles」「Coding Standards」三节
- 前置决议:`docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md`
  (Trace 信息架构 + 步骤流式呈现 + run 目录布局)。本决议**取代**该决议 §4「明确不做」的第一条
  「LLM 输出逐 token 流式」;该决议的 D1–D14、§4 其余条目、§5 其余处置**全部保持有效**。
- 范围:`packages/graph-agent`(engine)、`apps/studio/backend`、`apps/studio/frontend` 三处。
  **不含** `packages/graph-agent-gateway`(gateway)。

---

## 0. 术语

本决议全篇只用下列三个名字指代下列三样东西,不另造代称。

- **步骤帧(step event)**:描述「一个步骤开始了 / 一个步骤结束了」的事件。它低频、数量有界,
  因此可以持久化到磁盘、可以回放、可以作为取证材料、可以拿来做统计。
  引擎今天的全部 37 种 `CallbackEvent` 都属于这一类(见 B1)。
- **增量帧(delta)**:描述「一个**正在进行中**的步骤又产出了一小段内容」的帧,
  典型形态是模型逐 token 吐字。它高频、数量无界,并且只对「此刻正在观看这次运行的观众」有意义 ——
  运行结束之后再回头看,增量帧不提供步骤帧没有的信息。
- **Port / Adapter**:Port 是平台无关的稳定接口,规定「引擎需要对方提供什么能力」;
  Adapter 是这个接口的具体实现,负责把某个 provider、某个操作系统、某个网络协议的差异挡在引擎核心之外。
  引擎核心只依赖 Port,不依赖任何 Adapter。

---

## 1. 背景:已核实的事实

以下每条都以代码坐标坐实,不含推测。行号对应 2026-08-09 的 `main`。

### B1. 引擎事件契约现有 37 种,全部是步骤帧

`packages/graph-agent/src/graph_agent/callbacks/events.py` 中 `CallbackEvent` 判别联合共 **37** 个变体,
包含 2026-08-09 由 PR #655 新增的 `ToolCallStartedEvent`。
这 37 种描述的都是「某件事开始了」或「某件事结束了」,没有任何一种描述「某件事正在进行中又产出了一小段」。
换句话说:**引擎的事件契约今天只能表达步骤帧,不能表达增量帧。**

### B2. 流式能力不是缺失,是在三层被逐层丢弃

这是本决议最重要的事实。底层的模型客户端本来就会流式吐字,能力在向上传递的过程中被主动放弃了三次:

- **Studio adapter 层丢弃**:`apps/studio/backend/app/core/adapters/engine.py:378`
  ```
              result = model._generate(
                  request.messages,
                  stop=metadata.get("stop"),
              )
  ```
  这里的 `model` 是 `_GatewayBackedLLMProvider.invoke` 内由 gateway resolver 解析得到的
  **真正的 LangChain chat model**。LangChain 的 `BaseChatModel` 原生具备 `_stream` / `_astream`
  两个流式出口,而此处调用的是 `_generate` —— 一次性把全量响应取回来。**能力在这一行被主动放弃。**

- **引擎 Port 层无法表达**:`packages/graph-agent/src/graph_agent/core/llm_provider.py:47-49`
  ```
  class LLMProvider(Protocol):
      def invoke(self, request: LLMProviderRequest) -> LLMProviderResponse:
          ...
  ```
  Port `LLMProvider` 是一个 Protocol,只有一个同步方法 `invoke`,返回一个完整响应对象。
  **契约层面就没有"分多次返回"这个概念**,因此即使下层 Adapter 拿到了流,也无处交付。

- **图执行层不流式**:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:2079`
  ```
                  result = agent_graph.invoke(
  ```
  图的执行走 `invoke(...)` —— 同步的整体调用,等全部跑完一次性返回,
  而不是 `.stream()` / `.astream()` 那种边跑边往外交付的形态。

### B3. 引擎侧不存在任何真实 provider 流式

在 `packages/graph-agent/src/graph_agent/` 全域搜索 `astream` / `stream=True` / `.stream(`,
唯一命中是 `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:77` 的 `_astream`。
那是 predict 功能的拦截桩(用于在 predict 时截住调用并给出预演结果),不是真实 provider 的流。
结论:**今天没有任何一条真实的模型流数据进入引擎。**

### B4. 步骤帧今天不只喂 UI,还是四件东西的真相来源

任何「把事件降级为纯粹的流式产物」的方案都会同时切断以下四条链路:

- **运行报告 `report.md`**:`apps/studio/backend/app/services/run_report.py:161`
  按 `event_type == "tool_call"` 累加工具调用计数,`:320` 按同一事件类型统计各工具的调用次数。
- **有界取证查询**:`apps/studio/backend/app/services/run_trace_query.py:99`
  按 phase 累加 LLM 调用数与工具调用数(并在同处按 `tool_name != "finish_task"` 区分驳回原因),
  `:140` 把 `tool_call` 事件投影成查询结果字段。
- **画布节点状态**:`apps/studio/frontend/src/components/studio/node-status.ts:100` 的
  `deriveNodeStatuses` —— 画布上每个节点显示 running / success / failed,
  完全由事件流推导得出(函数内按 `event.event_type` 分支,最后一条 `run_ended` 的判定赢)。
- **token 与工具调用统计**:`packages/graph-agent/src/graph_agent/callbacks/metrics.py:48` 的
  `on_llm_call` 累加输入/输出 token,`:61` 的 `on_tool_call` 累加工具调用总数。

### B5. 一条事件今天的完整旅程,以及增量帧若走同一条路要付的五处代价

一条引擎事件从产生到抵达前端,今天经过下列环节:

1. `apps/studio/backend/app/services/run_manager.py:102-104` —— `_queue_event_subscriber`
   把每条引擎事件 `model_dump(mode="json")` 序列化后 `process_queue.put({"type": "event", ...})`,
   **跨进程**送出。
2. `run_manager.py:513-514` —— 运行确实在子进程中执行:
   `self.process_factory: Any = multiprocessing.Process` / `self.queue_factory: Any = multiprocessing.Queue`。
3. `run_manager.py:1219` —— 父进程侧
   `message = await asyncio.to_thread(record.process_queue.get, True, 0.1)`,
   **每一条消息付一次线程跳转**。
4. `run_manager.py:1232` —— `seq=len(record.events) + 1`:每条事件被追加进 `record.events`
   (进程内一个无上限的列表)并**占用一个序号**。
5. `run_manager.py:1515-1527` —— `_events_after_cursor` 以 seq 实现断线重连游标;
   请求的序号低于可用下界抛 `StreamCursorExpiredError`(`:1525`),高于上界抛 `StreamCursorGapError`(`:1527`)。

另有一条落盘路径:`packages/graph-agent/src/graph_agent/callbacks/tracing.py:101-111` 的
`_write_typed_event` 把每条事件逐行写入 `trace.jsonl`。

因此,**如果让增量帧走步骤帧这同一条路**,同一份代价会在五处同时付出:
跨进程序列化与传输一次、线程跳转一次、无界内存列表增长一格、消耗一个 seq 序号、磁盘多写一行;
并且断线重连时,游标机制要求把每一个 token 逐个重放一遍才能补齐序号连续性。

### B6. 仓内已有一条成熟的流式实现可作范式

`apps/studio/backend/app/models/copilot.py` 定义了 Copilot 的 WebSocket 流式事件模型:
`:55` `thinking_delta`(推理增量)、`:60` `text_delta`(正文增量)、`:64` 起的
`CopilotEventToolUseStart`(`:73` `tool_use_start`)、以及配对的 `:81` `tool_use_result`。
它跑在 Claude Agent SDK 上,是「步骤开始 / 增量 / 步骤结束」三段式在本仓的**已运行实证** ——
本决议要建立的分层,在同一个仓里已有一份可参照的工作实现。

### B7. 工具步骤的开始信号刚刚补齐,并留下一个已知缺口

2026-08-09 合入的 PR #655 为引擎新增了 `ToolCallStartedEvent`,
并给 `ToolCallEvent` 加了必填字段 `tool_call_id` 作为两者的配对键。
发射点审计结论:只有 `packages/graph-agent/src/graph_agent/middleware/tracing.py` 发出开始事件
(它包裹工具执行,握有「即将开始」这一时刻);
`core/graph_assembler.py` 与 `callbacks/tracing.py` 属于事后转换型发射点,只填 `tool_call_id`,
不伪造一个并不存在的开始时刻。

同一 PR 记录了一个**已知缺口**:
`packages/graph-agent/src/graph_agent/middleware/__init__.py:59-67` 的
`MVP0_MIDDLEWARE_ORDER_CONTRACT` 把 `CognitiveFlow` 排在 `Tracing` 之前,
而 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:400` 的 `wrap_tool_call`
自行应答 `finish_task` 并直接 `return self._handle_finish_task(...)`,不调用内层 handler。
因此 `finish_task` 这一个工具**不产生开始事件**。

### B8. 同一发射逻辑已出现三份拷贝

> **2026-08-09 订正(S2 实施时机械复核)。** 本条初稿把「构造事件」与「遍历 callbacks 分发」
> 两件事合并成一句话说三处都做,与代码不符。下面是逐处核对后的准确事实,结论(没有单一出口)不变。

`ToolCallEvent` 在引擎中有三处各自独立的**构造**点,每一处都自己决定这次调用的身份
(`tool_call_id`)、自己决定装不装 `duration_ms`:

- `packages/graph-agent/src/graph_agent/middleware/tracing.py:110` —— agent 路径的包裹点。
  **这一处确实自己遍历 callbacks、自己 try/except 兜异常**(该分发循环是 PR #655 引入的)。
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py:262` —— **这一处不是发射点,是文件 sink。**
  `TracingCallback` 自己就是一个 callback;它构造 `ToolCallEvent` 只是为了把 legacy 钩子
  `on_tool_call(...)` 收到的调用写成 `trace.jsonl` 的记录格式(经由
  `_write_typed_event`,该方法只写文件、不分发给任何 callback)。它之所以要自己造事件对象,
  是因为 legacy 钩子的入参里根本没有事件对象可用 —— 病根在 legacy 路径(见下条),不在这个 sink。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:2153` —— agent 节点的事后补报点。
  它构造事件后调用共享分发 `callbacks/emit.py::_safe_emit_event`,**没有**自己遍历 callbacks。

另有**第四处**本条初稿漏列,且它才是第二份真正的手搓分发循环:
`packages/graph-agent/src/graph_agent/core/callback_bridge.py:216-236` —— legacy LLM phase 路径上
`_HarnessCallbackBridge.on_tool_end` 自己 `for cb in self._callbacks` 逐个调 legacy 钩子,
外层 `except TypeError` 再降级重试一次不带 `duration_ms` 的旧签名。
那个降级分支是向后兼容垫片,违反 `AGENTS.md`「Development Principles」的「No backward compatibility」。
同一路径的 `on_tool_start`(`callback_bridge.py:175-197`)握有真实的「工具即将开始」时刻,
却只把它塞进 `_pending_tools` 字典,不上报任何东西。

这是「上报动作没有单一出口」的直接证据 —— 违反 `AGENTS.md`「Coding Standards」的
「低耦合、高内聚」与「DRY,但三次成律」:同一业务含义的第三份拷贝已经出现。

**处置归属**:S2 收编第一处与第三处(两者改为向 `graph_agent/tracing/` 的单一出口报告);
第二处作为文件 sink 保持不动;第四处连同 legacy 路径的载荷不一致一起归 S3
(S3 本就要改 `callback_bridge.py:154-160`,见 B9),不在 S2 里顺手动。

### B9. 结束帧今天不承载模型最终产出,且两条执行路径的载荷不一致

`LLMCallEvent` 有两个可以装模型产出的字段,`callbacks/events.py` 中二者都是
`... | None = None`(可选、默认空):`messages: list[dict[str, Any]] | None = None` 与
`response_data: dict[str, Any] | None = None`。
**契约本身允许「什么都不装」,因此两条路径装不装、装什么,类型系统不会拦。**
实测结果是两条路径确实不一致:

- **V4 agent 路径:不装。** `packages/graph-agent/src/graph_agent/core/graph_assembler.py:2131-2132`
  构造 `LLMCallEvent` 时显式传入:
  ```
                          messages=None,
                          response_data=None,
  ```
  该事件只带 `input_tokens` / `output_tokens` / `resolved_model` / `parent_node_id` / `node_type`。
  **模型这次说了什么,一个字都不在结束帧里。**

- **旧 LLM phase 路径:装。** `packages/graph-agent/src/graph_agent/core/callback_bridge.py:154-160`
  中 `_HarnessCallbackBridge` 调 `cb.on_llm_call(...)` 时传入
  `messages=prompt_messages`(`:158`)与 `response_data=response_data`(`:159`)。
  其中 `response_data` 由同文件 `:304` 的 `_extract_response_data` 产出,
  而 `:344` 的 `data["content"] = _extract_text_content(raw_content)`
  装进去的正是**模型输出正文**。

**这两条路径中,agent 路径是今天真实运行所走的那条。**

**本条直接决定 D1 的「只流不存」能否成立。** 增量帧允许丢弃的唯一理由,是模型最终全文
另有一份完整副本留在结束帧里。B4 已证明步骤帧是四条链路的真相来源,B5 已证明
`trace.jsonl` 是唯一的落盘出口;而本条证明:在 agent 路径上,结束帧里没有这份副本。
因此若照搬「增量帧只流不存」而不先补齐结束帧,agent 路径上模型的输出全文将
**在盘上彻底消失** —— 既不在 `trace.jsonl`,也不在任何步骤帧里,
只活在 LangGraph 进程内的消息列表中,运行一结束即不可追。

### B10. agent 路径不发 LLM 步骤开始信号,因此没有任何输入落盘

`prompt_captured`(LLM 步骤的开始帧,承载模板 / 变量 / 渲染后 prompt)在 agent 路径上**一条都不产生**。
根因是结构性的,不是配置问题:

- **开始帧的唯一来源是一个代理。** `PromptCapturedEvent` 全仓唯一构造点是
  `packages/graph-agent/src/graph_agent/core/tracing_proxy.py:121`,位于 `TracingClientProxy` 内部。
  **不包这个代理,就绝不会有 `prompt_captured`。**
- **该代理的唯一构造点在旧路径。** `TracingClientProxy` 全仓唯一构造点是
  `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:206`,
  即**旧 LLM phase 路径**在此处把 chat model 包进代理。
- **agent 路径不包代理。** V4 agent 路径解析 chat model 走
  `packages/graph-agent/src/graph_agent/core/graph_assembler.py:2180` 的 `_resolve_phase_chat_model`。
  该函数按条件返回 `PredictGatewayChatModel` / 调用方传入的 `chat_model` /
  `LLMProviderChatModel` / model_resolver 的解析结果 —— **四个返回分支没有任何一个包 `TracingClientProxy`**。
- **两条路径并存。** `packages/graph-agent/src/graph_agent/core/phase_nodes/factory.py:41`
  在 `phase.requires_llm` 为真时仍然 `return LLMPhaseNode(...)`,旧路径没有被下线。

**因果证据(一次真实运行的观测)。** 2026-08-09 对一次真实 `run_skill`
(v0.3.0 skill,走 V4 agent 节点)打印全部事件类型,得到的序列是:

```
RunStartedEvent → InputDispatchEvent → PhaseStartEvent → AgentLoopIterationEvent
→ ToolCallStartedEvent → ToolCallEvent → AgentLoopIterationEvent
→ LLMCallEvent messages=None response_data=None
→ ToolCallEvent → LLMCallEvent messages=None response_data=None
→ ToolCallEvent → PhaseEndEvent → RunEndedEvent
```

**零条 `PromptCapturedEvent`**;两条 `LLMCallEvent` 的 `messages` 与 `response_data` 均为空。
这条序列同时验证了 B9(结束帧不带输出)与本条(没有开始帧、因而不带输入)。

**合并 B9 的结论:在真实运行所走的 agent 路径上,一次 LLM 调用既没有开始信号,
结束帧也不带输入和输出 —— 盘上只剩 token 数与模型名。**

### B11. 已合入的 Trace UI 依赖这两样,在 agent 路径上呈现为空

这不是尚未显形的隐患,而是**今天用户已经能看见的缺陷**。
`apps/studio/frontend/src/components/trace/TraceStepRow.tsx` 的 `PromptSections`(`:203`)
把一个 LLM 步骤渲染成四段,数据来源分别是:

```
206    const rendered = prompt.event_type === 'prompt_captured'
207      ? jsonText(prompt.resolved_prompt)
208      : jsonText(prompt.messages ?? undefined)
```

- `:211` **Template** ← `prompt.template_source`(开始帧)
- `:212` **Variables** ← `prompt.variables`(开始帧)
- `:213` **Rendered** ← `:206-208` 的三元式:开始帧是 `prompt_captured` 时取
  `resolved_prompt`,否则**回退**取 `llm_call.messages`
- `:215` **Response** ← `answered.response_data`(结束帧)

在 agent 路径上,开始帧不存在(B10)、`messages` 与 `response_data` 皆为空(B9),
因此 **Template / Variables / Rendered / Response 四段全为空**:
三元式的两个分支同时落空,Response 也取不到东西。

---

## 2. 决策

### D1 · 一次运行只有一条事件流,但流中的帧分两类,持久化策略不同

一次运行对外仍然只呈现**一条**事件流;这条流里的帧分成两类,两类的持久化策略不同:

- **步骤帧**:持久化进 `trace.jsonl`、占用 seq 序号、可回放、可取证、可统计。策略不变。
- **增量帧**:**只流不存** —— 不写 `trace.jsonl`、不进 `record.events`、不占 seq 序号;
  允许把相邻若干帧合并成一帧,允许在积压时丢弃中间帧。

**依据。** 其一是 B4:步骤帧今天同时是 `report.md`、有界取证查询、画布节点状态、token 统计
四者的真相来源;把全部事件一律降级为「仅供观看的流式产物」会同时切断这四条链路。
其二是 B5:增量帧若走步骤帧的同一条路,将在跨进程消息、线程跳转、无界内存列表、seq 序号、
磁盘行数五处同时付出代价,而且断线重连必须逐个重放每一个 token 才能补齐序号。

**「丢弃增量帧不损失正确性」依赖一个不变量,而该不变量今天不成立,必须由本决议补齐。**

**不变量:一次 LLM 调用的输入与输出,各有且只有一份完整落盘副本。**

- **输入的家是 `prompt_captured`(开始帧)** —— 模板、变量、渲染后 prompt。
- **输出的家是 `llm_call.response_data`(结束帧)** —— 模型最终全文。

「有且只有一份」是双向约束,**两头都要管**:
少于一份则数据丢失,多于一份则出现两个真相源、可以各自漂移。
增量帧之所以可丢,正是因为这两份副本都完整;任何一头缺失,增量帧就不再是可丢的中间态,
而变成该数据唯一的存在形式。**不变量成立,「只流不存」才成立;不变量不成立,「只流不存」就是在丢数据。**

该不变量今天**两头都不成立**,且两条执行路径的破法还不一样:

- **agent 路径(今天真实运行所走的那条):输入零份、输出零份。**
  不发开始帧(B10:`_resolve_phase_chat_model` 不包 `TracingClientProxy`),输入无处可存;
  结束帧显式传 `messages=None` / `response_data=None`(B9:`graph_assembler.py:2131-2132`),输出无处可存。
- **旧 LLM phase 路径:输入两份。**
  `prompt_captured.resolved_prompt` 存一份,`llm_call.messages` 又存一份(B9:`callback_bridge.py:158`)。
  两份副本各自独立填充,谁也不保证跟谁一致。

因此本决议把**补齐并收敛这个不变量**列为增量帧落地的**前置条件**,作为硬约束写死:

> 在「一次 LLM 调用的输入与输出各有且只有一份完整落盘副本」这一不变量成立之前,
> **「增量帧只流不存」不得先行落地。**

这不是建议,也不是「最好一并处理」。先后顺序由数据完整性决定,不由工期决定:
先落「只流不存」、后补不变量,中间这段时间里每一次 agent 路径的运行都会永久丢失模型的输入与输出,
而运行数据一旦没落盘就无法事后补救。落地顺序见 D7 的 S3。

**为什么不选另一种做法。** 另一种做法是「所有帧一视同仁,增量帧也落盘也占 seq」。
它的代价已由 B5 逐项列出,收益则是「回放时能看到当时的打字过程」——
而回放的读者要的是「这一步做了什么」,不是「这一步当时打字有多快」。代价与收益不成比例,故不选。

**外部佐证(只取其分层做法,不采用其具体 API)。** 同一结论在本仓之外有独立的先例:
OpenAI Agents SDK 把 `raw_response_event`(原始 token 增量)与 `run_item_stream_event`(语义条目)
分为两层;AG-UI 协议用 `TEXT_MESSAGE_START` / `CONTENT` / `END` 的三段式表达一条消息;
LangGraph 的 `stream_mode` 把 `"messages"`(token)与 `"updates"`(状态变更)分为两个独立模式。
这三例说明「增量与语义条目分层」是这一类系统的共同收敛结果,不是本仓的特殊选择。
本仓采纳的是这个**分层思路**,不采纳上述任何一方的具体接口形状或字段命名。

### D2 · 流式不是「缺失」,是「被丢弃」,三层逐层打通

按 B2 的三个坐标逐层恢复:

- `apps/studio/backend/app/core/adapters/engine.py:378` —— Studio adapter 不再把流式响应折叠成一次性结果。
- `packages/graph-agent/src/graph_agent/core/llm_provider.py:47-49` —— 引擎 Port 具备表达流式的能力。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:2079` —— 图执行路径能把增量传出来。

**这是「拆掉阻碍」,不是「从零新建」。** 底层的 LangChain chat model 本就具备 `_stream` / `_astream`,
流式数据一直存在,只是在上述三处被逐层折叠掉了。因此本项工作的性质是恢复既有能力的通路,
工作量与风险都应按「拆阻碍」估计,不应按「实现一套流式协议」估计。

**为什么不选另一种做法。** 另一种做法是绕开这三层,在 Studio 侧另起一条直连模型的旁路来取流。
它会造成同一次模型调用有两条互不知情的调用路径,token 统计、重试、fallback、取证四件事立刻出现两份真相,
并且直接违反 `AGENTS.md`「Three-Module Architecture」的 adapters 单一边界,故不选。

### D3 · Port 先行:先扩契约,再改实现

交付顺序固定为:**先**给 `LLMProvider` Port 增加表达流式的方法,**后**由 Adapter 实现它;
引擎核心逻辑不感知任何 provider 差异。

**顺序不可颠倒。** 契约无法表达的东西,实现层再努力也只能靠越界手段绕过去 ——
例如在 Adapter 里私自塞一个回调、或让 Adapter 反过来读引擎内部状态。
那是缺陷,不是方案。依据 `AGENTS.md`「稳定依赖(Port/Adapter)」:
领域逻辑依赖平台无关的稳定 Port,provider 差异由 Adapter 实现,不向核心职责泄漏。

**为什么不选另一种做法。** 另一种做法是「先让 Adapter 把流跑通,Port 之后再补」。
它在 Port 补上之前的那段时间里,必然存在一条绕过 Port 的私有通道;
按本仓「不写过渡形态、同一改动里删干净」的原则,这条私有通道从一开始就不该存在,故不选。

### D4 · 上报收敛到单一出口,流程各处只嵌入调用方

新建 `packages/graph-agent/src/graph_agent/tracing/` 模块(该目录当前不存在)。
该模块拥有「一个步骤的生命周期」这一个概念,对外只暴露很窄的接口:
**开启一个步骤**、**向进行中的步骤推送增量**、**结束该步骤**。
引擎流程各处嵌入的是这个出口的**调用方**(一个小组件),而不是各自的一份实现。
B8 列出的三处现有发射逻辑收编进该出口。

**依据。** B8:同一发射逻辑已有三份拷贝,分散在 `middleware/tracing.py:110`、
`callbacks/tracing.py:262`、`core/graph_assembler.py:2153`,属低内聚;
增量帧一旦落地,若不先收敛,它会成为第四份散落的发射逻辑。

**边界:本条是引擎内部重构,不改变对外事件契约。** 事件类型与字段一个不动,
因此本条可以独立验收 —— 既有的契约测试全绿即证明对外行为未变。

**同类成熟范式。** LangGraph 的 `get_stream_writer()` 是同一形状:
节点内部取得一个 writer 往流里写,不关心传输如何实现。此处只取其形状,不引入其代码。

**为什么不选另一种做法。** 另一种做法是保留三处发射逻辑,只在每处各加一段增量推送。
那会把拷贝数从三份变成六份,并让「一个步骤何时开始、何时结束」这个概念继续无人拥有,故不选。

### D5 · 增量帧走独立通道,并自带背压策略

- **传输分道**:增量帧与步骤帧在两处分开 —— 跨进程传输一处,WebSocket 传输一处。
- **不占资源**:增量帧不占 seq 序号、不落盘。
- **背压策略**:允许按时间窗把相邻增量帧合并成一帧;允许在积压时丢弃中间帧。
- **必带归属**:每一帧必须携带**其所属步骤的标识**,否则观众无法把这一帧贴到正确的步骤条目上,
  多个步骤并发进行时会串行错位。

**依据。** B5 列出的五处代价,正是由「与步骤帧共用一条路」直接导致的;分道即同时免除这五处代价。
「必带归属」不是可选优化:一次 agent 轮次可以并发多个工具调用与模型调用,
没有归属标识时,增量帧无法确定属于哪一条步骤条目。

**为什么不选另一种做法。** 另一种做法是不做背压、来多少发多少。
高频增量帧在慢速消费者面前会持续堆积,最终把内存与 WebSocket 缓冲一起拖垮;
而增量帧按 D1 本就允许丢弃,不设背压是放弃了一个零成本的安全阀,故不选。

### D6 · 前端复用已批准的步骤条目骨架,不另设计一套呈现

前置决议 `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` 的 D4 已经定义:
Trace 的呈现单位是「一个步骤一条」,状态机为 `进行中 → 完成`。
逐 token 呈现即在**「进行中」那一格内持续追加内容**,完成时该条按已批准的规则折叠为摘要。

- **不新增面板、不新增入口。**
- 增量帧按其携带的步骤标识(D5)贴到对应的那一条上。

**为什么不选另一种做法。** 另一种做法是为流式输出单开一个「实时输出」面板。
那会让同一次模型调用的内容出现在两个地方(实时面板一份、步骤条目摘要一份),
与前置决议 D5「一个信息只有一个家」的处置直接冲突,故不选。

### D7 · 交付切分与自评闸门

分五个阶段,一个 PR 一件事:

| 阶段 | 内容 |
|---|---|
| **S1** | 扩 `LLMProvider` Port 的流式方法;`LLMProviderChatModel` 实现流式;Studio adapter 改用底层 chat model 的流式出口 |
| **S2** | 建 `graph_agent/tracing/` 单一出口,收编 B8 的三处现有发射点(对外事件契约不变) |
| **S3** | 五项同属本阶段,共同让 D1 的不变量成立:①**agent 路径补发 LLM 步骤开始信号**,使 `prompt_captured` 在两条路径上都成立(B10);②**补齐结束帧承载模型最终产出**,消除 `core/graph_assembler.py:2131-2132`(agent 路径)与 `core/callback_bridge.py:154-160`(legacy 路径)在 `LLMCallEvent` 载荷上的不一致;③`llm_call` 的 `response_data` 改为**必填**;④**删除 `llm_call.messages` 字段**,连同 `TraceStepRow.tsx:206-208` 回退到 `messages` 的分支一并删除;⑤定义增量帧契约(模型正文增量、模型推理增量),每帧携带所属步骤标识,与步骤帧分道 |
| **S4** | 传输分道与背压落地(跨进程通道、WebSocket 通道、不占 seq、不落盘) |
| **S5** | 前端在步骤条目内逐字追加 |

**S3 的五项必须同属一个阶段,不得拆成多个 PR 先后交付。**
它们**服务于同一个不变量** —— D1 的「一次 LLM 调用的输入与输出,各有且只有一份完整落盘副本」。
①②补的是「少于一份」(agent 路径输入输出皆零份),③④治的是「多于一份」与「允许零份」:

- **③ `response_data` 改必填的理由:让非法状态不可表示。** 该字段今天是
  `dict[str, Any] | None = None`,**契约本身允许「什么都不装」** —— 这正是 B9 的不一致能长期存在
  而不被任何门禁发现的原因:两条路径装不装都合法,类型系统不会拦。改必填之后,
  「结束帧不带输出」在构造那一刻就构造不出来,而不是等到读盘时才发现是空的。
  这与 PR #655 对 `tool_call_id` 的处理是同一手法(必填不给默认值),不是新发明。
- **④ 删除 `llm_call.messages` 的理由:输入只能有一个家。** 输入的家是 `prompt_captured`;
  留着 `messages` 就是第二个家,两份副本各自填充、可以互相漂移,直接违反不变量的「只有一份」。
  与前置决议 D5「一个信息只有一个家」的处置同理。按不向后兼容原则**同一改动里删干净**:
  字段删除的同时,`TraceStepRow.tsx:206-208` 那个回退到 `messages` 的三元式分支随之删除,
  Rendered 一律取 `prompt_captured.resolved_prompt`,**不留过渡分支**。

拆开交付意味着在 PR 之间存在窗口:例如「增量帧已可丢、开始帧尚未补发」的窗口内,
每一次 agent 路径运行都会永久丢失模型的输入与输出(D1);
又如「`messages` 已删、`prompt_captured` 尚未在 agent 路径产生」的窗口内,
Rendered 两个来源同时不存在。同一阶段交付才能让这些窗口都不存在。

**阶段之间顺序不可乱,理由是数据依赖而非偏好:**
S1 不通,则 S3 定义出的增量帧**无源可发** —— 契约定义了却没有任何数据能填进去;
S2 不做,则 S3 的增量帧发射会成为 B8 之外的**第四个散落发射点**,把待收敛的拷贝数越做越多。

**闸门。** S1 与 S2 完成后由实施者自评效果,无问题则直接推进 S3–S5,**不需要再次审批**。

### D8 · 取代关系

本决议**取代** `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` §4「明确不做」的**第一条**。
该条原文把「LLM 输出逐 token 流式」列为「属独立大件,另行排期」,
并列出三项前置:打通 provider streaming、定义增量事件、处理传输与背压。
这三项前置正是本决议 S1、S3、S4 的内容 —— 该条的「另行排期」在本决议落盘时即被兑现,故取代。

该决议的其余部分 —— D1 至 D14 全部条目、§4「明确不做」的其余条目、§5 的其余处置 ——
**全部保持有效,不受本决议影响**。

---

## 3. 验收判据

因果验证:每条都要有动作**之后**的可观察结果作证据;命令跑过、函数返回、测试通过、
或实施者自报「已完成」,都不单独构成证据。

**S1(打通流式)**

1. 一次**真实**模型调用被证明是分多次增量返回的,而非一次性返回 ——
   证据形式为该次调用收到的分片记录:分片数 > 1,且各分片的到达时刻依次递增。
   只拿到一个完整响应即判不通过。
2. `apps/studio/backend/app/core/adapters/engine.py` 的 `model._generate(...)`
   在流式路径上不再是唯一出口;流式路径确实走到 chat model 的流式方法。

**S2(单一出口)**

3. `ToolCallEvent` 与 `ToolCallStartedEvent` 的构造与分发在
   `packages/graph-agent/src/graph_agent/` 中**只有一处**(收编前为三处,坐标见 B8);
   以全域 grep 结果为证。
4. 三条引擎门禁全绿:`uv run ruff check packages/graph-agent` ·
   `uv run mypy --strict packages/graph-agent/src` · `uv run pytest packages/graph-agent/tests`。
5. 对外事件契约不变,由**既有的**契约测试全部通过来证明(不新写、不放宽既有断言)。

**S3(开始帧补发 + 结束帧补齐 + 字段收敛 + 增量帧契约)**

6. **结束帧独立可复原模型全文**:跑完一次真实运行后,`trace.jsonl` 中**每一条** `llm_call`
   都带有该次调用的模型最终文本;把该次运行的增量帧**全部丢弃**后,
   仍能**仅从 `trace.jsonl`** 复原模型输出全文。
   证据形式为**该文件的实际内容**(逐条 `llm_call` 的载荷),
   **不接受**「代码里传了参数」「构造函数签名已改」这类上游断言 ——
   B9 的缺陷正是上游看似传了、agent 路径实际传 `None`,只有读盘上的成品才能证伪这种情形。
7. **Trace 四段全非空**:一次真实运行结束后,Trace 中**每一个** LLM 步骤的
   **Template / Variables / Rendered / Response 四段均非空**。
   证据为**真机截图**或该次运行 `trace.jsonl` 的实际内容。
   本条直接证伪 B11 记录的缺陷 —— 四段今天在 agent 路径上全空。
8. 每一条增量帧都携带其所属步骤的标识;随机抽取的增量帧均可据此贴回唯一的步骤条目。
9. 跑完一次真实运行后,`trace.jsonl` 中增量帧的出现次数为 **0**。

**S4(传输分道与背压)**

10. 一次真实运行过程中断线重连:游标**不因增量帧而产生缺口**,
    即重连后收到的步骤帧序号连续,不出现 `StreamCursorGapError`(`run_manager.py:1527`)。
11. 增量帧不进入 seq 序列:运行结束时 `record.events` 的长度等于步骤帧总数。

**S5(前端呈现)**

12. 一次真实运行中,某个 LLM 步骤在**进行中**即逐字增长,**完成后**折叠为摘要 ——
    以真机**录屏或分帧截图**为证。静态截图不接受(它无法区分「逐字增长」与「一次性出现」)。

**全局(改造不得损伤既有真相链路)**

13. B4 的四条链路在改造后行为不变,逐条给出证据:
    `report.md` 的工具调用统计不变;有界取证查询的迭代数 / LLM 调用数 / 工具调用数 / 驳回原因不变;
    画布节点状态推导结果不变;token 与工具调用统计不变。

---

## 4. 明确不做

- **不改变步骤帧的地位。** 步骤帧仍然是 `report.md`、有界取证查询、画布节点状态、
  token 统计这四者的真相来源(B4),不因为引入增量帧而降级为「仅供观看」。
- **不为已落盘的旧 run 写迁移或双读。** 依 `AGENTS.md`「No backward compatibility」原则,
  已存在的 run 数据直接丢弃,不写版本嗅探分支,不写兼容读取路径。
- **不引入新的第三方依赖来实现流式。** 底层 chat model 已具备该能力(B2),
  需要的是打通通路,不是引进新库。
- **不触碰 gateway 模块**(`packages/graph-agent-gateway`)。
- **不在本轮解决 `finish_task` 无开始事件的缺口**(B7 记录)。
  该缺口的根因是中间件顺序契约与 `CognitiveFlow` 自行应答两者共同造成的,
  修它需要先裁决「agent 路径上究竟由谁拥有 tracing」——那是一个独立的架构裁决,不在本决议范围。

---

## 5. 本决议取代/作废的既有记录

| 既有记录 | 处置 |
|---|---|
| `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` §4「明确不做」第一条:「LLM 输出逐 token 流式……属独立大件,另行排期」 | **取代**。该条列出的三项前置(打通 provider streaming / 定义增量事件 / 处理传输与背压)即本决议 S1、S3、S4 |

`docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` 的 **D1 至 D14 全部条目**、
§4「明确不做」的**其余条目**(run 概要中间层、批量运行 UI、模型对比机制、旧 run/predict 目录不迁移)、
以及 §5 表格中的**全部处置**,**保持有效,不受本决议影响**。

**关于该决议 D4 与 D5 的关系,须避免一个误读。** 本决议的 B10 与 B11 指出:
LLM 步骤的开始帧在 agent 路径上不存在,导致该决议 D4(LLM 步骤 = 开始帧 + 结束帧合成一条)
与 D5(prompt 回到步骤条目内)在 agent 路径上今天呈现为空。
**这不构成对 D4 / D5 的推翻或修改,恰恰相反** —— 那两条今天之所以空,
正是因为它们所需的数据从未产生;本决议 S3 把这份数据补齐之后,D4 / D5 才第一次真正可用。
换言之,**本决议 S3 是该决议 D4 / D5 在 V4 agent 路径上得以成立的前提,不是对它们的修改。**

本决议不改动任何 `docs/studio/mvp1/` 下的设计源,因此不触发
`docs/studio/mvp1/_audited-ready-hashes.json` 的哈希锁(校验器
`apps/studio/backend/tests/test_doc_hash_lock.py`)。各实施 PR 若改动上锁文件,
须在同一个 PR 内重钉哈希。

---

## 6. 实施切分

一个 PR 一件事,顺序即 D7 的 S1 → S5,不可乱序。

| PR | 内容 | 落点模块 | 必须同步更新的设计源 |
|---|---|---|---|
| S1 | `LLMProvider` Port 增流式方法;`LLMProviderChatModel` 实现流式;Studio adapter 改用 chat model 的流式出口 | engine + studio backend | `docs/engine/mvp1/` 对应机制档(LLM Port 契约) |
| S2 | 新建 `graph_agent/tracing/` 单一出口,收编 B8 三处发射点;对外契约不变 | engine | `docs/engine/mvp1/` 对应机制档(事件发射) |
| S3 | ①agent 路径补发 LLM 步骤开始信号,使 `prompt_captured` 在两条路径上都成立;②补齐 `LLMCallEvent` 结束帧承载模型最终产出,消除 agent 路径(`core/graph_assembler.py:2131-2132`)与 legacy 路径(`core/callback_bridge.py:154-160`)的载荷不一致;③`response_data` 改必填;④删除 `llm_call.messages` 字段 + 删除 `TraceStepRow.tsx:206-208` 的回退分支;⑤增量帧契约(正文增量 / 推理增量),每帧携带所属步骤标识,与步骤帧分道。**五项同一个 PR,不拆分**(理由见 D7) | engine + studio frontend | `docs/engine/mvp1/` 对应机制档 |
| S4 | 传输分道与背压:跨进程通道、WebSocket 通道、不占 seq、不落盘 | studio backend | `docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md`(如上锁则重钉哈希) |
| S5 | 步骤条目内逐字追加 | studio frontend | `docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md`(如上锁则重钉哈希) |

**S1、S2、S3 合并后必须重建 vendor 快照。** 三者都改动 `packages/graph-agent` 源码。
桌面 app 的 Python sidecar 无论是否 dev 构建,都从冻结的
`apps/studio/tauri/vendor/site-packages` 快照 import `graph_agent`;
不重建则运行中的 app 仍跑旧引擎代码,新字段会被 `extra_forbidden` 拒绝。
操作步骤:先关闭运行中的桌面 app(Windows 会锁住 vendor 的 `.pyd`/`.dll`),
再从仓根执行 `uv run python apps/studio/backend/scripts/build_vendor.py` 与 `compileall` 预热,
最后用标准启动器重启。完整规程见 `AGENTS.md`「Workflow Pipeline」第 7 条。
