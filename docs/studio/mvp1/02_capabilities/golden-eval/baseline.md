# golden-eval Baseline

Status: Studio-only WS-6 closeout is partially live: backend accepts manual per-node golden expected output, rejects whole-run and predict-source golden promotion, and the frontend compare helper uses the run `/diff` route. Engine-pinned per-node golden physical layout and mounted authoring UX remain deferred/floating draft.

Source workflow: `01_workflows/04_run-and-verify.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Frontend save helper | `saveGoldenBaseline` still posts a legacy `run_id`; when invoked, backend rejects it as whole-run promotion. There is not yet a mounted per-node golden authoring UI. | `apps/studio/frontend/src/api/client.ts:143`, `apps/studio/backend/app/routers/golden.py:32` |
| Frontend diff helper | `compareRunToGolden` calls GET `/skills/{skill_id}/runs/{run_id}/diff` with optional `against`. | `apps/studio/frontend/src/api/client.ts:156`, `apps/studio/frontend/src/hooks/useGoldenDiff.ts:27` |
| Golden routes | Backend lists golden baselines and accepts manual node golden saves under `/api/skills/{skill_id}/golden`; old `run_id` promotion is rejected with `WHOLE_RUN_GOLDEN_PROMOTION_NOT_ALLOWED`, and `source="predict"` is rejected. | `apps/studio/backend/app/routers/golden.py:15`, `apps/studio/backend/app/routers/golden.py:32`, `apps/studio/backend/app/routers/golden.py:38` |
| Current persistence | `set_golden_baseline_for_manual_node` writes a Studio-side floating draft under `.workspace/golden/manual-{node_id}/final_state.json` and records `node_id` / `source` metadata. | `apps/studio/backend/app/services/golden_diff.py:68`, `apps/studio/backend/app/services/golden_diff.py:80`, `apps/studio/backend/app/models/golden.py:11` |
| Legacy persistence | `set_golden_baseline_for_run` still exists as an internal compatibility function, but the HTTP route no longer exposes whole-run promote as a success path. | `apps/studio/backend/app/services/golden_diff.py:34`, `apps/studio/backend/app/routers/golden.py:33` |
| Current diff | `compare_run_to_golden` compares a run `final_state.json` against the selected/latest golden draft and returns field-level scores. | `apps/studio/backend/app/services/golden_diff.py:105`, `apps/studio/backend/app/services/golden_diff.py:135` |
| Compare API | Backend exposes POST `/compare` and GET `/diff`. | `apps/studio/backend/app/routers/compare.py:14`, `apps/studio/backend/app/routers/compare.py:23` |
| Frontend hook alignment | `useGoldenDiff.compare` now delegates to the `/diff` helper instead of inlining the old `/compare` path. | `apps/studio/frontend/src/hooks/useGoldenDiff.ts:19`, `apps/studio/frontend/src/hooks/useGoldenDiff.ts:27` |
| Predict guard | Diagnostic export blocks predict trace promotion to golden. | `apps/studio/backend/app/services/diagnostic_export.py:25` |
| Diff UI tokens | Diff components use local `Button` wrapper and semantic tokens; WS-6 tests cover empty/data/fallback preview states against one-off slate/sky/amber/red/zinc palette classes. | `apps/studio/frontend/src/components/diff/DiffView.tsx:6`, `apps/studio/frontend/src/components/diff/DiffField.tsx:118`, `apps/studio/frontend/src/components/diff/DiffView.ws6.red.test.tsx:10` |
| Trace buttons | TracePanel has Compare and Golden buttons, but the panel is not mounted. | `apps/studio/frontend/src/components/TracePanel.tsx:50` |

## Current Coverage

- live/backend: list golden, manual per-node golden draft save, whole-run promote rejection, predict-source rejection, run-vs-golden diff.
- live/frontend: compare helper and `useGoldenDiff.compare` use `/diff`; DiffView token cleanup is covered by focused tests.
- orphan/frontend: TracePanel compare/golden buttons and `useGoldenDiff.promote` still model old run promotion and are not the mounted per-node authoring UX.
- target gap/deferred: engine-pinned per-node golden binding, i/o panel golden JSON editing, copilot-assisted design, output-schema invalidation, real run-artifact e2e.

## Known Drift

- Engine per-node golden physical layout is not pinned. Studio currently writes a floating draft keyed by `manual-{node_id}` and stores an object shaped as `{node_id: expected_output}`.
- `saveGoldenBaseline` / `useGoldenDiff.promote` still send a `run_id`; this is now a rejected path, not a valid MVP1 promote flow.
- `compare_run_to_golden` still reads run `final_state.json`; true engine node-artifact binding remains deferred until run artifacts and engine layout are stable.
- `docs/studio/mvp1/DESIGN_UNITS_INDEX.md` is referenced by WS-6 requirements but is absent in this worktree.
