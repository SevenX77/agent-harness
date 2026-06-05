---
module: 03_regions/properties
doc: mvp1-alignment
status: drafted（Properties 仍用旧 phase 字段和 raw Connection Trace JSON；golden 完全不在 Properties 的新决策需保持 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [phase-field-whitelist, node-properties-role-test, trace-dot-blackboard]
aligns_with: 01_workflows/02_authoring.md（properties）· 01_workflows/00_settings-ux-spec.md（node role test）
---

# properties — MVP1 Alignment

> **Tier**: region | **Owns**: `phase-field-whitelist` 的 Properties UI + `node-properties-role-test` role 行 UI + `trace-dot-blackboard` inspector 落点 | **现状**: Properties 仍用旧 phase 字段和 raw Connection Trace JSON；golden 完全不在 Properties 的新决策需保持 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `phase-editing` · `studio-settings` · `trace-observability` · `input` · `editor`

## 1. 定义
`properties` owns the right/left panel view for the selected object's editable fields and contextual metadata: phase node whitelist forms, field-level diagnostics, and any selected-object summary that is not a full trace timeline.

Source workflow basis: `01_workflows/02_authoring.md:28`, `01_workflows/03_compile.md:16`, `01_workflows/04_run-and-verify.md:99`.

## 2. 数据流 / 机制（设计细节）
### F1. Node Field Whitelist Form

- 机制: render editable fields per agent/logic/subgraph node type and save to the phase file。**Properties 只管节点的 frontmatter 属性(白名单字段);节点正文结构(XML / L3 步骤)不在 Properties,在画布上以内联子节点呈现与编辑(见 `canvas` / `phase-editing` F5)**。
- 决策: rebuild away from stale generic mode/frontmatter fields;**职责切分锁定:Properties=frontmatter 属性,canvas=正文 XML 结构**(PM 2026-06-04)。
- 原话/来源: `01_workflows/02_authoring.md:28` marks current save stale; `01_workflows/02_authoring.md:29` requires the whitelist rebuild.
- 测试: selected agent/logic/subgraph each show only allowed fields; save preserves non-edited body blocks.
- Status: target-design.
- 归属: region `properties`; capability `phase-editing`.

### F2. Field-level Compile Marker

- 机制: compile diagnostics map to the exact field with tooltip and severity.
- 决策: properties is one of the three contextual error locations.
- 原话/来源: `01_workflows/03_compile.md:16` defines property/io field tooltip.
- 测试: invalid field shows tooltip next to the field; drawer links or focuses that field.
- Status: target-design.
- 归属: region `properties`; capability `compile-lint`.

### F3. Remove Raw Edge Trace Dump

- 机制: selected-edge raw JSON is replaced by trace-owned dot/context views.
- 决策: trace interpretation belongs to trace-observability, while Properties should not duplicate timeline.
- 原话/来源: `01_workflows/04_run-and-verify.md:99` calls for cleaning Properties selectedEdge JSON dump.
- 测试: edge click opens trace/dot context in the trace flow; Properties no longer displays mock JSON.
- Status: target-design cleanup.
- 归属: region `timeline`/`canvas`; capability `trace-observability`.

### F4. Golden Diff Summary

- 机制: **golden 完全不在 Properties**——golden 设置/文件/摘要/diff 入口归 **I/O 面板 output 区**,完整详细 diff 在**编辑器分屏**看(Monaco diff,见 `editor`)。Properties 不显示任何 golden。
- 决策: golden 属于 I/O(输出的期望基准);Properties 只剩 frontmatter 属性表单 + 字段级编译标记(PM 2026-06-04)。
- 原话/来源: `01_workflows/04_run-and-verify.md:128`(字段 diff);golden 归 I/O、Properties 纯 frontmatter = PM 2026-06-04。
- 测试: Properties 不出现任何 golden UI;golden 编辑/查看从 I/O output 或 Assets;详细 diff 从编辑器分屏。
- Status: target-design。
- 归属: region `input`(I/O); region `editor`; capability `golden-eval`。

## 3. 接口契约
- Inputs: selected node/edge, skill detail, diagnostics.（golden **不在** Properties，见 F4/§4）
- Outputs: phase file save, file open requests, panel focus changes.
- Capability links: `phase-editing`, `compile-lint`, `trace-observability`, `golden-eval`（**负向边界**：golden 不在 Properties）。

## 4. 设计决策基础（PM 原话）
- **golden 完全不在 Properties**:设置/文件/摘要归 **I/O output**,完整 diff 在**编辑器分屏(Monaco diff)**。Properties 只剩 frontmatter 属性 + 字段级编译标记。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| PROPERTIES-1 | 字段表单 | 对齐 `phase-field-whitelist` 设计单元，保证 region 切面能被测试回扣 |
| PROPERTIES-2 | edge trace | 对齐 `phase-field-whitelist` 设计单元，保证 region 切面能被测试回扣 |
| PROPERTIES-3 | golden scope | 对齐 `phase-field-whitelist` 设计单元，保证 region 切面能被测试回扣 |

## 6. 测试关键点
1. 字段表单: baseline 现状为 旧 Mode/Python/SystemPrompt/ExitContract/TargetSkill ⚠️；目标为 字段白名单按 engine MVP1 schema。
2. edge trace: baseline 现状为 selected edge 显示 raw JSON dump ⚠️；目标为 dot/blackboard inspector 结构化显示。
3. golden scope: baseline 现状为 旧未决口径曾把 golden 留在 Properties ⚠️；目标为 golden 完全不在 Properties；入口归 I/O/Assets，diff 归 editor。

## 7. 涉及 region / platform
`phase-editing` · `studio-settings` · `trace-observability` · `input` · `editor`

## 8. gaps / 报警
- 🚨 字段表单: 旧 Mode/Python/SystemPrompt/ExitContract/TargetSkill ⚠️；目标 字段白名单按 engine MVP1 schema。
- 🚨 edge trace: selected edge 显示 raw JSON dump ⚠️；目标 dot/blackboard inspector 结构化显示。
- 🚨 golden scope: 旧未决口径曾把 golden 留在 Properties ⚠️；目标 golden 完全不在 Properties；入口归 I/O/Assets，diff 归 editor。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `phase-editing` · `studio-settings` · `trace-observability` · `input` · `editor`
