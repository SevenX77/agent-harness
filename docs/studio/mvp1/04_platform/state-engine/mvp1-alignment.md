---
module: 04_platform/state-engine
doc: mvp1-alignment
status: FROZEN（状态分散在 Workspace/sessionStorage/SWR/copilotStore/settings hooks；run stream 与 global events 存在但未形成单一 state-engine/WS bridge ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [shell-runtime-gate, compile-stage-gate, run-execution-node-status, trace-dot-blackboard, settings-six-state-provider-health]
aligns_with: 01_workflows/01_init.md（D10 决策留底）· 01_workflows/03_compile.md · 01_workflows/04_run-and-verify.md
---

# state-engine — MVP1 Alignment

> **Tier**: platform | **Owns**: `run-execution-node-status` 的事件→节点态投影 + shell/runtime/stage 状态协调切面 | **现状**: 状态分散在 Workspace/sessionStorage/SWR/copilotStore/settings hooks；run stream 与 global events 存在但未形成单一 state-engine/WS bridge ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `shell-layout` · `compile-lint` · `predict` · `run-execution` · `trace-observability` · `settings` · `gateway`

## 1. 定义
`state-engine` is the front-end platform block for Studio state: workspace UI state, websocket/event bridges, stage state, run/trace/debug reducers, settings refresh signals, and copilot chat store.

Source workflow basis: `01_workflows/03_compile.md:20`, `01_workflows/04_run-and-verify.md:103`, `01_workflows/05_debugging.md:25`.

## 2. 数据流 / 机制（设计细节）
### F1. Workspace UI State

- 机制: track active panel, selected node/edge, open files, nav stack, settings/coprocess panels.
- 决策: shell state should reset cleanly when changing workspaces.
- 原话/来源: `01_workflows/01_init.md:16` includes workspace enter/return actions.
- 测试: changing skill clears old selection/files/copilot context; Back Home returns cleanly.
- Status: live.
- 归属: platform `state-engine`; region `shell-layout`.

### F2. Compile/Predict/Run Stage State

- 机制: centralize stage transitions from lint, manual compile, predict, and run events.
- 决策: stage gate is a spine across Compile/Predict/Run.
- 原话/来源: `01_workflows/03_compile.md:20` and `01_workflows/04_run-and-verify.md:10` define the gate.
- 测试: all transitions are deterministic; no stale predict-pass after file edit.
- Status: partial live.
- 归属: platform `state-engine`; regions `center-action-bar`, `canvas`.

### F3. Event-to-node-state Deriver

- 机制: derive running/success/error/paused/resume-valid states from run/trace/debug events.
- 决策: Q4 assigns this to trace-observability but implementation belongs in shared state.
- 原话/来源: `01_workflows/04_run-and-verify.md:106` and `01_workflows/05_debugging.md:25` record the decision.
- 测试: event fixture maps to node status map; loop/retry attempts preserve all executions.
- Status: target-design.
- 归属: platform `state-engine`; capability `trace-observability`, `debug-resume`.

### F4. Websocket Bridges

- 机制: manage run stream, global settings events, and copilot websocket connection/reconnect.
- 决策: streaming state should be scoped by run_id/skill_id to avoid cross-workspace leaks.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` requires live trace stream; `01_workflows/00_settings-ux-spec.md:462` records settings cross-cutting updates.
- 测试: reconnect does not duplicate events; switching skill closes old subscriptions.
- Status: partial live.
- 归属: platform `state-engine`; regions `timeline`, `settings`, `copilot`.

### F5. Scoped Sidecar Failure State

- 机制: represent sidecar readiness per feature rather than block the whole app.
- 决策: shell/file surfaces should render even when backend-dependent functions fail.
- 原话/来源: `04_platform/native-fs` §4 D10 + `01_workflows/01_init.md` §3(non-fullscreen sidecar gate)。
- 测试: sidecar down leaves Home/editor available; compile/copilot/settings show scoped error.
- Status: target-design/audit.
- 归属: platform `state-engine`; region `shell-layout`.

## 3. 接口契约
- Inputs: API/SWR responses, websocket events, local UI actions, native runtime config.
- Outputs: selected panel/file/node, stage, node status map, trace focus, settings refresh, copilot messages.
- Capability links: all runtime capabilities consume this platform.

## 4. 设计决策基础（PM 原话）
- 保持 **hooks + 文档化契约**,**不引入**正式 store/reducer 框架(YAGNI,MVP1 状态量未到需要 Redux 级)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| STATE_ENGINE-1 | 状态源 | 单元 `run-execution-node-status`（节点态投影切面 owner；**stage→`compile-stage-gate`、provider→`settings-six-state-provider-health`、sidecar→`shell-runtime-gate` 分属其他单元**）；**为什么**：四类状态要有清晰单源和投影边界，现分散 Workspace/sessionStorage/SWR |
| STATE_ENGINE-2 | WS bridge | 单元 `run-execution-node-status`（+`trace-dot-blackboard`）；**为什么**：run/global events 经统一 WS bridge 驱动节点灯/timeline/settings refresh |
| STATE_ENGINE-3 | sidecar failure | 单元 `shell-runtime-gate`；**为什么**：sidecar failure 为局部壳状态、不阻塞基础 UI(D10) |

## 6. 测试关键点
1. 状态源: baseline 现状为 Workspace/sessionStorage/SWR/store 分散持状态 ⚠️；目标为 stage/node/provider/sidecar 状态有清晰单源和投影边界。
2. WS bridge: baseline 现状为 useRunStream/global events 未统一接 state projection ⚠️；目标为 run/global events 驱动 node lights/timeline/settings refresh。
3. sidecar failure: baseline 现状为 RuntimeGate 可全屏阻塞 ⚠️；目标为 sidecar failure 为局部壳状态，不阻塞基础 UI。

## 7. 涉及 region / platform
`shell-layout` · `compile-lint` · `predict` · `run-execution` · `trace-observability` · `settings` · `gateway`

## 8. gaps / 报警
- 🚨 状态源: Workspace/sessionStorage/SWR/store 分散持状态 ⚠️；目标 stage/node/provider/sidecar 状态有清晰单源和投影边界。
- 🚨 WS bridge: useRunStream/global events 未统一接 state projection ⚠️；目标 run/global events 驱动 node lights/timeline/settings refresh。
- 🚨 sidecar failure: RuntimeGate 可全屏阻塞 ⚠️；目标 sidecar failure 为局部壳状态，不阻塞基础 UI。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `shell-layout` · `compile-lint` · `predict` · `run-execution` · `trace-observability` · `settings` · `gateway`
