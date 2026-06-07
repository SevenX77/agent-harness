---
module: 03_regions/canvas
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；React Flow 画布 live；node status 仍非真实 run 态，edge dot 用 mock 黑板，inline subgraph 用 mock rows ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:GraphCanvas · apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:buildNodes · apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext · apps/studio/frontend/src/components/studio/SubgraphInline.tsx:SubgraphInline · apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace
units: [subgraph-path-inline-drilldown, run-execution-node-status, trace-dot-blackboard]
---

# canvas — Baseline（当下代码实现逻辑）

> **Scope**: 中心画布的 graph render/selection/topology edit、节点灯、子图视觉 affordance 与 edge dot hit target。
> **现状一句话**: React Flow 画布 live；node status 仍非真实 run 态，edge dot 用 mock 黑板，inline subgraph 用 mock rows ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| GraphCanvas props | Canvas receives skill detail, selected node, persistence callbacks, optional status map, and file-save callback. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:GraphCanvas（L43）` |
| Build nodes/edges | Build helpers create React Flow nodes/edges from skill files and graph phases. | `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:buildNodes（L166）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:rawNodes（L208）` |
| Layout/cycle | Layout can detect cycle and show a blocking overlay. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:layoutResult（L217）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:targetNode（L381）` |
| Select/open | Node click selects; double-click opens input/GRAPH/phase file and panel. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:targetNode（L409）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:targetNode（L423）` |
| Connect/disconnect | Canvas validates and persists edge edits with rollback on error. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:onConnect（L319）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:CanvasContextMenuContent（L462）` |
| SkillNode | Node renders status badge, handles, subgraph button, and overwrite popover. | `apps/studio/frontend/src/components/nodes/SkillNode.tsx:SkillNode（L56）`, `apps/studio/frontend/src/components/nodes/SkillNode.tsx:nodeContent（L106）` |
| ContextEdge | Edge renders click target and mock context data. | `apps/studio/frontend/src/components/edges/ContextEdge.tsx:ContextEdge（L106）`, `apps/studio/frontend/src/components/edges/ContextEdge.tsx:buttonClasses（L206）` |
| Subgraph inline | Inline subgraph panel displays mock step rows. | `apps/studio/frontend/src/components/studio/SubgraphInline.tsx:SubgraphInline（L8）` |
| Runtime status | Workspace does not pass real `statusByNodeId`, so run/debug node states are not driven. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L515）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| GraphCanvas props | Canvas receives skill detail, selected node, persistence callbacks, optional status map, and file-save callback. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:GraphCanvas（L43）` |
| Build nodes/edges | Build helpers create React Flow nodes/edges from skill files and graph phases. | `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:buildNodes（L166）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:rawNodes（L208）` |
| Layout/cycle | Layout can detect cycle and show a blocking overlay. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:layoutResult（L217）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:targetNode（L381）` |
| Select/open | Node click selects; double-click opens input/GRAPH/phase file and panel. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:targetNode（L409）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:targetNode（L423）` |
| Connect/disconnect | Canvas validates and persists edge edits with rollback on error. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:onConnect（L319）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:CanvasContextMenuContent（L462）` |
| SkillNode | Node renders status badge, handles, subgraph button, and overwrite popover. | `apps/studio/frontend/src/components/nodes/SkillNode.tsx:SkillNode（L56）`, `apps/studio/frontend/src/components/nodes/SkillNode.tsx:nodeContent（L106）` |
| ContextEdge | Edge renders click target and mock context data. | `apps/studio/frontend/src/components/edges/ContextEdge.tsx:ContextEdge（L106）`, `apps/studio/frontend/src/components/edges/ContextEdge.tsx:buttonClasses（L206）` |
| Subgraph inline | Inline subgraph panel displays mock step rows. | `apps/studio/frontend/src/components/studio/SubgraphInline.tsx:SubgraphInline（L8）` |
| Runtime status | Workspace does not pass real `statusByNodeId`, so run/debug node states are not driven. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L515）` |

## 后端功能
N/A。

## 当前边界（canvas 现在不是什么）
- 不拥有 run 机制，节点灯只消费 `state-engine` 投影。
- 不复制 engine path / trace contract，只渲染 Studio UI。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 节点态 | Workspace 未传真实 `statusByNodeId`，buildNodes 有默认假态 ⚠️ | 节点灯来自真实 run/predict/state-engine 投影 |
| dot 黑板 | `ContextEdge:getMockEdgeContext` 生成 mock JSON ⚠️ | edge dot 点击打开真实 blackboard transition |
| 子图 inline | `SubgraphInline` 是 mock rows ⚠️ | 解析绝对 `path` 后 inline 展开/下钻/面包屑可用 |
> **验"是否按目标改了"**：1. 节点态；2. dot 黑板；3. 子图 inline。

## 读代码主路径提示
`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:GraphCanvas` → `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:buildNodes` → `apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext` → `apps/studio/frontend/src/components/studio/SubgraphInline.tsx:SubgraphInline` → `apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-canvas)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `graph-authoring` · `run-execution` · `state-engine` · `trace-observability` · `assets` · `engine`
