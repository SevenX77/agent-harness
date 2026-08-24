---
role: workflow-record
---

# Node 1: 发现与初始化 (Discovery & Init)

> Tier: workflow · Owns: 进入 Studio + Home↔skill-workspace 强隔离切换的完整旅程 · 能力 `skill-workspace`(引用 `copilot-assist`)· 区域 `welcome` / `shell-layout` · 平台 `native-fs`(Rust) / `gateway`(sidecar)
> Status: ✅ PM 已确认(批次1:D1–D11 + R1/R2 + D-1-1/D-1-4)
> 设计权威: **D11 IDE/workspace 模型(锁)** + D1/D7/D10/D6 + INDEX §6;无专属 studio-feature spec。PM 决策原话就近留底于 §3。
> 本文 = 该节点**最终设计**(atom action 决策 + file:line 依据)。

## 1. 用户旅程目标
PM 如何进入 Studio、在「主页 Home」与「沉浸式 skill workspace」间切换。核心范式 = **强隔离 Home/Workspace + IDE/workspace 模型**(D11 锁):skill = 一个文件夹;Home = 打开文件夹 + Recent(MRU localStorage);**无聚合注册表**;一窗口专注一个 skill;子图按 path 解析(D7)。

## 2. atom action 决策表
> status 见 INDEX §4。**2026-08-24 模块二真机点验复核**:下表 status 与 file:line 依据已逐行按当前代码核实更新(改动明细见 §7 修订记录)。此前记录的「⚠️ 全局架构错配」——Home/后端仍是注册表模型(MetadataStore + `GET /skills` 聚合 + 自动发现 unregistered)与 D1/D11「无注册表」方向冲突、导致多条看似 live 的动作实为 stale——**核实后已不成立**:`GET /skills` 列表聚合端点已从后端路由整体移除(`apps/studio/backend/app/routers/skills.py` 现无任何裸 `@router.get("")`/list 路由,`apps/studio/backend/app/services/skills.py` 亦无 `list_skills`/`MetadataStore` 聚合函数),前端 `useSkills.ts:6-11` 的注释原样记载了这次退役("Only the per-skill DETAIL fetch remains. The old GET /skills LIST was retired…Design: Home = local MRU, no registry aggregation (D11 "无注册表")")。Home 现完全由 Rust native-fs MRU(`useRecentSkills.ts`)驱动,不再有列表级注册表聚合;下表因此多数动作由 stale-doc/stale-code 改判 live,真实剩余缺口见各行与 §6。

| 动作 | 最终决策 / status | 能力·区域 | 依据(file:line)+ 动机/FROZEN |
|---|---|---|---|
| 应用启动 gate(全屏 splash→ready 才渲染) | **live**:RuntimeGate 并未退役,而是演进为「壳/FS 立即渲染 + 非阻塞底部横幅」(D10)——冷启动显示"Connecting to backend…",失败态显示"Backend unavailable"+ Retry,从不遮蔽整个 UI;新增**有界自动重启**(1s/4s/16s,耗尽后停,靠手动 Retry 重开一轮),覆盖"sidecar 运行中途死掉"这一此前的空白(dead-sidecar-says-so) | skill-workspace · shell-layout | `App.tsx:19`(`<RuntimeGate>` 包裹 `<Workspace>`)/`RuntimeGate.tsx:31-33`(非阻塞横幅设计注释)`,34-65`(`RuntimeShell`)`,72-204`(`RuntimeGate`)`,77-123`(有界自动重启调度)`,159-164`(`useBackendDownSignal` 检测运行中掉线)/`runtime-gate-auto-restart.ts:26`(`AUTO_RESTART_DELAYS_MS=[1000,4000,16000]`;文件头注释自标"2026-08-24 dead-sidecar-says-so fix");D10 |
| 进入 Home 屏(`currentSkillId===null`→WelcomePage) | **live** | skill-workspace · welcome | `Workspace.tsx:3094-3103`(`currentSkillId === null` 分支渲染 `WelcomePage`;组件已迁至 `components/welcome/WelcomePage.tsx`);D11 强隔离落点 |
| Home 显示 Recent 列表(MRU 卡片) | **live**:Recent 完全由 Rust native-fs MRU 驱动,后端不参与;卡片极简(名+路径+时间,D-1-1),欢迎屏整体沿用 Cursor/VS Code 范式(R2) | skill-workspace · welcome | `useRecentSkills.ts:104-159`(`useRecentSkills` hook,读 Rust `recent_workspaces.json`)`,17-18`(`RECENT_CAP=10`)/`lib/tauri.ts:700,716,733`(`addRecentWorkspace`/`listRecentWorkspaces`/`removeRecentWorkspace` 均为 Rust invoke)/`WelcomePage.tsx:101-106,180-185`(卡片模型只取 absolutePath/displayName/identity/lastOpenedAt) |
| 打开一个 Recent skill(点卡片→进 workspace) | **live** | skill-workspace · welcome | `WelcomePage.tsx:203-222`(`openSkill`/`openWorkspace`)`,382-392`(卡片 `onClick`/`onKeyDown`);Cursor Open Recent 同款 |
| 新建 Skill(填名/选父目录→建文件夹+脚手架+git init→进 workspace) | **live**:D12 写盘已全量迁 Rust,D-1-4 脚手架(logic→agent 模板)已生效 | skill-workspace · welcome | `WelcomePage.tsx:252-281`(`submitNewSkill` 调 `createSkillWorkspace`)/`NewSkillDialog.tsx:9-38,46,107`(表单壳,委托 `onSubmit`)/`lib/tauri.ts:578-589`(`createSkillWorkspace` invoke `create_skill_workspace`)/`native_fs.rs:1619-1664`(`create_skill_workspace_impl`:建目录+写脚手架+`git init`+写 `skill_index`)`,1290-1298`(`scaffold_files_for`:`GRAPH.md` `schema_version: "v0.3.0"`、单 `init` agent phase)`,1465-1481`(`initialize_skill_repository`:写 `.gitignore`+`git init`+`git add -A`+提交 `initial-skill`)。**FROZEN/D12 已兑现**:无 Python `POST /skills` 参与(该端点的孤儿嫌疑见 §6) |
| 新建对话框选父目录(OS 目录选择器;默认来自 `default_skills_directory`) | **live** | skill-workspace · welcome | `WelcomePage.tsx:63-74`(`defaultSkillsDirectory`)`,231-241`(`chooseNewSkillParentDirectory`)/`lib/tauri.ts:513-534`(`selectSkillDirectory`) |
| 打开现有文件夹(选任意本地文件夹→进 workspace) | **live**:D2 校验门已删(不卡导入,不合规交 compile+copilot),D12 写路径已迁 Rust,文案已是"Open folder" | skill-workspace · welcome | `WelcomePage.tsx:286-299`(`openFolder`)`,187-216`(`resolveBackendSkillIdForWorkspace`/`openSkill` 调 `openSkillWorkspace`)/`lib/tauri.ts:596-603`(`openSkillWorkspace` invoke `open_skill_workspace`)/`native_fs.rs:1666-1688`(`open_skill_workspace_impl`:仅 OS 级存在性/目录检查,不校验 manifest,skill id 由路径推导)。**FROZEN/D2 已兑现**:后端 `services/skills.py:1225-1245` 的 import 分支自身也已实现同一条 D2(行内注释直接引用本文档),但前端 D12 迁移后已不再调用它(孤儿嫌疑见 §6) |
| Recent 卡片 → Reveal(系统文件管理器定位) | **live**(浏览器降级复制路径) | skill-workspace · welcome | `WelcomePage.tsx:243-245`(`handleReveal`)`,425-428,449-452`(菜单项)/`lib/tauri.ts:42-70`(`revealInFileManager`,非 Tauri 环境降级为复制路径到剪贴板) |
| ~~Recent 卡片 → Delete~~ | **移除(R1)**:抄 Cursor,**不在 IDE 内删 skill**(要删去系统文件夹);Recent 失效路径改为**点击报错 + 自动移除** | skill-workspace · welcome | 现状核查(2026-08-24):`WelcomePage.tsx` 仅剩 `handleRemove`(:247-250,"Remove from recent",调 Rust `removeRecentWorkspace`)与 `REMOVE_ACTION_LABEL`(:46)两处菜单入口(:429-435 下拉、:453-459 右键),全文件 grep 未见"删除 skill 文件夹"相关代码,确认仍移除;旧引用 `WelcomePage.tsx:486-492`/`services/skills.py:436-447` 对应 D12 重写前的文件版本,该版本已不存在 |
| ~~Recent 卡片 Config drift 徽章~~ | **移除(D-1-1)**:去注册表后无落点 | skill-workspace · welcome | 现状核查(2026-08-24):`WelcomePage.tsx` 全文件 grep "drift" 零命中,卡片模型(:101-106)只有 absolutePath/displayName/identity/lastOpenedAt 四字段,确认仍移除;旧引用 `WelcomePage.tsx:431-457`/`config_arbitration.py:15-41` 对应 D12 重写前的文件版本,该版本已不存在 |
| 返回 Home(Back-to-Home→卸载工作区:清 navStack/面板/分屏/选中/copilot) | **live** | skill-workspace · shell-layout | `Header.tsx:161-173`(「Back to Home」按钮+tooltip)/`Workspace.tsx:2878-2881`(`handleHome`)`,3072`(`onHome={handleHome}`)`,513-523`(`skillId` 变 null 时清 `navStack`/`activePanel`/`copilotOpen`)/`App.tsx:23`(`onCloseSkill={() => setCurrentSkillId(null)}`);D11 退出专注模式 |
| 返回 Home 后 copilot 对话应可恢复(旧记录:现全丢) | **live(机制已接线;端到端真机行为复核留待模块十一)**:D8 要求的"退出再进恢复一模一样"已有完整代码路径——离开 workspace 只清内存投影,**不删磁盘文件**;重新进入同一 skill 时从磁盘重新水合窗口状态与会话内容 | copilot-assist · shell-layout | `useCopilot.ts:270-296`(`skillId` 变化时依次 `copilotStore.setContext`+`copilotStore.hydrate`,注释"Cold-start recovery (F2): restore only the last persisted window state (`_window.json`)")/`copilotStore.ts:332-363`(`hydrate`:读 `_window.json`,按需逐个读回未在内存中的 session 文件)`,236-249`(`persistSessionToDisk`)`,173-198`(`writeWindowState`/`persistWindowState`)`,555-568`(`reset`:仅清内存 `sessionsByContext`/`hydratedKeys`,不触碰磁盘文件)/`native_fs.rs:1243-1253`(`ensure_workspace_support_dirs` 建 `.workspace/copilot/{sessions,checkpoints}`)/单测 `copilotStore.test.ts:301`("hydrate round-trips persisted assistant content through _window.json")。本次为代码级核实,非真机逐项点验,行为级验证按 brief 归模块十一 |
| 打开 Settings 不算退出工作区(center overlay) | **live** | skill-workspace · shell-layout | `Workspace.tsx:3230-3249`(`<Dialog open={settingsOpen} ... modal={false}>` 与画布同层渲染,不卸载 `navStack`/`copilot`)`,1222-1233`(`openSettings`/`handleSettingsToggle`) |
| 进 workspace 后右侧出现 Copilot(welcome 无;新建空 skill 进入即有) | **live** | copilot-assist · shell-layout | `Workspace.tsx:513-523`(`skillId` 非空时 `setCopilotOpen(true)`)`,3020-3025`(`rightPanelOverlay` 渲染 `CopilotPanel`)`,3046-3050`(`copilotFab`/`copilotMorph`,仅在有 `currentSkillId` 时可能渲染;WelcomePage 分支两者均不渲染) |
| [失败退路] Recent 加载失败(局部红框,不阻塞新建/打开) | **live** | skill-workspace · welcome | `WelcomePage.tsx:367-373`(`recentError` 红框 Alert)/`useRecentSkills.ts:96-101`(读失败降级为 `entries: []` + 非空 `error`) |
| [失败退路] 新建/打开失败(结构化错误文案) | **live**:D2 删校验门后,manifest 校验类退路已随之移除,仅留 OS 级失败 | skill-workspace · welcome | `WelcomePage.tsx:125-140`(`formatCreateSkillError`,注释明写"D2: ...surfaces only OS-level reasons...otherwise falls through to the raw error message")`,142-157`(`formatImportSkillError`,直接 `errorMessage(error)`,注释记载旧 manifest/registry 拒绝分支"are removed")`,219-221,276-278,294-296`(三处调用点) |
| [空态] 无 skill → "No skills found"(引导新建/打开) | **live** | skill-workspace · welcome | `WelcomePage.tsx:466-476`(`Empty`/`EmptyTitle` "No recent skills") |
| [NFR 缺口] Recent 列表加载骨架(D6/§11) | **live(缺口已补)** | skill-workspace · welcome | `WelcomePage.tsx:375-376`(`isHydrating ? <RecentSkeleton /> : ...`)`,505-530`(`RecentSkeleton` 组件,注释"N1 Home · atom #8 (recent-skeleton)")/`useRecentSkills.ts:110-113,123-124`(`isHydrating` 状态:首次原生读取完成前为 true)。D6 里另一处"available models 巨长列表"skeleton 不在本节点范围,本次未核查 |

## 3. 设计决策基础(原话依据,锁定决策)
- **D11 [锁] IDE/workspace 模型** > "锁 IDE/workspace 模型";Home=打开文件夹+Recent(MRU),skill=文件夹,无注册表,子图按 path(D7)。
- **D1** > "skill 到底要不要注册表. 注册表(多了非常乱) vs ide方式(干净+自由)";Home 改 IDE 模型。
- **D2 不卡导入** > "不用卡导入, 导入什么文件真不重要, 我们有compile, 有copilot, 屎都给你改成标准skill"。
- **D12 写全量 Rust**(本地写经 native-fs,仅 engine/gateway 用 Python sidecar)> "全量切 rust, 除了 graph agent 和 llm gateway 相关使用 python sidecar"。
- **R1 删 Delete**(抄 Cursor)/ **R2 欢迎屏抄 Cursor/VS Code** / **D-1-1 删 Config drift** / **D-1-4 脚手架 logic→agent 模板**。
- **D3 删外部 IDE 联动** > "[Open in Cursor] 外部 IDE 联动 不需要了, 21、22、23都不需要了, 已经上copilot了";copilot 内置后无需外跳(`lib/tauri.ts:26-36` open_in_cursor/terminal/codex 死代码待删)。
- **D6 skeleton + lazy load**(跨切 NFR,落 INDEX §11)> "后端相关所有组件需要skeleton、lazy load功能(available models, 巨长列表)"。
- **D9 多窗口**(实现归 `04_platform`)> "多窗口难不难, 不难就实现吧";D10 三块拆分(Rust 壳 + 无状态 sidecar)下多窗口不难 → 做。
- **D10 后端三分**(实现归 `04_platform`:gateway/engine = Python sidecar、native-fs = Rust)> "后端应该分为3块: 1. gateway 包括 studio backend里面的llm gateway相关的后端部分代码要并入 gateway, 全部用服务形式 python sidecar; 2. graph agent engine, 也是python, 用 sidecar; 3. 大量的本地操作, 读写文件, 文件系统(打开文件夹)等等, 全部用rust本地操作";启动期 sidecar **eager-spawn(非全屏 gate)** > "启动程序时就后端拉起sidecar, 因为未来还要登陆用户呢, 还有setting 页面里api、llm role这些配置都需要服务端"。

## 4. 失败退路 + 节点间流转
- **失败退路**:Recent 加载失败→局部红框(不阻塞入口);新建/打开失败→结构化文案(D2 后仅留 OS 级);sidecar 未就绪→skeleton + 全局就绪指示(非全屏 gate)。
- **下游**:进入 workspace → [02_authoring](./02_authoring.md)(画布/编辑/编译);右侧 copilot → copilot-assist。
- **上游**:无(应用入口)。

## 5. 测试关键点
- 去注册表后 Recent 卡片只靠 MRU(路径+名)渲染,后端不可用也能新建/打开。
- D2:打开**任意**文件夹(缺 GRAPH.md/SKILL.md)不被拒,交 compile+copilot。
- D12:新建/打开的落盘走 Rust 文件命令(非 Python `POST /skills`)。
- Back-to-Home 卸载工作区但 copilot 对话可恢复(D8);打开 Settings **不**卸载。
- RuntimeGate 未退役:壳/FS 立即渲染,sidecar 状态用非阻塞底部横幅呈现(冷启动/掉线两态),从不用全屏 splash 挡住 UI;运行中途死掉时还有有界自动重启(1s/4s/16s,耗尽后停,靠手动 Retry 重开一轮)。

## 6. 跨切 / 已知债
- **注册表→无注册表重塑(已还,2026-08-24 复核确认)**:`GET /skills` 列表聚合端点已从后端路由整体移除(`apps/studio/backend/app/routers/skills.py` 现无任何裸 `@router.get("")`/list 路由;`apps/studio/backend/app/services/skills.py` 也已无 `list_skills`/`MetadataStore` 聚合函数),前端 `useSkills.ts:6-11` 的注释原样记载这次退役("Only the per-skill DETAIL fetch remains. The old GET /skills LIST was retired…Design: Home = local MRU, no registry aggregation (D11 "无注册表")")。Home 完全由 `useRecentSkills.ts`(Rust `recent_workspaces.json`)驱动,不再有任何列表级注册表聚合。
- **D12 写归属(已还)**:新建(`createSkillWorkspace`→`native_fs.rs:1619-1664` `create_skill_workspace_impl`)、打开注册(`openSkillWorkspace`→`native_fs.rs:1669-1688` `open_skill_workspace_impl`)、Recent 增/查/删(`lib/tauri.ts:700,716,733` `addRecentWorkspace`/`listRecentWorkspaces`/`removeRecentWorkspace`)全部落 Rust native-fs(命令已注册于 `apps/studio/tauri/src/lib.rs:4430-4431`),前端全仓多种 grep 模式下未见任何调用 Python `POST /skills` 创建/导入路径的残留。
- **孤儿嫌疑,新增(2026-08-24 复核发现)——Python 注册表式 CRUD 端点未随迁移退役**:`apps/studio/backend/app/routers/skills.py:312-313`(`POST "" create_skill`)与 `:985-986`(`DELETE "/{skill_id}" delete_skill_endpoint`)在 `apps/studio/frontend/src` 全仓多种 grep 模式(`createSkill`/`deleteSkill`/`post('/skills'`/`` delete(`/skills/${id}` ``等)下均无非测试调用方——D12(创建落盘迁 Rust)与 R1(禁止 IDE 内删 skill)生效后,这两个端点疑似已成孤儿。本次任务范围为文档 status 追平,未做进一步代码健康度裁决;是否退役留待后续复核。
- **D3 死代码(已还)**:`lib/tauri.ts` 现全仓 grep `open_in_cursor`/`open_in_terminal`/`open_in_codex`(含 camelCase 变体)零命中,对应 Rust 命令与前端 helper 均已删除。
- **孤儿(已还)**:`components/WelcomeScreen.tsx` 现仓库内不存在(`find` 确认零文件);真实 Home 挂载路径固定在 `components/studio/Workspace.tsx:3094-3103`(`WelcomePage`,已随重构迁至 `components/welcome/WelcomePage.tsx`)。
- **多窗口(D9)**:归 04_platform(Rust 壳 + 无状态 sidecar);本次复核未涉及,状态未变。

## 7. 修订记录
- **2026-08-24**(动因:模块二真机点验发现本文件 status 列与 file:line 依据系统性滞后于代码)——逐行按当前代码核实更新;FROZEN 决策原文(D1/D2/D3/D6/D8/D9/D10/D11/D12/R1/R2/D-1-1/D-1-4 及 §3 全部原话)未改一字,仅改了 §2 的 status/依据列与 §6。逐条改动:
  - §2 头部「⚠️ 全局架构错配」警示:改判为**不再成立**并重写说明——`GET /skills` 列表聚合与 `MetadataStore` 已从后端**整体移除**(不只是前端弃用调用),`useSkills.ts` 顶部注释自证这次退役。
  - 「应用启动 gate」:`stale-doc` → **live**(RuntimeGate 未退役,演进为非阻塞横幅 + 有界自动重启,`runtime-gate-auto-restart.ts` 自标 2026-08-24 的 dead-sidecar-says-so 修复)。
  - 「Home 显示 Recent 列表」:`stale-doc` → **live**(确认为 Rust native-fs MRU,非 localStorage)。
  - 「新建 Skill」:`stale-code` → **live**(D12 已兑现:`createSkillWorkspace` → Rust `create_skill_workspace_impl`)。
  - 「打开现有文件夹」:`stale-code` → **live**(D2+D12 均已兑现)。
  - 「返回 Home 后 copilot 对话应可恢复」:`target-design` → **live(机制已接线;端到端真机行为复核留待模块十一)**(`useCopilot.ts`/`copilotStore.ts` 的 hydrate/persist 路径完整存在且有单测覆盖)。
  - 「[失败退路] 新建/打开失败」:`stale-code` → **live**(D2 已兑现,manifest 校验分支已从前端删除)。
  - 「[NFR 缺口] Recent 列表加载骨架」:`target-design` → **live(缺口已补)**(`RecentSkeleton` 组件与 `isHydrating` 分支已存在)。
  - 「Recent 卡片 → Delete」「Recent 卡片 Config drift 徽章」:决策状态不变(仍移除),依据列改为现状核查证据(旧文件行号对应 D12 重写前的版本,已不存在)。
  - 「进入 Home 屏」「打开一个 Recent skill」「新建对话框选父目录」「Recent 卡片 → Reveal」「返回 Home」「打开 Settings 不算退出工作区」「进 workspace 后右侧出现 Copilot」「[失败退路] Recent 加载失败」「[空态] 无 skill」:决策状态不变(原已是 live),仅因组件从 `components/WelcomePage.tsx` 迁至 `components/welcome/WelcomePage.tsx` 且历经重写而重新核实、更新 file:line。
  - §6:「注册表→无注册表重塑」「D12 写归属」「D3 死代码」「孤儿 `WelcomeScreen.tsx`」四项标记为**已还**;新增一条孤儿嫌疑记录(Python `POST /skills`/`DELETE /skills/{id}` 疑似孤儿,留待代码健康度复核);「多窗口(D9)」未改动。
  - **未改动、超出授权范围、留待复核**:§1/§3/§4/§5 正文与全部 FROZEN 决策原文本次未动一字;§5 现存"RuntimeGate 退役后壳/FS 立即可用"一句与本次更新后的 §2 第一行(RuntimeGate 未退役)已不一致,因超出本次任务的授权编辑范围(仅限 §2 status/依据列 + §6 + 本修订记录)未一并修正,已在交付说明中另行提请复核。
  - **2026-08-24(追加,协调者补授权)**:上一条记录的 §5/§2 不一致已收掉——§5「测试关键点」最后一行改写为与 §2「应用启动 gate」行一致的现状描述(RuntimeGate 未退役,演进为壳/FS 立即渲染 + 非阻塞底部横幅 + 有界自动重启),复核依据同 §2 该行:`App.tsx:19`(`<RuntimeGate>` 包裹 `<Workspace>`)、`RuntimeGate.tsx:31-33,34-65,72-204,77-123,159-164`、`runtime-gate-auto-restart.ts:26`。
