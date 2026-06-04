# welcome MVP1 Alignment

## 定义

`welcome` is the Home region for starting or switching local workspace work: Recent skills, open/import folder, create new skill, reveal, delete/unregister, and loop return after save/publish.

Source workflow basis: `01_workflows/01_init.md:8`, `01_workflows/01_init.md:16`, `01_workflows/06_eval.md:9`.

## 接口契约

- Props: `onSelectSkill(skillId)` enters `Workspace`.
- Uses local/native directory picker for create/import.
- Reads skill summaries and recent skills; writes MRU on open.
- Capability links: `skill-workspace`, `publish`.
- Platform link: `native-fs`.

## F1. Recent Workspace Grid

- 机制: show recent/local skills as cards with health/status hints and open actions.
- 决策: Home is the workspace switcher, not a marketing landing page.
- 原话/来源: `01_workflows/01_init.md:8` defines Home/workspace model; `01_workflows/01_init.md:35` locks IDE/workspace model.
- 测试: recent sort persists; no skill state leaks after switching from another workspace.
- Status: live.
- 归属: region `welcome`; capability `skill-workspace`.

## F2. Open Or Import Folder

- 机制: pick a local folder, register it as current workspace, and open it even if compile later reports errors.
- 决策: import should not block on file shape.
- 原话/来源: `01_workflows/01_init.md:38` records the PM decision to let compile/copilot normalize bad folders.
- 测试: non-standard folder opens into repair state; invalid folder is not rejected before Workspace.
- Status: target-design.
- 归属: region `welcome`; capability `skill-workspace`; platform `native-fs`.

## F3. Create New Skill

- 机制: choose parent folder, fill name, scaffold skill, enter Workspace.
- 决策: creation is a Home action; detailed graph filling begins after entering.
- 原话/来源: `01_workflows/01_init.md:16` lists Home create/open atom actions.
- 测试: cancel keeps user on Home; create success opens new skill and adds to Recent.
- Status: live with scaffold drift risk.
- 归属: region `welcome`; capability `skill-workspace`.

## F4. Reveal And Delete/Unregister

- 机制: card menu reveals folder or removes the skill from Studio's list.
- 决策: local workspace actions should be explicit and non-surprising.
- 原话/来源: `01_workflows/01_init.md:16` includes local workspace management in Home actions.
- 测试: reveal calls native command; delete/unregister does not silently remove disk contents unless PM later chooses destructive delete.
- Status: live.
- 归属: region `welcome`; platform `native-fs`.

## 待 PM 补 gap

- Final copy: "Import skill" versus "Open folder".
- Whether card delete should say "Remove from Studio" to avoid implying disk deletion.
