# engine MVP1 Alignment

## 定义

`engine` is the graph-agent Python sidecar platform block: compile/lint, predict, run, trace event production, run artifacts, golden/diff support, and future debug resume semantics.

Source workflow basis: `01_workflows/03_compile.md:22`, `01_workflows/04_run-and-verify.md:144`, `01_workflows/05_debugging.md:38`.

## 接口契约

- Compile returns structured errors for Studio contextual display.
- Predict runs logic and mocks agent nodes according to golden state.
- Run performs true execution and emits events/artifacts.
- Trace events must support node, edge/dot, loop/retry/batch grouping.
- Debug resume needs checkpoint and validity APIs.
- Capability links: `compile-lint`, `predict`, `run-execution`, `trace-observability`, `golden-eval`, `debug-resume`.

## F1. Compile/Lint Authority

- 机制: engine validates structure, fields, topology, IO data flow, mentions, and returns structured errors.
- 决策: Studio triggers and presents; it should not invent a parallel compiler.
- 原话/来源: `01_workflows/03_compile.md:22` lists engine compile checks; `01_workflows/03_compile.md:30` keeps error codes engine-owned.
- 测试: invalid graph returns file/line/field/severity enough for canvas/properties/editor markers.
- Status: live with metadata expansion likely needed.
- 归属: platform `engine`; capability `compile-lint`.

## F2. Predict Semantics

- 机制: predict validates schema, executes logic nodes, and mocks agent nodes without real token burn.
- 决策: predict is the hard precondition for run; golden only changes mock source.
- 原话/来源: `01_workflows/04_run-and-verify.md:23`, `01_workflows/04_run-and-verify.md:24`, and `01_workflows/04_run-and-verify.md:29` define semantics.
- 测试: logic runs real code; agent uses placeholder/golden; no provider route is called for mock.
- Status: partial live.
- 归属: platform `engine`; capability `predict`, `golden-eval`.

## F3. Run And Artifacts

- 机制: run executes real graph, writes final_state/metrics/trace/checkpoints/artifacts.
- 决策: run burns real tokens and is downstream of predict.
- 原话/来源: `01_workflows/04_run-and-verify.md:48` lists run artifacts; `01_workflows/04_run-and-verify.md:71` defines run tests.
- 测试: run artifacts exist; failed run records error payload; successful run can trigger autocommit.
- Status: live.
- 归属: platform `engine`; capability `run-execution`, `publish`.

## F4. Trace Event Schema

- 机制: emit enough structured runtime events for live stream, human-readable trace, dot transitions, prompt inspector, and node states.
- 决策: trace needs both node internals and between-node blackboard operations.
- 原话/来源: `01_workflows/04_run-and-verify.md:75` to `01_workflows/04_run-and-verify.md:81` define trace requirements; `01_workflows/04_run-and-verify.md:101` lists engine payload need.
- 测试: events include phase id/execution id, edge transition id, iteration/attempt/source where needed.
- Status: partial live; schema expansion needed.
- 归属: platform `engine`; capability `trace-observability`.

## F5. Per-node Golden And Diff

- 机制: maintain per-agent-node expected outputs and compare real output fields after run.
- 决策: replace whole-run captured snapshots.
- 原话/来源: `01_workflows/04_run-and-verify.md:131` and `01_workflows/04_run-and-verify.md:132` define the replacement.
- 测试: per-node golden storage; output schema invalidation; field diff by node.
- Status: target-design.
- 归属: platform `engine`; capability `golden-eval`.

## F6. Node-level Debug Resume

- 机制: resume from node/dot using valid upstream checkpoints, injected HitL answer, or tampered context.
- 决策: core difficulty belongs in engine.
- 原话/来源: `01_workflows/05_debugging.md:26` and `01_workflows/05_debugging.md:38` assign checkpoint/resume to engine.
- 测试: node X resume does not rerun upstream; dirty upstream invalidates downstream resume; HitL answer resumes.
- Status: target-design.
- 归属: platform `engine`; capability `debug-resume`.

## 待 PM 补 gap

- None for core direction; remaining gaps are mostly engine design details already listed above.
