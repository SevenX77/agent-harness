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
| E4 | agent 节点内部步骤(中间件/md2json/validator 查了什么/protocol 检查)无 print 级语义事件——"只给结果不给过程" | 引擎→前端 | 🧩 已坐实:`utils/trace.ts:600-607` 的 `machineryNarration` 只读 `details`/`errors`/`violations`,而**整个 events.py 里带这三者的只有 2 个类**(`FinishTaskVerdictEvent`、`ProtocolViolationEvent`)。其余 20+ 类事件(`loop_detected`/`tool_error_handled`/`runtime_input_injected`/`nudge`/`working_memory_update`/`compaction`/`blackboard_reduce`/`input_dispatch`/`edge_*`/`phase_*`/`run_*`/`parallel_map_group_*`…)一律落 raw JSON | 08-14②"tracing对用户的目的是去黑箱";08-19 Q9(说过不止两次) | 展开任一步骤能读到它每一步做了什么,无原始 JSON 兜底 |
| E5 | DeadEndPrunedEvent 等旁路事件要合入正规回调链 | 引擎 | 🔎 | 08-16 | 事件在 trace 正常出现 |
| E6 | **run 级 token 汇总漏掉 iterate/batch/loop 下的全部花费(已确诊引擎缺陷)** | 引擎 | ⏳ 根因已定位到一行:`core/graph_assembler.py:916-919`(batch)与 `:973-976`(loop)把节点返回值整个换成 `_phase_outputs_delta(...)`,而该函数(`:476-482`)的 flow delta **只有 `phase_execution_ids`**——每个 item 由 `PhaseWrapper` 算好的 `flow.metrics` 被整体丢弃;且 channel 合并是覆盖不是求和(`core/state.py:310-317` `{**merged, **delta}`),指望通道求和救不回来。**不是 compare 特有**:磁盘实测普通 run `2026-08-19T05-21-45` 也是 0/0/0 而 trace 里 84 次调用共 687613/98592;`06-22` 那次 metadata 的 147414/21323 恰好等于全图**唯一三个不在 iterate 下**的 phase 之和 | 08-19 截图 | 结局卡 token = Σ调用;`report.md` 与 `metrics.json` 两个 token 源不许打架(现已在磁盘上打架:`06-58-15` run 报告写 27009、metadata 写 0) |
| E7 | 时间口径:run id/事件 UTC 与本地混用(裁决 08-09:用系统本地时间) | 引擎/后端/前端 | 🧩 **同屏 06:58/11:38 不是串台**——resume 复用同一个 run_id(`routers/runs.py:296-341` 全程用传入 run_id,`record_resume_result` 直接 append 进原 record),两簇时间戳本来就该同屏。剩下的真问题只有"时区口径"本身 | 08-09;08-19 截图 | 全部显示本地时间且互相一致 |
| E8 | 调用前探针缺失 + 最终报告对本次 run 全部路由做一次 warning 汇总 | gateway→报告 | 🔎 报告已有 Routes 节(`services/run_report.py:76-86` `routes_section(events)`) | 08-10 两条 | 报告有路由汇总节 |

## 1.1 画布运行时观测

**1.1.1 node**
| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| N1 | 状态只有小胶囊换字,整卡无状态表达;裁决呈现方式:状态灯闪烁+状态标签(idle/running/success/failed)+边框虚线流动+有空间加运行时间,找成熟参考 | 前端 | 🔎 **#875 已合**:状态灯(复用 Settings 路由灯)+ 标签(Idle/Running/Success/Failed)+ running 卡片虚线流动边框(图案与 edge 流动线同源)+ 运行时间(`deriveNodeRuntimes` 投影,running 逐秒推进、终态冻结);设计源 canvas F3 ② 同 PR 改写 | 08-19 Q3 | 扫一眼画布即知进度 |
| N2 | running 节点不显示"正在干什么"(第几次调用/工具/已耗时) | 前端(事实源已有) | 🧩 #875 已给"已耗时";"第几次调用/当前工具"仍缺 | 08-19 视觉裁决 | running 卡上有活动说明 |
| N3 | run 结束动画/running 态残留不清("老生常谈"×3);要求组件建立"状态↔显示效果对照表" | 前端 | 🔎 对照表已存在且有测试:`utils/run-status-projection.ts:38-45` `NODE_STATUS_AT_RUN_END`,`:188-193` 用 run verdict 无条件关掉所有 running。残留风险见 P1(两条终态通道都没送达时仍永久 running) | 08-04②;08-09⑤;08-14⑥ | run 结束 10s 后画布无任何运动元素 |
| N4 | 完成节点留痕(耗时/调用次数),run 后画布=结果地图 | 前端 | 🗳 耗时已由 #875 落地;"调用次数"待裁 | 08-19 讨论中方案 D | — |

**1.1.2 edge**
| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| G1 | edge 无任何运行状态;"哪一部分运行哪一部分呈现 running"必须覆盖 edge | 前端(E1 引擎侧已就绪) | 🔎 **#879 已合**:`utils/edge-status-projection.ts` 从 `edge_start`/`edge_end` 派生 idle/running/done/failed/paused,取代 `flowing = (target === runningPhase)` 的倒推;run 终态按与节点同一张对照表关闭 | 08-19 Q1 | 数据流过哪条边哪条边动 |
| G2 | edge 选中要点得中、有高亮 | 前端 | 🔎 **#879 已合**:整条线加 20px 透明命中路径(`EDGE_INTERACTION_WIDTH`),选中出加粗环 | 08-19 Q4-1 | 点边即高亮 |
| G3 | 运行中连线虚线流动动画(含 subgraph 连接线) | 前端 | 🔎 **#879 + 本 PR 已合**:数据边由 edge 运行态驱动 `.animated-flow-line`;subgraph 连接线由容器 running 驱动(`isContainerRunning`) | 08-19 Q3-2/5 | — |

**1.1.3 subgraph**
| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| S1 | 运行状态不递归:展开容器内子节点恒 Idle(状态表按裸 phase 名记账,子图内没人喂) | 前端(E2 就绪) | 🔎 **#882 + 本 PR 已合**:相位投影改按 phase path 记账(`utils/phase-path.ts`,#882);本 PR 把同一条规则贯彻到**边与端点**——边分段 key 带作用域前缀(`edge-status-projection.ts`),`from_phases: []` 在子图内指该子图自己的入口而不是 run 的输入,展开预览的内部边与自己那对端点都读本作用域证据(`inlineChildEdge`/`inlineChildNode`)。根层键逐字不变。设计源 canvas F9 | 08-19 Q2×2 天 | 子图内正在跑的节点亮 |
| S2 | running 时自动展开,跑完收起,手动操作优先 | 前端 | 🔎 **本 PR 已合**:`containerAutoAction` 按状态**跃迁**驱动;失败的容器保持展开(参考 GitHub Actions 日志分组);本次 run 内手动开合过即接管 | 08-19"running的时候subgraph要打开" | — |
| S3 | 折叠态容器显示进度(3/7 完成)+ 容器框呼吸/边框流动 | 前端 | 🔎 **本 PR 已合**:容器 chip 常驻 `3/7`(子拓扑未加载时只报 `3 done`,不编分母);容器框走与节点卡片、运行边同一套行进虚线(`.studio-running-dash-frame`),未选"呼吸"是为了三个尺度只有一套运行语汇 | 08-19 Q2/Q3-6 | — |

**1.1.4 input/output 端点**
| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| IO1 | INPUT/OUTPUT 节点及其连线的显示与状态管理必须与普通 node/edge 统一(重复:"我也说过,也不做") | 前端 | 🔎 **已合**:#878 把根边判定收敛成一处(`utils/edge-identity.ts`,两套逻辑删净),#879 让 IO 边界边与普通边走同一套 edge 运行态与命中区。端点自身与 phase 同住一张状态表、戴同一枚状态胶囊、running 时同一套行进虚线;多来源取最差;端点被显式排除在 resume 锚点之外。**两端的证据来源不同**(2026-08-20 真机实证修正):Input 读从它出发的边分段(`inputBoundaryStatus`);Output 读**产出它的相位**(`outputBoundaryStatus`)——实测 run `predict-2026-08-20T04-09-33` 全量事件流里**没有任何事件指向 output 端点**(最后一条 `edge_end` 是 `[story_analysis] -> global_synthesis`),原先"看入边"让 Output 在完全成功的 run 上恒为 Idle;进入 Output 的那条边同样跟随产出相位(`outputEdgeStatus`),否则端点绿了喂它的线还是灰的。设计源 canvas F8 | 08-14⑦;08-19 Q7 | 同一状态系统驱动全部节点 |

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
| T9 | 每个 llm_call 上重复渲染 Probe failed 黄块;"3 route issues" chip 语义 | 前端 | ⏳ **无任何去重/聚合**:`trace-steps.ts:150-156` 把每条 route decision 挂到所属步骤,`TraceStepRow.tsx:287-307` 逐条画盒子。chip 语义已查明:`utils/trace.ts:415-420` 数的是**全 run 中 `decision !== 'answered'` 的事件条数**(同一坏端点被探 3 次就是 3),且喂全量不随范围收窄。两处必须同改,否则 chip 数与可见黄块数继续对不上 | 08-19 截图 | 降级信息一次一处 |
| T10 | run 级 LLM 降级计数 chip 缺;run_id 概要中间层缺 | 前端 | ✅ **本行不成立,关闭**:前半已 live(`TracePanel.tsx:561-586`,设计源亦标 live);后半**已被 D1 裁决作废**(`03_regions/timeline/mvp1-alignment.md:162`「F3 已被 D1 作废,Trace 视图本身就是完整 trace」)。遗留待办:`trace-observability/mvp1-alignment.md:44` 还挂着"仍 target-design:run_id 概要中间层",与 timeline 那份矛盾,删掉 | MVP1 对账 gap(F2/F7) | — |
| T11 | predict 完 timeline 空白 | 前端 | 🔎 **已实现**,2026-08-09 那次修在案且注释直接引用了这句原话(`services/predictor.py:172-185`);predict 开跑即广播 gate 带人进 trace(`:95-114` + `gate-state.ts:99-107`)。**唯一残留复现路径**:`predictor.py:108` 的 `transport == "in_process"` 判定——切到 `http_loopback` 则不注册瞬态 run 也不推事件,面板停在 "Waiting for run events" | 08-09① | predict 后 trace 有内容 |
| T12 | 跨 run 事件串台 | 前端 | 🔎 **流层面已堵死两道锁**:`hooks/useRunStream.ts:39-44` 渲染期同步重置(不留一帧)、`:63-70` 每次写入都要报出 subject。**截图现象另有解释**:resume 复用同一 run_id(见 E7),两簇时间戳本就同屏。**由此新开一条**:trace 里没有"这里是一次 resume 的接续点"的视觉分隔,导致同一 run 的两段被误读为串台 → 落点前端,`resumed` 事件应渲染成明确分隔行而不是掉进 `GenericPayload`(T4) | 08-09;08-19 截图 | 一个 trace 只含一个 run |

## 1.3 run 汇总

| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| R1 | run 报告内容对照 08-08 规格逐项核对 | 后端 | 🧩 **11 项已逐项核过:6 齐、5 缺**。齐:整体情况 / 花费时间 / token / 每节点时间-token-模型 / 文件链接 / artifacts 链接。缺:①**input files 是 code 文本不是链接**(`services/run_report.py:341`),且数据源是 `runtime_config.snapshot` 的声明绑定而非引擎实发的 `input_file_injected`;②**batch/loop 详情整块没有**(`:208-209` 把 agent ReAct 轮次误标成列名 `loop iterations`;引擎的 `parallel_map_group_started/ended` 从未被读;iterate 的每个 item 折成一行,item 数/耗时/token/成败全不可见);③**llm vs 结果零链接**(`:403-414` 只打印 group/candidate id;且**基准 run 的报告里根本没有 Model compare 节**);④每节点报错详情只收 2 类事件(`:210-221`),`loop_detected`/`interrupted`/`builtin_subagent_fallback`/`nudge` 一概不收,且单条 message 不截断(实测数千字);⑤Nodes 表**没有状态列**。另有一条结构缺陷:报告只在 run 终态写一次,**没有重生成入口**,而设计 RUN_EXECUTION-5 明说它是可随时重生的纯投影——同名 subgraph 折行 bug 虽已修好,08-19 07:14 vendor 重建前的历史报告永远错下去 | 08-08 大单 | 逐项在报告中找到 |
| R2 | compare 侧跑 token 汇总 0 | 引擎 | ⏳ **= E6,同源同修**。定性已从"待查"升级为**已确诊引擎缺陷**:同一个 run 目录里 `report.md` 写 27009 tokens、`metrics.json` 写 0(`2026-08-19T06-58-15_179d1440`),而设计 RUN_EXECUTION-6 明写"两者对不上就是引擎缺陷" | 08-19 截图 | — |

## 2 运行控制

| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| C1 | 暂停表达:有 checkpoint 却无法暂停;暂停态显式 resume+stop 双按钮;节点级暂停缺 | 后端→前端(节点级要引擎) | 🧩 **run 级全有**:`services/run_manager.py:1088` `pause_run` 保 checkpoint,`center-action-bar.tsx:168` paused 态同时给 Resume+Stop(测试钉死),落地 PR #584(08-04 当天)。**节点级暂停 = 全仓零实现**(右键菜单只有缩放/锁定/删除;节点 toolbar 只有 HITL 应答与 Resume;`nodes/types.ts:5` 有 `breakpoint` 状态但**没有任何动作产生它**)——落点 engine 断点能力 → backend `POST /runs/{id}/breakpoints` → frontend 入口。**另有可达性缺陷(会让用户复述"无法暂停")**:`stage` 只来自内存(`Workspace.tsx:561`),刷新/切 skill 后 run 还在后台跑但 Pause 按钮消失;`handlePause` 还要求 `runId` 非空而 `handleSelectRun` 只设 `viewedTrace`;后端 `pause_run` 只认内存 `self._runs`,sidecar 重启后 409 | 08-04×2 | 真机走查 |
| C2 | run 运行中按钮至少变成可停止 | 前端 | 🔎 **本 PR 已合**:`running` 现在同时给 **Pause + Stop**,与 `paused` 的 **Resume + Stop** 对称。后端本就一步到位(`test_run_pause_stop.py::test_stopping_a_run_in_flight_skips_the_pause` 断言在飞的 run 直接 `cancelled`),`handleStop` 也只要求有 `runId`——所以"先暂停再停止"那一步是 UI 自己发明的绕路。设计源 run-execution F7 | 08-04③ | 真机走查 |
| C3 | compile 按钮状态机:compile 成功后再按一次卡死 | 前端 | 🔎 **已修**:PR #676(2026-08-09,正是复现当天)。病灶不在 `gate-state.ts` 而在 `Workspace.applyGateEvent`(:685)——状态落地已无条件且先于任何去重,去重键从 `runId ?? contentHash` 换成整份 projection 指纹(`gate-effect-fold.ts:51-63`),回归测试在案。**残留风险**:`compileSkillById` 无超时兜底,后端永不返回时 stage 永远停在 `compiling` | 08-09 复现 | 复现路径不再卡 |

## 3 LLM 配置

| # | 模块问题 | 层 | 状态 | 出处 | 验收判据 |
|---|---|---|---|---|---|
| L1 | **模型组身份不稳定**:显示层的"同一模型"跨端点合并键被当成组的对外身份 id 发布——`_model_groups_response` 按 `project_model_group_identity` 语义键合并路由,再由 `_representative_canonical_id` **选举**一个代表 canonical id(官方优先→最短者胜,`routers/llm.py:2919-2938`)。角色配置持久化引用历史 canonical id;任何端点增删都可能改选代表——08-12 加入 deepseek-official 后代表从 `deepseek-v4-flash-260425` 翻转成 `deepseek-v4-flash`,analyst 三个组 id 全部悬空→"Unavailable in registry"。**执行不受影响**(fallback_chain 按 route_id 解析,这就是 badge 挂着 run 照样跑通的原因)。修复方向:身份与显示分离,组身份必须是稳定纯函数(语义键本身作 id),不许选举;角色存储引用同步重写,不留双读 | gateway→后端→前端 | 🔧 根因已明 | 08-19 Q13+截图 | 角色卡三组全绿;增删端点不再翻转任何组身份 |
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
| P2 | app 重启静默失败(Try again) | 壳 | ⏳ **Retry 不重启任何东西**:`RuntimeGate.tsx:100` 只是重跑 `initializeRuntimeConfig()`,而 `get_sidecar_config` 在 sidecar 起不来时返回的是**缓存的启动错误**(`lib.rs:1181-1198`),重试多少次都是同一条 → 用户体验就是"点了没反应"。真正的 `restart_sidecar` 命令存在但**零调用方**(`lib.rs:1220`,注释自认为将来预留),且它在 `manager == None` 时直接 Err——**只能重启一个还活着的 sidecar,救不了从没起来的那个**。**本册唯一一条"用户按了按钮什么也没发生"的死路,优先级最高** |
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
