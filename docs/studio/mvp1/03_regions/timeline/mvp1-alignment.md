---
module: 03_regions/timeline
doc: mvp1-alignment
status: FROZEN（2026-08-07 viewed-run 决议落地:timeline 区域三视图=历史列表/所查 run 的 Trace 视图/EdgeContext,由 Workspace viewedTrace 状态分流(Panels.tsx timeline 分支);run 结束可返回列表;predict 以 kind 判别入列;命名统一 区域=Timeline/视图=Trace/文档=Full Trace。决议:docs/design/2026-08-07-timeline-viewed-run-and-trace-ui-decision.md；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [compile-lint-structured-error, trace-dot-blackboard, run-execution-node-status]
aligns_with: 01_workflows/04_run-and-verify.md（run history / trace）· 01_workflows/03_compile.md（compile drawer coordination）
---

# timeline — MVP1 Alignment

> **Tier**: region | **Owns**: `trace-dot-blackboard` inspector/timeline 切面 + `run-execution-node-status` 历史/trace 显示 + `compile-lint-structured-error` 布局协调切面 | **现状**: viewed-run 模型已落地(2026-08-07):列表行点击进该 run 的 Trace 视图(历史一次性拉取,与 Full Trace 文档/PromptInspector 共读同一事件源),live run 流式复用同一视图并带返回;predict 行以 `RunMetadata.kind` 判别、仅 icon 区分。 | **Related**: [baseline](./baseline.md)（双向）· `trace-observability` · `run-execution` · `compile-lint` · `golden-eval` · `copilot-assist`

## 1. 定义
`timeline` owns time-based runtime inspection: run/predict history, live trace stream, run-after full trace timeline, prompt inspector entry, model comparison tabs, and selected run summary.

Source workflow basis: `01_workflows/04_run-and-verify.md:75`, `01_workflows/04_run-and-verify.md:79`, `01_workflows/04_run-and-verify.md:83`.

## 2. 数据流 / 机制（设计细节）
### F1. Run/Predict History List

- 机制: list predict and run attempts with status, timing, token metrics, and detail entry.
- 决策: run-after review starts from a run_id row.
- 原话/来源: `01_workflows/04_run-and-verify.md:52` lists run history; `01_workflows/04_run-and-verify.md:81` defines clicking a run to see summary.
- 测试: run row opens selected run summary; refresh updates rows; empty state is clear.
- Status: live(2026-08-07:行点击经 Workspace.handleSelectRun 打开该 run 的 Trace 视图;predict 行以 kind 判别入列、仅 icon(FlaskConical)区分;run 结束由 archive 效果把终态 metadata 投影回列表)。run_id 概要层仍 target-design(见 F3)。
- 归属: region `timeline`; capability `run-execution`.

### F2. Live Trace Auto-open

- 机制: starting Run opens the timeline/trace panel and streams events.
- 决策: user should see tracing live while the graph runs.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` and `01_workflows/04_run-and-verify.md:86` define live trace.
- 测试: Run opens panel; events append live; reconnection does not duplicate events.
- Status: live(gate started(predict 与 run 同权)→ follow-run + open-trace(gate-state.ts);流式列表贴底跟随走 message-scroller;返回按钮任何时刻可回列表——2026-08-07 viewed-run 决议修复「跑过一次后列表不可达」)。
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

- 机制: top tabs switch between different model results for comparison。**对比源 = 节点级候选的旁路单节点多跑**（不是整图按角色扇出）：focus 对比节点时，顶部 tab = 基准输出 + 该节点各候选的独立 run 输出；候选 = model group + route（`properties` F5 配置、Studio 后端按 skill+node 持久化）。
- 决策: P8 model comparison uses top tabs。**运行机制重定（PM 2026-07-02）**：主图用基准模型跑一次；Studio 抓对比节点在主 run 的 `InputDispatchEvent` 输入切片，把该单个 phase 物化成 `depends_on=input` 单节点临时 skill 变体 + 候选临时 roles，走现成 `run_artifact` 各跑一遍——独立单节点 run ⇒ 不改 engine 执行、永不写主黑板、per-candidate artifacts 分目录。**旧整图按角色扇出链（`CompareRunDialog` + `POST /runs/compare` fan-out + `run_compare.py`）删除**（实证坐实引擎跑不了图内并联，见 `00_settings-ux-spec.md §2.8`）。
- 原话/来源: `01_workflows/04_run-and-verify.md:98`、`01_workflows/04_run-and-verify.md:105`（顶部 tab）+ PM 2026-07-01/07-02 对比机制拍板。
- 测试: tabs preserve scroll/focus and show correct model result；对比运行产基准 + 各候选独立 run；候选 run 不改主 run final_state。
- Status: target-design（PR2 实现候选持久化 + 旁路单节点运行 + tab 接线）。
- 归属: region `timeline`; capabilities `trace-observability`、`run-execution`；候选配置 UI 归 `properties` F5。

## 3. 接口契约
- Inputs: current skill id, selected run id, live websocket events, persisted trace.
- Outputs: selected run/focus changes, compare/golden actions, prompt inspector open, editor trace document open.
- Capability links: `run-execution`, `trace-observability`, `golden-eval`, `debug-resume`.

## 4. 设计决策基础（PM 原话）
- predict 历史行**仅用 icon 与真实 run 行区分**,其余样式一致。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| TIMELINE-1 | live trace | 单元 `trace-dot-blackboard`；**为什么**：live trace 流挂 TimelinePanel，竖向时间轴(LangSmith 式) |
| TIMELINE-2 | run detail | 单元 `run-execution-node-status`（消费/落点；owner=run-execution/state-engine）；**为什么**：run row 开 RunDetailDrawer，run 历史归 timeline |
| TIMELINE-3 | golden actions | 单元 `golden-per-agent-node`（消费；owner=golden-eval）；**为什么**：golden 相关动作入口/分析在 copilot bar，timeline 消费 |

## 6. 测试关键点
1. live trace: baseline 现状为 TracePanel/useRunStream 未挂主流程 ⚠️；目标为 run/predict 时 Timeline 自动打开 live trace。
2. run detail: baseline 现状为 RunDetailDrawer 不由 row 打开 ⚠️；目标为 row 可开 detail/replay/compare/export。
3. golden actions: baseline 现状为 旧 sonner/batch copilot 入口残留 ⚠️；目标为 golden analysis 入口为 Copilot analysis bar，Timeline 只提供 compare/detail。

## 7. 涉及 region / platform
`trace-observability` · `run-execution` · `compile-lint` · `golden-eval` · `copilot-assist`

## 8. gaps / 报警
- ✅ live trace 已挂主流程(2026-08-07 清除旧报警):run/predict started 自动开面板并 follow 流;run 结束可返回列表(viewed-run 决议)。
- ✅ run detail 回看已 live(行点击 → 该 run 完整 Trace 视图,只读回放)。仍缺:run_id 概要层(F3)、Replay 重跑、detail/export 动作。
- 🚨 golden actions: 旧 sonner/batch copilot 入口残留 ⚠️；目标 golden analysis 入口为 Copilot analysis bar，Timeline 只提供 compare/detail。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `trace-observability` · `run-execution` · `compile-lint` · `golden-eval` · `copilot-assist`
