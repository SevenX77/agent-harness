---
module: 03_regions/welcome
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；Welcome 仍从 `/skills` 注册表聚合，import 仍走 backend 门禁；MVP1 open-folder IDE 模型未落 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/welcome/WelcomePage.tsx:WelcomePage · apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:NewSkillDialog · apps/studio/frontend/src/lib/tauri.ts:selectSkillDirectory · apps/studio/backend/app/services/skills.py:create_new_skill · apps/studio/backend/app/services/skills.py:list_skill_summaries
units: [workspace-open-folder-mru]
---

# welcome — Baseline（当下代码实现逻辑）

> **Scope**: Welcome/Home region：最近工作区 grid、Open/Import Folder、Create Skill、Reveal 与 Remove/Unregister。
> **现状一句话**: Welcome 仍从 `/skills` 注册表聚合，import 仍走 backend 门禁；MVP1 open-folder IDE 模型未落 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Welcome state | Welcome reads skill list and recent skills, then sorts visible cards by recent use. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:WelcomePage（L231）`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:visibleSkills（L244）` |
| Open card | Opening a skill remembers it and calls the parent `onSelectSkill`. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:openSkill（L246）` |
| New skill | New skill dialog posts to `/skills` with selected parent directory and opens the result. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:submitNewSkill（L288）`, `apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:currentParentDirectory（L39）` |
| Import skill | Import uses directory picker then posts path/name to `/skills`. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:importSkillDirectory（L310）`, `apps/studio/frontend/src/lib/tauri.ts:selectSkillDirectory（L64）` |
| Reveal/delete | Card menu can reveal in file manager or delete/unregister. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:handleReveal（L270）`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:deleteSkill（L274）` |
| Error/empty state | Welcome renders list error and empty state. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:existingSkillId（L392）`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:existingSkillId（L524）` |
| Backend import gate | Backend import rejects missing `GRAPH.md` and `SKILL.md`. | `apps/studio/backend/app/services/skills.py:create_new_skill（L512）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Welcome state | Welcome reads skill list and recent skills, then sorts visible cards by recent use. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:WelcomePage（L231）`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:visibleSkills（L244）` |
| Open card | Opening a skill remembers it and calls the parent `onSelectSkill`. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:openSkill（L246）` |
| New skill | New skill dialog posts to `/skills` with selected parent directory and opens the result. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:submitNewSkill（L288）`, `apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:currentParentDirectory（L39）` |
| Import skill | Import uses directory picker then posts path/name to `/skills`. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:importSkillDirectory（L310）`, `apps/studio/frontend/src/lib/tauri.ts:selectSkillDirectory（L64）` |
| Reveal/delete | Card menu can reveal in file manager or delete/unregister. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:handleReveal（L270）`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:deleteSkill（L274）` |
| Error/empty state | Welcome renders list error and empty state. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:existingSkillId（L392）`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:existingSkillId（L524）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Backend import gate | Backend import rejects missing `GRAPH.md` and `SKILL.md`. | `apps/studio/backend/app/services/skills.py:create_new_skill（L512）` |

## 当前边界（welcome 现在不是什么）
- 不拥有 workspace 业务规则；owner 是 `skill-workspace`。
- 不显示 copilot；copilot 随 skill shell 出现。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 数据源 | Welcome 读 `/skills` 注册表列表 ⚠️ | Home 以本地文件夹/MRU 为主，不依赖注册表聚合 |
| import gate | 后端缺 GRAPH/SKILL 就拒 ⚠️ | Open/Import 任意文件夹，不因根文档缺失阻塞 |
| Remove | delete/unregister 旧语义仍在 | Remove from Studio 只移出 MRU/注册痕迹，不删目录 |
> **验"是否按目标改了"**：1. 数据源；2. import gate；3. Remove。

## 读代码主路径提示
`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:WelcomePage` → `apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:NewSkillDialog` → `apps/studio/frontend/src/lib/tauri.ts:selectSkillDirectory` → `apps/studio/backend/app/services/skills.py:create_new_skill` → `apps/studio/backend/app/services/skills.py:list_skill_summaries`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-welcome)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `skill-workspace` · `native-fs` · `shell-layout`
