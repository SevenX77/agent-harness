# predict Baseline

Status: Workspace已接postPredictRun，结构化错误有单测覆盖；i/o panel输入选择和真实手动QA/e2e仍deferred。

Source workflow: `01_workflows/04_run-and-verify.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Predict button | Center action bar enables Predict after compile-pass. Workspace handler invokes the `postPredictRun` API client. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:42`, `apps/studio/frontend/src/components/studio/Workspace.tsx:520` |
| API helper | `postPredictRun` posts input data to `/skills/{skill_id}/runs/predict`. | `apps/studio/frontend/src/api/client.ts:135` |
| Backend route | Predict route dispatches predictor service, catching compilation/validation ValueErrors and returning structured 400 DTOs. | `apps/studio/backend/app/routers/runs.py:32` |
| Predictor service | Predictor dispatches a predict job and persists `result.json`. | `apps/studio/backend/app/services/predictor.py:41`, `apps/studio/backend/app/services/predictor.py:111` |
| Engine predict | graph-agent exposes `predict_skill` and writes predict artifacts/trace. | `packages/graph-agent/src/graph_agent/core/runner.py:163`, `packages/graph-agent/src/graph_agent/core/runner.py:353` |
| Input validation | Backend has a validate-input endpoint. | `apps/studio/backend/app/routers/skills.py:454` |
| Golden guard | Diagnostic export rejects predict traces from promotion to golden. | `apps/studio/backend/app/services/diagnostic_export.py:25` |
| Stage update | Workspace sets `predicting`, `predict-pass`, and `predict-fail` stage states based on predict execution outcome; drives button enable/disable. | `apps/studio/frontend/src/components/studio/Workspace.tsx:520` |

## Current Coverage

- live/backend: predict endpoint, predictor service with custom 400 error translation for ValueError, engine predict path, diagnostic persistence, golden guard.
- live/frontend: Workspace integrated predict handler, dynamic stages based on react states, toast error feedback with structured compile messages.

## Known Drift / Deferred Items

- **i/o panel** 输入选择和对应的数据契约并未在本批次中与 Predict 触发进行端到端闭环，依然为 **deferred**。
- 真实的本地运行与 Tauri/App 层的真实手动 QA/e2e 验证不包含在此批次中，属于 **deferred**。
