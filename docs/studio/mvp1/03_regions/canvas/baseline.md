# canvas Baseline

Status: live for graph rendering and topology edits; several runtime/debug/trace affordances are mock or missing.

Source workflows: `01_workflows/02_authoring.md`, `01_workflows/04_run-and-verify.md`, `01_workflows/05_debugging.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| GraphCanvas props | Canvas receives skill detail, selected node, persistence callbacks, optional status map, and file-save callback. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:43` |
| Build nodes/edges | Build helpers create React Flow nodes/edges from skill files and graph phases. | `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:166`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:208` |
| Layout/cycle | Layout can detect cycle and show a blocking overlay. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:217`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:381` |
| Select/open | Node click selects; double-click opens input/GRAPH/phase file and panel. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:409`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:423` |
| Connect/disconnect | Canvas validates and persists edge edits with rollback on error. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:319`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:462` |
| SkillNode | Node renders status badge, handles, subgraph button, and overwrite popover. | `apps/studio/frontend/src/components/nodes/SkillNode.tsx:56`, `apps/studio/frontend/src/components/nodes/SkillNode.tsx:106` |
| ContextEdge | Edge renders click target and mock context data. | `apps/studio/frontend/src/components/edges/ContextEdge.tsx:106`, `apps/studio/frontend/src/components/edges/ContextEdge.tsx:206` |
| Subgraph inline | Inline subgraph panel displays mock step rows. | `apps/studio/frontend/src/components/studio/SubgraphInline.tsx:8` |
| Runtime status | Workspace does not pass real `statusByNodeId`, so run/debug node states are not driven. | `apps/studio/frontend/src/components/studio/Workspace.tsx:515` |

## Current Region Ownership

- Owns: graph drawing, node/edge hit targets, canvas context menus, visible node status, subgraph visual affordance.
- Does not own: Properties form fields, engine compile rules, trace data interpretation.

## Known Drift

- Target dot means blackboard transition; current ContextEdge data is generated mock JSON (`apps/studio/frontend/src/components/edges/ContextEdge.tsx:30`).
- Target runtime/debug status needs trace event derivation; current Canvas receives no real status map from Workspace (`apps/studio/frontend/src/components/studio/Workspace.tsx:515`).
