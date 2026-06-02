# event-bus-and-websocket (studio system-level) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Studio backend ↔ frontend realtime communication over WebSocket plus frontend/internal event bus surfaces.
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

当前 realtime 体验有三类。
第一类是 run event stream，供 Trace/Run UI 使用。
第二类是 workspace file change stream，供打开文件冲突和刷新使用。
第三类是 Copilot token/tool streaming，供聊天面板使用。
终端 panel 还有 PTY stream，但它是工具型通道，不是 graph trace。

WebSocket URL 都通过 frontend `wsUrl()` 生成。
它把 API base URL 转成 ws/wss，并把 token 放进 query string，见 `apps/studio/frontend/src/api/client.ts:101` 到 `apps/studio/frontend/src/api/client.ts:108`。
因此 UI 使用者不直接手写 ws 地址。

Run stream 体验有重连。
`useRunStream` 维护 status、reconnectInMs、error、events，见 `apps/studio/frontend/src/hooks/useRunStream.ts:12` 到 `apps/studio/frontend/src/hooks/useRunStream.ts:20`。
消息先进入队列，再每 100ms flush，见 `apps/studio/frontend/src/hooks/useRunStream.ts:32` 到 `apps/studio/frontend/src/hooks/useRunStream.ts:38`。

Copilot stream 体验也有重连和文本 batching。
`useCopilot` 建立 WebSocket，见 `apps/studio/frontend/src/hooks/useCopilot.ts:72` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:102`。
文本 delta 每 75ms flush，见 `apps/studio/frontend/src/hooks/useCopilot.ts:50` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:70`。

Workspace file change 体验是后台发生的。
`Workspace` 监听 `/ws/events`，收到 `skill_changed` 后刷新打开文件或弹 conflict，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:218` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:256`。
这里没有全局 toast feed 或 event center。

## 前端逻辑

当前 frontend 没有统一 event bus library。
没有 `mitt`。
没有 Redux middleware。
有一个 `CustomEvent` 用于 lint status，见 `apps/studio/frontend/src/hooks/useDebouncedLint.ts:6` 到 `apps/studio/frontend/src/hooks/useDebouncedLint.ts:18`。
有一个 `copilotStore` 使用 Set listeners，见 `apps/studio/frontend/src/store/copilotStore.ts:15` 到 `apps/studio/frontend/src/store/copilotStore.ts:25`。

Run WebSocket consumption is hook-local.
`useRunStream` opens one socket per run id, see `apps/studio/frontend/src/hooks/useRunStream.ts:40` to `apps/studio/frontend/src/hooks/useRunStream.ts:75`.
On close it computes exponential backoff through `nextBackoffMs`, see `apps/studio/frontend/src/hooks/useRunStream.ts:64` to `apps/studio/frontend/src/hooks/useRunStream.ts:72`.
The backoff helper caps at 30 seconds in `apps/studio/frontend/src/lib/websocket.ts:9` to `apps/studio/frontend/src/lib/websocket.ts:10`.

Copilot WebSocket consumption is hook-local plus global message store.
`useCopilot` appends normalized events to `copilotStore`, see `apps/studio/frontend/src/hooks/useCopilot.ts:119` to `apps/studio/frontend/src/hooks/useCopilot.ts:141`.
Send payload is only `{ user_message, model_override? }`, see `apps/studio/frontend/src/hooks/useCopilot.ts:143` to `apps/studio/frontend/src/hooks/useCopilot.ts:157`.

Terminal WebSocket consumption is component-local.
`TerminalPanel` opens a socket from session URL, see `apps/studio/frontend/src/components/TerminalPanel.tsx:43` to `apps/studio/frontend/src/components/TerminalPanel.tsx:62`.
This channel sends raw text/bytes rather than JSON event envelopes.

Workspace events are consumed directly in `Workspace`, not in a reusable hook.
That makes file change behavior tightly coupled to Workspace state.
The route is `/ws/events`, not skill-specific.

There is no frontend-level subscription registry for these sockets.
Each hook or component owns its own lifecycle.
For example, `useRunStream` closes its socket from the hook cleanup in `apps/studio/frontend/src/hooks/useRunStream.ts:76` to `apps/studio/frontend/src/hooks/useRunStream.ts:80`.
`Workspace` also closes the event socket from effect cleanup in `apps/studio/frontend/src/components/studio/Workspace.tsx:257` to `apps/studio/frontend/src/components/studio/Workspace.tsx:260`.
That means teardown is understandable locally, but there is no shared place to pause all Studio realtime channels.

The token is appended per socket URL by the common API helper.
The helper reads runtime config and adds `token` only when available, see `apps/studio/frontend/src/api/client.ts:101` to `apps/studio/frontend/src/api/client.ts:108`.
Because token handling sits in one helper, individual UI hooks do not duplicate auth query construction.
The tradeoff is that every socket URL carries the token in the URL rather than in a WebSocket subprotocol or first auth message.

## 后端功能

Backend WebSocket endpoints live in two routers.
Generic websocket endpoints are in `apps/studio/backend/app/routers/websockets.py:27` to `apps/studio/backend/app/routers/websockets.py:63`.
Copilot websocket is in `apps/studio/backend/app/routers/copilot.py:34` to `apps/studio/backend/app/routers/copilot.py:55`.

All generic websocket endpoints validate token query param.
`_websocket_token_is_valid` calls `_is_valid_token`, see `apps/studio/backend/app/routers/websockets.py:17` to `apps/studio/backend/app/routers/websockets.py:24`.
Unauthorized sockets close with 4401, see `apps/studio/backend/app/routers/websockets.py:23` to `apps/studio/backend/app/routers/websockets.py:24`.

`/ws/runs/{run_id}` streams run manager queue events.
The route accepts, calls `run_manager.stream_run(run_id)`, then sends each event JSON until `None`, see `apps/studio/backend/app/routers/websockets.py:27` to `apps/studio/backend/app/routers/websockets.py:39`.
Run events are produced by `_queue_event_subscriber(process_queue)` and `run_skill(event_subscriber=...)`, see `apps/studio/backend/app/services/run_manager.py:74` to `apps/studio/backend/app/services/run_manager.py:104`.

`/ws/events` streams the in-memory event bus topic.
The route subscribes to `STUDIO_EVENTS_TOPIC` and `send_json`s each event, see `apps/studio/backend/app/routers/websockets.py:50` to `apps/studio/backend/app/routers/websockets.py:63`.
The event bus is an in-memory queue-based pub/sub, see `apps/studio/backend/app/core/adapters/eventbus_memory.py:10` to `apps/studio/backend/app/core/adapters/eventbus_memory.py:45`.

File watcher publishes to that event bus from a watchdog thread.
`broadcast_from_thread` schedules publication on the saved event loop, see `apps/studio/backend/app/core/adapters/eventbus_memory.py:59` to `apps/studio/backend/app/core/adapters/eventbus_memory.py:69`.
File watcher builds `skill_changed` events in `apps/studio/backend/app/services/file_watcher.py:120` to `apps/studio/backend/app/services/file_watcher.py:132`.

`/ws/terminal/{term_id}` bridges a PTY.
The router delegates to terminal manager, see `apps/studio/backend/app/routers/websockets.py:42` to `apps/studio/backend/app/routers/websockets.py:47`.
Terminal manager accepts and starts read/write tasks, see `apps/studio/backend/app/services/terminal_manager.py:86` to `apps/studio/backend/app/services/terminal_manager.py:104`.

Copilot WS loops forever: receive JSON, validate request, stream backend events to frontend.
The route receives `CopilotWsRequestPayload` and sends event model dumps, see `apps/studio/backend/app/routers/copilot.py:44` to `apps/studio/backend/app/routers/copilot.py:55`.

Backend disconnect semantics are best-effort.
The generic run stream exits when `stream_run` yields `None`, not through an explicit typed terminal envelope.
The event bus route catches `WebSocketDisconnect` and then unsubscribes, see `apps/studio/backend/app/routers/websockets.py:56` to `apps/studio/backend/app/routers/websockets.py:63`.
Terminal handling delegates disconnect behavior to the terminal manager, which reads browser input and PTY output in separate tasks.

Event bus lifetime is process-local.
`InMemoryEventBus` is created through app dependency wiring, and subscribers are asyncio queues held in memory.
If the backend process restarts, `/ws/events` has no replay source.
That is acceptable for current file-change refresh hints, but it is not enough for audit-grade trace history.

## API

Current websocket endpoint inventory:

| Endpoint | Owner | Payload |
|---|---|---|
| `GET ws /ws/runs/{run_id}` | RunManager | JSON callback/run events |
| `GET ws /ws/events` | EventBus/FileWatcher | JSON studio events |
| `GET ws /ws/terminal/{term_id}` | TerminalManager | text/bytes PTY data |
| `GET ws /api/skills/{skill_id}/copilot/ws` | Copilot | JSON Copilot events |

Current run URL helper:

```typescript
export type WebSocketStatus = "idle" | "connecting" | "open" | "closed" | "reconnecting" | "error"

export function runEventsWsUrl(runId: string): string
export function nextBackoffMs(attempt: number): number
```

The real helper is in `apps/studio/frontend/src/lib/websocket.ts:3` to `apps/studio/frontend/src/lib/websocket.ts:10`.

Current file watcher event shape:

```typescript
export interface SkillChangedEvent {
  type: "skill_changed"
  skill_id: string
  path: string
  change: string
  hash: string | null
  mtime: number | null
}
```

The backend dict is built in `apps/studio/backend/app/services/file_watcher.py:125` to `apps/studio/backend/app/services/file_watcher.py:132`.

Current Copilot request:

```python
class CopilotWsRequestPayload(BaseModel):
    user_message: str
    model_override: str | None = None
```

The model is referenced by route in `apps/studio/backend/app/routers/copilot.py:47` to `apps/studio/backend/app/routers/copilot.py:52`.

Current terminal stream shape:

```typescript
type TerminalWireMessage = string
```

The browser sends terminal input as text through `TerminalPanel`, see `apps/studio/frontend/src/components/TerminalPanel.tsx:57` to `apps/studio/frontend/src/components/TerminalPanel.tsx:62`.
The backend websocket route forwards the socket to `terminal_manager.handle_ws`, see `apps/studio/backend/app/routers/websockets.py:42` to `apps/studio/backend/app/routers/websockets.py:47`.
This is intentionally not JSON because PTY I/O is byte/text oriented.

Current internal browser event shape:

```typescript
export type SkillLintStatusEvent = CustomEvent<{
  skillId: string
  status: "idle" | "running" | "ok" | "error"
}>
```

The implementation dispatches `skill-lint-status` from `useDebouncedLint`, see `apps/studio/frontend/src/hooks/useDebouncedLint.ts:6` to `apps/studio/frontend/src/hooks/useDebouncedLint.ts:18`.
This is the only browser event-bus style contract found in the inspected frontend.

## Data Model & State

Run events are open JSON today.
Frontend type `CallbackEvent` is a base event plus arbitrary JSON fields, referenced by `useRunStream` in `apps/studio/frontend/src/hooks/useRunStream.ts:1` to `apps/studio/frontend/src/hooks/useRunStream.ts:3`.
This makes Trace flexible but weakly typed.

Studio event bus events are `dict[str, Any]` internally.
`InMemoryEventBus` stores subscribers as queues by topic, see `apps/studio/backend/app/core/adapters/eventbus_memory.py:15` to `apps/studio/backend/app/core/adapters/eventbus_memory.py:27`.
There is no persisted event log for `/ws/events`.

WebSocket backpressure is simple batching on frontend.
Run stream flushes every 100ms.
Copilot text stream flushes every 75ms.
Backend generic streams await `send_json`, so slow clients can back up route handling.

Reconnect behavior exists on run and Copilot streams.
Workspace `/ws/events` has no explicit reconnect logic; it opens socket in an effect and closes on cleanup.
Terminal panel behavior is separate.

There is no bridge to engine `TraceEventKind` yet.
Engine tracing MVP0 proposes a typed event enum; current Studio consumes callback events from legacy callback adapters.

Ordering is channel-local.
One WebSocket preserves message order for that connection, but Studio does not define ordering across `/ws/runs/{run_id}`, `/ws/events`, Copilot, and terminal channels.
For example, a file watcher change and a run callback can arrive in either UI order.
Current UI code treats them as independent state updates, which matches the present behavior.

Message identity is partial.
Run events are appended by frontend array position.
File watcher events include `path`, `hash`, and `mtime`, but no event id.
Copilot events are normalized into store messages by the hook/store path, not by server sequence id.
This keeps the baseline simple, but it also means reconnect dedupe is not exact.

## Cross-feature interaction

### Events state bridge owner {#cross-events-state-bridge}

This baseline owns realtime endpoint inventory.
State update ownership is documented in [state-management baseline](../state-management/baseline.md#cross-state-event-bridge).

### Events trace current gap {#cross-events-trace-current-gap}

Trace visualization currently receives open callback JSON, not a typed V2 trace stream.
Feature details are in [trace-visualization baseline](../../trace-inspector/baseline.md).

### Events workspace watcher {#cross-events-workspace-watcher}

File watcher events feed editor conflict/reload.
Filesystem details are in [workspace-file-system baseline](../workspace-file-system/baseline.md).
