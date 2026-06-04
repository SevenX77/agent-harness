# trace-observability MVP1 Alignment

## 定义

`trace-observability` owns making a graph run inspectable: live trace stream, run-after timeline, human-readable trace document, node-focused trace, edge-dot blackboard transitions, prompt inspection, and the shared event-to-node-state derivation.

Source workflow basis: `01_workflows/04_run-and-verify.md:75`, `01_workflows/04_run-and-verify.md:83`, `01_workflows/05_debugging.md:23`.

## 接口契约

- Runtime input: run_id websocket events plus persisted `trace.jsonl`.
- UI output: timeline stream/list, node status map, prompt inspector, read-only editor document, dot context.
- Engine dependency: structured phase/transition events and enough ids for loop/retry/batch grouping.
- Region links: `timeline`, `canvas`, `properties`, `editor`.
- Capability links: `run-execution`, `golden-eval`, `debug-resume`.

## F1. Live Trace While Run Is Running

- 机制: starting a run opens the trace panel and streams events, with agent output summarized/collapsible.
- 决策: agent output should feel like copilot output: summary first, details expandable.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` and `01_workflows/04_run-and-verify.md:86` define live trace; `01_workflows/04_run-and-verify.md:110` keeps the PM quote.
- 测试: live events append without duplication; agent chunks collapse/expand; source switch resets by run_id.
- Status: orphan + target-design.
- 归属: capability `trace-observability`; regions `timeline`, `canvas`.

## F2. Run-after Summary And Full Trace

- 机制: clicking a past predict/run shows run_id summary; a button opens the full timeline and a read-only formatted trace document.
- 决策: full trace must be human-readable, not raw jsonl.
- 原话/来源: `01_workflows/04_run-and-verify.md:81` defines run-after behavior; `01_workflows/04_run-and-verify.md:104` records the readable-doc decision.
- 测试: summary appears for selected run; full trace opens timeline and read-only editor; payload truncation does not crash UI.
- Status: target-design.
- 归属: regions `timeline`, `editor`; platform `engine`.

## F3. Focus Determines Trace Granularity

- 机制: blank canvas focus shows whole-run summary; node focus shows all executions for that node and jumps editor range.
- 决策: loop/retry/batch must not collapse history to the latest attempt only.
- 原话/来源: `01_workflows/04_run-and-verify.md:81` defines focus behavior; `01_workflows/04_run-and-verify.md:105` clarifies blank canvas versus node focus.
- 测试: node with three attempts shows all three grouped executions; blank focus returns to run summary.
- Status: target-design, engine id dependency.
- 归属: capability `trace-observability`; regions `canvas`, `timeline`, `editor`.

## F4. Edge Dot Blackboard Transition

- 机制: clicking the dot between nodes shows blackboard state and all operations between upstream end and downstream start.
- 决策: dot is the between-node state-machine transition point.
- 原话/来源: `01_workflows/04_run-and-verify.md:76` defines dot semantics; `01_workflows/04_run-and-verify.md:109` keeps the PM wording.
- 测试: dot shows reducer/filter/inject/persist operations for the selected run; parallel branches show shared filtered input.
- Status: placeholder/mock.
- 归属: rendering `graph-authoring`/`canvas`; data `trace-observability`.

## F5. Prompt Inspector

- 机制: selecting an LLM call opens Template, Variables, and Rendered prompt views.
- 决策: PM needs to inspect why a model saw what it saw, without leaving the trace flow.
- 原话/来源: `01_workflows/04_run-and-verify.md:93` lists the prompt inspector action.
- 测试: llm_call event opens inspector with all three tabs populated.
- Status: orphan.
- 归属: capability `trace-observability`; region `timeline`.

## F6. Event To Node State Deriver

- 机制: trace events derive canvas node state for run progress and debug red/resume affordances.
- 决策: this belongs to trace because it interprets runtime events into node view state.
- 原话/来源: `01_workflows/04_run-and-verify.md:106` and `01_workflows/05_debugging.md:25` assign the derivation to trace.
- 测试: running/success/error/paused states match event order and reset between runs.
- Status: target-design.
- 归属: capability `trace-observability`; capabilities `run-execution`, `debug-resume`; region `canvas`.

## 待 PM 补 gap

- Exact visual density for long trace documents and maximum auto-expanded payload size.
