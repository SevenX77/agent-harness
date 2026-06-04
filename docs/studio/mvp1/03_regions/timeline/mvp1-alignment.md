# timeline MVP1 Alignment

## 定义

`timeline` owns time-based runtime inspection: run/predict history, live trace stream, run-after full trace timeline, prompt inspector entry, model comparison tabs, and selected run summary.

Source workflow basis: `01_workflows/04_run-and-verify.md:75`, `01_workflows/04_run-and-verify.md:79`, `01_workflows/04_run-and-verify.md:83`.

## 接口契约

- Inputs: current skill id, selected run id, live websocket events, persisted trace.
- Outputs: selected run/focus changes, compare/golden actions, prompt inspector open, editor trace document open.
- Capability links: `run-execution`, `trace-observability`, `golden-eval`, `debug-resume`.

## F1. Run/Predict History List

- 机制: list predict and run attempts with status, timing, token metrics, and detail entry.
- 决策: run-after review starts from a run_id row.
- 原话/来源: `01_workflows/04_run-and-verify.md:52` lists run history; `01_workflows/04_run-and-verify.md:81` defines clicking a run to see summary.
- 测试: run row opens selected run summary; refresh updates rows; empty state is clear.
- Status: run list live, detail click missing.
- 归属: region `timeline`; capability `run-execution`.

## F2. Live Trace Auto-open

- 机制: starting Run opens the timeline/trace panel and streams events.
- 决策: user should see tracing live while the graph runs.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` and `01_workflows/04_run-and-verify.md:86` define live trace.
- 测试: Run opens panel; events append live; reconnection does not duplicate events.
- Status: orphan.
- 归属: region `timeline`; capability `trace-observability`.

## F3. Full Trace Timeline And Editor

- 机制: from a run summary, open full timeline and formatted read-only editor document.
- 决策: full trace is human-readable and lightly formatted.
- 原话/来源: `01_workflows/04_run-and-verify.md:81` and `01_workflows/04_run-and-verify.md:104` define this behavior.
- 测试: full trace action opens both timeline and editor; payload truncation is visible and expandable.
- Status: target-design.
- 归属: region `timeline`; region `editor`; capability `trace-observability`.

## F4. Prompt Inspector

- 机制: clicking an LLM call opens Template/Variables/Rendered prompt inspector.
- 决策: trace should explain prompt construction, not only final output.
- 原话/来源: `01_workflows/04_run-and-verify.md:93` lists prompt inspector.
- 测试: inspector tabs populate from event payload and close without losing timeline position.
- Status: orphan.
- 归属: region `timeline`; capability `trace-observability`.

## F5. Golden And Compare Actions

- 机制: trace/timeline can trigger compare and design-golden flows.
- 决策: golden prompts have both trace-local and sonner batch entries.
- 原话/来源: `01_workflows/04_run-and-verify.md:124` and `01_workflows/04_run-and-verify.md:137` require trace and batch entries.
- 测试: trace-local button opens one copilot chat; compare uses correct backend route.
- Status: orphan/route mismatch.
- 归属: region `timeline`; capabilities `golden-eval`, `copilot-assist`.

## F6. Model Compare Tabs

- 机制: top tabs switch between different model results for comparison.
- 决策: P8 model comparison uses top tabs.
- 原话/来源: `01_workflows/04_run-and-verify.md:98` and `01_workflows/04_run-and-verify.md:105` define this.
- 测试: tabs preserve scroll/focus and show correct model result.
- Status: target-design.
- 归属: region `timeline`; capability `trace-observability`.

## 待 PM 补 gap

- Whether predict history rows should be visually distinct from real run rows.
