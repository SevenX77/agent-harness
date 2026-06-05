# skill-workspace MVP1 Alignment

## 定义

`skill-workspace` owns the local Studio workspace journey: open a folder, keep recent work, create/import skills, navigate into subgraphs by path, and return to Home. It does not own graph editing fields; it owns the workspace boundary around those files.

Source workflow basis: `01_workflows/01_init.md:8`, `01_workflows/01_init.md:16`, `01_workflows/02_authoring.md:37`.

## 接口契约

- Frontend: Welcome/Home selects a local directory or recent skill, then passes `skillId/currentSkillId` into `Workspace`.
- Native-fs target: local folder operations, MRU, reveal, and write orchestration should be Rust-owned.
- Backend sidecar: compile/copilot may repair or validate content after import, but should not be the first gate to opening a folder.
- Region links: `welcome`, `shell-layout`, `assets`.
- Platform links: `native-fs`, `state-engine`.

## F1. Open Existing Workspace

- 机制: Home opens a local folder, remembers it in recent skills, and enters the workspace shell.
- 决策: Studio should feel like an IDE, not a registry browser.
- 原话/来源: `01_workflows/01_init.md:35` records "锁 IDE/workspace 模型"; `01_workflows/01_init.md:36` rejects registry-first behavior for MVP1.
- 测试: selecting a folder opens the workspace; reopening from Recent works after app restart; missing sidecar does not blank the shell.
- Status: partial live. UI and MRU exist; registry-centered backend remains.
- 归属: capability `skill-workspace`; region `welcome`; platform `native-fs`.

## F2. Import Any Folder Without Blocking

- 机制: accept a picked folder into workspace state, then show compile/copilot repair opportunities if the contents are not a valid skill yet.
- 决策: import should optimize for getting the user into Studio, not for pre-validating every file shape.
- 原话/来源: `01_workflows/01_init.md:38` keeps the PM decision that import should not be blocked because compile and copilot can normalize the skill.
- 测试: importing a folder with no root docs still opens a repairable workspace; compile shows actionable errors rather than the import failing.
- Status: target-design. Current backend rejects missing root docs.
- 归属: capability `skill-workspace`; regions `welcome`, `assets`; platform `native-fs`.

## F3. Create New Skill

- 机制: pick a parent directory, create a skill scaffold, then open it immediately.
- 决策: new skill creation is a workspace action; generated starter files should match the current engine spec.
- 原话/来源: `01_workflows/01_init.md:16` lists Home creation as an atom action; `01_workflows/02_authoring.md:18` makes graph authoring the next journey.
- 测试: create succeeds in a writable directory; generated files compile or produce only intentional starter warnings.
- Status: live but stale scaffold risk.
- 归属: capability `skill-workspace`; platform `native-fs`; downstream `graph-authoring`.

## F4. Subgraph Path Workspace Membership

- 机制: subgraph references resolve by local path; if missing, Assets lets the user add that folder into the workspace.
- 决策: subgraph identity is a path, not a registry id.
- 原话/来源: `01_workflows/02_authoring.md:37` locks the subgraph path direction.
- 测试: a missing subgraph path is visible, actionable, and becomes resolved after adding the folder.
- Status: target-design. Current Assets panel has a fake registered-subgraph cache.
- 归属: capability `skill-workspace`; regions `assets`, `canvas`; platform `native-fs`.

## F5. Close And Return Home

- 机制: leaving a skill clears panels/copilot state and returns to Welcome without killing the local app shell.
- 决策: Home is the loop-closing point after save/publish, and also the workspace switcher.
- 原话/来源: `01_workflows/06_eval.md:9` sends the user back to Home after save/publish.
- 测试: Back Home clears selected node/edge/panel state; opening a different skill does not leak old copilot context.
- Status: live with a suspected copilot `skillId/currentSkillId` mismatch to watch.
- 归属: capability `skill-workspace`; region `shell-layout`; capability `copilot-assist`.

## 已决(PM 2026-06-04)

- delete = **仅从 Studio 列表移除("Remove from Studio")、不删磁盘**;入口动词 = "Open folder"(非 "Import skill")。
- 打开**非标准技能文件夹**不在门口拦,进入后进 **repair 态**(由 compile/copilot 帮补齐)。
