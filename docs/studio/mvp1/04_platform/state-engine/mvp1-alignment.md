# state-engine MVP1 Alignment

## 定义

`state-engine` is the front-end platform block for Studio state: workspace UI state, websocket/event bridges, stage state, run/trace/debug reducers, settings refresh signals, and copilot chat store.

Source workflow basis: `01_workflows/03_compile.md:20`, `01_workflows/04_run-and-verify.md:103`, `01_workflows/05_debugging.md:25`.

## 接口契约

- Inputs: API/SWR responses, websocket events, local UI actions, native runtime config.
- Outputs: selected panel/file/node, stage, node status map, trace focus, settings refresh, copilot messages.
- Capability links: all runtime capabilities consume this platform.

## F1. Workspace UI State

- 机制: track active panel, selected node/edge, open files, nav stack, settings/coprocess panels.
- 决策: shell state should reset cleanly when changing workspaces.
- 原话/来源: `01_workflows/01_init.md:16` includes workspace enter/return actions.
- 测试: changing skill clears old selection/files/copilot context; Back Home returns cleanly.
- Status: live.
- 归属: platform `state-engine`; region `shell-layout`.

## F2. Compile/Predict/Run Stage State

- 机制: centralize stage transitions from lint, manual compile, predict, and run events.
- 决策: stage gate is a spine across Compile/Predict/Run.
- 原话/来源: `01_workflows/03_compile.md:20` and `01_workflows/04_run-and-verify.md:10` define the gate.
- 测试: all transitions are deterministic; no stale predict-pass after file edit.
- Status: partial live.
- 归属: platform `state-engine`; regions `center-action-bar`, `canvas`.

## F3. Event-to-node-state Deriver

- 机制: derive running/success/error/paused/resume-valid states from run/trace/debug events.
- 决策: Q4 assigns this to trace-observability but implementation belongs in shared state.
- 原话/来源: `01_workflows/04_run-and-verify.md:106` and `01_workflows/05_debugging.md:25` record the decision.
- 测试: event fixture maps to node status map; loop/retry attempts preserve all executions.
- Status: target-design.
- 归属: platform `state-engine`; capability `trace-observability`, `debug-resume`.

## F4. Websocket Bridges

- 机制: manage run stream, global settings events, and copilot websocket connection/reconnect.
- 决策: streaming state should be scoped by run_id/skill_id to avoid cross-workspace leaks.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` requires live trace stream; `01_workflows/00_settings-ux-spec.md:462` records settings cross-cutting updates.
- 测试: reconnect does not duplicate events; switching skill closes old subscriptions.
- Status: partial live.
- 归属: platform `state-engine`; regions `timeline`, `settings`, `copilot`.

## F5. Scoped Sidecar Failure State

- 机制: represent sidecar readiness per feature rather than block the whole app.
- 决策: shell/file surfaces should render even when backend-dependent functions fail.
- 原话/来源: `docs/studio/INDEX.md:221` records non-fullscreen sidecar gate.
- 测试: sidecar down leaves Home/editor available; compile/copilot/settings show scoped error.
- Status: target-design/audit.
- 归属: platform `state-engine`; region `shell-layout`.

## 已决(PM 2026-06-04)

- 保持 **hooks + 文档化契约**,**不引入**正式 store/reducer 框架(YAGNI,MVP1 状态量未到需要 Redux 级)。
