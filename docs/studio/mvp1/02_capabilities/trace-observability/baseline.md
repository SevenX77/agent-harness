# trace-observability Baseline

Status: useRunStream和node status projection已接入并单测覆盖；TracePanel完整挂载、run-after readable trace、dot blackboard仍不是本批完成项。

Source workflows: `01_workflows/04_run-and-verify.md`, `01_workflows/05_debugging.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Trace panel | `TracePanel` renders events, search/filter, compare/golden buttons, and virtualized list. | `apps/studio/frontend/src/components/TracePanel.tsx:22`, `apps/studio/frontend/src/components/TracePanel.tsx:50` |
| Run stream hook | `useRunStream` opens run websocket, reconnects, and queues events. | `apps/studio/frontend/src/hooks/useRunStream.ts:12`, `apps/studio/frontend/src/hooks/useRunStream.ts:49` |
| Prompt inspector | Prompt inspector dialog exists with Template, Variables, and Rendered tabs. | `apps/studio/frontend/src/components/PromptInspector.tsx:20`, `apps/studio/frontend/src/components/PromptInspector.tsx:44` |
| Timeline panel | Mounted Timeline panel shows historical runs. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:32`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:71` |
| Run detail | `RunDetailDrawer` exists with Replay/Compare/Export and payload blocks. | `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:27`, `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:54` |
| Edge context | Context edge click opens mock upstream JSON in Properties. | `apps/studio/frontend/src/components/edges/ContextEdge.tsx:30`, `apps/studio/frontend/src/components/edges/ContextEdge.tsx:206` |
| Properties trace | Properties panel renders selected-edge "Connection Trace" as JSON dump. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:195` |
| Backend stream | Backend exposes `/ws/runs/{run_id}` and reads trace/run events. | `apps/studio/backend/app/routers/websockets.py:27`, `apps/studio/backend/app/services/run_manager.py:334` |
| Engine trace | graph-agent writes typed callback events to `trace.jsonl`. | `packages/graph-agent/src/graph_agent/callbacks/tracing.py:80`, `packages/graph-agent/src/graph_agent/callbacks/tracing.py:101` |
| Node status mapping | `Workspace` connects the WebSocket stream events and derives `statusByNodeId` (mapping `phase_start` -> `running`, `phase_end` -> `success`, errors -> `error`), passing it down to `GraphCanvas` and `SplitEditor`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:87`, `apps/studio/frontend/src/components/studio/SplitEditor.tsx:112` |

## Current Coverage

- live/backend: trace file, websocket stream, run history detail.
- live/frontend: TracePanel, PromptInspector, RunDetailDrawer, useRunStream, filtering, node status updates driven by WebSocket events.

## Known Drift / Deferred Items

- TracePanel 的完整面板交互式挂载挂起为 **deferred**。
- 运行后（run-after）可读性强的 trace document 人类友好报告渲染为 **deferred**。
- 各种 edge / dot blackboard 精细黑板状态转换投影（dot blackboard）为 **deferred**。
