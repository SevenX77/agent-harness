---
module: 03_regions/welcome
doc: mvp1-alignment
status: drafted（Welcome 仍从 `/skills` 注册表聚合，import 仍走 backend 门禁；MVP1 open-folder IDE 模型未落 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [workspace-open-folder-mru]
aligns_with: 01_workflows/01_init.md（workspace open / MRU）
---

# welcome — MVP1 Alignment

> **Tier**: region | **Owns**: `workspace-open-folder-mru` 的 Home UI 切面 | **现状**: Welcome 仍从 `/skills` 注册表聚合，import 仍走 backend 门禁；MVP1 open-folder IDE 模型未落 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `skill-workspace` · `native-fs` · `shell-layout`

## 1. 定义
`welcome` is the Home region for starting or switching local workspace work: Recent skills, open/import folder, create new skill, reveal, delete/unregister, and loop return after save/publish.

Source workflow basis: `01_workflows/01_init.md:8`, `01_workflows/01_init.md:16`, `01_workflows/06_eval.md:9`.

## 2. 数据流 / 机制（设计细节）
### F1. Recent Workspace Grid

- 机制: show recent/local skills as cards with health/status hints and open actions.
- 决策: Home is the workspace switcher, not a marketing landing page.
- 原话/来源: `01_workflows/01_init.md:8` defines Home/workspace model; `01_workflows/01_init.md:35` locks IDE/workspace model.
- 测试: recent sort persists; no skill state leaks after switching from another workspace.
- Status: live.
- 归属: region `welcome`; capability `skill-workspace`.

### F2. Open Or Import Folder

- 机制: pick a local folder, register it as current workspace, and open it even if compile later reports errors.
- 决策: import should not block on file shape.
- 原话/来源: `01_workflows/01_init.md:38` records the PM decision to let compile/copilot normalize bad folders.
- 测试: non-standard folder opens into repair state; invalid folder is not rejected before Workspace.
- Status: target-design.
- 归属: region `welcome`; capability `skill-workspace`; platform `native-fs`.

### F3. Create New Skill

- 机制: choose parent folder, fill name, scaffold skill, enter Workspace.
- 决策: creation is a Home action; detailed graph filling begins after entering.
- 原话/来源: `01_workflows/01_init.md:16` lists Home create/open atom actions.
- 测试: cancel keeps user on Home; create success opens new skill and adds to Recent.
- Status: live with scaffold drift risk.
- 归属: region `welcome`; capability `skill-workspace`.

### F4. Reveal And Delete/Unregister

- 机制: card menu reveals folder or removes the skill from Studio's list.
- 决策: local workspace actions should be explicit and non-surprising.
- 原话/来源: `01_workflows/01_init.md:16` includes local workspace management in Home actions.
- 测试: reveal calls native command; delete/unregister does not silently remove disk contents unless PM later chooses destructive delete.
- Status: live.
- 归属: region `welcome`; platform `native-fs`.

## 3. 接口契约
- Props: `onSelectSkill(skillId)` enters `Workspace`.
- Uses local/native directory picker for create/import.
- Reads skill summaries and recent skills; writes MRU on open.
- Capability links: `skill-workspace`, `publish`.
- Platform link: `native-fs`.

## 4. 设计决策基础（PM 原话）
- 入口动词 = **"Open folder"**(非 "Import skill"):贴 IDE「打开文件夹」心智 + "技能即文件夹"。
- 卡片删除文案 = **"Remove from Studio"**:明确只摘出 Studio 列表、不删磁盘,避免误以为删盘。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| WELCOME-1 | 数据源 | 对齐 `workspace-open-folder-mru` 设计单元，保证 region 切面能被测试回扣 |
| WELCOME-2 | import gate | 对齐 `workspace-open-folder-mru` 设计单元，保证 region 切面能被测试回扣 |
| WELCOME-3 | Remove | 对齐 `workspace-open-folder-mru` 设计单元，保证 region 切面能被测试回扣 |

## 6. 测试关键点
1. 数据源: baseline 现状为 Welcome 读 `/skills` 注册表列表 ⚠️；目标为 Home 以本地文件夹/MRU 为主，不依赖注册表聚合。
2. import gate: baseline 现状为 后端缺 GRAPH/SKILL 就拒 ⚠️；目标为 Open/Import 任意文件夹，不因根文档缺失阻塞。
3. Remove: baseline 现状为 delete/unregister 旧语义仍在；目标为 Remove from Studio 只移出 MRU/注册痕迹，不删目录。

## 7. 涉及 region / platform
`skill-workspace` · `native-fs` · `shell-layout`

## 8. gaps / 报警
- 🚨 数据源: Welcome 读 `/skills` 注册表列表 ⚠️；目标 Home 以本地文件夹/MRU 为主，不依赖注册表聚合。
- 🚨 import gate: 后端缺 GRAPH/SKILL 就拒 ⚠️；目标 Open/Import 任意文件夹，不因根文档缺失阻塞。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `skill-workspace` · `native-fs` · `shell-layout`
