---
module: 03_regions/center-action-bar
doc: mvp1-alignment
status: drafted（Compile 入口 live；Predict/Run handler 仍是 `console.info` 桩，compile error 仍底部浮层 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [compile-stage-gate, predict-execution]
aligns_with: 01_workflows/03_compile.md（stage gate）· 01_workflows/04_run-and-verify.md（predict/run）
---

# center-action-bar — MVP1 Alignment

> **Tier**: region | **Owns**: `compile-stage-gate` 的触发 UI + `predict-execution` 的入口 UI | **现状**: Compile 入口 live；Predict/Run handler 仍是 `console.info` 桩，compile error 仍底部浮层 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `compile-lint` · `predict` · `run-execution` · `timeline`

## 1. 定义
`center-action-bar` owns the main stage controls at the bottom center of the workspace: Compile, Predict, Run, their enabled/highlighted states, and the compile error drawer entry.

Source workflow basis: `01_workflows/03_compile.md:10`, `01_workflows/04_run-and-verify.md:8`.

## 2. 数据流 / 机制（设计细节）
### F1. Stage-gated Primary Actions

- 机制: one action is emphasized at a time according to build/predict/run stage.
- 决策: the user should always see the next safe action.
- 原话/来源: `01_workflows/03_compile.md:20` defines the gate; `01_workflows/04_run-and-verify.md:10` repeats it.
- 测试: compile fail highlights Compile; compile pass highlights Predict; predict pass highlights Run.
- Status: compile gate live, predict/run incomplete.
- 归属: region `center-action-bar`; capabilities `compile-lint`, `predict`, `run-execution`.

### F2. Compile Drawer Entry

- 机制: clicking Compile after or during failure opens a copyable drawer of all compile errors.
- 决策: replace the old floating card.
- 原话/来源: `01_workflows/03_compile.md:18` defines drawer behavior; `01_workflows/03_compile.md:35` records PM wording.
- 测试: drawer does not cover side panel; copy includes file/line/field/message.
- Status: target-design.
- 归属: region `center-action-bar`; capability `compile-lint`.

### F3. Predict And Run Click Wiring

- 机制: Predict and Run callbacks start their capability flows and update stage.
- 决策: Predict is a required flight test; Run is real execution.
- 原话/来源: `01_workflows/04_run-and-verify.md:20` and `01_workflows/04_run-and-verify.md:46` define the button actions.
- 测试: Predict success sets predict-pass; Run click creates run_id and opens live trace.
- Status: missing/stub.
- 归属: capabilities `predict`, `run-execution`; regions `input`, `timeline`.

### F4. Scoped Error Feedback

- 机制: action failures should show contextual markers and scoped drawer/toast, not noisy global error floods.
- 决策: real-time lint only marks; manual action can show detailed error.
- 原话/来源: `01_workflows/03_compile.md:28` states no global lint panel/toast during editing.
- 测试: lint fail changes stage without global toast; manual compile fail opens/updates drawer.
- Status: partial.
- 归属: region `center-action-bar`; capability `compile-lint`.

## 3. 接口契约
- Input props: stage and action callbacks.
- Stage contract: compile-pass enables Predict; predict-pass enables Run.
- Compile drawer target uses local `@/components/ui/*` drawer/sheet wrapper if available.
- Capability links: `compile-lint`, `predict`, `run-execution`.

## 4. 设计决策基础（PM 原话）
- 手动 Compile 失败时,报错 drawer **自动弹出**(非"再点一次才弹")——失败必想看原因。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| CENTER_ACTION_BAR-1 | Predict/Run wiring | 单元 `predict-execution`（+run 消费）；**为什么**：中心条 Predict/Run 按钮要接真实 onPredict/onRun，非 console 桩 |
| CENTER_ACTION_BAR-2 | compile drawer | 单元 `compile-stage-gate`；**为什么**：Compile 按钮触发编译并自动弹 drawer(呈现归 compile-lint) |
| CENTER_ACTION_BAR-3 | gate | 单元 `compile-stage-gate`；**为什么**：compile→predict→run 逐级门控，predict-pass 解锁 Run |

## 6. 测试关键点
1. Predict/Run wiring: baseline 现状为 `onPredict/onRun` 只 `console.info` ⚠️；目标为 Predict/Run 真发请求并驱动状态。
2. compile drawer: baseline 现状为 错误仍底部浮层 ⚠️；目标为 Compile error drawer 由操作条入口/自动弹出。
3. gate: baseline 现状为 Run 依赖永不会置位的 predict-pass ⚠️；目标为 compile-pass -> Predict；predict-pass -> Run。

## 7. 涉及 region / platform
`compile-lint` · `predict` · `run-execution` · `timeline`

## 8. gaps / 报警
- 🚨 Predict/Run wiring: `onPredict/onRun` 只 `console.info` ⚠️；目标 Predict/Run 真发请求并驱动状态。
- 🚨 compile drawer: 错误仍底部浮层 ⚠️；目标 Compile error drawer 由操作条入口/自动弹出。
- 🚨 gate: Run 依赖永不会置位的 predict-pass ⚠️；目标 compile-pass -> Predict；predict-pass -> Run。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `compile-lint` · `predict` · `run-execution` · `timeline`
