---
module: 03_regions/properties
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；Properties 仍用旧 phase 字段和 raw Connection Trace JSON；golden 完全不在 Properties 的新决策需保持 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:PropertiesPanel · apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:parsePhaseFrontmatter · apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:applyPhaseFrontmatterForm
units: [phase-field-whitelist, node-properties-role-test, trace-dot-blackboard]
---

# properties — Baseline（当下代码实现逻辑）

> **Scope**: Properties region：节点字段白名单表单、field-level compile marker、移除 raw edge trace dump、role test 状态。
> **现状一句话**: Properties 仍用旧 phase 字段和 raw Connection Trace JSON；golden 完全不在 Properties 的新决策需保持 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Panel route | Panels routes `activePanel === "properties"` to `PropertiesPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L43）` |
| Local UI wrappers | Properties imports local Button/Badge/Field/Input/Select/Textarea/ScrollArea wrappers. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:PropertiesPanel（L1）` |
| Phase parse | Panel reads phase file content and parses old frontmatter/body fields. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:modeLabel（L121）` |
| Save | Save applies form data and calls `onPhaseFileSave`. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:handleSave（L172）` |
| Selected edge branch | Selected edge renders a "Connection Trace" JSON block. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:next（L195）` |
| Phase form | Phase fields include old Mode, Python callable, System prompt, Exit contract, Tools, Target skill. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:kind（L380）` |
| Form model | `phase-frontmatter.ts` defines old field names and writes old XML blocks. | `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:phase-frontmatter（L8）`, `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:bodyFromForm（L203）` |
| Compile field markers | No field-level tooltip/diagnostic mapping exists. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:next（L293）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Panel route | Panels routes `activePanel === "properties"` to `PropertiesPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L43）` |
| Local UI wrappers | Properties imports local Button/Badge/Field/Input/Select/Textarea/ScrollArea wrappers. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:PropertiesPanel（L1）` |
| Phase parse | Panel reads phase file content and parses old frontmatter/body fields. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:modeLabel（L121）` |
| Save | Save applies form data and calls `onPhaseFileSave`. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:handleSave（L172）` |
| Selected edge branch | Selected edge renders a "Connection Trace" JSON block. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:next（L195）` |
| Phase form | Phase fields include old Mode, Python callable, System prompt, Exit contract, Tools, Target skill. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:kind（L380）` |
| Form model | `phase-frontmatter.ts` defines old field names and writes old XML blocks. | `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:phase-frontmatter（L8）`, `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:bodyFromForm（L203）` |
| Compile field markers | No field-level tooltip/diagnostic mapping exists. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:next（L293）` |

## 后端功能
N/A。

## 当前边界（properties 现在不是什么）
- 不拥有 golden diff。
- 字段权威归 engine skill-syntax；Properties 只显示白名单 UI。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 字段表单 | 旧 Mode/Python/SystemPrompt/ExitContract/TargetSkill ⚠️ | 字段白名单按 engine MVP1 schema |
| edge trace | selected edge 显示 raw JSON dump ⚠️ | dot/blackboard inspector 结构化显示 |
| golden scope | 旧未决口径曾把 golden 留在 Properties ⚠️ | golden 完全不在 Properties；入口归 I/O/Assets，diff 归 editor |
> **验"是否按目标改了"**：1. 字段表单；2. edge trace；3. golden scope。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:PropertiesPanel` → `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:parsePhaseFrontmatter` → `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:applyPhaseFrontmatterForm`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-properties)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `phase-editing` · `studio-settings` · `trace-observability` · `input` · `editor`
