# conflict-overwrite MVP1 Alignment

## 定义

`conflict-overwrite` owns user-facing conflict decisions where Studio would otherwise silently lose intent: file save conflicts and graph/data-flow overwrite conflicts.

Source workflow basis: `01_workflows/02_authoring.md:18`, `01_workflows/03_compile.md:13`.

## 接口契约

- File conflicts: expected hash mismatch returns local, remote, and a resolution action.
- Data-flow conflicts: engine/canvas identifies an output overwrite and requires explicit allow metadata.
- UI regions: `canvas` renders node/edge conflicts; `editor` resolves file conflicts; `center-action-bar`/drawer lists compile conflicts.
- Platform links: `native-fs` for write conflict authority, `engine` for graph semantic conflicts.

## F1. Prevent Silent File Overwrite

- 机制: every save includes an expected hash; mismatch opens a conflict flow rather than replacing remote content.
- 决策: local editing should be forgiving but never silently destructive.
- 原话/来源: `01_workflows/02_authoring.md:31` keeps live lint/compile active while editing; this implies saves can race with validation or file-watch changes.
- 测试: stale editor save returns conflict; choosing remote replaces local; choosing diff shows both sides.
- Status: live.
- 归属: capability `file-editing`; capability `conflict-overwrite`; platform `native-fs`.

## F2. Detect Sequential Output Overwrite

- 机制: when later phases overwrite the same output key, Studio flags the downstream node and asks for explicit confirmation.
- 决策: overwrites are legal only when the author marks them intentional.
- 原话/来源: `01_workflows/02_authoring.md:31` makes compile/lint the safety net for graph correctness; overwrite detection belongs in that safety layer.
- 测试: accidental overwrite blocks/marks; intentional allow writes metadata and clears warning.
- Status: partial live.
- 归属: capability `graph-authoring`; `compile-lint`; region `canvas`.

## F3. Shared Conflict Presentation

- 机制: canvas popovers, editor conflict dialogs, and compile drawer should use the same conflict severity/copy vocabulary.
- 决策: one user mental model for "this would overwrite or invalidate something."
- 原话/来源: `01_workflows/03_compile.md:32` requires contextual error locations plus a drawer; overwrite conflicts should participate in that same display model.
- 测试: the same conflict appears in context and in the compile drawer with a copyable detail.
- Status: target-design.
- 归属: regions `canvas`, `editor`, `center-action-bar`; capabilities `compile-lint`, `file-editing`.

## 已决(PM 2026-06-04)

- "允许覆盖写"开关落在**消费/下游节点**(冲突在"谁要覆盖写入"那侧更直观)。
