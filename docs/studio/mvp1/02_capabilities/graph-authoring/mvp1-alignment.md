# graph-authoring MVP1 Alignment

## 定义

`graph-authoring` owns the macro and meso graph composition flow: render graph skill topology, create phase nodes, connect/disconnect dependencies, expand subgraphs, and surface graph-level topology errors.

Source workflow basis: `01_workflows/02_authoring.md:8`, `01_workflows/02_authoring.md:18`, `01_workflows/03_compile.md:13`.

## 接口契约

- Source of truth: `GRAPH.md` plus phase file paths; canvas is a visual editor, not a second schema.
- Frontend: React Flow canvas emits topology mutations and selection events.
- Platform target: topology writes go through native-fs; engine compile validates graph legality.
- Region links: `canvas`, `center-action-bar`, `properties`, `input`.
- Capability links: `phase-editing`, `compile-lint`, `trace-observability`.

## F1. Render Graph Skill Topology

- 机制: load skill detail, build nodes and edges from `GRAPH.md`, and display input/output/phase/subgraph nodes.
- 决策: the graph canvas represents the business flow, while detailed node fields live in Properties.
- 原话/来源: `01_workflows/02_authoring.md:8` sets the target as graph_skill authoring; `01_workflows/02_authoring.md:20` moves input/output and artifact setup into the i/o panel.
- 测试: root graph loads with all phases; missing or cyclic topology shows an actionable compile/canvas error.
- Status: partial live.
- 归属: capability `graph-authoring`; region `canvas`; platform `engine`.

## F2. Connect And Disconnect Dependencies

- 机制: creating or deleting an edge mutates dependency data, persists `GRAPH.md`, and rolls back if validation/persistence fails.
- 决策: topology edits should be direct manipulation, but compile remains the final validator.
- 原话/来源: `01_workflows/02_authoring.md:31` makes lint/compile the real gate; `01_workflows/03_compile.md:13` lists topology validation as part of compile.
- 测试: connecting creates a dependency; disconnect removes it; cycle attempts are blocked and leave the file unchanged.
- Status: live with stale file-write path.
- 归属: capability `graph-authoring`; region `canvas`; platform `native-fs`, `engine`.

## F3. Add Phase Node

- 机制: edge context menu can create a downstream phase, create its file, update `GRAPH.md`, and open it for editing.
- 决策: adding a node is a graph action; editing the generated node body belongs to `phase-editing`.
- 原话/来源: `01_workflows/02_authoring.md:18` lists graph assembly actions before node property editing.
- 测试: add phase creates a valid phase folder/file and a dependency from the selected edge source.
- Status: partial live; generated file format is stale.
- 归属: capability `graph-authoring`; downstream `phase-editing`; platform `native-fs`.

## F4. Expand Subgraph By Path

- 机制: subgraph node expands inline or navigates into a child graph when its local path resolves;**新建子图默认嵌在父 phase 下 `<phase_name>/<subskill_name>/SKILL.md`**——子图/孙图物理嵌套、好找,只有要独立复用时才把 `<subskill_name>` 拎到顶层。
- 决策: child graph references are paths, not registry ids, and child IO is not forced into one-to-one mapping;**子图默认嵌套父 phase 文件夹内、独立化是显式"拎出"**——避免所有子/孙图平铺难找(PM 2026-06-04)。
- 原话/来源: `01_workflows/02_authoring.md:37` locks path-based subgraph references; `01_workflows/02_authoring.md:38` records the relaxed child IO decision.
- 测试: resolved path expands/navigates; unresolved path shows an Assets recovery action; child IO filters from the shared blackboard.
- Status: placeholder/stale.
- 归属: capability `graph-authoring`; capability `skill-workspace`; region `canvas`, `assets`.

## F5. Edge Dot And Transition Context

- 机制: the edge/dot between nodes should represent blackboard transition work between upstream end and downstream start.
- 决策: rendering the dot belongs to Canvas; interpreting the trace/context belongs to `trace-observability`.
- 原话/来源: `01_workflows/04_run-and-verify.md:75` defines trace as seeing node internals and between-node state-machine work; `01_workflows/04_run-and-verify.md:103` records the dot decision.
- 测试: clicking the dot opens real transition context for that run, not mock JSON.
- Status: placeholder.
- 归属: capability `graph-authoring` for rendering; `trace-observability` for data.

## 待 PM 补 gap

- Exact inline subgraph expansion depth limit and whether expansion should auto-collapse sibling branches.
