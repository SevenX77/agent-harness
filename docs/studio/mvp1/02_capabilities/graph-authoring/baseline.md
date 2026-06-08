# graph-authoring Baseline

Status: mixed. Canvas rendering and basic topology mutation exist; many node/file schema assumptions are still stale.

Source workflows: `01_workflows/02_authoring.md`, `01_workflows/03_compile.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Canvas shell | `GraphCanvas` receives graph, selection, persistence callbacks, status map, and file-save callback. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:43` |
| Node build | `buildNodes` maps manifest files and `GRAPH.md` phases into React Flow nodes, including input/output nodes. | `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:166` |
| Status default | Without a real status map, the first node becomes success and the rest idle. | `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:193` |
| Layout guard | Canvas layout catches cycle errors and renders a blocking overlay. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:217`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:381` |
| Connect | New edges validate the connection, update local state, persist, and roll back on failure. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:319` |
| Disconnect/add phase | The edge context menu exposes Disconnect and Add Phase Node. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:462` |
| Persist graph | Workspace serializes graph changes and writes `GRAPH.md` through the current file API. | `apps/studio/frontend/src/components/studio/Workspace.tsx:186`, `apps/studio/frontend/src/components/studio/Workspace.tsx:206` |
| Node interaction | Click selects a node; double-click phase opens its source file and Properties. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:409`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:423` |
| Subgraph UI | Node has expand affordance; inline subgraph display is currently mock data. | `apps/studio/frontend/src/components/nodes/SkillNode.tsx:116`, `apps/studio/frontend/src/components/studio/SubgraphInline.tsx:8` |
| Edge context | Context edge click produces mock JSON rather than real transition trace. | `apps/studio/frontend/src/components/edges/ContextEdge.tsx:30`, `apps/studio/frontend/src/components/edges/ContextEdge.tsx:206` |

## Current Coverage

- live: render, select, double-click open, connect/disconnect persistence, cycle overlay, add phase command, phase type inference derived from file names, subgraph path rendering and recovery.
- placeholder: edge context JSON, status derivation from run events.

## Known Drift

- The target trace/dot model needs real transition state; current edge panel is mock (`apps/studio/frontend/src/components/edges/ContextEdge.tsx:30`).
- D12 says writes should route through Rust/native-fs; current graph persist uses the Python file API (`apps/studio/frontend/src/components/studio/Workspace.tsx:206`).
