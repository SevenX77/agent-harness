# golden-eval MVP1 Alignment

## 定义

`golden-eval` owns per-agent-node expected outputs: node golden state, predict mock selection, manual/copilot golden creation, output-schema invalidation, and run-after actual-vs-golden diff.

Source workflow basis: `01_workflows/04_run-and-verify.md:118`, `01_workflows/04_run-and-verify.md:131`, `01_workflows/04_run-and-verify.md:135`.

## 接口契约

- Golden unit: one agent node's expected output, not a whole-run captured snapshot.
- Storage/UI target: golden settings and JSON files live with i/o output configuration.
- Predict: agent nodes mock from placeholder or golden automatically.
- Run: actual output compares against golden after real execution.
- Region links: `input`, `timeline`, `properties`, `canvas`, `copilot`.
- Platform links: `engine`, `native-fs`, `gateway` through copilot design.

## F1. Agent Node Golden State

- 机制: agent nodes move from untested to logic-ok to has-golden.
- 决策: golden is only for agent nodes; logic nodes already run deterministically in predict.
- 原话/来源: `01_workflows/04_run-and-verify.md:122` lists the three-state machine; `01_workflows/04_run-and-verify.md:133` says logic nodes do not participate.
- 测试: first successful predict marks no-golden agent as logic-ok; adding valid golden marks has-golden; logic nodes show no golden label.
- Status: target-design.
- 归属: capability `golden-eval`; regions `canvas`, `input`.

## F2. Automatic Mock Selection

- 机制: predict chooses placeholder mock when no golden exists and golden replay when golden exists.
- 决策: no manual mock selector.
- 原话/来源: `01_workflows/04_run-and-verify.md:123` defines mock by state; `01_workflows/04_run-and-verify.md:133` records g-b.
- 测试: no-golden predict emits schema-shaped placeholder; has-golden predict emits golden case; no real provider call occurs.
- Status: target-design/backend partial.
- 归属: capability `predict`; capability `golden-eval`; platform `engine`.

## F3. Create Golden Manually Or With Copilot

- 机制: i/o panel can generate an empty JSON template from output schema, while trace/sonner can open copilot chats to design golden.
- 决策: both the contextual trace button and batch sonner entry are required.
- 原话/来源: `01_workflows/04_run-and-verify.md:124` and `01_workflows/04_run-and-verify.md:125` list the two creation paths; `01_workflows/04_run-and-verify.md:137` records "两者都要".
- 测试: manual template matches output schema; trace button opens one chat for one node; batch entry opens chats for all missing-golden agent nodes.
- Status: target-design.
- 归属: capability `golden-eval`; capability `copilot-assist`; regions `input`, `timeline`, `copilot`.

## F4. Output Schema Invalidation

- 机制: changing output schema so a golden lacks required fields raises warning and compile error until fixed.
- 决策: prompt/internal agent changes do not invalidate golden; output shape changes do.
- 原话/来源: `01_workflows/04_run-and-verify.md:127` defines the invalidation trigger; `01_workflows/04_run-and-verify.md:137` keeps the PM wording.
- 测试: prompt edit keeps golden valid; adding required output field blocks compile/predict until golden contains it.
- Status: target-design.
- 归属: capability `golden-eval`; capability `compile-lint`; platform `engine`.

## F5. Run-after Field Diff

- 机制: after real run, compare actual agent output to per-node golden at field level.
- 决策: golden is for acceptance quality after Run, not a prerequisite for Run.
- 原话/来源: `01_workflows/04_run-and-verify.md:128` lists field diff; `01_workflows/04_run-and-verify.md:136` records run-after diff.
- 测试: changed/missing/extra fields show scores and values; route mismatch between frontend and backend is fixed.
- Status: backend whole-run diff live; per-node target-design; frontend orphan/mismatch.
- 归属: capability `golden-eval`; regions `properties`, `timeline`; platform `engine`.

## F6. Predict Trace Promotion Guard

- 机制: predict trace cannot be promoted into golden.
- 决策: golden must be author/copilot-defined expectation.
- 原话/来源: `01_workflows/04_run-and-verify.md:129` keeps the guard; `01_workflows/04_run-and-verify.md:132` replaces whole-run snapshot model.
- 测试: predict trace promotion returns 409; manual/copilot golden save succeeds.
- Status: backend-only live.
- 归属: capability `golden-eval`; platform `engine`.

## 待 PM 补 gap

- Exact golden file layout for per-node JSON under workspace storage.
- Copilot golden-design prompt content and stopping criteria.
