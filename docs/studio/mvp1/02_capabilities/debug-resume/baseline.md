# debug-resume Baseline

Status: mostly missing. Backend has placeholders and engine events/checkpoint primitives; Studio UI has no node-level resume flow.

Source workflow: `01_workflows/05_debugging.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Resume route | Backend exposes `/runs/{run_id}/resume` but returns 501. | `apps/studio/backend/app/routers/runs.py:64`, `apps/studio/backend/app/routers/runs.py:69` |
| Run checkpoints | Run manager creates a run directory with `checkpoints.db`, but Studio resume is not implemented on top. | `apps/studio/backend/app/services/run_manager.py:164`, `apps/studio/backend/app/services/run_manager.py:167` |
| Run worker | Run worker calls graph-agent with checkpoint cleanup disabled on finish. | `apps/studio/backend/app/services/run_manager.py:81`, `apps/studio/backend/app/services/run_manager.py:103` |
| Engine HitL event | graph-agent defines ambiguity/clarification events and resume-related callback shapes. | `packages/graph-agent/src/graph_agent/callbacks/events.py:157`, `packages/graph-agent/src/graph_agent/callbacks/events.py:394` |
| Clarification tool | graph-agent has an `ask_clarification` tool path. | `packages/graph-agent/src/graph_agent/tools/builtin/clarification_tool.py:8` |
| Node UI | SkillNode renders status badges and subgraph/overwrite controls, but no Resume button. | `apps/studio/frontend/src/components/nodes/SkillNode.tsx:106`, `apps/studio/frontend/src/components/nodes/SkillNode.tsx:116` |
| Context editor base | Monaco supports read-only toggle; writable context tamper flow is not wired. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:217` |
| Trace dependency | TracePanel and event-to-node derivation are not mounted, so debug has no reliable failed-node source. | `apps/studio/frontend/src/components/TracePanel.tsx:22`, `apps/studio/frontend/src/components/studio/Workspace.tsx:515` |

## Current Coverage

- backend-only/placeholder: resume route, checkpoint file, engine clarification events.
- missing frontend: failed-node red light, node Resume, HitL question frame, context tamper editor, dirty checkpoint invalidation.
- engine gap: node-level checkpoint validity and resume-from-node semantics.

## Known Drift

- Workflow requires node-level resume from the failed node without rerunning upstream; current route is 501 (`apps/studio/backend/app/routers/runs.py:69`).
- Workflow requires dirty-state invalidation; current Studio has no checkpoint validity model (`apps/studio/backend/app/services/run_manager.py:167`).
