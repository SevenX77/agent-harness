---
module: 03_regions/input
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；InputPanel 仍投影固定 `input/sample.json`/`input/schema.json`，schema inference 无写回，Predict/Run 不消费选中输入 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:InputPanel · apps/studio/frontend/src/components/studio/panels/panel-files.ts:inputFiles · apps/studio/backend/app/routers/test_inputs.py:create_test_input · apps/studio/backend/app/routers/test_inputs.py:delete_test_input · apps/studio/frontend/src/components/studio/Workspace.tsx:onPredict · apps/studio/frontend/src/components/studio/Workspace.tsx:onRun
units: [io-panel-artifacts-test-inputs, golden-per-agent-node]
---

# input — Baseline（当下代码实现逻辑）

> **Scope**: I/O 面板身份、input/schema 文件、output artifact settings、Predict/Run 输入选择、golden JSON 与 batch 输入选择。
> **现状一句话**: InputPanel 仍投影固定 `input/sample.json`/`input/schema.json`，schema inference 无写回，Predict/Run 不消费选中输入 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Panel route | `Panels` routes `activePanel === "input"` to `InputPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L34）` |
| Title | Panel title is still "Input". | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:InputPanel（L72）`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:sample（L78）` |
| File rows | Panel projects `input/sample.json` and `input/schema.json` through `inputFiles`. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:files（L73）`, `apps/studio/frontend/src/components/studio/panels/panel-files.ts:inputFiles（L70）` |
| Schema inference | User can paste/drop JSON and see inferred schema, but there is no writeback. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:SchemaInferPanel（L18）`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:handleDrop（L28）` |
| File open | Input file rows open editor through `onFileOpen`. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:sample（L83）`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:sample（L86）` |
| Backend validation | Backend validates input data/file against schema. | `apps/studio/backend/app/routers/skills.py:fork_existing_skill（L454）` |
| Predict/run gap | Predict/Run buttons do not consume selected input from this panel. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L537）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L538）` |
| Batch orphan | BatchRunner can list inputs and run batch but is not mounted here. | `apps/studio/frontend/src/components/playground/BatchRunner.tsx:BatchRunner（L33）`, `apps/studio/frontend/src/hooks/useBatchRun.ts:runBatch（L73）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Panel route | `Panels` routes `activePanel === "input"` to `InputPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L34）` |
| Title | Panel title is still "Input". | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:InputPanel（L72）`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:sample（L78）` |
| File rows | Panel projects `input/sample.json` and `input/schema.json` through `inputFiles`. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:files（L73）`, `apps/studio/frontend/src/components/studio/panels/panel-files.ts:inputFiles（L70）` |
| Schema inference | User can paste/drop JSON and see inferred schema, but there is no writeback. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:SchemaInferPanel（L18）`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:handleDrop（L28）` |
| File open | Input file rows open editor through `onFileOpen`. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:sample（L83）`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:sample（L86）` |
| Predict/run gap | Predict/Run buttons do not consume selected input from this panel. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L537）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L538）` |
| Batch orphan | BatchRunner can list inputs and run batch but is not mounted here. | `apps/studio/frontend/src/components/playground/BatchRunner.tsx:BatchRunner（L33）`, `apps/studio/frontend/src/hooks/useBatchRun.ts:runBatch（L73）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Backend validation | Backend validates input data/file against schema. | `apps/studio/backend/app/routers/skills.py:fork_existing_skill（L454）` |

## 当前边界（input 现在不是什么）
- Predict/Run 执行归能力模块；input 只拥有输入选择/文件 UI。
- golden eval 数据流归 `golden-eval`，input 只承载入口。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| input 文件 | 固定假 `input/schema.json` 行 ⚠️ | 从 workspace/test-inputs 列出真实输入并可写回 |
| Predict/Run 输入 | 按钮不消费面板选中输入 ⚠️ | Predict/Run 使用 I/O 面板当前选择 |
| test_inputs API | create/delete 仍 501 ⚠️ | 增删测试输入 live，错误就近显示 |
> **验"是否按目标改了"**：1. input 文件；2. Predict/Run 输入；3. test_inputs API。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:InputPanel` → `apps/studio/frontend/src/components/studio/panels/panel-files.ts:inputFiles` → `apps/studio/backend/app/routers/test_inputs.py:create_test_input` → `apps/studio/backend/app/routers/test_inputs.py:delete_test_input` → `apps/studio/frontend/src/components/studio/Workspace.tsx:onPredict` → `apps/studio/frontend/src/components/studio/Workspace.tsx:onRun`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-input)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `phase-editing` · `predict` · `run-execution` · `golden-eval` · `assets`
