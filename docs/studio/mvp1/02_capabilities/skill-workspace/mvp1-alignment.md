---
module: 02_capabilities/skill-workspace
doc: mvp1-alignment
status: FROZEN（Welcome 仍读 `/skills` 注册表聚合，import 仍要求 GRAPH/SKILL 门禁；MVP1 IDE-folder 模型未落 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [workspace-open-folder-mru, subgraph-path-inline-drilldown]
aligns_with: 01_workflows/01_init.md（open folder / MRU）· 01_workflows/02_authoring.md（subgraph workspace）
---

# skill-workspace — MVP1 Alignment

> **Tier**: capability | **Owns**: `workspace-open-folder-mru`（工作区/MRU/Remove）+ `subgraph-path-inline-drilldown` 的 workspace membership 切面 | **现状**: Welcome 仍读 `/skills` 注册表聚合，import 仍要求 GRAPH/SKILL 门禁；MVP1 IDE-folder 模型未落 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `welcome` · `native-fs` · `graph-authoring` · `assets`

## 1. 定义
`skill-workspace` owns the local Studio workspace journey: open a folder, keep recent work, create/import skills, navigate into subgraphs by path, and return to Home. It does not own graph editing fields; it owns the workspace boundary around those files.

Source workflow basis: `01_workflows/01_init.md:8`, `01_workflows/01_init.md:16`, `01_workflows/02_authoring.md:37`.

## 2. 数据流 / 机制（设计细节）
### F1. Open Existing Workspace

- 机制: Home opens a local folder, remembers it in recent skills, and enters the workspace shell.
- 决策: Studio should feel like an IDE, not a registry browser.
- 原话/来源: `01_workflows/01_init.md:35` records "锁 IDE/workspace 模型"; `01_workflows/01_init.md:36` rejects registry-first behavior for MVP1.
- 测试: selecting a folder opens the workspace; reopening from Recent works after app restart; missing sidecar does not blank the shell.
- Status: partial live. UI and MRU exist; registry-centered backend remains.
- 归属: capability `skill-workspace`; region `welcome`; platform `native-fs`.

### F2. Import Any Folder Without Blocking

- 机制: accept a picked folder into workspace state, then show compile/copilot repair opportunities if the contents are not a valid skill yet.
- 决策: import should optimize for getting the user into Studio, not for pre-validating every file shape.
- 原话/来源: `01_workflows/01_init.md:38` keeps the PM decision that import should not be blocked because compile and copilot can normalize the skill.
- 测试: importing a folder with no root docs still opens a repairable workspace; compile shows actionable errors rather than the import failing.
- Status: target-design. Current backend rejects missing root docs.
- 归属: capability `skill-workspace`; regions `welcome`, `assets`; platform `native-fs`.

### F3. Create New Skill

- 机制: pick a parent directory, create a skill scaffold, then open it immediately.
- 决策: new skill creation is a workspace action; generated starter files should match the current engine spec.
- 原话/来源: `01_workflows/01_init.md:16` lists Home creation as an atom action; `01_workflows/02_authoring.md:18` makes graph authoring the next journey.
- 测试: create succeeds in a writable directory; generated files compile or produce only intentional starter warnings.
- Status: live but stale scaffold risk.
- 归属: capability `skill-workspace`; platform `native-fs`; downstream `graph-authoring`.

### F4. Subgraph Path Workspace Membership

- 机制: subgraph references resolve by **绝对 path**(engine skill-syntax §2.1); if missing, Assets lets the user add that folder into the workspace.
- 决策: subgraph identity is a path, not a registry id.
- 原话/来源: `01_workflows/02_authoring.md:37` locks the subgraph path direction.
- 测试: a missing subgraph path is visible, actionable, and becomes resolved after adding the folder.
- Status: target-design. Current Assets panel has a fake registered-subgraph cache.
- 归属: capability `skill-workspace`; regions `assets`, `canvas`; platform `native-fs`.

### F5. Close And Return Home

- 机制: leaving a skill clears panels/copilot state and returns to Welcome without killing the local app shell.
- 决策: Home is the loop-closing point after save/publish, and also the workspace switcher.
- 原话/来源: `01_workflows/06_eval.md:9` sends the user back to Home after save/publish.
- 测试: Back Home clears selected node/edge/panel state; opening a different skill does not leak old copilot context.
- Status: live with a suspected copilot `skillId/currentSkillId` mismatch to watch.
- 归属: capability `skill-workspace`; region `shell-layout`; capability `copilot-assist`.

## 3. 接口契约
- Frontend: Welcome/Home selects a local directory or recent skill, then passes `skillId/currentSkillId` into `Workspace`.
- Native-fs target: local folder operations, MRU, reveal, and write orchestration should be Rust-owned.
- Backend sidecar: compile/copilot may repair or validate content after import, but should not be the first gate to opening a folder.
- Region links: `welcome`, `shell-layout`, `assets`.
- Platform links: `native-fs`, `state-engine`.

## 4. 设计决策基础（PM 原话）
- delete = **仅从 Studio 列表移除("Remove from Studio")、不删磁盘**;入口动词 = "Open folder"(非 "Import skill")。
- 打开**非标准技能文件夹**不在门口拦,进入后进 **repair 态**(由 compile/copilot 帮补齐)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| SKILL_WORKSPACE-1 | Open Folder | 单元 `workspace-open-folder-mru`；**为什么**：IDE 模型——打开任意文件夹即工作区，无聚合注册表(D1/D11) |
| SKILL_WORKSPACE-2 | Import gate | 单元 `workspace-open-folder-mru`；**为什么**：不卡导入校验，不合规交 compile+copilot 改成标准 skill(D2) |
| SKILL_WORKSPACE-3 | 子图 membership | 单元 `subgraph-path-inline-drilldown`（消费/引；owner 非 skill-workspace）；**为什么**：子图按 path 解析、随便放哪，copilot cwd 必须纳入子图 path(D7) |

## 6. 测试关键点
1. Open Folder: baseline 现状为 Home 读 `/skills` 注册表/聚合 ⚠️；目标为 直接打开任意文件夹，MRU/Remove 不依赖注册表。
2. Import gate: baseline 现状为 backend 要求 `GRAPH.md` + `SKILL.md` ⚠️；目标为 import/open 不因缺根文档阻塞。
3. 子图 membership: baseline 现状为 旧 local path 口径残留 ⚠️；目标为 按 engine 绝对 `path` 判断同 workspace membership。

## 7. 涉及 region / platform
`welcome` · `native-fs` · `graph-authoring` · `assets`

## 8. gaps / 报警
- 🚨 Open Folder: Home 读 `/skills` 注册表/聚合 ⚠️；目标 直接打开任意文件夹，MRU/Remove 不依赖注册表。
- 🚨 Import gate: backend 要求 `GRAPH.md` + `SKILL.md` ⚠️；目标 import/open 不因缺根文档阻塞。
- 🚨 子图 membership: 旧 local path 口径残留 ⚠️；目标 按 engine 绝对 `path` 判断同 workspace membership。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `welcome` · `native-fs` · `graph-authoring` · `assets`
