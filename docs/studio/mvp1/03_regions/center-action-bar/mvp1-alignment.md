# center-action-bar MVP1 Alignment

## 定义

`center-action-bar` owns the main stage controls at the bottom center of the workspace: Compile, Predict, Run, their enabled/highlighted states, and the compile error drawer entry.

Source workflow basis: `01_workflows/03_compile.md:10`, `01_workflows/04_run-and-verify.md:8`.

## 接口契约

- Input props: stage and action callbacks.
- Stage contract: compile-pass enables Predict; predict-pass enables Run.
- Compile drawer target uses local `@/components/ui/*` drawer/sheet wrapper if available.
- Capability links: `compile-lint`, `predict`, `run-execution`.

## F1. Stage-gated Primary Actions

- 机制: one action is emphasized at a time according to build/predict/run stage.
- 决策: the user should always see the next safe action.
- 原话/来源: `01_workflows/03_compile.md:20` defines the gate; `01_workflows/04_run-and-verify.md:10` repeats it.
- 测试: compile fail highlights Compile; compile pass highlights Predict; predict pass highlights Run.
- Status: compile gate live, predict/run incomplete.
- 归属: region `center-action-bar`; capabilities `compile-lint`, `predict`, `run-execution`.

## F2. Compile Drawer Entry

- 机制: clicking Compile after or during failure opens a copyable drawer of all compile errors.
- 决策: replace the old floating card.
- 原话/来源: `01_workflows/03_compile.md:18` defines drawer behavior; `01_workflows/03_compile.md:35` records PM wording.
- 测试: drawer does not cover side panel; copy includes file/line/field/message.
- Status: target-design.
- 归属: region `center-action-bar`; capability `compile-lint`.

## F3. Predict And Run Click Wiring

- 机制: Predict and Run callbacks start their capability flows and update stage.
- 决策: Predict is a required flight test; Run is real execution.
- 原话/来源: `01_workflows/04_run-and-verify.md:20` and `01_workflows/04_run-and-verify.md:46` define the button actions.
- 测试: Predict success sets predict-pass; Run click creates run_id and opens live trace.
- Status: missing/stub.
- 归属: capabilities `predict`, `run-execution`; regions `input`, `timeline`.

## F4. Scoped Error Feedback

- 机制: action failures should show contextual markers and scoped drawer/toast, not noisy global error floods.
- 决策: real-time lint only marks; manual action can show detailed error.
- 原话/来源: `01_workflows/03_compile.md:28` states no global lint panel/toast during editing.
- 测试: lint fail changes stage without global toast; manual compile fail opens/updates drawer.
- Status: partial.
- 归属: region `center-action-bar`; capability `compile-lint`.

## 待 PM 补 gap

- Whether the Compile drawer opens automatically on failed manual compile or only after clicking Compile again.
