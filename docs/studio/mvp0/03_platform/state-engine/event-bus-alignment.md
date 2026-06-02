# event-bus-and-websocket (studio system-level) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Studio backend ↔ frontend realtime communication over WebSocket plus frontend/internal event bus surfaces.
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL make realtime behavior predictable: run trace streams, Copilot tokens stream, file changes notify, and compile progress can surface without refresh.
The current endpoint inventory is in [baseline.md](./baseline.md).

First term: event bus means a publish/subscribe channel where one producer sends an event and many consumers can receive it.
First term: WebSocket means a persistent browser-backend connection used for live updates.
Studio already uses WebSocket, but MVP0 needs typed message contracts.

MVP0 SHOULD show connection state for long-running streams.
Run stream already has `status` and `reconnectInMs` in `useRunStream`, see `apps/studio/frontend/src/hooks/useRunStream.ts:12` to `apps/studio/frontend/src/hooks/useRunStream.ts:20`.
Copilot has `connectionStatus`, `reconnectInMs`, and `lastError`, see `apps/studio/frontend/src/hooks/useCopilot.ts:25` to `apps/studio/frontend/src/hooks/useCopilot.ts:33`.
MVP0 should standardize this UI language.

MVP0 SHOULD make backpressure visible only when it affects user work.
Backpressure means the producer sends faster than the consumer can render or process.
The user should not see internal queue sizes, but should see "trace stream paused/reconnecting" if the stream falls behind.

MVP0 SHOULD keep file-change notifications non-intrusive.
If an open file changes remotely and the user is editing, show conflict.
If not editing, refresh silently.
This is already partly implemented in `apps/studio/frontend/src/components/studio/Workspace.tsx:229` to `apps/studio/frontend/src/components/studio/Workspace.tsx:249`.

## 前端逻辑

MVP0 WILL add a shared websocket client layer.
Today run, Copilot, workspace, and terminal each open sockets separately.
MVP0 SHOULD keep feature hooks, but route them through a common client for auth, reconnect, heartbeat, and backpressure policy.

```typescript
export interface StudioSocketOptions<TIn, TOut> {
  url: string;
  parse(raw: MessageEvent): TOut;
  serialize?(message: TIn): string | ArrayBuffer;
  reconnect: { enabled: boolean; maxDelayMs: number };
  backpressure: { maxQueuedMessages: number; dropPolicy: "oldest" | "newest" | "close" };
  onMessage(message: TOut): void;
  onStatus(status: WebSocketStatus): void;
}

export interface StudioSocketHandle<TIn> {
  send(message: TIn): boolean;
  close(): void;
}
```

MVP0 SHOULD add a frontend event dispatcher for cross-component events.
It does not need to replace React state.
It should carry events like `selection.changed`, `file.changed`, `trace.event_received`, `copilot.patch_proposed`.

```typescript
export type StudioClientEvent =
  | { type: "selection.changed"; selection: unknown }
  | { type: "file.changed"; skillId: string; path: string; hash?: string | null }
  | { type: "trace.event_received"; runId: string; event: unknown }
  | { type: "copilot.patch_proposed"; proposalId: string }
  | { type: "compile.issue"; skillId: string; issue: unknown };
```

MVP0 SHOULD let state-management consume these events through one ingestion point.
The state owner is [state-management mvp0](../state-management/mvp0-alignment.md#cross-state-realtime-ingestion).

Run trace SHOULD use typed events.
Trace visualization MVP0 defines `StudioTraceEvent`; engine tracing MVP0 defines `TraceEventKind`.
The stream should not remain arbitrary callback JSON.

Copilot SHOULD use request IDs.
Current Copilot WS sends payload without request id, see `apps/studio/frontend/src/hooks/useCopilot.ts:151` to `apps/studio/frontend/src/hooks/useCopilot.ts:155`.
MVP0 should tie text deltas, tool events, patch proposals, and done/error to one request id.

## 后端功能

MVP0 SHOULD add typed trace stream support.
Existing `/ws/runs/{run_id}` can continue, but it should stream `StudioTraceEvent` envelopes for V2.1 runs.
The current route sends queue events from `run_manager.stream_run`, see `apps/studio/backend/app/routers/websockets.py:27` to `apps/studio/backend/app/routers/websockets.py:39`.

MVP0 SHOULD keep `/ws/events` for workspace/global events.
The in-memory event bus can remain for local Studio, see `apps/studio/backend/app/core/adapters/eventbus_memory.py:10` to `apps/studio/backend/app/core/adapters/eventbus_memory.py:45`.
But payloads should be typed Pydantic models before `send_json`.

MVP0 SHOULD add compile progress stream only if compile becomes long-running.
For MVP0, compile can still be HTTP request/response.
If compile progress is added, it should share the same event envelope rather than a bespoke shape.

Copilot WS SHOULD move to typed request/response.
Current route reads `CopilotWsRequestPayload` and streams events, see `apps/studio/backend/app/routers/copilot.py:44` to `apps/studio/backend/app/routers/copilot.py:55`.
Copilot feature owns mention payload and patch events in [copilot-assistance mvp0](../../copilot-chat/mvp0-alignment.md#cross-copilot-mentions).

MVP0 SHOULD add heartbeat or ping semantics for long streams.
This can be an app-level event if browser WebSocket ping is unavailable.
Heartbeat helps detect dead connections without waiting for user action.

## API

Unified envelope:

```typescript
export interface StudioWsEnvelope<TType extends string, TPayload> {
  type: TType;
  id: string;
  timestamp: string;
  skillId?: string;
  runId?: string;
  sequence?: number;
  payload: TPayload;
}
```

Python model:

```python
class StudioWsEnvelope(BaseModel, Generic[T]):
    type: str
    id: str
    timestamp: datetime
    skill_id: str | None = None
    run_id: str | None = None
    sequence: int | None = None
    payload: T
```

Proposed endpoints:

```http
GET /ws/runs/{run_id}/trace
  -> StudioWsEnvelope["trace.event", StudioTraceEvent]

GET /ws/events
  -> StudioWsEnvelope["skill.changed" | "workspace.changed" | "system.notice", object]

GET /api/skills/{skill_id}/copilot/ws
  <-> CopilotWsClientMessage / CopilotWsServerEvent
```

Trace event payload should align with [trace-visualization mvp0](../../trace-inspector/mvp0-alignment.md#cross-trace-edge-inspection) and [tracing-and-observability mvp0](../../../engine/tracing-and-observability/mvp0-alignment.md#api).

Backpressure policy:

```typescript
export interface WsBackpressurePolicy {
  maxQueuedMessages: number;
  maxBatchIntervalMs: number;
  onOverflow: "drop_oldest_preview_events" | "close_with_error" | "request_replay";
}
```

Replay request:

```typescript
export interface ReplayTraceRequest {
  runId: string;
  afterSequence: number;
  limit: number;
}
```

## Data Model & State

MVP0 SHOULD make every stream ordered or explicitly unordered.
Run trace is ordered by sequence.
Workspace file events are unordered notifications.
Copilot token events are ordered per request id.
Terminal data is raw ordered stream.

MVP0 SHOULD store last seen sequence for replayable streams.
Trace stream should resume with `afterSequence`.
Workspace events can revalidate via `getSkillDetail`.
Copilot can reconnect but should not replay arbitrary tokens unless session supports it.

MVP0 SHOULD define event durability.
Trace events should persist with runs.
Workspace events are ephemeral.
Copilot messages are memory for MVP0 unless session history is explicitly saved.
Terminal output is ephemeral.

MVP0 SHOULD avoid sending UI commands over backend streams.
Backend should send facts: phase started, file changed, trace event, compile issue.
Frontend decides border colors, tabs, and badges.
This matches trace research and keeps frontend behavior testable.

## Cross-feature interaction

### Events state ingestion owner {#cross-events-state-ingestion}

Event bus and WebSocket owns socket and envelope contracts.
State management owns how envelopes update UI state, see [state-management mvp0](../state-management/mvp0-alignment.md#cross-state-realtime-ingestion).

### Events trace stream owner {#cross-events-trace-stream}

Trace visualization owns trace rendering and filters.
Engine tracing owns event production.
This document owns transport shape between backend and frontend.
See [trace-visualization mvp0](../../trace-inspector/mvp0-alignment.md#cross-trace-edge-inspection).

### Events Copilot stream owner {#cross-events-copilot-stream}

Copilot owns token/tool/patch message schema.
Transport must support request id, streaming deltas, errors, and done events.
See [copilot-assistance mvp0](../../copilot-chat/mvp0-alignment.md#cross-copilot-mentions).

### Events lifecycle batch owner {#cross-events-lifecycle-batch}

Skill lifecycle batch runs should publish progress through run/trace streams rather than polling only.
Lifecycle owner is [skill-lifecycle mvp0](../../skill-lifecycle/mvp0-alignment.md#cross-lifecycle-golden-batch).

