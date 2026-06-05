---
module: 02_capabilities/debug-resume
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；Studio resume route 存在但直接 501，节点级 Resume 主路径不可用 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/backend/app/routers/runs.py:resume_run · apps/studio/backend/app/services/run_manager.py:start_run · apps/studio/frontend/src/components/nodes/SkillNode.tsx:SkillNode · apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel
units: [debug-resume-checkpoint]
---

# debug-resume — Baseline（当下代码实现逻辑）

> **Scope**: 失败节点 resume、checkpoint 失效、HitL 问答注入与 dot/context tamper 的调试闭环。
> **现状一句话**: Studio resume route 存在但直接 501，节点级 Resume 主路径不可用 ⚠️。

## UI/UX
失败节点 resume、checkpoint 失效、HitL 问答注入与 dot/context tamper 的调试闭环。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Engine HitL event | graph-agent defines ambiguity/clarification events and resume-related callback shapes. | `packages/graph-agent/src/graph_agent/callbacks/events.py:AmbiguityReportEvent（L157）`, `packages/graph-agent/src/graph_agent/callbacks/events.py:ResumedEvent（L394）` |
| Clarification tool | graph-agent has an `ask_clarification` tool path. | `packages/graph-agent/src/graph_agent/tools/builtin/clarification_tool.py:clarification_tool（L8）` |
| Node UI | SkillNode renders status badges and subgraph/overwrite controls, but no Resume button. | `apps/studio/frontend/src/components/nodes/SkillNode.tsx:nodeContent（L106）`, `apps/studio/frontend/src/components/nodes/SkillNode.tsx:nodeContent（L116）` |
| Context editor base | Monaco supports read-only toggle; writable context tamper flow is not wired. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:handleChange（L217）` |
| Trace dependency | TracePanel and event-to-node derivation are not mounted, so debug has no reliable failed-node source. | `apps/studio/frontend/src/components/TracePanel.tsx:TracePanel（L22）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L515）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Resume route | Backend exposes `/runs/{run_id}/resume` but returns 501. | `apps/studio/backend/app/routers/runs.py:delete_run（L64）`, `apps/studio/backend/app/routers/runs.py:resume_run（L69）` |
| Run checkpoints | Run manager creates a run directory with `checkpoints.db`, but Studio resume is not implemented on top. | `apps/studio/backend/app/services/run_manager.py:_ensure_run_files（L164）`, `apps/studio/backend/app/services/run_manager.py:_ensure_run_files（L167）` |
| Run worker | Run worker calls graph-agent with checkpoint cleanup disabled on finish. | `apps/studio/backend/app/services/run_manager.py:_run_worker_main（L81）`, `apps/studio/backend/app/services/run_manager.py:_run_worker_main（L103）` |
| Engine HitL event | graph-agent defines ambiguity/clarification events and resume-related callback shapes. | `packages/graph-agent/src/graph_agent/callbacks/events.py:AmbiguityReportEvent（L157）`, `packages/graph-agent/src/graph_agent/callbacks/events.py:ResumedEvent（L394）` |
| Clarification tool | graph-agent has an `ask_clarification` tool path. | `packages/graph-agent/src/graph_agent/tools/builtin/clarification_tool.py:clarification_tool（L8）` |

## 当前边界（debug-resume 现在不是什么）
- checkpoint/resume 的底层协议归 engine；Studio 只写 UI 与 ③a 适配。
- 不把 debug tamper 写成常规文件编辑；它消费 trace/context。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| resume API | `resume_run` 返回 501 ⚠️ | 失败节点可 resume，并携带 checkpoint / answer / tamper 输入 |
| 节点入口 | SkillNode 无 Resume button ⚠️ | 失败节点显示 Resume，非失败态不显示或 disabled |
| trace 来源 | TracePanel/useRunStream 未挂主路径 ⚠️ | resume 选择基于真实 failed-node trace/state |
> **验"是否按目标改了"**：1. resume API；2. 节点入口；3. trace 来源。

## 读代码主路径提示
`apps/studio/backend/app/routers/runs.py:resume_run` → `apps/studio/backend/app/services/run_manager.py:start_run` → `apps/studio/frontend/src/components/nodes/SkillNode.tsx:SkillNode` → `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-debug-resume)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `trace-observability` · `timeline` · `properties` · `engine` checkpoint/resume SSOT
