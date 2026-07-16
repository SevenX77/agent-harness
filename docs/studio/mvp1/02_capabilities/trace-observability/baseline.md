---
module: 02_capabilities/trace-observability
doc: baseline
status: FROZEN（2026-07 对账:TracePanel/useRunStream/PromptInspector 均已挂主 Studio 流(Panels.tsx:237 / TimelinePanel.tsx:153);edge dot 双态齐备——运行期 edgeContextFromEvents + 未跑期 staticEdgeInference,假黑板 getMockEdgeContext 已删;edge 上下文已从 Properties 迁到 EdgeContextView。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/TracePanel.tsx:TracePanel · apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream · apps/studio/frontend/src/lib/edge-static-inference.ts:staticEdgeInference · apps/studio/frontend/src/lib/edge-context.ts:edgeContextFromEvents · apps/studio/frontend/src/components/studio/panels/EdgeContextView.tsx:EdgeContextView · apps/studio/backend/app/routers/websockets.py:run_events
units: [trace-dot-blackboard, run-execution-node-status]
---

# trace-observability — Baseline（当下代码实现逻辑）

> **Scope**: trace live/history、dot/黑板语义、prompt inspector、event -> node state 派生的观测能力。
> **现状一句话**: TracePanel/useRunStream/PromptInspector 均已挂主 Studio 流;edge dot 双态齐备(运行期真实事件派生 + 未跑期静态字段推断,假黑板已删);edge 上下文已迁出 Properties 到 EdgeContextView。

## UI/UX
trace live/history、dot/黑板语义、prompt inspector、event -> node state 派生的观测能力。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Trace panel | `TracePanel` 渲染事件/搜索过滤/compare-golden 按钮/虚拟列表,已挂主路径(active run→TracePanel)。 | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:TracePanel（L237）`, `apps/studio/frontend/src/components/TracePanel.tsx:TracePanel（L22）` |
| Run stream hook | `useRunStream` opens run websocket, reconnects, and queues events. | `apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream（L12）`, `apps/studio/frontend/src/hooks/useRunStream.ts:connect（L49）` |
| Prompt inspector | PromptInspector(Template/Variables/Rendered 三视图,均从事件填充)已挂 live + 历史两路径,点 llm_call/prompt_captured 的"Inspect prompt"打开。 | `apps/studio/frontend/src/components/PromptInspector.tsx:PromptInspector（L20）`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:PromptInspector（L153）`, `apps/studio/frontend/src/components/trace/TraceEventRow.tsx:inspectable（L51）` |
| Timeline panel | Mounted Timeline panel shows historical runs, not the full trace stream. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L32）`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L71）` |
| Run detail | `RunDetailDrawer` 组件已删;run-after 概要/全 trace 现经 TimelinePanel 打开选中 run(F2 仍属 target-design,细粒度编辑器视图未落)。 | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:openRun（L107）` |
| Edge context | 点 dot 打开 EdgeContextView(trace-owned):运行期真实事件派生(edgeContextFromEvents)?? 未跑期静态推断(staticEdgeInference);假黑板 getMockEdgeContext 已删。 | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:（L1432-1433）`, `apps/studio/frontend/src/components/studio/panels/EdgeContextView.tsx:EdgeContextView（L256）` |
| Edge trace 归属 | selected-edge 上下文已迁出 Properties,归 trace(EdgeContextView 挂 TimelinePanel/Panels,D14 dot 优先)。 | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:EdgeContextView（L124）`, `apps/studio/frontend/src/components/studio/panels/Panels.tsx:EdgeContextView（L226）` |
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
| trace 挂载 | TracePanel/useRunStream 已挂主路径(active run→TracePanel,Panels.tsx:237)✅ | run live 时可看到流式 trace，结束后可查历史 |
| dot 黑板 | dot 双态:运行期 edgeContextFromEvents ?? 未跑期 staticEdgeInference,mock 已删(GraphCanvas.tsx:1432-1433)✅ | dot 打开真实 transition blackboard / before-after |
| 节点态 | event -> node state 派生未成统一源 | state-engine 消费 trace events 并投影 canvas/timeline |
> **验"是否按目标改了"**：1. trace 挂载；2. dot 黑板；3. 节点态。

## 读代码主路径提示
`apps/studio/frontend/src/components/TracePanel.tsx:TracePanel` → `apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream` → `apps/studio/frontend/src/lib/edge-static-inference.ts:staticEdgeInference` / `apps/studio/frontend/src/lib/edge-context.ts:edgeContextFromEvents` → `apps/studio/frontend/src/components/studio/panels/EdgeContextView.tsx:EdgeContextView` → `apps/studio/backend/app/routers/websockets.py:run_events`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-trace-observability)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `canvas` · `timeline` · `properties` · `debug-resume` · `state-engine` · `engine` observability
