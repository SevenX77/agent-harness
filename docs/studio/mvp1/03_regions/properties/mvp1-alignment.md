---
module: 03_regions/properties
doc: mvp1-alignment
status: FROZEN（Properties 仍用旧 phase 字段和 raw Connection Trace JSON；golden 完全不在 Properties 的新决策需保持 ⚠️。；目标结构已按 R4-R8 retrofit）
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

- 机制: render editable fields per agent/logic/subgraph node type and persist field changes directly to the owning Markdown file (`SKILL.md` / `LOGIC.md` / `SUBGRAPH.md`) through file-editing/native-fs autosave; the form does not depend on a manual `Save` button. **Properties 只管节点的 frontmatter 属性(白名单字段);节点正文结构(XML / L3 步骤)不在 Properties,在画布上以内联子节点呈现与编辑(见 `canvas` / `phase-editing` F5)**。
- 决策: rebuild away from stale generic mode/frontmatter fields;**职责切分锁定:Properties=frontmatter 属性,canvas=正文 XML 结构**(PM 2026-06-04)。
- 原话/来源: `01_workflows/02_authoring.md:28` marks current save stale; `01_workflows/02_authoring.md:29` requires the whitelist rebuild.
- 测试: selected agent/logic/subgraph each show only allowed fields; editing a field debounces into a Markdown write without clicking Save; save preserves non-edited body blocks.
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

### F5. Node Compare LLMs Candidates（节点级对比候选配置）

- 机制: 节点 Properties 面板保留 `Compare LLMs` 区块，作者在此为**该节点**登记若干**对比候选**；每个候选 = 一个 model group + 一条 endpoint route（"auto" 或具体 route）。**候选只选模型，不做 role / bundle**（有意简化：对比 = 同节点同输入、只换底层模型）。
- 决策（PM 2026-07-02）:
  - **候选持久化在 `.workspace/runtime_config.json`**，按 `skill + node` 归属，**不写进 SKILL.md**（对比是运行期实验配置，不是 skill 源文件的一部分）；节点改名 → runtime_config key 同步迁移。
  - **运行机制 = 旁路单节点多跑**（详见 `01_workflows/00_settings-ux-spec.md §2.8` + `timeline` F6）：主图用基准模型照常跑一次；Studio 抓对比节点在主 run 的 `InputDispatchEvent` 输入切片，对每个候选把**该单个 phase** 物化成 `depends_on=input` 的单节点临时 skill 变体 + 候选临时 roles，走现成 `run_artifact` 各跑一遍。独立单节点 run ⇒ **不改 engine 执行、永不写主黑板、per-candidate artifacts 各自分目录**。
  - **旧整图按角色扇出链删除**：`CompareRunDialog` + `POST /runs/compare` role fan-out + `run_compare.py` 整图 roles 物化同批清掉。
- 原话/来源: PM 2026-07-01「跑对比是在整图真的 run 的时候跑的……直接在这个节点加一个平行的 node，同样的输入和其他配置，除了 llm 不同」+ 2026-07-02 实证"引擎跑不了并联"后 PM 批准的旁路单节点等价方案。
- 测试: 候选增删改持久化按 skill+node 存取；对比运行产出基准 + 各候选独立 run（各自 artifacts 目录）；候选 run 不改主 run 的 final_state（零黑板污染）；Trace 顶部 tab 显示基准 + 候选。
- Status: target-design（PR2 实现）。
- 归属: region `properties`（候选配置 UI）; capabilities `run-execution`、`trace-observability`（结果 tab 归 `timeline` F6）。

### F6. Agent Node Custom Model Params

- 机制: Agent 节点 Properties 的 `Custom model params` 是独立于 `SKILL.md` 的节点级运行参数开关，数据存于 `.workspace/runtime_config.json` 的 llm/node params 区。`enabled=true` 时该节点的 `thinking` / `max_output_tokens` / `temperature` 作为 node override 参与运行；`enabled=false` 时运行时完全继承当前 llm role，但已有字段值作为未激活草稿保留，重新打开开关应恢复之前的节点设定。只有 `enabled=false` 且所有字段均为空时，后端才把该 node entry 视为可清理的空记录。
- 决策: 关闭开关不得清空作者刚调好的参数；它只改变“是否把这些值用于运行”。继承态仍必须显示具体数值而不是 `Model default`，并且 fallback 值来自实时 `GET /api/llm/roles` 数据源（Settings 保存或 `roles_changed` 事件重拉后同步刷新），不得在 Properties 打开时复制一份静态 role 参数。
- 默认: MVP1 llm role setting 应有明确默认值；temperature 缺省显示 role 默认 70%（authored `1.4`），正常情况下不应落到 opaque model default。
- 测试: 关闭 custom checkbox 后 PUT 保存 `enabled:false` 且保留字段值；UI 显示角色 fallback 具体值；重新打开恢复之前字段值。Settings / LLM Roles 修改 role 参数或收到 `roles_changed` 重拉后，Properties 继承态同步更新同一份 role 数据源。temperature slider 只在 commit/放手/blur/key 结束时触发保存。
- Status: target-design.
- 归属: region `properties`; capability `phase-field-whitelist`; backend `node-llm-params`.

## 3. 接口契约
- Inputs: selected node/edge, skill detail, diagnostics, **节点级对比候选（runtime_config 按 skill+node 存取）**, **实时 LLM Roles 数据源与 node custom model params**。（golden **不在** Properties，见 F4/§4）
- Outputs: phase file save, file open requests, panel focus changes, **对比候选写入 runtime_config + 触发对比运行**, **node custom model params 保存到 runtime_config**。
- Capability links: `phase-editing`, `compile-lint`, `trace-observability`, `run-execution`, `golden-eval`（**负向边界**：golden 不在 Properties）。

## 4. 设计决策基础（PM 原话）
- **golden 完全不在 Properties**:设置/文件/摘要归 **I/O output**,完整 diff 在**编辑器分屏(Monaco diff)**。Properties 只剩 frontmatter 属性 + 字段级编译标记。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| PROPERTIES-1 | 字段表单 | 单元 `phase-field-whitelist`（落点/消费；owner=phase-editing）；**为什么**：字段权威归 engine skill-syntax，Properties 按节点类型白名单显示 |
| PROPERTIES-2 | edge trace | 单元 `trace-dot-blackboard`（消费；owner=trace-observability）；**为什么**：选中 edge 的 raw JSON dump 要换成 dot/blackboard 结构化 inspector |
| PROPERTIES-3 | golden scope | 单元 `golden-per-agent-node`（负向边界）；**为什么**：golden 完全不在 Properties，入口归 I/O、diff 归 editor |
| PROPERTIES-4 | node custom model params | 单元 `phase-field-whitelist`（消费；owner=properties/backend node params）；**为什么**：节点级 LLM 参数是运行期覆盖层，关闭开关只停用覆盖而不销毁作者草稿 |

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
