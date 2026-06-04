# canvas MVP1 Alignment

## 定义

`canvas` owns the visible graph workspace: nodes, edges, topology direct manipulation, subgraph affordances, runtime status badges, compile/debug markers, and edge-dot hit targets.

Source workflow basis: `01_workflows/02_authoring.md:18`, `01_workflows/04_run-and-verify.md:75`, `01_workflows/05_debugging.md:14`.

## 接口契约

- Inputs: skill detail, selected node id, status map, compile diagnostics, trace dot data references.
- Outputs: node selection, file open requests, topology mutation requests, active panel changes.
- Capability links: `graph-authoring`, `phase-editing`, `compile-lint`, `trace-observability`, `debug-resume`.

## F1. Graph Render And Selection

- 机制: render graph nodes/edges and use node click/double-click to drive selection and file/panel focus.
- 决策: canvas is the macro/mid-level authoring surface; Properties/editor handle details.
- 原话/来源: `01_workflows/02_authoring.md:18` lists graph authoring and Properties actions.
- 测试: click selects node; double-click phase opens file and Properties; double-click input opens i/o panel.
- Status: live.
- 归属: region `canvas`; capabilities `graph-authoring`, `phase-editing`.

## F2. Topology Edit

- 机制: edge create/delete and add-phase context menu mutate topology through persistence callbacks.
- 决策: direct graph manipulation should persist to source and then compile validates.
- 原话/来源: `01_workflows/02_authoring.md:31` ties edits to lint/compile.
- 测试: connect/disconnect persists; cycle is blocked; rollback preserves old graph on failure.
- Status: live with native-fs migration pending.
- 归属: region `canvas`; capability `graph-authoring`.

## F3. Compile And Runtime Node Markers

- 机制: canvas badges show compile errors, running/success/fail, debug paused/resume states.
- 决策: errors and run states must be contextual on the node.
- 原话/来源: `01_workflows/03_compile.md:15` requires node error marker; `01_workflows/04_run-and-verify.md:50` requires node lights; `01_workflows/05_debugging.md:14` requires red failed node.
- 测试: compile error marker appears on affected node; run events update node states; failed node shows Resume when valid.
- Status: partial/target-design.
- 归属: capabilities `compile-lint`, `run-execution`, `debug-resume`.

## F4. Subgraph Visual Affordance

- 机制: subgraph node can expand inline or navigate to child graph when path resolves.
- 决策: child graph references are local paths and missing paths recover through Assets.
- 原话/来源: `01_workflows/02_authoring.md:37` locks path-based subgraph references.
- 测试: resolved subgraph expands; unresolved path shows recovery state; inline content is real, not mock.
- Status: placeholder/stale.
- 归属: region `canvas`; capability `skill-workspace`, `graph-authoring`.

## F5. Edge Dot Hit Target

- 机制: the line/dot between nodes is clickable and opens blackboard transition data for the selected run.
- 决策: dot represents operations between upstream end and downstream start.
- 原话/来源: `01_workflows/04_run-and-verify.md:76` defines dot; `01_workflows/04_run-and-verify.md:109` preserves the PM quote.
- 测试: dot opens real transition context; parallel branch dot shows shared filtered blackboard.
- Status: mock/target-design.
- 归属: region `canvas`; capability `trace-observability`.

## 待 PM 补 gap

- Exact visual hierarchy when a node has compile error, run error, and Resume available at the same time.
