# trace-visualization (studio feature) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: 历史溯源、瀑布流展示、图节点边级错误追踪 (Edge Inspection / Compile 结构化报错)
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL make trace visualization answer one PM question: "what did each phase receive, produce, and fail on?"
The current list, filter, and missing Edge Inspection are documented in [baseline.md](./baseline.md).

First term: Trace means a chronological record of runtime events.
Example events are phase start, phase end, LLM call, tool call, compile error, and exception.
Current `TracePanel` already renders events, filters, search, and golden buttons in `apps/studio/frontend/src/components/TracePanel.tsx:22` to `apps/studio/frontend/src/components/TracePanel.tsx:110`.

MVP0 SHOULD keep the virtual waterfall list.
Waterfall means a vertical timeline where each row is an event and nested activity is visually indented.
Current `VirtualTraceList` renders a windowed list for performance, see `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx:26` to `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx:59`.
MVP0 SHOULD add nested phase grouping without losing virtualization.

MVP0 WILL implement Edge Inspection.
Edge Inspection means clicking a canvas edge to see source phase output and target phase input.
The spec states this exact behavior in `.kiro/specs/trace-and-predict-visibility/requirement.md:32` to `.kiro/specs/trace-and-predict-visibility/requirement.md:37`.
Current edge click only stops propagation in `apps/studio/frontend/src/components/edges/ContextEdge.tsx:48` to `apps/studio/frontend/src/components/edges/ContextEdge.tsx:59`.

MVP0 SHOULD show a right or bottom Context Inspector panel.
It SHOULD render JSON in a read-only Monaco view for large payloads.
It SHOULD show truncation state when payloads are large because the spec warns against browser OOM in `.kiro/specs/trace-and-predict-visibility/requirement.md:56` to `.kiro/specs/trace-and-predict-visibility/requirement.md:58`.

MVP0 SHOULD make compile errors PM-readable.
PM-readable means "Phase `summarize` depends on missing phase `extract` in GRAPH.md line 23", not a raw Python stack.
The existing compile panel lives in `apps/studio/frontend/src/components/studio/Workspace.tsx:452` to `apps/studio/frontend/src/components/studio/Workspace.tsx:472`.
MVP0 SHOULD add file:line jump and Ask Copilot actions.

MVP0 SHOULD keep prompt inspection and expand it.
Current rows allow prompt inspection for `prompt_rendered` and `llm_call`, see `apps/studio/frontend/src/components/trace/TraceEventRow.tsx:44` to `apps/studio/frontend/src/components/trace/TraceEventRow.tsx:45`.
MVP0 SHOULD also inspect tool calls, subagent entry, and subgraph entry when engine emits those events.

## 前端逻辑

MVP0 WILL consume engine V2 trace events instead of inferring everything from generic callback JSON.
Current `CallbackEvent` is an open JSON record, see `apps/studio/frontend/src/api/types.ts:408` to `apps/studio/frontend/src/api/types.ts:428`.
MVP0 SHOULD define a typed `StudioTraceEvent` union that mirrors engine `TraceEventKind`.

The run stream hook SHOULD remain the realtime input.
Current `useRunStream` uses `runEventsWsUrl(runId)`, queues events, and flushes every 100ms, see `apps/studio/frontend/src/hooks/useRunStream.ts:12` to `apps/studio/frontend/src/hooks/useRunStream.ts:72`.
MVP0 SHOULD keep batching but preserve event order by `sequence`.

Filtering SHOULD become structured.
Current `useTraceFilter` filters by search/type/phase, see `apps/studio/frontend/src/hooks/useTraceFilter.ts:20` to `apps/studio/frontend/src/hooks/useTraceFilter.ts:75`.
MVP0 SHOULD add filters for failed-only, has-prompt, has-edge-snapshot, LLM-only, tool-only, and phase input/output.

Edge Inspection SHOULD be selected by `(runId, sourcePhaseId, targetPhaseId)`.
Canvas owns the click; Trace owns the lookup.
The current `ContextEdgeData` already has `sourcePhaseId`, `targetPhaseId`, `hasTraceData`, and `contextJson`, see `apps/studio/frontend/src/components/edges/ContextEdge.tsx:5` to `apps/studio/frontend/src/components/edges/ContextEdge.tsx:10`.
MVP0 SHOULD stop storing full JSON on the edge object and fetch the snapshot by id.

```typescript
export type StudioTraceKind =
  | "RUN_START"
  | "RUN_END"
  | "PHASE_START"
  | "PHASE_END"
  | "PHASE_INPUT"
  | "PHASE_OUTPUT"
  | "LLM_CALL_START"
  | "LLM_CALL_END"
  | "TOOL_CALL_START"
  | "TOOL_CALL_END"
  | "SUBGRAPH_ENTER"
  | "SUBGRAPH_EXIT"
  | "EXCEPTION"
  | "COMPILE_ISSUE";

export interface StudioTraceEvent {
  id: string;
  runId: string;
  sequence: number;
  timestamp: string;
  kind: StudioTraceKind;
  phaseId?: string;
  parentEventId?: string;
  durationMs?: number;
  input?: unknown;
  output?: unknown;
  error?: { code?: string; message: string; filePath?: string; line?: number };
  prompt?: { messages: unknown[]; rendered?: string; model?: string };
  tokenUsage?: { input?: number; output?: number; total?: number };
}
```

MVP0 SHOULD derive node highlight from trace events.
The trace research recommends frontend consuming business events and deriving UI state, not backend sending "make border red" commands, see `.kiro/specs/trace-and-predict-visibility/research.md:86` to `.kiro/specs/trace-and-predict-visibility/research.md:90`.

## 后端功能

MVP0 WILL depend on engine tracing work.
Engine mvp0 defines `V2TracingCallback` and `TraceEventKind`, see [tracing-and-observability mvp0](../../../engine/tracing-and-observability/mvp0-alignment.md#api).
Studio SHOULD not invent a parallel runtime event model that engine cannot emit.

The backend SHOULD persist traces after run.
Current run detail already reads events/final state/artifacts from run directory, see `apps/studio/backend/app/services/run_manager.py:408` to `apps/studio/backend/app/services/run_manager.py:422`.
MVP0 SHOULD store trace events so refresh and historical replay work.
The trace research recommends local `.workspace` trace storage in `.kiro/specs/trace-and-predict-visibility/research.md:82` to `.kiro/specs/trace-and-predict-visibility/research.md:90`.

The backend SHOULD expose edge snapshots.
Edge snapshots are not separate engine work; they are projections over phase input/output events.
Engine state-and-io mvp0 defines isolated `phase_input` and `phase_outputs`, see [state-and-io-contract mvp0](../../../engine/state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation).

The backend SHOULD normalize compile errors into the same display model.
Compile errors currently affect Workspace compile state in `apps/studio/frontend/src/components/studio/Workspace.tsx:292` to `apps/studio/frontend/src/components/studio/Workspace.tsx:322`.
Engine skill-compilation mvp0 defines `CompileIssue`, see [skill-compilation mvp0](../../../engine/skill-compilation/mvp0-alignment.md#api).

Studio 的 queue subscriber 是 adapter, not source of truth.
It maps engine `CallbackEvent` values into queue events via `_queue_event_subscriber`, see `apps/studio/backend/app/services/run_manager.py:74` to `apps/studio/backend/app/services/run_manager.py:78`.
MVP0 SHOULD adapt engine typed trace events into the same WebSocket stream.

## API

MVP0 SHOULD keep current run endpoints and add trace replay/edge inspection endpoints.
Existing run endpoints are in `apps/studio/backend/app/routers/runs.py:27` to `apps/studio/backend/app/routers/runs.py:55`.
Current run stream is WebSocket, used by `apps/studio/frontend/src/hooks/useRunStream.ts:49` to `apps/studio/frontend/src/hooks/useRunStream.ts:57`.

```typescript
export interface ListTraceEventsRequest {
  skillId: string;
  runId: string;
  afterSequence?: number;
  limit?: number;
  phaseId?: string;
  kinds?: StudioTraceKind[];
}

export interface ListTraceEventsResponse {
  runId: string;
  events: StudioTraceEvent[];
  nextAfterSequence?: number;
}

export interface EdgeInspectionRequest {
  skillId: string;
  runId: string;
  sourcePhaseId: string;
  targetPhaseId: string;
}

export interface EdgeInspectionResponse {
  runId: string;
  sourcePhaseId: string;
  targetPhaseId: string;
  sourceOutput: unknown;
  targetInput: unknown;
  blackboardDiff?: unknown;
  events: StudioTraceEvent[];
  truncated: boolean;
  truncationMessage?: string;
}
```

Proposed REST signatures:

```http
GET /api/skills/{skill_id}/runs/{run_id}/trace?after_sequence=0&limit=200
ListTraceEventsResponse

GET /api/skills/{skill_id}/runs/{run_id}/trace/edge?source_phase_id=a&target_phase_id=b
EdgeInspectionResponse
```

MVP0 SHOULD extend compile response shape.

```typescript
export interface StudioCompileIssue {
  severity: "error" | "warning";
  code: string;
  message: string;
  filePath?: string;
  line?: number;
  column?: number;
  phaseId?: string;
  field?: string;
  askCopilotPayload?: {
    mention: CopilotCompileErrorMention;
    prompt: string;
  };
}
```

## Data Model / State

MVP0 SHOULD keep trace state append-only.
Append-only means new events are appended by sequence and never edited in place.
Derived UI state like active phase, failed phase, and edge has trace data can be recomputed from events.

```typescript
export interface TraceVisualizationState {
  runId?: string;
  eventsById: Record<string, StudioTraceEvent>;
  orderedEventIds: string[];
  activePhaseIds: Set<string>;
  selectedEventId?: string;
  selectedEdge?: {
    sourcePhaseId: string;
    targetPhaseId: string;
    runId: string;
  };
  filters: {
    query: string;
    kinds: StudioTraceKind[];
    phaseIds: string[];
    failedOnly: boolean;
    hasPayloadOnly: boolean;
  };
}
```

MVP0 SHOULD make edge trace availability a derived index.

```typescript
export interface EdgeTraceIndex {
  [edgeKey: `${string}->${string}`]: {
    runId: string;
    sourcePhaseId: string;
    targetPhaseId: string;
    hasInput: boolean;
    hasOutput: boolean;
    latestEventId?: string;
  };
}
```

MVP0 SHOULD cap large JSON payloads.
The UI state SHOULD store a preview and a fetch token, not always the full payload.
This protects the virtual list and Context Inspector from huge tool outputs.

## Cross-feature interaction

### Trace edge inspection owner {#cross-trace-edge-inspection}

Trace visualization owns the data for Edge Inspection.
Canvas owns the click source and selected edge UI, see [canvas-topology mvp0](../canvas-topology/mvp0-alignment.md#cross-canvas-edge-inspection).
Layout owns where Context Inspector appears, see [studio-layout mvp0](../../system-level/studio-layout/mvp0-alignment.md#前端逻辑).

### Trace compile issues {#cross-trace-compile-issues}

Trace visualization owns PM-readable display of compile and run issues.
Engine compile issue shape is owned by [skill-compilation mvp0](../../../engine/skill-compilation/mvp0-alignment.md#api).
Copilot owns Ask Copilot payload handling in [copilot-assistance mvp0](../copilot-assistance/mvp0-alignment.md#cross-copilot-mentions).

### Trace golden lifecycle {#cross-trace-golden}

Trace can promote a run to golden and compare future runs.
Skill lifecycle owns the broader batch/golden workflow in [skill-lifecycle mvp0](../skill-lifecycle/mvp0-alignment.md#cross-lifecycle-golden-batch).

### Trace provider errors {#cross-trace-provider-errors}

Provider and model errors SHOULD link to LLM Provider Config.
LLM provider setup and ModelResolver linkage are specified in [llm-provider-config mvp0](../llm-provider-config/mvp0-alignment.md#cross-llm-role-resolution).
