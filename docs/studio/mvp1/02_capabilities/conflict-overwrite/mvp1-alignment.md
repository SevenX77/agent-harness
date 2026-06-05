---
module: 02_capabilities/conflict-overwrite
doc: mvp1-alignment
status: drafted（顺序覆盖与文件保存冲突都有实现痕迹，但还是两套 UX，没有统一冲突呈现 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [conflict-overwrite-resolution]
aligns_with: 01_workflows/02_authoring.md（保存 / 覆盖冲突）
---

# conflict-overwrite — MVP1 Alignment

> **Tier**: capability | **Owns**: `conflict-overwrite-resolution`（冲突呈现 owner） | **现状**: 顺序覆盖与文件保存冲突都有实现痕迹，但还是两套 UX，没有统一冲突呈现 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `canvas` · `editor` · `file-editing`

## 1. 定义
`conflict-overwrite` owns user-facing conflict decisions where Studio would otherwise silently lose intent: file save conflicts and graph/data-flow overwrite conflicts.

Source workflow basis: `01_workflows/02_authoring.md:18`, `01_workflows/03_compile.md:13`.

## 2. 数据流 / 机制（设计细节）
### F1. Prevent Silent File Overwrite

- 机制: every save includes an expected hash; mismatch opens a conflict flow rather than replacing remote content.
- 决策: local editing should be forgiving but never silently destructive.
- 原话/来源: `01_workflows/02_authoring.md:31` keeps live lint/compile active while editing; this implies saves can race with validation or file-watch changes.
- 测试: stale editor save returns conflict; choosing remote replaces local; choosing diff shows both sides.
- Status: live.
- 归属: capability `file-editing`; capability `conflict-overwrite`; platform `native-fs`.

### F2. Detect Sequential Output Overwrite

- 机制: when later phases overwrite the same output key, Studio flags the downstream node and asks for explicit confirmation.
- 决策: overwrites are legal only when the author marks them intentional.
- 原话/来源: `01_workflows/02_authoring.md:31` makes compile/lint the safety net for graph correctness; overwrite detection belongs in that safety layer.
- 测试: accidental overwrite blocks/marks; intentional allow writes metadata and clears warning.
- Status: partial live.
- 归属: capability `graph-authoring`; `compile-lint`; region `canvas`.

### F3. Shared Conflict Presentation

- 机制: canvas popovers, editor conflict dialogs, and compile drawer should use the same conflict severity/copy vocabulary.
- 决策: one user mental model for "this would overwrite or invalidate something."
- 原话/来源: `01_workflows/03_compile.md:32` requires contextual error locations plus a drawer; overwrite conflicts should participate in that same display model.
- 测试: the same conflict appears in context and in the compile drawer with a copyable detail.
- Status: target-design.
- 归属: regions `canvas`, `editor`, `center-action-bar`; capabilities `compile-lint`, `file-editing`.

## 3. 接口契约
- File conflicts: expected hash mismatch returns local, remote, and a resolution action.
- Data-flow conflicts: engine/canvas identifies an output overwrite and requires explicit allow metadata.
- UI regions: `canvas` renders node/edge conflicts; `editor` resolves file conflicts; `center-action-bar`/drawer lists compile conflicts.
- Platform links: `native-fs` for write conflict authority, `engine` for graph semantic conflicts.

## 4. 设计决策基础（PM 原话）
- "允许覆盖写"开关落在**消费/下游节点**(冲突在"谁要覆盖写入"那侧更直观)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| CONFLICT_OVERWRITE-1 | 冲突呈现 | 单元 `conflict-overwrite-resolution`；**为什么**：canvas/editor/compile 三处冲突要一套统一分类，不能各报各的 |
| CONFLICT_OVERWRITE-2 | 顺序覆盖 | 单元 `conflict-overwrite-resolution`；**为什么**：顺序覆盖是前端 opt-in 警告，引擎 compile 才是数据流非法的持久权威 |
| CONFLICT_OVERWRITE-3 | 保存冲突 | 单元 `conflict-overwrite-resolution`；**为什么**：expected-hash 乐观并发，冲突要给 use-remote/overwrite 明确选项、不静默覆盖 |

## 6. 测试关键点
1. 冲突呈现: baseline 现状为 文件冲突与顺序覆盖是两条 UI 路径 ⚠️；目标为 共享一个冲突面：diff/use-remote/keep-local/allow overwrite 语义清楚。
2. 顺序覆盖: baseline 现状为 可标红并写 `allow_sequential_overwrite`；目标为 不得静默覆盖；允许后写入显式标记。
3. 保存冲突: baseline 现状为 409 payload 传给 Workspace；目标为 冲突决策后按同一路径重试/取消。

## 7. 涉及 region / platform
`canvas` · `editor` · `file-editing`

## 8. gaps / 报警
- 🚨 冲突呈现: 文件冲突与顺序覆盖是两条 UI 路径 ⚠️；目标 共享一个冲突面：diff/use-remote/keep-local/allow overwrite 语义清楚。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `canvas` · `editor` · `file-editing`
