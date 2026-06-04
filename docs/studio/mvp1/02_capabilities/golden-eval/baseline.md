# golden-eval Baseline

Status: backend has whole-run golden snapshots and diffing; MVP1 target is per-agent-node expected output, mostly target-design.

Source workflow: `01_workflows/04_run-and-verify.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Frontend save helper | `saveGoldenBaseline` posts a run id to `/golden`; this models golden as a run-derived baseline. | `apps/studio/frontend/src/api/client.ts:141` |
| Golden routes | Backend lists and sets golden baselines under `/api/skills/{skill_id}/golden`. | `apps/studio/backend/app/routers/golden.py:15`, `apps/studio/backend/app/routers/golden.py:24` |
| Current persistence | `set_golden_baseline_for_run` copies a run's final_state into a golden baseline folder. | `apps/studio/backend/app/services/golden_diff.py:34` |
| Current diff | `compare_run_to_golden` compares a run final_state to the latest or selected golden final_state. | `apps/studio/backend/app/services/golden_diff.py:68`, `apps/studio/backend/app/services/golden_diff.py:130` |
| Compare API | Backend exposes POST `/compare` and GET `/diff`. | `apps/studio/backend/app/routers/compare.py:14`, `apps/studio/backend/app/routers/compare.py:23` |
| Frontend hook mismatch | `useGoldenDiff` calls GET `/compare`, which does not match the backend route shape. | `apps/studio/frontend/src/hooks/useGoldenDiff.ts:19`, `apps/studio/frontend/src/hooks/useGoldenDiff.ts:27` |
| Predict guard | Diagnostic export blocks predict trace promotion to golden. | `apps/studio/backend/app/services/diagnostic_export.py:25` |
| Trace buttons | TracePanel has Compare and Golden buttons, but the panel is not mounted. | `apps/studio/frontend/src/components/TracePanel.tsx:50` |

## Current Coverage

- live/backend: list/set whole-run golden, run-vs-golden diff, predict trace guard.
- orphan/frontend: useGoldenDiff, TracePanel compare/golden buttons.
- target gap: per-node golden state, i/o panel golden JSON editing, copilot-assisted design, output-schema invalidation.

## Known Drift

- Target golden is per-agent-node author expectation; current implementation copies whole-run final_state (`apps/studio/backend/app/services/golden_diff.py:34`).
- Frontend diff hook route is wrong for current backend (`apps/studio/frontend/src/hooks/useGoldenDiff.ts:27`).
