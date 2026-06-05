---
module: 03_regions/timeline
doc: mvp1-alignment
status: drafted（TimelinePanel 只列历史 run；TracePanel/PromptInspector/RunDetailDrawer/useRunStream 都存在但未挂主流程 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [compile-lint-structured-error, trace-dot-blackboard, run-execution-node-status]
aligns_with: 01_workflows/04_run-and-verify.md（run history / trace）· 01_workflows/03_compile.md（compile drawer coordination）
---

# timeline — MVP1 Alignment

> **Tier**: region | **Owns**: `trace-dot-blackboard` inspector/timeline 切面 + `run-execution-node-status` 历史/trace 显示 + `compile-lint-structured-error` 布局协调切面 | **现状**: TimelinePanel 只列历史 run；TracePanel/PromptInspector/RunDetailDrawer/useRunStream 都存在但未挂主流程 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `trace-observability` · `run-execution` · `compile-lint` · `golden-eval` · `copilot-assist`

## 1. 定义
`timeline` owns time-based runtime inspection: run/predict history, live trace stream, run-after full trace timeline, prompt inspector entry, model comparison tabs, and selected run summary.

Source workflow basis: `01_workflows/04_run-and-verify.md:75`, `01_workflows/04_run-and-verify.md:79`, `01_workflows/04_run-and-verify.md:83`.

## 2. 数据流 / 机制（设计细节）
### F1. Run/Predict History List

- 机制: list predict and run attempts with status, timing, token metrics, and detail entry.
- 决策: run-after review starts from a run_id row.
- 原话/来源: `01_workflows/04_run-and-verify.md:52` lists run history; `01_workflows/04_run-and-verify.md:81` defines clicking a run to see summary.
- 测试: run row opens selected run summary; refresh updates rows; empty state is clear.
- Status: run list live, detail click missing.
- 归属: region `timeline`; capability `run-execution`.

### F2. Live Trace Auto-open

- 机制: starting Run opens the timeline/trace panel and streams events.
- 决策: user should see tracing live while the graph runs.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` and `01_workflows/04_run-and-verify.md:86` define live trace.
- 测试: Run opens panel; events append live; reconnection does not duplicate events.
- Status: orphan.
- 归属: region `timeline`; capability `trace-observability`.

### F3. Full Trace Timeline And Editor

- 机制: from a run summary, open full timeline and formatted read-only editor document.
- 决策: full trace is human-readable and lightly formatted.
- 原话/来源: `01_workflows/04_run-and-verify.md:81` and `01_workflows/04_run-and-verify.md:104` define this behavior.
- 测试: full trace action opens both timeline and editor; payload truncation is visible and expandable.
- Status: target-design.
- 归属: region `timeline`; region `editor`; capability `trace-observability`.

### F4. Prompt Inspector

- 机制: clicking an LLM call opens Template/Variables/Rendered prompt inspector.
- 决策: trace should explain prompt construction, not only final output.
- 原话/来源: `01_workflows/04_run-and-verify.md:93` lists prompt inspector.
- 测试: inspector tabs populate from event payload and close without losing timeline position.
- Status: orphan.
- 归属: region `timeline`; capability `trace-observability`.

### F5. Golden And Compare Actions

- 机制: trace/timeline can trigger compare and design-golden flows.
- 决策: golden prompts 有 trace-local 入口;**批量入口 = Copilot 分析 bar**(不在 timeline,归 `copilot-assist` F7),旧 sonner 批量已被取代。
- 原话/来源: `01_workflows/04_run-and-verify.md:124` and `01_workflows/04_run-and-verify.md:137` require trace and batch entries.
- 测试: trace-local button opens one copilot chat; compare uses correct backend route.
- Status: orphan/route mismatch.
- 归属: region `timeline`; capabilities `golden-eval`, `copilot-assist`.

### F6. Model Compare Tabs

- 机制: top tabs switch between different model results for comparison.
- 决策: P8 model comparison uses top tabs.
- 原话/来源: `01_workflows/04_run-and-verify.md:98` and `01_workflows/04_run-and-verify.md:105` define this.
- 测试: tabs preserve scroll/focus and show correct model result.
- Status: target-design.
- 归属: region `timeline`; capability `trace-observability`.

## 3. 接口契约
- Inputs: current skill id, selected run id, live websocket events, persisted trace.
- Outputs: selected run/focus changes, compare/golden actions, prompt inspector open, editor trace document open.
- Capability links: `run-execution`, `trace-observability`, `golden-eval`, `debug-resume`.

## 4. 设计决策基础（PM 原话）
- predict 历史行**仅用 icon 与真实 run 行区分**,其余样式一致。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| TIMELINE-1 | live trace | 对齐 `compile-lint-structured-error` 设计单元，保证 region 切面能被测试回扣 |
| TIMELINE-2 | run detail | 对齐 `compile-lint-structured-error` 设计单元，保证 region 切面能被测试回扣 |
| TIMELINE-3 | golden actions | 对齐 `compile-lint-structured-error` 设计单元，保证 region 切面能被测试回扣 |

## 6. 测试关键点
1. live trace: baseline 现状为 TracePanel/useRunStream 未挂主流程 ⚠️；目标为 run/predict 时 Timeline 自动打开 live trace。
2. run detail: baseline 现状为 RunDetailDrawer 不由 row 打开 ⚠️；目标为 row 可开 detail/replay/compare/export。
3. golden actions: baseline 现状为 旧 sonner/batch copilot 入口残留 ⚠️；目标为 golden analysis 入口为 Copilot analysis bar，Timeline 只提供 compare/detail。

## 7. 涉及 region / platform
`trace-observability` · `run-execution` · `compile-lint` · `golden-eval` · `copilot-assist`

## 8. gaps / 报警
- 🚨 live trace: TracePanel/useRunStream 未挂主流程 ⚠️；目标 run/predict 时 Timeline 自动打开 live trace。
- 🚨 run detail: RunDetailDrawer 不由 row 打开 ⚠️；目标 row 可开 detail/replay/compare/export。
- 🚨 golden actions: 旧 sonner/batch copilot 入口残留 ⚠️；目标 golden analysis 入口为 Copilot analysis bar，Timeline 只提供 compare/detail。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `trace-observability` · `run-execution` · `compile-lint` · `golden-eval` · `copilot-assist`
