---
module: 02_capabilities/phase-editing
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；Properties/phase parser 仍读写旧 `mode/system_prompt/exit_contract/python_callable/target_skill` 字段 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:PropertiesPanel · apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:parsePhaseFrontmatter · apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:applyPhaseFrontmatterForm · apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:InputPanel
units: [phase-field-whitelist, node-properties-role-test, io-panel-artifacts-test-inputs]
---

# phase-editing — Baseline（当下代码实现逻辑）

> **Scope**: Properties 对节点 phase 字段的编辑、字段白名单、i/o 与 role test UI 落点。
> **现状一句话**: Properties/phase parser 仍读写旧 `mode/system_prompt/exit_contract/python_callable/target_skill` 字段 ⚠️。

## UI/UX
Properties 对节点 phase 字段的编辑、字段白名单、i/o 与 role test UI 落点。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Properties branch | Properties panel renders selected-node form and selected-edge trace branch. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:next（L195）`, `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:next（L293）` |
| Phase file parsing | Properties reads the selected phase file, parses frontmatter, and infers mode/kind from old fields. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:modeLabel（L121）`, `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:kind（L359）` |
| Save | Properties applies form data to the file and calls `onPhaseFileSave`. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:handleSave（L172）`, `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:next（L188）` |
| Form fields | Phase form fields are old `mode/pythonCallable/systemPrompt/exitContract/tools/targetSkill`. | `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:phase-frontmatter（L8）`, `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:kind（L380）` |
| XML blocks | Phase write helper manages old XML blocks like system prompt and exit contract. | `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:bodyFromForm（L203）` |
| Add phase scaffold | New phase draft writes old `mode`, prompt, exit contract, target skill, and python callable body. | `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:defaultPhaseMarkdown（L143）` |
| Node type inference | Build helpers still inspect `mode`, `target_skill`, and old subagent shape. | `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:subagentsForPhase（L151）`, `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:frontmatter（L197）` |
| Phase save path | Workspace writes the edited phase file and updates open editor/skill detail. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handlePhaseFileSave（L159）` |
| Input/schema panel | Input panel shows inferred schema only; no writeback to node i/o/golden settings. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:SchemaInferPanel（L18）`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:InputPanel（L72）` |

## 后端功能
N/A。

## 当前边界（phase-editing 现在不是什么）
- 字段权威归 engine skill-syntax；这里不复制完整语法。
- role 测试机制归 `studio-settings`，Properties 只承载节点 UI。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 字段白名单 | parser/form 仍用旧字段 ⚠️ | 只暴露 engine MVP1 phase schema 白名单字段 |
| subgraph path | 旧 `targetSkill` / local-path 口径残留 ⚠️ | 使用绝对 `path`，解析 contract 引 engine |
| role test | Properties role 行 Test+状态未建 ⚠️ | role 旁有 Test 键，状态来自 studio-settings/gateway 投影 |
> **验"是否按目标改了"**：1. 字段白名单；2. subgraph path；3. role test。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:PropertiesPanel` → `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:parsePhaseFrontmatter` → `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:applyPhaseFrontmatterForm` → `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:InputPanel`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-phase-editing)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `properties` · `input` · `studio-settings` · `engine` skill-syntax
