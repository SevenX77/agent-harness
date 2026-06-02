# canvas-topology — Baseline (画布拓扑基线对齐文档)

> **Status**: Completed (Aligned with V0.3.0)
> **Scope**: Canvas Node Renderers, Slot Connections, Edge Custom Styles, Whitelist Overlay Trigger

---

## 1. Core Codebase Structures

The macro-topology of the visual flow editor is orchestrated by the canvas component:

### Main Files
* **[GraphCanvas.tsx](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx)**: Main canvas containing node definitions, connect callbacks, viewport handlers, and the conflict overlay popovers.
* **[canvas-authoring.test.ts](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.test.ts)**: Validates model conflicts and whitelists sequential overwrite logic.

---

## 2. In-Code Node Categories

The visual editor categorizes nodes into three physical types in the React Flow viewport:
1. **Input Node**: Hardcoded with `id="INPUT"`. Acts as the starting anchor pin representing the input schemas.
2. **Output Node**: Hardcoded with `id="OUTPUT"`. Acts as the termination anchor representing final contexts.
3. **Phase Node**: Any executable cognitive phase (such as logic, skill, or subgraph modes). Managed dynamically based on files inside `phases/`.

---

## 3. Current Connection & Validation Logic

The connection callbacks are restricted in `onConnect` inside `GraphCanvas.tsx:319-340`:

```typescript
const onConnect = useCallback((connection: Connection) => {
  const source = connection.source
  const target = connection.target
  if (!source || !target || source === INPUT_ID || source === OUTPUT_ID || target === INPUT_ID || target === OUTPUT_ID) {
    toast.error('Only phase nodes can be connected as dependencies')
    return
  }
...
```

### Logical Gaps Identifed
* **Strict Block on Anchors**: `INPUT_ID` and `OUTPUT_ID` are barred from connections. Users cannot visually connect top-level inputs to the first execution phase, making dataflow representations visually incomplete.
* **Lack of Live Persistence**: Adjusting dependencies on the React Flow canvas only updates the React state array (`setEdges`). It does **not** persist or rewrite the `depends_on` metadata in `phases/<phase_id>/*.md` back to the file system.

---

## 4. Edge Pins & Traces Renderers

The custom context edge renderer (`ContextEdge.tsx`) draws custom Bezier curves connecting nodes.
* **Center Pin**: Generates a circular button at the center of the edge path (`pathX`, `pathY`).
* **Interactive State**: Clicking this pin triggers context popups, capturing inputs, outputs, and JSON traces directly on the Properties Panel.
