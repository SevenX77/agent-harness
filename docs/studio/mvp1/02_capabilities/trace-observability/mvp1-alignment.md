---
module: 02_capabilities/trace-observability
doc: mvp1-alignment
status: FROZEN（2026-07-02 按代码核对:TracePanel 已挂 timeline 主路径(active run 流式)、EdgeContextView 已挂 selectedEdge、edge dot 数据 = edgeContextFromEvents 真实事件派生(假黑板已删);2026-07 对账:未跑时 dot 静态字段推断已落地(staticEdgeInference,GraphCanvas.tsx:1429-1434),双态齐备;2026-07 深核:F1 agent 折叠摘要(ToolCallSubtree/~2KB,TraceEventRow.tsx:220-280)与 F5 PromptInspector 三视图(Workspace.tsx:2688/TimelinePanel.tsx:153)均已 live,旧 orphan 过时。；目标结构已按 R4-R8 retrofit；2026-07-16 增补:F7 LLM fallback 可见性落地(纯前端消费 gateway llm_fallback 事件,PM 排队单第一优先)）
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

- 机制: starting a run opens the trace panel and streams events, with agent output summarized/collapsible.
- 决策: agent output should feel like copilot output: summary first, details expandable.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` and `01_workflows/04_run-and-verify.md:86` define live trace; `01_workflows/04_run-and-verify.md:110` keeps the PM quote.
- 测试: live events append without duplication; agent chunks collapse/expand; source switch resets by run_id.
- Status: live(2026-07 对账:TracePanel 已挂 live 路径,`handleRun`→`setActivePanel("timeline")`(Workspace.tsx:2172);agent 输出折叠已实现——tool_call 按语义 verb 分类 + args→result 子树(ToolCallSubtree,TraceEventRow.tsx:220-243),长 payload 默认折叠 ~2KB head 带展开钮(GenericPayload,TraceEventRow.tsx:255-280 / `TRACE_PAYLOAD_AUTO_EXPAND_BYTES=2048` utils/trace.ts:119);旧 orphan 已过时)。
- 归属: capability `trace-observability`; regions `timeline`, `canvas`.

### F2. Run-after Summary And Full Trace

- 机制: clicking a past predict/run shows run_id summary; a button opens the full timeline and a read-only formatted trace document.
- 决策: full trace must be human-readable, not raw jsonl. 2026-08-08(PM):承载形态是**面板内的排版文档**,不是只读编辑器("在 panel 里面不要用编辑器的样式");且文档必须**完整**——长值折叠可展开,不做不可恢复的截断。Trace(区域内视图)负责**定位**(过滤/搜索/联动),Full Trace(文档)负责**通读与取证**(全文/分组/不过滤)。
- 原话/来源: `01_workflows/04_run-and-verify.md:81` defines run-after behavior; `01_workflows/04_run-and-verify.md:104` records the readable-doc decision.
- 测试: summary appears for selected run; full trace opens as a grouped read-only document (no editor chrome); an oversized value is kept whole and expandable rather than truncated.
- Status: 部分 live(2026-08-07 viewed-run 决议:列表点某次 → 该 run 完整 trace 视图(一次性拉取,与 Full Trace 文档/PromptInspector 共读同一事件缓存,修复「Full Trace 永远读实时流」的脱钩);predict 行以 RunMetadata.kind 判别。2026-08-08 决议:Full Trace 去 Monaco 化为按节点分块的排版文档、删除 1200 字符硬截断(长值折叠可展开);predict 与已完成 run 的事件流由 `stream_run` 从该 run 目录回放,不再因内存 record 消失而失联。仍 target-design:run_id 概要中间层、从 trace 行跳到文档对应状态)。
- 归属: regions `timeline`, `editor`; platform `engine`.

### F3. Focus Determines Trace Granularity

- 机制: blank canvas focus shows whole-run summary; node focus shows all executions for that node and jumps editor range.
- 决策: loop/retry/batch must not collapse history to the latest attempt only.
- 原话/来源: `01_workflows/04_run-and-verify.md:81` defines focus behavior; `01_workflows/04_run-and-verify.md:105` clarifies blank canvas versus node focus.
- 测试: node with three attempts shows all three grouped executions; blank focus returns to run summary.
- Status: target-design, engine id dependency.
- 归属: capability `trace-observability`; regions `canvas`, `timeline`, `editor`.

### F4. Edge Dot Blackboard Transition(双态:静态推断 + 运行期真实)

- 机制: dot 有两态,同一个 dot 面板承载:
  - **未跑前(静态推断)**:像节点 io 一样给出该边的黑板字段推断——"graph 跑到这个 dot 时,黑板上应该有哪些字段"。推导规则与编译期数据流校验同源:该边可用字段 = 根 `io.inputs` ∪ 下游节点全部上游祖先 phase 的 `io.outputs` ∪ runtime_config 中该 phase 的 import binding 注入字段 ∪ iterate/batch 注入字段;同名顺序覆盖(`allow_sequential_overwrite`)取最近祖先;并标出下游节点将按其 `io.inputs` 切走哪些字段。逐边不同,随拓扑/io 声明/runtime_config 编辑即时更新;由前端按拓扑 + 节点 io 声明 + runtime_config 推导(engine `graph-exec` E4 已把 canvas 黑板可视化划给前端,呼应本 workflow REQ-2 黑板可视化连线)。
  - **跑后(选中某次 run)**:clicking the dot shows real blackboard state and all operations between upstream end and downstream start——数据源 = engine 边操作事件族(`InputDispatchEvent`/`BlackboardReduceEvent`/`InputFileInjectedEvent`/`ArtifactSavedEvent`/`CompactionEvent`)的 `blackboard_snapshot` + `changed_keys` + `branch_index`,按 `from_phase`/`to_phase` 聚合(engine `02-observability` OB4/OB5)。
- 决策: dot is the between-node state-machine transition point;**默认显示静态推断,选中某次 run 切换为该 run 的真实快照/操作记录**(PM 2026-07-02 扩充)。
- 原话/来源: `01_workflows/04_run-and-verify.md:76` defines dot semantics; `01_workflows/04_run-and-verify.md:109` keeps the PM wording;PM 2026-07-02:"我说的不是跑过一次后拿到trace,我说的是在没跑之前,也要像node的io一样,给出一个schema推断,这个dot在这里应该会有哪些字段。当然你说的这些(运行期快照/操作记录)都要加上"。
- 测试: 未跑时 dot 显示静态字段推断且逐边不同、随 io 声明/拓扑变化即时更新;dot shows reducer/filter/inject/persist operations for the selected run; parallel branches show shared filtered input(`branch_index` 区分)。
- Status: live(双态齐备:运行期 edgeContextFromEvents + 未跑期 staticEdgeInference;GraphCanvas.tsx:1429-1434 / lib/edge-static-inference.ts:139,2026-07 对账)。
- 归属: rendering `graph-authoring`/`canvas`; data `trace-observability`.

### F5. Prompt Inspector

- 机制: selecting an LLM call opens Template, Variables, and Rendered prompt views.
- 决策: PM needs to inspect why a model saw what it saw, without leaving the trace flow.
- 原话/来源: `01_workflows/04_run-and-verify.md:93` lists the prompt inspector action.
- 测试: llm_call event opens inspector with all three tabs populated.
- Status: live(2026-07 对账:PromptInspector 已挂 live+历史两路径(Workspace.tsx:2688 / TimelinePanel.tsx:153);点 llm_call/prompt_captured 的"Inspect prompt"控件经 `findPromptEvent` 打开(TraceEventRow.tsx:51/136 · utils/trace.ts:291-306);Template/Variables/Rendered 三视图分别填 `template_source`/`variables`/`resolved_prompt|messages`(PromptInspector.tsx:55/58/62-64);旧 orphan 已过时)。
- 归属: capability `trace-observability`; region `timeline`.

### F6. Event To Node State Deriver

- 机制: trace events derive canvas node state for run progress and debug red/resume affordances.
- 决策: this belongs to trace because it interprets runtime events into node view state.
- 原话/来源: `01_workflows/04_run-and-verify.md:106` and `01_workflows/05_debugging.md:25` assign the derivation to trace.
- 测试: running/success/error/paused states match event order and reset between runs.
- Status: target-design.
- 归属: capability `trace-observability`; capabilities `run-execution`, `debug-resume`; region `canvas`.

### F7. LLM Fallback Visibility

- 机制: gateway 的 `llm_fallback` 事件（provider route 失败、同 role 兜底 route 接手时发射）作为一等 trace UI 渲染：事件行人话化消息（`LLM fallback: A → B`；`to_provider='<none>'` 显 `failed — no remaining route`）、琥珀 warning 徽章/时间线圆点、FallbackBlock（`context.from_route/to_route` 的 provider_model_id 双模型 + 失败原因 + role + HTTP 码）、run 级 fallback 计数 chip（点击经 trace 类型过滤器只看降级事件）、模型 chip（`prompt_captured`/`model_resolved` 的 `resolved_model` = 解析时真值，`llm_call.response_data.model_name` = provider 回报的 post-call 真值，PromptInspector 标题同显）。纯前端消费：事件链 gateway emit（`gateway_chat_model.py` 三处）→ studio `run_manager._queue_event_subscriber` → WS + trace.jsonl 此前已 live，本条零后端改动。
- 决策: 降级不可见则模型对比不可信——run 可能静默从模型 A 降到模型 B，用户拿着 B 的产物当 A 的结论。因此任何 LLM 对比类功能之前必须先落本条（PM 排队单 2026-07-16 第一优先）。
- 原话/来源: PM 排队单 2026-07-16「用户做模型对比时可能『以为测的是模型 A、实际已降级到 B』而不自知」；事件契约 `graph_agent_gateway/events.py` LLMFallbackEvent（code `[F-v3-gateway-llm-fallback]`）；手册设计页原子 n4-trace #29。
- 测试: `utils/trace.test.ts`（message/color/details 解析/count/模型名三来源）、`TraceEventRow.fallback.test.tsx`（FallbackBlock/exhausted/模型 chip）、`TracePanel.test.tsx`（run 级 chip 单复数与 aria-label）、`PromptInspector.test.tsx`（标题模型 chip）。
- Status: live（2026-07-16 落地：utils/trace.ts `llmFallbackDetails`/`countLlmFallbacks`/`eventModelName` + TraceEventRow FallbackBlock + TracePanel fallback chip + PromptInspector 模型 chip；活跑与历史回看共用同一渲染链）。
- 归属: capability `trace-observability`; region `timeline`.

## 3. 接口契约
- Runtime input: run_id websocket events plus persisted `trace.jsonl`.
- UI output: timeline stream/list, node status map, prompt inspector, read-only editor document, dot context.
- Engine dependency: structured phase/transition events and enough ids for loop/retry/batch grouping.
- Region links: `timeline`, `canvas`, `properties`, `editor`.
- Capability links: `run-execution`, `golden-eval`, `debug-resume`.

## 4. 设计决策基础（PM 原话）
- 长 trace **默认折叠大块**;自动展开 payload 上限 **~2KB**(超出给"展开"按钮)。

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
