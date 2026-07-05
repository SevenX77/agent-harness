---
module: 02_capabilities/phase-editing
doc: mvp1-alignment
status: FROZEN（Properties 按 phase kind 暴露可写白名单；SUBGRAPH 通过 folder reconnect 写 `path`，旧字段只读迁移、不写回；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [phase-field-whitelist, node-properties-role-test, io-panel-artifacts-test-inputs]
aligns_with: 01_workflows/02_authoring.md（phase editing / properties）· 01_workflows/00_settings-ux-spec.md（node role test）
---

# phase-editing — MVP1 Alignment

> **Tier**: capability | **Owns**: `phase-field-whitelist`（字段白名单/Properties）+ `node-properties-role-test` UI 落点 + `io-panel-artifacts-test-inputs` 消费切面 | **现状**: Properties 按 phase kind 暴露可写白名单；SUBGRAPH 通过 folder reconnect 写 `path`，旧字段只读迁移、不写回。 | **Related**: [baseline](./baseline.md)（双向）· `properties` · `input` · `studio-settings` · `engine` skill-syntax

## 1. 定义
`phase-editing` owns editing the selected phase node's allowed fields and body details in Properties/input/editor surfaces, then saving back to the node file and triggering compile feedback.

Source workflow basis: `01_workflows/02_authoring.md:18`, `01_workflows/02_authoring.md:28`, `01_workflows/02_authoring.md:37`.

## 2. 数据流 / 机制（设计细节）
### F1. Node Type From File Kind

- 机制: determine phase kind from the file the phase points to, not a mutable `mode` field.
- 决策: node type should be structural and stable.
- 原话/来源: `01_workflows/02_authoring.md:29` calls current mode/subagent shape stale and requires a three-type field rebuild.
- 测试: changing old `mode` frontmatter does not change rendered node type; file kind does.
- Status: target-design.
- 归属: capability `phase-editing`; region `properties`; platform `engine`.

### F2. Properties Field Whitelist

- 机制: render only the fields allowed for agent, logic, or subgraph nodes; field changes autosave to the owning Markdown file and save only those fields.
- 决策: Properties must stop being a generic old-frontmatter editor.
- 原话/来源: `01_workflows/02_authoring.md:28` marks current Properties save live but stale; `01_workflows/02_authoring.md:29` requires the whitelist rebuild.
- 测试: old fields are absent; required target fields are visible; editing a field writes the Markdown file without clicking Save; save round-trips without deleting body content.
- Status: target-design.
- 归属: region `properties`; platform `engine`; capability `file-editing`.

### F3. I/O And Artifact Outputs

- 机制: node input/output config includes imported file injection and output artifact paths, with defaults under workspace artifacts.
- 决策: output artifacts are per-node configuration and belong with i/o, not a separate predict concern.
- 原话/来源: `01_workflows/02_authoring.md:20` assigns i/o panel rename and artifact setup; `01_workflows/02_authoring.md:40` records artifact output decision.
- 测试: output artifact path persists; imported input file is injected when that node runs.
- Status: target-design.
- 归属: capability `phase-editing`; region `input`; platform `native-fs`, `engine`.

### F4. Subgraph Path Field

- 机制: subgraph nodes store a `path` reference (relative to the current skill root when possible; absolute accepted only inside the boundary). Properties changes it by reconnecting an existing child graph folder, not by freeform text input.
- 决策: no registry id for child graph resolution in MVP1.
- 原话/来源: `01_workflows/02_authoring.md:37` records subgraph path; `01_workflows/02_authoring.md:38` records relaxed child IO.
- 测试: Properties exposes a subgraph target reconnect control; missing path marks the target/assets state and offers folder reconnect; no strict child IO one-to-one check blocks compile.
- Status: target-design; current code stale.
- 归属: capability `phase-editing`; capability `skill-workspace`; region `properties`, `assets`.

### F5. L3 Step Editing

- 机制: agent body 的 steps/actions(正文 XML 结构)以**画布内联子节点**呈现,**在画布上直接拖拽增/删/改/重排**(保留源文本);**不在 Properties 做**——Properties 只管 frontmatter 属性。这些内联子节点正是运行期 debug bar「对话续跑」作用的对象(agent phase 子节点)。
- 决策: L3 步骤编辑 = **画布内联**(canvas-inline),非 Properties-first;职责切分:Properties=frontmatter,canvas=XML 正文结构(PM 2026-06-04)。
- 原话/来源: `01_workflows/02_authoring.md:30` defines the L3 add/edit/reorder target.
- 测试: add step creates body block; reorder preserves content; compile sees the updated body.
- Status: target-design.
- 归属: capability `phase-editing`; regions `canvas`, `properties`, `editor`.

### F6. Autosave Then Compile Feedback

- 机制: autosaving a phase file updates editor state, skill detail, and compile/lint context markers.
- 决策: authoring stays tight: edit field, autosave, see compile feedback at the place to fix.
- 原话/来源: `01_workflows/02_authoring.md:31` ties lint/compile and error panel to authoring; `01_workflows/03_compile.md:37` defines context-marker tests.
- 测试: autosave updates file hash; compile markers point to changed field/line; conflict recovery works.
- Status: autosave live, feedback target-design.
- 归属: capabilities `phase-editing`, `file-editing`, `compile-lint`.

## 3. 接口契约
- Node type is inferred from the phase file kind: agent, logic, or subgraph file.
- Properties renders a whitelist form per node type; unsupported old fields are not exposed.
- I/O panel owns node input/output files, output schema, artifacts, and golden-adjacent settings.
- Autosaves go through file-editing/native-fs and then compile-lint.
- Region links: `properties`, `input`, `editor`, `canvas`.
- Platform links: `native-fs`, `engine`.

## 4. 设计决策基础（PM 原话）
- L3 步骤重排 = **画布内联拖拽**(canvas-inline),非 Properties。Properties 只设 frontmatter 属性;正文 XML 结构(L3 步骤)= 画布内联子节点。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| PHASE_EDITING-1 | 字段白名单 | 单元 `phase-field-whitelist`；**为什么**：字段权威归 engine skill-syntax，Properties 只按三类节点(SKILL/LOGIC/SUBGRAPH)白名单显示 |
| PHASE_EDITING-2 | subgraph path | 单元 `phase-field-whitelist`；**为什么**：SUBGRAPH.md 使用 `path` 引用 child graph；Properties 只能通过重连文件夹写入该字段 |
| PHASE_EDITING-3 | role test | 单元 `node-properties-role-test`；**为什么**：节点 Properties 的 role 旁要有 Test 键+状态，复用 settings 的 role 测试机制 |

## 6. 测试关键点
1. 字段白名单: baseline 现状为 parser/form 仍用旧字段 ⚠️；目标为 只暴露 engine MVP1 phase schema 白名单字段。
2. subgraph path: 目标为 `path` 引用 child graph；UI 通过 folder reconnect 设置，保存时优先相对 skill root，解析 contract 引 engine。
3. role test: baseline 现状为 Properties role 行 Test+状态未建 ⚠️；目标为 role 旁有 Test 键，状态来自 studio-settings/gateway 投影。

## 7. 涉及 region / platform
`properties` · `input` · `studio-settings` · `engine` skill-syntax

## 8. gaps / 报警
- 🚨 字段白名单: parser/form 仍用旧字段 ⚠️；目标 只暴露 engine MVP1 phase schema 白名单字段。
- 🚨 subgraph path: 目标使用 `path` 引用 child graph；UI 通过 folder reconnect 设置，保存时优先相对 skill root，解析 contract 引 engine。
- 🚨 role test: Properties role 行 Test+状态未建 ⚠️；目标 role 旁有 Test 键，状态来自 studio-settings/gateway 投影。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `properties` · `input` · `studio-settings` · `engine` skill-syntax
