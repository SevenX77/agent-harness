# state-management (studio system-level) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Studio frontend 跨 feature 共享 client state；不覆盖 server 数据获取本身。
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL make shared state support the locked Studio goal: PM can visually edit, change, run, and inspect a V2.1 skill.
The current state inventory is in [baseline.md](./baseline.md).
This file describes target state slices and persistence boundaries.

First term: state slice means one named piece of frontend state with a clear owner.
Examples: selected canvas node, active editor pane, trace filter, Copilot mentions.
Today many of these are local `useState` fields inside `Workspace`; MVP0 SHOULD separate them enough to avoid accidental re-render storms.

MVP0 SHOULD add a unified selection model.
Selection means "what the PM is looking at or acting on".
It must support phase node, edge, file, trace event, compile issue, and settings item.
This is required because Context Inspector, Copilot mentions, PropertiesPanel, and Trace all need the same active target.

MVP0 SHOULD add inspector state.
Inspector state means whether the right-side Properties/Context Inspector panel shows a node, an edge, or nothing.
Studio layout MVP0 already plans Context Inspector in the right-side panel, see [studio-layout mvp0](../studio-layout/mvp0-alignment.md#前端逻辑).

MVP0 SHOULD add trace filter state.
Trace visualization MVP0 needs filters for event kind, phase, failed-only, payload-only, and search.
The owner UI is [trace-visualization mvp0](../../trace-inspector/mvp0-alignment.md#cross-trace-edge-inspection).

MVP0 SHOULD add Copilot session state that is separate from raw chat messages.
Chat messages can remain in an external store, but mentions, pending patch proposals, and current implicit context need explicit state.
Copilot owns the message schema in [copilot-assistance mvp0](../../copilot-chat/mvp0-alignment.md#cross-copilot-mentions).

## 前端逻辑

MVP0 SHOULD refactor Provider nesting by concern, not by component convenience.
Current `WorkspaceContext` carries many unrelated fields, see `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:22` to `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:38`.
MVP0 SHOULD split it into smaller providers or external stores.

Proposed provider stack:

```tsx
<RuntimeStateProvider>
  <WorkspaceStateProvider>
    <LayoutStateProvider>
      <SelectionStateProvider>
        <EditorStateProvider>
          <TraceStateProvider>
            <CopilotStateProvider>
              <Workspace />
            </CopilotStateProvider>
          </TraceStateProvider>
        </EditorStateProvider>
      </SelectionStateProvider>
    </LayoutStateProvider>
  </WorkspaceStateProvider>
</RuntimeStateProvider>
```

This is not a mandate to add many React Contexts if an external store is better.
It is a mandate to split high-churn state from low-churn state.
For example, editor keystrokes should not re-render Copilot.

MVP0 SHOULD define typed slices.

```typescript
export type StudioSelection =
  | { type: "none" }
  | { type: "phase"; skillId: string; phaseId: string }
  | { type: "edge"; skillId: string; sourcePhaseId: string; targetPhaseId: string; runId?: string }
  | { type: "file"; skillId: string; path: string }
  | { type: "trace_event"; skillId: string; runId: string; eventId: string }
  | { type: "compile_issue"; skillId: string; issueId: string; filePath?: string; line?: number };

export interface LayoutStateSlice {
  activeLeftPanel: "assets" | "input" | "timeline" | "properties" | "local-history" | null;
  rightPanel: "properties" | "context-inspector" | "copilot";
  panelSizes: { left: number; center: number; right: number };
}

export interface EditorStateSlice {
  splitMode: boolean;
  activeFocusSide: "left" | "right";
  openFiles: Partial<Record<"left" | "right", { path: string; hash: string | null; dirty: boolean }>>;
}

export interface TraceStateSlice {
  activeRunId?: string;
  selectedEventId?: string;
  filters: { query: string; kinds: string[]; phaseIds: string[]; failedOnly: boolean };
}
```

MVP0 SHOULD keep server cache separate.
SWR/API cache for `SkillDetail` is not the same as UI state.
The current `useSkills` result is consumed in `Workspace`, see `apps/studio/frontend/src/components/studio/Workspace.tsx:60` to `apps/studio/frontend/src/components/studio/Workspace.tsx:61`.
Do not copy full `SkillDetail` into every store.

MVP0 SHOULD add selectors.
Selectors mean functions that read a small derived value from state.
Example: `selectActivePhaseId(state)` should not require components to inspect `selection` shape manually.

## 后端功能

MVP0 SHOULD keep most client state out of backend.
Panel selection, selected node, trace filters, Copilot input draft, and split focus are frontend-only.
Backend should not persist them except where user recovery is needed.

Draft persistence SHOULD be upgraded.
Workspace-file-system MVP0 proposes IndexedDB or Tauri local data dir for durable drafts, see [workspace-file-system mvp0](../workspace-file-system/mvp0-alignment.md#前端逻辑).
State management SHOULD define which draft state enters that layer.

Backend events SHOULD update state through one event ingestion point.
Current `Workspace` directly consumes `/ws/events`, see `apps/studio/frontend/src/components/studio/Workspace.tsx:218` to `apps/studio/frontend/src/components/studio/Workspace.tsx:256`.
MVP0 SHOULD move this into an event bus/store adapter so editor, file tree, and toast can subscribe without duplicating sockets.

Run events SHOULD enter TraceState first.
Current `useRunStream` owns its own event list, see `apps/studio/frontend/src/hooks/useRunStream.ts:12` to `apps/studio/frontend/src/hooks/useRunStream.ts:20`.
MVP0 SHOULD let TraceState expose derived status to Canvas and CenterActionBar.

Copilot messages SHOULD stay in a dedicated store but use the unified selection state.
Current `copilotStore` is minimal and external-store compatible, see `apps/studio/frontend/src/store/copilotStore.ts:21` to `apps/studio/frontend/src/store/copilotStore.ts:45`.
MVP0 can extend this pattern instead of forcing Copilot into React Context.

## API

Proposed frontend state module contracts:

```typescript
export interface StudioState {
  workspace: {
    currentSkillId: string | null;
    navStack: string[];
  };
  layout: LayoutStateSlice;
  selection: StudioSelection;
  editor: EditorStateSlice;
  trace: TraceStateSlice;
  copilot: {
    activeSkillId: string | null;
    pendingMentionIds: string[];
    pendingPatchIds: string[];
  };
}

export interface StudioStateStore {
  getSnapshot(): StudioState;
  subscribe(listener: () => void): () => void;
  dispatch(action: StudioStateAction): void;
}
```

Actions:

```typescript
export type StudioStateAction =
  | { type: "workspace/select_skill"; skillId: string | null }
  | { type: "selection/set"; selection: StudioSelection }
  | { type: "layout/open_panel"; panel: LayoutStateSlice["activeLeftPanel"] }
  | { type: "layout/open_inspector"; selection: StudioSelection }
  | { type: "editor/open_file"; side?: "left" | "right"; path: string; skillId: string }
  | { type: "trace/set_filter"; filters: Partial<TraceStateSlice["filters"]> }
  | { type: "copilot/add_mention"; mentionId: string };
```

Persistence policy:

```typescript
export interface StatePersistencePolicy {
  memoryOnly: Array<keyof StudioState>;
  sessionStorage: string[];
  localStorage: string[];
  indexedDb: string[];
  tauriLocalDataDir: string[];
}
```

MVP0 SHOULD document exact placement:

| State | Persistence |
|---|---|
| selected node/edge | memory |
| Context Inspector open target | memory |
| trace filters | sessionStorage or localStorage |
| panel sizes | localStorage |
| editor dirty drafts | IndexedDB or Tauri local data dir |
| recent skills | localStorage |
| Copilot messages | memory for MVP0 |
| Copilot patch proposals | memory until applied |

## Data Model & State

MVP0 state should be normalized.
Normalized means store IDs and maps instead of duplicating full objects.
Example: selection stores `phaseId`, not an entire React Flow node object.

The selection model SHOULD be the central cross-feature pointer.
Canvas sets it.
Layout reads it.
Trace enriches it.
Copilot turns it into mention candidates.
Editor uses it for file focus.

Editor state SHOULD gain `activeFocusSide`.
The split focus spec requires it, and current code lacks it.
Current `Workspace` chooses target side from split state and current files, see `apps/studio/frontend/src/components/studio/Workspace.tsx:108` to `apps/studio/frontend/src/components/studio/Workspace.tsx:117`.

Draft state SHOULD be keyed by `skillId + path`, not only skill id.
Current `useDraftPersist` stores a single draft per skill and separate edge draft keys, see `apps/studio/frontend/src/hooks/useDraftPersist.ts:21` to `apps/studio/frontend/src/hooks/useDraftPersist.ts:31`.
MVP0 multi-file editing needs per-file recovery.

Trace state SHOULD be append-only by run id.
Trace visualization MVP0 defines event and index structures; state-management should not redefine event payloads.
It only decides where selected run/filter lives.

Copilot mention state SHOULD reference selection and editor drafts.
It should not copy full file content into global state unless the user sends the message.
This avoids stale prompt context.

## Cross-feature interaction

### State selection owner {#cross-state-selection-owner}

State management owns the shared `StudioSelection` shape.
Canvas sets graph selections in [canvas-topology mvp0](../../canvas-topology/mvp0-alignment.md#cross-canvas-copilot-context).
Trace sets event/edge selections in [trace-visualization mvp0](../../trace-inspector/mvp0-alignment.md#cross-trace-edge-inspection).
Layout renders the selection in [studio-layout mvp0](../studio-layout/mvp0-alignment.md#前端逻辑).

### State draft persistence owner {#cross-state-draft-persistence}

State management defines the draft slice.
Workspace file system owns durable storage implementation in [workspace-file-system mvp0](../workspace-file-system/mvp0-alignment.md#前端逻辑).
Multi-file editor owns editor behavior in [multi-file-editor mvp0](../../asset-explorer/mvp0-alignment.md#cross-editor-copilot-drafts).

### State realtime ingestion owner {#cross-state-realtime-ingestion}

Event bus and WebSocket owns sockets and message schemas.
State management owns how those messages update frontend state.
Realtime transport details are in [event-bus-and-websocket mvp0](../event-bus-and-websocket/mvp0-alignment.md#cross-events-state-ingestion).

