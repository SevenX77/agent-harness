# trace-visualization — Baseline (追踪可视化基线对齐文档)

> **Status**: Completed (Aligned with V0.3.0)
> **Scope**: Custom Edge Click Handlers, Live Run Diagnostics, Node State Highlighting, Theme Overrides

---

## 1. Core Codebase Structures

The execution tracing and diagnostics features are distributed across:

### Key Components
* **[TimelinePanel.tsx](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx)**: Displays node execution histories, latency metrics, and step-level event timelines.
* **[PropertiesPanel.tsx](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx)**: Currently used as a dump for rendering inputs, outputs, and JSON traces when edge pins are clicked.
* **[run_manager.py](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/backend/app/services/run_manager.py)**: Drains trace lines from absolute run directories `trace.jsonl` and delivers serialized `CallbackEvent` arrays to the client.

---

## 2. Tracing Context Click Flow

When a user clicks on a center circular pin of a custom context edge (`ContextEdge.tsx`):
1. The canvas triggers the edge action handler, sending the edge source and target phase data.
2. The values are dispatched to the `WorkspaceContext` state.
3. Because there is no standalone debugging panel, the static **Properties Sidebar** intercepts this context, replacing the node's static field editor with raw JSON listings of the trace data.

---

## 3. Visual Styling & Theme Limits

* **React Flow Grids**: Overridden in `index.css` to toggle background color palettes based on active classes.
* **Theme Switching Gaps**: Theme selection is stored in LocalStorage via `themeStore.ts`. However, dynamic canvases (React Flow grids, dot patterns, edge custom stroke paths) do not re-render responsively when light/dark mode is toggled, resulting in illegible contrast or visual grid lines dropping off.
