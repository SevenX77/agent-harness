---
module: 02_capabilities/run-execution
doc: mvp1-alignment
status: FROZEN（后端 run manager live；前端 Run handler 仍是桩，predict-pass 不会置位，batch UI 未挂主路径 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [run-execution-node-status, golden-per-agent-node]
aligns_with: 01_workflows/04_run-and-verify.md（run / batch / node status）
---

# run-execution — MVP1 Alignment

> **Tier**: capability | **Owns**: `run-execution-node-status`（run 机制 + 批量/循环展示）+ `golden-per-agent-node` 的 run 播种切面 | **现状**: 后端 run manager live；前端 Run handler 仍是桩，predict-pass 不会置位，batch UI 未挂主路径 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `predict` · `canvas` · `timeline` · `state-engine` · `golden-eval` · `engine` iterate/observability

## 1. 定义
`run-execution` owns true execution after predict-pass: start a real run, stream state, light nodes, persist final context/metrics/trace, show run history, and support batch execution once input configuration is ready.

Source workflow basis: `01_workflows/04_run-and-verify.md:42`, `01_workflows/04_run-and-verify.md:61`, `01_workflows/04_run-and-verify.md:70`.

## 2. 数据流 / 机制（设计细节）
### F1. Start Single Run

- 机制: clicking Run posts selected input to `/runs`; backend spawns `run_skill` and returns run metadata.
- 决策: run burns real tokens and must come after predict.
- 原话/来源: `01_workflows/04_run-and-verify.md:46` defines the action; `01_workflows/04_run-and-verify.md:67` keeps the PM quote that predict/run just run according to config.
- 测试: Run disabled until predict-pass; successful click creates a run_id and metadata row.
- Status: backend live, frontend stub.
- 归属: capability `run-execution`; region `center-action-bar`, `input`; platform `engine`.

### F2. Live Run State And Node Lights

- 机制: run websocket events derive graph node statuses, edge animation, and current focus.
- 决策: run animation should reuse the role-test style for consistency.
- 原话/来源: `01_workflows/04_run-and-verify.md:49` and `01_workflows/04_run-and-verify.md:50` list status and node lights; `01_workflows/04_run-and-verify.md:67` records the PM animation decision.
- 测试: each node lights running/success/error from real events; failed node becomes red and stops focus.
- Status: placeholder.
- 归属: capability `run-execution`; capability `trace-observability`; region `canvas`; platform `state-engine`.

### F3. Run History And Detail

- 机制: list past runs, show status/duration/token summaries, and open a run detail/replay view.
- 决策: run aftercare belongs in the timeline/history area, not in the graph authoring form.
- 原话/来源: `01_workflows/04_run-and-verify.md:52` and `01_workflows/04_run-and-verify.md:58` list history and detail actions.
- 测试: completed/failed runs appear; detail drawer can replay with same input; delete removes a run row.
- Status: history live, detail drawer orphan.
- 归属: region `timeline`, `local-history`; capability `run-execution`.

### F4. Batch Run

- 机制: i/o panel selects multiple inputs, backend starts a batch, frontend polls progress and reports per-item failure.
- 决策: batch is input/run configuration, not an independent predict concept.
- 原话/来源: `01_workflows/04_run-and-verify.md:54` to `01_workflows/04_run-and-verify.md:57` list batch actions; `01_workflows/04_run-and-verify.md:62` places run entry in i/o panel.
- 测试: each input gets a run result; one failed item is visible and does not silently disappear.
- Status: backend live, frontend orphan.
- 归属: capability `run-execution`; region `input`; platform `engine`.

### F5. Successful Run Autocommit

- 机制: successful run triggers local git autocommit and stores status.
- 决策: autocommit is triggered by run but owned by save/publish.
- 原话/来源: `01_workflows/04_run-and-verify.md:59` marks autocommit backend-only; `01_workflows/04_run-and-verify.md:64` assigns it to save/publish.
- 测试: successful run commits; failed or interrupted run does not commit.
- Status: backend-only live.
- 归属: capability `publish`; platform `native-fs`.

## 3. 接口契约
- Entry: Run is enabled only after compile-pass and predict-pass.
- Input: i/o panel supplies single or batch input selection.
- Backend: run manager owns process lifecycle, run artifacts, websocket stream, and history.
- Trace/golden consumers read run outputs after completion.
- Region links: `center-action-bar`, `input`, `canvas`, `timeline`, `local-history`.
- Platform links: `engine`, `state-engine`, `native-fs`.

## 4. 设计决策基础（PM 原话）
- Replay 先放 **Timeline**;Local History **只做 git**(不吸收 RunDetailDrawer/BatchSummary);batch 输入范围命名随实现定。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| RUN_EXECUTION-1 | Run 入口 | 单元 `run-execution-node-status`；**为什么**：onRun 现仅日志，要真调 startRun 带选中 input/settings |
| RUN_EXECUTION-2 | 节点态 | 单元 `run-execution-node-status`；**为什么**：run events 经 state-engine 投到节点灯/边，非画布默认假态 |
| RUN_EXECUTION-3 | batch | 单元 `run-execution-node-status`；**为什么**：后端 batch 与 hook 已存在但未挂 Workspace，批量/循环入口要可用 |
| RUN_EXECUTION-4 | golden seed | 单元 `golden-per-agent-node`；**为什么**：run 真实输出可做 golden 默认种子，predict 假数据不可(409) |

## 6. 测试关键点
1. Run 入口: baseline 现状为 `onRun` 只日志 ⚠️；目标为 Run 真调用 `startRun`，携带选中 input/settings。
2. 节点态: baseline 现状为 GraphCanvas 默认/假态 ⚠️；目标为 run events 经 state-engine 投到节点灯/边。
3. batch: baseline 现状为 后端与 hook 存在但未挂 Workspace ⚠️；目标为 批量/循环入口与结果展示可用。
4. golden seed: baseline 现状为 run final output 可做 golden 默认种子；目标为 predict fake trace 不可做 golden。

## 7. 涉及 region / platform
`predict` · `canvas` · `timeline` · `state-engine` · `golden-eval` · `engine` iterate/observability

## 8. gaps / 报警
- 🚨 Run 入口: `onRun` 只日志 ⚠️；目标 Run 真调用 `startRun`，携带选中 input/settings。
- 🚨 节点态: GraphCanvas 默认/假态 ⚠️；目标 run events 经 state-engine 投到节点灯/边。
- 🚨 batch: 后端与 hook 存在但未挂 Workspace ⚠️；目标 批量/循环入口与结果展示可用。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `predict` · `canvas` · `timeline` · `state-engine` · `golden-eval` · `engine` iterate/observability
