# Requirements Document — studio-moirai-agent-system

## Introduction

把 Studio 的两条 AI 助手路径(面板内 SDK copilot 与「Open in CLI」的 ah/MoirAI 编排)统一成**一个代理人体系**:同一组角色文档(MoirAI + Clotho/Lachesis/Atropos)、同一份操作手册、同一个随包知识库、同一个技能池,由代码(而非散文)强制同一套工具边界;差异只保留在派遣机制(SDK 原生 subagent vs `ah ask`)与极薄的表面机制层。

两条底层原则贯穿全部需求:

- **基座 + delta(按运行位差异化)**:两条路的**主线程**都自带完整 Claude Code 基座 system prompt(SDK 经 `preset: claude_code`,CLI 天然内置);但 **SDK subagent 只有薄 harness 基座**——2026-07-09 spike 实测(research.md §T6):AgentDefinition 的系统提示约 300 词(身份句 + 基础语气/工具规约 + knowledge cutoff),**不含**完整基座的 file:line 引用规范/任务管理/安全政策/git 段,也看不到主线程 append;而 ah 路的女神是完整 CLI 实例,基座完整——两路女神的基座不对称。因此:资产只做 delta、与基座矛盾的内容禁止出现(不变);同时手册必须**薄基座自足**——对任务执行关键的纪律(证据引用格式、修改后验证、审批被拒判断义务)显式写出,不依赖完整基座兜底(R3.9)。(依据:vendored `claude_agent_sdk/types.py:1604-1612`、`types.py:86`——AgentDefinition.prompt 为纯 `str`,无 preset 入口;现状缺陷:copilot.py:651 传纯字符串把基座整个替换掉了。)
- **英文资产 + 语言跟随**:全部 agent 消费资产(roles/manual/knowledge/skills/contexts)以英文撰写;对用户的回复语言跟随用户消息语言(手册规则)。

需求源:PM 2026-07-07 两轮 + 2026-07-08 一轮指令(见 research.md §T5);上游设计:`docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md`(继承其阶段 2 成果,取代其 §9.8 知识接入方案,升级其 §7 SDK 路定位)。

**范围内**:`apps/studio/backend/app/agents/`(由 `app/prompts/` 更名重组)资产撰写、`copilot.py`/`copilot_tools.py` 装载与护栏改造、`apps/studio/tauri/src/lib.rs` 物化改造、相关设计文档回写。
**范围外**:ah 侧强制沙箱/hooks(等 ah 能力)、MCP 独立 stdio 化(阶段 3)、antigravity provider、F8 面板流式。

## Requirements

### Requirement 1: 资产单源四层布局与拼装契约

**Objective:** As a Studio 维护者, I want 所有 agent 资产收拢为 `app/agents/` 下单一真相源的四层布局,并以显式标记的拼装契约组合进各运行时产物, so that 两路装载同一套内容,后来者知道在哪编辑、怎么编辑。

#### Acceptance Criteria

1. The 资产树 shall 位于 `apps/studio/backend/app/agents/`(语义更名,替代 `app/prompts/`),收敛为 `roles/`(四份角色文档)、`operating-manual.md`、`knowledge/`、`skills/`、`contexts/`(极薄表面机制层)与 `agent-skill-map.json`。
2. The 技能池 shall 包含全部六个技能的文件源,其中 eval-judgement 与 moirai-intro 从 `lib.rs` 内联常量迁出;`lib.rs` shall 不再内联任何角色/技能/知识正文(含 `include_str!`),全部改为运行时从 backend 资产目录读取。
3. If 资产目录在装载/物化时缺少任一预期文件, then the 流程 shall 以明确错误中止(SDK 会话拒建 / Open in CLI 中止)并列出缺失路径,不得静默跳过或降级。
4. The 落盘拼装产物(`.ah/rules/*.md` 等 `.ah/` 物化文件)shall 由显式分段标记包裹每个来源段:`<!-- BEGIN assembled-section source=<相对路径> sha256=<8hex> -->` … `<!-- END assembled-section source=<相对路径> -->`,产物头部附来源清单;the 内存拼装产物(SDK append 字符串、AgentDefinition prompt)shall 仅在头部附一条来源清单注释、不加逐段标记——避免实现层路径在模型上下文反复出现(与 R2.9 零实现层词汇的精神一致),反暗箱由 R1.7 指纹承担。
5. The 每个源文件 shall 以编辑说明注释开头:本文件的职责、会被拼进哪些产物、编辑规范(英文撰写、只写 delta 不复写基座、事实契约引用 KB 不复写、机制性内容不入文档)。
6. The 全部资产 shall 以英文撰写;引用中文设计源时翻译并保留来源锚点。
7. When copilot 会话每轮开始, the `context_resolved` 事件 shall 回显覆盖**全部**资产(roles+manual+contexts+knowledge+skills+agent-skill-map.json)的版本指纹(`assets@<8hex>`,取代 `rules@<hash>`)——技能或映射变更同样必须反映在指纹里,不留反暗箱盲区。
8. The 旧资产 `copilot-rules.md` shall 被删除,其仍有效的内容按四层归位,不保留兼容读取路径。

### Requirement 2: MoirAI = 用户的代理人(scope 契合派遣)

**Objective:** As a skill 作者, I want MoirAI 像一个资深代理人:理解、research、规划、亲自执行;派遣时保证任务 scope 与女神专长完全契合,否则自己拆分 scope, so that 我得到结果闭环,而每位女神拿到的都是她能独立完成的完整任务。

#### Acceptance Criteria

1. The `roles/moirai.md` 操作协议 shall 规定:理解并澄清需求 → research 现状 → 制定计划 → 亲自执行;当且仅当某个子任务的 scope 完全契合某位女神的专长时才派遣;scope 不契合时 shall 由 MoirAI 自行拆分成契合的任务包再派遣,或亲自完成。
2. The 派遣单位 shall 为自包含任务包(目标、输入/上下文、边界、期望交付物);被派遣的女神在包内自主完成 research 与 plan;MoirAI 回收后汇总并对最终交付负责。
3. The `roles/moirai.md` shall 不包含「按用户所处阶段直接转交对应 agent」式的分诊规则。
4. The 首版角色文档 shall 不包含 few-shot 派遣示例(先以零示例测协议鲁棒性,偏差=提示词根因;few-shot 仅在 refine 阶段凭验收偏差证据决定引入);「分析一下这个 skill」→ 拆「领域/设计分析」派 Clotho 与「工程规范分析」(含 compile→predict 诊断链)派 Lachesis 并行、无 run 产物不派 Atropos、回收合成单份报告 shall 作为鲁棒性验收场景。
5. The `roles/clotho.md` shall 将职责定义为 graph_skill 的整体功能、领域能力、节点编排与 agent prompt 设计(怎么写才能发挥好)。
6. The `roles/lachesis.md` shall 将职责定义为工程规范:符合 engine 契约、编译通过、可正常运行。
7. The `roles/atropos.md` shall 将职责定义为以真实运行证据评估 graph 效果并给出终判与回流方向。
8. The 四份角色文档 shall 遵循三段式(身份锚点 + Wikipedia 渐进背景 + 内部操作协议)与人格写作方法论(只正面陈述、无防御性否认、实现脚手架词不进台词、对齐叙事真相源)。
9. The 人格文本 shall 以英文重新打磨:第一人称真正入戏,不泄露任何实现层词汇(ah/copilot/master/worker/派单),不携带修订过程语境,无「没人问就先否认」式台词;人格质量以 PM 通读认可为验收。
10. While 以 ah 路运行, the 派遣动词 shall 为 `ah ask <id> --wait`;while 以 SDK 面板路运行, the 派遣动词 shall 为原生 Agent 工具;两种表述 shall 由 `contexts/` 薄层提供(CLI 侧仅做女神↔id 绑定、不复述命令语法,见 R7.5),不写死在角色文档正文。

### Requirement 3: 操作手册同源(delta 纪律 + 诊断优先级 + 沟通规则)

**Objective:** As a skill 作者, I want 两条路径的 agent 遵循同一份工程纪律与沟通规则,诊断问题先走引擎诊断链, so that 两路行为一致、分析快而不漏、不与基座 prompt 重复或冲突。

#### Acceptance Criteria

1. The `operating-manual.md` shall 作为唯一手册源,经 R1.4 拼装契约进入 SDK append 内容、SDK 三女神 AgentDefinition prompt 与 ah 路四份 `.ah/rules/*.md`。
2. The 手册 shall 内置诊断优先级决策树:先 compile 拿全量聚合诊断;compile 干净后 predict 做无 LLM 空跑排除运行期结构错误;仅当两者均无法解释症状时才逐文件人工排查。
3. The 手册 shall 包含项目特有纪律:证据先行(结论附文件/行号/运行产物)、根因修复不打补丁、渐进披露(事实契约引用知识库不整段复述)、predict 产物不得用作 golden。
4. The 手册 shall 包含跨路沟通规则:回复语言跟随用户最后一条消息的语言;结论先行;写操作说明"为什么这么改"而不逐字复述改动。
5. The 手册 shall 规定审批被拒后的判断义务:重新评估任务条件是否仍然充分——能换路就换路;不能则停下向用户说明缺口与所需决策;shall 不在条件不足时降质续跑。
6. The 手册 shall 不包含:工具枚举、审批流程、路径白名单等由 harness 代码强制的机制性内容;以及 Claude Code 基座 prompt 已覆盖的通用行为(先读后改的一般形式、优先专用工具等)——仅当项目语义更严时(如"改完必须 compile 验证")才写出更严的那部分。delta 基线以**完整基座**产物(主线程/CLI)为准;薄基座下的自足性由 3.9 单独约束。
7. When 手册内容更新, the 变更 shall 仅发生于该单一文件并经 PR 生效,两条装载路无需各自改动即获得同一内容。
8. The 手册 shall 内置知识库入口(KB-00 场景路由的一行式索引),使含手册的每个拼装产物(主线程 append、三女神 AgentDefinition prompt、`.ah/rules/*.md`)都自带知识入口——被派遣的女神在任务包内自主 research,不得因拼装组合差异而丢失知识库入口。
9. The 手册与角色文档的拼装结果 shall 在 SDK subagent 薄基座下自足:任务执行关键纪律(证据引用带文件/行号、修改后验证、审批被拒判断义务)由手册显式承载,不依赖完整 claude_code 基座存在(依据 research.md §T6 spike;R3.3–3.5 的显式条目即此保障,本条为验收口径)。

### Requirement 4: 随包知识库(网状索引,渐进披露)

**Objective:** As a skill 作者, I want agent 的领域知识来自一个随应用分发、面向 agent 提炼、网状互链的知识库, so that 打包版不缺知识,agent 能沿链接快速跳转到所需契约,而不是遍历树杈目录。

#### Acceptance Criteria

1. The `knowledge/` 目录 shall 提供 KB-00 hub(场景→文档路由 + 链接图 + 链接解析规则)与主题文档,覆盖:skill 解剖与三种 phase 模式、io schema 与数据流、LOGIC/action 契约、SKILL/agent 节点与 mention、SUBGRAPH 契约、iterate、compile 诊断体系、predict 语义与 mock 策略、run/trace/checkpoint 与 resume/HitL、golden 评估、`.workspace` 运行时布局、LLM roles 心智模型与排障、Studio 阶段门与工具地图。
2. The 每篇知识文档 shall 采用 obsidian 式网状结构:frontmatter 含 `related:` 列表,正文在概念首次出现处以 `[[KB-xx-slug]]` 内联互链;链接解析规则(同目录文件名 stem)在 KB-00 声明。
3. The 每篇知识文档 shall 标注提炼来源(设计源路径+节),内容为面向 agent 的契约表/决策树/反模式,而非设计叙述的复制;与设计源冲突时以设计源为准并回修。
4. The SDK 路 shall 通过 `add_dirs` 挂载随包 `knowledge/` 目录,append 内容仅携带 KB-00 级别的一行式路由;the ah 路 shall 在工作区物化 `.ah/knowledge/`(受管头机制),rules 中以相对路径引用。
5. The `_mounted_doc_dirs()` shall 不再包含任何指向开发仓 `docs/` 的条目;`mounted/studio-config-map.md` 内容并入知识库对应主题后原目录退役。
6. While 应用以打包形态运行(backend 来自 vendor 快照), the 知识库 shall 与开发态内容一致且完整可读。
7. Where 设计源发生影响知识库内容的变更, the 同一变更集 shall 同步更新对应 KB 文档(reconcile 纪律写入手册方法论)。

### Requirement 5: 技能统一池(方法论层,事实引用 KB)

**Objective:** As a Studio 维护者, I want 全部技能出自同一池子、只承载方法论、事实契约一律引用知识库, so that 同一事实只有一处权威表述,技能按需交叉挂载。

#### Acceptance Criteria

1. The 六个技能 shall 全部以 `app/agents/skills/<name>/SKILL.md` 为唯一源;SDK 路经 `.claude/skills/` 物化,ah 路经 `.ah/skills/` 物化,内容一致。
2. The 技能内容 shall 限于方法论与工作流程(怎么干);涉及格式/契约/错误码等事实时 shall 以 `[[KB-xx]]` 引用知识库,不得复写事实本体。
3. The 角色↔技能映射 shall 集中声明于 `agent-skill-map.json` 单处,允许一个技能映射给多个角色;默认映射:moirai=moirai-intro;clotho=domain-analysis+graph-design+agent-prompt-design;lachesis=compile-error-repair+graph-design(交叉);atropos=eval-judgement+agent-prompt-design(交叉)。
4. The `moirai-intro` 技能 shall 重写为表面中立(自报协议:身份/工作区现状/三只手职责与状态/能做什么),编队状态查询动词由 contexts 提供(cli=`ah ps`;panel=三女神为常驻子 agent 随叫随到),两路装载同一份技能。
5. When 映射配置变更, the ah.toml 生成与 SDK AgentDefinition.skills shall 从同一配置派生一致结果。

### Requirement 6: SDK 路装载(基座 preset + append;原生 subagent 带工具)

**Objective:** As a skill 作者, I want 面板会话保留 Claude Code 基座 prompt 并在其后追加 MoirAI delta,三女神以原生 subagent 注册且各自带齐职责所需工具, so that 面板与终端同构,派出去的女神能独立完成任务。

#### Acceptance Criteria

1. The SDK 会话 shall 使用 `system_prompt={"type":"preset","preset":"claude_code","append":<拼装内容>}`;append 内容 = moirai 角色 + 手册(KB-00 路由已内含于手册,R3.8)+ panel 薄层(替换现纯字符串整体替换的用法)。
2. The SDK 会话 shall 通过 `ClaudeAgentOptions.agents` 注册 clotho/lachesis/atropos 三个 AgentDefinition:prompt 按 R1.4 契约拼装(角色文档+手册),skills 取 R5 映射,model 继承会话路由;AgentDefinition prompt 运行于薄 harness 基座之上(Introduction 原则 1),自足性按 R3.9 验收。
3. The 每个 AgentDefinition shall 配置其职责所需工具:三者均含读类工具;lachesis 额外含 `compile_skill` 与 `predict_skill` MCP 工具;atropos 额外含读取 run 产物所需的读类访问(经工作区)。
4. When 用户请求含明确契合某女神专长的子任务, the 面板 MoirAI shall 能经原生 Agent 工具派遣并汇总结果作答(R2.4 范式示例为验收场景)。
5. The `contexts/panel.md` shall 仅承载面板表面机制(judge_context XML 契约、写入产生 diff 卡片的机制说明、编队状态语义:三女神为常驻子 agent 经 Agent 工具随叫随到);通用沟通规则一律归手册(R3.4)。
6. The SDK probe 路(Settings 的 copilot 角色连通性冒烟:发固定小 prompt 验证模型+SDK 接线,要求确定性与低成本)shall 维持裸配置——无技能、无 MCP、不注册 subagents;真实会话路 shall 始终注册三女神。

### Requirement 7: ah 路装载对齐

**Objective:** As a skill 作者, I want 「Open in Claude Code」物化出来的 `.ah/` 内容与面板路同源同构, so that 两个化身读的是同一套资产。

#### Acceptance Criteria

1. When 「Open in CLI」以 StartFresh 打开工作区, the tauri 物化 shall 生成 `.ah/rules/{master,clotho,lachesis,atropos}.md`(按 R1.4 契约拼装:角色 + 手册 + `contexts/cli.md`)、`.ah/skills/*`(R5 池)与 `.ah/knowledge/*`(R4 知识库),全部带 Studio 受管头 + 内容 hash。
2. The 物化 shall 维持既有安全语义:受管头缺失或 hash 不匹配(用户改过)的文件不静默覆盖并报出冲突路径;已存在用户手写 `ah.toml` 时尊重用户配置不生成。
3. The `transient_ah_config_content` 生成的 ah.toml shall 从 R5 统一映射派生 skills 列表,并维持 `window_size = "follow"`、master 挂 moirai-intro 等既有阶段 2 验收约束。
4. The `.ah/rules/*.md` shall 不包含指向开发仓 docs 的路径提示(取代 ah-orchestration-design §9.8 资料表);知识引用一律指向工作区内 `.ah/knowledge/`。
5. The `contexts/cli.md` shall 仅承载 Studio 专属的 CLI 表面 delta:女神 agent id 绑定(clotho/lachesis/atropos,经 `ah ask <id> --wait` 派遣)与工作区事实;shall **不复述 ah 命令语法、不做命令可用性断言**——ah ≥ 1.4.0 的 master 内核与自动注入的内置技能(ah-commands/ah-config/ah-runtime-state/ah-operate)已是 CLI 侧命令事实的权威基座(ah-commands 自述 "Authoritative CLI reference"),基座+delta 原则同样适用。原「`ah status` 非可用命令」条目作废:ah 1.4.0 已提供 `ah status --json`(ah CHANGELOG #115),复述可用性必然随 ah 升级漂移。
6. The ah 路 shall 以 **ah ≥ 1.4.0** 为版本基线(master 内置技能注入、`ah status`、bare-start guard 均始于该版);when ah 升级改变内置技能覆盖面, the cli.md 的 delta 范围 shall 随之重审。

### Requirement 8: 工具边界代码强制(读放开 / 写圈定 / 审批超时停任务)

**Objective:** As a skill 作者, I want 工具边界由 harness 代码统一强制且宽严得当,审批超时的后果是停任务而不是带病续跑, so that 只读探索零摩擦,写操作被可靠圈定,任务质量不被"超时视为拒绝"糟蹋。

#### Acceptance Criteria

1. The SDK 读类工具(Read/Glob/Grep)shall 一律放行,不产生审批请求;实现 shall 用声明式 `allowed_tools`(CLI 层直放,types.py:1592),不在回调里写放行分支。此为对现状「读圈定 + 出圈审批」(`_READ_FENCED_TOOLS`,copilot.py:496-504)的**有意放宽**,依据:会话无网络出口工具、写侧有硬边界(8.2)、本地单用户环境。
2. The SDK 写类工具(Write/Edit)shall 仅允许目标位于当前 skill 工作区(含其内 subskill 子树)或 Skills 技能库根内;shall 排除 LLM 配置真相与应用设置文件(`llm/` 目录、app_settings.json 等)——配置变更只能经 Requirement 10 的服务层工具;白名单外 shall 直接拒绝并附原因,不进入审批等待。写边界的强制 shall 位于**对每次工具调用必然触发的层——`PreToolUse` hook**:SDK 契约明确 `can_use_tool` 仅在权限规则判 "ask" 时触发、会被 `allowed_tools`/`acceptEdits` 静默绕过,"To observe or gate *every* tool call regardless of permission rules, use a `PreToolUse` hook"(types.py:1747-1756);`can_use_tool` 仅承担审批 UX(Bash 挂起、白名单内写操作的 diff 卡流程),不承担硬边界。
3. The SDK Bash 工具 shall 维持挂起式审批语义(无 OS 沙箱前提下不伪造路径级围栏);命令前缀 allowlist 机制列为后续迭代。
4. The 审批挂起 shall 采用长时限(默认 30 分钟,可配置);if 挂起超时, then the 系统 shall 停止整个任务并向用户说明「等待审批超时,任务已停止(会话保留)」——shall 不将超时折算为拒绝后继续执行。停止 shall 实现为 interrupt 当前任务并**保留会话上下文**(不销毁会话):用户返回后可直接续起对话或重新下达,已完成的工作与上下文不因超时丢失(业界对照:Claude Code 权限弹窗与 Managed Agents `always_ask` 均为无限期挂起零损失;本设计以"停 + 可续"达成同等的不带病续跑且不弃前功)。
5. When 用户明确拒绝审批, the 拒绝及理由 shall 返回给 agent,后续行为按手册判断义务(R3.5)执行。
6. The 实施 shall 验证 CLI/SDK 控制协议侧不存在会截断长挂起的内部超时;若存在,从协议/参数层解决而非退回计时器拒绝。
7. The 角色文档与手册 shall 不复述上述机制;工具引导仅限判断性内容。
8. The ah 路的等价强制 shall 记录为已知差距与后续项(依赖 ah hooks/沙箱能力),本期不在 Studio 层造次优 workaround。

### Requirement 9: 补齐 predict MCP 工具,落地诊断链

**Objective:** As a skill 作者, I want copilot/MoirAI(及被派遣的 Lachesis)能亲自执行 predict, so that 诊断优先级决策树有完整的工具支撑而不是纸面流程。

#### Acceptance Criteria

1. The studio MCP 工具集 shall 新增 `predict_skill`(入参 skill_id;经 studio 后端既有 predict 出口执行无 LLM 空跑),与现有三工具同为零审批。
2. The `predict_skill` 返回 shall 含 success、逐 phase 记录摘要、path_diff 与诊断列表;超长明细 shall 截断并给出 `.workspace/runs/<run_id>/` 供 Read 深查。
3. When agent 按手册执行诊断流, the compile→predict 两步 shall 均可经 MCP 工具在会话内完成(主线程与被派遣的 lachesis subagent 均可调用)。
4. The 真实 run shall 不新增 MCP 工具,维持用户主动触发(UI/CLI)。

### Requirement 10: LLM 角色配置操作(经服务层的写能力)

**Objective:** As a skill 作者, I want copilot/MoirAI 能替我配置 LLM 角色(建角色、调模型组、排 fallback、改意图参数), so that 配 llm_role 这一设计环节不必离开对话去点 UI。

#### Acceptance Criteria

1. The studio MCP 工具集 shall 新增角色配置写工具(如 `update_llm_role` / `create_llm_role`:模型组增删与排序、fallback 开关、thinking/max_output_tokens/temperature 意图参数),一律经 studio 后端既有服务层/FastAPI 出口写入 gateway 真相——复用既有校验、canonicalize、级联与领域事件;shall 不直接写配置文件(底座一:配置写入走 frontend→FastAPI→gateway 通道,agent 即另一个前端)。
2. The 配置写工具 shall 零审批,但返回 shall 回显结构化变更摘要含 before/after 快照(前端以卡片呈现);the 变更卡片 shall 提供一键撤销——经同一服务层把 before 快照写回(撤销本身也产生变更卡);写入失败 shall 结构化返回错误,不抛栈。「零审批写配置 + 会话可读外部来料(skill 文件/导入材料)」的提示注入风险为**已评估接受**:密钥不经对话(10.3)、变更可见(卡片)且一键可逆(本条),记录于 research.md 风险节。
3. The 凭据/endpoint 的新增与密钥录入 shall 维持 UI 通道(密钥不经模型上下文往返);后续按需另评估。
4. The KB(LLM roles 篇)shall 说明这些工具的能力面与选用时机。
