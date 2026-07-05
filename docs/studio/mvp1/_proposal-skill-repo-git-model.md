---
doc: proposal
title: Skill 存储与身份模型 — 从"技能库"到"一 skill 一 git 仓"
status: proposed（变更提案，不入哈希锁；待 owner 评审后决定正式并入方式）
date: 2026-07-03
supersedes-drift-in:
  - 02_capabilities/skill-workspace（workspace-open-folder-mru：no-registry IDE 模型）
  - 03_regions/local-history（local-history-snapshot：snapshot 来源）
aligns_with:
  - docs/engine/mvp1/02-mechanism/02-resolver/mvp1-alignment.md（RS1/RS2：删 registry、path 直接解析）
  - docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md（D3：核心 runtime 只吃 ArtifactRef/path）
binds_code:
  - apps/studio/backend/app/core/config.py:64（SKILLS_DIR 解析链待删；repo/skills 已移除）
  - apps/studio/backend/app/services/git_local.py（per-skill git，L1，已实现）
  - apps/studio/backend/app/services/git_collab.py（Gitea 协作，L2，已实现）
---

# Skill 存储与身份模型 — 从"技能库"到"一 skill 一 git 仓"（设计变更提案）

## 0. 这份文档是什么（治理说明，先读）

- **它是 `status: proposed` 的变更提案，不是 FROZEN 单元，不入哈希锁**（不受
  `test_doc_hash_lock.py` / `_audited-ready-hashes.json` 约束）。
- **它填补的是一个设计真空**：`DESIGN_UNITS_INDEX.md` 里**没有**任何 owner 单元
  描述"skill 的物理存储 = 独立 git 仓 / 身份 / L1 本地版本 / L2 Gitea 协作"。
  代码（`git_local.py` = L1、`git_collab.py` = L2 Gitea）已经写在前面，设计单元
  体系没跟上；相关目标只零散散落在 `workspace-open-folder-mru`（no-registry）和
  engine 的 no-registry 契约里，没有一个连贯的底座单元。
- **它不直接改任何 FROZEN 单元**。真正要落进 `skill-workspace/mvp1-alignment.md`、
  `local-history/mvp1-alignment.md` 的内容，须 owner 批准后走 exemption / 同步哈希
  底账；本提案是那一步的依据。正式并入建议见 §7。

## 1. 一句话目标

**一个 skill = 一个独立 git 仓。** Studio 运行时只认「**当前 skill 的绝对路径 +
它所有 subgraph 的路径**」；**不存在"技能库 / 中心注册表 / SKILLS_DIR"这个概念**；
唯一保留的全局路径是「**新建 skill 的默认落点**」（现 `DEFAULT_SKILLS_ROOT`）。
版本历史、协作、发布都由每个 skill 自己的 git 仓（L1 本地 + L2 Gitea）承载。

## 2. 设计依据 —— 这不是新发明，是回归"早已写定、代码没落地"的目标

| 主张 | 权威依据（文件:行号 + 引文） |
|---|---|
| 无 registry、path 直接解析 | `docs/engine/mvp1/02-mechanism/02-resolver/baseline.md:48`：mvp1 目标"子图**绝对 `path`** 直接解析，删 registry/id/dotted-id/多命中（RS1）"；`:49` resolver"只剩**边界校验**（RS2）" |
| 核心 runtime 不吃源码路径/库，只吃 path→artifact | `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md:13`：Engine"**不能把源码路径作为核心 runtime 输入**"、Studio"**不能绕过 compile 直接跑源码**"；`:23`（D3）"核心 runtime 只吃 `ArtifactRef`，源码入口必须先 compile 到 ephemeral artifact" |
| Studio = IDE、不是注册表浏览器 | `02_capabilities/skill-workspace/mvp1-alignment.md:23`："**Studio should feel like an IDE, not a registry browser**"（来源 `01_workflows/01_init.md:35` 锁 IDE/workspace 模型、`:36` rejects registry-first） |
| skill/subgraph 身份是 path，不是 registry id | `02_capabilities/skill-workspace/mvp1-alignment.md:50`："**subgraph identity is a path, not a registry id**" |
| 现状代码 = 已认定的 drift | `02_capabilities/skill-workspace/baseline.md:37`：`list_skill_summaries` "merges **registry, public paths, workspace paths** … **this conflicts with the MVP1 no-registry IDE model**"；同档 frontmatter："**MVP1 IDE-folder 模型未落 ⚠️**" |

**结论：** "去技能库、path 定位、无中心索引"是 engine 与 studio 设计源**双料写定**的
MVP1 目标，当前代码是 drift。本提案只是把它讲成一个连贯的存储/身份模型 + 落地清单。

## 3. 现状（as-is）与 drift 集群

### 3.1 SKILLS_DIR = 运行时"技能库根"（要删的核心）
- `apps/studio/backend/app/core/config.py:64` `SKILLS_DIR = default_skills_dir(RESOURCE_DIR)`
  → `paths.py:56` `resource_dir / "skills"`；`RESOURCE_DIR` 缺省 = `REPO_ROOT`
  （`config.py:12/60`、`paths.py:14`）→ **dev 下 `SKILLS_DIR` = 仓库根 `skills/`**。
- 被 ~15 处运行时服务当"可枚举/可按 id 索引的技能库"用：`skill_resolver.py:36`、
  `core/adapters/engine.py:182`、`skills.py`（`751/850/898/932/987/1017/1056/1456`）、
  `golden_headless.py:606-607`、`file_watcher.py:338`、`terminal_manager.py:215-228`。
  它们构成 `indexed → workspace → **bundled SKILLS_DIR**` 的解析链回退。

### 3.2 bundled skill 赖在主仓子目录、无独立 `.git`（截图现象的根因）
- PR-C 决策（2026-07-05）：主仓不再跟踪 `skills/`。这些示例 skill 的机器本地副本
  放在仓库外，由用户按需要打开；仓库不记录机器专属落点，也不再把 bundled skill 当
  运行时输入。
- PR-C 前，`skills/text-segmentation`、`skills/story-deconstruction`、`skills/event-extraction`
  … 共 16 个技能目录，是**主开发仓 `agent-harness` 的 tracked 内容**（271 个文件），
  **没有各自的 `.git`**。
- 后果：`HistoryPanel` → `git_local.list_history(skill_dir)` → `git log`（cwd=skill_dir）。
  skill 目录没有自己的 `.git`，**git 从 cwd 向上冒泡找到主仓的 `.git`** → 读到的是
  主开发仓的提交历史（`docs(strategy)/fix(studio)…`），而不是 skill 自己的历史。
  实测：对 `skills/text-segmentation` 跑 `git log` 返回的 sha 与主仓 HEAD 完全一致。

### 3.3 registry 聚合的列表模型
- `apps/studio/backend/app/services/skills.py:list_skill_summaries` 合并
  registry + public paths + workspace paths（`skill-workspace/baseline.md:37` 已标 ⚠️）。
- import 门禁：`create_new_skill`（`skills.py:512`）要求 `GRAPH.md` + `SKILL.md`
  才接受文件夹（违 D2/D11，见 `skill-workspace` gaps）。

### 3.4 对照：per-skill git + Gitea 协作**代码已实现，却因 skill 未独立化而空转**
- **L1 本地**（`git_local.py`）：`GitLocalService` 明确"**scoped to one skill
  repository**"（`:90`）；`initialize_skill_repository(skill_dir)`（`:531`）对每个
  skill 目录 `git init` + 写 `.gitignore` + 设 local user + commit `initial-skill`；
  已有 init/add/commit/log/`list_history`/`reset_hard`/`revert_to`/`remote_add`/
  `remote_set_url`/`push`/`pull` 全套原语。
- **L2 Gitea**（`git_collab.py`）：`GiteaClient`（REST：`create_repo`/`create_branch`/
  `create_pull_request` + token 认证）；`GitCollaborateService.save_to_team`（push，
  403 protected 自动 fallback dev 分支 + PR）/`sync_from_team`（`pull --ff-only`，冲突
  报 requires_review）/`submit_for_review`；`_ensure_origin` 把 origin 设成
  `{gitea_host}/{owner}/{repo}.git`。已接到 `routers/skills.py` + 前端 Settings
  （`useSkillSync.ts`、`GeneralTab.tsx`）。
- **空转原因**：bundled skill 从没走过 `initialize_skill_repository`（它们是直接
  check-in 进主仓的），没有独立 `.git` → L1 history 冒泡主仓、L2 push 的会是主仓。

## 4. 目标（to-be）

1. **物理存储**：每个 skill 是**独立 git 仓**（`git init` per skill，L1）。
   `initialize_skill_repository` 已实现，缺的是"让所有 skill 都走它"。
2. **定位**：Studio 编排层持有「当前打开 skill 的**绝对路径**」；后端只在该路径 +
   其 subgraph 路径（相对父 skill 根解析，engine 契约）上操作。**删除 `SKILLS_DIR`
   与解析链的库回退**；不引入任何中心索引。
3. **保留**：`DEFAULT_SKILLS_ROOT` = 新建 skill 的默认落点（用户可在 Settings 改），
   这是**唯一**该保留的全局路径概念，与"技能库"无关。
4. **历史**：`local-history` 读的就是 skill 自己那个独立仓 → skill 独立化后，截图
   那个"history 是开发仓的"问题自动消失。
5. **身份**：不新增 uuid / manifest id。**路径负责定位**；git `root-commit` SHA /
   `origin` URL 负责判断"是不是同一个仓"。**不依赖中心索引**。
   （git 本身只会向上找 `.git`，所以根仓必须先独立；同一性锚点使用 root commit /
   origin，而不是应用层另造 id。）
6. **协作**：L2 = Gitea，每个 skill 对应一个 Gitea 仓（`GiteaClient`/
   `GitCollaborateService` 已在）。
7. **"最近打开列表"**：退化为纯 UI 的**路径 MRU 清单**（localStorage），不是运行时
   的库/索引。

## 5. 改造清单（分步 · 标落点 · engine 不动）

> **前置结论：engine 无需改**。engine 已是"路径优先"：`compile_skill(root: Path)`、
> `SkillResolverProtocol.resolve_skill(skill_id)->Path`、subgraph 相对父 skill 路径
> 解析。债全在 studio 后端。

| Step | 动作 | 落点 | 备注 |
|---|---|---|---|
| 1 | **skill 独立化**：新建/导入一律走 `initialize_skill_repository`（git init）；主仓移除 tracked `skills/`，示例 skill 作为仓库外本地目录打开 | `git_local.py`（已实现）+ 新建/导入流程 + repo root | 不独立化，L1/L2 全空转；PR-C 已移除 tracked `skills/` |
| 2 | **删 SKILLS_DIR 解析链**：删 `config.SKILLS_DIR` + `default_skills_dir`，解析改为"当前 skill 绝对路径"驱动 | `config.py:64`、`skill_resolver.py:36`、`engine.py:182`、`skills.py`(751/850/898/932/987/1017/1056/1456)、`golden_headless.py:606`、`terminal_manager.py:215-228` | 保留 `DEFAULT_SKILLS_ROOT` |
| 3 | **去 registry 列表**：`list_skill_summaries` 去 registry/public merge，改路径 MRU | `skills.py:183`、`WelcomePage.tsx` | 对齐 `workspace-open-folder-mru` |
| 4 | **import 去门禁**：不因缺 `GRAPH/SKILL` 阻塞打开，进 repair 态 | `create_new_skill`（`skills.py:512`） | 对齐 D2/D11 |
| 5 | **history 读独立仓**：确认 `list_history` 作用于独立仓；补测试"skill history 不含主仓提交" | `git_local.list_history`、`HistoryPanel.tsx` | 独立化后自然成立，测试锁死 |
| 6 | **身份收敛**：不引入 uuid / manifest id；定位用路径，同一性用 git root-commit / origin | `git_local.py` / 后续协作 UI | 不触碰 engine skill-syntax schema |
| 7 | **Gitea 打磨**：token 存储/发放、owner/repo 命名规则、首次 `create_repo` 时机、冲突 UX | `git_collab.py`、Settings、`useSkillSync.ts` | 骨架已在，属接线打磨 |

`file_watcher.py:338` 的 watch roots 与 `terminal_manager` 的访问边界（现用 SKILLS_DIR
兜底）随 Step 2 一并改为"当前 workspace 路径 + DEFAULT_SKILLS_ROOT"驱动。

## 6. PM 已拍板 / owner 待正式化

- **(a) 身份不用 uuid。** 路径负责打开和定位；git `root-commit` / `origin` 负责判断
  同一性。不改 `GRAPH.md` / `SKILL.md` schema，不为此引入 manifest id。
- **(b) bundled 示例技能退出主仓。** tracked `skills/` 从主仓删除；机器本地副本放在
  仓库外，打开后按 PR-A 的自动 git init 机制变成独立仓。仓库只保留空工作区 + 新建
  skill 的能力，不再把示例目录当运行时库。
- **(c) `DEFAULT_SKILLS_ROOT` 保留。** 它只是"新建 skill 的默认落点"，不是技能库 /
  中心索引。
- **(d) L2 Gitea 后置。** 先把 L1 本地独立仓跑稳，再继续 Gitea 协作打磨。

## 7. 正式并入建议（治理路径）

本提案通过评审后，建议按 `DESIGN_UNITS_INDEX.md` 的锁流程正式并入：

1. **新增一个 owner 单元**（暂名 `skill-repo-git-identity`）承载"skill 物理存储 =
   独立 git 仓 / 身份 / L1-L2"这个当前真空的切面；owner 待定（skill-workspace 或
   新平台单元）。→ 需 owner 评审 + 同步 `_design-unit-lock-snapshot.json`。
2. **更新两个 FROZEN 单元**（走 exemption / 同步哈希底账）：
   - `skill-workspace/mvp1-alignment.md`：补"skill 存储层 = 独立 git 仓"，把 §3 的
     drift 集群落进其 baseline 差异表。
   - `local-history/mvp1-alignment.md`：显式写"snapshot 来自 skill **自己的独立
     git 仓**；bundled skill 未独立化导致冒泡主仓 = drift"。
3. `binds_code` 的 ⚠️ 逐条对齐到各 baseline「测试锚点」差异表。

> 在 owner 完成上述并入前，本文件是 skill 存储/身份/git 模型的**唯一草案 SSOT**；
> 落地实施（§5）应引用本文件，并按 owner 拍板的 §6 结论推进。
