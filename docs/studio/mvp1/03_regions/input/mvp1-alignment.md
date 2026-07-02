---
module: 03_regions/input
doc: mvp1-alignment
status: FROZEN（2026-07-02 按代码核对:InputPanel 已是 per-node 实例预览(假文件投影已删),Predict/Run 已消费选中测试输入(resolveRunInput),test_inputs CRUD live;缺口=TestInputsSection/GoldenSection 建而未挂、file-import/artifact 设置无面板入口 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [io-panel-artifacts-test-inputs, golden-per-agent-node]
aligns_with: 01_workflows/02_authoring.md（i/o panel）· 01_workflows/04_run-and-verify.md（predict/run input/golden）
---

# input — MVP1 Alignment

> **Tier**: region | **Owns**: `io-panel-artifacts-test-inputs`（i/o 面板 owner）+ `golden-per-agent-node` 的 I/O output/golden JSON 入口切面 | **现状**: InputPanel 已是 per-node 实例预览(假文件投影已删,jsonExampleFromSchema + Edit 跳文件);Predict/Run 已消费选中输入(Workspace→resolveRunInput);test_inputs 后端 CRUD live;⚠️ 缺口=TestInputsSection/GoldenSection 建而未挂进面板,file-import/artifact 设置纯函数在 `lib/schema-infer.ts` 但无面板入口。 | **Related**: [baseline](./baseline.md)（双向）· `phase-editing` · `predict` · `run-execution` · `golden-eval` · `assets`

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

### F2. Input Files And Schema Instance Preview

- 机制: 面板显示两层真实内容:① **实例预览**——按当前声明的 io schema 推导出"按现在的 schema 大致会得到什么"的示例 JSON(清爽只读,input/output 两侧都给);② **真实测试输入文件**——import/select files,选中项即 Predict/Run payload,照 schema 校验后才可 Predict。**schema 本体不在面板内编辑**:面板只提供两个编辑入口——打开对应源文件(editor)/ 唤起 copilot 改;不再有 schema 表单,也不再有独立的 schema 推断展示。
- 决策: 面板 = 实例预览 + 数据选择;schema 编辑走 copilot 或直接改文件——在面板里维护 schema 表单太复杂,字段多、嵌套深会把人搞晕(PM 2026-07-02,修订本条旧 "infer or edit schema" 语义);selected input belongs to the node/run configuration(不变)。
- 原话/来源: PM 2026-07-02(原话见 §4);`01_workflows/04_run-and-verify.md:21` assigns test input selection here; `01_workflows/04_run-and-verify.md:22` keeps validation inside predict.
- 测试: 实例预览由真实 io 声明推导(非投影假文件、非独立推断产物);面板无 schema 表单,编辑入口跳文件/copilot;file import persists; invalid input blocks predict with field error.
- Status: target-design(旧 inference demo 与假文件投影一并废弃)。
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

- 机制: generate/edit per-agent-node golden JSON from output schema;**golden 文件可从 I/O output 区直接点开编辑/查看(随时可编辑),另一入口在 Assets workspace 文件树直接打开该文件**;golden 摘要/diff 入口归 I/O,不在 Properties。**golden JSON 与 F2 的 output 实例预览同构**——都是该节点 `io.outputs` schema 的数据实例,形状无区别,差别只在生命周期(预览=临时示意,golden=作者认可并持久化到 `.workspace/golden` 的期望值);预览"存为 golden"即完成创建路 B,schema→实例生成器与 predict 占位 mock、golden 空模板共用一套(PM 2026-07-02)。
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
- Outputs: file open, schema edit jump(editor/copilot;面板不直接写 schema), selected predict/run input, batch input list, artifact path edits.
- Capability links: `phase-editing`, `predict`, `run-execution`, `golden-eval`.
- Platform links: `native-fs`, `engine`.

## 4. 设计决策基础（PM 原话）
- 面板可见名 = **"I/O"**(文件夹路径 `input` 不变)。
- golden 主入口 = ① Assets workspace 文件树直接打开文件;② I/O 面板 output 区点开编辑/查看;**随时可编辑**;golden 归 I/O,不归 Properties。
- **I/O 面板 = 实例预览,schema 编辑走 copilot/文件**(PM 2026-07-02):"原设计在panel里面做这步太复杂了,有太多的字段以及字段嵌套,会把人搞晕的,还不如清爽的让用户看到这里按照现在的schema大致会得到什么,然后用copilot或者自己直接去改文件"。
- **golden JSON 与推导实例同构**(PM 2026-07-02):"golden输出的json和现在推测的json没有区别"——都是 `io.outputs` schema 的实例,差别只在语义/生命周期。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| INPUT-1 | input 文件 | 单元 `io-panel-artifacts-test-inputs`；**为什么**：input panel 改 i/o panel，每节点 io 设置 + 文件导入注入黑板 |
| INPUT-2 | Predict/Run 输入 | 单元 `io-panel-artifacts-test-inputs`；**为什么**：predict/run 的输入选择落在 i/o 面板 |
| INPUT-3 | test_inputs API | 单元 `io-panel-artifacts-test-inputs`；**为什么**：test_inputs CRUD 现 501，要接通批量测试输入 |

## 6. 测试关键点
1. input 文件: baseline 现状为 TestInputsSection 建而未挂载,面板无输入文件区 ⚠️；目标为 面板列出 `.workspace/test_inputs/` 真实输入并可增删/选中。
2. Predict/Run 输入: baseline 现状为 Workspace→resolveRunInput 链路已消费 selectedTestInputId,但 InputPanel 忽略该 props、无选择 UI ⚠️；目标为 面板选中项 = Predict/Run payload,端到端可点。
3. test_inputs API: baseline 现状为 后端 CRUD live(app/routers/test_inputs.py),前端未挂消费 UI ⚠️；目标为 增删测试输入端到端 live,错误就近显示。

## 7. 涉及 region / platform
`phase-editing` · `predict` · `run-execution` · `golden-eval` · `assets`

## 8. gaps / 报警
- 🚨 input 文件区: TestInputsSection 建而未挂载 ⚠️；目标 面板 input files 区列真实输入、可增删/选中。
- 🚨 Predict/Run 输入选择 UI: 消费链路已 live 但 InputPanel 无选择 UI(忽略 selectedTestInputId props)⚠️；目标 面板选中项 = Predict/Run payload。
- 🚨 golden 入口: GoldenSection 建而未挂载 ⚠️；目标 output 区可点开查看/编辑 golden。
- 🚨 file-import / artifact 设置入口: `lib/schema-infer.ts` 纯函数在、面板无入口 ⚠️；目标 input files 区导入文件(source:file)、output 区设 artifact 路径。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `phase-editing` · `predict` · `run-execution` · `golden-eval` · `assets`
