---
module: 02_capabilities/graph-authoring
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；画布主拓扑 live；新建 phase 和 subgraph 仍混旧字段，inline subgraph 是 mock ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:GraphCanvas · apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:buildNodes · apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:defaultPhaseMarkdown · apps/studio/frontend/src/components/studio/SubgraphInline.tsx:SubgraphInline
units: [subgraph-path-inline-drilldown]
---

# graph-authoring — Baseline（当下代码实现逻辑）

> **Scope**: 画布 authoring：拓扑渲染、连线/断线、加 phase、子图 path 下钻入口。
> **现状一句话**: 画布主拓扑 live；新建 phase 和 subgraph 仍混旧字段，inline subgraph 是 mock ⚠️。

## UI/UX
画布 authoring：拓扑渲染、连线/断线、加 phase、子图 path 下钻入口。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Canvas shell | `GraphCanvas` receives graph, selection, persistence callbacks, status map, and file-save callback. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:GraphCanvas（L43）` |
| Node build | `buildNodes` maps manifest files and `GRAPH.md` phases into React Flow nodes, including input/output nodes. | `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:buildNodes（L166）` |
| Status default | Without a real status map, the first node becomes success and the rest idle. | `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:frontmatter（L193）` |
| Layout guard | Canvas layout catches cycle errors and renders a blocking overlay. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:layoutResult（L217）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:targetNode（L381）` |
| Connect | New edges validate the connection, update local state, persist, and roll back on failure. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:onConnect（L319）` |
| Disconnect/add phase | The edge context menu exposes Disconnect and Add Phase Node. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:CanvasContextMenuContent（L462）` |
| Persist graph | Workspace serializes graph changes and writes `GRAPH.md` through the current file API. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handleCreatePhase（L186）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:handlePersistConnection（L206）` |
| Node interaction | Click selects a node; double-click phase opens its source file and Properties. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:targetNode（L409）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:targetNode（L423）` |
| Subgraph UI | Node has expand affordance; inline subgraph display is currently mock data. | `apps/studio/frontend/src/components/nodes/SkillNode.tsx:nodeContent（L116）`, `apps/studio/frontend/src/components/studio/SubgraphInline.tsx:SubgraphInline（L8）` |
| Edge context | Context edge click produces mock JSON rather than real transition trace. | `apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext（L30）`, `apps/studio/frontend/src/components/edges/ContextEdge.tsx:buttonClasses（L206）` |

## 后端功能
N/A。

## 当前边界（graph-authoring 现在不是什么）
- path 解析、skill 语法、物理落点归 engine SSOT。
- 写盘归 `native-fs`，graph-authoring 只发起保存意图。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 子图字段 | `defaultPhaseMarkdown` 写旧 `mode/target_skill` ⚠️ | 子图 frontmatter 写 engine MVP1 绝对 `path` |
| inline 展开 | `SubgraphInline` 使用假数据 ⚠️ | 展开真实解析子图、面包屑/下钻可回退 |
| 节点态 | `buildNodes` 默认首节点 success ⚠️ | 节点态来自真实 run/predict/state projection |
> **验"是否按目标改了"**：1. 子图字段；2. inline 展开；3. 节点态。

## 读代码主路径提示
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:GraphCanvas` → `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:buildNodes` → `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:defaultPhaseMarkdown` → `apps/studio/frontend/src/components/studio/SubgraphInline.tsx:SubgraphInline`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-graph-authoring)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `canvas` · `assets` · `phase-editing` · `native-fs` · `engine` resolver/skill-syntax
