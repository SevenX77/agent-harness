# run-execution MVP1 Alignment

## 定义

`run-execution` owns true execution after predict-pass: start a real run, stream state, light nodes, persist final context/metrics/trace, show run history, and support batch execution once input configuration is ready.

Source workflow basis: `01_workflows/04_run-and-verify.md:42`, `01_workflows/04_run-and-verify.md:61`, `01_workflows/04_run-and-verify.md:70`.

## 接口契约

- Entry: Run is enabled only after compile-pass and predict-pass.
- Input: i/o panel supplies single or batch input selection.
- Backend: run manager owns process lifecycle, run artifacts, websocket stream, and history.
- Trace/golden consumers read run outputs after completion.
- Region links: `center-action-bar`, `input`, `canvas`, `timeline`, `local-history`.
- Platform links: `engine`, `state-engine`, `native-fs`.

## F1. Start Single Run

- 机制: clicking Run posts selected input to `/runs`; backend spawns `run_skill` and returns run metadata.
- 决策: run burns real tokens and must come after predict.
- 原话/来源: `01_workflows/04_run-and-verify.md:46` defines the action; `01_workflows/04_run-and-verify.md:67` keeps the PM quote that predict/run just run according to config.
- 测试: Run disabled until predict-pass; successful click creates a run_id and metadata row.
- Status: backend live, frontend stub.
- 归属: capability `run-execution`; region `center-action-bar`, `input`; platform `engine`.

## F2. Live Run State And Node Lights

- 机制: run websocket events derive graph node statuses, edge animation, and current focus.
- 决策: run animation should reuse the role-test style for consistency.
- 原话/来源: `01_workflows/04_run-and-verify.md:49` and `01_workflows/04_run-and-verify.md:50` list status and node lights; `01_workflows/04_run-and-verify.md:67` records the PM animation decision.
- 测试: each node lights running/success/error from real events; failed node becomes red and stops focus.
- Status: placeholder.
- 归属: capability `run-execution`; capability `trace-observability`; region `canvas`; platform `state-engine`.

## F3. Run History And Detail

- 机制: list past runs, show status/duration/token summaries, and open a run detail/replay view.
- 决策: run aftercare belongs in the timeline/history area, not in the graph authoring form.
- 原话/来源: `01_workflows/04_run-and-verify.md:52` and `01_workflows/04_run-and-verify.md:58` list history and detail actions.
- 测试: completed/failed runs appear; detail drawer can replay with same input; delete removes a run row.
- Status: history live, detail drawer orphan.
- 归属: region `timeline`, `local-history`; capability `run-execution`.

## F4. Batch Run

- 机制: i/o panel selects multiple inputs, backend starts a batch, frontend polls progress and reports per-item failure.
- 决策: batch is input/run configuration, not an independent predict concept.
- 原话/来源: `01_workflows/04_run-and-verify.md:54` to `01_workflows/04_run-and-verify.md:57` list batch actions; `01_workflows/04_run-and-verify.md:62` places run entry in i/o panel.
- 测试: each input gets a run result; one failed item is visible and does not silently disappear.
- Status: backend live, frontend orphan.
- 归属: capability `run-execution`; region `input`; platform `engine`.

## F5. Successful Run Autocommit

- 机制: successful run triggers local git autocommit and stores status.
- 决策: autocommit is triggered by run but owned by save/publish.
- 原话/来源: `01_workflows/04_run-and-verify.md:59` marks autocommit backend-only; `01_workflows/04_run-and-verify.md:64` assigns it to save/publish.
- 测试: successful run commits; failed or interrupted run does not commit.
- Status: backend-only live.
- 归属: capability `publish`; platform `native-fs`.

## 待 PM 补 gap

- Final UX for batch input range naming and whether Replay belongs in Timeline or Local History first.
