# trace-observability Baseline

Status: backend stream/history exist; most frontend trace UI is built but unmounted or mock-fed.

Source workflows: `01_workflows/04_run-and-verify.md`, `01_workflows/05_debugging.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Trace panel | `TracePanel` can render events, search/filter, compare/golden buttons, and virtualized list; it is not mounted in the Studio panels. | `apps/studio/frontend/src/components/TracePanel.tsx:22`, `apps/studio/frontend/src/components/TracePanel.tsx:50` |
| Run stream hook | `useRunStream` opens run websocket, reconnects, and queues events. | `apps/studio/frontend/src/hooks/useRunStream.ts:12`, `apps/studio/frontend/src/hooks/useRunStream.ts:49` |
| Prompt inspector | Prompt inspector dialog exists with Template, Variables, and Rendered tabs. | `apps/studio/frontend/src/components/PromptInspector.tsx:20`, `apps/studio/frontend/src/components/PromptInspector.tsx:44` |
| Timeline panel | Mounted Timeline panel shows historical runs, not the full trace stream. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:32`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:71` |
| Run detail | `RunDetailDrawer` exists with Replay/Compare/Export and payload blocks; not mounted in Workspace flow. | `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:27`, `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:54` |
| Edge context | Context edge click opens mock upstream JSON in Properties. | `apps/studio/frontend/src/components/edges/ContextEdge.tsx:30`, `apps/studio/frontend/src/components/edges/ContextEdge.tsx:206` |
| Properties trace | Properties panel renders selected-edge "Connection Trace" as JSON dump. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:195` |
| Backend stream | Backend exposes `/ws/runs/{run_id}` and reads trace/run events. | `apps/studio/backend/app/routers/websockets.py:27`, `apps/studio/backend/app/services/run_manager.py:334` |
| Engine trace | graph-agent writes typed callback events to `trace.jsonl`. | `packages/graph-agent/src/graph_agent/callbacks/tracing.py:80`, `packages/graph-agent/src/graph_agent/callbacks/tracing.py:101` |

## Current Coverage

- live/backend: trace file, websocket stream, run history detail.
- orphan/frontend: TracePanel, PromptInspector, RunDetailDrawer, useRunStream, filtering.
- placeholder/mock: edge dot context, node state derivation, human-readable full trace doc.

## Known Drift

- Workflow wants run-time panel auto-open and run-after readable trace document; current mounted Timeline only lists runs (`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:71`).
- Dot semantics are real blackboard transitions; current edge context uses generated mock JSON (`apps/studio/frontend/src/components/edges/ContextEdge.tsx:30`).
