# predict Baseline

Status: backend mostly live, frontend entry is a stub.

Source workflow: `01_workflows/04_run-and-verify.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Predict button | Center action bar can enable Predict after compile-pass, but Workspace handler only logs. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:42`, `apps/studio/frontend/src/components/studio/Workspace.tsx:537` |
| API helper | `postPredictRun` exists and posts input data to `/runs/predict`. | `apps/studio/frontend/src/api/client.ts:134` |
| Backend route | Predict route dispatches predictor service with mock flag, input data, and current hashes. | `apps/studio/backend/app/routers/runs.py:32` |
| Predictor service | Predictor dispatches a predict job and persists `result.json`. | `apps/studio/backend/app/services/predictor.py:41`, `apps/studio/backend/app/services/predictor.py:111` |
| Engine predict | graph-agent exposes `predict_skill` and writes predict artifacts/trace. | `packages/graph-agent/src/graph_agent/core/runner.py:163`, `packages/graph-agent/src/graph_agent/core/runner.py:353` |
| Input validation | Backend has a validate-input endpoint but it is not wired into a full i/o panel predict flow. | `apps/studio/backend/app/routers/skills.py:454` |
| Golden guard | Diagnostic export rejects predict traces from promotion to golden. | `apps/studio/backend/app/services/diagnostic_export.py:25` |
| Stage update | No frontend code sets `predict-pass`; Run remains gated. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:52`, `apps/studio/frontend/src/components/studio/Workspace.tsx:537` |

## Current Coverage

- live/backend: predict endpoint, predictor service, engine predict path, diagnostic persistence, golden guard.
- placeholder/frontend: button handler, input-file selection, stage update, trace display.
- stale: old dynamic JSON predict dialog concept is replaced by i/o panel file selection.

## Known Drift

- Workflow says Predict is the hard precondition for Run; current UI cannot complete predict-pass (`apps/studio/frontend/src/components/studio/Workspace.tsx:537`).
- Predict should run according to node i/o configuration; current helper only accepts ad hoc `input_data` (`apps/studio/frontend/src/api/client.ts:134`).
