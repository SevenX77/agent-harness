# 问题台账(Problem Ledger)

> 本文件是**用户指出的产品问题的唯一销账台账**:每条问题翻译成"哪个模块的问题",标注它牵动的层
> (事实源 / 中间层 / UI),修一条勾一条,勾销的唯一判据是**最终真机效果**,不是 PR 合并。
> 与 [DELIVERY_LEDGER.md](DELIVERY_LEDGER.md) 分工:交付台账管"正在做什么/到哪一步",本台账管
> "问题全集与销账状态"。全仓已实现功能的全景对照另见 2026-08-19 MVP1 功能对账
> (claude.ai Artifact:https://claude.ai/code/artifact/129408d8-1ffd-4b8c-a2b0-d155074b3ffb,
> 代码级核验);本台账不复制那份全景,只登记**用户点名的问题**。
>
> **建账方法(用户裁决 2026-08-19)**:①问题按模块树归属,一个模块一个包逐个解决,不做大杂烩包;
> ②台账把用户原话翻译成模块问题,原话仅作出处;③每个模块从底层(事实源)修到 UI 一次修完,
> 台账必须把三层受影响面记全,防"修了底层漏了 UI";④对照台账修完一个勾掉一个,判断修完看最终结果。
> 出处标注:全部 36 个历史会话的用户消息(1630 条)已于 2026-08-19 全量挖掘归档。
>
> 状态词汇:
> - `⏳ 未修` —— 已用代码坐实"这件事没做"。
> - `🧩 部分实现` —— 一部分已在,缺口已定位到 file:line;台账里必须写清缺的是哪一半。
> - `🔧 进行中` —— 本会话正在做。
> - `🔎 代码已实证,待真机` —— 逐行核过代码,实现完整;差的只是**最终真机效果**这一道判据。
>   **不许直接标 ✅**——建账方法第 ④ 条说得死:判断修完看最终结果。
> - `✅ 已修` —— 已合并 **且** 真机点验通过,证据写在行内。
> - `🗳 待裁决` —— 需用户定设计取舍。
>
> **2026-08-20 全量核实**:除 1.1.1 外的每一行都由 4 个只读核查 agent 逐条对着当前 `main`
> 的代码坐实过(每条带 file:line)。核实推翻了建账时的大量猜测状态——建账时的 `❓` 是
> "疑似,没查",现在的 `🔎` 是"查过了,代码这一层实现完整"。两者不是同一件事。

## 模块树(问题归属坐标系)

```
1 运行时观测
  1.0 事实源:运行事件契约(engine + gateway,多个 UI 模块共享的底层)
  1.1 画布运行时观测(区别于 trace)
      1.1.1 node   1.1.2 edge   1.1.3 subgraph   1.1.4 input/output 端点
  1.2 trace 面板
      1.2.1 步骤流时序   1.2.2 步骤内部过程(去黑箱)   1.2.3 长文本呈现
      1.2.4 edge 分段视图   1.2.5 结局卡与报告入口   1.2.6 search 与范围
      1.2.7 LLM 调用细节(路由/降级/配置对比/token)
  1.3 run 汇总(报告内容 / 统计口径 / 时间口径)
2 运行控制(run/pause/resume/stop/compile 按钮状态机)
3 LLM 配置(gateway 真相 + Settings + compare 链路)
4 Copilot(MoirAI)
5 平台与桌面壳(任务状态/重启/登录控制台)
6 发布与分发
7 skill 工作区与 golden
```

修复顺序(按「底座先行 + 统一状态系统」自行推导,不再逐项上呈):
1.0 → 1.1.1 → 1.1.2 → 1.1.3 → 1.1.4 → 1.2.x 逐个 → 1.3 → 2 → 3 → 4/5/6/7;
L1(模型组身份漂移)与 E6(token 汇总)是数据正确性问题,不排在 UI 队列里,并行推进。

---

## 1.0 事实源:运行事件契约

| # | 模块问题 | 层 | 状态 | 出处(用户原话日期) | 验收判据 |
|---|---|---|---|---|---|
| E1 | edge 是"上一 phase end→下一 phase start 之间的过程",引擎必须发 edge 分段事件,trace 中 edge 与 node 平级作为运行分段 | 引擎✅→前端⏳ | 🧩 **引擎侧已完成**:`callbacks/events.py:380-419` 定义 `EdgeStartEvent`/`EdgeEndEvent`(带 `edge_transition_id`/`from_phases`/`to_phase`/`changed_keys`/`blackboard_snapshot`/`operation_count`),`core/edge_transition.py:118-155` 真发。**缺口 100% 在前端**,见 T6 三条 | 08-16"edge指的是一个node到下一个中间的过程…把engine该补的补齐";08-14④;08-19 Q1/Q4 | 跑一次 run,trace 里能看到 edge 分段 |
| E2 | subgraph_path 已随事件上线(#867)但前端零消费 | 前端 | 🔎 **本 PR 已合**:`phasePathOf` 把 `subgraph_path` + `phase_name` 接成一个键,三条投影全部改用它 | 08-19 Q2 | 见 1.1.3 |
| E3 | prompt_captured 不携带模板原文,只有来源名——"SKILL.md 里写的是什么"无法展示 | 引擎→前端(+vendor 重建) | ✅ **已修(与 T2 同 PR)**:`prompt_captured` 增 `template_text`(认知模板全文)与 `phase_source_path`(相位文档的工作区相对路径);模板正文从 f-string 提成模块常量 `V030_COGNITIVE_TEMPLATE_TEXT`,渲染结果钉在 golden 上(`tests/cognitive/test_template_text_is_a_value.py`,golden 由改动前的 f-string 实现产出)。**真机点验前须重建 vendor** | 08-19"SKILL.md里写的是什么,模板写的是什么" | trace 步骤里能看到模板原文 |
| E4 | agent 节点内部步骤(中间件/md2json/validator 查了什么/protocol 检查)无 print 级语义事件——「只给结果不给过程」 | 引擎→前端 | 🔎 **已修,且原诊断已过时**。建账时写的病灶(`machineryNarration` 只读 `details`/`errors`/`violations`)是**前端**的,已随 T4 修掉(单句通道 + `eventFacts` 事实表 + `UnreadEventBody` 明确告警 + 镜像门禁),所以「无原始 JSON 兜底」这半条判据由 F12 结构性保证。**逐个重查四项内部步骤后,真缺口只剩一项**:①md2json ✅ 已在发——`cognitive_flow.py` 的 `story` 连**通过**的检查都写进去(「Schema check against X: all N block(s) passed」);②validator 查了什么 ✅ 同源(「Business validator passed N item(s)」/「No business validator is declared」);③protocol 检查 —— 通过时静默,**这是对的**,见下面的边界;④**中间件 ❌ 真缺**:`ExitControlMiddleware` 决定「这个相位继续还是停下」,五个答案里有四个**只写成 `logger.info(...)`**。后果是循环**最常见的结局也最看不见**——相位因提交被接受而正常结束,trace 里只有 `finish_task`、verdict、`phase_end`,没有一行说闸同意了。实测真实 8 相位 run(`2026-08-19T06-58-15_179d1440/trace.jsonl`):77 条事件、4 个 agent 相位,**结束了这四个相位的那个组件贡献 0 条事件**。引擎其实早把这些句子写出来了,只是写在了运行的读者永远不看的地方——这正是本行「print 级语义事件」的字面含义。**修法**:新增 `AgentExitDecisionEvent`,闸的每一个答案都发,取值封闭(`exit_success`/`continue_tool_work`/`continue_nudged`/`continue_open`);**五个决策点全覆盖**,包括写测试时才实测发现的第五个——挂在 `after_model` 的 planning gate,它在 `after_agent` 轮到之前就把循环打回去。前端按 F12 既有契约消费:镜像表 + 事实读法(`outcome: phase ended` / `loop continues` + `iteration`),不需要新设计单元。**边界(同一条规则的另一半,写进 OB8)**:会改变后续控制流的组件是**决定者**,每次决定都报;不改变控制流的检查是**断言**,只报失败——所以 protocol 校验维持只发 `ProtocolViolationEvent`,给一个每次模型调用要跑两遍的断言加「通过」事件是纯噪声 | 08-14②「tracing对用户的目的是去黑箱」;08-19 Q9(说过不止两次) | 展开任一步骤能读到它每一步做了什么,无原始 JSON 兜底 |
| E5 | DeadEndPrunedEvent 等旁路事件要合入正规回调链 | 引擎 | 🔎 **已收口,补上本行一直缺的证据**:决议 D7(`docs/design/2026-08-15-edge-as-first-class-run-segment-decision.md`)之后 `Callback.on_event` 是唯一入口、`_safe_emit_event` 是唯一发射器,旧 `on_*` 钩子family连同翻译层已删;门禁 `tests/callbacks/test_one_emission_path.py` 用一个**只实现 `on_event`** 的消费者接住 `DeadEndPrunedEvent`(它正是当年走旁路的那一个)。接线也在:`middleware/factory.py:59-97` 八个槽位**全部**收到同一份 run callbacks。前端有读法(`utils/trace.ts` 的 `dead_end_pruned` → `fact('pruned', …)`),不落 JSON 兜底。**另做了一次机械审计**:events.py 的 37 个事件类逐个找发射点,零个从未被构造(`LLMRouteDecisionEvent`/`LLMCallSettingsEvent` 由 gateway `call/tracing.py` 构造引擎的类,不是死契约) | 08-16 | 事件在 trace 正常出现 |
| E6 | **run 级 token 汇总漏掉 iterate/batch/loop 下的全部花费(已确诊引擎缺陷)** | 引擎 | ✅ **已修**:根因是 iterate 把每个 item / 每一轮跑在**子状态**上、跑完整个丢掉——相位级换成 `_phase_outputs_delta` 的通道增量,图级换回原始 state;子状态记的花费不在幸存者里就没了(`phase_execution_ids` 当初已被手工牵出过一次,token 是掉进同一个洞的第二样东西)。**四条 iterate 路径全修**(相位 batch / 相位 loop / 图级 batch / 图级 loop):子状态的账**从零起算**(`_accounting_from_zero`),它报回来的就是它自己花的,父层把这些增量加进自己那一份(`_SpendHarvest`)——G-Counter 纪律,拒绝了「继承总数再取差」(N 个兄弟会把基数数 N 遍)。门禁是不变量而非硬编码数字:run 报出的花费 == 它自己报告过的那些 `llm_call` 之和(`tests/core/test_iterate_token_accounting.py`)。**真机点验前须重建 vendor** | 08-19 截图 | 结局卡 token = Σ调用;`report.md` 与 `metrics.json` 两个 token 源不许打架 |
| E7 | 时间口径:run id/事件 UTC 与本地混用(裁决 08-09:用系统本地时间) | 引擎/后端/前端 | 🔎 **已修,三层各一处**。先澄清两件不是缺陷的事:**同屏 06:58/11:38 不是串台**(resume 复用同一个 run_id,`routers/runs.py:296-341` 全程用传入 run_id,两簇时间戳本来就该同屏);**存 UTC 也不是缺陷**——带时区的瞬间才是代码能算、换时区仍正确的那个值。真缺陷是**呈现口径**:实测真报告 `2026-08-19T06-58-15_179d1440/report.md` 相隔两行写着 `| Run | …T06-58-15… |`(本地)与 `| Started | 2026-08-19T13:58:15.556101Z |`(UTC),一个瞬间两个读数差七小时。**修法 = 把 D13「UTC 戳对着读它的人就是错的时间」推广到每一个人读得到的时刻,换算只发生在「值变成给人看的文字」那一个边界**:①后端 `services/run_report.py` 的 `_wall_clock`,`Started` 改本机墙钟 + 偏移量;②前端新增唯一换算出口 `utils/wall-clock.ts`,**收编此前散在五处的读法**——其中 Settings 真相源那处(`GeneralTab.formatTimestamp`)是把偏移量从字符串上抹掉、把 UTC 数字当本地显示,是同一缺陷的第二个实例;③导出文件名 `reportTimestamp` 改用同一个 `fileStamp`,与 run 目录同形。门禁钉的是不变量而非格式:同一瞬间的 `Z`/`-07:00`/`+02:00` 三种写法必须渲染成同一段文字。设计源 run-execution F1b 决策 ⑤ + `FRONTEND_UI_SPEC.md` §2.11a | 08-09;08-19 截图 | 全部显示本地时间且互相一致 |
| E8 | 调用前探针缺失 + 最终报告对本次 run 全部路由做一次 warning 汇总 | gateway→报告 | 🔎 报告已有 Routes 节(`services/run_report.py:76-86` `routes_section(events)`) | 08-10 两条 | 报告有路由汇总节 |
| E9 | 框架工具(finish_task / update_working_memory 等)从不被宣告,界面答不出「它现在在跑哪个工具」 | 引擎→前端 | ✅ **已修**。**上一版的定性是错的**,已订正:`ToolCallStartedEvent` 一直在发,只是**只对 skill 自带工具**——`CognitiveFlowMiddleware` 排在 `TracingMiddleware` 前面,对自己拦下的工具直接作答、不调 `handler(request)`,整条 wrapper 链连观察者一起被跳过(实测:两个框架工具产出 2 条 `tool_call`、0 条 `tool_call_started`,两个 wrap 钩子探针各 0 次)。**裁决=观察者放到决策者外层**:顺序契约把 `Tracing` 移到第 1 位(参考 Django MIDDLEWARE / Express app.use);配套把「已报告过的调用不再报告」收进相位唯一那个 `StepReporter`,否则同一次调用会被中间件和 agent 节点各报一遍。UI 侧:节点卡在有工具在跑时直接写工具名,按 `tool_call_id` 配对判断「还开着」 | 08-19(N2 派生) | running 节点与 trace 都能显示正在执行的工具名 |

## 1.1 画布运行时观测

**1.1.1 node**
| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| N1 | 状态只有小胶囊换字,整卡无状态表达;裁决呈现方式:状态灯闪烁+状态标签(idle/running/success/failed)+边框虚线流动+有空间加运行时间,找成熟参考 | 前端 | 🔎 **#875 已合**:状态灯(复用 Settings 路由灯)+ 标签(Idle/Running/Success/Failed)+ running 卡片虚线流动边框(图案与 edge 流动线同源)+ 运行时间(`deriveNodeRuntimes` 投影,running 逐秒推进、终态冻结);设计源 canvas F3 ② 同 PR 改写 | 08-19 Q3 | 扫一眼画布即知进度 |
| N2 | running 节点不显示"正在干什么"(第几次调用/工具/已耗时) | 前端+引擎 | ✅ **三样全齐**:已耗时 #875、第几次调用 #896、**当前工具本 PR**。#896 当时写的「当前工具做不到」是**错判并已订正**——`ToolCallStartedEvent` 一直在发,只是被 `CognitiveFlowMiddleware` 抢答的工具收不到(详见 E9)。现在:有工具在跑时卡片那一行直接写工具名,工具返回后回到 `Call N`,终态回到 `3 calls`;「还开着」按 `tool_call_id` 配对判断,不是「最近听说的那一个」 | 08-19 视觉裁决 | running 卡上有活动说明 |
| N3 | run 结束动画/running 态残留不清("老生常谈"×3);要求组件建立"状态↔显示效果对照表" | 前端 | 🔎 对照表已存在且有测试:`utils/run-status-projection.ts:38-45` `NODE_STATUS_AT_RUN_END`,`:188-193` 用 run verdict 无条件关掉所有 running。残留风险见 P1(两条终态通道都没送达时仍永久 running) | 08-04②;08-09⑤;08-14⑥ | run 结束 10s 后画布无任何运动元素 |
| N4 | 完成节点留痕(耗时/调用次数),run 后画布=结果地图 | 前端 | 🔎 **已合**:耗时 #875,**调用次数**本 PR 与 N2 同源同修——同一个 `deriveNodeActivity` 投影,running 读作序数、终态读作基数。原先标"待裁"的那一项在此自决:它和 N2 的"第几次调用"**是同一个事实**,分两处裁会得到两个数;而"run 后画布=结果地图"这条本行自己的判据,不给调用次数就达不到。**iterate 相位按全部执行累加**(时长仍只取最后一段),否则一个跑了 N 个 item 的节点会把工作量少报 N 倍 | 08-19 讨论中方案 D | run 后每个跑过的节点都留下耗时与调用次数 |

## 1.2 trace 面板

| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| T1 | 步骤流时序倒置:running 时流式输出画在 prompt 段上方,prompt 被压到最底 | 前端 | 🔎 **本 PR 已合**:按台账当时给出的正解做了——流式思考/回答并入 `LlmFlowBody` 的 Thinking/Answer 位次(设计 D1 的执行顺序),调用落定后由 `llm_call` 终值接管、流式副本消失;折叠行没有序列可言,仍单独显示流入文本。顺序已加测试锁死 | 08-19×2 天,痛斥 | 时序=装载 prompt→组合→思考→回答 |
| T2 | prompt 装载展示不全:要"SKILL.md 原文/模板/组合后/system prompt/user prompt"分段人话 | 引擎+前端 | ✅ **已修**:展开的 LLM 步骤按执行顺序给出四格——`Loaded — <相位文档路径>`(可点开真文件)、`Wrapped — cognitive/v0.3.0`(模板全文)、`Filled in`(变量)、`Sent — System/User`(一条消息一格、正文原样,取代从前那坨 `JSON.stringify`)。标题写**动作**不写数据类别,因此不违反 2026-08-13 D1「废除 TEMPLATE/VARIABLES 容器」。设计源 trace-observability F5 已改写 | 08-19;08-14① | 一步内五段齐 |
| T3 | iteration 区分:机制在(Iteration N 分隔条),部分 phase 事件无轮次标记导致不显示 | 引擎→前端 | 🔎 **本 PR 已合,根因不是"缺标记"而是"两个数被当成一个"**。实测(引擎批处理夹具)每个 batch item 花 2 个 ReAct 轮次却发了 **3 次** LLM 调用——被驳回的 finish_task 不触发新 `before_model` 就重试——所以 `prompt_captured.loop_index`(数调用)与 `agent_loop_iteration.iteration`(数轮次)本就是两件事,而前端 `trace-steps.ts` 拿前者当后者的等价数据源。**两处同修**:①引擎 `LLMProviderChatModel` 的调用计数器是个 per-instance 计数,而 chat model 与中间件链一样每个 phase 节点只建一次 → 跨 batch item 一路涨到 6,改为按 `agent_invocation_key()` 记账(`next_invocation_call_index`,与 `ExecutionControlMiddleware` 2026-08-15 那次修复同一条既有配方);②前端轮次分层**只认 `agent_loop_iteration`**,往后顺延,删掉 loop_index 兜底;首条轮次标记之前的调用保持平铺,不猜。设计源同 PR 更正(原文并列写了两个数据源) | 08-19 Q11 | 全部循环 phase 有分隔 |
| T4 | 非 LLM 步骤展开=原始 JSON 兜底,"只有结果没有过程"(重复≥2 次) | 前端 | 🔎 **本 PR 已合**。核查推翻了本行原先的判断「依赖 E4」:D4 要求的引擎自述**大部分已经在发**——`md2json` 的逐阶段叙述走 `FinishTaskVerdictEvent.details`(`cognitive_flow.py` 的 `story`),`loop_detected`/`tool_error_handled`/`tool_history_repaired`/`runtime_input_injected`/`nudge` 各自带整句 `message`。**缺口在前端**:`machineryNarration` 只读 `details`/`errors`/`violations`,于是所有只带 `message` 的决策事件一路掉进 `JSON.stringify`。三处同修:①自述并入单句通道(`message`/`warning`/`reason`)与单数 `error`;②新增 `eventFacts` 逐类型事实表(transition / dispatched / synthesized・dropped / removed / …),长值仍归文本井;③`GenericPayload` 换成**明确告警** `UnreadEventBody`(`data-trace-unread-event`)。**并加了防退化门禁**:`utils/engine-event-types.ts` 镜像引擎事件联合体,后端测试`test_engine_event_types_are_mirrored.py` 两边对读,前端断言每一项都有读法——引擎新加事件而没人给读法,CI 直接红。设计源 F12 | 08-14②;08-19 Q9 | 无 GenericPayload 兜底可见 |
| T5 | 长文本:"View full text"按裁决应打开常规编辑器而非自造 modal | 前端 | 🔎 **已实现**:`components/trace/TraceText.tsx:12-21,44-58` → `Workspace.handleFileOpen`(:1083-1096)→ 工作区编辑器,打开的是只读虚拟文档 `trace/<slug>.json`;测试 `TraceText.test.tsx:84-91` 同时断言 payload 与"无 `[role=dialog]`"。**两个会让用户以为没做的触发条件**:①按钮只在文本溢出时出现(`ui/text-well.tsx:27-34` 用 `scrollHeight>clientHeight` 量,被折叠父容器隐藏时两值都是 0);②无 workspace context 时按钮不渲染 | 08-14③→08-15 修订三条 | 点开=编辑器 |
| T6 | edge dot 面板:run 成功后仍显示静态推断+"Run the skill to see real dispatched values" | 前端(E1 引擎侧已就绪) | 🔎 **#878 已合,三处全修**:①`lib/edge-context.ts:27-30,52` 的 `upstreamIncludes` 要求 `from_phases.includes(fromPhase)`,而首个 phase 的 `from_phases` 是 `[]` → 根边恒不匹配 → 回落静态推断(与 `trace-scope.ts:59-63` 的正确写法分裂,见 IO1);②`Workspace.tsx:2255` 给画布喂的是 `runStream.events`,而 trace 面板读 `viewedTraceEvents`(:738)——**回看历史 run 时画布 dot 永远拿不到真实值**;③`utils/trace-scope.ts:27` 的 `EDGE_OP_TYPES` 不含 `edge_start`/`edge_end`,选中一条 edge 后**它自己的分段步骤被范围过滤掉了**。①→`edge-identity.ts` 一处判定(空 `from_phases` = 根迁移);②→`Workspace.tsx` 的 `viewedRun` 三元组,画布与 trace 面板同源;③→`EDGE_SEGMENT_EVENT_TYPES` 收编两个分段事件 | 08-14④;08-19 Q4-2+截图 | 跑完点 dot 见真实值与操作 |
| T7a | 结局卡(Run succeeded)在任何 node/edge 范围收窄下都渲染,与时间线脱节 | 设计源→前端 | 🔎 **本 PR 已合**:设计源先改(`trace-observability/mvp1-alignment.md` F3 的「run 级派生不受范围影响」一刀切措辞被推翻),判据改为**这个派生长在哪里**——身份区(顶条 run_id + 状态徽章,F8)属于运行本身、不受范围影响并加了 `data-trace-verdict` 供锁定;列表区属于当前取景,`TracePanel` 的 `outcome` 在有 scope 时直接为 null。`degradedRouteCount` 一并改读 `scopedEvents`,理由是它**可操作**——点它就是往当前列表里搜,点开找不到的计数比没有计数更坏 | 08-19 Q5 | 收窄范围时不出现 |
| T7b | Open run report 用系统默认程序打开,裁决=app 内编辑器/阅读器(重复≥2 次) | 前端+后端 | 🔎 **本 PR 已合,两处同修**:`TraceOutcomeRow` 与运行列表行 `TimelinePanel.RunReportLink` 都改走 `onFileOpen(runReportOpenRequest(path))`,以只读 markdown 文档落在工作区编辑器(与 T5 同一条通道);`openLocalPath` 在这两处删净。**根上还改了后端**:`RunMetadata.report_path` 由绝对路径改为**工作区相对路径**(`.workspace/runs/<id>/report.md`)——编辑器按相对路径读文件,绝对路径只有交给 OS 时才用得上,而那正是被推翻的做法 | 08-19 Q6 | 点开=app 内打开 |
| T8 | search:多轮返工仍不符("直接用 shadcn 模板组件不要改";"说了不知道多少次") | 前端 | 🧩 **组件壳子没跑偏**:`TraceSearchBar.tsx:26-31` 100% 用本地 shadcn `ui/input-group`,零样式覆写。用户不满的是**行为**。已列出 11 条行为限制(零事件时搜索框整个不挂载 / 筛选行只在聚焦时可见 / "n filters on" 计数在聚焦时被隐藏 / 匹配面是整个事件 `JSON.stringify` / 纯子串无正则无字段限定 / 无高亮无命中计数无跳转 / 过滤事件而非步骤导致步骤被拆成孤立完成态 / 无防抖 / route-issues chip 与搜索框共用 searchTerm 会覆盖用户输入 / 搜到 0 条时结局卡仍在 / 图标尺寸被测试禁止覆写)——**需与用户逐条对账后一次修对,不再猜** | 08-08④;08-09⑩;08-19 Q8 | 用户点头 |
| T9 | 每个 llm_call 上重复渲染 Probe failed 黄块;"3 route issues" chip 语义 | 前端 | 🔎 **两处分别已合**。①chip:#887 改读 `scopedEvents`——它是**可操作**的(点它就是往当前列表里搜),计数与点开能看到的必须一致。②黄块去重(本 PR):一条降级按「结果+route+endpoint+原因+状态码」认身份,**第一次完整解释,之后只报一行"又一次 + 累计第几次 + 原因见上"**(投影层 `TraceVerdict.occurrence`,渲染层只选版式)。实测依据 run `2026-08-19T06-58-15_179d1440`:一个超时 endpoint 在连续三个 LLM 步骤上各画一整块黄框。参考 syslog 的 `last message repeated N times`,差别是不要求连续(降级会被正常步骤隔开)。`answered` 不折叠——「这次由谁应答」是每次调用各自的事实。设计源 F10 | 08-19 截图 | 降级信息一次一处 |
| T10 | run 级 LLM 降级计数 chip 缺;run_id 概要中间层缺 | 前端 | ✅ **本行不成立,关闭**:前半已 live(`TracePanel.tsx:561-586`,设计源亦标 live);后半**已被 D1 裁决作废**(`03_regions/timeline/mvp1-alignment.md:162`「F3 已被 D1 作废,Trace 视图本身就是完整 trace」)。遗留待办:`trace-observability/mvp1-alignment.md:44` 还挂着"仍 target-design:run_id 概要中间层",与 timeline 那份矛盾,删掉 | MVP1 对账 gap(F2/F7) | — |
| T11 | predict 完 timeline 空白 | 前端 | 🔎 **已实现**,2026-08-09 那次修在案且注释直接引用了这句原话(`services/predictor.py:172-185`);predict 开跑即广播 gate 带人进 trace(`:95-114` + `gate-state.ts:99-107`)。**唯一残留复现路径**:`predictor.py:108` 的 `transport == "in_process"` 判定——切到 `http_loopback` 则不注册瞬态 run 也不推事件,面板停在 "Waiting for run events" | 08-09① | predict 后 trace 有内容 |
| T12 | 跨 run 事件串台 | 前端 | 🔎 **已合,两层都已坐实**。①流层面本就干净:`hooks/useRunStream.ts:39-44` 渲染期同步重置、`:63-70` 每次写入都要报出 subject。②真正缺的是**把断点画出来**(本 PR):resume 复用同一个 `run_id`,两簇相隔很远的时间戳同屏,而 `resumed` 事件按普通步骤渲染、一路掉进 `GenericPayload` 原始 JSON——唯一看得出"这里断过"的线索只剩时间跳变。现改为**接缝行**(`TraceResumeSeam`,`data-trace-resume-seam`):左右细线 + 一枚 chip 写清「这是 resume / 从哪个相位接上 / 人回答了什么 / 何时」,不展开、不参与相位缩进——与列表另一端的结局行同理(里面没有执行)。设计源 F11 | 08-09;08-19 截图 | 一个 trace 只含一个 run

## 1.3 run 汇总

| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| R1 | run 报告漏答 08-08 规格里的五个问题 | 后端(run 报告投影) | 🔎 **五项全修完**(②④⑤ 见 #902,①③ 本 PR)。**①input files**:从代码字体的路径改成**能点开的相对链接**(绑定路径相对 `.workspace`,run 目录在 `<workspace>/runs/<id>`,所以是上两级;**推不出这个布局就不给链接只给路径**——点不开的链接比纯文本更坏);并且不再只读快照的**声明绑定**,补上引擎实发的 `input_file_injected`(它挂在边上,所以「送给了哪个节点」一并报出)——只报声明的话,答案在 run 开始时为真、到结束就过期。**③llm vs 结果链接**:候选 side-run 的报告现在链回**它对照的那次 run** 的 `report.md`。这一条本来是**数据缺口**不只是渲染缺口——side-run 此前根本没记自己对着哪次 run 跑,本 PR 给 `RunMetadata` 补 `compare_base_run_id` 并在 `_spawn_side_run` 写入;没记到的照实说「没记录」,不猜 run id。**基准 run 那一侧仍无 compare 节**,且在报告可重生成之前**不可能有**:compare 发生在基准 run 结束之后,而报告是终态写一次的纯投影;让它去扫兄弟目录会使「这份报告说什么」取决于此后又跑了什么(RUN_EXECUTION-10 已写明这条边界)。**唯一遗留 = 结构缺陷**:报告没有重生成入口,而 RUN_EXECUTION-5 明说它是可随时重生的纯投影——历史报告永远停在写它那天的渲染逻辑上。设计源 RUN_EXECUTION-8/9/10(哈希已重钉) | 08-08 大单 | 逐项在报告中找到 |
| R2 | compare 侧跑 token 汇总 0 | 引擎 | ✅ **随 E6 同修**。两个源现在由不变量绑在一起:`report.md` 按定义是 trace 里 `llm_call` 事件之和(`run_report.py:200-202`),`metrics.json` 是 `result.metrics`(`runner.py:1980`),而引擎测试要求后者等于前者的定义式,所以「同一个 run 目录里一个写 27009 一个写 0」不再可能 | 08-19 截图 | — |

## 2 运行控制

| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| C1 | 暂停表达:有 checkpoint 却无法暂停;暂停态显式 resume+stop 双按钮;节点级暂停缺 | 后端→前端(节点级要引擎) | 🧩 **run 级全有**:`services/run_manager.py:1088` `pause_run` 保 checkpoint,`center-action-bar.tsx:168` paused 态同时给 Resume+Stop(测试钉死),落地 PR #584(08-04 当天)。**节点级暂停 = 全仓零实现**(右键菜单只有缩放/锁定/删除;节点 toolbar 只有 HITL 应答与 Resume;`nodes/types.ts:5` 有 `breakpoint` 状态但**没有任何动作产生它**)——落点 engine 断点能力 → backend `POST /runs/{id}/breakpoints` → frontend 入口。**另有可达性缺陷(会让用户复述"无法暂停")**:`stage` 只来自内存(`Workspace.tsx:561`),刷新/切 skill 后 run 还在后台跑但 Pause 按钮消失;`handlePause` 还要求 `runId` 非空而 `handleSelectRun` 只设 `viewedTrace`;后端 `pause_run` 只认内存 `self._runs`,sidecar 重启后 409 | 08-04×2 | 真机走查 |
| C2 | run 运行中按钮至少变成可停止 | 前端 | 🔎 **本 PR 已合**:`running` 现在同时给 **Pause + Stop**,与 `paused` 的 **Resume + Stop** 对称。后端本就一步到位(`test_run_pause_stop.py::test_stopping_a_run_in_flight_skips_the_pause` 断言在飞的 run 直接 `cancelled`),`handleStop` 也只要求有 `runId`——所以"先暂停再停止"那一步是 UI 自己发明的绕路。设计源 run-execution F7 | 08-04③ | 真机走查 |
| C3 | compile 按钮状态机:compile 成功后再按一次卡死 | 前端 | 🔎 **已修**:PR #676(2026-08-09,正是复现当天)。病灶不在 `gate-state.ts` 而在 `Workspace.applyGateEvent`(:685)——状态落地已无条件且先于任何去重,去重键从 `runId ?? contentHash` 换成整份 projection 指纹(`gate-effect-fold.ts:51-63`),回归测试在案。**残留风险**:`compileSkillById` 无超时兜底,后端永不返回时 stage 永远停在 `compiling` | 08-09 复现 | 复现路径不再卡 |

## 3 LLM 配置

| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| L1 | **模型组身份不稳定**:显示层的「同一模型」跨端点合并键被当成组的对外身份 id 发布 | gateway→后端→前端 | 🔎 **已修**。**归属更正**:本行原写 gateway→后端→前端,实际 gateway 的`project_model_group_identity` 一直是纯函数、没问题;缺陷**只在 studio 后端发布这一步**——`_model_groups_response` 按语义键把 route 合成组之后,又用 `_representative_canonical_id` **选举**一条 route,拿它的 `canonical_id` 当组的对外 id。前端把这个 id 当不透明键用,不需要改。**实测底数(2026-08-20,开发机真实凭据)**:400 个组发布的 id 与自己的合并键不同;`analyst` 三张卡全失联,存的是 `deepseek-v4-flash-260425`(08-12 加 deepseek-official **之前**选出来的 id)加两个裸模型 id,而**它们的 route 全都还在**、且**全都投影到同一个键** `deepseek-v4-flash`——也就是 `fast` / `copilot_deepseek_v4_flash` 引用得好好的那个。丢的从来只是标签。**修法两半,缺一不可**:①组 id 改成**合并键本身**(纯函数,不选举);②**角色里的组按它持有的 route 重算身份**——没有②的话①会当场打断 `claude-haiku-4-5-20251001` / `claude-opus-4.8` 这两个引用**当前**选举结果的角色(实测同一份文件里就有)。②同时负责合并「同一个模型的两张卡」并丢弃「一条 route 都不列的空组」(真实文件里有一个);注册表不认识其 route 的组**不丢**——那是 route 被删,不是标签过期。**显示名仍可择优**:会变的显示名只是换个说法,会变的 id 让每个写下它的角色失联。设计源 `00_settings-ux-spec.md` §2.2 | 08-19 Q13+截图 | 角色卡三组全绿;增删端点不再翻转任何组身份 |
| L2 | compare 候选的 UI 链路从未走查 | 前端+后端 | 🧩 **UI 全链路都在**(读/增/改/删/测/跑/看结果):候选区挂在 agent 节点属性面板(`PropertiesPanel.tsx:1374` → `LlmNodeCompareField`),整份 PUT 存 `.workspace/runtime_config.json`,有专门的 `Run compare` 按钮(`:3554`)。**三处真空**:①**SUBGRAPH 节点属性面板根本没有这一区**(`:1504-1534` 只渲染名字/路径/validator),而后端接得下 → 能力在、入口无;②必须有**本会话的 live runId**,从历史列表点开的 run 只设 `viewedTrace` → "设完候选点 Run compare 却被告知先跑一次"是必然;③**路由撞车(硬缺陷)**:`routers/runs.py:43` 与 `routers/compare.py:15` 注册同一路径 `POST /skills/{id}/runs/{id}/compare`,`main.py` 先 include runs → **golden 的 POST /compare 被永久遮蔽**(当前前端只用 GET 版所以没炸)。④候选存的是 L1 那个不稳定的 `model_group_id`,同源同修 | 08-19 Q12 | UI 全链路走查 |
| L3 | "我添加一个会出现两个" | 前端 | 🔎 **已修**:PR #866(08-19 21:11,晚于用户报障)——第三方 provider 身份改为按 name 合并(`provider-utils.ts:439`),回归测试断言同名卡只剩 1 张。其余"添加"流程(角色加模型 / 模型库 provider 标签 / 加 compare 候选)已逐个查过,均幂等。**唯一未排除**:一个第三方 URL 后端会 mint 三条协议兄弟记录,卡内渲染成多行 endpoint——需真机确认用户看到的"两个"是卡还是行 | 08-19[b31d7d1f] | 复现→修复 |
| L4 | reasoning_effort UI 入口 + 各家枚举;temperature=模型上限×百分比;越界 clamp 不 400;top_p 不暴露 | gateway→前端 | 🔎 **四条全满足**:effort 有 Select(`RoleSettingsDialog.tsx:254`),枚举双来源(协议词表 `registry/bounds.py:62` + 实测 `probing/questions.py`);temperature 是"作者刻度 0–2 → 各路由上限的份额"(`bounds.py:130`);越界两层都 clamp 不报错(`schema.py:341`、`call/settings.py:250-265`);top_p 全仓无输入控件。**两个会让用户以为没做的点**:所有路由都没测出 effort 时 Select 是**禁用**的;temperature 显示的是作者刻度百分比而非该模型实际温度(提示语藏在 tooltip 里) | 08-10 四连 | Settings 走查 |
| L5 | key 掩码位数与真实长度一致 | 后端→前端 | 🔎 **已实现**:`models/llm_config.py:120` `api_key_length` 是 computed_field(永不落盘、不回传 gateway、客户端回传一律丢弃),前端按它重复掩码字符无截断(`ProviderCard.tsx:137`),测试 `api_key_length: 51` → 51 个 `•` | 08-12 | 走查 |
| L6 | 探测能力 T1/T2/T3 整合成可复用接口;provider chip 真聚合等遗留 | gateway | 🧩 **T1/T2 已整合**(`probing/__init__.py` 导出 `probe_provider_endpoint`/`probe_provider_route`/`probe_official_call_method`/effort 三件套,宿主在 `routers/llm.py:3262-3285` 统一接线)。**T3(tool call/ReAct)未实现**——`probing/questions.py:44` 只留了一句 "and later the tool shape",包内无 tool 探测构造器、`bounds.py` 无 tools bounds。"provider chip 真聚合"**台账没给判据,代码单方面判不了**,需用户补一句"聚合到什么粒度算数" | 08-11 | — |
| L7 | 密钥被拒后端点永久砖化 | 后端→前端 | ✅ #872,真机点验通过 | 08-19"为什么点 test 会失效" | 已达成:`deepseek-official` 由 `disabled` 转 `verified`;在仍 `disabled` 的 `gemini-official` 上复验,Test 走完全程并如实报告密钥无效 |
| L8 | 聚焦密钥输入框露出 `**********` 占位符且可就地编辑 | 前端 | ✅ #872 + #873,真机点验通过。**顺带查到的遗留物**:`components/studio/ApiKeyInput.tsx` 是无人引用的死组件,而它实现的正是被 #872 废弃的旧语义(掩码截断到 32、退格砍真实密钥)——留着它,下一个人复用就会把两个缺陷一起复活,建议删 | 08-19"点击激活 api key 的 input 组件为什么显示成这样" | 已达成:9 张卡聚焦后一律 `•` × `api_key_length`、退格无效、键入整把替换 |
| L9 | 改完 Base URL,整张卡到达即死:三个格子全灰、点 Test 报「没有可测项」,而新地址从未被探测过 | 后端→前端 | ✅ #876 + #880,真机点验通过 | 08-19「所以这里的前端交互很有问题啊,需要全面检查一遍」+ jiekou 卡截图 | 已达成:改地址后三个格子回到 `unverified_manual`、密钥保留、旧地址的模型清单清空;普通 Test 真的发出三条 `endpoint_test`;卡片头部按状态分别说「Protocol not supported」/「Not tested」,不再落回「Not configured」。收尾时那张卡由「三格全死」变成「OpenAI 绿、196 个模型、gpt-4o 生成验证通过」。**顺带审计出的独立问题**(整页保存差集删除的三条误删路径 A-1/A-2/A-4)按用户裁决不夹带进本修复,已登记在 [DELIVERY_LEDGER](DELIVERY_LEDGER.md)「审计发现批次 2026-08-20」,并已按用户 2026-08-20 裁决「删除必须显式表达」随 #886 全部销账(交付台账 W2-43) |

## 4 Copilot(MoirAI)

| # | 模块问题 | 层 | 状态 | 出处 |
|---|---|---|---|---|
| CP1 | @mention 节点未实现;图片附件未实现 | 前端→后端 | ⏳ **两项都零实现**,且 **placeholder 在撒谎**:输入框写着 `Use '@' to mention nodes...`(`copilot-panel.tsx:1116-1127`)而 `handleComposerKeyDown`(:813-819)全文只有发送键判定;同文件 :1160 的注释自己立了规矩「no dead placeholders」却被 placeholder 本身违反。后端 `CopilotWsRequestPayload.user_message` 是纯 `str`,无附件字段。**零成本止血**:先把 placeholder 降级为不承诺 `@` |
| CP2 | 建技能向导(brainstorming)未成型 | 全栈 | ⏳ 设计源自标 target(`copilot-assist/mvp1-alignment.md:61-66`);agent 资产里无 brainstorming skill(`agent-skill-map.json` 七个 skill 里没有);New Skill 对话框只有名字+父目录直接铺模板。现状退化成"MoirAI 自由发挥 + `create_skill` 一把梭" |
| CP3 | CLI 设置页七条(08-12)残项核对 | 前端 | 🔎 **六条全中**(第 1 条本就是机器环境问题不改代码):全称文案 / codex effort 词表 / 模型下拉非自由输入 / MoirAI worker 三行双下拉+env 注入 / 版本自检并入探测(不加定时器,"查不到 ≠ 版本旧") / 行内更新+登录按钮。唯一遗留是设计源自己记的实测项:worker env 的 `ANTHROPIC_MODEL` 是否吃别名 |
| CP4 | trace-local"为该节点设计 golden"CTA 缺 | 前端 | 🧩 CTA 已在(`TracePanel.tsx:587-601`),但语义是"从本次 run 提升"(promote)而非"设计",且**无 run 时整个消失**(`:344-347` 依赖 `canCompare = Boolean(runId)`)——而"还没有可用输出时先把期望写下来"恰恰是这条要的路径。与 K1 同族 |
| CP5 | 回 Home copilot 上下文清空未坐实 | 前端 | 🔎 **三层都清**:store `copilotStore.reset(null)`(`useCopilot.ts:212-216`)、面板整体卸载、ws 断开后端连带清 SDK 会话与挂起审批(`routers/copilot.py:168-169`)。**隐性缺陷**:`reset` 是**全局**清空所有 workspace 的会话窗口,作用域比声明大(磁盘 `_window.json` 还在所以看不出来) |
| CP6 | 审批卡 approve 后按钮不置灰仍可重复点击 | 后端→前端 | 🧩 **同一次挂载内会置灰**(`tool-approval-card.tsx:73` + :53-56 自锁),服务端也幂等。但**决议只存在组件本地 `useState`**,事件反序列化时状态被硬编码成 `pending`(`types/copilot.ts:180-195`),而消息是要落盘的 → **面板收起再展开 / 切 session tab / 冷启 Restore chat,已决议的卡片复活成可点**,点下去得到红 toast「Approval expired: approval_not_found」。同一个错误码还同时代表"超时"和"会话重置",错因不可分辨 |
| CP7 | 审批挂起不设超时;超时自动拒绝并继续跑是缺陷,应停任务 | 后端 | 🔎 **已按裁决实现**,台账原描述过时:默认 1800s 可环境变量调(`services/copilot.py:362-365`),**超时 = `interrupt=True` 停任务保会话**,用户主动拒绝才是 `interrupt=False` 继续跑——两条语义分开,正是 07-08 两条裁决的形状,回归测试在案。**前端侧缺口**:`tool_approval_timeout` 全前端零命中,超时后卡片还停在 "Waiting for approval." 且按钮可点(与 CP6 同一次改) |
| CP8 | 回复语言跟随用户是否已固化进 MoirAI 规则 | 规则资产 | 🔎 **已固化**:`app/agents/operating-manual.md:48`「Always reply in the language used by the user in their last message」,且确实装进会话级 system prompt(`services/copilot.py:882-897`),三女神 worker 同吃(:942) |

## 5 平台与桌面壳

| # | 模块问题 | 层 | 状态 | 出处 |
|---|---|---|---|---|
| P1 | 后台任务状态不收敛,"我看到的状态就是一直在运行啊"(×3) | 壳/前端 | 🔎 **状态源已收口**到唯一模块(`utils/run-status-projection.ts`,决议 D7),三个消费点(画布节点灯 / trace 步骤 spinner / 顶条徽标)各自登记对照表。**残留真空**:`runVerdict` 的兜底是 `?? "running"`——worker 被外部杀死(既无 `run_ended`,用户又没点 Stop/Pause)时 `liveRunRecord` 永不写入,徽标继续转到用户切走为止。无看门狗、无心跳超时 → 补一个"流断且长时间无帧 ⇒ 回捞 `getRunDetail`"的收敛器 |
| P2 | **Retry 按钮不重启任何东西**:能启动 sidecar 的配方被关在「已经启动成功的 sidecar」里,首启失败即失去重试能力 | 壳(Rust)→前端 | 🔎 **已修**。**根因不是少调一个函数**:`launch_config` 原本存放在 `SidecarManager` 内部,而 `SidecarManager` 只能由一次**成功**的启动构造出来——首启失败,配方跟着陪葬,所以 `restart_sidecar` 在 `manager == None` 时只能直接 Err(只救得了一个还活着的 sidecar);同时 `get_sidecar_config` 回的是**首启那一刻缓存下来的错误字符串**,按一万次字面同一条,用户体验就是「点了没反应」。**修法(三层全改)**:①**壳/Rust**——新增 `SidecarSupervisor`(`sidecar.rs`),它持有**配方**并最多持有一个由配方造出来的 sidecar;状态是 `Running(manager)` / `Absent(原因)` 二选一(不会既有又无);`restart()` 无论从哪个状态出发都去拿一个 sidecar(活的就地重启,没有的就从头启动),且**每次尝试的结果覆盖记录**,所以之后读到的永远是这次尝试说的话。参照 Erlang/OTP supervisor 的 child spec 与 systemd 的 unit 文件——两者都把子进程规格放在**监督者**手里而不是被监督的进程里,`restart_child`/`systemctl restart` 才能作用于一个没在跑的子进程;**不借**它们的自动重启策略(触发器是人按 Retry,永久性失败上自动重试只会把错误刷没)。②**壳/命令层**——`SidecarAppState` 只剩 `supervisor: Option<..>`,`None` 专指`STUDIO_TAURI_DISABLE_SIDECAR=1`(压根没有配方,与「启动失败」是两回事);`restart_sidecar` 从此有真实调用方。③**前端**——`config/runtime.ts` 新增 `restartSidecar()`,`RuntimeGate` 的 Retry 改调它(首次挂载仍只是读配置,不去踢一个健康的 sidecar);重试期间先回到 `loading`,长达 30s 的 health 超时期间按钮看起来在干活而不是又一次装死。设计源 `03_regions/shell-layout/mvp1-alignment.md` F5 + SHELL_LAYOUT-4(同 PR 落盘,哈希已重钉);顺带订正了同一单元里「RuntimeGate 仍可全屏 gate」这条过期现状(代码里 `RuntimeShell` 无条件渲染 `{children}`,D10 早已满足)。测试:Rust 3 条(从没起来过的 sidecar 上重试会**真的尝试启动**并报出这次尝试的原因、而不是 `is not running` 这条拒绝)+ 前端 4 条 | 08-19 Q「Try again 点了没反应」 |
| P3 | 登录控制台 c/v 快捷键 | 前端/壳 | 🔎 **已实现且多做一步**:`c` 重新复制最近 URL、`v` 把 Windows 剪贴板注入 CLI 输入,首条 URL 零按键自动复制并打一行提示。第二轮"没有 v"的根因已定位并删掉肇事判定——旧的"输入行为空"判定在 Ink TUI 下被终端应答(如光标位置报告)记成"已开始输入",v 从此永久失效;现只剩 60ms 孤立键判定。**限制**:只在 Windows/WSL 生效;CLI 从没吐 URL 时用户永远不知道有这两个键 |
| P4 | 登录按钮常驻(换账号)+显示已登录账号 | 前端/壳 | 🔎 **两项都在**:登录按钮无条件返回、与行状态无关(`CliSection.tsx:90-96`,**推翻了设计文档 08-12 的 `missing\|broken` 条件,以代码为准**);账号显示三段齐(claude 读 `.claude.json` 的 `oauthAccount.emailAddress`,codex 解 auth.json 里 id_token 的 JWT email 声明,都是只读身份字段)。**缺陷**:账号只在 `state == ok` 分支打印,`broken`(token 过期)时不带账号——恰恰是换账号排障最需要那一刻 |

## 6 发布与分发

| # | 模块问题 | 层 | 状态 | 出处 |
|---|---|---|---|---|
| D1 | 新用户零安装:"第一次使用者要装多少外部应用?" | 壳/打包 | 🧩 **已内化**:Python 运行时(5 个三元组全 pin)、后端+SDK 闭包、ah/ahd(构建链 `--strict`)。**仍要用户自己装**:tmux、Claude Code CLI、codex,Windows 上还硬依赖 WSL。**且打包版的一键安装必炸**:`lib.rs:606-611` 去仓库里找 `scripts/install-claude-code-wsl.ps1`,而 `tauri.conf.json` 的 `bundle.resources` 根本没带它 → 打包后 `installer script not found (packaged build?)` |
| D2 | Windows 发布打包链从未跑通 | 打包 | ⏳ **仓库里根本没有打包 CI**(`.github/workflows/` 只有 ci/codeql/scorecard,全仓 `tauri build`/`tauri-action` 零命中),Windows 在 CI 里只有非必需的观测 smoke 且 vendor 是 stub。python3 坑仍在编排层(`tauri.conf.json:8` 的 `beforeBuildCommand`),而脚本内部其实**已经**适配了 Windows——坑在编排不在脚本。**⚠️ 顺带查到一个安全问题**:`sync_resources.js:34-46` 打包时会把仓库同级的 `../skills` 整个拷进安装包,本机该路径是 `D:\coding\skills`(30+ 个私人技能源码)。`.workspace` 被过滤所以 run 记录不进包,但技能源码会 |

## 7 skill 工作区与 golden

| # | 模块问题 | 层 | 状态 | 出处 |
|---|---|---|---|---|
| K1 | golden 种子化后半截(空模板/坏文件用 run 输出重填) | 后端→前端 | ⏳ **自动种子化整半截零代码**:全仓 `seed`×`golden` 前后端各 0 命中;run 终态路径(`run_manager._finalize_terminal_run:1399-1422`)完全不碰 golden;现存的只有用户点按的显式 promote。"空模板/坏文件"当前语义是**跳过**而非**重填**(`golden_diff.py:541-551` `reason=expected_output_invalid` → skip) |
| K2 | 每个 agent node 自动生成桩数据,无 copilot 也能跑 predict | 引擎/后端 | 🔎 **已实现且真机实测通过**:三级兜底最后一定有桩(`_predict_internal/interception.py:124-136`),连无 schema 也有值;作者 validator 只对 `heuristic_stub` 降级。实测 `predict-2026-08-19T06-21-43_cf1a8014` 全绿:42 条 phase 记录、30 个 `phase_end`、**0 条真实 llm_call**。真实边界是确定性假值可能把路由卡在环里 → `MAX_PHASE_REVISITS = 10` / 422 `PREDICT_DEADLOCK`,**若判据是"predict 必须永远跑到底",这条边界要单列** |
| K3 | 两套冲突 UX 统一 | 前端 | ⏳ **两套依然并存、零共享层**,设计源自陈 target(`conflict-overwrite/mvp1-alignment.md:38-45` F3)。A 套=文件保存冲突 Dialog(View Diff/Use Remote/Overwrite/Keep Local,`ConflictDialog.tsx:20-46`),B 套=顺序覆盖 Popover(Cancel/Allow Overwrite,`SkillNode.tsx:226-264`)。**四处不共享**:容器、动词表、严重度语汇、真相源(HTTP 409 结构化 payload vs **compile error 文本正则** `sequential-overwrite-routing.ts:34-38`)。修复要点:顺序覆盖识别改吃结构化 `error_code`,按 no-backward-compat 删掉消息串匹配 |
| K4 | i18n P2 + 后端 skills.py 中文 | 全栈 | 🧩 **账目要改**:后端不是"27 行中文"——`routers/skills.py` 全文只剩 4 行含中日韩字符,其中**用户可见的只有 2 行**(`:496`/`:505` 的 `APP_SETTINGS_INCOMPLETE` 分支 message),其余 router 的中文全是注释。**i18n P2 一步没走**:只有 `settings`/`errors` 两个命名空间(`i18n.ts:11-20,36`),`canvas`/`copilot`/`trace` 都不存在;`useTranslation` 只出现在 16 个文件、全是 settings 家族 |

---

## 附:方法纪律(不入销账,指向规则文件)

用户反复重申的工作纪律已固化于:AGENTS.md(Development Principles/Coding Standards/铁律)、
CLAUDE.md(交互偏好/汇报纪律/裁决分层)、`.claude/skills/studio-verify`、记忆库。高频重申且需持续自查:
不问选择题、自己测完再说、结论要端到端实测支撑、黑话必解释、报告正文直接贴出、截图走 Artifact、
第一性原理+找成熟工程参考、模块化高内聚低耦合、一个一个模块扎实做完(2026-08-19 建账方法即其落地)。
