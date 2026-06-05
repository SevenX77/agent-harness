# Node 1: 发现与初始化 (Discovery & Init)

> Tier: workflow · Owns: 进入 Studio + Home↔skill-workspace 强隔离切换的完整旅程 · 能力 `skill-workspace`(引用 `copilot-assist`)· 区域 `welcome` / `shell-layout` · 平台 `native-fs`(Rust) / `gateway`(sidecar)
> Status: ✅ PM 已确认(批次1:D1–D11 + R1/R2 + D-1-1/D-1-4)
> 设计权威: **D11 IDE/workspace 模型(锁)** + D1/D7/D10/D6 + INDEX §6;无专属 studio-feature spec。PM 决策原话就近留底于 §3。
> 本文 = 该节点**最终设计**(atom action 决策 + file:line 依据)。

## 1. 用户旅程目标
PM 如何进入 Studio、在「主页 Home」与「沉浸式 skill workspace」间切换。核心范式 = **强隔离 Home/Workspace + IDE/workspace 模型**(D11 锁):skill = 一个文件夹;Home = 打开文件夹 + Recent(MRU localStorage);**无聚合注册表**;一窗口专注一个 skill;子图按 path 解析(D7)。

## 2. atom action 决策表
> status 见 INDEX §4。**⚠️ 全局架构错配(影响整层 status)**:现状 Home/后端是**注册表模型**(MetadataStore + `GET /skills` 聚合 + 自动发现 unregistered,`useSkills.ts:7`/`services/skills.py:183-258`),与 D1/D11 锁定的「无注册表」**方向冲突** → 很多看似 live 的动作其底层机制要重塑为 skill-workspace(故标 stale-doc/stale-code 非 live)。

| 动作 | 最终决策 / status | 能力·区域 | 依据(file:line)+ 动机/FROZEN |
|---|---|---|---|
| 应用启动 gate(全屏 splash→ready 才渲染) | **stale-doc**:RuntimeGate 退役 → 两 sidecar 启动期 Rust eager-spawn + 壳/FS 立即渲染 + 调 sidecar 处 skeleton(非全屏 gate,D10) | skill-workspace · shell-layout | `App.tsx:16`/`RuntimeGate.tsx:31-44`/`config/runtime.ts:53-61`;实现归 04_platform(native-fs 管 sidecar) |
| 进入 Home 屏(`currentSkillId===null`→WelcomePage) | **live** | skill-workspace · welcome | `Workspace.tsx:512-513,38-54`;D11 强隔离落点 |
| Home 显示 Recent 列表(MRU 卡片) | **stale-doc** → 机制重塑为 Recent(MRU)主导,**卡片极简(只存路径+名,D-1-1)**;欢迎屏整体抄 Cursor/VS Code(R2) | skill-workspace · welcome | `WelcomePage.tsx:241-244,401-521`/`useRecentSkills.ts:26-32`(MRU localStorage max10);现内容来自注册表聚合=冲突 |
| 打开一个 Recent skill(点卡片→进 workspace) | **live** | skill-workspace · welcome | `WelcomePage.tsx:246-249,408-416`;Cursor Open Recent 同款 |
| 新建 Skill(填名/选父目录→建文件夹+脚手架+git init→进 workspace) | **stale-code** → 写盘迁 Rust(D12);**脚手架=logic→agent 模板**(D-1-4,非空文件夹、不调 copilot) | skill-workspace · welcome | `WelcomePage.tsx:352-361`/`NewSkillDialog.tsx:23-107`/`skills.py:81-96`/`services/skills.py:558-560`。**FROZEN/D12**:写脚手架+git init 从 Python `POST /skills` 迁 Rust 文件命令 |
| 新建对话框选父目录(OS 目录选择器;默认来自 `default_skills_directory`) | **live** | skill-workspace · welcome | `WelcomePage.tsx:258-268,239-240`/`lib/tauri.ts:64-81`/`skill-paths.ts:18` |
| 打开现有文件夹(选任意本地文件夹→进 workspace) | **stale-code** → **删导入校验门**(D2:不卡导入、不合规交 compile+copilot 修);写路径迁 Rust(D12);文案改"打开文件夹" | skill-workspace · welcome | `WelcomePage.tsx:370-381,310-335`/`services/skills.py:517-522`(缺 GRAPH.md/SKILL.md 硬拒=违 D2)。**FROZEN/D2**:删校验门+import-error 文案 |
| Recent 卡片 → Reveal(系统文件管理器定位) | **live**(浏览器降级复制路径) | skill-workspace · welcome | `WelcomePage.tsx:481-484`/`lib/tauri.ts:38-62` |
| ~~Recent 卡片 → Delete~~ | **移除(R1)**:抄 Cursor,**不在 IDE 内删 skill**(要删去系统文件夹);Recent 失效路径改为**点击报错 + 自动移除** | skill-workspace · welcome | `WelcomePage.tsx:486-492`/`services/skills.py:436-447`(原 delete=仅注销不删盘) |
| ~~Recent 卡片 Config drift 徽章~~ | **移除(D-1-1)**:去注册表后无落点 | skill-workspace · welcome | `WelcomePage.tsx:431-457`/`config_arbitration.py:15-41` |
| 返回 Home(Back-to-Home→卸载工作区:清 navStack/面板/分屏/选中/copilot) | **live** | skill-workspace · shell-layout | `Header.tsx:56-66`/`Workspace.tsx:439-442,44-48`;D11 退出专注模式 |
| 返回 Home 后 copilot 对话应可恢复(现全丢) | **target-design** → D8 MUST:退出再进恢复一模一样;其余工作态(面板/分屏)可丢(Q3) | copilot-assist · shell-layout | `copilotStore.ts:10-12,27-28`(纯内存 reset);实现归 copilot-assist / native-fs(D8 Rust 写) |
| 打开 Settings 不算退出工作区(center overlay) | **live** | skill-workspace · shell-layout | `Workspace.tsx:496-497,466,439-440`;Q3 |
| 进 workspace 后右侧出现 Copilot(welcome 无;新建空 skill 进入即有) | **live** | copilot-assist · shell-layout | `Workspace.tsx:41,47-52,545-555`;Q4(PM 修正:无矛盾) |
| [失败退路] Recent 加载失败(局部红框,不阻塞新建/打开) | **live** | skill-workspace · welcome | `WelcomePage.tsx:392-399` |
| [失败退路] 新建/打开失败(结构化错误文案) | **stale-code** → D2 删校验门后,manifest 校验类退路随之移除(仅留 OS 级失败) | skill-workspace · welcome | `WelcomePage.tsx:193-228`/`services/skills.py:488-510` |
| [空态] 无 skill → "No skills found"(引导新建/打开) | **live** | skill-workspace · welcome | `WelcomePage.tsx:524-534` |
| [NFR 缺口] Recent 列表加载骨架(D6/§11) | **target-design** | skill-workspace · welcome | `WelcomePage.tsx:401-521`(无 skeleton 分支);available models 巨长列表是首要 |

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
- RuntimeGate 退役后壳/FS 立即可用、调 sidecar 处 skeleton(无全屏 splash)。

## 6. 跨切 / 已知债
- **注册表→无注册表重塑**(最重要):MetadataStore/`GET /skills` 聚合 → skill-workspace(Recent MRU + 子图按 path)。
- **D12 写归属**:新建脚手架/打开注册/删除等落盘 → Rust(native-fs 唯一写者)。
- **D3 死代码**:`lib/tauri.ts:26-36` open_in_cursor/terminal/codex 前端零调用 → 删 helper + Rust 命令。
- **孤儿**:`components/WelcomeScreen.tsx`(no-op 包装,真实挂载=`Workspace.tsx:513`)。
- **多窗口(D9)**:归 04_platform(Rust 壳 + 无状态 sidecar)。
