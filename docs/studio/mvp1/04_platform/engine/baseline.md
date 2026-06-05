---
module: 04_platform/engine
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；Studio 已消费 compile/predict/run/trace 部分 engine 能力；resume 仍 501，engine contract 应引用 `docs/engine/mvp1/` SSOT，不在 Studio 重写 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/backend/app/services/skills.py:lint_skill_path · apps/studio/backend/app/services/predictor.py:dispatch_predict_job · apps/studio/backend/app/services/run_manager.py:start_run · apps/studio/backend/app/services/golden_diff.py:compare_run_to_golden · apps/studio/backend/app/routers/runs.py:resume_run
units: [compile-stage-gate, predict-execution, run-execution-node-status, trace-dot-blackboard, golden-per-agent-node, debug-resume-checkpoint, subgraph-path-inline-drilldown, phase-field-whitelist]
---

# engine — Baseline（当下代码实现逻辑）

> **Scope**: Studio 对 engine-owned contract 的消费面：compile/lint、predict、run/artifacts、trace schema、golden、debug resume、skill syntax/path。
> **现状一句话**: Studio 已消费 compile/predict/run/trace 部分 engine 能力；resume 仍 501，engine contract 应引用 `docs/engine/mvp1/` SSOT，不在 Studio 重写 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Compile facade | graph-agent exposes compile facade used by Studio backend. | `packages/graph-agent/src/graph_agent/core/compiler.py:compile_skill（L41）`, `apps/studio/backend/app/services/skills.py:lint_skill_path（L313）` |
| Predict | graph-agent exposes `predict_skill`; Studio predictor dispatches and persists predict results. | `packages/graph-agent/src/graph_agent/core/runner.py:predict_skill（L163）`, `apps/studio/backend/app/services/predictor.py:dispatch_predict_job（L41）` |
| Run | graph-agent exposes `run_skill`; run manager starts process and writes status/final/metrics. | `packages/graph-agent/src/graph_agent/core/runner.py:run_skill（L376）`, `apps/studio/backend/app/services/run_manager.py:_run_worker_main（L81）` |
| Trace | engine tracing writes typed callback events to `trace.jsonl`. | `packages/graph-agent/src/graph_agent/callbacks/tracing.py:set_trace_dir（L80）`, `packages/graph-agent/src/graph_agent/callbacks/tracing.py:_write_typed_event（L101）` |
| Result model | RunResult and PhaseRecord capture run/predict structured output. | `packages/graph-agent/src/graph_agent/core/result.py:PhaseRecord（L58）`, `packages/graph-agent/src/graph_agent/core/result.py:RunResult（L68）` |
| Error payload | Engine error payload includes code/message/detail/location/hint-like fields. | `packages/graph-agent/src/graph_agent/core/exceptions.py:ErrorPayload（L21）`, `packages/graph-agent/src/graph_agent/core/exceptions.py:make_error_payload（L49）` |
| Golden diff | Studio backend compares run final state to stored golden final state. | `apps/studio/backend/app/services/golden_diff.py:compare_run_to_golden（L68）` |
| Resume gap | Studio resume endpoint exists but returns 501. | `apps/studio/backend/app/routers/runs.py:delete_run（L64）` |

## 前端逻辑
N/A。

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Compile facade | graph-agent exposes compile facade used by Studio backend. | `packages/graph-agent/src/graph_agent/core/compiler.py:compile_skill（L41）`, `apps/studio/backend/app/services/skills.py:lint_skill_path（L313）` |
| Predict | graph-agent exposes `predict_skill`; Studio predictor dispatches and persists predict results. | `packages/graph-agent/src/graph_agent/core/runner.py:predict_skill（L163）`, `apps/studio/backend/app/services/predictor.py:dispatch_predict_job（L41）` |
| Run | graph-agent exposes `run_skill`; run manager starts process and writes status/final/metrics. | `packages/graph-agent/src/graph_agent/core/runner.py:run_skill（L376）`, `apps/studio/backend/app/services/run_manager.py:_run_worker_main（L81）` |
| Trace | engine tracing writes typed callback events to `trace.jsonl`. | `packages/graph-agent/src/graph_agent/callbacks/tracing.py:set_trace_dir（L80）`, `packages/graph-agent/src/graph_agent/callbacks/tracing.py:_write_typed_event（L101）` |
| Result model | RunResult and PhaseRecord capture run/predict structured output. | `packages/graph-agent/src/graph_agent/core/result.py:PhaseRecord（L58）`, `packages/graph-agent/src/graph_agent/core/result.py:RunResult（L68）` |
| Error payload | Engine error payload includes code/message/detail/location/hint-like fields. | `packages/graph-agent/src/graph_agent/core/exceptions.py:ErrorPayload（L21）`, `packages/graph-agent/src/graph_agent/core/exceptions.py:make_error_payload（L49）` |
| Golden diff | Studio backend compares run final state to stored golden final state. | `apps/studio/backend/app/services/golden_diff.py:compare_run_to_golden（L68）` |
| Resume gap | Studio resume endpoint exists but returns 501. | `apps/studio/backend/app/routers/runs.py:delete_run（L64）` |

## 当前边界（engine 现在不是什么）
- 不拥有 engine 内部机制；engine-owned contract 只引用 `docs/engine/mvp1/`。
- `binds_code` 只绑定 Studio ③a 适配/消费符号，不绑定 engine 包作为 Studio owned code。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| resume | Studio `resume_run` 仍 501 ⚠️ | 节点级 resume 引用 engine checkpoint/resume contract 并接 Studio 适配 |
| engine SSOT | 旧文/旧 prompt 容易被当 engine 需求 ⚠️ | 只引用 `docs/engine/mvp1/` 具体 contract/mechanism |
| golden/path/schema | Studio 文档多处消费 engine-owned 契约 | 只写消费边界，落点/skill syntax/resolver 不复制 |
> **验"是否按目标改了"**：1. resume；2. engine SSOT；3. golden/path/schema。

## 读代码主路径提示
`apps/studio/backend/app/services/skills.py:lint_skill_path` → `apps/studio/backend/app/services/predictor.py:dispatch_predict_job` → `apps/studio/backend/app/services/run_manager.py:start_run` → `apps/studio/backend/app/services/golden_diff.py:compare_run_to_golden` → `apps/studio/backend/app/routers/runs.py:resume_run`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#04-platform-engine)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `compile-lint` · `predict` · `run-execution` · `trace-observability` · `golden-eval` · `debug-resume` · `graph-authoring` · `phase-editing` · `docs/engine/mvp1/`
