# predict MVP1 Alignment

## 定义

`predict` owns the compile-after, run-before "flight test": run the graph according to node i/o configuration, validate schema and logic, execute deterministic logic nodes, and mock agent nodes without burning real tokens.

Source workflow basis: `01_workflows/04_run-and-verify.md:8`, `01_workflows/04_run-and-verify.md:16`, `01_workflows/04_run-and-verify.md:28`.

## 接口契约

- Entry: center Predict becomes available after compile-pass.
- Input: i/o panel selects an imported test input file or configured input set.
- Backend: predict endpoint runs engine predict and returns run-like diagnostic output.
- Golden: agent mock selection is automatic based on golden state.
- Region links: `center-action-bar`, `input`, `canvas`, `timeline`.
- Platform link: `engine`, `gateway` only through mock/model resolution boundaries.

## F1. Trigger Predict From I/O Configuration

- 机制: user chooses already-imported input in the i/o panel, then clicks Predict.
- 决策: input/validate/batch are configuration, not separate predict subproducts.
- 原话/来源: `01_workflows/04_run-and-verify.md:21` assigns input selection to i/o config; `01_workflows/04_run-and-verify.md:31` replaces the old dynamic dialog with the path-style i/o panel flow.
- 测试: Predict uses the selected file/config; no freeform JSON modal appears.
- Status: target-design.
- 归属: capability `predict`; region `input`; platform `engine`.

## F2. Validate Schema And Logic Chain

- 机制: predict validates input schema, runs logic nodes deterministically, and verifies output schema compatibility.
- 决策: Predict exists to prove logic and schema before Run.
- 原话/来源: `01_workflows/04_run-and-verify.md:22` and `01_workflows/04_run-and-verify.md:23` list validation and logic execution; `01_workflows/04_run-and-verify.md:34` records the PM explanation.
- 测试: invalid input blocks predict; logic node executes real code; schema mismatch produces compile/predict error.
- Status: backend live, frontend not connected.
- 归属: capability `predict`; platform `engine`; downstream `compile-lint`.

## F3. Agent Mock By Golden State

- 机制: agent nodes do not call real models during predict; they emit placeholder mock or golden output depending on node golden state.
- 决策: golden is not a prerequisite; it only changes mock source.
- 原话/来源: `01_workflows/04_run-and-verify.md:24` lists agent mock behavior; `01_workflows/04_run-and-verify.md:29` locks golden as non-prerequisite.
- 测试: no provider token is used; no-golden node emits placeholder; golden node emits golden case.
- Status: backend/design partial.
- 归属: capability `predict`; capability `golden-eval`; platform `engine`.

## F4. Predict-pass Stage

- 机制: successful predict sets `predict-pass`, enabling Run; failed predict keeps Run disabled.
- 决策: Predict is the hard precondition for Run.
- 原话/来源: `01_workflows/04_run-and-verify.md:10` and `01_workflows/04_run-and-verify.md:11` define the hard gate.
- 测试: passing predict unlocks Run; failing predict leaves Run disabled and shows the error at context.
- Status: missing.
- 归属: capability `predict`; capability `run-execution`; region `center-action-bar`.

## F5. Predict Trace Cannot Become Golden

- 机制: any promotion attempt from a predict trace is rejected.
- 决策: golden is author/copilot-defined expected output, not a captured predict/run snapshot.
- 原话/来源: `01_workflows/04_run-and-verify.md:25` keeps the 409 guard; `01_workflows/04_run-and-verify.md:131` changes golden to per-node author expectation.
- 测试: predict trace promotion returns 409; manual/copilot golden creation remains allowed.
- Status: backend-only live.
- 归属: capability `predict`; capability `golden-eval`; platform `engine`.

## 待 PM 补 gap

- Exact i/o panel affordance for choosing single input versus future batch input.
