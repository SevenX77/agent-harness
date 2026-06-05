---
module: 03_regions/input
doc: mvp1-alignment
status: drafted（InputPanel 仍投影固定 `input/sample.json`/`input/schema.json`，schema inference 无写回，Predict/Run 不消费选中输入 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [io-panel-artifacts-test-inputs, golden-per-agent-node]
aligns_with: 01_workflows/02_authoring.md（i/o panel）· 01_workflows/04_run-and-verify.md（predict/run input/golden）
---

# input — MVP1 Alignment

> **Tier**: region | **Owns**: `io-panel-artifacts-test-inputs`（i/o 面板 owner）+ `golden-per-agent-node` 的 I/O output/golden JSON 入口切面 | **现状**: InputPanel 仍投影固定 `input/sample.json`/`input/schema.json`，schema inference 无写回，Predict/Run 不消费选中输入 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `phase-editing` · `predict` · `run-execution` · `golden-eval` · `assets`

## 1. 定义
`input` is the current folder name for the MVP1 i/o panel region. It owns node/run input files, schema, validation entry, output artifact paths, golden JSON/settings, and single/batch input selection for Predict/Run.

Source workflow basis: `01_workflows/02_authoring.md:20`, `01_workflows/04_run-and-verify.md:21`, `01_workflows/04_run-and-verify.md:62`.

## 2. 数据流 / 机制（设计细节）
### F1. I/O Panel Identity

- 机制: rename visible panel semantics from Input to i/o and include output-side settings.
- 决策: input, validate, and batch are configuration; not separate predict products.
- 原话/来源: `01_workflows/04_run-and-verify.md:30` removes input/validate/batch as standalone predict issues; `01_workflows/04_run-and-verify.md:35` keeps PM wording.
- 测试: panel copy and affordances cover input and output; no separate PredictInputDialog appears.
- Status: target-design.
- 归属: region `input`; capabilities `predict`, `phase-editing`.

### F2. Input Files And Schema

- 机制: import/select files, infer or edit schema, and validate against schema before Predict/Run.
- 决策: selected input belongs to the node/run configuration.
- 原话/来源: `01_workflows/04_run-and-verify.md:21` assigns test input selection here; `01_workflows/04_run-and-verify.md:22` keeps validation inside predict.
- 测试: file import persists; schema inference can be saved; invalid input blocks predict with field error.
- Status: inference demo live, persistence target-design.
- 归属: region `input`; capability `predict`; platform `engine`.

### F3. Output Artifact Settings

- 机制: configure node output files and artifact paths from the i/o panel.
- 决策: output artifact paths are per-node output settings.
- 原话/来源: `01_workflows/02_authoring.md:20` assigns artifact setup to i/o; `01_workflows/02_authoring.md:40` records artifact output decision.
- 测试: setting an output artifact path updates node file; default path lands under workspace artifacts.
- Status: target-design.
- 归属: region `input`; capability `phase-editing`; platform `native-fs`.

### F4. Predict/Run Input Selection

- 机制: selected file/config becomes the input payload for Predict and Run.
- 决策: Predict and Run execute according to configuration.
- 原话/来源: `01_workflows/04_run-and-verify.md:34` and `01_workflows/04_run-and-verify.md:67` record that predict/run run according to config.
- 测试: changing selected input changes predict/run payload; missing selection produces scoped panel error.
- Status: missing.
- 归属: region `input`; capabilities `predict`, `run-execution`.

### F5. Golden Settings And JSON

- 机制: generate/edit per-agent-node golden JSON from output schema;**golden 文件可从 I/O output 区直接点开编辑/查看(随时可编辑),另一入口在 Assets workspace 文件树直接打开该文件**;golden 摘要/diff 入口归 I/O,不在 Properties。
- 决策: golden settings belong with output because golden is expected output;**golden 主入口 = Assets workspace + I/O output,随时可编辑;golden 不归 Properties**(PM 2026-06-04)。
- 原话/来源: `01_workflows/04_run-and-verify.md:125` and `01_workflows/04_run-and-verify.md:126` assign golden template/settings to i/o.
- 测试: create template from schema; fill JSON; node state changes to has-golden.
- Status: target-design.
- 归属: region `input`; capability `golden-eval`.

### F6. Batch Input Selection

- 机制: select multiple inputs, start batch, and show progress/per-item failures.
- 决策: batch is run input configuration.
- 原话/来源: `01_workflows/04_run-and-verify.md:54` to `01_workflows/04_run-and-verify.md:57` list batch actions.
- 测试: multiple selected inputs create batch; failed item is visible.
- Status: backend/orphan frontend.
- 归属: region `input`; capability `run-execution`.

## 3. 接口契约
- Inputs: selected node, skill files, node i/o schema, imported input files, golden state.
- Outputs: file open, schema write/update, selected predict/run input, batch input list, artifact path edits.
- Capability links: `phase-editing`, `predict`, `run-execution`, `golden-eval`.
- Platform links: `native-fs`, `engine`.

## 4. 设计决策基础（PM 原话）
- 面板可见名 = **"I/O"**(文件夹路径 `input` 不变)。
- golden 主入口 = ① Assets workspace 文件树直接打开文件;② I/O 面板 output 区点开编辑/查看;**随时可编辑**;golden 归 I/O,不归 Properties。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| INPUT-1 | input 文件 | 对齐 `io-panel-artifacts-test-inputs` 设计单元，保证 region 切面能被测试回扣 |
| INPUT-2 | Predict/Run 输入 | 对齐 `io-panel-artifacts-test-inputs` 设计单元，保证 region 切面能被测试回扣 |
| INPUT-3 | test_inputs API | 对齐 `io-panel-artifacts-test-inputs` 设计单元，保证 region 切面能被测试回扣 |

## 6. 测试关键点
1. input 文件: baseline 现状为 固定假 `input/schema.json` 行 ⚠️；目标为 从 workspace/test-inputs 列出真实输入并可写回。
2. Predict/Run 输入: baseline 现状为 按钮不消费面板选中输入 ⚠️；目标为 Predict/Run 使用 I/O 面板当前选择。
3. test_inputs API: baseline 现状为 create/delete 仍 501 ⚠️；目标为 增删测试输入 live，错误就近显示。

## 7. 涉及 region / platform
`phase-editing` · `predict` · `run-execution` · `golden-eval` · `assets`

## 8. gaps / 报警
- 🚨 input 文件: 固定假 `input/schema.json` 行 ⚠️；目标 从 workspace/test-inputs 列出真实输入并可写回。
- 🚨 Predict/Run 输入: 按钮不消费面板选中输入 ⚠️；目标 Predict/Run 使用 I/O 面板当前选择。
- 🚨 test_inputs API: create/delete 仍 501 ⚠️；目标 增删测试输入 live，错误就近显示。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `phase-editing` · `predict` · `run-execution` · `golden-eval` · `assets`
