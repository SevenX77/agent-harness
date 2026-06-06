---
module: 02_capabilities/trace-observability
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；TracePanel/useRunStream/PromptInspector 存在但未挂主 Studio 流；edge dot 仍是假黑板 JSON ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/TracePanel.tsx:TracePanel · apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream · apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext · apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:PropertiesPanel · apps/studio/backend/app/routers/websockets.py:run_events
units: [trace-dot-blackboard, run-execution-node-status]
---

# trace-observability — Baseline（当下代码实现逻辑）

> **Scope**: trace live/history、dot/黑板语义、prompt inspector、event -> node state 派生的观测能力。
> **现状一句话**: TracePanel/useRunStream/PromptInspector 存在但未挂主 Studio 流；edge dot 仍是假黑板 JSON ⚠️。

## UI/UX
trace live/history、dot/黑板语义、prompt inspector、event -> node state 派生的观测能力。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Trace panel | `TracePanel` can render events, search/filter, compare/golden buttons, and virtualized list; it is not mounted in the Studio panels. | `apps/studio/frontend/src/components/TracePanel.tsx:TracePanel（L22）`, `apps/studio/frontend/src/components/TracePanel.tsx:filter（L50）` |
| Run stream hook | `useRunStream` opens run websocket, reconnects, and queues events. | `apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream（L12）`, `apps/studio/frontend/src/hooks/useRunStream.ts:connect（L49）` |
| Prompt inspector | Prompt inspector dialog exists with Template, Variables, and Rendered tabs. | `apps/studio/frontend/src/components/PromptInspector.tsx:PromptInspector（L20）`, `apps/studio/frontend/src/components/PromptInspector.tsx:PromptInspector（L44）` |
| Timeline panel | Mounted Timeline panel shows historical runs, not the full trace stream. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L32）`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L71）` |
| Run detail | `RunDetailDrawer` exists with Replay/Compare/Export and payload blocks; not mounted in Workspace flow. | `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer（L27）`, `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer（L54）` |
| Edge context | Context edge click opens mock upstream JSON in Properties. | `apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext（L30）`, `apps/studio/frontend/src/components/edges/ContextEdge.tsx:buttonClasses（L206）` |
| Properties trace | Properties panel renders selected-edge "Connection Trace" as JSON dump. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:next（L195）` |
| Engine trace | graph-agent writes typed callback events to `trace.jsonl`. | `packages/graph-agent/src/graph_agent/callbacks/tracing.py:set_trace_dir（L80）`, `packages/graph-agent/src/graph_agent/callbacks/tracing.py:_write_typed_event（L101）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Backend stream | Backend exposes `/ws/runs/{run_id}` and reads trace/run events. | `apps/studio/backend/app/routers/websockets.py:_close_unauthorized（L27）`, `apps/studio/backend/app/services/run_manager.py:stream_run（L334）` |
| Engine trace | graph-agent writes typed callback events to `trace.jsonl`. | `packages/graph-agent/src/graph_agent/callbacks/tracing.py:set_trace_dir（L80）`, `packages/graph-agent/src/graph_agent/callbacks/tracing.py:_write_typed_event（L101）` |

## 当前边界（trace-observability 现在不是什么）
- 事件源 contract 归 engine observability；Studio 不复制 engine callback 细节。
- 节点态投影 owner 是 `state-engine`，trace 只拥有语义与消费。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| trace 挂载 | TracePanel/useRunStream 未挂 Timeline/Workspace 主路径 ⚠️ | run live 时可看到流式 trace，结束后可查历史 |
| dot 黑板 | ContextEdge 用 mock JSON ⚠️ | dot 打开真实 transition blackboard / before-after |
| 节点态 | event -> node state 派生未成统一源 | state-engine 消费 trace events 并投影 canvas/timeline |
> **验"是否按目标改了"**：1. trace 挂载；2. dot 黑板；3. 节点态。

## 读代码主路径提示
`apps/studio/frontend/src/components/TracePanel.tsx:TracePanel` → `apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream` → `apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext` → `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:PropertiesPanel` → `apps/studio/backend/app/routers/websockets.py:run_events`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-trace-observability)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `canvas` · `timeline` · `properties` · `debug-resume` · `state-engine` · `engine` observability
