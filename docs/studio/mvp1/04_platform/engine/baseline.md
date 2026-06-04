# engine Baseline

Status: graph-agent engine is the strongest live backend area: compile, predict, run, trace, error payloads, and partial golden diff exist; debug resume remains a gap.

Source workflows: `01_workflows/03_compile.md`, `01_workflows/04_run-and-verify.md`, `01_workflows/05_debugging.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Compile facade | graph-agent exposes compile facade used by Studio backend. | `packages/graph-agent/src/graph_agent/core/compiler.py:41`, `apps/studio/backend/app/services/skills.py:313` |
| Predict | graph-agent exposes `predict_skill`; Studio predictor dispatches and persists predict results. | `packages/graph-agent/src/graph_agent/core/runner.py:163`, `apps/studio/backend/app/services/predictor.py:41` |
| Run | graph-agent exposes `run_skill`; run manager starts process and writes status/final/metrics. | `packages/graph-agent/src/graph_agent/core/runner.py:376`, `apps/studio/backend/app/services/run_manager.py:81` |
| Trace | engine tracing writes typed callback events to `trace.jsonl`. | `packages/graph-agent/src/graph_agent/callbacks/tracing.py:80`, `packages/graph-agent/src/graph_agent/callbacks/tracing.py:101` |
| Result model | RunResult and PhaseRecord capture run/predict structured output. | `packages/graph-agent/src/graph_agent/core/result.py:58`, `packages/graph-agent/src/graph_agent/core/result.py:68` |
| Error payload | Engine error payload includes code/message/detail/location/hint-like fields. | `packages/graph-agent/src/graph_agent/core/exceptions.py:21`, `packages/graph-agent/src/graph_agent/core/exceptions.py:49` |
| Golden diff | Studio backend compares run final state to stored golden final state. | `apps/studio/backend/app/services/golden_diff.py:68` |
| Resume gap | Studio resume endpoint exists but returns 501. | `apps/studio/backend/app/routers/runs.py:64` |

## Current Coverage

- live: compile, predict, run, trace file, run artifacts, error payloads, whole-run diff.
- target gaps: per-node golden model, trace transition payload schema, node-level checkpoint resume, dirty invalidation, HitL injection.

## Known Drift

- MVP1 wants per-node golden and predict mock-by-golden; current golden diff is whole-run final_state based (`apps/studio/backend/app/services/golden_diff.py:34`).
- Debug resume requires node-level checkpoint validity; current Studio endpoint is 501 (`apps/studio/backend/app/routers/runs.py:69`).
