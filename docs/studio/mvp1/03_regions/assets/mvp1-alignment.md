---
module: 03_regions/assets
doc: mvp1-alignment
status: FROZEN（文件树 live；subgraph 检测读取 topology path / legacy migration signal；无本地假 fallback 行；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [subgraph-path-inline-drilldown]
aligns_with: 01_workflows/02_authoring.md（assets / subgraph）
---

# assets — MVP1 Alignment

> **Tier**: region | **Owns**: `subgraph-path-inline-drilldown` 的未解析导入 / Assets UI 切面 | **现状**: 文件树 live；subgraph 检测读取 topology path / legacy migration signal；无本地假 fallback 行。 | **Related**: [baseline](./baseline.md)（双向）· `graph-authoring` · `canvas` · `skill-workspace` · `native-fs` · `engine` resolver/skill-syntax

## 1. 定义
`assets` owns the left panel file browser and subgraph workspace membership surface: opening files, showing real skill files, marking missing subgraph paths, and adding subgraph folders to the workspace.

Source workflow basis: `01_workflows/01_init.md:16`, `01_workflows/02_authoring.md:37`.

## 2. 数据流 / 机制（设计细节）
### F1. Skill File Tree

- 机制: render actual files/folders from skill detail and open files into the editor.
- 决策: Assets is inspection/navigation, not a second source of file metadata.
- 原话/来源: `01_workflows/02_authoring.md:48` links `.workspace`/file tree to file-editing.
- 测试: all files in detail appear once; clicking file opens editor; file tree updates after save/create.
- Status: live.
- 归属: region `assets`; capability `file-editing`.

### F2. Missing Subgraph Path Status

- 机制: detect subgraph `path` references(engine skill-syntax §2.1: relative skill-root path preferred, absolute accepted only inside boundary)and mark unresolved paths with a recovery action.
- 决策: subgraph references are paths and missing child graph should be fixable from Assets.
- 原话/来源: `01_workflows/02_authoring.md:37` locks path references.
- 测试: unresolved path appears red/actionable; resolved path shows ready; no fake fallback rows.
- Status: target-design.
- 归属: region `assets`; capabilities `skill-workspace`, `graph-authoring`.

### F3. Add Subgraph Folder To Workspace

- 机制: user picks a child folder and Studio adds it to workspace membership/resolution state.
- 决策: recovery should not require registry registration.
- 原话/来源: `01_workflows/01_init.md:35` locks local workspace model; `01_workflows/02_authoring.md:37` removes registry-based child lookup.
- 测试: picker result resolves the missing subgraph; reload keeps resolution.
- Status: placeholder/fake today.
- 归属: region `assets`; platform `native-fs`.

### F4. Selected Node Context

- 机制: Assets may highlight the file/subgraph connected to the selected canvas node.
- 决策: cross-region focus should help orientation without duplicating Properties.
- 原话/来源: `01_workflows/02_authoring.md:18` keeps canvas/properties/file editing in one authoring loop.
- 测试: selecting a phase highlights its file; clearing selection clears highlight.
- Status: target-design.
- 归属: region `assets`; region `canvas`.

## 3. 接口契约
- Inputs: `skillDetail.files`, selected node, workspace path/subgraph resolution status.
- Outputs: file open requests and add-folder-to-workspace requests.
- Capability links: `file-editing`, `skill-workspace`, `graph-authoring`, `phase-editing`.
- Platform link: `native-fs`.

## 4. 设计决策基础（PM 原话）
- 子图成员归属**只在 Assets**(不在 Welcome 重复)。
- golden 文件也可从 **Assets workspace 文件树直接打开**(另一入口 = I/O output)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| ASSETS-1 | 子图检测 | 单元 `subgraph-path-inline-drilldown`；**为什么**：assets 子图类目 ↔ 节点文件同步，子图 path 找不到→标红 |
| ASSETS-2 | 假数据 | 单元 `subgraph-path-inline-drilldown`；**为什么**：现 AssetsPanel 读 `sub_skill_ref` 旧形态假数据，要按 D7 path 真实呈现 |
| ASSETS-3 | 加入工作区 | 单元 `subgraph-path-inline-drilldown`；**为什么**：子图 path 解析不到 → OS 选文件夹导入工作区(R5+D7) |

## 6. 测试关键点
1. 子图检测: 目标为按 engine MVP1 `path` 与 resolver 状态显示；legacy fields 只作为 migration-needed signal，不作为 linked truth。
2. 假数据: baseline 现状为 本地 hardcoded cache / classifier fallback 行 ⚠️；目标为 无真实子图时显示空态，不造假行。
3. 加入工作区: baseline 现状为 Register 只更新 local cache/toast ⚠️；目标为 触发 Open Folder/MRU/native-fs 路径并保留冲突反馈。

## 7. 涉及 region / platform
`graph-authoring` · `canvas` · `skill-workspace` · `native-fs` · `engine` resolver/skill-syntax

## 8. gaps / 报警
- 🚨 子图检测: 目标按 engine MVP1 `path` 与 resolver 状态显示；legacy fields 只作为 migration-needed signal，不作为 linked truth。
- 🚨 假数据: 本地 hardcoded cache / classifier fallback 行 ⚠️；目标 无真实子图时显示空态，不造假行。
- 🚨 加入工作区: Register 只更新 local cache/toast ⚠️；目标 触发 Open Folder/MRU/native-fs 路径并保留冲突反馈。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `graph-authoring` · `canvas` · `skill-workspace` · `native-fs` · `engine` resolver/skill-syntax
