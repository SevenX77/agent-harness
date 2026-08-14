---
module: 02_capabilities/trace-observability
doc: mvp1-alignment
status: FROZEN（2026-07-02 按代码核对:TracePanel 已挂 timeline 主路径(active run 流式)、EdgeContextView 已挂 selectedEdge、edge dot 数据 = edgeContextFromEvents 真实事件派生(假黑板已删);2026-07 对账:未跑时 dot 静态字段推断已落地(staticEdgeInference,GraphCanvas.tsx:1429-1434),双态齐备;2026-07 深核:F1 agent 折叠摘要(ToolCallSubtree/~2KB,TraceEventRow.tsx:220-280)与 F5 PromptInspector 三视图(Workspace.tsx:2688/TimelinePanel.tsx:153)均已 live,旧 orphan 过时。；目标结构已按 R4-R8 retrofit；2026-07-16 增补:F7 LLM fallback 可见性落地(纯前端消费 gateway llm_fallback 事件,PM 排队单第一优先)；2026-08-09 决议改写:F3 聚焦语义由「过滤收窄」改为「滚动定位」(D2 作废原过滤语义)、F2 删除 Full Trace 独立文档面(D1)、新增 F8 顶条形态(D3/D9)；2026-08-09 第二轮:呈现单位改为步骤(新增 F9,D4/D6)、F5 由独立 Prompt Inspector 改为步骤内三段(D5 删除该组件)、F1 补上「开始即可见」的时机契约）
binds_baseline: ./baseline.md
units: [trace-dot-blackboard, run-execution-node-status]
aligns_with: 01_workflows/04_run-and-verify.md（trace / run observability）· 01_workflows/05_debugging.md（debug trace）
---

# trace-observability — MVP1 Alignment

> **Tier**: capability | **Owns**: `trace-dot-blackboard`（dot/黑板语义）+ `run-execution-node-status` 的事件消费切面 | **现状**: TracePanel 已挂 timeline 主路径(Panels.tsx:active run→TracePanel/无 run→TimelinePanel),EdgeContextView 已挂 selectedEdge 分支;dot 数据真实事件派生;2026-07 对账:未跑时 dot 静态字段推断已落地(staticEdgeInference,GraphCanvas.tsx:1429-1434),双态齐备。 | **Related**: [baseline](./baseline.md)（双向）· `canvas` · `timeline` · `properties` · `debug-resume` · `state-engine` · `engine` observability

## 1. 定义
`trace-observability` owns making a graph run inspectable: live trace stream, run-after timeline, human-readable trace document, node-focused trace, edge-dot blackboard transitions, prompt inspection, and the shared event-to-node-state derivation.

Source workflow basis: `01_workflows/04_run-and-verify.md:75`, `01_workflows/04_run-and-verify.md:83`, `01_workflows/05_debugging.md:23`.

## 2. 数据流 / 机制（设计细节）
### F1. Live Trace While Run Is Running

- 机制: starting a run opens the trace panel and streams events。呈现单位是**步骤**而不是事件行(见 F9):
  一步在**开始时就出现并默认展开**,显示这一步在做什么(LLM 步骤显示模板/变量/渲染后 prompt,
  工具步骤显示工具名与入参);**完成后就地转为完成态并自动折叠**为一行摘要(模型 / token / 耗时 / 结果)。
- 决策: agent output should feel like copilot output —— PM 原话「running的时候…要把每一步具体做了什么都流式的显示出来,
  就和copilot一样。不要直接显示折叠结果,而是和copilot一样,等完成后再折叠」(2026-08-09)。
  关键在**时机**不在信息量:一次 LLM 调用是一次运行里最慢的一段,而它期间面板此前一个字都不说,
  等结束才打印一条完成摘要——看起来就是死的。**注意本轮不做 token 级流式**(引擎的 LLM 调用路径没有
  token 流,见决议 §4「明确不做」);做到的是「开始即可见」,不是逐字打字机。
- 原话/来源: `01_workflows/04_run-and-verify.md:79` and `01_workflows/04_run-and-verify.md:86` define live trace; `01_workflows/04_run-and-verify.md:110` keeps the PM quote.
- 测试: live events append without duplication; agent chunks collapse/expand; source switch resets by run_id.
- Status: live(2026-07 对账:TracePanel 已挂 live 路径,`handleRun`→`setActivePanel("timeline")`(Workspace.tsx:2172);agent 输出折叠已实现——tool_call 按语义 verb 分类 + args→result 子树(ToolCallSubtree,TraceEventRow.tsx:220-243),长 payload 默认折叠 ~2KB head 带展开钮(GenericPayload,TraceEventRow.tsx:255-280 / `TRACE_PAYLOAD_AUTO_EXPAND_BYTES=2048` utils/trace.ts:119);旧 orphan 已过时)。
- 归属: capability `trace-observability`; regions `timeline`, `canvas`.

### F2. Run-after Summary And Full Trace

- 机制: clicking a past predict/run shows run_id summary; a button opens the full timeline and a read-only formatted trace document.
- 决策: 运行记录必须人类可读,不是裸 jsonl;必须**完整**——长值折叠可展开,不做不可恢复的截断。
  2026-08-08 曾把职责拆成两个面(Trace 定位 / Full Trace 通读),**2026-08-09 决议 D1 撤销该拆分并删除 Full Trace**:
  两个面读的是同一份事件,拆开只是同一件事做了两遍,且「哪个面是真相」不可判定。
  定位与通读现由**同一个 Trace 视图**同时承担——搜索与筛选是用户主动的取景,聚焦只滚动不删减(见 F3)。
- 原话/来源: `01_workflows/04_run-and-verify.md:81` defines run-after behavior; `01_workflows/04_run-and-verify.md:104` records the readable-doc decision.
- 测试: summary appears for selected run; full trace opens as a grouped read-only document (no editor chrome); an oversized value is kept whole and expandable rather than truncated.
- Status: 部分 live(2026-08-07 viewed-run 决议:列表点某次 → 该 run 完整 trace 视图(一次性拉取,与 Full Trace 文档/PromptInspector 共读同一事件缓存,修复「Full Trace 永远读实时流」的脱钩);predict 行以 RunMetadata.kind 判别。2026-08-08 决议:Full Trace 去 Monaco 化为按节点分块的排版文档、删除 1200 字符硬截断(长值折叠可展开);predict 与已完成 run 的事件流由 `stream_run` 从该 run 目录回放,不再因内存 record 消失而失联。仍 target-design:run_id 概要中间层、从 trace 行跳到文档对应状态)。
- 归属: regions `timeline`, `editor`; platform `engine`.

### F3. 选中即范围(2026-08-13 决议 D6,推翻 2026-08-09 D2)

- 机制: **画布选中态 = trace 显示范围**。选中节点 → 只显示该节点的事件(边事件按 `to_phase`
  归属);选中边 → 只显示该边的边操作事件(见 F4);选中 Input → 离开输入边界的派发事件;
  选中 Output → 到达输出边界的事件;**点空白 = 全量**。范围过滤的唯一实现是
  `utils/trace-scope.ts` 的 `eventInScope`;trace 面板头部显示当前范围 chip
  (`data-trace-scope`,文案 = `scopeLabel`,与画布命名一致)并带**一键清除**按钮,
  清除 = 与点空白同一条 `handleNodeDeselect`(全部选中态一起清)。run 级派生
  (verdict 徽章 / 结局行 / 降级计数)**不受范围影响**——范围只窄化列表。
- 决策: 本条**推翻** 2026-08-09 D2 的「聚焦只定位不过滤」,且当年的反对理由被正面化解:
  「不可见」→ 过滤严格绑定可见的画布选中环 + 面板头部范围 chip;「不可关」→ chip 一键清除、
  点空白回全量。两次裁决都在案:2026-08-09 删的是无锚点的隐形过滤,2026-08-13 立的是
  锚点即选中态、状态可见、一键可退的范围机制。
- 原话/来源: `docs/design/2026-08-13-trace-goes-glass-box-decision.md` §D6(含对 D2 的正面回应);
  历史脉络 `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` §D2。
- 测试: `utils/trace-scope.test.ts`(各范围的准入规则)、`TracePanel.test.tsx`
  (chip 呈现/清除按钮/节点范围窄化/边范围含 tamper 区/无范围无 chip)。
- Status: live(2026-08-14 落地)。
- 归属: capability `trace-observability`; regions `canvas`, `timeline`.

### F8. Trace 顶条只回答两个问题

- 机制: 顶条自左至右只有四件:`←` 返回运行列表 · **完整 run_id**(等宽,不截断,溢出靠 CSS 截断且 `title` 保留全文)·
  **状态图标徽章**(成功 ✓ / 失败 ✗ / 暂停 ⏸ / 取消 ✗,不带文字,文字进 tooltip;运行中保留脉冲点,
  因为「还在跑」是静态图标表达不了的持续态)· `⋮` run 级动作菜单(Resume / Compare to golden / Promote to golden)。
  predict 运行在 run_id 左侧加**烧瓶图标**(`FlaskConical`),与运行列表、全站其他 predict 标识同一个图标。
- 决策: 顶条只回答「这是哪一次运行」和「它现在怎么样」;其余曾经挤占该行的元素都已删除——
  `Trace` 标题(视图名两条挂载路径下恒被 run_id 取代,是够不着的兜底)、`Predict` 文字徽章(改图标)、
  收窄提示与 link 开关(过滤行为本身已按 D2 删除)、run_id 重复出现在 `⋮` 菜单里的那一份。
  状态用图标不用词,是因为文字状态在窄面板里与 run_id 争同一行宽度,而 run_id 是不可缩写的那个。
- 原话/来源: `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` §D3 / §D9;
  PM 原话「顶条只显示run_id,后面跟状态徽章,状态徽章不需要一串字,用打勾、错误等原型徽章就行,加上tooltip显示文字success等」
  「predict徽章用一个图标就可以了,而且所有ui代表predict的都要统一」。
- 测试: 顶条含完整 run_id 且 `title` 为同一字符串;状态以 `aria-label` 表达而**不**渲染 `>Success<` 字样;
  predict 视图渲染 `aria-label="Predict attempt"` 而不渲染 `>Predict<` 文字;无 run 级动作时不渲染 `⋮`。
- Status: live(2026-08-09)。
- 归属: capability `trace-observability`; region `timeline`。

### F9. 呈现单位 = 步骤(开始即出现,完成才折叠)

- 机制: 纯投影 `buildTraceSteps(events)`(`src/utils/trace-steps.ts`)把事件流合成步骤:
  - **LLM 步骤**:`prompt_captured`(开始)+ 同一节点的下一条 `llm_call`(完成)合成一条。
    按**节点**配对,因为 `prompt_captured` 不带调用 id,而同一节点的下一次完成必定属于它。
  - **工具步骤**:`tool_call_started`(开始)+ 同 `tool_call_id` 的 `tool_call`(完成)合成一条。
    按 **id** 配对而不是按位置:一个 agent 回合可以有多个调用同时在飞,谁先回来不确定
    (引擎侧契约见 PR #655 / 决议 D14)。
  - 其余事件各自成一条,形态不变;**只有完成半边、没有开始半边**的事件也自成一条完成态步骤
    (筛选会藏掉开始半边,答案是显示手上这半边,而不是把事件丢掉)。
- 默认展开态由**步骤状态**决定:进行中默认展开,完成默认折叠;**用户的手动切换优先**且此后一直生效
  (只记录被显式切换过的步骤,其余跟随状态,所以完成时会自动折叠而不会推翻读者的选择)。
- 分组沿用 2026-08-08 D3:相邻步骤同节点时只在组首标一次节点名。
- 中间结果**不设固定高度框**(D6):删掉工具输入的 `max-h-32` 与 payload 的 `max-h-40` 内层滚动。
  面板本身已有滚动,嵌套滚动更难读;超长内容靠折叠/展开(用户可控),不靠固定高度截断(强加)。
- 原话/来源: 决议 D4 / D6;PM 原话「tracing里面的中间结果不要用一个固定高度的框框住,本来panel就有scroll」。
- 测试: 只有 `prompt_captured` 时步骤为 running 且 `end` 为空;补上 `llm_call` 后合成一条 done;
  一个节点的答复不会关掉另一个节点的 prompt;两个工具调用在飞时按 id 各自关闭;
  列表里 running 步骤 `aria-expanded="true"`、done 步骤 `false`。
- Status: live(2026-08-09)。
- 归属: capability `trace-observability`; region `timeline`; platform `engine`(`tool_call_started` 半边)。

### F4. 边点 = 边的步骤(2026-08-13 决议 D5,改组 2026-07-02 双态方案)

- 机制: 点边 dot = 选中这条边 = trace 范围收窄到这条边(F3 的 edge 范围),此时列表里的
  行**就是**这条边的操作步骤——`input_dispatch` / `blackboard_reduce` /
  `input_file_injected` 按 `from_phase`/`to_phase` 归边,`artifact_saved` 按上游
  `phase_name` 归边——与节点步骤同一套行样式(M1 折叠原语),不再有第二套"边专用"呈现。
  面板中随范围 chip 保留的是 `EdgeTamperSection`,承载两件 trace 行给不了的东西:
  - **未跑前(静态推断)**:像节点 io 一样给出该边的黑板字段推断——"graph 跑到这个 dot
    时,黑板上应该有哪些字段"。推导规则与编译期数据流校验同源:该边可用字段 = 根
    `io.inputs` ∪ 下游节点全部上游祖先 phase 的 `io.outputs` ∪ runtime_config 中该
    phase 的 import binding 注入字段 ∪ iterate/batch 注入字段;同名顺序覆盖
    (`allow_sequential_overwrite`)取最近祖先;并标出下游节点将按其 `io.inputs` 切走
    哪些字段。没跑过就没有事件,trace 行天然空白——静态推断正是补这块的。
  - **篡改黑板续跑(操作,不是展示)**:`EdgeTamperEditor` 编辑该边派发的黑板 JSON 并从
    checkpoint 恢复下游,这是一个动作入口,不属于事件流呈现,留在面板。
- 决策: dot 仍是节点间状态机转换点(2026-07-02 语义不变),但**运行期"真实快照/操作记录"
  的呈现载体从独立的 EdgeContextView 面板改组为 trace 行本身**(D5:"边点显示 phase 间
  步骤,与节点步骤同样式")。理由:边操作本来就是事件流里的事件,再养一个平行面板等于同一
  信息两处呈现、两处要同步;`EdgeContextView.tsx` 已删除,不重建。
- 原话/来源: `docs/design/2026-08-13-trace-goes-glass-box-decision.md` §D5;
  `01_workflows/04_run-and-verify.md:76` defines dot semantics;PM 2026-07-02 原话
  (静态推断 + 运行期都要)继续有效,变的只是运行期呈现的载体。
- 测试: `trace-scope.test.ts`(边范围恰好收进该边的边操作事件、`artifact_saved` 归上游、
  Input 边界边接受 null `from_phase`);`EdgeTamperSection.test.tsx`(静态推断体 / tamper
  编辑器 / 无记录时的诚实空态);`TracePanel.test.tsx`(边范围时 tamper 区出现在范围 chip 下)。
- Status: live(2026-08-14:EdgeContextView 删除,EdgeTamperSection + edge 范围接管;
  静态推断 lib/edge-static-inference.ts 不变)。
- 归属: rendering `graph-authoring`/`canvas`; data `trace-observability`.

### F5. Prompt 就在它自己的步骤里(原 Prompt Inspector 已删除)

- 机制: 展开一条 LLM 步骤,就地看到 **Template / Variables / Rendered** 三段(以及完成后的 Response);
  数据分别来自 `prompt_captured` 的 `template_source` / `variables` / `resolved_prompt`
  (无 `prompt_captured` 半边时退到 `llm_call.messages`)。**没有第二个入口**——
  没有 "Inspect prompt" 链接,没有独立弹窗。
- 决策: 2026-08-09 D5 **删除 `components/PromptInspector.tsx` 及 `promptIndex` / `findPromptEvent` 整条链**。
  理由是 F9 落地后 prompt 本来就要在步骤开始时展示——PM 原话「这个prompt inspect是什么东西?
  不要搞那么复杂,如果显示清楚每一步做了什么,就能直接从tracing里面看到具体的prompt,不用搞特殊化」。
  一个信息只有一个家:两个入口意味着两处要同步、两处会不一致。
- 原话/来源: 决议 `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D5;
  上述 PM 原话(2026-08-09)。本条**取代** `01_workflows/04_run-and-verify.md:93` 的独立 inspector 动作。
- 测试: 展开的 LLM 步骤同时含 Template / Variables / Rendered 三段与其内容;
  任何步骤都不再渲染 "Inspect prompt"。
- Status: live(2026-08-09)。
- 归属: capability `trace-observability`; region `timeline`.

### F6. Run Status Projection(状态投影 SSOT,2026-08-13 决议 D7)

- 机制: 前端模块 `utils/run-status-projection` 是把 `(事件流, run 记录)` 折叠成一切
  派生运行状态的**唯一出口**——画布节点灯、trace 步骤行、顶条/run 列表徽章全部消费它,
  不允许第二份推导逻辑。裁决函数 `runVerdict(events, metadata)`:落章的 run 记录终态
  优先(流只知道 worker 停了,记录才知道那次停是 cancelled 还是 paused),其次取最后
  一条流式 `run_ended`(resumed run 结束多次,只有最后一次描述读者所见),两者皆无 = running。
  第二真相通道的来源:`run_ended` 后的终态回读、以及 stop/pause 请求返回的 canonical
  记录快照(成功写返回权威快照,属 SSOT 读取原则允许的 revalidation 触发)。
- **铁律: run 到终态 ⇒ 任何派生状态不得为 running。** 缺结束帧(worker 被杀、流先死)
  不是「永远转圈」的理由——记录终态本身就是最后的裁决输入。
- 消费组件「状态 → 显示效果」对照表(各自用测试锁死):
  - **画布节点**(`NODE_STATUS_AT_RUN_END`,`run-status-projection.test.ts` 锁):
    verdict success → 节点 success;failed → error;cancelled → paused(用户止损不是节点失败);
    paused → paused。
  - **trace 步骤行**(`trace-steps.test.ts` + `TraceStepRow.test.tsx` 锁):
    running → 旋转 spinner + 自动展开;done → 落定行,无标记;终态 verdict 下未闭合的
    步骤 = **severed** →「never completed」灰 chip、无 spinner(不是 done:读者应看见
    「它没做完」,而不是一个看似完整的摘要)。paused 不 sever——步骤是挂起不是死亡,
    resume 的闭合半帧仍会配对。
  - **顶条/run 列表徽章**(`runStatusMark`,`run-status-mark.test.ts` 锁):
    running → 进行中;success → Run succeeded;failed → Run failed;paused → Run paused;
    cancelled → Run cancelled。live 且 running 时顶条显脉冲点(F8 形态不变)。
  - **结局行**(`trace-outcome.test.ts` 锁):只有真终态(success/failed/cancelled)产生
    结论条目;running/paused 无结论。流侧孤立的 `interrupted` 不武断下结论,等记录落章。
- 决策: this belongs to trace because it interprets runtime events into node view state;
  D7 把它从「trace 内一处推导」升格为跨表面 SSOT,收编原 `node-status.ts` 独立分支与
  `buildTraceSteps` 无闭合输入两处旧推导(B8)。
- 原话/来源: `docs/design/2026-08-13-trace-goes-glass-box-decision.md` §D7;
  `01_workflows/04_run-and-verify.md:106` 与 `01_workflows/05_debugging.md:25` 把派生归属 trace。
- 测试: `run-status-projection.test.ts`(裁决优先级 + 铁律 + 节点闭合表)、
  `run-status-projection.derived.test.ts`(迁移的逐事件派生回归)、
  `trace-steps.test.ts`(severed)、`TraceStepRow.test.tsx`(三态视觉)、
  `run-status-mark.test.ts`(徽章表)、`trace-outcome.test.ts`(结论门槛)。
- Status: live(2026-08-14 落地)。
- 归属: capability `trace-observability`; capabilities `run-execution`, `debug-resume`; region `canvas` + `timeline`.

### F7. LLM Fallback Visibility

- 机制: gateway 的 `llm_fallback` 事件（provider route 失败、同 role 兜底 route 接手时发射）作为一等 trace UI 渲染：事件行人话化消息（`LLM fallback: A → B`；`to_provider='<none>'` 显 `failed — no remaining route`）、琥珀 warning 徽章/时间线圆点、FallbackBlock（`context.from_route/to_route` 的 provider_model_id 双模型 + 失败原因 + role + HTTP 码）、run 级 fallback 计数 chip（点击经 trace 类型过滤器只看降级事件）、模型 chip（`prompt_captured`/`model_resolved` 的 `resolved_model` = 解析时真值，`llm_call.response_data.model_name` = provider 回报的 post-call 真值，PromptInspector 标题同显）。纯前端消费：事件链 gateway emit（`call/chat_model.py` 三处）→ studio `run_manager._queue_event_subscriber` → WS + trace.jsonl 此前已 live，本条零后端改动。
- 决策: 降级不可见则模型对比不可信——run 可能静默从模型 A 降到模型 B，用户拿着 B 的产物当 A 的结论。因此任何 LLM 对比类功能之前必须先落本条（PM 排队单 2026-07-16 第一优先）。
- 原话/来源: PM 排队单 2026-07-16「用户做模型对比时可能『以为测的是模型 A、实际已降级到 B』而不自知」；事件契约 `graph_agent_gateway/events.py` LLMFallbackEvent（code `[F-v3-gateway-llm-fallback]`）。
- 测试: `utils/trace.test.ts`（message/color/details 解析/count/模型名三来源）、`TraceEventRow.fallback.test.tsx`（FallbackBlock/exhausted/模型 chip）、`TracePanel.test.tsx`（run 级 chip 单复数与 aria-label）、`PromptInspector.test.tsx`（标题模型 chip）。
- Status: live（2026-07-16 落地：utils/trace.ts `llmFallbackDetails`/`countLlmFallbacks`/`eventModelName` + TraceEventRow FallbackBlock + TracePanel fallback chip + PromptInspector 模型 chip；活跑与历史回看共用同一渲染链）。
- 归属: capability `trace-observability`; region `timeline`.

## 3. 接口契约
- Runtime input: run_id websocket events plus persisted `trace.jsonl`.
- UI output: timeline stream/list, node status map, prompt inspector, dot context。(独立的只读文档面已按 2026-08-09 D1 删除,见 F2。)
- Engine dependency: structured phase/transition events and enough ids for loop/retry/batch grouping.
- Region links: `timeline`, `canvas`, `properties`, `editor`.
- Capability links: `run-execution`, `golden-eval`, `debug-resume`.

## 4. 设计决策基础（PM 原话）
- 长 trace **默认折叠大块**;折叠机制按 2026-08-13 决议 D3(`docs/design/2026-08-13-trace-goes-glass-box-decision.md`)为**按行三态**:收起显示 5 行(一眼识别这段是什么)→ 展开显示 20 行 → 点链接进 Monaco 只读视图看全文。唯一实现是共享原语 `components/ui/folded-text`(超长单行按显示行折算,禁止任何 trace 表面自造折叠;原「自动展开 payload 上限 ~2KB」的字节阈值机制被本条取代,「默认折叠大块」的原则不变)。
- 2026-08-13 D1:展开的 LLM 步骤按**执行顺序**渲染子条目——装载 prompt(`template_source`)→ 渲染后 prompt → 思考(`response_data.reasoning`)→ 回答 / 工具 → 设置 / 路由判定;废除 TEMPLATE / VARIABLES 特殊容器。agent phase 内按 Iteration 分层(数据源 `agent_loop_iteration` + `prompt_captured.loop_index`,纯前端投影)。机器自述事件(`finish_task_verdict` / `loop_detected` / `protocol_violation` 等,决议 D4)以通用语义行渲染:行首整句 `message`,展开显示 `details` 管线叙述与 `errors`/`violations` 原因列表。
- 2026-08-09:「full trace删掉,功能重复,本来就应该显示full tracing」——通读职责回到 Trace 自身(F2/F3)。
- 2026-08-09:「顶条只显示run_id,后面跟状态徽章,状态徽章不需要一串字,用打勾、错误等原型徽章就行,加上tooltip显示文字success等」(F8)。
- 2026-08-09:「predict徽章用一个图标就可以了,而且所有ui代表predict的都要统一」(F8)。
- 2026-08-09:「running的时候,timeline的显示要和copilot一样显示动态过程啊,内部处理的过程显示太少了,要把每一步具体做了什么都流式的显示出来,就和copilot一样。不要直接显示折叠结果,而是和copilot一样,等完成后再折叠」(F1/F9)。
- 2026-08-09:「tracing里面的中间结果不要用一个固定高度的框框住,本来panel就有scroll」(F9)。
- 2026-08-09:「这个prompt inspect是什么东西?不要搞那么复杂,如果显示清楚每一步做了什么,就能直接从tracing里面看到具体的prompt,不用搞特殊化」(F5)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| TRACE_OBSERVABILITY-1 | trace 挂载 | 单元 `trace-dot-blackboard`；**为什么**：TracePanel/useRunStream 已建但零挂载(zombie)，要接线成 live trace |
| TRACE_OBSERVABILITY-2 | dot 黑板 | 单元 `trace-dot-blackboard`；**为什么**：边 dot 现假黑板，要换真实黑板 state card + 只读编辑器查看 |
| TRACE_OBSERVABILITY-3 | 节点态 | 单元 `run-execution-node-status`；**为什么**：事件→节点态投影的实现归共享 state(state-engine)，trace 只拥有语义 |

## 6. 测试关键点
1. trace 挂载: TracePanel 已挂 timeline 主路径(active run 流式,结束回 TimelinePanel 历史);agent 分类折叠摘要已实现(ToolCallSubtree verb 分类 + ~2KB 折叠,TraceEventRow.tsx:220-280);PromptInspector 三视图已挂 live+历史两路径(F1/F5 旧 orphan 标注已过时,2026-07 对账)。
2. dot 黑板: 双态均 live——运行期真实事件派生(edgeContextFromEvents,mock 已删)+ 未跑期静态字段推断(staticEdgeInference,前端按拓扑 + io 声明 + runtime_config 推导,GraphCanvas.tsx:1429-1434 / lib/edge-static-inference.ts:139);跑后打开真实 transition blackboard / before-after。(2026-07 对账:旧"未跑时仅空态"已落地静态推断。)
3. 节点态: baseline 现状为 event -> node state 派生未成统一源；目标为 state-engine 消费 trace events 并投影 canvas/timeline。

## 7. 涉及 region / platform
`canvas` · `timeline` · `properties` · `debug-resume` · `state-engine` · `engine` observability

## 8. gaps / 报警
- ✅ dot 双态已齐备(2026-07 对账清除旧报警): 未跑期静态字段推断 staticEdgeInference(lib/edge-static-inference.ts:139)+ 跑后真实 transition blackboard edgeContextFromEvents,均挂 GraphCanvas.tsx:1429-1434。(trace 挂载与 dot 真实数据 2026-07-02 已 live。)

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `canvas` · `timeline` · `properties` · `debug-resume` · `state-engine` · `engine` observability
