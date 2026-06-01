# trace-visualization (studio feature) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: run trace / predict trace 可视化、事件列表、prompt inspection、edge inspection
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

Trace 面板入口是 `TracePanel`，它展示运行事件列表、搜索、过滤、link views、compare to golden 和 promote to golden 操作，见 `apps/studio/frontend/src/components/TracePanel.tsx:22` 到 `apps/studio/frontend/src/components/TracePanel.tsx:110`。没有事件时显示 “Waiting for run events”，见 `apps/studio/frontend/src/components/TracePanel.tsx:37` 到 `apps/studio/frontend/src/components/TracePanel.tsx:47`。

列表采用虚拟滚动，`VirtualTraceList` 以固定 row height 128 计算可视窗口，并只渲染当前窗口内的行，见 `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx:26` 到 `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx:59`。列表提供 listbox 语义、键盘上下移动和 Enter/Space 展开，见 `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx:115` 到 `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx:146`。

单行事件由 `TraceEventRow` 展示，包含 timeline dot、事件类型 badge、token badge、mocked source badge、phase/message、错误信息、inspect prompt 按钮和原始 JSON 展开区，见 `apps/studio/frontend/src/components/trace/TraceEventRow.tsx:44` 到 `apps/studio/frontend/src/components/trace/TraceEventRow.tsx:122`。Prompt inspection 只对 `prompt_rendered` 和 `llm_call` 这类事件开放，见 `apps/studio/frontend/src/components/trace/TraceEventRow.tsx:44` 到 `apps/studio/frontend/src/components/trace/TraceEventRow.tsx:45`。

Edge Inspection 当前缺失。Canvas 的边按钮有 “查看连线传递数据” aria-label，但点击只阻止冒泡，没有打开 trace drawer 或 edge panel，见 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:48` 到 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:59`。`buildEdges` 还把 `hasTraceData` 固定为 false，见 `apps/studio/frontend/src/components/nodes/buildEdges.ts:8` 到 `apps/studio/frontend/src/components/nodes/buildEdges.ts:20`。

## 前端逻辑

TracePanel 先调用 `useTraceFilter(traceLogs, linkEnabled ? activePhase : null)`，再把过滤后的事件交给虚拟列表，见 `apps/studio/frontend/src/components/TracePanel.tsx:35` 到 `apps/studio/frontend/src/components/TracePanel.tsx:110`。这意味着 link views 打开时，列表会自动按 active phase 收窄。

过滤 hook 管理搜索文本、事件类型集合和 phase 集合，过滤条件包括 message/type/phase/activePhase，见 `apps/studio/frontend/src/hooks/useTraceFilter.ts:20` 到 `apps/studio/frontend/src/hooks/useTraceFilter.ts:75`。它会从当前事件集合推导可选 event types 和 phases，见 `apps/studio/frontend/src/hooks/useTraceFilter.ts:34` 到 `apps/studio/frontend/src/hooks/useTraceFilter.ts:40`。

运行事件流由 `useRunStream` 订阅 WebSocket。Hook 根据 runId 建立 `runEventsWsUrl(runId)`，收到消息后解析成 `CallbackEvent` 并进入队列，每 100ms 批量 flush 到 React state，见 `apps/studio/frontend/src/hooks/useRunStream.ts:12` 到 `apps/studio/frontend/src/hooks/useRunStream.ts:72`。异常关闭会进行最多 5 次重连，见 `apps/studio/frontend/src/hooks/useRunStream.ts:64` 到 `apps/studio/frontend/src/hooks/useRunStream.ts:72`。

Trace 列表有 selected event 定位逻辑：当 `selectedEventId` 存在时，虚拟列表会计算位置并滚动到相应 row，见 `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx:64` 到 `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx:83`。Predict trace 会根据 `mocked_source` 或部分 event type 标记，见 `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx:60` 到 `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx:63`。

## 后端功能

运行时事件来自 `RunManager` 和 `_queue_event_subscriber(process_queue)`。subscriber 会把 graph-agent 的 `phase_start`、`phase_end`、`llm_call` 等 typed event 转换为 Studio run event，并进入队列，见 `apps/studio/backend/app/services/run_manager.py:74` 到 `apps/studio/backend/app/services/run_manager.py:78`。实际运行 skill 时，subprocess worker 调用 `run_skill(event_subscriber=emit_to_queue, ...)`，默认 trace 由 engine 内部写入 `trace.jsonl`，见 `apps/studio/backend/app/services/run_manager.py:95` 到 `apps/studio/backend/app/services/run_manager.py:104`。

运行结束后，后端写入 final_state 和 metrics，见 `apps/studio/backend/app/services/run_manager.py:238` 到 `apps/studio/backend/app/services/run_manager.py:243`。获取 run detail 时返回 metadata、input_data、events、final_context 和 artifacts，见 `apps/studio/backend/app/services/run_manager.py:408` 到 `apps/studio/backend/app/services/run_manager.py:422`。

Predict 诊断通过 predictor/diagnostic export 生成，并能作为 compare/golden 的输入。predict router endpoint 在 `apps/studio/backend/app/routers/runs.py:32` 到 `apps/studio/backend/app/routers/runs.py:40`，诊断 export 函数在 `apps/studio/backend/app/services/diagnostic_export.py:13` 到 `apps/studio/backend/app/services/diagnostic_export.py:57`。

Compile errors 不是 trace event，但会在同一工作流里影响用户理解运行前状态。Workspace 的 compile 逻辑在 `apps/studio/frontend/src/components/studio/Workspace.tsx:292` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:322`，compile error panel 渲染在 `apps/studio/frontend/src/components/studio/Workspace.tsx:452` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:472`。

## API

Run APIs：`POST /api/skills/{skill_id}/runs` 创建 run，`POST /api/skills/{skill_id}/runs/predict` 创建 predict，`GET /api/skills/{skill_id}/runs/{run_id}` 获取详情，定义见 `apps/studio/backend/app/routers/runs.py:27` 到 `apps/studio/backend/app/routers/runs.py:55`。resume endpoint 当前未实现，见 `apps/studio/backend/app/routers/runs.py:64` 到 `apps/studio/backend/app/routers/runs.py:70`。

Run stream API 由前端 `runEventsWsUrl(runId)` 订阅，hook 代码在 `apps/studio/frontend/src/hooks/useRunStream.ts:49` 到 `apps/studio/frontend/src/hooks/useRunStream.ts:57`。事件类型在 `CallbackEvent` 里以扩展 JSON 形式承载，前端类型定义见 `apps/studio/frontend/src/api/types.ts:408` 到 `apps/studio/frontend/src/api/types.ts:428`。

Golden/compare API 和 Trace 面板按钮相关：保存 golden 在 `apps/studio/frontend/src/api/client.ts:127` 到 `apps/studio/frontend/src/api/client.ts:133`，后端 golden list/set/delete 在 `apps/studio/backend/app/routers/golden.py:15` 到 `apps/studio/backend/app/routers/golden.py:39`，compare endpoint 在 `apps/studio/backend/app/routers/compare.py:14` 到 `apps/studio/backend/app/routers/compare.py:29`。

## Data Model / State

Trace 前端核心 state 是 `traceLogs`、`activePhase`、`selectedEventId`、`linkEnabled` 和 filter state。`TracePanel` 的 props 明确定义这些输入和回调，见 `apps/studio/frontend/src/components/TracePanel.tsx:8` 到 `apps/studio/frontend/src/components/TracePanel.tsx:20`。

Run detail 类型包含 metadata、input_data、events、final_context、artifacts，见 `apps/studio/frontend/src/api/types.ts:185` 到 `apps/studio/frontend/src/api/types.ts:191`。`CallbackEvent` 是 `CallbackEventBase & Record<string, JsonValue | undefined>`，说明事件 payload 是开放结构，见 `apps/studio/frontend/src/api/types.ts:408` 到 `apps/studio/frontend/src/api/types.ts:428`。

Batch trace 状态独立于单次 trace 列表。`BatchRunStatus` 包含 batch id、skill id、items 和 status，见 `apps/studio/frontend/src/api/types.ts:132` 到 `apps/studio/frontend/src/api/types.ts:149`。批量执行会启动多个 run，每个 run 仍然有自己的 run detail 和 event stream。

## Cross-feature interaction

与 Canvas：Trace 目前不会反向填充 edge 的 `hasTraceData/contextJson`，所以边按钮无法展示 phase 间上下文。Canvas 现状见 [canvas-topology baseline](../canvas-topology/baseline.md)。

与 skill lifecycle：Trace 可以被 promote 成 golden baseline。后端 `set_golden_baseline` 会复制 run final_state 并写 metadata，见 `apps/studio/backend/app/services/golden_diff.py:34` 到 `apps/studio/backend/app/services/golden_diff.py:65`；skill 生命周期里的 golden diff 说明见 [skill-lifecycle baseline](../skill-lifecycle/baseline.md)。

与 system-level UX：Trace、CompileErrorPanel、Edge Inspection 的缺口已在 system-level 工作流文档里暴露，详见 [ux-workflow baseline](../../system-level/ux-workflow/baseline.md)。
