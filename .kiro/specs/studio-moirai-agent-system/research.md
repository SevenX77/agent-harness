# Research & Design Decisions — studio-moirai-agent-system

---
**Purpose**: 沉淀本 spec 的调研发现与决策依据。四路并行调研(engine 契约 / gateway 概念 / studio 用户旅程 / copilot+ah 设计与资产)+ 对承重设计源的亲读核实。

**Discovery Scope**: Complex Integration(横跨 tauri / studio backend / prompts 资产 / 设计文档,不改 engine·gateway 核心)
---

## Summary

- **Feature**: `studio-moirai-agent-system`
- **Key Findings**:
  1. **知识挂载在打包版会整体消失**:copilot 的 4 个挂载目录中 3 个指向开发仓 `docs/`,靠 `Path(__file__).parents[5]` 反推仓根,打包版 `is_dir()` 不成立即静默省略(`copilot.py:140-165` 注释自供"仓库 docs 缺席时(打包版)对应条目自动省略")。ah 路的知识接入(§9.8)同样把开发仓 docs 路径写进设计表。
  2. **copilot 没有"诊断优先级"心智**:规则文档只把 `compile_skill` 列进工具清单,没有 compile→predict→人工 的决策树;predict 根本没有 MCP 工具(现有仅 `get_llm_roles` / `compile_skill` / `run_role_test`,见 `copilot_tools.py:144-153`),copilot 想走 predict 也走不了。
  3. **角色/规则双源且不同构**:SDK copilot = 单体"Studio Copilot"人格(`copilot-rules.md`);ah 路 = MoirAI 四角色(lib.rs 内联常量)。`copilot.py:92-94` 注释声称"ah 拉起路装载同一份 [copilot-rules.md]"与代码不符(全仓 grep 无 tauri 引用)。
  4. **SDK 原生支持 subagents**:`ClaudeAgentOptions.agents: dict[str, AgentDefinition]`(vendored `claude_agent_sdk/types.py:1787`),`AgentDefinition` 具备 `description/prompt/tools/disallowedTools/model/skills/permissionMode/effort/maxTurns`(`types.py:82-100`)——copilot 可用原生 Agent 工具派遣三女神,与 ah `ah ask` 同构。
  5. **运行时路径大头干净**:技能库/工作区/settings 全在 `%APPDATA%\AgentStudio`(`paths.py:17-61`),不在开发仓;唯一伸进开发仓的就是挂载 docs(发现 1)。
  6. **工具边界两极分化**:SDK copilot 无 OS 沙箱、全靠进程内 `can_use_tool` 护栏(读圈定+审批、写圈 workspace、Bash 逐条挂起审批,`copilot.py:301-349`);ah 路 systemd scope 只是生命周期隔离,agent 以 `--dangerously-skip-permissions` 运行、文件系统零限制。
  7. **SDK subagent 只有薄基座**(2026-07-09 spike 实测定谳,§T6):AgentDefinition 系统提示 ≈300 词,无完整 claude_code 基座各段——「两路都自带基座」前提修正为四运行位差异化;同日 ah 1.4.0 发布使 CLI 侧命令事实基座变厚(master 内置技能),cli.md 收缩为纯 Studio delta。

## Research Log

### T1 — Engine:graph_skill 契约与三段生命周期

- **Sources**: `docs/engine/mvp1/01-contract/02-skill-syntax/00-FORMAT-GROUND-TRUTH.md`(§1 目录布局、§2 GRAPH.md、§3 LOGIC、§4 SUBGRAPH、§5 SKILL、§6 io schema、§7 iterate、§8 mention、§10 sequential-overwrite);`packages/graph-agent/src` 的 `compiler.py:41`、`loader.py`、`runner.py:268/453`、`error_registry.py`。
- **Findings**:
  - skill = `GRAPH.md` + `phases/<id>/` 每目录**恰好一个**模式文件(`LOGIC.md`/`SUBGRAPH.md`/`SKILL.md`,类型由文件名决定,frontmatter 禁写 `mode`/`phase_id`);`schema_version` 精确 `"v0.3.0"`;io 一律 Draft 2020-12 inline object(`type: object` + `properties` 必有 + `required ⊆ properties`)。
  - 三名一致(frontmatter `phases` = body `<phase>` = 目录名);DAG 无环无孤岛(`[F-v3-graph-phase-cycle/island]`)。
  - LOGIC action 契约 `def <name>(inputs) -> dict`,纯度扫描拒 FS/`run_skill`/`sys.path`/动态 import;SUBGRAPH `path`(inputs 宽松、**outputs 与子图严格相等**);SKILL 节点 body 必有 `<role>`/`<goal>`,mention(`@tool:`/`@subagent:`/`@subgraph:`/`@reference:`/`@example:`/`@protocol:`)编译期必须可达;`use_graph_llm_role: true` = 图级角色优先且**不销毁**节点自身 `llm_role`。
  - **compile**:单出口 `compile_skill()`,一次返回全量 `CompileResult.issues`(96 个 `[F-v3-*]` 码,`export_error_catalog()` 带 remediation);能查语法/拓扑/io 契约/纯度/mention/iterate,**不能**查 `.workspace` 数据、真实执行行为、LLM 角色可用性。
  - **predict**:`predict_skill()` LLM-free 空跑——compile + 真跑 LOGIC action + agent 节点走 mock 策略(P0 golden case → P1 copilot 回调/手动覆盖 → P2 启发式占位),外加 path diff;能暴露 compile 抓不到的 `[F-v3-runtime-state-mapping-failed]`、`[F-v3-iterate-over-not-list]`、golden 装载失败等运行期结构错误。
  - **run**:真执行 + 33 种 typed 事件进 `trace.jsonl` + 按超步 checkpoint(namespace:外层 `""` / `agent:<phase>` / `iter{k}`);`resume_skill()` 支持 checkpoint 续跑、`context_overrides`(篡改黑板)、`tool_call_responses`(HitL)。
  - **golden**:`.workspace/golden/<baseline_id>/`(baseline.json + cases/ + report.json),逐节点字段级 diff + 评分;predict 产物禁止升级为 golden(假数据),run 产物可播种。
- **Implications**: 知识库 KB-01..KB-11 的内容框架与来源即由此确定;compile→predict→run 的"能查什么"分层是操作手册诊断决策树的事实依据。

### T2 — Gateway:LLM 配置心智模型

- **Sources**: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/{schema,resolver,credentials,error_classification}.py`、`role_materialization.py`、`gateway_chat_model.py`;studio 侧 `llm_role_materializer.py`、`routers/llm.py`。
- **Findings**:
  - 概念链:credential/endpoint(v4 `llm_credentials.json`)→ route(`endpoint_id:route_slug`,状态 verified/unverified_manual 才可执行)→ role(`llm_roles.yaml`,model groups → materialize 成 fallback_chain)→ 运行时 `GatewayChatModel` 按序尝试、按 HTTP 状态分类(401/403/404 fallback 下一条,429/5xx 重试,业务 400 fail-fast)。
  - 作者最小心智:`llm_role` 按名精确匹配;空 fallback_chain = 全部 failed/off/cooling_down 或 role 无 model_groups;`materialization_report` 有 warnings(如 thinking_unsupported)与 skipped 明细;`run_role_test` 只探测不改配置。
- **Implications**: KB-12 的内容框架;Agent 节点排障表(症状→检查点)可直接落知识库。

### T3 — Studio:设计态用户旅程(9 阶段)

- **Sources**: `docs/studio/mvp1/01_workflows/`(00_settings-ux-spec / 01_init / 02_authoring / 03_compile / 04_run-and-verify / 05_debugging / 06_eval);`02_capabilities/compile-lint/mvp1-alignment.md`(F6 + 2026-07-05 数据链澄清);`02_capabilities/{predict,golden-eval,run-execution,trace-observability,skill-workspace}` 等 14 个能力单元;`03_regions/` 12 个 UI 区域。
- **Findings**(旅程主干,详表见 design.md §用户旅程):
  1. 打开/新建/导入(IDE 工作区模型 D11,无导入门 D2,Rust 唯一写者 D12)
  2. 画布拓扑设计(建节点/连线→写 `depends_on`→即时 relint;子图内联展开/下钻)
  3. 节点编辑(Properties=frontmatter 白名单;Editor=正文 XML;节点级 role test / 自定义模型参数进 `runtime_config.json`)
  4. 实时 lint + 手动 Compile(**诊断 SSOT**:单出口全量聚合,徽章/tooltip/行内 marker/抽屉四面同一份;warning 不拦 Predict,error 拦)
  5. 输入数据准备(`.workspace/import_files/` + `runtime_config.json` 绑定,studio preflight 并入同一次 compile 结果)
  6. Predict(硬门:predict-pass 才解锁 Run;agent 节点 mock,零 token;409 禁止 predict 产物变 golden)
  7. Run(真跑;节点灯;trace 面板;边 dot 双态=赛前静态黑板推断/赛后真实过渡)
  8. Debug(节点级 Resume/HitL/篡改上下文)+ Golden(三态 🔘untested→🟡logic_ok→🟢has_golden;run 产物播种;字段级 diff)
  9. 收尾(run 成功自动 git commit;发布低优)
- **Implications**: "用户在每一阶段必须懂什么"直接映射成知识库主题与角色技能分工;compile→predict→run 阶段门是 MoirAI 判断"该伸哪只手"的生命周期轴。

### T4 — copilot/ah:设计源与现有资产

- **Sources**(亲读核实): `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md`(854 行,2026-07-07 更新)§5/§6.4/§8/§9.3/§9.4/§9.5/§9.8/§9.9;`apps/studio/tauri/src/lib.rs`(#476 后:`MOIRAI_INTRO_SKILL` :537、`STUDIO_AH_MANAGED_FILES` 十文件、`transient_ah_config_content` :803 master 挂 `moirai-intro`);`apps/studio/backend/app/services/copilot.py`、`copilot_tools.py`;`app/prompts/` 全树。
- **Findings**:
  - **设计已定的**:三位一体关系模型(Moirai=统称结合体,非第四个上司,§5);人格写作方法论四条(§6.4:写自我认知、只正面陈述、脚手架词不进台词、对齐叙事源 `docs/strategy/moirai-copilot-persona-narrative.md`);rules 三段式收敛(§9.5:身份锚点+Wikipedia 渐进背景+内部操作协议);项目根=skill 工作区、`.ah/` 物化布局(§9.3);受管头+hash 防覆盖(§9.4);已有 `ah.toml` 用户优先(§9.4);阶段 2 验收清单(§9.9)。
  - **设计缺口(§8)**:MCP 独立化(阶段 3)、知识库挂载(`[sandbox] additional_ro_binds` 在 WSL user scope 落成 `BindReadOnlyPaths` 被拒→agent 秒退,推迟)、antigravity provider。
  - **§9.8 现状**:知识接入 = rules 里写明**开发仓 docs 路径表**(`docs/engine/mvp1/`、`packages/graph-agent` README 等)——与用户 2026-07-07 指令(知识库索引随包,不挂设计文档)直接冲突,本 spec 取代之。
  - **资产盘点**:6 个 SKILL.md(4 个文件源:domain-analysis/graph-design/agent-prompt-design/compile-error-repair;2 个 lib.rs 内联:moirai-intro/eval-judgement)+ 4 份人格常量(lib.rs)+ `copilot-rules.md` + `mounted/studio-config-map.md`。skills→agent 布线:master=moirai-intro,clotho=3 设计技能,lachesis=compile-error-repair,atropos=eval-judgement。
  - **MCP 工具现状**:`build_copilot_mcp_servers()` 仅 3 个(get_llm_roles / compile_skill / run_role_test),零审批;**无 predict**。
  - **装载机制**:SDK 隔离模式 `setting_sources=[]`(不吃宿主 CLAUDE.md);挂载 = `add_dirs` + 读护栏放行 + system prompt 一行路由(`copilot.py:615-693`);`context_resolved` 事件回显 `rules@<hash>`(反暗箱)。
- **Implications**: 本 spec 是 ah-orchestration-design 阶段 2 之后的下一步,继承其已验证机制(物化布局/受管头/人格方法论/三段式 rules),取代其 §9.8 知识接入方案,并把 §7"SDK 路=辅路单体人格"升级为"SDK 路=MoirAI 面板化身 + 原生 subagents"。

### T5 — 用户指令沉淀(PM 2026-07-07,两轮)

原话要点(本 spec 的需求源):

1. MoirAI 是**独立 agent**:理解需求、分析需求、做 research、做计划、完成任务;期间遇到**特定适合子 agent 的任务**才派遣——不是判断阶段后直接甩给子 agent。
2. 三女神职责重划:Clotho 关注 graph skill 整体功能/领域能力/节点编排/prompt 怎么写才能发挥好;Lachesis 关注工程规范/符合 engine 规范/能正常运行;Atropos 评估 graph 效果。
3. skills 放统一的地方,所有 agent 可能用到、互有交叉而非非此即彼。
4. copilot 规则应是"一份说明文档 + 具体文档的索引"做渐进式披露,链接详细文档,不要面面俱到却每处潦草。
5. 挂载不能挂开发仓 docs;要整理 copilot/moirai 到底需要哪些知识,做成**知识库索引**,不是直接挂设计文档。
6. copilot 必须理解 compile/predict/run 的作用:分析 skill 问题先 compile 拿全量报错,再 predict 无 LLM 空跑排掉 ~80% 逻辑/规范错误;只有 compile 无报错却跑不了时才人肉查文件。
7. 工具边界两路应一致:只读工具完全放开;写/Bash 圈定在 skill、subskill、studio 运行时路径,不伸进 studio 开发仓。前提:核查运行时文件是否放对位置(已核:仅挂载 docs 违例)。
8. 工具契约不写进 rules 散文(CLAUDE.md 从来不写这些)——强制在 harness 配置,文档只留判断性引导。
9. SDK 有原生 subagent → copilot 用与 moirai 同一份角色文档,唯一区别是派遣机制(Agent 工具 vs `ah ask`),不再单写一份 copilot 人格。

### T6 — 2026-07-09 复审定谳(spec 接手人;第一性原理 + 行业最佳实践复审后的实证补课)

- **Sources**: 真实 SDK spike(脚本:scratchpad `spike_subagent_base/spike.py`,claude-agent-sdk 0.1.80 + 捆绑 CLI,1 会话 2 turns,$0.16);vendored `types.py` 精读;ah v1.4.0 仓(commit 35d3016)`CHANGELOG.md`、`assets/builtin/`、`src/cli/config.rs`。
- **Findings**:
  1. **SDK subagent 只有薄基座(实测定谳)**。同一会话内主线程与 AgentDefinition subagent 各自报告自身 system prompt 结构:主线程 ≈3500 词,完整 claude_code 基座(tone/工具政策/file:line 引用规范/TodoWrite/安全政策/git 段)+ append 标记均在;subagent ≈300 词,仅身份句("You are Claude Code… running within the Claude Agent SDK.")+ 基础语气/工具规约 + knowledge cutoff,**无**完整基座各段、**不可见**主线程 append,AgentDefinition.prompt 直接拼在身份句后。类型佐证:`AgentDefinition.prompt` 为纯 `str`,无 preset 入口(types.py:86)。→ 「两路都自带基座」的原始前提修正为四运行位差异化(design.md 基座表);手册须薄基座自足(R3.9)。
  2. **can_use_tool 的触发契约**(types.py:1747-1756 原文):仅在权限规则判 "ask" 时触发,被 `allowed_tools`/`acceptEdits`/settings allow 规则绕过;SDK 明示"To observe or gate *every* tool call regardless of permission rules, use a `PreToolUse` hook"。→ 写白名单这类硬边界必须落在 PreToolUse hook,can_use_tool 只做审批 UX(D8)。
  3. **ah 1.4.0 改变了 CLI 侧命令事实的基座**:master 沙箱自动注入内置技能 ah-commands(自述 "Authoritative CLI reference",覆盖 ps/ask/tell/pend/watch/logs/events/cancel/kill/attach/ack-ready/prompt resolve)、ah-config、ah-runtime-state、ah-operate(#108/109);`ah status --json` 已存在(#115)——原 cli.md 计划中的「`ah status` 非可用命令」已被证伪,复述命令可用性必随 ah 升级漂移。→ cli.md 收缩为纯 Studio delta(女神 id 绑定+工作区事实),ah 基线钉 ≥1.4.0(R7.5/7.6)。`window_size="follow"` 变体在 1.4.0 仍有效(config.rs:633-647 测试)。
  4. **审批超时的业界对照**:Claude Code 权限弹窗与 Managed Agents `always_ask` 均为无限期挂起、零工作损失;「30 分钟停任务」若销毁会话则比业界更差。SDK 侧 `PermissionResultDeny(interrupt=True)`(types.py:247)可干净停当前任务而保留面板会话上下文。→ 超时=停任务+会话保留可续(R8.4 修订)。
  5. **杂项类型事实**:`allowed_tools`=声明式免审批放行(types.py:1592,读类放行的正解);`skills` 是上下文过滤非沙箱、设置后自动配 Skill 工具与 setting_sources(types.py:1805-1823);`SystemPromptPreset.exclude_dynamic_sections` 可剥动态段稳定缓存前缀(types.py:41-52,单用户桌面收益有限,列为实施评估项);SDK `sandbox` 选项存在(types.py:1825)但 Windows 无 OS 沙箱支撑,R8.3 判断在 Windows 成立——Studio 未来上 macOS/Linux 时 Bash 审批疲劳有官方沙箱可换,留作前瞻。
- **Implications**: 复审结论「架构方向全部成立,无需推翻」;修订集中在前提精化(基座差异化)、机制选型(hook vs 回调)、随 ah 1.4.0 对齐、超时语义保会话、R10 撤销卡与注入风险记账、指纹全覆盖、KB 路由归手册、拼装标记分档。

## Architecture Pattern Evaluation

### 知识/资产装载路线对比

| Option | 描述 | 优点 | 风险/局限 | 结论 |
|---|---|---|---|---|
| A. 继续挂开发仓 docs(现状 + §9.8) | `add_dirs`/rules 指向 `docs/engine/mvp1/` 等 | 零内容工作量 | 打包版整体消失;设计文档面向人而非 agent,噪声大;用户明确否决 | ❌ 弃 |
| B. `[sandbox] additional_ro_binds` 只读挂载(ah) | ah 层 ro-bind 知识目录 | 系统级只读保证 | WSL user scope 拒 `BindReadOnlyPaths` → agent 秒退(§9.8 实证);依赖 ah 修复 | ❌ 现阶段不可用 |
| C. **随包知识库 + 双路装载**(选定) | 单源 `app/prompts/knowledge/`;SDK 路 `add_dirs` 直指(dev=活后端目录,打包=vendor/backend 真实目录);ah 路物化拷贝进 `<ws>/.ah/knowledge/`(沿用 .ah/skills 已验证模式) | 打包版完整;绕开 WSL bind 问题;工作区自包含可入用户 skill 仓;单一真相源 | 需一次性内容提炼(最大工作量);ah 路有拷贝时点(受管头已解决覆盖冲突) | ✅ |

### 角色文档装载路线对比(tauri 侧)

| Option | 描述 | 优点 | 风险 | 结论 |
|---|---|---|---|---|
| A. 继续 lib.rs 内联常量 + `include_str!`(现状) | 编译期嵌入 | 无运行时 IO | 双源(4 人格纯内联)、改文案要动 Rust、与 backend 资产割裂 | ❌ |
| B. **运行时从 backend prompts 目录读取**(选定) | lib.rs 复用 sidecar 的 backend_dir 解析(dev=活仓 `apps/studio/backend`,打包=`vendor/backend`),启动物化时现读现写 | 单源;改文案=改 md 文件走 PR;eval-judgement/moirai-intro 落成真实文件 | dev 态 backend 目录缺文件时需 fail loud(不静默跳过) | ✅ |

## Design Decisions

### Decision 1: 四层资产架构(角色 / 操作手册 / 知识库 / 技能),单源随包

- **Context**: 需求 1/3/4/5/9 —— 角色同源、手册同源、知识随包、技能统一池。
- **Selected Approach**: `apps/studio/backend/app/prompts/` 收拢为 `roles/`(4 角色文档)+ `operating-manual.md`(同源工程纪律)+ `knowledge/`(KB-00 索引 + 主题文档)+ `skills/`(6 技能全部文件化)+ `contexts/`(面板/CLI 装载差异薄层)。SDK 与 ah 两条装载路都从这一棵树取材。
- **Rationale**: prompts 目录随 backend 一起 ship(dev 活目录 / 打包 vendor 快照均为真实磁盘目录),两条路天然可达;与 §9.4 已验证的物化+受管头机制兼容。
- **Trade-offs**: 打包版更新知识库需 vendor rebuild(既有规则,AGENTS.md 第 7 条已覆盖);换来单一真相源与打包完整性。

### Decision 2: MoirAI 主控行为 = 代理人闭环,派遣是手段不是流程

- **Context**: 需求 1;现行 `MOIRAI_MASTER_RULES` 操作协议第一条即"判断请求在哪一段→用 `ah ask` 派对应女神",PM 明确否决这种"分诊台"模式。
- **Alternatives**: ① 保留分诊+加例外(补丁);② 重写为独立 agent 协议:理解→research(读工作区/知识库)→计划→执行,**遇到匹配三女神专长的子任务才派遣**,派遣后汇总并对结果负责。
- **Selected**: ②。角色文档按 §9.5 三段式,操作协议段重写;三女神职责措辞按需求 2 重划(功能/领域/编排/prompt ↔ 工程规范/契约/可运行 ↔ 效果评估)。
- **Follow-up**: 人格文字须过 §6.4 四条方法论(正面陈述、无防御性否认、脚手架词不进台词、对齐叙事源)。

### Decision 3: 操作手册单文件同源,只装"判断",不装"机制"

- **Context**: 需求 4/6/8;现 `copilot-rules.md` 把工具契约散文化且与代码已 drift(Skill 工具未列),格式知识内联劣化版与挂载 spec 打架。
- **Selected Approach**: `operating-manual.md` 只收**跨两路皆真**的工程纪律:证据先行、先 Read 后改、根因修复不打补丁、**诊断优先级决策树(compile 全量 → predict 空跑 → 仅当 compile 干净仍跑不通才人肉逐文件)**、渐进披露纪律(重内容进知识库,正文只留索引)、golden/predict 数据纪律(predict 产物不可作 golden)。工具枚举/审批机制/出界行为一律不写——由 harness 代码强制。面板/CLI 特有约定(渲染、judge_context、派遣动词)下沉 `contexts/` 薄层。
- **Trade-offs**: 手册瘦 → 模型对机制的"预期"来自实际工具反馈而非散文;换来零 drift。

### Decision 4: 知识库 = KB-00 索引 + 13 篇主题文档,从设计源提炼而非链接

- **Context**: 需求 5/6;发现 1(打包消失)与 §9.8 冲突。
- **Selected Approach**: 见 design.md §知识库内容规划:KB-01..06(skill 解剖/io 数据流/LOGIC/SKILL/SUBGRAPH/iterate)、KB-07 compile 诊断体系、KB-08 predict、KB-09 run/trace/checkpoint、KB-10 golden、KB-11 workspace 运行时布局、KB-12 LLM roles 心智模型与排障、KB-13 Studio 工具与阶段门地图(吸收 `mounted/studio-config-map.md`)。每篇标注提炼来源(engine skill-spec / workflows / gateway docs),**面向 agent 重写**(契约表+决策树+反模式,不复制叙述性设计文)。
- **Rationale**: 设计文档是"为什么这样设计"(给人),知识库是"照此办事"(给 agent);两者受众与更新节奏不同,链接原文既漏(打包)又噪。
- **Follow-up**: 知识库与设计源的 reconcile 纪律写入手册方法论(设计变更 PR 同步更新对应 KB)。

### Decision 5: SDK copilot = MoirAI 面板化身,三女神走原生 AgentDefinition

- **Context**: 需求 9;SDK 能力已坐实(types.py:82-100, 1787)。
- **Selected Approach**: 主线程 system prompt = `roles/moirai.md` + `operating-manual.md` + KB-00 索引路由 + `contexts/panel.md`;`agents={clotho,lachesis,atropos}`,每个 `AgentDefinition.prompt` = 对应角色文档(+手册),`skills` 按角色映射(交叉允许),model 继承会话路由。`copilot-rules.md` 删除。
- **Trade-offs**: 面板首答人格从"Studio Copilot"变为 MoirAI(叙事一致,ah/面板同一代理人);SDK 路与 ah 路的行为对照(§7 的 A/B 台)反而更干净——同一份角色/知识/技能,只差派遣机制。

### Decision 6: 工具边界收敛为三档,代码强制,双路同一策略文件

- **Context**: 需求 7/8;发现 6(两极分化)。
- **Selected Approach**(SDK 路先落地,ah 路挂 P2):
  - **读(Read/Glob/Grep)**: 全放开,不审批(信息获取无副作用;知识库/工作区/任意路径均可读)。
  - **写(Write/Edit)**: 白名单 = skill 工作区(含 subskill,engine 契约保证子图不逃逸)∪ `%APPDATA%\AgentStudio`(runtime);白名单外直接拒绝(带原因),不进审批队列。
  - **Bash**: 保留挂起式审批(Windows 无 OS 沙箱,进程内无法可靠约束命令的实际触达路径;诚实设计:宁可审批也不做"解析命令猜路径"的假围栏)。
  - ah 路现状(skip-permissions 全放开)记为已知差距:等 ah hooks/沙箱能力(§8-3)再收敛,不在本 spec 造次优 workaround。
- **Rationale**: 用户"只读完全放开"与"写圈定运行时"直接落地;Bash 的差别处理是因为可执行边界与文件边界不同质——写死圈定反而制造假安全感。
- **Follow-up**: 回显机制升级:`context_resolved` 的 `rules@hash` 扩为资产集指纹(roles+manual+KB 版本)。

### Decision 7: 新增 `predict_skill` MCP 工具,补齐诊断链

- **Context**: 需求 6;发现 2(predict 无工具)。
- **Selected Approach**: `copilot_tools.py` 增第 4 个零审批工具 `predict_skill`(入参 `skill_id`,走 studio 后端既有 predict 出口,返回 RunResult 摘要:success/phase 记录/path_diff/诊断)。run 不做 MCP 工具(真跑有成本且有 UI 观测面,保持用户主动触发)。
- **Trade-offs**: predict 可能耗时(仍远小于 run);工具返回做摘要截断,详情引导 Read `.workspace/runs/<id>/`。

### Decision 8: 写边界落 PreToolUse hook,can_use_tool 只做审批 UX(2026-07-09)

- **Context**: T6 发现 2——can_use_tool 仅在 "ask" 态触发,依赖「Write 恒处 ask 态」这一隐含不变量,未来 allowed_tools/acceptEdits 任何变动都会静默穿透白名单。
- **Selected**: 两层结构。硬边界(写白名单+llm/ 排除)= PreToolUse hook,每次调用必然触发,SDK 文档指名的正确机制;审批 UX(Bash 挂起、白名单内写的 diff 卡)留 can_use_tool;读类与零审批 MCP 用声明式 allowed_tools 直放。配 invariant 回归测试。

### Decision 9: 审批超时 = 停任务 + 会话保留可续(2026-07-09)

- **Context**: T6 发现 4——业界(Claude Code/Managed Agents)是无限期挂起零损失;30 分钟停任务若丢会话则更差。PM 裁定的核心是「超时不折算拒绝」,与保留会话不冲突。
- **Selected**: interrupt 当前任务(可用 PermissionResultDeny(interrupt=True)),会话上下文保留,前端明示「任务已停止(会话保留)」,用户回来直接续对话。不带病续跑 + 不弃前功兼得。

### Decision 10: 拼装标记分档(落盘全标记 / 内存仅头部清单)(2026-07-09)

- **Context**: BEGIN/END 逐段标记在 `.ah/` 落盘文件里是纯收益(定位/审计);在 SDK append 与 AgentDefinition prompt 里让 `roles/moirai.md` 等实现层路径反复进模型上下文,与 R2.9「零实现层词汇」精神相抵。
- **Selected**: 落盘产物全标记;内存产物仅头部来源清单一行;反暗箱由 assets 指纹承担(R1.4/R1.7)。

### Decision 11: KB-00 路由内置于手册,不做独立拼装项(2026-07-09)

- **Context**: 原设计 KB-00 路由行只进主线程 append;三女神 prompt=角色+手册,被派遣后要在任务包内自主 research 却没有知识库入口。
- **Selected**: 手册自带 KB-00 一行式路由(R3.8),凡含手册的拼装产物(主线程/三女神/.ah rules)天然带知识入口;拼装组合不再单列路由项。

### Decision 12: R10 写工具零审批维持,叠加变更卡一键撤销 + 注入风险显式记账(2026-07-09)

- **Context**: 零审批配置写工具 + 会话可读外部来料(skill 文件/导入材料)= 提示注入可静默改 LLM 角色配置;PM 已裁定零审批,密钥不经对话挡住最坏面。
- **Selected**: 维持零审批;变更摘要含 before/after,前端卡片一键撤销(经同一服务层写回,撤销亦出卡);风险作为已评估接受显式记入 R6。破坏性操作分级审批列为后续可选项,不在本期。
- **REVISED(2026-07-11)**: 本决策已被修订。为抵御外部来料的 Prompt 注入安全威胁、并响应用户的安全审查直觉,**放弃「零审批 + 事后 Undo」,改为写操作前接入既有挂起审批链**(`can_use_tool` 挂起 → 前端脱敏审批卡 → 批准后 CLI 才执行)。before/after 快照与一键撤销机制整体删除(前后端)。虽略增操作摩擦,但在单用户工作流下安全级别极大提升(动作已经用户显式批准,误触概率极低,不再需要事后可逆)。实测坐实:MCP 写工具移出免审批白名单后确实经 `can_use_tool` 触发(无 Bash 式沙箱自动放行),审批仅靠 `can_use_tool` 即成立。

## Risks & Mitigations

- **R1 知识库内容质量**(最大风险,纯人力):KB 提炼错误会被 agent 当真相执行 → 每篇 KB 标注来源锚点(路径+节),tasks 中安排"KB 对照设计源复核"独立步骤;与 audited-doc 哈希锁机制隔离(KB 是新文件,不在 `_audited-ready-hashes.json` 范围)。
- **R2 vendor 快照过期**:打包/dev 桌面 app 的 sidecar 从 vendor 读 prompts —— 改 prompts 后需 `build_vendor.py` + 预热 pyc + 重启(AGENTS.md 第 7 条既有流程);tasks 显式列入验收步骤。
- **R3 tauri 运行时读文件失败面**:backend prompts 目录缺文件时必须 fail loud(阻断 Open in CLI 并报清单),不得静默降级为旧常量(旧常量已删,无处降级——no-backward-compat 反而消除了这个风险面)。
- **R4 人格重写回退口吻**:R1/R2 轮的"念稿/防御性否认"病史 → 写作过 §6.4 方法论四条;验收含 §9.9 式人工对话检查。
- **R5 面板身份切换的用户感知**:copilot 面板改自称 MoirAI —— 与叙事源一致且为 PM 明确方向(需求 9),不做兼容旧人格的开关(pre-release 原则)。
- **R6 配置写工具的提示注入面(已消除,2026-07-11 修订)**:原风险为零审批 create/update_llm_role + 会话可读外部来料 → 注入指令可静默改角色配置。**Mitigation 升级**:所有配置写工具(角色/endpoint/route 增删改)已剥离零审批白名单、统一接入事前挂起审批(D12 REVISED);任何配置改变在发生前均以脱敏审批卡暴露于用户视觉内,用户可拒绝——**静默注入写入的威胁被彻底消除**,不再是「已评估接受」。明文密钥仍不经对话(R10.3/R10.5,SecretStr 脱敏 + 审批明细硬脱敏)。
- **R7 ah 基座事实漂移**:cli.md 的 delta 范围以 ah ≥1.4.0 的 master 内核+内置技能为基座(R7.5/7.6);ah 升级改变内置技能覆盖面时须重审 cli.md——教训:spec 起草次日 ah 1.4.0 就把「`ah status` 非可用」证伪了(T6 发现 3),复述基座事实必漂移。

## References

- `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md` — ah 编排真相源(§5 拓扑/§6.4 人格方法论/§8 缺口/§9 阶段 2);本 spec 取代其 §9.8 知识接入表。
- `docs/strategy/moirai-copilot-persona-narrative.md` — 角色叙事真相源(名字/神话职能/关系)。
- `docs/engine/mvp1/01-contract/02-skill-syntax/00-FORMAT-GROUND-TRUTH.md` — skill 语法地面真相(KB-01..06 提炼源)。
- `docs/studio/mvp1/01_workflows/*.md` + `02_capabilities/compile-lint/mvp1-alignment.md` — 用户旅程与诊断 SSOT(KB-07/08/09/10/13 提炼源)。
- `docs/graph-agent-gateway/mvp1/README.md` — LLM 概念模型(KB-12 提炼源)。
- `apps/studio/backend/app/services/copilot.py` / `copilot_tools.py` — SDK 装载与 MCP 工具现状。
- `apps/studio/tauri/src/lib.rs`(#476 后)— ah 物化与 ah.toml 生成现状。
- vendored `claude_agent_sdk/types.py:82-100, 1787` — AgentDefinition / agents 能力证据。
