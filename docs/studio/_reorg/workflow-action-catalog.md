# Skill Studio 文档重组 — Workflow 动作目录(master)

> 来源: workflow `wf_1c266263-f42`(6 节点并行编目 + critic 审校), 2026-06-02。配套决策日志: [alignment-notes.md](alignment-notes.md)。
> 本表 = 「**划分 scope + 理清每个 workflow 动作 + 每个动作动机 + FROZEN 改动**」。下一步据此撰写 `mvp1/02_capabilities/*` 与 `mvp1/03_regions/*`(新设计在 mvp1)。

## 怎么读
- **权威序**: 动作**目标**=新 spec(`.kiro/specs/studio-feature-*`)+ alignment-notes 决策; **格式/字段**=FROZEN(`docs/engine/skill-spec`); **status**=当前代码(file:line)。
- **status 词表**(INDEX §4): `live` 已接线真实驱动 / `placeholder` 入口在·回调是桩 / `orphan-unmounted` 组件已建无 importer / `backend-only` 后端就绪·前端无 UI / `target-design` 仅设计·代码无对应 / `stale-doc` 文档与实现相反 / `stale-code` 代码在跑但过时格式·冲突 FROZEN。

## 横切约束(贯穿所有节点)
1. **[D12] 写入全量 Rust**: 所有本地写/落盘经 Rust 文件命令(native-fs 唯一写者); 仅 graph-agent engine + llm-gateway 走 Python sidecar。表中凡写类动作目标态=经 Rust(现走 Python 的标迁移)。
2. **[D2] 不卡导入**: 删 import 校验门 + import-error 文案; 开任意文件夹即用, 不合规交 compile + copilot 修。
3. **skeleton + lazy load(D6/§11)**: 所有后端数据驱动组件须骨架屏 + 懒加载(available models / Recent / run 历史 / trace 大列表)。
4. **[D8] copilot 持久化(MUST)**: 对话 + session 落盘(Rust 写 skill 目录), 退出再进恢复一模一样; 当前纯内存全丢 = target-design。
5. **整层现状 = 「后端实 / 前端虚」**: predict/run/golden/publish 后端 live 或 backend-only, 但 TracePanel/DiffView/BatchRunner/PromptInspector/useRunStream/useGoldenDiff 全套已实现却**零挂载**(orphan), Eval 模式(view='eval')整体不可达。**主要工程量 = 接线孤儿, 不是缺能力。**

## 审校修正(critic, 读各节点表时按此校准)
1. **stage 机归属**: idle→compile→predict→run 的 center-action-bar 门控被 03/04 各述一遍(违所有权不变量)→ 归 `compile-lint` 单一拥有, predict/run-execution 只链接;「predict-pass 永不置位→Run 不可达」是一条跨能力 known-gap(记一次)。
2. **region 列纠错**: 04/05 把 `engine`/`native-fs`/`state-engine`(属 `04_platform`)误填进 region 列 → 这些动作真实 UI 区域应是 timeline/canvas 等, platform 归属用「依赖的 platform 服务」另列(**region ≠ platform**)。
3. **batch 失败上报 status = `backend-only`**(取 04, 非 03 的 target-design): 后端逐项 status live, 前端 surface 在孤儿 useBatchRun; 接 BatchRunner 必须同时接失败项渲染, 否则违零容忍静默失败。
4. **run-execution 动作以 04 为权威源**: 批量等动作在 03/04 各列一遍(一能力→多节点正常), status 以 04_execution 为准, 03 仅链接。
5. **i/o panel 是两能力共用一区域**: 改名后的 i/o panel 里「测试输入段」归 predict,「io/artifact 设置段」归 phase-editing, 非 predict 独占。

## FROZEN 新版本改动集(本 session 锁定, 待统一改 spec 文件)
- **FROZEN-1 删 `04-subgraph` io 严格 1:1**(G2): 子图 input 改为从黑板按 io.inputs 过滤, 同任何节点; 删 `F-v3-subgraph-io-mismatch` 的 1:1 强制。
- **FROZEN-2 `02`/`03`/`05` io.outputs 加 artifact 落盘标注**(G3): schema 顶层加文件路径(`xx/xx.json|md`)+ 其下 schema; 支持一 schema 多文件 / 多 schema 各落; 只写文件名=默认 `.workspace/artifacts`; 文字仅 md/json; md 源=最终 validated `business_data_md`(不回转)。
- **FROZEN-3 节点级文件导入→黑板注入**(G2 新需求, 引擎/runtime): 任意 i/o 面板导入文件=注入字段进黑板; 时机=a(跑到该节点才注入)。
- **FROZEN-4 canvas REQ-2 黑板可视化连线**: 删类型相等红叉, 改按 io.inputs 切片字段高亮勾选(影响 io 语义)。
- **(非 FROZEN·连带删除) D2**: 删 import 校验门(`services/skills.py` 缺 GRAPH.md/SKILL.md 检查)+ import-error 文案 + 相关错误退路。
- **(非 FROZEN·全局约束) D12**: 写归属全量 Rust(见横切#1)。

## PM 决策(已拍, 2026-06-02)
- **settings 旅程无主 → 立 `00_settings` 节点**: 新增 workflow 节点承载 settings 旅程(API keys / LLM roles / copilot 配置 / 产物路径), 与 01-06 并列。
- **copilot 持久化失败退路 → 补失败退路动作**: 在 copilot/native-fs spec 显式加「session 写盘/读回失败 → 显式告警, 不静默」, 登记为待建动作(D8 MUST 配套)。

## 节点 PM 确认状态
- ✅ **已 PM 确认**: `01_init`(批次1 D1–D11)、`02_authoring`(Half A + T5/T6/io 的 G1–G9 + canvas 设计细化)。跨 session 决策(D12 / FROZEN-1..4 / 00_settings / copilot 失败退路)亦已拍。
- ⏳ **未过 PM(下个 session 接着过)**: `03_prediction`、`04_execution`、`05_debugging`、`06_eval` —— 由 workflow 编目 + critic 抽检, 但 PM 尚未逐节点走查。

## 可疑项核实(2026-06-02, 已做)
- ✅ engine `events.py` 真实存在, **34** 个事件类 → trace 契约可信。
- ✅ 最终 `business_data_md` 在 `cognitive_flow.py:482`(finish_task 中间件)保留 → **G3 md artifact 直接取它, 不做 json→md 回转**(artifact 写入接线是新工作)。
- ✅ `useGoldenDiff.ts:27` 调 `GET /runs/{id}/compare`, 但后端 `/compare` 是 **POST**(`compare.py:14`)、GET 是 `/diff`(`compare.py:23`)→ method/path mismatch, 确认为 orphan 期潜伏 bug, 接线时修。

> 各节点表尾「待定」为节点级 open question, 留下个 session 逐节点过。

---

## 01_init — Init / Home / 打开工作区

**Scope**: 本节点拥有"进入 Studio + 在 Home 与某个 skill workspace 之间切换"的完整用户旅程: Home(WelcomePage)的新建/打开文件夹/Recent(MRU)/reveal/移除最近/空态/加载错误退路, 以及壳层的 Home↔Workspace 强隔离切换(Back-to-Home 卸载工作区)。设计权威=D11 IDE/workspace 模型(锁)+ D1/D7/D10/D6 + INDEX §6(skill-workspace 能力 / welcome+shell-layout region); 无专属 studio-feature-* spec。

拥有(owns): skill-workspace 能力在 welcome / shell-layout 两个 region 的所有动作; RuntimeGate 启动门(待退役判定)。

不拥有(移交其他节点/spec):
- 进入 workspace 后的画布/编辑/copilot 对话本身 → 02_authoring(graph-authoring/file-editing)、copilot-chat spec。
- 子图下钻产生的多级面包屑(Header navStack>1)→ graph-authoring(canvas REQ-6 L2/T6), 非 01_init(本节点 navStack 恒为单条 Workspace.tsx:50)。
- copilot 建技能向导(D5 graph skill)、copilot session 持久化(D8)的实现 → copilot-assist / copilot spec(本节点仅引用其"welcome 屏无 copilot""重进恢复对话"两个旅程事实)。
- 后端三分/sidecar 生命周期/RuntimeGate 退役后的 eager-spawn+skeleton → 04_platform(native-fs/gateway/engine, D10)。
- settings 页(API/role)→ settings region(本节点仅记"打开 Settings 是 center overlay, 不算退出工作区")。

⚠️ 全局架构错配(待 PM 拍, 影响整层 status): 当前 Home 是**注册表模型**(GET /skills 聚合全量 + POST import_existing + DELETE 注销 + 自动发现 unregistered, 见 useSkills.ts:7 / skills.py / services/skills.py:183-258), 与 D1/D11 锁定的"无注册表, Home=打开文件夹+Recent(MRU), skill=文件夹"是**方向冲突**。因此本节点几乎所有"现状 live"动作的实现机制都需重塑为 skill-workspace(target-design), 现机制标 stale-doc/stale-code 注明冲突点。

### [stale-doc] 应用启动: RuntimeGate 拉起后端配置并 gate 整个 UI(全屏 'Starting Skill Studio' splash → ready 才渲染 Workspace; 失败显示 'Backend startup failed')
- **能力·区域**: `skill-workspace` · `shell-layout` — 目标: — (待建; 设计源 INDEX §11 NFR + alignment-notes D10/D10-确认)
- **动机**: 用户打开 Studio 的第一帧必须有确定性入口; 当前用全屏 gate 保证 API baseURL/token 就绪。但 D10(锁)裁定 RuntimeGate 退役→改为两 sidecar 启动期由 Rust eager-spawn + 壳/FS 立即渲染 + 调 sidecar 处 skeleton + 全局就绪指示(非全屏 gate), 故现实现与目标设计相反, 标 stale-doc。
- **证据**: App.tsx:16 (<RuntimeGate>包裹 Workspace); RuntimeGate.tsx:31-44 (loading splash / error 屏 / ready 才 return children); config/runtime.ts:53-61 (initializeRuntimeConfig 调 Tauri get_sidecar_config + configureApiBaseURL)

### [live] 进入 Home 屏(currentSkillId===null 时渲染 WelcomePage, 强隔离 Home; 有 skill 时渲染 workspace)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 alignment-notes D11; INDEX §6 skill-workspace)
- **动机**: Studio 顶层导航心智=Home(纯入口) 与 沉浸式 Skill Workspace 强隔离(D11 锁); 一个窗口专注一个 skill。这条 gate 是该范式的落点。
- **证据**: Workspace.tsx:512-513 (currentSkillId===null ? <WelcomePage>); Workspace.tsx:38-54 (navStack 状态机: skillId null→navStack[]→currentSkillId null); App.tsx:9-25 (currentSkillId 顶层 state)

### [stale-doc] Home 显示 Recent skills 列表(MRU 卡片网格: 名称/路径/phases 数/last_run/Golden 徽章)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 alignment-notes D1/D11)
- **动机**: D1 锁定 Home=打开文件夹+Recent(MRU, localStorage)无聚合注册表。当前列表内容来自注册表(GET /skills 聚合全量+后端自动发现 unregistered), MRU 仅做排序覆盖层, 与'无注册表'方向冲突→机制需重塑为 Recent(MRU)主导, 标 stale-doc。MRU 本身(localStorage)已就位。
- **证据**: WelcomePage.tsx:241-244 (useSkills(null)=GET /skills + useRecentSkills + sortRecent); WelcomePage.tsx:401-521 (卡片渲染); welcome/utils.ts:20-28 (sortRecent: recent 在前+剩余按 last_run); useRecentSkills.ts:26-32 (MRU localStorage 'recentSkills' max10); useSkills.ts:7 (SWR '/skills'); services/skills.py:183-258 (list_skill_summaries 聚合+自动发现)

### [live] 打开一个 Recent skill(点卡片/Enter/Space → rememberSkill + 进入 workspace)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D1)
- **动机**: Recent 列表的核心功能=一键回到上次工作的 skill(Cursor Open Recent 同款); 打开即写 MRU 头部。
- **证据**: WelcomePage.tsx:246-249 (openSkill: rememberSkill+onSelectSkill); WelcomePage.tsx:408-416 (Card onClick/onKeyDown→openSkill); useRecentSkills.ts:26-32 (rememberSkill 置顶)

### [stale-code] 新建 Skill(点 New skill → NewSkillDialog 填名/选父目录 → 提交 → 创建文件夹+脚手架+git init → 自动进入新 workspace)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D1; 写归属 D12)
- **动机**: Home 两大入口之一(D1: 新建文件夹)。当前走 POST /skills 由 Python 写脚手架文件+git init, 且生成的脚手架内容/装配是后端职责。按 D12(本地操作全量 Rust, 仅 engine/gateway 用 Python sidecar), '新建文件夹+写脚手架+落盘'必须改为经 Rust 文件命令; 故现 Python 写盘路径标 stale-code(目标=Rust 写)。对话式细化建技能由 D5 graph skill 在 workspace 内补。
- **证据**: WelcomePage.tsx:352-361 (New skill 按钮→openNewSkillDialog); NewSkillDialog.tsx:23-107 (名/父目录表单); WelcomePage.tsx:288-308 (submitNewSkill→POST /skills buildSkillCreatePayload→openSkill); skills.py:81-96 (create_skill 端点); services/skills.py:558-560 (write_skill_files_atomic + initialize_skill_repository); services/skills.py:544-549 (非空文件夹拒绝)
- **FROZEN 改动**: D12: 新建 skill 的'写脚手架文件+git init+落盘'从 Python POST /skills 迁为 Rust 文件命令(native-fs 唯一写者); Python 端退为只读/装配。

### [live] 新建对话框内选择父目录(Choose folder → OS 目录选择器; 默认父目录来自 app settings default_skills_directory)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D1)
- **动机**: 新建时需让用户决定 skill 落在文件系统哪里(IDE 模型: skill=文件夹); 提供默认路径降低决策负担。
- **证据**: WelcomePage.tsx:258-268 (chooseNewSkillParentDirectory→selectSkillDirectory); lib/tauri.ts:64-81 (select_directory Tauri 命令); WelcomePage.tsx:239-240 (defaultSkillParentDirectory←useAppSettings); utils/skill-paths.ts:18 (effectiveDefaultSkillsDirectory)

### [stale-code] 打开现有文件夹(Import skill → OS 目录选择器 → 选任意本地文件夹 → 注册并进入 workspace; 若已注册则直接重新打开)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D1/D2; 写归属 D12)
- **动机**: Home 两大入口之二(D1: 打开现有文件夹, VS Code 风格)。当前 POST /skills import_existing **硬卡校验**: 缺 GRAPH.md/SKILL.md 直接拒绝(INVALID_DIRECTORY_PATH), 与 D2(锁: 不卡导入, 开任意文件夹即用, 不合规交 compile+copilot 修)**直接冲突**; 且按钮文案'Import skill'应改为'打开文件夹'语义。故标 stale-code: 需删导入校验门 + 写路径迁 Rust。
- **证据**: WelcomePage.tsx:370-381 (Import skill 按钮); WelcomePage.tsx:310-335 (importSkillDirectory→selectSkillDirectory→registeredSkillIdForImport 命中即重开→否则 POST import); services/skills.py:517-522 (缺 GRAPH.md/SKILL.md→_raise_invalid_directory_path, 违 D2); services/skills.py:523-525 (有 GRAPH.md 仅 lint 不 raise)
- **FROZEN 改动**: D2: 删 import 校验门(services/skills.py:517-522 的 GRAPH.md/SKILL.md 必需检查)+ 删 import-error-format; D12: 打开文件夹的注册/落盘改 Rust。

### [live] Recent 卡片右键/⋯菜单 → Reveal('Show in folder', 在系统文件管理器中定位 skill 文件夹)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D1; INDEX §6 skill-workspace 列含 reveal)
- **动机**: IDE 模型下用户常需跳到真实文件夹做外部操作; reveal 是 skill=文件夹 心智的自然配套(浏览器降级为复制路径)。
- **证据**: WelcomePage.tsx:481-484,507-510 (Show in folder 菜单项→handleReveal); WelcomePage.tsx:270-272 (handleReveal→revealInFileManager); lib/tauri.ts:38-62 (reveal_in_file_manager Tauri 命令 / 浏览器降级复制路径)

### [stale-code] Recent 卡片右键/⋯菜单 → Delete(从 Studio 移除最近, 二次确认 toast; 源文件夹保留在磁盘)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D1)
- **动机**: D1 把动作 11 skill-delete 重定义为 remove-from-recent(不删盘)。当前已是'保留磁盘'(delete_skill 仅注销 metadata), 语义对; 但它注销的是**注册表条目**, 与无注册表目标不符——目标应是从 MRU(localStorage)移除。故标 stale-code: 删除目标改为 remove-from-Recent。'保留磁盘'承诺已正确传达给用户。
- **证据**: WelcomePage.tsx:486-492,512-518 (Delete 菜单项→handleDelete); WelcomePage.tsx:96-107 (requestSkillDeleteConfirmation: 'Its source folder stays on disk'); WelcomePage.tsx:274-282 (deleteSkill→DELETE /skills); skills.py:475-483 (delete_skill_endpoint 204); services/skills.py:436-447 (delete_skill: 仅 unregister+remove index/summary, 不 rmtree skill 目录)

### [stale-doc] Recent 卡片显示 Config drift 徽章(本地 git remote URL 与期望不符时告警, hover 显示 actual/expected/建议)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D1, 标'存疑/待定')
- **动机**: 现状: 后端比对实际/期望 git remote 给出 config_mismatch, 前端渲染徽章(live 端到端)。但 D1 明确'12 config-drift-warn 在无注册表下存疑(待定)'——去注册表后该告警的存在意义/落点不明, 故标 stale-doc 待 PM 拍是否保留。
- **证据**: WelcomePage.tsx:431-457 (Config drift Badge + Tooltip actual/expected/recommendation); models/skills.py:36 (config_mismatch 字段); services/skills.py:217,258-266 (_attach_config_mismatch); services/config_arbitration.py:15-41 (detect_config_mismatch 比对 remote URL)

### [live] 返回 Home(workspace 内 Header 左上 'Back to Home' → 卸载工作区: 清 navStack/面板/分屏/选中态/copilot, 回 WelcomePage)
- **能力·区域**: `skill-workspace` · `shell-layout` — 目标: — (设计源 D11)
- **动机**: 强隔离范式必须有明显的退出专注模式入口(D11; 类 VS Code 关项目)。这是 Home↔Workspace 切换的反向动作, 属壳层(shell-layout)旅程。
- **证据**: Header.tsx:56-66 (Back to Home 按钮→onHome); Workspace.tsx:439-442 (handleHome: setSettingsOpen(false)+onCloseSkill); App.tsx:20-21 (onCloseSkill→setCurrentSkillId(null)); Workspace.tsx:44-48 (skillId null→清 navStack/activePanel/copilotOpen)

### [target-design] 返回 Home 时工作态丢失而 copilot 对话应可恢复(当前: 退出工作区 copilot 对话+面板+分屏+选中全丢; localStorage 仅留 Recent+主题; 重进对话清空)
- **能力·区域**: `copilot-assist` · `shell-layout` — 目标: — (设计源 alignment-notes D8 + Q3; 归属 copilot-chat/native-fs spec)
- **动机**: D8(硬需求, MUST): copilot 对话不能丢, 退出再进恢复一模一样(Cursor 同款)。当前 copilotStore 纯内存, 切 skill 即 reset 清空, 退出回 Home 全丢——D8 未落地。本节点只记这条旅程事实(重进 workspace 须恢复对话), 持久化实现归 copilot/native-fs spec(D8: Rust 写 skill 目录)。其余工作态(面板/分屏/选中)允许丢(Q3 澄清)。
- **证据**: store/copilotStore.ts:10-12 (let state 内存); copilotStore.ts:27-28 (reset(skillId)→messages:[]); useCopilot.ts:59-62 (skillId 变即 reset); Workspace.tsx:47-48 (回 Home 时 copilotOpen=false); 无 localStorage/disk 写 copilot(grep store 无 persist)

### [live] 打开 Settings 不算退出工作区(Toolbar→Settings = center overlay, skill 态/copilot/面板保留; 关闭 overlay 回原工作区)
- **能力·区域**: `skill-workspace` · `shell-layout` — 目标: — (设计源 Q3)
- **动机**: Q3 澄清: 打开 Settings 是 center overlay 覆盖中心视图, 不卸载 workspace(区别于 Back-to-Home)。本节点记此边界以免与'退出工作区'混淆; settings 内容本身归 settings region。
- **证据**: Workspace.tsx:496-497 (settingsOpen?<SettingsPage onClose>:...); Workspace.tsx:466 (Toolbar onSettingsOpen→setSettingsOpen(true)); Workspace.tsx:439-440 (handleHome 额外 setSettingsOpen(false), 说明 settings 独立于 skill 卸载)

### [live] 进入 workspace 后右侧出现 Copilot(welcome 屏无 copilot; 有 skill 时 copilotOpen=true; 新建空 skill 进入即可用)
- **能力·区域**: `copilot-assist` · `shell-layout` — 目标: — (设计源 Q4)
- **动机**: Q4 澄清(PM 修正 AI 误判): copilot 随 skill 出现, welcome 屏不放 copilot; 新建空 skill 后进入即有 copilot, 无矛盾。本节点记 copilot 的'出现时机'旅程事实(welcome 无 / workspace 有); copilot 内部能力(对话/建技能 D5)归 copilot-assist。
- **证据**: Workspace.tsx:41 (copilotOpen 初值=Boolean(skillId)); Workspace.tsx:47-52 (skillId null→copilotOpen false / 有→true); Workspace.tsx:545-555 (copilotOpen 才渲染 CopilotPanel); copilot-panel.tsx:74,154 (skillId null 时空态)

### [live] [失败退路] Recent 列表加载失败(GET /skills 出错 → 'Could not load skills' 红框, 不阻塞新建/打开入口)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D1)
- **动机**: 后端不可用时 Home 仍要能新建/打开文件夹, 故列表错误降级为局部告警而非整屏失败。(去注册表后 GET /skills 本身会被 Recent(MRU) 取代, 但'列表区错误退路'旅程仍需保留。)
- **证据**: WelcomePage.tsx:392-399 (skillListError→Could not load skills 红框); useSkills.ts:7 (SWR skillListError)

### [stale-code] [失败退路] 新建/打开文件夹失败(同名 SKILL_ALREADY_EXISTS / 无效目录 / 非空文件夹 / manifest 校验失败 / 后端不支持 import → 结构化错误文案; import 命中已存在则直接重开)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D1/D2)
- **动机**: 创建/导入需对各类失败给可读引导(降低用户卡死)。但其中'manifest 校验失败/folder import not supported'等错误分支源于注册表+导入校验门, 与 D2(不卡导入)冲突; D2 落地后这些校验类错误退路应大幅收缩(仅留 OS 级失败如目录不存在/无权限)。故标 stale-code。
- **证据**: WelcomePage.tsx:193-228 (formatCreateSkillError/formatImportSkillError: SKILL_ALREADY_EXISTS/INVALID_DIRECTORY_PATH/MANIFEST_VALIDATION_FAILED 文案); WelcomePage.tsx:317-321,326-330 (import 命中已存在→openSkill 重开); WelcomePage.tsx:174-182 (import_existing 不被支持的提示); services/skills.py:488-510,544-556 (后端各错误码来源)
- **FROZEN 改动**: D2: 删导入校验门后, 与 import 校验相关的错误退路(MANIFEST_VALIDATION_FAILED on import / 'missing GRAPH.md')随之移除。

### [live] [空态] 无任何 skill 时显示 'No skills found' 空态卡片(引导新建/打开)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D1)
- **动机**: 首次启动/清空后 Home 需给明确下一步(创建或打开), 避免空白迷茫。
- **证据**: WelcomePage.tsx:524-534 (visibleSkills.length===0→Empty 'No skills found'+'Create or import a skill')

### [target-design] [NFR 缺口] Recent 列表加载态(后端数据驱动组件应有 skeleton + lazy load; 当前 GET /skills 无 skeleton)
- **能力·区域**: `skill-workspace` · `welcome` — 目标: — (设计源 D6 / INDEX §11 NFR)
- **动机**: D6/INDEX §11(锁): 所有后端数据驱动组件必须 skeleton+lazy load。Recent 列表当前直接渲染, 加载期无骨架屏——属未落地的跨切 NFR, 在本节点登记为缺口(available models 巨长列表是首要, Recent 列表同此约定)。
- **证据**: WelcomePage.tsx:401-521 (列表直接 map visibleSkills, 无 isLoading/skeleton 分支); useSkills.ts:7-10 (SWR 仅 data/error, 无 loading skeleton 投影)

**跨切**: 1) 全局架构错配(最重要, 影响本节点几乎所有 status): 当前 Home/后端是**注册表模型**(MetadataStore: register/unregister/list_skills + skill index entries + 自动发现 unregistered; useSkills→GET /skills 聚合), 而 D1/D11(锁)要求 **skill-workspace 无注册表**(Home=打开文件夹+Recent(MRU)+ 子图按 path D7)。后果: 很多看似 'live' 的 Home 动作(Recent 列表内容、Delete=注销、import 注册)其底层机制需整体重塑→因此标 stale-doc/stale-code 而非 live。能力名已在 INDEX §6 从 skill-registry 重塑为 `skill-workspace`。

2) D12 写归属(写类动作统一): 新建脚手架/打开文件夹注册/删除 等所有**落盘**操作目标=经 Rust 文件命令(native-fs 唯一写者), 当前走 Python POST/DELETE /skills 的写路径标 stale-code; engine/gateway 才用 Python sidecar。本节点新建(create_new_skill 写文件)是首要受影响点。

3) D2 与 import 校验门冲突已坐实于代码: services/skills.py:517-522 硬拒缺 GRAPH.md/SKILL.md 的文件夹, 与'开任意文件夹即用'直接矛盾→该门(及配套 import-error 文案)是 FROZEN-改动外的纯实现删除项。

4) RuntimeGate 退役(D10 锁): App.tsx 仍用全屏 RuntimeGate gate 整个 UI; 目标=两 sidecar 启动期 Rust eager-spawn + 壳/FS 立即渲染 + skeleton + 全局就绪指示(非全屏 gate)。本节点标 stale-doc, 实现归 04_platform(native-fs 管 sidecar 生命周期)。

5) D3 外部 IDE 联动: openInCursor/Terminal/Codex 仍存在于 lib/tauri.ts:26-36(对应 Tauri 命令 open_in_cursor/terminal/codex), 但**前端零 UI 调用**(grep 仅自引用)——已是 orphan 死代码; D3 删除只需清掉这些未挂载 helper + 对应 Rust 命令, 不影响任何现有 Home/Workspace 旅程。故未单列为'动作', 在此备案。

6) 孤儿组件: components/WelcomeScreen.tsx 是 WelcomePage 的 no-op 包装(onSelectSkill=()=>undefined), 全仓仅其自身定义引用, 非挂载路径(orphan-unmounted); 真实挂载=Workspace.tsx:513。CopilotView 类型里残留 'WelcomeScreen' 字面量(types/copilot.ts:5)。

7) 多窗口(D9 决定做)在本节点无对应代码(单 App 实例); 归 04_platform(Rust 壳+无状态 sidecar)。本节点不含多窗口动作。

**待定**:
- Config drift 徽章(D1 标'存疑/待定'): 去注册表后是否保留这个 git-remote 比对告警? 若保留, 在 skill-workspace 模型下它的触发点/落点是什么(Recent 卡片? compile?)? 现为 live 端到端实现(WelcomePage.tsx:431-457 + config_arbitration.py), 需 PM 拍去留。
- Home 的 Recent 数据源: D1 锁'无聚合注册表 + Recent(MRU localStorage)', 但当前 Recent 卡片的丰富元数据(phase_count/last_run/has_golden/config_mismatch)来自后端 GET /skills 聚合。去注册表后这些元数据从哪来(Rust 按 MRU 路径逐个读 skill 目录? 还是 Recent 只存路径+名, 卡片退化为极简)? 影响 Recent 卡片信息密度与是否需后端调用(关联 D6 skeleton)。
- import 校验门删除范围(D2): services/skills.py:517-522 的'缺 GRAPH.md/SKILL.md 即拒'明确要删; 但 line 523-525 的'有 GRAPH.md 则 lint(不 raise)'是否也一并去掉(完全不在打开时做任何校验, 全交 compile)? D2 原话'有 compile 有 copilot 屎都改成标准 skill'倾向全删, 待确认。
- 新建 skill 的脚手架内容归属(D12 迁 Rust 后): 当前 _scaffold_files_for/write_skill_files_atomic 由 Python 生成默认 GRAPH.md 等(services/skills.py:558); 迁 Rust 后脚手架模板由谁持有(Rust 内置? 还是 D5 graph skill 在进入 workspace 后由 copilot 生成 SKILL.md, 新建时只建空文件夹)? 关联 01_init 与 02_authoring 的边界。

---

## 02_authoring — 编辑与编译(画布拓扑 / 节点编辑 / 编译门控)

**Scope**: 拥有「把业务逻辑转成严谨 graph_skill」的装配旅程 —— 宏观全局契约(GRAPH.md `name`/`schema_version`/`llm_role`/`description`/`phases`/`io`)、中观拓扑(连线/断连/新建 phase/子图 inline 容器展开 + 下钻)、微观节点编辑(Properties 白名单字段 + L3 步骤增删改序)、实时 compile/lint 门控(绿灯才解锁 Predict)。OWNS: `graph-authoring`(canvas REQ-1..10) + `phase-editing`(Properties 白名单 + io/artifact 设置, 对齐 FROZEN) + `file-editing`(Monaco/分屏/io) + `compile-lint`(lint/compile/门控) + `conflict-overwrite`(顺序覆盖)。
NOT-OWNS: 测试输入/predict 触发 → 03; 真实 run/运行态可视化 → 04; trace 去黑盒/resume → 05; golden/publish → 06; copilot 对话/inline diff → copilot spec; 文件树/.workspace 去黑盒 → asset-explorer。

> ⚠️ workflow agent 对本节点产出退化(`probe-17`, scope/跨切丢失)。本节点 scope/跨切由 orchestrator 据 [alignment-notes「批次2 Half A」](alignment-notes.md) + canvas-topology spec 重建; 动作行取 agent 残件(已含 file:line, 与 Half A 一致, 表述较简)。详尽 M1–M4 / T1–T7 / V1–V2 动作及证据见 alignment-notes 批次2 Half A 表。

### [target-design] M1
- **能力·区域**: `graph-authoring` · `canvas` — 目标: —
- **动机**: FROZEN header 无 type(workflow doc type=stale) 需结构化表单 现无 panel 只能裸开
- **证据**: GraphCanvas.tsx:397-405,423-429; FROZEN 02-graph-md-spec.md:12-20; workflow doc 02_authoring.md:31

### [stale-code] M2+M3 io 内联/schema-infer
- **能力·区域**: `file-editing` · `input` — 目标: —
- **动机**: M2 双击 IO 开 GRAPH.md=live; InputPanel 投影 io 成假文件=stale; M3 只读不写回 io
- **证据**: GraphCanvas.tsx:423-429; FROZEN 02-graph-md-spec.md:60,86-87; panel-files.ts:70-97+InputPanel.tsx:18-70,73-87

### [target-design] i/o panel 改名+artifact
- **能力·区域**: `phase-editing` · `input` — 目标: —
- **动机**: PM 锁 input 改 i/o panel 每节点 io+artifact 逐节点可设 现名仍 input 无 UI
- **证据**: InputPanel.tsx:78; alignment-notes G3; INDEX section6 region input
- **FROZEN 改动**: G3 io.outputs 加文件路径+schema 默认落 .workspace/artifacts; md 用 business_data_md 不回转

### [live] M4 IO 独立节点
- **能力·区域**: `graph-authoring` · `canvas` — 目标: —
- **动机**: FROZEN IO 也是独立节点 已渲染可双击
- **证据**: build-nodes.ts:203-217; GraphCanvas.tsx:423-429; FROZEN 02-graph-md-spec.md:44

### [target-design] REQ-1 TB 布局
- **能力·区域**: `graph-authoring` · `canvas` — 目标: —
- **动机**: LR 挤瘪面板 目标 TB 现仍 LR
- **证据**: lib/layout.ts:31 rankdir LR; SkillNode.tsx:82,132

### [live] T1+T2 连线/断连
- **能力·区域**: `graph-authoring` · `canvas` — 目标: —
- **动机**: 连线/断连 serialize 写回带 hash+回滚 写走 Python 目标 Rust
- **证据**: GraphCanvas.tsx:319-361,475-483; canvas-authoring.ts:68-127; Workspace.tsx:206-244→skills.py:122,366

### [target-design] T3 拓扑校验
- **能力·区域**: `graph-authoring` · `canvas` — 目标: —
- **动机**: 环 live 字段断层红叉前端无 REQ-2 改黑板可视化 旧类型红已删
- **证据**: GraphCanvas.tsx:217-243; ContextEdge.tsx:131-148; FROZEN 02-graph-md-spec.md:89-96

### [live] T4 新建 phase
- **能力·区域**: `graph-authoring` · `canvas` — 目标: —
- **动机**: 接线 live 脚手架 stale 写 mode/system_prompt/exit_contract/python_callable 违 FROZEN
- **证据**: GraphCanvas.tsx:485-498; Workspace.tsx:186-204; canvas-authoring.ts:143-189; FROZEN 05-agent:40-55,00:114

### [placeholder] T5 子图 inline
- **能力·区域**: `graph-authoring` · `canvas` — 目标: —
- **动机**: PM 锁 inline 展开 toggle live 但渲染写死假数据
- **证据**: SkillNode.tsx:116-131; SubgraphInline.tsx:19-23; build-nodes.ts:196-199
- **FROZEN 改动**: G2 删 04-subgraph io 1:1

### [target-design] T6 下钻+T7 bridge
- **能力·区域**: `graph-authoring` · `canvas` — 目标: —
- **动机**: T6 就地聚焦无下钻现状; T7 FROZEN SUBGRAPH.md 无 context_bridge
- **证据**: GraphCanvas.tsx:423-435; canvas requirement.md:92; FROZEN 04-subgraph:32-38

### [stale-code] Properties 编辑保存
- **能力·区域**: `phase-editing` · `properties` — 目标: —
- **动机**: 保存 live 但字段集全过时与 FROZEN 全冲突
- **证据**: PropertiesPanel.tsx:293-305,340-457,172-193; phase-frontmatter.ts:8-16,149,205-212

### [target-design] Properties 白名单重建
- **能力·区域**: `phase-editing` · `properties` — 目标: —
- **动机**: REQ-10 确认 batch-2 stale 现字段残缺; subagents 读取层过时 shape
- **证据**: FROZEN 05-agent:14-26,42-50/03-logic:35-41/04-subgraph:32-38; PropertiesPanel.tsx:392-444,64-101; build-nodes.ts:151-160
- **FROZEN 改动**: G2 删 io 1:1; D7 path

### [target-design] L3 步骤增删改序
- **能力·区域**: `phase-editing` · `canvas` — 目标: —
- **动机**: 右缘加号展开 body 步骤 走 Rust mutate_phase_body 现无 L3
- **证据**: SkillNode.tsx:116-131; canvas REQ-6 L3; FROZEN 05-agent:48,03-logic:64

### [live] Lint+Compile+错误面板
- **能力·区域**: `compile-lint` · `center-action-bar` — 目标: —
- **动机**: 防抖 lint+compileSkill 引擎真编译 CompileErrorPanel 渲染 live
- **证据**: useDebouncedLint.ts:48-49; Workspace.tsx:432-435,397-427,531-532/571→skills.py:109

### [placeholder] Predict 门控解锁
- **能力·区域**: `compile-lint` · `center-action-bar` — 目标: —
- **动机**: Compile 绿灯 Predict 解锁门控 live; 点击进入试飞归 03_predict 桩
- **证据**: center-action-bar.tsx:31-50,76-85; Workspace.tsx:537

### [live] 顺序覆盖冲突保存
- **能力·区域**: `conflict-overwrite` · `canvas` — 目标: —
- **动机**: 下游 io.outputs 与祖先同名覆盖风险 overlay Allow/Cancel 视口 pan 完整 live
- **证据**: canvas-authoring.ts:237-337; GraphCanvas.tsx:105-119,134-177; SkillNode.tsx:136-172

### [live] 失败退路 回滚/拒写/error/环阻断
- **能力·区域**: `graph-authoring` · `canvas` — 目标: —
- **动机**: 写失败回滚 hash 拒写 YAML 坏 error+Open file 环全屏阻断
- **证据**: GraphCanvas.tsx:354-360,217-226,381-387; Workspace.tsx:200-203,171; PropertiesPanel.tsx:306-321; phase-frontmatter.ts:46-72

**跨切**: ① [D12] 写全量 Rust: serialize_graph / mutate_phase_body / 新建 phase 写文件 / Properties 保存全经 Rust 文件命令(现走 Python `writeSkillFile` + `graph/serialize`, 标迁移)。② 读取层已 v030-aware(`CURRENT_SCHEMA_VERSION='v0.3.0'`), 但写入/脚手架/子图渲染层多为 V2.x `stale-code`: `defaultPhaseMarkdown` 写 mode/system_prompt/exit_contract/python_callable; `phase-frontmatter.ts` 字段集过时; `SubgraphInline` mock; `subagentsForPhase` 读过时 shape `phase_config.subagents`。③ FROZEN 改动落点集中本节点: 删子图 io 1:1(FROZEN-1)、io.outputs artifact(FROZEN-2)、REQ-2 字段勾选(FROZEN-4)。④ canvas REQ-7/8/9 覆盖核对: REQ-7 结构化 diff 归 trace(05/06); REQ-8 运行时策略开关(prompt_cache/compaction)= engine 未落地⏭️延后; REQ-9 = 右键新建节点(=T4, 已覆盖)。

**待定**: Half B 细化(Properties 白名单逐字段表单 / L3 步骤 Rust `mutate_phase_body` 事务粒度 / 子图 inline 容器布局态持久化 G1)留实现期; 新建 skill 脚手架归属(Rust 内置模板 vs copilot 生成)与 01_init 边界待定(见 01 待定#4)。

---

## 03_prediction — Predict (试飞/测试输入/拟真输出)

**Scope**: 本节点 = 烧真实 token 前的"试飞": 把测试语料喂进来 → 触发 predict(code 节点跑真 Python / agent 节点走 mock-llm) → 得到拟真 trace, 并守住"predict trace 不可固化为 golden"的红线。

【拥有(in scope)】predict 旅程的这些动作: ① 测试输入(test_inputs)导入/列出/删除/分类(json vs raw)——由 `predict` 能力的"测试输入"段拥有数据流; ② 触发单次 predict(选 json 输入→远程校验→postPredictRun); ③ agent 节点 mock-llm 策略选择(copilot_predict / heuristic-stub / golden-case); ④ predict→golden 守卫(409 `PREDICT_TRACE_CANNOT_BE_GOLDEN`, 后端已实现); ⑤ 批量 predict/run(一输入一运行 + 序列自动批量建议); ⑥ predict 失败退路(deadlock guard / 装载防崩 / 批量失败显式上报)。

【移交其他 spec / 不拥有(out of scope, 仅链接)】
- i/o panel **组件本身**(input region, 即将改名 i/o panel)→ `canvas` region + `graph-authoring`(canvas-topology REQ-2)。本节点只是该 panel 的一个"消费场景"(测试输入/导入落点)。
- predict 产出的**拟真 trace 可视化**(节点灯 / LangSmith 竖向时间轴 / Nudge 计数 / Payload schema)→ canvas-topology REQ-11/12/13 + `trace-observability` + `timeline` region。
- golden **固化/对比/打磨编排**(workflow doc §3 "对比与打磨视图" + Save as Golden)→ `golden-eval` 能力(judge 无主待建)。predict 只到"产出可被固化的 trace"为止, 且被 409 守卫挡住(必须走真实 Run, 见 cross_cutting)。
- 真实 **Run** 执行/WS 流/autocommit → `run-execution`(workflow Node 4)。
- compile/lint 门控与 stage 语义 → `compile-lint` + `center-action-bar` region。
- 文件标准化/格式转换(md_to_json 等)→ 引擎内置 tools(`packages/graph-agent`)。
- 节点级文件导入→黑板注入(G2 新需求)的**引擎/runtime 落地** → engine; 本节点只在 io 面板暴露"导入"入口动作。

【权威源】设计目标: `.kiro/specs/studio-feature-skill-lifecycle/`(已收敛为"测试输入+批量", 建议改名 test-inputs-batch)——但该 spec **明确把 compile/predict/run 叙事移交 skills.py**, 故 predict 触发/mock/golden-guard 的设计目标部分散落在 `docs/engine/public-api-contract.md`(predict_skill 签名 + RunResult.source + PhaseRecord.mocked_source)与 FROZEN `12-compile-runtime-flow-spec.md`(运行时流)。格式契约: FROZEN skill-spec。status: 当前代码。

### [backend-only] 在 i/o panel(测试输入区)点'导入' → Rust 原生文件/文件夹对话框选本地路径 → 路径交 Python sidecar 读入/拷贝进 .workspace/test_inputs/
- **能力·区域**: `predict` · `input` — 目标: skill-lifecycle requirement R1.1-R1.3 (导入=原生选路径, 非网页 multipart)
- **动机**: 本地桌面 app 的自然形态是'选路径→后端读入'而非浏览器 multipart; 让 PM 把语料喂进来是 predict 的前置。当前 create 是 501 桩, 导入入口在 UI 上尚不存在(InputPanel 无导入按钮)——需新建。
- **证据**: POST create_test_input=raise_not_implemented (routers/test_inputs.py:50-51); Rust 原生对话框 select_directory 已接通(spec design.md:34 引 tauri/src/lib.rs:94 pick_folder + lib/tauri.ts selectSkillDirectory); InputPanel.tsx:72-92 当前无导入 UI
- **FROZEN 改动**: G2 新需求: 任意 i/o 面板可导入文件=把文件字段注入黑板(同首 input 节点), 时机=a(跑到该节点才注入)。属引擎/runtime 改动, 登记 FROZEN 新版本清单第3条, 本节点仅暴露导入入口。

### [live] 查看 test_inputs 列表(文件名/大小/修改时间/内容预览)
- **能力·区域**: `predict` · `input` — 目标: skill-lifecycle requirement R1.4 (列出物料+元数据)
- **动机**: PM 需看到已导入哪些测试语料才能选择跑哪个; 这是 predict/批量的选择基础。当前 list 已实现但只 glob *.json, 漏掉 .md/.txt 原始物料。
- **证据**: list_test_inputs live 但 glob '*.json' only (routers/test_inputs.py:31); _preview_json 已对非 JSON 回退原文 (test_inputs.py:63-69); TestInputMetadata 模型 (models/test_inputs.py)

### [backend-only] 删除某个测试输入 → 从 test_inputs 移除并刷新列表
- **能力·区域**: `predict` · `input` — 目标: skill-lifecycle requirement R1.5 (删除物料)
- **动机**: 语料管理需要清理过时/错误的测试输入。当前 delete 是 501 桩, 无可用删除路径。
- **证据**: DELETE delete_test_input=raise_not_implemented (routers/test_inputs.py:59-60)

### [target-design] 系统按扩展名给测试输入标 kind(json=结构化输入 / raw=原始物料), UI 分区呈现避免混淆
- **能力·区域**: `predict` · `input` — 目标: skill-lifecycle requirement R2.1/R2.3 (区分物料与结构化输入, 分区呈现)
- **动机**: 放宽 list glob 到 * 后, 若 .md/.txt 直接流入仅认 JSON 的装载路径(_load_test_input 硬 json.loads)会崩。先在数据层打 kind 标签 + UI 分区, 是'防崩'的基础。当前 TestInputMetadata 无 kind 字段, UI 无分区。
- **证据**: TestInputMetadata 当前无 kind (models/test_inputs.py); _load_test_input 硬 json.loads (services/run_manager.py:566 per spec design.md:36); 无前端 kind 分区 UI

### [live] compile 通过后 Predict 按钮亮起(stage 门控: idle→compiling→compile-pass 才点亮 Predict)
- **能力·区域**: `predict` · `center-action-bar` — 目标: FROZEN 12-compile-runtime-flow-spec (编译期先于执行); workflow doc §2 (Compile 通过→Predict 亮)
- **动机**: 烧 token/跑逻辑前必须先编译通过, 防止对坏图试飞。按钮高亮/禁用的 stage 派生是 live 的。
- **证据**: deriveButtons: compile-pass/predicting/predict-fail → predictHighlight:true predictDisabled:false (center-action-bar.tsx:42-50); deriveBuildStage 从 lint/compileStages 推 (Workspace.tsx:429-437); setCompileStages 设 compiling/compile-fail/compile-pass (Workspace.tsx:400-419)

### [placeholder] 点击 [Predict] 触发试飞 → 当前是 console.info('predict clicked') 空桩, 不发请求、不推进 stage
- **能力·区域**: `predict` · `center-action-bar` — 目标: skill-lifecycle (predict 触发, 叙事移交 skills.py); public-api-contract predict_skill 签名; workflow doc §2 分支A 步骤1
- **动机**: 这是 predict 旅程的核心动作, 但目前完全未接线: onPredict 是桩, 既不调用已存在的 postPredictRun API, 也不把 stage 推进到 predicting/predict-pass。后果: Predict 点了没反应, 且因 predict-pass 永不置位, Run 按钮的 stage 门控永远 runDisabled=true(Run 经此门控不可达)。
- **证据**: onPredict={() => console.info('predict clicked')} (Workspace.tsx:537); setCompileStages 从不设 predicting/predict-pass/predict-fail/running (Workspace.tsx:400-419 grep 证实); deriveButtons run 段需 stage 越过 predict-pass (center-action-bar.tsx:52-59)

### [orphan-unmounted] 选 JSON 测试输入 → 加载即过 Schema 校验 → 点 Validate input(远程校验) → 提交 payload
- **能力·区域**: `predict` · `input` — 目标: skill-lifecycle requirement R1.1 (加载瞬间通过 Schema 校验); workflow doc §3 (即时 Schema 校验反馈)
- **动机**: 试飞前确认输入符合技能 io.inputs schema, 避免跑到一半因输入不合法报错。承载此动作的 PredictInputDialog 已完整构建(JSON 编辑 + inferJsonSchema 预览 + validateRemote)但无任何 importer, 不可达; 且其 validateRemote 调用 shape 与后端不符。
- **证据**: PredictInputDialog 零 importer (grep 证实仅自身+test); validateRemote POST /skills/{id}/validate_input 传 values JSON (useInputPlayground.ts:179-181); 但后端 validate_input 期望 {input_file_path:str} + 云存储 deps (routers/skills.py:454-473, models/validation.py:13) = 契约不匹配, 即便挂载也跑不通

### [backend-only] 提交 predict 请求 → POST /skills/{id}/runs/predict(带 input_data/mock_llm/current_hashes)→ 引擎按拓扑跑, 持久化 result.json
- **能力·区域**: `predict` · `center-action-bar` — 目标: public-api-contract predict_skill (copilot_predict 参数, unattended=True); FROZEN 12 运行时引擎流
- **动机**: predict 的后端编排是 live 的(PredictorService.dispatch_predict_job 调 predict_skill, 持久化 result.json), 但前端无任何调用方: postPredictRun API 方法已写好却零 caller。这是'后端就绪、前端缺触发'的典型断层。
- **证据**: predict_run 路由 live (routers/runs.py:32-41); PredictorService.dispatch_predict_job 调 predict_skill + _persist_predict_result (services/predictor.py:41-128,134-140); postPredictRun API 已写 (api/client.ts:134-139) 但零 caller (grep 证实)

### [backend-only] Code-only(logic)节点跑真实 Python 逻辑(动作链+validator), 验证数据组装/工具函数无报错
- **能力·区域**: `predict` · `canvas` — 目标: FROZEN 12-compile-runtime-flow-spec (LOGIC 节点: action 链+validator); workflow doc §2 底层机制
- **动机**: predict 的价值之一就是不烧 token 也能验证 Python 侧逻辑(logic 节点照常真跑)。引擎层 predict_skill 已实现此行为; 前端无触发+无可视化。
- **证据**: FROZEN 12 LOGIC 节点契约 (12-compile-runtime-flow-spec.md:117-120); predict 经 predict_skill 真实执行 (services/predictor.py:114-123); PhaseRecord.type Literal['logic','llm'] (public-api-contract)

### [backend-only] Agent-Loop 节点走 mock-llm(copilot_predict/heuristic-stub/golden-case 策略)返回拟真/占位结果, 不烧线上 token
- **能力·区域**: `predict` · `canvas` — 目标: public-api-contract predict_skill(copilot_predict 参数) + PhaseRecord.mocked_source Literal['golden_case','copilot','heuristic_stub','manual']
- **动机**: predict 的核心省钱机制: agent 节点不调真模型, 由 mock 策略产出拟真结果。引擎已支持多种 mocked_source; 但 PredictRunRequest.mock_llm 是 Any=None, 前端需选策略却无 UI 选择器——mock-llm 策略选择动作在前端完全缺失。
- **证据**: PredictRunRequest.mock_llm: Any = None (models/runs.py:34); predict_skill 有 copilot_predict 参数 (public-api-contract.md:43); mocked_source 4 值含 copilot/heuristic_stub/golden_case (public-api-contract PhaseRecord); _predict_internal 策略 GoldenCaseStrategy/HeuristicStubStrategy (public-api-contract.md:352-403); 前端无 mock 策略选择器 (grep 无 mock_llm UI)

### [orphan-unmounted] predict 跑完 → 拟真 trace 在画布/时间轴上可视化(节点灯/竖向时间轴/拟真来源标记)
- **能力·区域**: `trace-observability` · `timeline` — 目标: canvas-topology REQ-11 (运行态只读节点内联展开, LangSmith 竖向时间轴); 移交 trace-observability
- **动机**: PM 看 predict 结果需要可视化(哪些节点 mock、路径是否符合预期)。前端已有 predict-aware trace 工具(isPredictTrace/isMockedSource)与 TracePanel/useRunStream, 但全是 zombie(零引用未挂载)。此动作主体归 canvas/trace-observability, 在 predict 节点仅作'产出后看结果'链接。
- **证据**: utils/trace.ts predict 工具 live: isPredictTrace/isPredictRootEvent/isMockedSource (utils/trace.ts:63-76); TracePanel + useRunStream 零引用未挂载 (grep 证实; alignment-notes:190 标 zombie 需接线); RunResult.source Literal['run','predict'] + path_diff (public-api-contract)

### [target-design] (分支A)predict 跑完自动展开'对比与打磨视图'(左拟真输出/右 baseline 草稿 + copilot 侧栏)→ Save as Golden 固化基线
- **能力·区域**: `golden-eval` · `properties` — 目标: golden-eval(judge 无主待建); workflow doc §3 沉浸式打磨区 + §2 分支A
- **动机**: workflow doc 把'predict→打磨→Save as Golden'画成标准路径, 但: ① 前端无任何对比/打磨/Save-as-Golden UI(零实现); ② 更关键——后端有硬守卫禁止 predict trace 固化为 golden(见下一条)。故此 doc 叙事是 target-design 且与后端语义冲突, 实际 golden 必须走真实 Run(分支B)。归 golden-eval 能力。
- **证据**: 前端无 Save-as-Golden/对比打磨 UI (grep saveasgolden/对比打磨/GoldenPolish/CompareView 全空); saveGoldenBaseline/listGoldenBaselines API 已写但零 caller (api/client.ts:141-152)

### [backend-only] predict→golden 守卫: 把 predict 来源 trace 提交固化时, 后端 409 拒绝(PREDICT_TRACE_CANNOT_BE_GOLDEN)
- **能力·区域**: `predict` · `properties` — 目标: public-api-contract RunResult.source / PhaseRecord.mocked_source(predict 与 run 区分); 守卫实现 diagnostic_export
- **动机**: 拟真输出含 mock 数据, 当作'完美锚点'会污染质量基线——所以引擎硬性禁止 predict trace 升级为 golden。此守卫后端已实现且会 409, 但前端无 UI 触发/无错误呈现。它直接反驳 workflow doc §3 分支A的'predict→Save as Golden'叙事: golden 只能来自真实 Run(分支B)。
- **证据**: assert_trace_can_be_promoted_to_golden → 409 PREDICT_TRACE_CANNOT_BE_GOLDEN not_retryable (services/diagnostic_export.py:25-42); set_golden_baseline_for_run 在固化前调此守卫 (services/golden_diff.py:43-47); _is_predict_trace 检测 is_predict 标记 (diagnostic_export.py:45-55)

### [orphan-unmounted] 选多个测试输入触发批量运行(一输入一运行)→ POST /runs/batch-run → 轮询 /batch/{id} 进度
- **能力·区域**: `run-execution` · `input` — 目标: skill-lifecycle requirement R3.1 (批量=每输入各发起一次运行)
- **动机**: 1000 章规整语料需要批量试飞/运行。前端 useBatchRun + BatchRunner 已完整实现(选输入→POST batch-run→轮询)但未挂载; 后端 batch-run 路由 live。批量更偏 run-execution 能力, 但触发入口落在测试输入面板。
- **证据**: useBatchRun 完整: runBatch POST /skills/{id}/runs/batch-run + poll /batch/{id} (hooks/useBatchRun.ts:73-90,33-63) 但 BatchRunner 未挂载 (grep 证实); 后端 create_batch_run live (routers/runs.py:48-49)

### [target-design] 导入文件呈统一命名数字序列(chapter1/chapter2…)时, 系统识别并建议自动开启批量, 默认运行数=文件数
- **能力·区域**: `run-execution` · `input` — 目标: skill-lifecycle requirement R3.2/R3.3 (序列检测建议自动批量; 假定命名规整)
- **动机**: 降低批量配置负担——序列文件天然成批。这是纯前端便利(不改后端运行语义), 当前无任何序列检测实现。spec 明确假定输入干净, 不为脏数据过度设计。
- **证据**: spec design.md:91-96 (序列检测=前端便利, 不改后端); 前端无序列检测逻辑 (grep 无相关实现); BatchRunner 本身未挂载

### [target-design] 批量运行中某输入失败 → 显式报告失败项(不静默跳过, WARNING 日志 + UI 可见)
- **能力·区域**: `run-execution` · `input` — 目标: skill-lifecycle requirement R3.4 (批量失败显式上报)
- **动机**: 失败退路: 批量跑 N 个不能静默吞掉失败项, 否则 PM 误以为全成功。属失败可观测性要求; 当前 BatchRunner 未挂载, 此 UI 行为无实现。
- **证据**: spec design.md:104-105 (显式报告失败项+WARNING); BatchRunner 未挂载; useBatchRun 仅记 batchError 总错 (hooks/useBatchRun.ts:84-87) 无逐项失败上报

### [target-design] (失败退路)raw 物料误入仅认 JSON 的装载路径时不崩 → 按 kind 分流, 仅 kind=json 进 _load_test_input
- **能力·区域**: `predict` · `input` — 目标: skill-lifecycle requirement R2.2 (raw 不进 JSON-only 装载路径)
- **动机**: 防崩: 放宽 list glob 到 * 后, .md 流入硬 json.loads 会抛 ValueError 整批崩。需在装载前按 kind 分流。当前 _load_test_input 无 kind 分流。
- **证据**: _load_test_input 硬 json.loads, start_batch_run 消费 (spec design.md:36 引 run_manager.py:566,239); 无 kind 分流逻辑

### [backend-only] (失败退路)predict 中 heuristic-stub 把路由困在环里 → P2 deadlock guard 触发(某 phase 重访超阈值即报错)
- **能力·区域**: `predict` · `center-action-bar` — 目标: public-api-contract predict_skill(unattended predict 行为); 引擎 P2 启发式桩
- **动机**: predict 用占位结果驱动 agent 路由时, 桩可能让条件路由死循环。引擎有死锁守卫(MAX_PHASE_REVISITS=10)显式报错而非挂死, 是 predict 的安全网。前端无此错误呈现。
- **证据**: PredictDeadlockError + MAX_PHASE_REVISITS=10 (services/predictor.py:20-32); dispatch_predict_job 捕获 SDK 死锁转抛 (predictor.py:124-125)

### [target-design] (失败退路)predict 写文件撞覆盖白名单 hash 冲突(403/409)→ 提供重新加载, 或后端原子 read-modify-write 加白名单字段
- **能力·区域**: `conflict-overwrite` · `properties` — 目标: skill-lifecycle design §5 / DEF-011(原 S1 覆盖白名单 hash, 降级为独立本地小修)
- **动机**: predict 携带 current_hashes 做乐观并发; 外部也改了同一文件会撞冲突。spec 把此事(原 S1)移出 predict 主线、降级为独立本地小修(DEF-011, owner 待定)。归 conflict-overwrite 能力, 在 predict 节点仅作失败退路链接。
- **证据**: PredictRunRequest.current_hashes 透传 (models/runs.py:35, predictor.py:47,58,118); spec requirement.md:19 + design.md:111-117 (S1 移出→DEF-011 独立小修)

**跨切**: 【最关键矛盾 — workflow doc §3 分支A 与后端守卫直接冲突】03_prediction.md 把 "Predict → 同步打磨 Mock Golden → Save as Golden" 画成"标准稳健路径"(分支A)。但后端 `assert_trace_can_be_promoted_to_golden` (diagnostic_export.py:25-42) 会对任何 predict 来源 trace 返回 409 `PREDICT_TRACE_CANNOT_BE_GOLDEN`(not_retryable)。即: predict trace **设计上禁止**固化为 golden。结论: golden 必须走真实 Run(workflow doc 分支B), 分支A 的 doc 叙事是 STALE / 与实现相反。建议在新 spec/迁移时裁定: predict 只产出"可检视的拟真 trace", golden 固化整段归 golden-eval 且只接受 run-source。

【Run 经 stage 门控不可达】center-action-bar 的 Run 按钮要求 stage 越过 predict-pass(center-action-bar.tsx:52-59), 但 Workspace 的 setCompileStages 从不设 predicting/predict-pass/predict-fail/running(只设 compile-*, Workspace.tsx:400-419), 且 onPredict 是 console.info 空桩。后果: 即便 compile 通过, Predict 点了无反应、stage 停在 compile-pass、Run 永远 runDisabled=true。predict 接线时必须把 stage 机推进到 predict-pass 才能解锁 Run(否则 Node 4 入口经此门控死锁)。

【predict 是"半身不遂": 后端 live / 前端断头】后端 predict 全链路就绪(predict_run 路由 + PredictorService + predict_skill + 持久化 result.json + 409 守卫 + 死锁守卫 + batch-run)。前端对应件大多已写但全是孤儿或空桩: onPredict 桩(Workspace.tsx:537)、postPredictRun/saveGoldenBaseline/listGoldenBaselines 零 caller(client.ts:134-152)、PredictInputDialog/InputPlayground/BatchRunner 未挂载、TracePanel/useRunStream zombie。predict 节点的工程实质 = "把已存在的后端能力接到 UI 上 + 补 mock 策略选择器 + 接 stage 机"。

【D12 写入归属】本节点写类动作(导入 test_inputs 落盘、create/delete test_input、predict result.json 持久化、golden 固化落盘)按 D12 统一标"经 Rust 文件命令": .workspace/test_inputs、.workspace/runs、.workspace/golden 的读写全归 native-fs(Rust); 仅 predict_skill 执行(engine)+ mock-llm 经 gateway 走 Python sidecar。skill-lifecycle design D1 主张的"Python 独占 .workspace 写"已被 D12 覆盖(改 Rust)。

【input region 即将改名 i/o panel】本节点多个动作落在 `input` region(测试输入导入/列出/删除/kind 分区)。PM 已定 input region → i/o panel(INDEX region 表待改), 每节点 io 设置 + artifact 落盘设置都在此 panel。本节点的"测试输入"段是 i/o panel 的一个使用场景, panel 组件本身归 canvas/graph-authoring。

【schema-infer 倾向弃用】InputPanel 的 SchemaInferPanel(拖/粘 JSON→推 schema)是死路 `<pre>`(不写回 io, InputPanel.tsx:18-70), 且 PredictInputDialog 里的 inferJsonSchema 同样只读预览。canvas REQ-2 改为"黑板字段勾选"后, paste-infer 倾向废弃(alignment-notes:189 Q-C)。predict 选输入不应依赖 schema-infer。

**待定**:
- 改名确认: skill-lifecycle spec 自身建议改名 studio-feature-test-inputs-batch(design §8 开放项1); 若改, 本节点 target_spec 引用与 INDEX 映射需同步。
- predict 触发的入口落点未定: 是复用孤儿 PredictInputDialog(需修 validateRemote 与后端 {input_file_path} 契约不匹配 + 挂载), 还是改为'在 i/o panel 选已导入的 test_input 文件→直接 predict'(更贴合 spec 的'选路径而非动态表单'方向)? 后者更一致但 PredictInputDialog 整件可能废弃。
- mock-llm 策略选择 UI 缺失: PredictRunRequest.mock_llm=Any=None, 引擎支持 copilot/heuristic_stub/golden_case 三种 mocked_source, 但前端无策略选择器。predict 默认用哪种 mock? 是否暴露给 PM 选(如'用某个 golden case 当 mock')? 需新 spec 定义此交互。
- workflow doc §3 分支A(predict→Save as Golden)与后端 409 守卫冲突已确认 STALE。需 PM/新 spec 裁定: 是删除分支A 叙事(golden 只走 run-source), 还是放宽守卫允许某种'手工修正后的 predict trace'晋升? 默认按后端守卫(禁止)处理。
- validate_input 双重契约: 孤儿 PredictInputDialog POST 原始 JSON values 到 /validate_input, 但后端期望 {input_file_path:str} + 云存储 deps(get_storage/get_auth_user_id, routers/skills.py:454-473)。此后端端点像是云/多租户残留, 与本地单用户 Tauri 模型不符。predict 输入校验该走哪条路径需澄清(本地路径校验 vs 云存储校验)。
- 节点级文件导入→黑板(G2 新需求, 时机=a)的引擎落地未实现, 已登记 FROZEN 新版本清单第3条。i/o panel 的'导入'入口动作(本节点 backend-only 那条)依赖此引擎能力; 引擎未落地前前端导入按钮只能落到 test_inputs 拷贝, 不能真正注入黑板。

---

## 04_execution — Run(真实运行/状态流/批量/运行态可视化)

**Scope**: 本节点拥有「真实运行的触发 + 运行态流式观察 + 批量运行 + 运行态画布可视化」这条用户旅程。OWNS(链接, 不重述组件): run-execution 能力(触发/WS流/autocommit/batch/run历史), trace-observability 能力(运行时实时trace控制台/节点过滤/边state黑板/Prompt透视/节点灯/微观拓扑) 在 canvas+timeline+properties+editor 区域的运行态投影, canvas 能力的运行态部分(REQ-11..14 只读内联展开/Nudge/Payload schema/性能)。
NOT-OWNED(移交其他节点/spec): (1) 测试输入的导入/列出/删除 + raw/json 分区 = 02_authoring/predict 准备期(skill-lifecycle spec R1/R2), 本节点只消费已存在的 test_inputs 触发 batch; (2) compile 门控与 stage 推导(center-action-bar 的 stage 逻辑)= 02_authoring/compile-lint; (3) predict 试飞(mock_llm/拟真)= 03_predict 节点(predict 能力), 本节点只负责真实 run; (4) 运行失败后的 HitL 干预/节点级 Resume/篡改 state 续跑 = 05_debugging 节点(debug-resume 能力, resume 端点 501); (5) 运行成功后的 golden 固化/eval = 06_eval 节点; (6) 子图 inline 展开/下钻的编辑态语义 = 02_authoring(canvas REQ-6); 本节点只用其运行态只读 mode(REQ-11, 共用UI组件 DECISION-CANVAS-09); (7) 运行态微观事件的后端装配(engine run_manager)= engine spec, 本节点只定义/消费前端 Payload schema 契约(canvas REQ-13)。
权威序已遵循: status 全部亲读当前前后端代码并配 file:line; 格式/字段以 FROZEN + spec 为目标; workflow doc(04_execution.md)仅取动作骨架(其"VS-Code/Canvas-first 双流派 Trace 布局""context_bridge"措辞已 STALE — canvas spec REQ-1 锁 TB 布局、REQ-2 删类型红改黑板字段勾选、G2 删子图 io 1:1 故无 context_bridge)。

### [placeholder] 点击中心动作条 [Run] 按钮触发真实运行(compile-pass 后高亮可点)
- **能力·区域**: `run-execution` · `center-action-bar` — 目标: skill-lifecycle (run 触发, 叙事仍归 skills.py); canvas REQ-(运行态入口)
- **动机**: Run 是本节点的入口动作: 用真实大模型跑通过编译的 skill。按钮与 stage 门控(只在 run 阶段高亮/可点)是旅程脊柱的起点, 必须穷举为第一动作。
- **证据**: Run 按钮 live: apps/studio/frontend/src/components/studio/center-action-bar.tsx:86-95(Play 图标 + runDisabled/runHighlight 由 stage 派生, line 52-59); 但回调是桩: apps/studio/frontend/src/components/studio/Workspace.tsx:538 `onRun={() => console.info("run clicked")}`

### [placeholder] 前端把当前测试输入 POST /skills/{id}/runs 发起单次运行, 拿到 run_id 与 running 元数据
- **能力·区域**: `run-execution` · `center-action-bar` — 目标: skill-lifecycle (单次运行); public-api-contract POST /runs
- **动机**: onRun 点击后必须真正调后端起 run — 这是 console.info 桩与真实运行之间缺失的接线。API 客户端已备好但无人调用, 是接线 gap 的核心证据。
- **证据**: API 客户端已实现但零调用: apps/studio/frontend/src/api/client.ts:154 `startRun(skillId, inputData)` → POST `/skills/${skillId}/runs`; grep 全仓 `startRun(` 无业务调用方(仅定义处)。后端 live: apps/studio/backend/app/routers/runs.py:27-29 `create_run` → run_manager.start_run

### [live] 后端 spawn 子进程跑 graph_agent.run_skill(真实引擎+gateway 模型解析), 落盘 final_state/metrics/trace.jsonl
- **能力·区域**: `run-execution` · `engine` — 目标: execution-runtime/baseline; skill-lifecycle
- **动机**: 真实运行的实质 = 调 engine 跑 agent-loop。需标注这是 D12 两块 Python sidecar 之一(engine 调用 gateway), 与本地 FS 写入(D12 归 Rust)区分; 也是 trace 数据的来源。
- **证据**: apps/studio/backend/app/services/run_manager.py:81-130 `_run_worker_main` 调 `run_skill(... model_resolver=build_gateway_model_resolver(), skill_resolver=build_studio_skill_resolver(), event_subscriber=emit_to_queue)`; start_run spawn 进程 run_manager.py:200-206; 写 final_state.json/metrics.json run_manager.py:108-109
- **FROZEN 改动**: D12: 引擎 run_skill 留 Python sidecar(允许); 但 .workspace/runs 目录(run_dir/input_data.json/final_state.json/metrics.json/trace.jsonl)的读写归 native-fs(Rust)— 当前由 Python run_manager._write_json 写(run_manager.py:130,190,108-109), 目标改经 Rust 文件命令收口

### [placeholder] 运行状态指示(Running/Paused/Failed/Success)实时显示在画布节点或动作条
- **能力·区域**: `run-execution` · `center-action-bar` — 目标: skill-lifecycle (运行状态); canvas REQ-11(运行态)
- **动机**: workflow doc §2.1 要求运行状态指示。stage 机里有 'running'/'run-fail' 态且 SkillNode 有 Running/Paused 徽章样式, 但无 live run 推动它们 — 旅程必经的'我现在在跑'反馈缺失。
- **证据**: stage 含 running/run-fail: center-action-bar.tsx:11-13; SkillNode 状态样式 running/paused/breakpoint 已定义: apps/studio/frontend/src/components/nodes/SkillNode.tsx:11-40; 但 deriveBuildStage 不消费 live run 事件(Workspace.tsx:535 stage 来自编译态), statusByNodeId 未接 live(见下条)

### [placeholder] 运行时画布节点亮起'呼吸灯'+红绿状态(idle→running→success/error), 随执行进度逐节点点亮
- **能力·区域**: `trace-observability` · `canvas` — 目标: trace-inspector REQ-1(突出 phase 边界/红灯); canvas REQ-11
- **动机**: 去黑盒的第一层: PM 在大图上一眼看到跑到哪、哪个节点红了。节点状态 UI(动画/图标/配色)齐全, 但 GraphCanvas 渲染处根本没传 live statusByNodeId, 只能显示硬编码兜底态 — 这是'UI 在但无 live 数据'的典型 placeholder。
- **证据**: Workspace.tsx:515-519 渲染 `<GraphCanvas>` 未传 statusByNodeId prop → GraphCanvas.tsx:195 `safeStatusByNodeId = statusByNodeId ?? {}`; build-nodes.ts:193 兜底 `statusByNodeId[phase.name] ?? (index === 0 ? 'success' : 'idle')`; 状态样式 live: SkillNode.tsx:11-40(running=animate-pulse-primary 等)

### [target-design] 运行时 focus 自动跟随当前运行节点(进子图则 focus 到子图具体节点, 无需先展开)
- **能力·区域**: `trace-observability` · `canvas` — 目标: canvas REQ-(运行态导航) / alignment-notes G9
- **动机**: G9 锁定需求: 运行时镜头跟随执行节点, 大图很宽时不至于跟丢。当前 fitView 只在拓扑变更时触发, 无任何'跟随活跃节点'逻辑 — 纯目标设计, 代码零对应。
- **证据**: GraphCanvas.tsx:125 fitView 在初始化/拓扑变更触发; :438 `fitViewRef.current = () => instance.fitView(...)`; :181 fitViewRef 仅在节点集合变化调用; grep canvas 无 setCenter/活跃节点 follow 逻辑

### [orphan-unmounted] 运行时 Trace 控制台实时流入事件(phase 边界/llm_call/tool_call/nudge/validator/token·耗时), 突出关键信息
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector REQ-1 (P1, design §2 挂载 TracePanel + 新增 useRunTrace)
- **动机**: 去黑盒的核心组件(trace-inspector REQ-1): 唯一控制台, 运行时实时看每一步。组件 + WS hook 全已实现且功能完整(搜索/过滤/虚拟列表), 但零引用挂载, PanelKind 也无 'trace' 槽 — 最大的'僵尸已实现'孤儿。
- **证据**: TracePanel 零引用: apps/studio/frontend/src/components/TracePanel.tsx:22(含 TraceSearchBar/TraceFilter/VirtualTraceList); useRunStream 零引用: apps/studio/frontend/src/hooks/useRunStream.ts:12; PanelKind union 无 trace: apps/studio/frontend/src/components/studio/Toolbar.tsx:7; 后端 WS live: apps/studio/backend/app/routers/websockets.py:27-39 `/ws/runs/{run_id}`

### [placeholder] 运行结束后从 Run 历史列表回看同一 Trace 控制台(点历史卡片 → 载入该 run 的 events)
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector REQ-1 / design §2 (TimelinePanel 卡片加 onClick)
- **动机**: trace-inspector REQ-1 的非运行时分支: 历史回看。TimelinePanel 已是 live 历史列表(真实 useRunHistory), 但卡片只有 cursor-pointer 样式、无 onClick 进 trace — 列表能看不能进, 接线缺失。
- **证据**: TimelinePanel live 挂载: apps/studio/frontend/src/components/studio/panels/Panels.tsx:38; 用真实数据: apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:34 `useRunHistory(currentSkillId)`; 卡片 line 71-95 有 `cursor-pointer hover` 但无 onClick→trace(design.md:40 命补 onClick→setActiveRunId+onPanelChange('trace'))

### [live] Run 历史列表(run_id/状态图标/相对时间/耗时/token)读取并刷新
- **能力·区域**: `run-execution` · `timeline` — 目标: skill-lifecycle (run 历史) / public-api GET /runs
- **动机**: PM 跑完要能看到历史运行记录。这是本节点少数完全接通的能力(真实 GET /runs + 刷新), 作为 live 基线锚定, 也是回看 trace 的入口载体。
- **证据**: TimelinePanel.tsx:32-101 渲染列表 + Refresh 按钮(:44-53); useRunHistory live: apps/studio/frontend/src/hooks/useRunHistory.ts:13 `useSWR<RunListResponse>('/skills/${skillId}/runs')`; 后端 list_runs live: runs.py:43-45

### [stale-doc] Toolbar 'Trace Timeline' 按钮打开该面板(命名混淆: 标签是 Trace Timeline 实为 run 历史列表)
- **能力·区域**: `run-execution` · `shell-layout` — 目标: trace-inspector (regions/timeline 文档命澄清两者)
- **动机**: INDEX §9 已登记的命名漂移: Toolbar 把 run 历史列表(TimelinePanel)标成 'Trace Timeline', 而真正流式 TracePanel 未挂载。穷举入口动作时必须标出这个误导, 接 trace 时要澄清两者。
- **证据**: Toolbar.tsx:19 `{ id: "timeline", icon: Clock, label: "Trace Timeline", shortcut: "4" }` → 实际渲染 TimelinePanel(只读历史 Panels.tsx:38), 非流式 TracePanel

### [orphan-unmounted] 画布选中某节点 → Trace 控制台只显示该节点的 trace(按 phase_name 过滤)
- **能力·区域**: `trace-observability` · `canvas` — 目标: trace-inspector REQ-2.1 / design D1
- **动机**: trace-inspector REQ-2 findability: 海量日志里定位单节点。过滤机制(useTraceFilter/activePhase)已在未挂载的 TracePanel 内实现且契约已验证(selectedNode.id == phase_name), 随 TracePanel 一起是孤儿。
- **证据**: TracePanel 内 useTraceFilter 支持 activePhase(TracePanel.tsx:22 引入); 契约已验证 design.md:54 `selectedNode.id == phase.name`(build-nodes.ts:183/utils/graph.ts:41); 但 TracePanel 整体零引用(同上)

### [orphan-unmounted] Trace 控制台内按事件类型(llm_call/tool_call/error/state)与关键字检索定位
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector REQ-2.2
- **动机**: trace-inspector REQ-2.2: '找得到那一条'。检索/筛选 UI 已在 TracePanel 内实现完整, 同属未挂载孤儿 — 穷举查找类动作时不可漏。
- **证据**: TracePanel.tsx:22 含 TraceSearchBar/TraceFilter/VirtualTraceList; 组件零引用(grep TracePanel 仅定义处)

### [placeholder] 点击连线中心 dot → 弹出该边 A→B 的 state 黑板卡片(真实 blackboard 状态)
- **能力·区域**: `trace-observability` · `canvas` — 目标: trace-inspector REQ-3 / design D2 (buildEdgeContext 替换 mock)
- **动机**: trace-inspector REQ-3/4 + workflow §2.3: 验证数据流转的最直观抓手。dot 与点击交互 live, 但弹的是 getMockEdgeContext() 纯造假数据并倒进 Properties — '入口在、数据假'的 placeholder/mock, 是 trace 接真实数据的关键改造点。
- **证据**: apps/studio/frontend/src/components/edges/ContextEdge.tsx:30-104 `getMockEdgeContext`(完全捏造 inputs/phase_outputs/scratch); dot onClick line 213-225 → setSelectedEdge(mockJson) + `onPanelChange('properties')`(line 223); hasTraceData 硬编码: apps/studio/frontend/src/components/nodes/buildEdges.ts:26 `hasTraceData: isTestEnv ? false : !isGlobal`(非 live run 派生)
- **FROZEN 改动**: G2: 删 FROZEN 子图 io 严格 1:1 后, 黑板卡片语义 = 从黑板按 io.inputs 切片(REQ-2), 而非父子 1:1 映射; workflow doc §2.3 'context_bridge' 措辞 STALE(已无 context_bridge)

### [target-design] 点击 state 黑板卡片 → 进入编辑器(只读)看该刻黑板完整详情(深层可折叠)
- **能力·区域**: `trace-observability` · `editor` — 目标: trace-inspector REQ-3/REQ-4 / design D4
- **动机**: trace-inspector REQ-3/4 第二跳: 卡片→只读 Monaco 看全量 state。EdgeStateCard + 只读编辑器组件 design.md 明确标'无/新增', 代码零对应 — 纯目标设计。
- **证据**: design.md:45 `EdgeStateCard + 只读编辑器 | 无 | 新增`; grep 前端无 EdgeStateCard 组件; 当前 dot 只倒 mock 进 Properties(ContextEdge.tsx:223), 无只读编辑器路径

### [backend-only] 节点在 Trace 流中抛出 context 变化/working_memory/state 快照作为可见条目, 点击跳编辑器看状态
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector REQ-4
- **动机**: trace-inspector REQ-4: state snapshot 是 trace 一等内容。引擎已把完整黑板快照落进 trace.jsonl(phase_start/end 带 context), 但前端无任何条目渲染/跳转 — 后端数据齐、前端无 UI。
- **证据**: 引擎 events 携带快照(spec requirement.md:36-39 phase_start/phase_end 带 `context={inputs,phase_outputs,scratch}`, prompt_captured/working_memory_update 等, packages/graph-agent/.../callbacks/events.py 32类); 前端 TracePanel 未挂载(同上) → 无条目可点

### [target-design] 点击 Timeline 中 llm_call 事件 → Prompt Inspector 三视图(Template/Variables/Rendered)
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector REQ-5
- **动机**: trace-inspector REQ-5 + workflow §2.5: 透视发给大模型的最终 prompt。数据已在 prompt_captured 事件里(无需引擎改), 但 PromptInspector 组件 design 标'新增', 代码无 — 目标设计(数据就绪/组件待建)。
- **证据**: design.md:46 `PromptInspector(3-tab) | 无(数据已在 prompt_captured) | 新增`; 数据源 requirement.md:38 `prompt_captured` 带 resolved_prompt+variables+resolved_model; grep 前端无 PromptInspector 组件

### [target-design] 运行完/挂起的 agent 节点点 '+' → 内联展开内部执行子树(update_working_memory/tool_calls/LLM Reply/md2json/validator/finish_task)
- **能力·区域**: `trace-observability` · `canvas` — 目标: canvas REQ-11 (运行态只读展开, DECISION-CANVAS-09 共用UI按mode区分) / research §6 LangSmith 竖向时间轴
- **动机**: workflow §2.4 + canvas REQ-11: 打破 agent-loop 黑盒的微观拓扑。当前节点 '+' 只用于子图 inline 展开, 没有任何运行态内部循环展开 — 纯目标设计(运行态只读 mode 待建, 与编辑态 L3 共用 UI)。
- **证据**: SkillNode '+' 仅 subgraph: apps/studio/frontend/src/components/nodes/SkillNode.tsx:116-128 `data.subgraphPath ? <button onToggleSubgraph>`; 展开内容 SubgraphInline(子图占位, 非运行态微观); grep canvas 无 working_memory/md2json/finish_task 微观节点渲染

### [target-design] Validator 重试节点标 Nudge:2/3(红/黄徽章), 最终失败附 Error Stack 气泡 — PM 看到大模型跑偏被强拉回
- **能力·区域**: `trace-observability` · `canvas` — 目标: canvas REQ-12
- **动机**: workflow §2.2 nudge 高亮 + canvas REQ-12: 让 PM 清楚哪步触发了几次纠偏。节点数据里 max_nudges 写死 null, 无 nudge 计数/徽章/Error Stack 渲染 — 目标设计。
- **证据**: build-nodes.ts:56,86 `max_nudges: null`(legacy 分支硬编码); grep canvas 无 Nudge 徽章/Error Stack 气泡组件; SkillNode 状态徽章仅 idle/running/success/error/paused/breakpoint(SkillNode.tsx:11-40), 无 nudge 计数

### [target-design] 后端向前端推流运行态微观执行事件(Payload schema, 含 parent_node_id/node_type), 前端消费
- **能力·区域**: `trace-observability` · `state-engine` — 目标: canvas REQ-13 / DECISION-CANVAS-10 (B 快照覆盖)
- **动机**: canvas REQ-13: 运行态微观拓扑的数据契约(B 快照覆盖 MVP0)。本 spec 只定义前端消费的 schema, 后端装配归 engine; 当前 trace.jsonl 是 phase 级事件, 无微观 parent_node_id 嵌套 schema — 目标设计。
- **证据**: canvas requirement.md:104-106 REQ-13(B 快照, 必含 parent_node_id/node_type)标 🆕; 现有事件无微观嵌套字段(events.py phase 级); 前端无 micro payload 消费(grep 无 parent_node_id)

### [orphan-unmounted] 选中多个测试输入触发批量运行(一输入一运行), 各自发起 run
- **能力·区域**: `run-execution` · `input` — 目标: skill-lifecycle R3.1 (一输入一运行)
- **动机**: skill-lifecycle R3.1: 批量跑。后端 start_batch_run 完全 live(逐项 start_run), 前端 useBatchRun hook + BatchRunner UI 全实现且调真实端点, 但无任何 JSX/import 挂载 — 已实现孤儿, 批量旅程当前不可达。
- **证据**: 后端 live: run_manager.py:231-248 `start_batch_run`(逐 input_id → start_run); runs.py:48-50 `create_batch_run`; 前端 hook 实现但孤儿: apps/studio/frontend/src/hooks/useBatchRun.ts:12-103(调 `/runs/batch-run` + 轮询 `/batch/{id}`), 无 importer; BatchRunner.tsx:22 无 JSX 渲染处(grep `<BatchRunner` 空)

### [target-design] 导入呈统一命名序列(chapter1/chapter2…)时, 系统识别并建议自动开启批量模式(默认运行数=文件数)
- **能力·区域**: `run-execution` · `input` — 目标: skill-lifecycle R3.2
- **动机**: skill-lifecycle R3.2: 序列自动批量(纯前端便利, 不改后端语义)。这是设计目标; 当前 useBatchRun 仅手动 toggleInput 多选, 无数字后缀序列检测逻辑 — 目标设计。
- **证据**: useBatchRun.ts:65-71 仅 `toggleInput` 手动多选; grep 前端无序列/数字后缀检测(design.md:93 命前端识别序列建议); 后端不参与(design.md:94 '仅前端便利, 不改后端运行语义')

### [orphan-unmounted] 批量运行轮询批次状态(running/success/failed, total/completed/逐项 status)
- **能力·区域**: `run-execution` · `input` — 目标: skill-lifecycle R3 / public-api GET /batch/{id}
- **动机**: 批量旅程的进度反馈。后端 get_batch_status live(聚合逐项 status), 前端 useBatchRun 已实现 1s 轮询 + BatchSummary 展示, 但随 useBatchRun/BatchSummary 一起未挂载 — 孤儿。
- **证据**: 后端 live: run_manager.py:250-286 `get_batch_status`(completed/failed 聚合); runs.py:73-75 `get_batch_status`; 前端轮询: useBatchRun.ts:33-63(1s setInterval GET `/batch/${batchId}`); BatchSummary.tsx:32 无 importer(grep `<BatchSummary` 空)

### [backend-only] 批量中某输入失败时显式报告失败项(不静默跳过)
- **能力·区域**: `run-execution` · `input` — 目标: skill-lifecycle R3.4
- **动机**: skill-lifecycle R3.4: 失败显式上报。后端逐项 status 已含 failed 且 batch 聚合标 failed(可见), 失败 run 也写 metrics.json error; 但前端 UI 孤儿无法呈现失败项 — 后端就绪、前端无 surface。
- **证据**: 后端失败可见: run_manager.py:275-276 `any(item.status=='failed') → status='failed'`; worker 失败写 error: run_manager.py:117-123 metrics.json `{status:failed, error}`; 前端 batchError 在孤儿 useBatchRun.ts:98(未挂载)

### [backend-only] 运行成功后自动 git commit 该 run(autocommit), 结果 git_status(committed/locked/failed)记入元数据
- **能力·区域**: `run-execution` · `native-fs` — 目标: skill-lifecycle / INDEX D10 (native-fs 闭环编排)
- **动机**: 已知上下文点名 run-autocommit=backend-only。运行成功自动固化为 git 快照, 是闭环编排的一环(D10 编排归 Rust)。后端完整 live 含降级日志, 但前端无任何 git_status 展示 — 后端就绪、前端无 surface。
- **证据**: 后端 live: run_manager.py:445-461 `_auto_commit_successful_run`(git lock→'locked' WARNING line 456, 失败→'failed' WARNING line 459); :429 成功 run 触发; git_status 字段: apps/studio/backend/app/models/runs.py:61 `git_status: Literal['committed','locked','failed']|None`; grep 前端无 git_status 渲染
- **FROZEN 改动**: D12/D10: autocommit 闭环编排归 native-fs(Rust); 当前由 Python GitLocalService(run_manager.py:180,450)执行, 目标迁 Rust 编排

### [backend-only] 运行失败/中断后查看失败原因并进入 05_debugging 干预(节点级 Resume 续跑)
- **能力·区域**: `debug-resume` · `center-action-bar` — 目标: trace-inspector §5 (DEF-005, resume 501); 05_debugging 节点拥有
- **动机**: workflow §3 下游流转的失败退路: 失败→debug。本节点拥有'失败→转 debug'这一旅程出口, resume 是其落点(归 05/debug-resume)。后端 resume 端点是 501 桩, 前端无 Resume 入口 — 接口在但 501。
- **证据**: resume 501: apps/studio/backend/app/routers/runs.py:64-70 `resume_run` → `raise_not_implemented`; 失败态可达: worker 写 failed metrics(run_manager.py:117-123); 前端无 Resume 按钮(grep 无 resumeRun 调用)。DEF-005 登记

### [stale-code] 净化 PropertiesPanel: 移除 selectedEdge JSON 倾倒分支, 边状态改走 trace 控制台/黑板卡片
- **能力·区域**: `trace-observability` · `properties` — 目标: trace-inspector REQ-6 / design D5
- **动机**: trace-inspector REQ-6: 属性栏回归单一职责。当前 edge dot 把 mock JSON 倒进 PropertiesPanel 的 selectedEdge 分支(违反 INDEX §2 所有权: properties 不该持边状态流), 是接 trace 时必须拆除的过时实现 — 配 file:line 标 stale-code。
- **证据**: ContextEdge.tsx:217-223 setSelectedEdge(mockJson)+onPanelChange('properties'); design.md:44 `PropertiesPanel.tsx:195-280 if(selectedEdge) 倾倒 inputs/phase_outputs/frame JSON | 删除该分支`(REQ-6)

### [orphan-unmounted] 回看历史 run 详情(RunDetailDrawer)并 Replay 重跑该 run
- **能力·区域**: `run-execution` · `local-history` — 目标: skill-lifecycle (run 历史/replay) — replay 复用 start_run
- **动机**: run 历史的进阶动作(详情抽屉 + replay)。RunDetailDrawer/RunHistoryRow/BatchSummary 组件全实现含 onReplay, 但 local-history 面板实际挂的是 git 快照 revert 面板(非 run replay), 这些 run-replay 组件无 importer — 孤儿。穷举历史交互必须标出。
- **证据**: 组件存在: apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:27(onReplay :57-61)、RunHistoryRow.tsx:57(onReplay :95)、BatchSummary.tsx:32; 均无 JSX importer(grep `<RunDetailDrawer`/`<RunHistoryRow`/`<BatchSummary` 空); local-history 实挂 git revert: apps/studio/frontend/src/components/studio/panels/HistoryPanel.tsx 仅 re-export history/HistoryPanel.tsx(useLocalHistory→revert, 非 run replay)

### [target-design] 超大事件 payload(如 10MB 工具输出)在 Trace 列表/编辑器截断显示(__TRUNCATED__ + 展开), 防浏览器 OOM
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector design R3
- **动机**: trace-inspector design R3(风险/约束): 真实 run 的 trace 单事件可能极大, 不截断会 OOM。这是接 TracePanel 时的硬约束动作, 当前 TracePanel 未挂载且截断策略待落 — 目标设计/失败退路类。
- **证据**: design.md:101 R3 `单事件 payload 可能极大... TracePanel 列表与编辑器必须截断(超阈值 __TRUNCATED__ + 展开)`; TracePanel 未挂载(同上), 截断逻辑待实现

**跨切**: 1) 写入唯一权威=Rust(D12): 本节点所有 .workspace 落盘(runs 目录/input_data.json/final_state.json/metrics.json/trace.jsonl/artifacts/autocommit)目标统一'经 Rust 文件命令'; 仅 run_skill 引擎执行 + gateway 模型解析两块留 Python sidecar。当前这些写入由 Python run_manager 执行(run_manager.py:130,190,108-109)、autocommit 由 Python GitLocalService(run_manager.py:450)— 全部待迁 Rust native-fs(INDEX D10 闭环编排归 Rust)。
2) trace 的'单一当前运行真相源'(design §1 useRunTrace 新增)是接线枢纽: TracePanel/边state卡片/Prompt透视三消费者读同一份 events; live 走未挂载的 useRunStream(WS), history 走 live useRunHistory.fetchRunDetail — 后端两源都 live(websockets.py:27/run_manager.py get_run_detail), 缺的纯是前端 useRunTrace + 挂载。
3) skeleton+lazy-load NFR(INDEX §11): run/trace/batch 均后端数据驱动, 挂载时须配骨架屏(尤其 trace 大列表虚拟化 TracePanel 已内置 VirtualTraceList)。
4) canvas 运行态/编辑态共用展开 UI(DECISION-CANVAS-09): REQ-11 运行态只读展开与 REQ-6 L3 编辑态步骤展开共用组件按 mode 区分 — 本节点只拥有运行态只读 mode, 编辑态 mode 归 02_authoring。
5) edge 'hasTraceData' 当前硬编码 !isGlobal(buildEdges.ts:26)使所有非全局边永远显示流动动画+可点 dot, 与真实 run 无关 — 接 trace 时须改为由真实 events 派生(design D2 buildEdgeContext), 否则'有没有跑过'无法区分。
6) 节点状态(statusByNodeId)接线缺口贯穿多动作: GraphCanvas 已支持 statusByNodeId prop(GraphCanvas.tsx:88,195)且 SkillNode 状态样式齐全, 唯独 Workspace.tsx:515 渲染时不传 — 一处接线即可让节点灯活起来(需上游有 live run 事件→status 映射)。

**待定**:
- G3 artifact 落盘是否在引擎 run 写入点保留最终 validated business_data_md(用于 md artifact, 不做 json→md 回转)? — alignment-notes 锁定为待实现期核实; 当前 run_manager 只写 final_state.json/metrics.json(run_manager.py:108-109), 未见 business_data_md 落盘点, 影响 run 产物与 artifact 配置的衔接。
- 运行态 Payload schema(canvas REQ-13)采 B 快照覆盖, 需 engine 侧 run_manager 装配微观事件(parent_node_id/node_type) — 这部分后端装配归 engine spec, 但本节点是前端消费方; 两 spec 的 schema 契约对接点(字段名/嵌套)尚未在任一 spec 固化, 接 REQ-11 前需先定契约。
- trace-inspector REQ-7(结构化前后态 DIFF)依赖引擎 emit reducer 级 diff(P2); 在引擎支持前前端只能 phase_end[A] vs phase_start[B] 近似 diff(非权威)。本节点是否要先上近似 diff 还是等引擎? — spec 标 P2 不阻塞 P1, 但旅程上 PM 可能期望看到 added/modified/deleted。
- run 触发(startRun)与 batch 触发(useBatchRun)目前是两套独立前端路径(单次=center-action-bar onRun 桩, 批量=孤儿 BatchRunner); 序列自动批量(R3.2)建议开启批量后, 单次 Run 按钮与批量入口的 UI 关系/落点(i/o panel? 动作条?)未在 spec 明确 — 影响 input/i-o panel region 的运行入口归属。

---

## 05_debugging — Debug (trace 去黑盒 / 编辑续跑)

**Scope**: 本节点拥有"运行之后/之中的去黑盒观测 + 失败干预续跑"这段旅程。OWNS(本节点链接的能力): trace-observability(REQ-1~6 唯一权威=studio-feature-trace-inspector spec)+ debug-resume(scenarios A/B/C 干预续跑, 能力注册表标"全孤儿待新建")。涉及 region: timeline(Trace控制台/run历史)、canvas(边dot/节点灯/Resume按钮落点)、properties(待净化的edge JSON倾倒)、editor(state只读查看/篡改)、center-action-bar(predict/run入口=上游)。NOT-OWNED(移交其他 spec/节点): ①结构化前后态DIFF(REQ-7)在本spec内但P2依赖引擎emit reducer diff, 本轮不交付; ②Compile结构化报错底部drawer=DEF-010, 已明确拆出归 authoring(canvas-authoring-v1候选owner), 不属本节点; ③真实Run发起/状态机/autocommit/batch=run-execution能力(归04_execution节点), 本节点只消费其产出的trace+checkpoint; ④画布拓扑编辑(连线/断连/新建phase)=graph-authoring(归02_authoring), 本节点只读地复用节点/边渲染。后端归属(D10/D12): trace读取+resume执行属 engine(Python sidecar); state篡改的.workspace落盘属 native-fs(Rust); 前端状态+WS/event桥属 state-engine。

### [orphan-unmounted] 运行时实时看 trace 控制台: run 发起后, 所有事件/输出/错误实时流入唯一控制台, 突出 phase 边界/错误红灯/token·延迟 (REQ-1 运行时分支)
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector REQ-1
- **动机**: 去黑盒第一性原理之'看到所有操作日志': 长流程 skill 跑起来 PM 必须实时知道每步在干什么, 否则黑盒中无法判断该不该中断。引擎已把每步完整落盘 trace.jsonl + WS 实时推送, 缺的只是把已实现的消费端接上
- **证据**: TracePanel.tsx:1-114 全实现(含 golden/link/search/filter), 但 grep 全 src 零非测试引用(orphan); useRunStream.ts:1-89 WS+重连+100ms批刷全实现, 同样零引用; WS 后端就绪 websockets.py:27 /ws/runs/{run_id}; PanelKind 无 'trace' (Toolbar.tsx:7)

### [placeholder] 非运行时回看历史 run 的 trace: 从 run 历史列表点某次运行 → 同一控制台回看那次的完整事件流 (REQ-1 非运行时分支)
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector REQ-1
- **动机**: 去黑盒不只看当前跑, 还要复盘历史失败跑(token浪费的核心动机=不重跑就能回看上次哪步坏了)。历史数据后端齐全, 但 TimelinePanel 的 run 卡片是死的只读列表, 点不进 trace
- **证据**: TimelinePanel.tsx 仅 refresh 按钮有 onClick(:48), run 卡片(:73 keyed by run.run_id)无 onClick→无法 setActiveRunId/切 trace; 历史源后端就绪 GET /skills/{id}/runs/{run_id}→RunDetail.events(runs.py:53-55, run_manager.py:304); 需新增 useRunTrace 合并 live/history(spec design §1, 文件不存在已证实)

### [orphan-unmounted] 节点定位 trace: 画布选中某节点 → 控制台只显示该节点的事件(按 phase_name 过滤)
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector REQ-2
- **动机**: 去黑盒第二性原理之'找到想看的那一条': 海量日志里 PM 要快速定位到出问题的那个节点。过滤机制(useTraceFilter)已实现, selectedNode.id==phase_name 契约已验证, 但承载它的 TracePanel 未挂载, 整条链不可达
- **证据**: useTraceFilter.ts 存在; TraceFilter.tsx/TraceSearchBar.tsx/VirtualTraceList.tsx 全在 components/trace/; activePhase=selectedNode.id 契约已验证(build-nodes.ts:193 node.id=phase.name 与事件 phase_name 同源, spec design D1/R1 标已消解✅); 但只能经 orphan TracePanel 消费

### [orphan-unmounted] 检索/筛选 trace: 按事件类型(llm_call/tool_call/error/state…)+关键字在海量日志中检索
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector REQ-2
- **动机**: 同 findability: 节点过滤之外还要类型+关键字检索, 否则一个节点内几十条事件仍难定位。搜索/类型筛组件已建好, 随 TracePanel 一起未挂载
- **证据**: TraceSearchBar.tsx + TraceFilter.tsx(eventTypes/selectedTypes) 在 components/trace/; TracePanel.tsx:87-97 已接 filter.searchTerm/eventTypes; 整体零引用未挂载

### [placeholder] 点击边中心 dot → 弹出 state 黑板卡片, 看 A→B 这条边上的真实 blackboard 状态(数据汇入/reducer聚合/state流转)
- **能力·区域**: `trace-observability` · `canvas` — 目标: trace-inspector REQ-3
- **动机**: state snapshot 是 tracing 的一等内容(用户原话): PM 要看节点间黑板里真实流转了什么。当前入口已接线且能弹出, 但内容是写死的假数据, 不反映任何真实运行→等于黑盒未打开
- **证据**: ContextEdge.tsx:213-225 dot onClick 已wired(setSelectedEdge+onPanelChange), 但 data=getMockEdgeContext()(:30-55 返回硬编码假 JSON, 与真实 run 无关); 真实数据应由 phase_end[A]+phase_start[B] 的 context 重建(buildEdgeContext.ts 不存在, 已证实); 引擎 context 数据齐全 events.py:55/66 phase_start/end 携带完整黑板

### [target-design] 点击 state 黑板卡片 → 进入编辑器(只读)看该状态完整详情, 深层嵌套可折叠展开
- **能力·区域**: `trace-observability` · `editor` — 目标: trace-inspector REQ-3, REQ-4
- **动机**: 卡片只是黑板预览, PM 要钻进去看完整 state 全文(可能很大很深)。只读是本轮明确边界(篡改续跑是 scenario C 另一 mode)。该卡片+只读编辑器组件目前完全不存在
- **证据**: spec design §2 列 EdgeStateCard+只读编辑器='无, 新增'; D4 标 Monaco read-only; 当前 dot click 落到 PropertiesPanel 静态 pre(:228-263)而非可折叠只读 Monaco; 无 EdgeStateCard 组件(grep 无)

### [target-design] 从时间线进 state: 节点在 trace 流中显式抛出 context变化/working_memory/state快照作为可见条目, 点条目 → 跳编辑器看该刻黑板 (REQ-4 时间线入口)
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector REQ-4
- **动机**: REQ-3(画布连线进)与 REQ-4(时间线条目进)是同一'看那一刻黑板'能力的两个入口, 都要落到只读编辑器。引擎已 emit working_memory_update/snapshot, 但前端无'点 state 条目跳编辑器'的落点(依赖未挂载的 TracePanel + 未建的编辑器)
- **证据**: 引擎 events.py:119-128 WorkingMemoryUpdateEvent(全文)、phase_start/end context 齐全; 前端 onSelectEvent 形参存在(TracePanel.tsx:15)但无实现跳转编辑器; 编辑器组件未建(同上)

### [orphan-unmounted] Prompt 透视: 点一条 LLM 事件 → 三视图 Template(原始模板)/Variables(喂入变量JSON)/Rendered(渲染后纯文本)
- **能力·区域**: `trace-observability` · `properties` — 目标: trace-inspector REQ-5
- **动机**: 去黑盒到 LLM 调用层: PM 要看到底喂给模型的最终 prompt 长啥样(模板/变量/渲染后), 这是排查 agent 行为异常的关键。组件已完整实现, 数据已在 prompt_captured 事件里, 但组件零挂载
- **证据**: PromptInspector.tsx:18-63 三 tab(template/variables/rendered)全实现, 读 promptEvent.variables + resolved_prompt; 仅 PromptInspector.test.tsx 引用, 零非测试挂载(orphan); 数据源 events.py:230-236 PromptCapturedEvent(resolved_prompt+variables+resolved_model)无需引擎改动

### [stale-code] 净化 PropertiesPanel: 移除 selectedEdge 的 JSON 倾倒分支(inputs/phase_outputs/full frame), 属性栏回归静态节点配置单一职责; dot click 改道 trace 控制台/黑板卡片
- **能力·区域**: `trace-observability` · `properties` — 目标: trace-inspector REQ-6
- **动机**: 所有权不变量(INDEX §2): edge 状态应只走 trace 控制台/卡片, 不该把假 JSON 倒进属性栏让两处争抢同一职责。这是旧 trace-inspector(复用Properties) vs mvp0(独立面板)矛盾的清算, spec 定夺为独立控制台
- **证据**: PropertiesPanel.tsx:195 if(selectedEdge) 分支整段倾倒 inputs(:228-230)/phase_outputs(:241-243)/full JSON(:262-264)到'Connection Trace'视图=stale; ContextEdge.tsx:223 onPanelChange('properties')需改道'trace'; spec REQ-6/design D5

### [placeholder] 失败时节点亮红灯: 某 phase 运行失败(validator重试超限/报错)→ Timeline 停在错误节点, 画布该节点亮红灯显示 Error Message (scenario B 视觉)
- **能力·区域**: `trace-observability` · `canvas` — 目标: trace-inspector REQ-1 (突出错误红灯); debug-resume (节点态)
- **动机**: 干预的前提是先一眼看到哪个节点炸了。节点状态视觉(error红框/running脉冲/breakpoint/paused)组件已完整建好, 但从未被真实 run 事件驱动→节点永远是默认 idle/success, 红灯不会亮
- **证据**: SkillNode.tsx:11-42 STATUS_STYLE 全六态(idle/running/success/error红框AlertTriangle/paused/breakpoint)=live组件; 但 status 来自 statusByNodeId 形参(build-nodes.ts:171,193 默认 index0=success 其余 idle); GraphCanvas statusByNodeId 为可选 prop 默认{}(GraphCanvas.tsx:54,195); Workspace.tsx:515-527 与 SplitEditor.tsx:102-115 两处渲染 GraphCanvas 均未传 statusByNodeId → 永不驱动

### [backend-only] 节点级 Resume 按钮: 失败/暂停节点旁直接显示 [Resume](非全局), 改完 prompt/代码后点该节点的 Resume → 从该位置用 checkpoint 已有数据精准续跑 (scenario B 核心)
- **能力·区域**: `debug-resume` · `canvas` — 目标: trace-inspector §5边界(DEF-005); debug-resume(能力注册表标'全孤儿待新建')
- **动机**: 本节点存在的根本理由: 长流程不该每次从头重跑(浪费 token 和时间)。节点级粒度(非全局)是 PM 要求的精准续跑。但后端 resume 端点 501 未实现, 且无节点级 checkpoint 恢复粒度, 前端连按钮都没有
- **证据**: 前端 grep 全 src 无任何 Resume 按钮(零结果); 后端 runs.py:64-70 resume_run→raise_not_implemented→501; run_manager.py 有 checkpoints.db(:167)+thread_id=run_dir.name(:98)但仅 thread/run 级, 无节点级恢复; DEF-005(deferred-items.md:25-30)登记后端阻塞

### [target-design] 脏状态失效: PM 改了图拓扑(如删某前置节点)→ 所有受影响后续节点的 Resume 按钮自动消失/置灰, 只有存在合法前置数据的节点才允许 Resume (scenario B 依赖判断)
- **能力·区域**: `debug-resume` · `canvas` — 目标: debug-resume (待新建)
- **动机**: 续跑用的是旧 checkpoint 数据, 若上游拓扑已变, 拿旧数据续跑会产出错误结果。这个依赖关系守卫是 resume 正确性的安全门, 防止 PM 拿失效数据误续跑。当前 Resume 整体不存在, 此守卫更无从谈起
- **证据**: 前端无 Resume 按钮亦无依赖失效逻辑(grep 零结果); SkillNodeStatus 有 'breakpoint'/'paused' 态可承载(types.ts:4)但未驱动; 需 resume 端点(501)+节点级 checkpoint 粒度+拓扑依赖图分析, 三者皆缺

### [target-design] 场景A 人工干预点(HitL): 底层工具调 request_human_input()/ask_clarification() → Timeline 暂停, 顶部弹显眼提问框(含文本框/选项), PM 输入答案
- **能力·区域**: `debug-resume` · `canvas` — 目标: debug-resume (待新建); 05_debugging 场景A
- **动机**: 有些决策(如'文案选方案A还是B')必须人来拍, 引擎跑到该点要停下来问 PM。引擎侧 HitL 原语(clarification 工具 + ambiguity 事件)已存在, 但 Studio 前端完全没有把这个'问题'surface 成提问框, PM 看不到也答不了
- **证据**: 引擎有原语: clarification_tool.py(builtin) + events.py:157 AmbiguityReportEvent + RunEndedEvent status 含 'interrupted'(:275); 但前端 grep ambiguity/clarification/request_human/HitL 提问UI 零结果; api/types.ts 无 ambiguity/interrupt 事件类型映射(grep 零)

### [backend-only] 场景A Resume 注入答案: PM 答完点 [Resume] → 系统将答案作为 ToolMessage 注入, Graph 从断点继续向下流转
- **能力·区域**: `debug-resume` · `canvas` — 目标: debug-resume (待新建); DEF-005
- **动机**: HitL 提问的闭环: 答案要能注回 graph 让它接着跑。这与 scenario B/C 共用 resume 后端(都是从断点带数据续跑), 共同卡在 resume 501 + 无注入消费路径
- **证据**: runs.py:64-70 resume 501; ResumeReq(runs.py models:109-112)有 context_overrides 字段但全后端零消费(grep 仅 model定义+501端点两处); 无 ToolMessage 注入逻辑

### [target-design] 场景C 篡改 Context 黑板: 点边 dot 展开上一轮跑完的真实 Context → 纯净 Monaco JSON Editor 手写改值(如 {result:坏消息}→{result:好消息}) → 保存
- **能力·区域**: `debug-resume` · `editor` — 目标: debug-resume (待新建); 05_debugging 场景C; DEF-005
- **动机**: PM 发现某阶段输出有小瑕疵导致下游报错时, 不想改 prompt 重跑整个阶段, 只想立刻把瑕疵值改掉试下游逻辑——这是最省 token 的快速验证。需要可写的(非只读)JSON 编辑器, 当前 dot 只到只读 mock 展示, 无可编辑入口
- **证据**: 当前 dot click 落到 PropertiesPanel 只读 pre(:228-263), 非可写 Monaco; scenario C 需可编辑 JSON 编辑器(spec design D4 明确只读编辑-续跑是 DEF-005 不在本轮); EdgeStateCard+编辑器组件未建
- **FROZEN 改动**: D12: 篡改后的 state 若需落盘(.workspace 内伪造数据), 写入走 Rust 文件命令(native-fs), 非 Python 端点; resume 执行本身属 engine sidecar

### [backend-only] 场景C 用伪造数据续跑: 篡改保存后点下游节点 [Resume] → 系统拿这段伪造 JSON 继续往下跑下游 Phase
- **能力·区域**: `debug-resume` · `canvas` — 目标: debug-resume (待新建); DEF-005
- **动机**: 篡改的闭环: 改完的伪造黑板要喂给 resume 让下游接着跑。这正是 ResumeReq.context_overrides 字段的设计用途(用 override 替换 checkpoint 里的值), 但该字段定义后零消费, resume 端点 501
- **证据**: ResumeReq.context_overrides(runs.py models:112)定义但零引用(grep 全后端仅 2 处=model+501端点); runs.py:64-70 resume 501; DEF-005(deferred-items.md:28)明示'context_overrides 字段已定义但全代码零引用'

### [placeholder] 上游入口: 进入 debug 前需先有一次 Run(发起真实运行产出 trace+checkpoint)。当前中心动作条 Run/Predict 是桩
- **能力·区域**: `run-execution` · `center-action-bar` — 目标: (归 run-execution / 04_execution 节点, 非本 spec)
- **动机**: debug 节点是 run 的下游——没有真实 run 产出 trace 和 checkpoint, 去黑盒和续跑都无对象。此动作本体归 run-execution(04_execution 节点)拥有, 在此仅作为本节点的前置依赖登记, 提醒其当前为桩
- **证据**: Workspace.tsx:537-538 onPredict/onRun = console.info('predict/run clicked') 桩; 真实 create_run 后端已就绪(runs.py:27-29 start_run, run_manager.py:182)→桩在前端入口未接

### [target-design] 失败退路A — 一次都没跑过 / 无运行数据: trace 控制台显示空态('Waiting for run events'); 点未跑到的边 dot → 卡片优雅显示'该边尚无运行数据'
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector design D3
- **动机**: 去黑盒要诚实: 没数据时不能白屏或崩, 要明确告诉 PM'还没跑/这条边没数据'。TracePanel 自身空态已实现, 但'自动选 Latest Run / 无运行空态'的选择逻辑(activeRunId 生命周期)未建
- **证据**: TracePanel.tsx:37-48 traceLogs 为空时已渲染'Waiting for run events'空态(组件级已有); 但 activeRunId 状态+自动选 Latest Run 逻辑未建(spec design D3); buildEdgeContext 找不到数据返回 empty state 的逻辑未建(design D2, 文件不存在)

### [target-design] 失败退路B — 单事件 payload 极大(如 10MB 工具输出): trace 列表与编辑器必须截断(超阈值显示 __TRUNCATED__ + 展开按钮), 防浏览器 OOM
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector design R3
- **动机**: 真实 run 的某条事件(大工具输出/大黑板)可能几 MB, 直接渲染会卡死浏览器, 让去黑盒工具自身变成崩溃源。这是 spec 标的关键约束(R3), 当前未实现截断
- **证据**: spec design R3 标'必须截断超阈值显示 __TRUNCATED__'为关键约束; VirtualTraceList.tsx 虚拟列表已有(components/trace/)但截断逻辑待核(spec 标沿用旧 spec 约束=尚未落地)

### [target-design] 失败退路C — live→history 源切换时事件重复/丢失: useRunTrace 切换当前运行(live)与历史运行(history)时以 runId 为界重置, 避免 stream_run 结束 replay 与 None 哨兵导致重复
- **能力·区域**: `trace-observability` · `timeline` — 目标: trace-inspector design R5
- **动机**: PM 在'看当前跑'和'回看历史跑'间切换是高频操作, 切换时若事件重复或丢失, 去黑盒就不可信。useRunTrace 这个合并 live/history 的薄封装是接线核心, 尚未创建
- **证据**: spec design R5 标切换需'以 runId 为界重置'; useRunTrace.ts 不存在(已证实); 后端 stream_run 结束后 replay+None 哨兵(run_manager.py:334 stream_run)是已知重复源

**跨切**: 1. 核心判断(spec design 原话+代码已证实): 本节点去黑盒部分约80%是'接线+接真实数据', 不是造新组件——TracePanel/useRunStream/PromptInspector/useTraceFilter/components-trace 全套已实现且零引用(orphan-unmounted), 引擎 trace.jsonl + 32类事件 + WS 全就绪。最大障碍是'孤儿组件未挂载'而非'缺能力'。
2. status 分布: orphan-unmounted(TracePanel/useRunStream/PromptInspector/findability 一族, 组件全建好零挂载) / placeholder(edge dot 已wired但mock数据 + 节点灯组件全建好但statusByNodeId永不传driving) / stale-code(PropertiesPanel selectedEdge JSON倾倒, 违所有权不变量需删) / backend-only(resume相关: 端点501+checkpoint有但仅thread级) / target-design(EdgeStateCard/只读编辑器/HitL提问框/脏状态失效/篡改编辑器全不存在)。
3. 两条 GraphCanvas 渲染路径(Workspace.tsx:515 纯canvas + SplitEditor.tsx:102 split流派)均不传 statusByNodeId, 所以'节点跟随运行状态/失败红灯'在任一布局下都未驱动——这是 placeholder 而非 live 的关键证据, 不能因 SkillNode 有完整 STATUS_STYLE 就误判为 live。
4. D12 落点: 本节点写类动作极少。scenario C 篡改 state 若落盘到 .workspace → 走 Rust(native-fs); 但 resume 执行/trace 读取属 engine(Python sidecar), 不是 Rust。多数动作是读(trace观测)无写归属问题。
5. 能力边界提醒(INDEX §2 不变量): trace-observability 与 debug-resume 是两个能力——前者只读去黑盒(scenarios 之外的 REQ-1~6), 后者干预续跑(scenarios A/B/C)。spec design 反复强调'只读去黑盒 vs 编辑续跑是不同 mode', 编目时未混淆: REQ-3/4 的 state 是只读查看(trace-observability), scenario C 的 state 是可写篡改(debug-resume)。
6. REQ-7 结构化前后态 DIFF(added/modified/deleted)在 trace-inspector spec 内但 P2 依赖引擎 emit reducer 级 diff, 本轮非交付——已按指示不展开为本节点 P1 动作, 仅在此登记其归属(trace-observability 能力 / properties region / 依赖 engine)。
7. spec 文件行号 vs 实测微差: spec design 标 PropertiesPanel '195-280' 倾倒分支, 实测该分支主体在 195-274(全 463 行), 不影响结论(分支确存在且需删)。已用实测行号。
8. region 命名沿用 INDEX §6 注册表: 用了 timeline/canvas/properties/editor/center-action-bar(均在12区表内)。注意 PM 后续讨论提'input panel 改名 i/o panel', 但那属 02_authoring 的 M2/T7 落点, 与本 debug 节点无关, 本节点未用 input region。
9. 上游依赖诚实标注: onPredict/onRun=console.info 桩(Workspace.tsx:537), 本节点所有动作的前提'先有一次真实 run'当前在前端入口断裂; 该动作本体归 run-execution(04_execution), 在此仅作前置登记不抢所有权。

**待定**:
- scenario C 可写 JSON 编辑器 与 REQ-3/4 只读 EdgeStateCard 是否复用同一 Monaco 组件(只切 readonly flag)? spec design D4 暗示复用同一 EdgeStateCard/编辑器, 但只读 vs 篡改是不同能力(trace-observability vs debug-resume), 组件复用边界待 spec 明确, 涉及两能力的 region 归属(editor)是否各写一份还是共享。
- 节点级 Resume(scenario B)所需的'节点级 checkpoint 恢复粒度'——当前 run_manager 只有 thread/run 级 checkpoints.db(:167)。这是 debug-resume 能力新建时的硬前提, 但 checkpoint 节点级化属 engine(packages/graph-agent) 改动还是 backend(run_manager) 改动, 跨 engine/backend 边界, 归属待 D10 三分落地后定。
- 节点失败红灯(scenario B视觉)依赖 statusByNodeId 从 live trace 事件派生(phase_start→running / phase_end+error→error / interrupt→breakpoint)。这个'事件→节点态'派生器属于本节点 trace-observability 还是 run-execution(谁拥有运行态机)? 边界未定——节点态既是 run 的产物又是 debug 的观测入口。
- HitL 提问框(scenario A)的事件通道: 引擎有 AmbiguityReportEvent + clarification_tool, 但 api/types.ts 前端 CallbackEvent 无对应类型映射。该'问题事件→提问框'的传输+渲染归属(state-engine 桥 vs trace-observability 渲染 vs debug-resume 交互)三方交叉, 待 event-bus-alignment 明确。
- REQ-7 结构化 DIFF 的引擎依赖(emit reducer 级 diff)排期未定; 在此之前前端可做 phase_end[A] vs phase_start[B] 近似 diff(非权威预览)——这个'近似预览'要不要作为本节点 P1.5 过渡动作, 还是严格等引擎? spec 标 P2 但留了近似口子, 取舍待 PM。

---

## 06_eval — Eval(golden 固化/Diff/Judge/Publish)

**Scope**: 本节点拥有"真实 Run 成功后的验收交付旅程": 把 Run 终态固化为 golden、与 golden 做结构化 diff/字段得分、让 Copilot 充当 Judge 打分评述、最终 Publish 上线并闭环回主页。OWNS(链接): capability `golden-eval`(golden 固化/compare/字段得分/Judge/打磨编排) + `publish`(上线/artifact registry/撒花)，旅程上还借用 `copilot-assist`(Judge 评述) 与 `trace-observability`(看终态/REQ-7 结构化前后态 diff)。NOT-OWNS(移交他 spec): ① 结构化 before/after reducer 级 diff = trace-inspector REQ-7(P2, 依赖引擎 emit reducer diff), 本节点只做"近似 diff 展示"链接; ② 组件内部实现归 region(DiffView/DiffField→`properties` 未来 Diff 视图; Publish 按钮→`shell-layout` Header; Copilot Judge 对话→`copilot`); ③ golden/runs 目录读写 + publish 落盘编排归 `native-fs`(Rust, D12); compile/run/eval 引擎计算归 `engine` sidecar; copilot chat LLM 流归 `gateway`。设计权威源缺口: golden-eval 与 publish 在 INDEX §6 标注为"无主待建"(judge 无主待建 / publish 无主待建且文档与实现矛盾), 无专属 studio-feature-* spec, 故多数动作 target_spec = —(待建); 唯一有 spec 主的是结构化 diff(trace-inspector REQ-7)。FROZEN 契约: golden 固化的源 = RunResult 终态(public-api-contract RunResult.context / final_state.json); 与本节点 G3 artifact 落盘改 FROZEN(io.outputs 加路径)相关但 artifact 配置不在本旅程交互内。

### [target-design] 进入 Eval 视图(从 Run 成功后切到评估/对比模式)
- **能力·区域**: `golden-eval` · `shell-layout` — 目标: —(待建: INDEX §6 golden-eval 无主待建)
- **动机**: PM 在一次成功 Run 后需要一个明确的'验收模式'入口(workflow doc §1: 判断输出是否足够好)。这是整个 Eval 旅程的旅程脊柱起点, 必须存在才能触达后续 diff/judge/publish。
- **证据**: 无 Eval/对比视图挂载: components/studio/Workspace.tsx:554 只挂 <CopilotPanel skillId={skillId}/> 不传 view; copilot-panel.tsx:71 定义 view?:'edit'|'eval' 但全仓无任何调用方传 view='eval'(grep 0 命中), 故 inEvalView(copilot-panel.tsx:81) 永远 false; DiffView/useGoldenDiff 均无 importer(见下)。Eval 模式整体不可达。

### [backend-only] 将本次成功 Run 的终态固化为 Golden Baseline(Promote to Golden)
- **能力·区域**: `golden-eval` · `properties` — 目标: —(待建)
- **动机**: Diff 需要一个'对照基准'。把人工认可的一次 Run 终态钉成 golden, 是后续所有偏离检测的前提(workflow doc §2.1: 与 Node3 准备的 Golden Baseline 对比)。
- **证据**: 后端 live 且已注册: routers/golden.py:24-30 POST /api/skills/{id}/golden → services/golden_diff.py:34 set_golden_baseline_for_run 真实把 run_dir/final_state.json copy 进 golden 目录并写 golden_metadata.json(golden_diff.py:49-65); main.py:132 已 include golden.router; final_state.json 确实由真实 Run 写出 run_manager.py:108。但前端唯一调用方 hooks/useGoldenDiff.ts:39-56 promote() 是 orphan(无 importer, 见下), 故无 live UI 触达。

### [backend-only] Promote 时阻止把 Predict(试飞)trace 误固化为 Golden(409 守卫)
- **能力·区域**: `golden-eval` · `properties` — 目标: —(待建)
- **动机**: Predict 是 mock/拟真输出, 不是真实 Run; 若被当成 golden 会污染验收基线。这是数据正确性的硬守卫(防止假数据入基线)。
- **证据**: services/golden_diff.py:43 set 前调用 assert_trace_can_be_promoted_to_golden; services/diagnostic_export.py:25-42 检测 is_predict 则抛 PREDICT_TRACE_CANNOT_BE_GOLDEN(409, not_retryable)。后端 live, 但因前端 promote 入口 orphan, 该守卫当前无前端触达路径。

### [orphan-unmounted] 把当前 Run 终态与 Golden 做对比并计算字段级得分(Compare to Golden)
- **能力·区域**: `golden-eval` · `properties` — 目标: —(待建)
- **动机**: Eval 的核心: 让 PM 看到'哪里和 golden 不一样、差多少'。字段级 diff + 0-100 总分是验收决策的客观依据(workflow doc §2.1 文本/JSON 结构对比)。
- **证据**: 后端算法 live: services/golden_diff.py:68-110 compare_run_to_golden 递归 _diff_value(深度<5)+ SequenceMatcher 文本相似度(golden_diff.py:201-216)+ total_score; 端点 routers/compare.py:14(POST /compare)+:23(GET /diff), main.py:133 已注册。但前端 hooks/useGoldenDiff.ts 整文件零 importer(grep useGoldenDiff 仅命中自身定义); 且 useGoldenDiff.ts:27 调 GET /runs/{id}/compare 与后端 POST /compare 方法不符(method/path mismatch, 因 orphan 未暴露)。

### [orphan-unmounted] 渲染并排 Diff 视图(字段列表 + 选中字段差异 + 总分圆环)
- **能力·区域**: `golden-eval` · `properties` — 目标: —(待建); 组件本体归 03_regions/properties(INDEX §6: properties = …+(未来)Diff)
- **动机**: 把后端字段 diff 可视化, 让 PM 逐字段 drill 进去看 current vs golden(workflow doc §2.1 并排分屏 Split-view Diff + 差异高亮)。这是验收的主界面。
- **证据**: components/diff/DiffView.tsx:29 组件完整(左字段栏 DiffView.tsx:142-160 + 右 DiffField + 顶部 DiffScore 圆环 DiffView.tsx:86, DiffScore.tsx:16 conic-gradient 评分环), 配套 DiffField/DictDiffView/ListDiffView/TextDiffView/NumberDiffView/BoolDiffView 全在 components/diff/。但 grep DiffView(排除 diff/ 自身与 test)零外部 importer → 未挂载, 不可达。

### [orphan-unmounted] 导出对比报告(Compare 报告 → md/html)
- **能力·区域**: `golden-eval` · `properties` — 目标: —(待建)
- **动机**: PM 验收后需要把 diff 结论留档/分享(对比报告)。这是验收旅程的产出沉淀。
- **证据**: utils/reportTemplates.ts:34 renderCompareReport(md/html) 实现完整; 但其唯一挂载点是 components/diff/DiffView.tsx:95-105 内的 ExportButton, 随 DiffView orphan 一起不可达。注意: ExportButton 组件本身在 run 历史侧 live(BatchSummary.tsx:53/RunHistoryRow.tsx:114/RunDetailDrawer.tsx:72), 仅 compare 报告这一用法 orphan。

### [backend-only] 看 Run 终态本身(在编辑器/属性栏只读查看 final state, 为人工判断提供原始数据)
- **能力·区域**: `trace-observability` · `properties` — 目标: studio-feature-trace-inspector REQ-3/REQ-4(state 查看)
- **动机**: diff 之外, PM 常需直接看本次 Run 的完整终态黑板(去黑盒)。trace-inspector 第一性原理: 看到状态 > 计算差异。这是验收判断的底层数据。
- **证据**: 终态数据 live 落盘 run_manager.py:108 final_state.json + run_manager.py:316 final_context 读回; 但 trace-inspector requirement.md:40-43 实测前端 TracePanel.tsx/useRunStream.ts 零引用(僵尸)、状态查看入口未接线。终态'查看'属 trace REQ-3/REQ-4'现在可做'但当前 backend-only。

### [target-design] 查看节点转移前后变化的 key(结构化 before/after diff: added/modified/deleted 高亮)
- **能力·区域**: `trace-observability` · `properties` — 目标: studio-feature-trace-inspector REQ-7(P2, 本 spec 拥有, 依赖引擎)
- **动机**: 比'整段 diff'更精细: 让 PM 一眼看出某步到底改了哪些字段(reducer 级聚合/保留/丢弃)。但这是次级优化, 不得喧宾夺主于'看到状态'。
- **证据**: .kiro/specs/studio-feature-trace-inspector/requirement.md:71-76 REQ-7 = P2, 明确依赖引擎在 phase 边界 emit reducer 级 diff; design.md:91/:113 本轮不做 added/modified/deleted 高亮。引擎侧近似数据可由 PathDiff(public-api-contract: compute_diff/PathDiff expected/actual/missing/extra)与 phase_end[A] vs phase_start[B] 拼出, 但前端无对应渲染。代码无任何对应。

### [target-design] 触发 Copilot Judge: 让大模型对 artifact 与 golden diff 综合打分 + 意图偏离评述
- **能力·区域**: `copilot-assist` · `copilot` — 目标: —(待建: golden-eval 的 Judge 段无主待建)
- **动机**: workflow doc §2.1 强制诊断: 不只是机械 diff, 还要从'意图偏离'角度给分并指出原因(如语气不符 SKILL.md head 描述)。PM 依据这份诊断做最终验收。这是把'死 diff'变成'活判断'的关键。
- **证据**: 仅有一个 UI 预填按钮且不可达: copilot-panel.tsx:146-152 'Ask Copilot Judge' 仅 setDraft 一句提示语, 门控在 inEvalView; 而 inEvalView 恒为 false(view='eval' 无人传, 见动作1)。其自述文案 copilot-panel.tsx:140 '使用 Eval context endpoint, 非独立 judge 后端', 但后端 grep judge=0 命中、grep eval-context endpoint=0 命中 → 该 endpoint 不存在。INDEX §6 明确 'judge 无主待建'。无独立打分后端。

### [target-design] Copilot Judge 建议是否应把本次结果晋升为新的 golden baseline
- **能力·区域**: `copilot-assist` · `copilot` — 目标: —(待建)
- **动机**: 把 Judge 的评述直接连到下一步行动(要不要 promote), 减少 PM 手动决策负担。让 AI 评估闭环到具体操作建议。
- **证据**: copilot-panel.tsx:148 预填语含 '…whether this should become a new golden baseline', 但同动作9: 整条不可达(inEvalView 恒 false) + 无 judge 后端 + 与 promote(动作2)无任何代码联动。

### [target-design] 打磨编排: predict 完成 → 自动进入双屏对比(拟真输出 vs golden)的引导流
- **能力·区域**: `golden-eval` · `properties` — 目标: —(待建: 打磨编排无主)
- **动机**: alignment-notes 已知上下文标注 '打磨编排(predict 完→双屏对比)=无主'。把试飞产出和 golden 自动并排, 让 PM 在打磨阶段就能快速对照迭代, 是 Eval 与 Predict 之间的编排粘合。
- **证据**: 无任何编排代码: predictor 服务(services/predictor.py)产出 PredictDiagnosticExport(diagnostic_export.py:13)止于诊断导出, 不触发 compare; DiffView/useGoldenDiff orphan; Workspace.tsx 无 predict→diff 自动切屏逻辑。纯文档目标。

### [live] 点击 Publish/Release 上线本次 Skill
- **能力·区域**: `publish` · `shell-layout` — 目标: —(待建: INDEX §6 publish 无主待建)
- **动机**: 验收通过后一键上线, PM 绝不需要切出 Studio 去终端手动提交(workflow doc §2.2 底层机制注)。这是迭代周期闭环的收口动作。
- **证据**: components/studio/Header.tsx:35 usePublishSkill(skillId) + Header.tsx:119-122 'Release' 菜单项 onClick publish.publish() = live; hooks/usePublishSkill.ts:48 publishSkill → api/client.ts:78 POST /skills/{id}/publish; 后端 routers/skills.py:246 publish_skill 真实执行(见下)。注意: 入口落在 Header 的 'Team' 下拉菜单(非 workflow doc §2.2 说的'界面右上角独立 [Publish] 按钮')。

### [live] Publish 底层: 打包 skill 目录为 zip 并上传 Artifact Registry(非 git add/commit/push)
- **能力·区域**: `publish` · `shell-layout` — 目标: —(待建)
- **动机**: 实际上线机制是发布制品到 Artifact Registry, 不是提交源码到 git 仓库。workflow doc §2.2 写的 'git add SKILL.md && git commit && git push' 与实现相反, 必须按代码纠正。
- **证据**: routers/skills.py:286-293 build_publish_package(zip, 排除 .workspace/.git/.kiro)+ registry.upload_artifact; services/artifact_registry.py:46-88 httpx POST {host}/api/v1/artifacts(Bearer token); 返回 PublishResult(artifact_id)(skills.py:326)。git 仅用于 Save/Sync-to-Team(git_collab.py:222 TEAM_SAVE_COMMIT_MESSAGE / git_local.py:135), 与 Publish 无关。

### [live] Publish 前置校验失败退路(user_id 未配 / registry host/token 未配)
- **能力·区域**: `publish` · `shell-layout` — 目标: —(待建)
- **动机**: 上线依赖 Settings 里的 user_id 与 registry 配置; 缺失时必须明确报错并指引去 Settings, 而不是静默失败(失败退路也是动作)。
- **证据**: routers/skills.py:257-283 三重守卫: APP_SETTINGS_INCOMPLETE(400, '请到 Settings 设置')/REGISTRY_NOT_CONFIGURED(host)/REGISTRY_NOT_CONFIGURED(token); 网络/上游错误 skills.py:305-322 REGISTRY_API_ERROR(502)/REGISTRY_NETWORK_ERROR(503, backoff)。前端 usePublishSkill.ts:57-66 失败转 toast.error(ERROR_TOAST_MESSAGE='Release validation failed…')。

### [stale-doc] 填写可选 Commit Message(留空则 Copilot 自动生成发布说明)
- **能力·区域**: `publish` · `shell-layout` — 目标: —(待建)
- **动机**: workflow doc §2.2 要求 Publish 弹窗带可选 commit message 输入 + Copilot 智能托底自动生成。但当前实现既无该字段也无该 UI, 文档与实现不符, 需纠正/重建。
- **证据**: PublishSkillReq 只有 version 字段(models/publish.py:10-13, extra='forbid'), 无 commit_message; api/client.ts:78 publishSkill 不传任何 message; Header.tsx:119 Release 是直接菜单项无弹窗无输入框。commit_message 相关 grep 仅命中 git_local.py:135/git_collab.py:222(属 Save-to-Team, 非 publish)。Copilot 自动生成 commit message 无实现。

### [stale-doc] Publish 成功反馈(撒花特效 + 已成功发布提示)
- **能力·区域**: `publish` · `shell-layout` — 目标: —(待建)
- **动机**: workflow doc §2.2 要求成功后撒花(confetti)庆祝闭环。当前成功只弹普通 toast, 撒花组件已写但从未被调用, 文档与实现不符。
- **证据**: 成功路径 hooks/usePublishSkill.ts:50-54 仅 toast.success('Released to production: …') + 200ms 后复位, 无撒花; lib/confetti.ts:3 celebrateSuccess() 已实现(canvas-confetti)但全仓 grep confetti/celebrate(排除 lib/confetti.ts 与 .d.ts)零调用方 → orphan-unused, 未接入 publish 成功路径。

### [live] 发布成功后回到主页开始新探索(闭环完成)
- **能力·区域**: `skill-workspace` · `shell-layout` — 目标: —(skill-workspace 见 alignment-notes D11 已锁 IDE/workspace 模型, 但回主页动作无专属 REQ)
- **动机**: workflow doc §3: 一次迭代周期闭环, PM 可回主页重启探索。这是旅程的终点交接(回到 01_init)。
- **证据**: Header.tsx:57-65 'Back to Home' 按钮 onClick onHome(); 与 publish 成功无自动联动(publish 后不自动跳主页), 但回主页能力本身 live。capability 用 skill-workspace(INDEX §6: 打开文件夹/Recent/…), region shell-layout(Header)。

**跨切**: 权威序裁定记录(本节点): (1) Publish 机制 — 以代码为准: 实测 = Artifact Registry zip 上传(skills.py:286/artifact_registry.py:46), workflow doc §2.2 的 git add/commit/push 是 stale-doc(已与 INDEX §9/§6 'publish 文档与实现矛盾' 一致); 同理 commit message 输入 + Copilot 自动生成 + 撒花特效均为 stale-doc(PublishSkillReq 无字段 / confetti orphan)。(2) Diff 归属 — 结构化 before/after reducer 级 diff 有 spec 主 = trace-inspector REQ-7(P2 依赖引擎), 与本节点 golden-eval 的'整段字段 diff'(golden_diff.py compare, 无主待建)是两条不同的 diff: 前者是 trace 内 phase 转移的 key 级高亮, 后者是 run 终态 vs golden 的全量字段对比。两者都未挂前端 UI。(3) 组件本体 vs 旅程 — 按 INDEX §2 不变量: DiffView/DiffField/DiffScore 等组件本体应归 03_regions/properties(INDEX §6 已声明 properties 含'(未来)Diff'); Publish 按钮本体归 shell-layout(Header); Copilot Judge 对话本体归 copilot region; 本节点(workflow)只链接, 不重述。(4) D12 写入全量 Rust — golden 固化(copy final_state.json)、golden 目录 CRUD、publish 打包落盘当前都在 Python(golden_diff.py shutil.copyfile / artifact_registry.py)与 INDEX §6 native-fs(Rust owns runs 目录 + golden CRUD + 闭环编排)冲突: 这些写/编排步骤目标态须迁 Rust 命令, Python 端退为只读+引擎计算。标注为'经 Rust 文件命令'是目标设计, 当前实现仍 Python。(5) 引擎计算归属 — compare 的 diff 算法当前在 Studio backend(golden_diff.py), 但按 INDEX §6 engine sidecar owns eval, 目标态 eval 计算应归 engine。(6) 现状总体: 本节点是'后端实/前端虚'的典型 — golden 固化/compare/publish 后端 live 或 backend-only, 但 Diff 可视化整条(DiffView+useGoldenDiff+report export)orphan-unmounted, Judge 与 Eval 视图入口 target-design(view='eval' 无人传, 整个 Eval 模式不可达)。

**待定**:
- golden-eval 与 publish 在 INDEX §6 均为'无主待建', 无专属 studio-feature-* spec。本节点 17 个动作里 14 个 target_spec=待建。是否需要新建 studio-feature-golden-eval 与 studio-feature-publish 两份 spec 来承接(尤其 Judge 打分契约、打磨编排、Diff 视图归属、publish 是否要补 commit message/撒花)? 还是确认这些是 P2/未来不立 spec?
- useGoldenDiff.ts:27 调 GET /skills/{id}/runs/{runId}/compare, 后端只有 POST /compare(compare.py:14) 与 GET /diff(compare.py:23) — method/path 不一致。因 useGoldenDiff orphan 当前不暴露, 但接线时必须先对齐(改前端走 GET /diff, 或后端补 GET /compare)。属实现期 bug, 登记备查。
- Copilot Judge 自述'使用 Eval context endpoint'(copilot-panel.tsx:140), 但后端无此 endpoint。Judge 的目标实现路径是: ①真做一个 eval-context 端点把 artifact+golden diff 注入 copilot 上下文, 还是 ②纯靠 copilot 现有对话 + 前端把 diff 文本塞进 draft? 决定后才能定 Judge 的 backend 归属(gateway chat vs 新端点)。
- G3 artifact 落盘改 FROZEN(io.outputs 加文件路径)与本节点 golden 固化都涉及'把产出固化到磁盘', 但语义正交(artifact=作者声明的产出落盘; golden=验收基线快照)。需确认两者目录是否都归 .workspace 下(artifacts/ vs golden/), 由 native-fs(Rust)统一编排, 避免概念混淆。
- Publish 入口当前在 Header 'Team' 下拉(Save/Sync/Submit/Release 四合一, Header.tsx:106-123), 与 workflow doc §2.2'界面右上角独立 [Publish] 按钮'不符。是接受现状(Release 藏在 Team 菜单)还是按 doc 提为独立按钮? 属 UX 取舍, 待 PM 拍。
- golden 的 lock 语义: GoldenBaseline.locked 字段存在(golden.py:16)、SetGoldenReq.lock 可传, 但前端 useGoldenDiff.promote 恒传 lock:false(useGoldenDiff.ts:48), 且无任何'锁定 golden'UI。锁定 golden 是否是需求(防止误覆盖基线)? 若是需归入 golden-eval。

---

## 审校(Critic)

### 缺口(gaps)
- [probe-17 是残件] node='probe-17' (= 02_authoring) 的 scope_summary 和 cross_cutting_notes 字段值都是字面量 'x', open_questions 缺失。这是 6 个节点里唯一没有写 scope/边界/移交说明的节点。它承载 graph-authoring/phase-editing/file-editing/compile-lint/conflict-overwrite 多个核心能力, master doc 不能基于它的 scope 写 02_authoring 章节。必须打回补全 scope_summary(owns/not-owns 边界)+ cross_cutting_notes, 否则 01/02 节点边界(尤其'新建 skill 脚手架归属'见 01_init open_question #4)无法闭合。
- [失败退路缺口 - copilot 持久化崩溃态] D8(硬需求 MUST)= copilot 对话退出再进恢复一模一样。01_init 把'重进 workspace 须恢复对话'登记为 target-design 旅程事实, 但**没有任何节点登记'持久化写盘失败/session 文件损坏/读回失败'的失败退路**。Cursor 同款体验下, session 落盘失败如果静默吞掉=用户对话丢失且无感知, 违反零容忍静默失败铁律。建议在 copilot/native-fs spec 补一条失败退路动作(写盘失败显式告警 + 不静默)。
- [REQ 覆盖缺口 - 02_authoring REQ-9] canvas-topology spec(权威源)的 REQ 编号在各节点零散出现(REQ-1 TB / REQ-2 黑板连线 / REQ-6 L1-L3 下钻 / REQ-10 Properties 白名单 / REQ-11~14 运行态)。但 probe-17 动作表里**未见 REQ-7/REQ-8/REQ-9 的对应动作**(REQ-7 结构化 diff 被 trace-inspector 认领没问题; 但 REQ-8 '加字段须改契约'、REQ-9 若存在则无人认领)。因 probe-17 scope='x' 无法判断是有意移交还是漏掉。需对照 canvas-topology requirement.md 全量 REQ 清单逐条核对 probe-17 覆盖。
- [失败退路缺口 - 04 batch 部分失败的前端可观测] 04_execution '批量中某输入失败显式报告'标 backend-only, 证据说 batchError 在孤儿 useBatchRun.ts:98(未挂载)。后端逐项 status 可见, 但**前端无任何已挂载路径能 surface 单项失败**。这不只是'待接线', 而是 skill-lifecycle R3.4(失败显式上报, 不静默)当前在前端**完全不可达**——批量旅程一旦上线而 surface 没接, 就是静默失败。建议 master doc 标注: batch surface 接线是 R3.4 合规的前置, 不可只挂 BatchRunner 而不挂失败项渲染。
- [动作缺口 - settings region 无节点认领] 01_init 明确把 settings 内容移交 settings region, 06_eval 的 publish 前置校验失败退路指向'去 Settings 配 user_id/registry'。但 6 个节点里**没有任何节点拥有 settings region 的用户旅程**(INDEX §6 也标 settings='无 region 文档')。API keys/LLM roles/copilot 配置/artifact 路径配置 是 publish 和 predict 的硬前置, 却没有 workflow 节点覆盖其旅程。master doc 应确认 settings 旅程是否需要独立 workflow 节点(如 00_settings), 否则 publish 失败退路的'去 Settings'指向一个无主区域。

### 不一致(inconsistencies)
- [所有权不变量违反 - run-execution 的 stage 机跨 03/04 重复描述] 03_prediction 和 04_execution 都详细描述了同一个 center-action-bar stage 门控机(idle→compiling→compile-pass→predicting→predict-pass→running), 都引 center-action-bar.tsx:42-59 + Workspace.tsx:400-419。按 §2 不变量, stage 机这个'跨组件行为'应只在**一个** capability(compile-lint 或 run-execution)写实现, 其余链接。两节点都把'predict-pass 永不置位→Run 不可达'作为自己的 cross_cutting 核心结论重述, 是同一实现被 predict + run-execution 两 tier 重复描述。master doc 需裁定 stage 机归属单一能力(建议 compile-lint, 因 stage 派生在 center-action-bar)。
- [capability 越界 - 04/05 把 'i/o panel 改名' 归属打架] 03_prediction cross_cutting 说 'input region → i/o panel, PM 已定', 把测试输入导入/列出/删除/kind 分区 全落 predict 能力 + input region。但 alignment-notes G3/'input panel→i/o panel'原话明确: i/o panel 每节点 io 设置 = REQ-2 黑板字段勾选落点, panel 组件本身归 canvas/graph-authoring。03 自己也说'panel 组件本身归 canvas/graph-authoring'。**矛盾**: 03 把 input region 的多个动作(test_inputs CRUD)标 predict 能力, 但 region 改名 i/o panel 后该 region 的组件所有权归 graph-authoring/phase-editing(G3: 每节点 io+artifact 设置)。test_inputs 数据流(predict)与 io 字段设置(phase-editing)挤在同一改名后的 region, 需在 master doc 明确 i/o panel 里'测试输入段'(predict)vs 'io/artifact 设置段'(phase-editing)是两个能力共用一 region, 不是 predict 独占。
- [跨节点 status 不一致 - batch-run orphan vs backend-only] 同一'批量运行触发'动作: 03_prediction 标 `orphan-unmounted`(证据 useBatchRun 完整实现但 BatchRunner 未挂载), 04_execution 也标 `orphan-unmounted`(同证据)。一致。但'批量失败显式上报'03 标 `target-design`(证据 BatchRunner 未挂载 + useBatchRun 仅记 batchError 总错无逐项), 04 标 `backend-only`(证据后端逐项 status 可见, 前端 batchError 在孤儿)。**同一失败上报能力两节点给了不同 status(target-design vs backend-only)**。实际: 后端逐项 status live + 前端孤儿未挂载 → 更准确是 backend-only(后端就绪/前端无 surface), 03 的 target-design 偏轻。master doc 取 backend-only。
- [capability 归属漂移 - run-execution 动作出现在 03_prediction] 03_prediction 把'选多个测试输入批量运行''序列自动批量''批量失败上报'三条动作的 capability 标为 `run-execution`(正确, 它自己也注明'批量更偏 run-execution, 触发入口落测试输入面板')。但这三条同时也完整出现在 04_execution(run-execution 的主节点)。**同一 run-execution 动作在 03 和 04 各列一遍**, 属旅程节点正常的多节点引用(一能力→多节点), 但两处的 status/证据需保持同步(见上条 batch 失败 status 打架)。master doc 应以 04(run-execution 主节点)为 batch 动作的权威 status 源, 03 仅链接。
- [region 名疑似越界 - 04 用了 state-engine / native-fs / engine / local-history 作 region] 04_execution 多条动作的 region 字段填了 `engine`(后端 spawn)、`state-engine`(REQ-13 推流)、`native-fs`(autocommit)、`local-history`(RunDetailDrawer)。但 INDEX §6 的 **03_regions(12)是 UI 区域**, engine/native-fs/state-engine 属 **04_platform(4)** 不是 region; local-history 确在 §6 region 表内(✓)。把 platform 块当 region 填进动作表的 region 列, 违反三维正交(region=UI 区域 vs platform=后端块)。05_debugging 同样用了 state-engine/native-fs 当 region。master doc 需把这些动作的 region 列改为真实 UI 落点(如 REQ-13 推流的消费 UI 在 timeline/canvas), platform 归属用'依赖的 platform 服务'另列, 不混进 region。

### status 抽检
- [已核实 - 准确] 06_eval action='Publish/Release 上线' status=live: 核对 Header.tsx:35 usePublishSkill + :119-121 Release DropdownMenuItem onClick publish.publish() ✓; 后端 skills.py:246 publish_skill + artifact_registry.py upload_artifact(POST {host}/api/v1/artifacts, Bearer)✓; build_publish_package zip ✓。live 成立。补充: Release 确实藏在 Team 下拉(非独立按钮), 节点已正确标 stale-doc。
- [已核实 - 准确] 06_eval action='Promote to Golden' status=backend-only + '409 predict 守卫' status=backend-only: golden_diff.py:34 set_golden_baseline_for_run 真 copy final_state.json + 调 assert_trace_can_be_promoted_to_golden(diagnostic_export.py:25-42, 抛 409 PREDICT_TRACE_CANNOT_BE_GOLDEN not_retryable)✓; 前端 useGoldenDiff 零非自身/test importer ✓(grep 证实)。backend-only 成立。
- [已核实 - 准确] 06_eval / 04 / 05 多条 orphan-unmounted(DiffView/useGoldenDiff/TracePanel/useRunStream/PromptInspector/confetti): grep src 全部零非自身/test importer ✓。orphan 成立。inEvalView=view==='eval' 存在但 `view='eval'` 无任何 caller 传入(grep 仅 copilot-panel.tsx 内部 3 处自用)→ Eval 模式整体不可达 ✓, 06 action#1 target-design 成立。
- [已核实 - 准确] 03/04 predict backend chain backend-only: runs.py predict_run → predictor.py dispatch_predict_job → predict_skill(from graph_agent)→ _persist_predict_result ✓; MAX_PHASE_REVISITS=10 + PredictDeadlockError + SDK 死锁转抛(predictor.py:124-125)✓。backend-only 成立。前端 onPredict/onRun=console.info(Workspace.tsx:537-538)✓ placeholder 成立; startRun 仅 client.ts:154 定义零业务 caller ✓。
- [已核实 - 准确] 04/05 节点灯 statusByNodeId placeholder: grep 证实 Workspace.tsx:515 与 SplitEditor.tsx:102 两处 GraphCanvas 渲染**均不传 statusByNodeId** ✓。这是'节点灯随真实 run 亮起'判为 placeholder(非 live)的载荷证据, 两节点都正确。注意不能因 SkillNode 有完整 STATUS_STYLE 就误判 live——节点已正确避坑。
- [已核实 - 准确] 01_init 注册表模型(影响全层 status 的核心判定): services/skills.py:183 list_skill_summaries 聚合 public_ids + workspace_ids + metadata.list_skills + 自动发现 unregistered ✓; useSkills.ts SWR '/skills' ✓; delete_skill = unregister_skill + remove index/summary 无 rmtree ✓(:436-447); import 校验门 _raise_invalid_directory_path 'missing GRAPH.md or SKILL.md' 真实存在 ✓。'现机制=注册表, 与 D1/D11 无注册表方向冲突→标 stale-doc/stale-code 而非 live' 的整体判定成立。
- [行号轻微漂移 - 不影响结论] 01_init 引 services/skills.py:517-522 为 import 校验门, 实测在 ~515-521(create_skill 函数内 import 分支); 06_eval 引 compare 在 golden_diff.py:68-110, 实测 compare_run_to_golden 起于该区间且 _diff_value depth<5 在 132/146 ✓(与 06 自述 depth<5 一致)。多处证据行号有 ±几行漂移(常见于活跃改动分支), 但指向的代码实体均存在且语义相符, 不影响 status 判定。
- [未独立核实 - 引擎侧, 标注待核] 04/05 多条引 packages/graph-agent 的 events.py(32 类事件 / phase_start/end 携带 context / WorkingMemoryUpdateEvent / PromptCapturedEvent / AmbiguityReportEvent)与 public-api-contract.md(RunResult.source/PhaseRecord.mocked_source/PathDiff)。本轮抽查集中在 studio backend + frontend, **未打开 packages/graph-agent 源码逐一核对事件类与字段**。这些是 target-design/backend-only 动作的引擎侧依据, master doc 引用前建议实现期核实引擎契约(尤其 G3 open_question: artifact 写入点是否保留最终 business_data_md, alignment-notes 已标'实现期核')。

### FROZEN 改动合并(critic 原始)
- [FROZEN-1] 删 `04-subgraph` io 严格 1:1 映射(G2): 子图 input 改为从黑板按 io.inputs 过滤字段, 同任何普通节点; 删除 F-v3-subgraph-io-mismatch 的 1:1 强制。来源: probe-17(T5 'G2 删 04-subgraph io 1:1'、Properties白名单重建 'G2 删 io 1:1')+ 04_execution(边黑板卡片 frozen_change)+ alignment-notes §FROZEN清单#1。
- [FROZEN-2] `02`/`03`/`05` io.outputs 加 artifact 落盘路径标注(G3): io.outputs schema 顶层加文件路径(xx/xx/xx.json|md)+ 其下 schema; 支持一 schema 落多文件 / 多 schema 各落不同文件; 只写文件名=默认落 .workspace/artifacts; 文字格式仅 md/json; md 源用 agent 最终 validated business_data_md, 不做 json→md 回转。来源: probe-17(i/o panel 改名+artifact 'G3 io.outputs 加文件路径+schema 默认落 .workspace/artifacts; md 用 business_data_md 不回转')+ alignment-notes §FROZEN清单#2。
- [FROZEN-3] (引擎/runtime)节点级文件导入→黑板注入(G2 新需求): 任意 i/o 面板可导入文件 = 把文件字段注入黑板(同首 input 节点); 注入时机锁定为 a(跑到该节点才注入)。来源: 03_prediction(i/o panel 导入动作 frozen_change + open_question #6)+ alignment-notes §FROZEN清单#3。
- [FROZEN-4] (已登记)canvas REQ-2 黑板可视化连线 + 字段勾选 io.inputs: 删类型相等红叉, 改为按 io.inputs 切片字段高亮勾选(影响 io 语义)。来源: alignment-notes §FROZEN清单#4 + probe-17(T3 拓扑校验 'REQ-2 改黑板可视化 旧类型红已删')+ 04/05(边黑板卡片语义 = 从黑板按 io.inputs 切片, workflow doc 'context_bridge' 措辞 STALE)。
- [非 FROZEN 但配套删除项 - D2] 删 import 校验门(services/skills.py 缺 GRAPH.md/SKILL.md 必需检查)+ 删 import-error-format; 连带删除与 import 校验相关的错误退路(MANIFEST_VALIDATION_FAILED on import / 'missing GRAPH.md'), 仅留 OS 级失败(目录不存在/无权限)。来源: 01_init(打开现有文件夹 frozen_change + 失败退路 frozen_change + cross_cutting #3)。注: 这是纯实现删除项, 不改 FROZEN skill-spec 契约文件, 但属 FROZEN 范围外的连带改动, master doc 应与 4 条 FROZEN 改动分开列。
- [非 FROZEN 但全局写归属 - D12] 所有本地写/落盘统一'经 Rust 文件命令'(native-fs 唯一写者), 仅 engine/gateway 用 Python sidecar。受影响写步骤(跨全部节点): 新建 skill 脚手架+git init(01)、打开文件夹注册(01)、remove-from-recent 改 MRU(01)、serialize_graph/mutate_phase_body/新建 phase 写文件(02)、.workspace test_inputs/golden/runs/artifacts 读写(03/04/06)、predict result.json 持久化(03)、run 终态 final_state/metrics/trace.jsonl 落盘 + autocommit(04)、golden 固化 copy(06)、publish 打包落盘(06)、copilot session 落盘(01 D8)、篡改 state 落盘(05)。Python 端退为只读 + 编译/装配。来源: 全部 6 节点 cross_cutting D12 段 + alignment-notes [D12]。这是 master doc 的横切约束, 不是单条 FROZEN spec 改动。

### 总评 + 给 orchestrator 的建议
总体: 6 个节点里 5 个(01_init/03_prediction/04_execution/05_debugging/06_eval)是高质量产出——scope 边界清晰、owns/not-owns 移交明确、status 抽查全部经得起代码核对(我打开了 publish/registry、predict 链、409 守卫、golden compare、resume 501、注册表聚合、import 门、orphan grep、statusByNodeId 未传、autocommit git_status、ContextEdge/buildEdges mock 共 ~20 处 file:line, 无一证伪)。证据行号偶有 ±几行漂移(活跃分支正常), 不影响判定。最大的内容质量信号一致: 整层 Studio 是'后端实/前端虚'——predict/run/golden/publish 后端 live 或 backend-only, 但 TracePanel/DiffView/BatchRunner/PromptInspector/useRunStream/useGoldenDiff 全套已实现却零挂载(orphan), Eval 模式(view='eval')整体不可达。这个'孤儿组件未挂载 > 缺能力'的判断被多节点独立佐证, 可信。

给 orchestrator 写 master doc 的 5 条建议: (1) **probe-17(02_authoring)是残件**——scope_summary 和 cross_cutting_notes 都是字面量 'x', 不可直接入 master doc, 必须打回补全, 否则 01↔02 边界(新建 skill 脚手架归属)和 canvas REQ 全量覆盖无法闭合。(2) **裁定 stage 机单一归属**: idle→compile→predict→run 的 center-action-bar stage 门控被 03 和 04 重复详述(违 §2 不变量), 建议归 compile-lint 能力, predict/run-execution 只链接; 同时把'predict-pass 永不置位→Run 不可达'作为一个跨能力 known-gap 记一次, 不在两节点各记一遍。(3) **修正 region 列误用**: 04/05 把 engine/native-fs/state-engine(属 04_platform)填进了动作表的 region 列, 违反三维正交; master doc 应把这些动作的 region 改为真实 UI 落点, platform 归属另用'依赖的 platform 服务'列。(4) **batch 失败上报 status 取 backend-only**(04)而非 target-design(03), 并标注: 后端逐项 status live 但前端 surface 在孤儿 useBatchRun 里, R3.4(失败显式上报不静默)当前前端完全不可达, 接 BatchRunner 时必须同时接失败项渲染, 否则是静默失败违规。(5) **补两个无主缺口**: settings region 无任何 workflow 节点拥有其旅程(但 publish/predict 都硬依赖它), 以及 copilot 持久化(D8 MUST)缺'写盘失败'失败退路——两者建议 master doc 显式标记为待补节点/待补动作。FROZEN 改动我已去重合并为 4 条真 FROZEN(删子图 io 1:1 / io.outputs 加 artifact 路径 / 节点级文件导入注入 / REQ-2 字段勾选)+ 2 条横切(D2 删 import 门=非 FROZEN 连带删除; D12 写全量 Rust=全局约束), 见 frozen_change_consolidated。