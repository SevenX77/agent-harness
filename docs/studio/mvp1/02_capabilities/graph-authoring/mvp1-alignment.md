---
module: 02_capabilities/graph-authoring
doc: mvp1-alignment
status: drafted（画布主拓扑 live；新建 phase 和 subgraph 仍混旧字段，inline subgraph 是 mock ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [subgraph-path-inline-drilldown]
aligns_with: 01_workflows/02_authoring.md（graph authoring / subgraph）
---

# graph-authoring — MVP1 Alignment

> **Tier**: capability | **Owns**: `subgraph-path-inline-drilldown`（新建子图/默认落点 UI；inline 展开由 canvas region 承载） | **现状**: 画布主拓扑 live；新建 phase 和 subgraph 仍混旧字段，inline subgraph 是 mock ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `canvas` · `assets` · `phase-editing` · `native-fs` · `engine` resolver/skill-syntax

## 1. 定义
`graph-authoring` owns the macro and meso graph composition flow: render graph skill topology, create phase nodes, connect/disconnect dependencies, expand subgraphs, and surface graph-level topology errors.

Source workflow basis: `01_workflows/02_authoring.md:8`, `01_workflows/02_authoring.md:18`, `01_workflows/03_compile.md:13`.

## 2. 数据流 / 机制（设计细节）
### F1. Render Graph Skill Topology

- 机制: load skill detail, build nodes and edges from `GRAPH.md`, and display input/output/phase/subgraph nodes.
- 决策: the graph canvas represents the business flow, while detailed node fields live in Properties.
- 原话/来源: `01_workflows/02_authoring.md:8` sets the target as graph_skill authoring; `01_workflows/02_authoring.md:20` moves input/output and artifact setup into the i/o panel.
- 测试: root graph loads with all phases; missing or cyclic topology shows an actionable compile/canvas error.
- Status: partial live.
- 归属: capability `graph-authoring`; region `canvas`; platform `engine`.

### F2. Connect And Disconnect Dependencies

- 机制: creating or deleting an edge mutates dependency data, persists `GRAPH.md`, and rolls back if validation/persistence fails.
- 决策: topology edits should be direct manipulation, but compile remains the final validator.
- 原话/来源: `01_workflows/02_authoring.md:31` makes lint/compile the real gate; `01_workflows/03_compile.md:13` lists topology validation as part of compile.
- 测试: connecting creates a dependency; disconnect removes it; cycle attempts are blocked and leave the file unchanged.
- Status: live with stale file-write path.
- 归属: capability `graph-authoring`; region `canvas`; platform `native-fs`, `engine`.

### F3. Add Phase Node

- 机制: edge context menu can create a downstream phase, create its file, update `GRAPH.md`, and open it for editing.
- 决策: adding a node is a graph action; editing the generated node body belongs to `phase-editing`.
- 原话/来源: `01_workflows/02_authoring.md:18` lists graph assembly actions before node property editing.
- 测试: add phase creates a valid phase folder/file and a dependency from the selected edge source.
- Status: partial live; generated file format is stale.
- 归属: capability `graph-authoring`; downstream `phase-editing`; platform `native-fs`.

### F4. Expand Subgraph By Path

- 机制: subgraph node expands inline or navigates into a child graph when its local path resolves;**子图节点 = `phases/<phase_id>/SUBGRAPH.md`,frontmatter 写绝对 `path:` 直接指子图根(无 registry,D7);子图默认落 `<skill_root>/subgraph/<name>/`、递归自包含**(可移走、`path` 跟改)。
- 决策: 子图按绝对 `path` 引用(无 registry,D7)、父子 io 不做 1:1 校验(G2);**格式/落点/解析归 engine SSOT**([`01-physical-layout` §2.1.1](../../../../engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md) · `skill-syntax` §2.1 · `02-resolver`)——studio 只引用、不复制(避免"撞旧源");文件夹名统一 `subgraph/`(PM 2026-06-05)。
- 原话/来源: `01_workflows/02_authoring.md:37` locks path-based subgraph references; `01_workflows/02_authoring.md:38` records the relaxed child IO decision.
- 测试: resolved path expands/navigates; unresolved path shows an Assets recovery action; child IO filters from the shared blackboard.
- Status: placeholder/stale.
- 归属: capability `graph-authoring`; capability `skill-workspace`; region `canvas`, `assets`.

### F5. Edge Dot And Transition Context

- 机制: the edge/dot between nodes should represent blackboard transition work between upstream end and downstream start.
- 决策: rendering the dot belongs to Canvas; interpreting the trace/context belongs to `trace-observability`.
- 原话/来源: `01_workflows/04_run-and-verify.md:75` defines trace as seeing node internals and between-node state-machine work; `01_workflows/04_run-and-verify.md:103` records the dot decision.
- 测试: clicking the dot opens real transition context for that run, not mock JSON.
- Status: placeholder.
- 归属: capability `graph-authoring` for rendering; `trace-observability` for data.

## 3. 接口契约
- Source of truth: `GRAPH.md` plus phase file paths; canvas is a visual editor, not a second schema.
- Frontend: React Flow canvas emits topology mutations and selection events.
- Platform target: topology writes go through native-fs; engine compile validates graph legality.
- Region links: `canvas`, `center-action-bar`, `properties`, `input`.
- Capability links: `phase-editing`, `compile-lint`, `trace-observability`.

## 4. 设计决策基础（PM 原话）
- 子图展开 = 当前走查设计(`01_workflows/02_authoring.md` D7/G2/T5/T6),**非旧 canvas-micro-topology 那套**:**D7** `SUBGRAPH.md` 写死 `path` 直接解析、无注册表(copilot cwd 必须含子图 path);**G2** 不绑父子图 1:1 io(子图 input 从 state 状态机过滤字段拿);**T5** inline 展开(虚线容器 + 动态 group bbox);**T6** 下钻 = 就地聚焦、不切工程(+ 画布左上角面包屑返回、copilot 无缝);**L3** 右缘 `+` 展开 body `<step>`/`<action>` 走 Rust。**内联/聚焦递归展开**(超深子图性能退化为下钻属可选优化)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| GRAPH_AUTHORING-1 | 子图字段 | 单元 `subgraph-path-inline-drilldown`；**为什么**：子图按 path 解析(D7)、SUBGRAPH.md io 不再严格 1:1(G2 删伪需求) |
| GRAPH_AUTHORING-2 | inline 展开 | 单元 `subgraph-path-inline-drilldown`；**为什么**：主画布 inline 展开子拓扑 + 下钻并存，虚线容器靠父图最右(G4 LOD) |
| GRAPH_AUTHORING-3 | 节点态 | 单元 `run-execution-node-status`（消费）；**为什么**：节点运行态来自 run/predict/state 投影，graph-authoring 只消费不拥有 |

## 6. 测试关键点
1. 子图字段: baseline 现状为 `defaultPhaseMarkdown` 写旧 `mode/target_skill` ⚠️；目标为 子图 frontmatter 写 engine MVP1 绝对 `path`。
2. inline 展开: baseline 现状为 `SubgraphInline` 使用假数据 ⚠️；目标为 展开真实解析子图、面包屑/下钻可回退。
3. 节点态: baseline 现状为 `buildNodes` 默认首节点 success ⚠️；目标为 节点态来自真实 run/predict/state projection。

## 7. 涉及 region / platform
`canvas` · `assets` · `phase-editing` · `native-fs` · `engine` resolver/skill-syntax

## 8. gaps / 报警
- 🚨 子图字段: `defaultPhaseMarkdown` 写旧 `mode/target_skill` ⚠️；目标 子图 frontmatter 写 engine MVP1 绝对 `path`。
- 🚨 inline 展开: `SubgraphInline` 使用假数据 ⚠️；目标 展开真实解析子图、面包屑/下钻可回退。
- 🚨 节点态: `buildNodes` 默认首节点 success ⚠️；目标 节点态来自真实 run/predict/state projection。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `canvas` · `assets` · `phase-editing` · `native-fs` · `engine` resolver/skill-syntax
