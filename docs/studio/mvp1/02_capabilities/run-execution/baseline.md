# run-execution Baseline

Status: Workspace已接startRun和runId，节点状态投影有单测覆盖；真实Tauri/App手动QA和完整timeline flow仍deferred。

Source workflow: `01_workflows/04_run-and-verify.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Run button | Center action bar displays and enables Run after predict-pass. Workspace handler invokes the `startRun` API client. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:52`, `apps/studio/frontend/src/components/studio/Workspace.tsx:542` |
| API helper | `startRun` posts input data to `/skills/{skill_id}/runs`. | `apps/studio/frontend/src/api/client.ts:155` |
| Run route | Backend starts a run via `run_manager.start_run`. | `apps/studio/backend/app/routers/runs.py:27` |
| Worker | Run manager spawns a process, calls `run_skill`, writes final state, metrics, and status. | `apps/studio/backend/app/services/run_manager.py:81`, `apps/studio/backend/app/services/run_manager.py:182` |
| Run artifacts | Run directory includes trace, artifacts, checkpoints, and metadata files. | `apps/studio/backend/app/services/run_manager.py:164` |
| Run stream | Backend exposes run websocket and drains run event queue. | `apps/studio/backend/app/routers/websockets.py:27`, `apps/studio/backend/app/services/run_manager.py:334` |
| History | Frontend has run history hooks; TimelinePanel lists runs. | `apps/studio/frontend/src/hooks/useRunHistory.ts:7`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:32` |
| Batch | Backend batch-run exists and frontend batch hook/component exist but are not mounted in Workspace panels. | `apps/studio/backend/app/routers/runs.py:48`, `apps/studio/frontend/src/hooks/useBatchRun.ts:73` |
| Autocommit | Successful run auto-commits and records git status. | `apps/studio/backend/app/services/run_manager.py:445` |

## Current Coverage

- live/backend: start run, worker, run files, websocket stream, run history, batch route, autocommit.
- live/frontend: Run button execution, WS-3 stage integration with predict-pass gate, and WebSocket event stream connection via `useRunStream` driving node status projection.

## Known Drift / Deferred Items

- 真实的 Tauri/App 本地开发启动运行调试与手动 QA 处于 **deferred** 状态。
- Timeline 流式完整呈现、历史运行抽屉的完整渲染与闭环仍属于本批次 **deferred**。
