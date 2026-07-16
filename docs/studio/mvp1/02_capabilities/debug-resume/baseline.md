---
module: 02_capabilities/debug-resume
doc: baseline
status: FROZEN（2026-07 对账:Studio resume/validity 已实现非 501(runs.py:268-313 resume / :224-256 validity → adapter.resume/resume_validity);节点级 Resume 已接线(ResumeNodeToolbar,GraphCanvas.tsx:2525)、context tamper 已接(EdgeTamperEditor,EdgeContextView.tsx:256)、TracePanel 已挂(Panels.tsx:237)。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/backend/app/routers/runs.py:resume_run · apps/studio/backend/app/services/run_manager.py:start_run · apps/studio/frontend/src/components/nodes/SkillNode.tsx:SkillNode · apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel
units: [debug-resume-checkpoint]
---

# debug-resume — Baseline（当下代码实现逻辑）

> **Scope**: 失败节点 resume、checkpoint 失效、HitL 问答注入与 dot/context tamper 的调试闭环。
> **现状一句话**: Studio resume/validity 已实现非 501,节点级 Resume(ResumeNodeToolbar)/context tamper(EdgeTamperEditor)/TracePanel 均已接线;核心 checkpoint/resume 协议仍落引擎。

## UI/UX
失败节点 resume、checkpoint 失效、HitL 问答注入与 dot/context tamper 的调试闭环。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Engine HitL event | graph-agent defines ambiguity/clarification events and resume-related callback shapes. | `packages/graph-agent/src/graph_agent/callbacks/events.py:AmbiguityReportEvent（L157）`, `packages/graph-agent/src/graph_agent/callbacks/events.py:ResumedEvent（L394）` |
| Clarification tool | graph-agent has an `ask_clarification` tool path. | `packages/graph-agent/src/graph_agent/tools/builtin/clarification_tool.py:clarification_tool（L8）` |
| Node UI | 失败节点上有 node-anchored [Resume] 控件(ResumeNodeToolbar,仅 error 态显示)+ HitL 工具条,不再是"无 Resume"。 | `apps/studio/frontend/src/components/studio/ResumeNodeToolbar.tsx:ResumeNodeToolbar`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:ResumeNodeToolbar（L2525）`, `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:HitlNodeToolbar（L2517）` |
| Context editor base | 可写 context tamper 流已接线:EdgeTamperEditor 挂 EdgeContextView(选中边),经 resume `context_overrides` 回注引擎。 | `apps/studio/frontend/src/components/studio/panels/EdgeContextView.tsx:EdgeTamperEditor（L256）`, `apps/studio/backend/app/routers/runs.py:resume_run（L278）` |
| Trace dependency | TracePanel 已挂主路径(active run→TracePanel),event→node 派生 live,debug 有可靠 failed-node 源。 | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:TracePanel（L237）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:deriveNodeStatuses（L665）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Resume route | Backend `/runs/{run_id}/resume` 已实现(非 501):调 `adapter.resume`,携带 checkpoint/`context_overrides`/`human_input`/`human_response`;另有 `/resume/validity`。 | `apps/studio/backend/app/routers/runs.py:resume_run（L268）`, `apps/studio/backend/app/routers/runs.py:get_resume_validity（L224）` |
| Run checkpoints | Run manager 建 run 目录含 `checkpoints.db`,Studio resume 已在其上落地(resume_run→adapter.resume→record_resume_result)。 | `apps/studio/backend/app/services/run_manager.py:_ensure_run_files（L164）`, `apps/studio/backend/app/routers/runs.py:resume_run（L308）` |
| Run worker | Run worker calls graph-agent with checkpoint cleanup disabled on finish. | `apps/studio/backend/app/services/run_manager.py:_run_worker_main（L81）`, `apps/studio/backend/app/services/run_manager.py:_run_worker_main（L103）` |
| Engine HitL event | graph-agent defines ambiguity/clarification events and resume-related callback shapes. | `packages/graph-agent/src/graph_agent/callbacks/events.py:AmbiguityReportEvent（L157）`, `packages/graph-agent/src/graph_agent/callbacks/events.py:ResumedEvent（L394）` |
| Clarification tool | graph-agent has an `ask_clarification` tool path. | `packages/graph-agent/src/graph_agent/tools/builtin/clarification_tool.py:clarification_tool（L8）` |

## 当前边界（debug-resume 现在不是什么）
- checkpoint/resume 的底层协议归 engine；Studio 只写 UI 与 ③a 适配。
- 不把 debug tamper 写成常规文件编辑；它消费 trace/context。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| resume API | `resume_run` 已实现非 501,携带 checkpoint/answer/tamper 输入(runs.py:268-313)✅ | 失败节点可 resume，并携带 checkpoint / answer / tamper 输入 |
| 节点入口 | 失败节点显示 node-anchored [Resume](ResumeNodeToolbar,仅 error 态,GraphCanvas.tsx:2525)✅ | 失败节点显示 Resume，非失败态不显示或 disabled |
| trace 来源 | TracePanel/useRunStream 已挂主路径,resume 基于真实 failed-node trace(Panels.tsx:237)✅ | resume 选择基于真实 failed-node trace/state |
> **验"是否按目标改了"**：1. resume API；2. 节点入口；3. trace 来源。

## 读代码主路径提示
`apps/studio/backend/app/routers/runs.py:resume_run` → `apps/studio/backend/app/services/run_manager.py:start_run` → `apps/studio/frontend/src/components/nodes/SkillNode.tsx:SkillNode` → `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-debug-resume)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `trace-observability` · `timeline` · `properties` · `engine` checkpoint/resume SSOT
