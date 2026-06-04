# input MVP1 Alignment

## 定义

`input` is the current folder name for the MVP1 i/o panel region. It owns node/run input files, schema, validation entry, output artifact paths, golden JSON/settings, and single/batch input selection for Predict/Run.

Source workflow basis: `01_workflows/02_authoring.md:20`, `01_workflows/04_run-and-verify.md:21`, `01_workflows/04_run-and-verify.md:62`.

## 接口契约

- Inputs: selected node, skill files, node i/o schema, imported input files, golden state.
- Outputs: file open, schema write/update, selected predict/run input, batch input list, artifact path edits.
- Capability links: `phase-editing`, `predict`, `run-execution`, `golden-eval`.
- Platform links: `native-fs`, `engine`.

## F1. I/O Panel Identity

- 机制: rename visible panel semantics from Input to i/o and include output-side settings.
- 决策: input, validate, and batch are configuration; not separate predict products.
- 原话/来源: `01_workflows/04_run-and-verify.md:30` removes input/validate/batch as standalone predict issues; `01_workflows/04_run-and-verify.md:35` keeps PM wording.
- 测试: panel copy and affordances cover input and output; no separate PredictInputDialog appears.
- Status: target-design.
- 归属: region `input`; capabilities `predict`, `phase-editing`.

## F2. Input Files And Schema

- 机制: import/select files, infer or edit schema, and validate against schema before Predict/Run.
- 决策: selected input belongs to the node/run configuration.
- 原话/来源: `01_workflows/04_run-and-verify.md:21` assigns test input selection here; `01_workflows/04_run-and-verify.md:22` keeps validation inside predict.
- 测试: file import persists; schema inference can be saved; invalid input blocks predict with field error.
- Status: inference demo live, persistence target-design.
- 归属: region `input`; capability `predict`; platform `engine`.

## F3. Output Artifact Settings

- 机制: configure node output files and artifact paths from the i/o panel.
- 决策: output artifact paths are per-node output settings.
- 原话/来源: `01_workflows/02_authoring.md:20` assigns artifact setup to i/o; `01_workflows/02_authoring.md:40` records artifact output decision.
- 测试: setting an output artifact path updates node file; default path lands under workspace artifacts.
- Status: target-design.
- 归属: region `input`; capability `phase-editing`; platform `native-fs`.

## F4. Predict/Run Input Selection

- 机制: selected file/config becomes the input payload for Predict and Run.
- 决策: Predict and Run execute according to configuration.
- 原话/来源: `01_workflows/04_run-and-verify.md:34` and `01_workflows/04_run-and-verify.md:67` record that predict/run run according to config.
- 测试: changing selected input changes predict/run payload; missing selection produces scoped panel error.
- Status: missing.
- 归属: region `input`; capabilities `predict`, `run-execution`.

## F5. Golden Settings And JSON

- 机制: generate/edit per-agent-node golden JSON from output schema.
- 决策: golden settings belong with output because golden is expected output.
- 原话/来源: `01_workflows/04_run-and-verify.md:125` and `01_workflows/04_run-and-verify.md:126` assign golden template/settings to i/o.
- 测试: create template from schema; fill JSON; node state changes to has-golden.
- Status: target-design.
- 归属: region `input`; capability `golden-eval`.

## F6. Batch Input Selection

- 机制: select multiple inputs, start batch, and show progress/per-item failures.
- 决策: batch is run input configuration.
- 原话/来源: `01_workflows/04_run-and-verify.md:54` to `01_workflows/04_run-and-verify.md:57` list batch actions.
- 测试: multiple selected inputs create batch; failed item is visible.
- Status: backend/orphan frontend.
- 归属: region `input`; capability `run-execution`.

## 待 PM 补 gap

- Final visible name: "Input" vs "I/O"; path remains `input` unless the docs/code tree is later renamed.
