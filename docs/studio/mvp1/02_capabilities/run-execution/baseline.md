# run-execution Baseline

Status: backend live, frontend Run entry and live state wiring are stubs/orphans.

Source workflow: `01_workflows/04_run-and-verify.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Run button | Center action bar can display Run after predict-pass, but no code sets predict-pass and handler only logs. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:52`, `apps/studio/frontend/src/components/studio/Workspace.tsx:538` |
| API helper | `startRun` posts input data to `/runs`. | `apps/studio/frontend/src/api/client.ts:154` |
| Run route | Backend starts a run via `run_manager.start_run`. | `apps/studio/backend/app/routers/runs.py:27` |
| Worker | Run manager spawns a process, calls `run_skill`, writes final state, metrics, and status. | `apps/studio/backend/app/services/run_manager.py:81`, `apps/studio/backend/app/services/run_manager.py:182` |
| Run artifacts | Run directory includes trace, artifacts, checkpoints, and metadata files. | `apps/studio/backend/app/services/run_manager.py:164` |
| Run stream | Backend exposes run websocket and drains run event queue. | `apps/studio/backend/app/routers/websockets.py:27`, `apps/studio/backend/app/services/run_manager.py:334` |
| History | Frontend has run history hooks; TimelinePanel lists runs. | `apps/studio/frontend/src/hooks/useRunHistory.ts:7`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:32` |
| Batch | Backend batch-run exists and frontend batch hook/component exist but are not mounted in Workspace panels. | `apps/studio/backend/app/routers/runs.py:48`, `apps/studio/frontend/src/hooks/useBatchRun.ts:73` |
| Autocommit | Successful run auto-commits and records git status. | `apps/studio/backend/app/services/run_manager.py:445` |

## Current Coverage

- live/backend: start run, worker, run files, websocket stream, run history, batch route, autocommit.
- orphan/frontend: batch runner, run detail drawer, run stream hook, node status animation.
- missing: Run button hookup, `statusByNodeId` mapping, focus follow, i/o panel entry.

## Known Drift

- Workflow requires node lights driven by real run events; Workspace does not pass `statusByNodeId` to GraphCanvas (`apps/studio/frontend/src/components/studio/Workspace.tsx:515`).
- Run should start from i/o panel input selection; current button has no input contract (`apps/studio/frontend/src/components/studio/Workspace.tsx:538`).
