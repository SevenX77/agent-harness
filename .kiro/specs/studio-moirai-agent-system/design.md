# Design Document — studio-moirai-agent-system

## Overview

**Purpose**: 让 MoirAI 成为 skill 作者的**代理人**——理解需求、research、规划、亲自执行、在 scope 完全契合时派遣三女神——并把"人格、纪律、知识、技能、工具边界"从双源散装重构为**单源四层、双路装载**的资产体系,叠加在两条路各自的 Claude Code 基座 system prompt 之上(基座 + delta)。

**Users**: skill 作者(面板 copilot / 「Open in CLI」);Studio 维护者(维护 `app/agents/` 资产与装载代码)。

**Impact**: `app/prompts/` 更名重组为 `apps/studio/backend/app/agents/`;`copilot.py` 改 preset+append 装载、注册 subagents、护栏两层化(PreToolUse hook 硬边界 + can_use_tool 审批 UX)、审批超时改停任务(会话保留)、**配置写工具移出免审批白名单经 can_use_tool 挂起事前审批**;`copilot_tools.py` 增 predict + 补齐与 Settings 鼠标能力对齐的 LLM 配置工具全集(词汇发现 get_llm_registry、角色/endpoint/route 增删改、探测),**写工具返回纯成功状态、删除 before/after 撤销卡**;`lib.rs` 常量全退役改运行时物化;删除 `copilot-rules.md`、开发仓 docs 挂载与前端 `role-change-card` 撤销组件;回写 ah-orchestration-design §9.8/§7。

### Goals

- 四层资产(roles/manual/knowledge/skills)单源随包、全英文,两路同内容;基座已覆盖的通用行为零复写。
- MoirAI = 代理人闭环 + scope 契合派遣;人格英文重打磨(入戏、零实现层词汇、零防御性否认)。
- 诊断优先级(compile→predict→人工)进手册且有完整工具支撑(predict_skill 新增,Lachesis 子 agent 可用)。
- LLM 角色配置进对话(经服务层的 MCP 写工具,底座一合规)。
- 工具边界代码强制;审批超时=停任务,不带病续跑。
- 打包版(vendor 快照)资产完整,与开发态一致。

### Non-Goals

- ah 侧强制沙箱/hooks;MCP 独立 stdio 化(阶段 3);antigravity/codex 跨 provider 验证;F8 面板流式;三女神 UI 化。
- Bash 命令前缀 allowlist(后续迭代,本期全审批)。
- 凭据/endpoint 新增与密钥录入进对话(维持 UI 通道)。
- engine/gateway 核心行为变更。

## 用户旅程 → 知识与能力映射(知识库立库依据)

| # | 旅程阶段 | 用户操作/功能 | 必须理解的原理与规范 | 支撑资产 |
|---|---|---|---|---|
| 1 | 意图与领域澄清 | 与 MoirAI 对话,喂领域材料 | 领域材料→实体/流程/规则/术语结构化;确定性 vs agent 的分工 | skill: domain-analysis(Clotho) |
| 2 | 结构设计 | 画布建节点/连线;定根 io 边界 | 三种 phase 模式取舍;根 io→phase 拆分→DAG→每 phase io;三名一致;无环无孤岛 | KB-01/02;skill: graph-design(Clotho) |
| 3 | 节点落盘与编辑 | Properties/Editor/Rust 唯一写者 | 合法字段;io schema 三硬规则;action 签名与纯度;SUBGRAPH inputs 宽松 outputs 严格;mention 可达 | KB-01/03/04/05/06 |
| 4 | agent prompt 设计 | 编辑 `<role>/<goal>/<step>/<protocol>/<example>` | 五段结构;输出字段结构化对齐 golden;一次一变量迭代 | skill: agent-prompt-design(Clotho;交叉 Atropos) |
| 5 | LLM 配置 | 选 llm_role;建/调/删角色;endpoint·route 增删改;节点 role test/endpoint test/route probe | roles→routes→endpoints 概念链;fallback 物化;6 态;排障表 | KB-12;MCP 读/探测: get_llm_roles·get_llm_registry·run_role_test·test_llm_endpoint(_models)·probe_llm_route;MCP 写(**需审批**): create/update/delete_llm_role·apply_model_profile_to_role·upsert/delete_llm_endpoint·update/delete_llm_route |
| 6 | 输入数据准备 | i/o 面板导入绑定 | runtime_config.json 唯一配置层;import_files 布局 | KB-11 |
| 7 | 编译诊断 | 实时 lint + Compile 抽屉 | 诊断 SSOT 单出口全量聚合;`[F-v3-*]` 码族;compile 能查/不能查 | KB-07;MCP: compile_skill;skill: compile-error-repair(Lachesis) |
| 8 | Predict 空跑 | Predict(compile-pass 解锁) | LLM-free;mock 四档;path diff;predict-pass 是 Run 硬门 | KB-08;MCP: **predict_skill(新)** |
| 9 | Run 与观察 | Run;节点灯;trace;dot 双态 | 事件流→trace.jsonl;黑板快照;checkpoint | KB-09 |
| 10 | 调试 | Resume/HitL/篡改 | checkpoint 命名空间;dirty-state;篡改仅测试 | KB-09 |
| 11 | 效果评估 | golden 三态;diff;播种 | golden 布局状态机;predict 产物禁作 golden;失效规则 | KB-10;skill: eval-judgement(Atropos) |
| 12 | 迭代收尾 | 按终判回流;自动 commit | 终判四分类及回流对象 | skill: eval-judgement |
| — | 全程 | 工具地图与阶段门 | compile→predict→run 门;MCP 六工具能力面;配置文件地图 | KB-13;KB-00 hub |

角色分工投影:1–4=Clotho;7(修复)=Lachesis;11–12=Atropos;全程主线=MoirAI(5/6/8/9/10 通常亲自做;派遣唯一判据是 **scope 契合**,不是阶段归属)。

## Architecture

### 基座 + delta(总原则,按运行位差异化)

四个运行位的基座**不相同**(2026-07-09 spike 实测定谳,research.md §T6):

| 运行位 | 基座 | 证据 |
|---|---|---|
| SDK 主线程(MoirAI 面板) | 完整 claude_code 基座(~3500 词:tone/工具政策/file:line 引用/任务管理/安全政策/git 段)+ append | spike 主线程自报;types.py:1604-1612 |
| SDK subagent(三女神面板) | **薄 harness 基座(~300 词)**:身份句 + 基础语气/工具规约 + cutoff;无完整基座各段,不可见主线程 append | spike probe 自报;types.py:86(prompt 为纯 str,无 preset 入口) |
| CLI master(MoirAI ah 路) | CLI 原生完整基座 + ah master 内核 + 内置技能(ah ≥1.4.0) | ah assets/builtin/master_kernel.md、#108/109 |
| CLI worker(三女神 ah 路) | CLI 原生完整基座 + ah worker 内核 | ah assets/builtin/worker_kernel.md |

推论:资产只做 delta、矛盾内容禁止(不变);delta 基线以完整基座为准;**手册必须薄基座自足**(R3.9)——证据引用/验证/审批被拒判断义务等关键纪律显式承载,恰是 R3.3-3.5 已显式写出的内容,不新增复写。现纯字符串"整体替换"用法(copilot.py:651)是缺陷,一并修复。

### 资产树(单一真相源,全英文)

```text
apps/studio/backend/app/agents/          # 由 app/prompts/ 更名(无命名冲突,已验证)
├── roles/{moirai,clotho,lachesis,atropos}.md
├── operating-manual.md
├── contexts/{panel.md, cli.md}          # 极薄表面机制层
├── knowledge/                            # KB-00 hub + KB-01..13,网状互链
├── skills/                               # 6 技能(eval-judgement、moirai-intro 迁入)
└── agent-skill-map.json
```

### 拼装契约(R1.4/1.5,新)

**源文件头**(每个 roles/manual/contexts 文件第一段,HTML 注释,英文):

```markdown
<!--
  studio-agents source file — roles/moirai.md
  Assembled into: SDK session append; SDK subagent prompts; .ah/rules/master.md
  Editing rules: English only · delta over the Claude Code base prompt (never
  restate or contradict it) · facts belong in knowledge/ (link, don't copy) ·
  no tool mechanics (enforced in code) · edit THIS file, never the assembled outputs.
-->
```

**拼装产物分两档**(R1.4):

落盘产物(`.ah/rules/*.md` 等)带完整逐段标记:

```markdown
<!-- assembled-by=studio sources=roles/moirai.md,operating-manual.md,contexts/cli.md -->
<!-- BEGIN assembled-section source=roles/moirai.md sha256=a1b2c3d4 -->
...
<!-- END assembled-section source=roles/moirai.md -->
<!-- BEGIN assembled-section source=operating-manual.md sha256=e5f6a7b8 -->
...
```

内存产物(SDK append 字符串、AgentDefinition prompt)只带头部来源清单一行(`<!-- assembled-by=studio sources=... -->`),不加逐段标记——实现层路径不反复进模型上下文,反暗箱由 assets 指纹承担。ah 路落盘产物外层再套既有 Studio 受管头(hash 防覆盖机制不变)。

### 装载流

```mermaid
sequenceDiagram
    participant U as 用户
    participant T as tauri lib.rs
    participant B as backend copilot.py
    participant S as app/agents/ 单源

    rect rgb(240,248,255)
    note over U,T: ah 路(StartFresh)
    U->>T: Open in Claude Code
    T->>S: 运行时读四层资产 + map
    alt 任一缺失
        T-->>U: 中止,列缺失路径(fail loud)
    else 齐全
        T->>T: 物化 .ah/{rules,skills,knowledge}(拼装标记+受管头)
        T->>T: 生成 ah.toml(skills 由 map 派生)
        T-->>U: 拉起 master(MoirAI)
    end
    end

    rect rgb(245,255,245)
    note over U,B: SDK 面板路(新会话)
    U->>B: 首条消息
    B->>S: load moirai+manual+panel(KB 路由随手册;头部来源清单)
    B->>B: build_options(system_prompt=preset claude_code+append,
    note right of B: agents=3×AgentDefinition(带各自工具),add_dirs=[knowledge/],skills=map
    B-->>U: context_resolved(assets@<指纹>)
    end
```

### 诊断流(手册决策树)

症状 → `compile_skill`(全量聚合)→ 有 `[F-v3-*]` 按码+remediation 修根因回 compile;干净 → `predict_skill`(无 LLM 空跑)→ 报 state-mapping/iterate/path-diff 错则修;仍干净而症状在 → 人工 Read 对照 KB 契约 → 需真实证据时由用户触发 Run 后读 `.workspace/runs/`。

## Requirements Traceability

| Req | Summary | Components |
|---|---|---|
| 1.1–1.8 | 更名/四层/拼装契约/源头注释/英文/指纹/fail-loud/删旧 | PromptAssets, AssemblyContract, CopilotAssembler, TauriMaterializer |
| 2.1–2.10 | 代理人协议/任务包/无分诊/零 few-shot+验收场景/职责重划/三段式/英文重打磨/派遣动词薄层 | 角色文档, contexts |
| 3.1–3.9 | 手册同源/诊断树/纪律/沟通规则/拒后判断义务/不写机制/KB 入口内置/薄基座自足 | operating-manual |
| 4.1–4.7 | KB hub+网状/提炼来源/挂载与物化/退役 docs/打包一致/reconcile | knowledge/, CopilotAssembler, TauriMaterializer |
| 5.1–5.5 | 技能=方法论引用 KB/统一映射/intro 表面中立 | skills/, agent-skill-map |
| 6.1–6.6 | preset+append/AgentDefinition 带工具/派遣验收/panel 薄层/probe 裸配置 | CopilotAssembler |
| 7.1–7.6 | .ah 物化对齐/受管语义/ah.toml 派生/去 docs 路径/cli 薄层(仅 delta)/ah≥1.4.0 基线 | TauriMaterializer |
| 8.1–8.8 | 读放开(声明式 allowed_tools)/写白名单经 PreToolUse hook(排除配置真相)/Bash 审批/超时停任务(会话保留)/拒绝回传/协议侧验证/不写机制/ah 差距 | ToolGuardrails |
| 9.1–9.4 | predict 工具/摘要截断/子 agent 可用/run 不做 | PredictTool |
| 10.1–10.5 | 配置写工具经服务层/事前审批(删 Undo)/endpoint·route 写补齐+脱敏/KB 说明/明文密钥不进上下文 | LlmConfigTools · ToolGuardrails |
| 11.1–11.4 | 读写对称/get_llm_registry 词汇发现/探测复用/审批统一 | LlmConfigTools · ToolGuardrails |

## Components and Interfaces

### 资产层

#### PromptAssets(内容本体)

- **roles/moirai.md 操作协议**(英文撰写;此处为中文释义):
  1. Understand:复述目标与验收口径,缺料就问。
  2. Research:read 工作区现状(GRAPH.md/phases/.workspace)与 KB-00 路由到的知识。
  3. Plan:拆成可验证步骤;逐项判定「亲自做 or 派遣」——**唯一派遣判据 = 子任务 scope 与某位女神专长完全契合;不契合就再拆或亲自做**。
  4. Execute:亲自完成不契合派遣的部分。
  5. Dispatch:派遣单位=自包含任务包(goal/inputs/boundaries/expected deliverable);女神在包内自主 research+plan;回收后汇总,对最终交付负责。
  6. Close:按诊断树验证,给结论/取舍/下一步。
  - **无 few-shot 示例**(R2.4:零示例测协议鲁棒性;refine 阶段凭偏差证据决定)。
- **三女神职责句**(R2.5–2.7):Clotho=整体功能/领域能力/节点编排/agent prompt 设计;Lachesis=工程规范/engine 契约/编译通过/可运行;Atropos=真实运行证据评估/终判/回流。保留既有优质协议条目(先拿全量错误、一次修一类根因、评估基于真实运行)。
- **人格英文重打磨**(R2.9):遵循 §6.4 方法论(第一人称自我认知、只正面陈述、脚手架词——ah/copilot/master/worker——只出现在元指令不进台词、对齐 `docs/strategy/moirai-copilot-persona-narrative.md`);验收=PM 通读认可。
- **operating-manual.md**:诊断优先级决策树;证据先行/根因修复/渐进披露/predict 产物禁作 golden;沟通规则(回复语言跟随用户最后一条消息、结论先行、写操作讲 why 不复述 diff);**审批被拒后的判断义务**(评估条件是否仍充分→换路或停下说明,不降质续跑);delta 纪律声明(基座已有的不写)。
- **contexts/panel.md**(极薄):judge_context XML 契约;写入产生 diff 卡片的机制说明;编队状态语义=三女神为常驻子 agent 经 Agent 工具随叫随到。
- **contexts/cli.md**(极薄,R7.5/7.6):仅 Studio 专属 delta——女神↔agent id 绑定(clotho/lachesis/atropos,经 `ah ask <id> --wait` 派遣)与工作区事实;**不复述 ah 命令语法、不做可用性断言**(ah ≥1.4.0 的 master 内核 + 内置技能 ah-commands/ah-config/ah-runtime-state/ah-operate 是命令事实基座;原「`ah status` 非可用」条目作废——1.4.0 已有 `ah status --json`)。

#### knowledge/(13 篇 + hub,网状)

内容规划同下表;**网状约定**(R4.2):每篇 frontmatter 含 `related: [KB-xx-…]`;正文概念首现处内联 `[[KB-xx-slug]]`;KB-00 声明解析规则(同目录文件名 stem,用 Read/Glob 跳转)并给场景路由 + 链接图。

| KB | 主题(英文成文) | 核心内容 | 提炼来源 |
|---|---|---|---|
| 00 | index hub | 场景→KB 路由;链接解析规则;链接图 | 本表 |
| 01 | skill anatomy | 目录布局;GRAPH.md 字段表;三名一致;DAG body;模式=文件名;禁写字段 | engine skill-spec §1/§2 |
| 02 | io & dataflow | Draft2020-12 三硬规则;黑板 slice/merge;sequential_overwrite | skill-spec §6/§10 |
| 03 | LOGIC & actions | 签名/纯度禁项/多 action 串联/validator | skill-spec §3 |
| 04 | agent nodes | body 标签;mention 六族;tools/subagents/subgraphs;use_graph_llm_role;max_iterations | skill-spec §5/§8 |
| 05 | SUBGRAPH | path 规则;inputs 宽松 outputs 严格;与 SKILL.subgraphs 区别 | skill-spec §4 |
| 06 | iterate | batch/loop 字段;accumulate 四件套;io 必含 item_var/accumulate.var | skill-spec §7 |
| 07 | compile diagnostics | 单出口全量聚合;码族+remediation;能查/不能查清单;修复纪律 | compile-lint F6 + error_registry + 03_compile |
| 08 | predict | LLM-free;mock 四档;path diff;predict-pass 门;409 纪律 | 04_run-and-verify + predict capability |
| 09 | run/trace/checkpoint | 事件流与 trace.jsonl 读法;dot 双态;命名空间;resume/HitL/篡改+dirty-state | 04/05 workflows + trace-observability |
| 10 | golden | 布局;三态机;字段级 diff;run 播种;失效规则 | golden-eval + 06_eval |
| 11 | workspace runtime | `.workspace/` 布局;runtime_config 唯一配置层;import_files 镜像 | skill-spec runtime 附录 + skill-workspace |
| 12 | LLM roles | 概念链;6 态;错误分类;排障表;role test;**配置写工具能力面(R10.4)** | gateway mvp1 README + registry 契约 |
| 13 | studio gates & tools | compile→predict→run 门;MCP 六工具选用;配置文件地图(吸收 studio-config-map);Rust 唯一写者边界 | 03/04 workflows + 本 spec |

写作纪律:每篇标 `> Distilled from: <路径#节>`;与设计源冲突以设计源为准并回修;禁止从代码抄现状当契约。

#### skills/(方法论层)

- 六技能英文重写:**只写怎么干**;格式/契约/错误码等事实一律 `[[KB-xx]]` 引用(R5.2)。
- **moirai-intro 表面中立化**(R5.4):自报协议(who I am / workspace facts / the three hands' duties & status / what I can do);"如何查编队状态"引用 surface context 提供的动词——cli=`ah ps`,panel=常驻子 agent 无需查询。CLI 路开场触发 prompt(`使用 moirai-intro 介绍你自己`)不变;面板路由用户问"你是谁/你能干什么"时同一技能作答。

#### agent-skill-map.json

```json
{
  "moirai":   ["moirai-intro"],
  "clotho":   ["domain-analysis", "graph-design", "agent-prompt-design"],
  "lachesis": ["compile-error-repair", "graph-design"],
  "atropos":  ["eval-judgement", "agent-prompt-design"]
}
```

单文件;backend 构建 AgentDefinition.skills、tauri 渲染 ah.toml 同源派生(R5.5)。无表面维度(intro 已中立)。

### Backend

#### CopilotAssembler(copilot.py)

- `build_options()`:`system_prompt={"type":"preset","preset":"claude_code","append":assemble(["roles/moirai.md","operating-manual.md","contexts/panel.md"])}`(R6.1;KB-00 路由随手册携带,R3.8,不再单列拼装项)。
- `agents={ "clotho": AgentDefinition(description=职责一句话, prompt=assemble([role,manual]), tools=["Read","Glob","Grep"], skills=map["clotho"]), "lachesis": …tools=["Read","Glob","Grep","mcp__studio__compile_skill","mcp__studio__predict_skill"]…, "atropos": …tools=["Read","Glob","Grep"]… }`;model 不设(继承会话路由)(R6.2/6.3)。注意 AgentDefinition prompt 运行于薄基座(见「基座+delta」表),手册自足性即为此兜底。
- `allowed_tools=["Read","Glob","Grep"] + 六个 mcp__studio__* 工具名`:读类与零审批 MCP 工具**声明式**直放(R8.1/R9.1/R10.2),不再依赖回调分支;`permission_mode` 维持 `"default"`,Write/Edit/Bash 走 "ask" 路径进审批 UX。
- 可选评估项:`exclude_dynamic_sections`(types.py:41-52,剥离动态段进首条用户消息以稳定缓存前缀)——单用户桌面收益有限,实施时实测决定,不作硬要求。
- probe 路(`can_use_tool is None`):无 skills/无 MCP/无 agents,维持裸配置(R6.6)。
- 新 `agent_assets.py`:四层装载 + 缓存 + 缺文件报错清单 + `assets_fingerprint`(roles+manual+contexts+knowledge);`context_resolved` 回显 `assets@<8hex>`(R1.7);删除 `load_copilot_rules/copilot_rules_hash`。
- `_mounted_doc_dirs()` → 仅 `[(“graph_skill knowledge base (start at KB-00)”, <agents>/knowledge)]`(R4.5)。

#### ToolGuardrails(copilot.py)——两层结构

- **硬边界层 = `PreToolUse` hook**(每次工具调用必然触发):写类白名单 `workspace_root ∪ DEFAULT_SKILLS_ROOT`,**显式排除** `llm/` 配置真相目录与 `app_settings.json`(即使日后白名单扩到 settings 目录也保持排除)——越界/命中排除项直接 deny 附原因(R8.2)。机制依据:SDK 契约明确 `can_use_tool` 仅在权限规则判 "ask" 时触发、被 `allowed_tools`/`acceptEdits` 静默绕过;门禁每一次调用的官方机制是 PreToolUse hook(types.py:1747-1756)。这消除了"Write 必须恒处 ask 态"的隐含不变量——即使未来有人误把 Write 放进 allowed_tools,硬边界不失效(配 invariant 回归测试)。
- **审批 UX 层 = `can_use_tool`**:读/探测类 MCP(`get_llm_roles`/`get_llm_registry`/`compile_skill`/`run_role_test`/`predict_skill`/`test_llm_endpoint`/`test_llm_endpoint_models`/`probe_llm_route`)已由 `allowed_tools`(`_DECLARATIVE_ALLOWED_TOOLS`)声明式放行,不到达回调;白名单内 Write/Edit 走 patch_proposed 事件 + Allow(diff 卡机制不变);Bash 挂起审批。
- **配置写工具挂起审批(R10.2 revised)**:`_DECLARATIVE_ALLOWED_TOOLS` **移除** `create_llm_role`/`update_llm_role`,且所有新增写工具(`delete_llm_role`/`apply_model_profile_to_role`/`upsert_llm_endpoint`/`delete_llm_endpoint`/`update_llm_route`/`delete_llm_route`)一律**不入白名单**;`can_use_tool` 对 `_MCP_CONFIG_WRITE_TOOLS` 里的工具调 `_hold_for_tool_approval` 挂起审批,`_build_config_tool_approval_detail` 格式化明细并硬脱敏 `api_key`。**实测坐实(2026-07-11,探测真 claude CLI):MCP 写工具移出白名单后确实经 `can_use_tool` 触发(不像 Bash 有沙箱自动放行),故 MCP 写审批仅靠 `can_use_tool` 即成立,不需要额外的 PreToolUse hook**(Bash 才需要 `_bash_requires_approval_hook` 压掉沙箱自动放行)。
- **超时策略改造**(R8.4/8.5):`_hold_for_tool_approval` 的 `wait_for` 时限改为可配置常量(默认 1800s);超时路径不再返回 Deny-and-continue,而是:向前端发「approval timed out → task stopped (session preserved)」事件 + interrupt 当前任务(可用 `PermissionResultDeny(interrupt=True)`,types.py:247),**会话上下文保留**——用户返回后直接续起对话;用户拒绝路径返回 Deny(拒绝理由传给 agent,后续行为由手册 R3.5 约束)。
- 实施验证项(R8.6):确认 CLI 控制协议对 pending can_use_tool 无内部超时;若有,调 SDK/CLI 参数解决,不回退计时器拒绝。

#### PredictTool(copilot_tools.py)

`predict_skill(skill_id)` → 后端既有 predict 出口;返回 `{success, run_id, phases[{phase_id,mocked_source,ok}], path_diff, diagnostics(截断+总数), detail_hint:".workspace/runs/<run_id>/"}`;异常结构化;零审批(R9)。

#### LlmConfigTools(copilot_tools.py,R10/R11)——Settings 鼠标能力全对齐

所有工具走 `routers/llm.py` 背后同一服务层函数(校验/canonicalize/级联/领域事件全复用),**绝不直接写 yaml/json**;写工具全部经 R10.2 审批,返回纯成功状态(`{status,role_name/endpoint_id/route_id,message}`),失败结构化返回;**before/after 快照与一键撤销机制整体删除**。

- **词汇发现(只读,零审批)**:`get_llm_registry()` → 复用 `routers/llm.get_llm_registry()`,返回完整 Redacted 注册表(endpoints/routes/model_profiles/roles + canonical_groups/model_groups),`SecretStr` 自动脱敏;MoirAI 写前据此核对合法词汇,消灭毒数据(R11.2)。
- **角色写(需审批)**:`create_llm_role(name, model_groups, intent?)` / `update_llm_role(role_name, ops)`(ops:模型组增删/排序、fallback 开关、意图参数,保留 `_model_groups_violation` 词汇一致性校验)/ `delete_llm_role(role_name)`(固定角色拒删)/ `apply_model_profile_to_role(role_name, model_profile_id)`。
- **Endpoint 写(需审批)**:`upsert_llm_endpoint(endpoint_id, display_name, protocol, base_url, api_key?)` → `put_registry_endpoints`;`delete_llm_endpoint(endpoint_id)` → `delete_registry_endpoint`(级联删路由+清角色引用)。`protocol` 取真 schema 的 `openai_compatible/anthropic_compatible/google_genai/ark_runtime`;`api_key` 审批明细硬脱敏。
- **Route 写(需审批)**:`update_llm_route(route_id, display_name, canonical_id, status)` → `put_route_metadata`;`delete_llm_route(route_id)` → `delete_registry_route`(被引用则后端拒绝)。
- **探测/测试(只读,零审批)**:`test_llm_endpoint(endpoint_id)` / `test_llm_endpoint_models(endpoint_id, model_ids)` / `probe_llm_route(route_id)` / `run_role_test(role_name)`——只探测不改词汇,排障凭结构化状态判断,绝不读明文密钥(R11.3)。
- **明文密钥物理隔离(R10.5)**:读取明文密钥的 `/registry/endpoints/{id}/secret` REST 接口**绝不投影**给 MCP 工具面。

### Tauri(lib.rs)

#### TauriMaterializer

- `studio_agents_dir()`:dev=`CARGO_MANIFEST_DIR/../backend/app/agents`;打包=`<resource_root>/vendor/backend/app/agents`(与 sidecar backend 判据一致);缺失 fail loud(R1.3)。
- `prepare_studio_ah_workspace()`:运行时读四层+map → 按拼装契约生成 `.ah/rules/*`(role+manual+cli,带 BEGIN/END 标记)→ 物化 `.ah/skills/*`、`.ah/knowledge/*` → 全部走既有 `write_studio_managed_file`(受管头+hash;用户改动拒覆盖报冲突)(R7.1/7.2)。
- 删除六个内容常量与 include_str!;静态清单表改运行时构建;ah.toml skills 由 map 派生,window_size/moirai-intro 等阶段 2 约束保持(R7.3);既有内容断言测试迁移为对物化产物断言。

### Docs

#### DesignDocReconcile

ah-orchestration-design:§9.8 资料表→随包知识库方案;§7 SDK 路定位→MoirAI 面板化身+原生 subagents;§8-2 标记完成。copilot region mvp1-alignment 核对;INDEX 登记;涉 audited 哈希锁文档同 PR 重钉。

## Data Models

- 受管文件头机制不变;新增拼装分段标记(见拼装契约,落盘/内存两档)。
- `assets_fingerprint = sha256(sorted("relpath:sha256(content)" for roles/,manual,contexts/,knowledge/,skills/,agent-skill-map.json))[:8]` → `assets@<8hex>`(全资产覆盖,R1.7)。
- `agent-skill-map.json` schema:`{ <role>: [<skill-name>...] }`。
- 契约变更:`context_resolved.summary` 的 `rules@`→`assets@`(前端透传);MCP 工具集 3→16(补 predict_skill、get_llm_registry、create/update/delete_llm_role、apply_model_profile_to_role、upsert/delete_llm_endpoint、update/delete_llm_route、test_llm_endpoint(_models)、probe_llm_route);写工具经审批、读/探测工具零审批。

## Error Handling

| 场景 | 处理 |
|---|---|
| 装载/物化缺资产 | SDK 拒建会话 / Open 中止;列缺失相对路径;不写半套 `.ah/` |
| 用户改过受管文件 | 既有语义:报冲突路径拒覆盖 |
| 写工具越界或命中配置真相排除项 | 直接 deny+原因(结构化回模型,可改道走 R10 工具) |
| 审批超时(默认 30min) | 停整个任务(interrupt)+ 前端明示「等待审批超时,任务已停止(会话保留)」;不折算为拒绝续跑;会话上下文保留,用户可续起 |
| 用户拒绝审批 | Deny+理由回 agent;手册判断义务接管(换路或停下说明) |
| 配置写工具被注入滥用 | 已消除:所有写工具事前审批,配置改变发生前必暴露于用户视觉内(脱敏卡),用户可拒绝(research.md 风险 R6) |
| predict / 配置工具异常 | 结构化 `{status/success:error}`,不抛栈 |
| 打包版资产缺失 | 与装载缺资产同一失败面(vendor rebuild 缺步的显性信号) |

## Testing Strategy

### Unit
1. agent_assets:四层装载、指纹稳定且覆盖全资产(含 skills+map)、缺文件清单;拼装标记格式(落盘=BEGIN/END+sources 头,内存=仅 sources 头)。
2. build_options:preset+append 形状;三 AgentDefinition(prompt 拼装、skills=map、lachesis 工具含 compile+predict);`allowed_tools` 恰为读类 + 读/探测 MCP 工具名(写工具不在内);probe 路裸配置。
3. 护栏:读/探测 MCP 经 allowed_tools 放行(不达回调);写白名单经 PreToolUse hook(工作区/subskill/Skills root 放行,llm/ 与 app_settings 排除,越界 deny 消息);**invariant 回归:人为把 Write 加入 allowed_tools 后,白名单外写仍被 hook 拒绝**;**MCP 配置写工具经 `can_use_tool` 挂起审批(held→approve=Allow、deny=Deny、批准前不落盘)、审批明细脱敏 api_key**;审批超时→interrupt+会话保留路径、拒绝→Deny 路径。
4. lib.rs:agents_dir 双分支;物化产物断言(标记/受管头/缺失中止/ah.toml=map 派生/阶段 2 约束保持);无 include_str! 残留。
5. 工具:predict_skill 摘要/截断/异常;create/update/delete_llm_role · endpoint/route 增删 · apply_profile 走服务层(mock 层断言复用 router 函数、未直写文件)、返回纯成功状态(无 before/after);`get_llm_registry` 输出脱敏(明文 key 不出现);词汇校验(`_model_groups_violation`)保留。

### Integration
1. SDK 冒烟:preset+append 生效、assets@ 回显、knowledge 可读、Agent 工具派遣可用。
2. tauri 端到端(tempdir):四层全量落盘、幂等、拒覆盖、两路技能内容一致。
3. 诊断链 fixture:compile 干净而 predict 报错的 skill,主线程与 lachesis 子 agent 各走通一次。
4. 角色配置链:update_llm_role 后 `GET /api/llm/registry` 反映变更且领域事件发出(前端缓存革新路径);撤销后 registry 回到 before 状态且再发领域事件。
5. 审批超时链:超时事件后同一会话续发消息可正常应答(会话未销毁)。

### 鲁棒性人工验收(零 few-shot,R2.4)
1. 「分析一下这个 skill」→ 期望:拆两包并行派 Clotho+Lachesis(Lachesis 先 compile→predict),无 run 产物不派 Atropos,汇总单份报告;偏差大→修协议文本,不加示例。
2. 人格通读(四角色,英文规则中文对话):入戏、零 ah/copilot/master/worker、零防御性否认;PM 认可为准。
3. 「帮我把 X 角色的首选模型换成 Y」→ 期望走 update_llm_role 并出变更卡,不碰文件。
4. 审批场景:Bash 挂起 30min 超时→任务停止且明示「会话保留」,续发一条消息确认可对话;人为拒绝→agent 评估后换路或停下说明。
5. CLI 路:Open in Claude Code 后 `.ah/knowledge` 可见,intro 自报用 `ah ps` 报编队;面板路问"你是谁"同一技能作答且不提 ah。
6. vendor rebuild 后打包形态两路资产一致。

## Migration(删除清单,no-backward-compat)

- `git mv app/prompts app/agents` + `_PROMPTS_DIR`→`_AGENTS_DIR` 全量替换;`copilot-rules.md`、`mounted/` 删除(内容归位 KB-13);`load_copilot_rules/copilot_rules_hash` 删除。
- lib.rs 六常量 + include_str! + 静态物化表删除;`_TOOL_APPROVAL_TIMEOUT_S=120` 删除(改可配长时限+停任务语义)。
- 旧 `.ah/*` 无迁移:受管头 hash 匹配旧生成值的按既有逻辑覆盖,用户改过的报冲突。

## Supporting References

- requirements.md v4(本 spec);research.md(四路调研+决策+§T6 复审定谳)。
- vendored `claude_agent_sdk/types.py`:`1604-1612`(preset+append)、`:82-100/1787`(AgentDefinition/agents)、`:86`(AgentDefinition.prompt 纯 str)、`:1592`(allowed_tools 语义)、`:1747-1756`(can_use_tool 触发契约与 PreToolUse 指引)、`:247`(PermissionResultDeny.interrupt)、`:41-52`(exclude_dynamic_sections)、`:1805-1823`(skills=上下文过滤非沙箱)。
- 2026-07-09 subagent 基座 spike:脚本与输出见 research.md §T6(主线程 ~3500 词完整基座 vs subagent ~300 词薄基座,实测定谳)。
- ah ≥1.4.0:CHANGELOG #108/109(master 内置技能)、#115(`ah status --json`/`ah ps --all`)、#117(bare-start guard);`assets/builtin/{master_kernel.md,worker_kernel.md,skills/}`;`config.rs` window_size="follow" 测试(:633-647)。
- ah-orchestration-design §5/§6.4/§9.3–9.5/§9.8/§9.9;`moirai-copilot-persona-narrative.md`;engine skill-spec;compile-lint F6;gateway mvp1 README。
