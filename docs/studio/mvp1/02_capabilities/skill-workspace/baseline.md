---
module: 02_capabilities/skill-workspace
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；Welcome 仍读 `/skills` 注册表聚合，import 仍要求 GRAPH/SKILL 门禁；MVP1 IDE-folder 模型未落 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/welcome/WelcomePage.tsx:WelcomePage · apps/studio/frontend/src/hooks/useRecentSkills.ts:useRecentSkills · apps/studio/backend/app/services/skills.py:create_new_skill · apps/studio/backend/app/services/skills.py:list_skill_summaries · apps/studio/tauri/src/lib.rs:open_in_cursor
units: [workspace-open-folder-mru, subgraph-path-inline-drilldown]
---

# skill-workspace — Baseline（当下代码实现逻辑）

> **Scope**: Open Folder/MRU/Remove、创建/导入 skill、进入/退出 workspace 与子图 workspace membership。
> **现状一句话**: Welcome 仍读 `/skills` 注册表聚合，import 仍要求 GRAPH/SKILL 门禁；MVP1 IDE-folder 模型未落 ⚠️。

## UI/UX
Open Folder/MRU/Remove、创建/导入 skill、进入/退出 workspace 与子图 workspace membership。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Welcome data | Home reads the skills list and recent skills, then sorts visible skills by MRU. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:WelcomePage（L231）`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:visibleSkills（L244）` |
| Recent open | Opening a skill records it in localStorage-backed MRU before entering the workspace. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:openSkill（L246）`, `apps/studio/frontend/src/hooks/useRecentSkills.ts:useRecentSkills（L16）` |
| Folder picker | Create/import flows use a directory picker helper; browser fallback cannot really pick a folder. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:chooseNewSkillParentDirectory（L258）`, `apps/studio/frontend/src/lib/tauri.ts:selectSkillDirectory（L64）` |
| Create skill | New skill posts to `/skills`, then opens the created skill. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:submitNewSkill（L288）`, `apps/studio/backend/app/routers/skills.py:list_skills（L81）` |
| Import existing | Import posts name/path to `/skills`; backend rejects folders missing `GRAPH.md` and `SKILL.md`. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:importSkillDirectory（L310）`, `apps/studio/backend/app/services/skills.py:create_new_skill（L512）` |
| Delete | The UI offers delete; backend unregisters rather than recursively deleting the skill directory. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:deleteSkill（L274）`, `apps/studio/backend/app/services/skills.py:delete_skill（L436）` |
| Workspace enter/exit | `Workspace` resets panels and copilot when no skill is active; opening a skill defaults to Assets + Copilot. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentSkillId（L44）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:handleHome（L439）` |
| Nested navigation | Subgraph-like navigation is tracked in a local `navStack`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:pushNavSkill（L301）` |
| Native reveal | Tauri exposes reveal/open folder primitives already. | `apps/studio/tauri/src/lib.rs:select_directory（L90）`, `apps/studio/tauri/src/lib.rs:candidate（L129）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Create skill | New skill posts to `/skills`, then opens the created skill. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:submitNewSkill（L288）`, `apps/studio/backend/app/routers/skills.py:list_skills（L81）` |
| Import existing | Import posts name/path to `/skills`; backend rejects folders missing `GRAPH.md` and `SKILL.md`. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:importSkillDirectory（L310）`, `apps/studio/backend/app/services/skills.py:create_new_skill（L512）` |
| Delete | The UI offers delete; backend unregisters rather than recursively deleting the skill directory. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:deleteSkill（L274）`, `apps/studio/backend/app/services/skills.py:delete_skill（L436）` |
| Backend list model | Skill list merges registry, public paths, workspace paths, and metadata; this conflicts with the MVP1 no-registry IDE model. | `apps/studio/backend/app/services/skills.py:list_skill_summaries（L183）` |
| Native reveal | Tauri exposes reveal/open folder primitives already. | `apps/studio/tauri/src/lib.rs:select_directory（L90）`, `apps/studio/tauri/src/lib.rs:candidate（L129）` |

## 当前边界（skill-workspace 现在不是什么）
- 不拥有本地写者；落盘归 `native-fs`。
- 不复制 engine resolver/path 规则，只引用。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| Open Folder | Home 读 `/skills` 注册表/聚合 ⚠️ | 直接打开任意文件夹，MRU/Remove 不依赖注册表 |
| Import gate | backend 要求 `GRAPH.md` + `SKILL.md` ⚠️ | import/open 不因缺根文档阻塞 |
| 子图 membership | 旧 local path 口径残留 ⚠️ | 按 engine 绝对 `path` 判断同 workspace membership |
> **验"是否按目标改了"**：1. Open Folder；2. Import gate；3. 子图 membership。

## 读代码主路径提示
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:WelcomePage` → `apps/studio/frontend/src/hooks/useRecentSkills.ts:useRecentSkills` → `apps/studio/backend/app/services/skills.py:create_new_skill` → `apps/studio/backend/app/services/skills.py:list_skill_summaries` → `apps/studio/tauri/src/lib.rs:open_in_cursor`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-skill-workspace)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `welcome` · `native-fs` · `graph-authoring` · `assets`
