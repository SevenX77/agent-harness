# 决议 2026-08-15:派工操作规则按运行位分写,SDK 面板那份补齐

状态:已批准(用户 2026-08-15 原话「Moirai的规则得是拼合成的,sdk和cli是两种机制,
需要两种操作规则」;本文档为方案落盘)。这不是新架构——拼合机制早已存在且形状正确,
本决议补的是**内容对等**:CLI 那一层写全了派工怎么做,面板那一层没写。

## 背景与证据

### 1. 拼合机制已存在,两条运行位各叠一层 context delta

同一套内核 + 每条运行位一份机制 delta,是既有设计,不需要改动:

- **SDK 面板路**:`apps/studio/backend/app/services/copilot.py:870`
  ```python
  ["roles/moirai.md", "operating-manual.md", "contexts/panel.md"]
  ```
- **CLI(ah)路**:`apps/studio/tauri/src/lib.rs:1649` 把 `"contexts/cli.md"`
  拼进同一条装配链(装配标记见 `lib.rs:7845` 的测试断言
  `BEGIN assembled-section source=contexts/cli.md`)。

`apps/studio/backend/app/agents/README.md:47`/`:66` 记录的两条装配清单也印证:
CLI = `roles/moirai.md,operating-manual.md,contexts/cli.md`,
面板 = `roles/moirai.md,operating-manual.md,contexts/panel.md`。

### 2. 两侧的派工小节内容严重不对等

`contexts/cli.md:26-31`(原文):

```
## Subagent Dispatch and ID Bindings
- **Fate Agent ID Bindings**: The three specialized subagents (Clotho, Lachesis,
  Atropos) are dispatched from the CLI using the standard `ah ask` command.
- **Dispatch Command**: Use `ah ask <id> --wait` to delegate a subtask, where the
  `<id>` maps to the target Fate's agent identifier:
  - `clotho`: Domain Analysis, Graph Design, and Agent Prompt Design.
  - `lachesis`: Compile Error Repair and Graph Design.
  - `atropos`: Evaluation Judgement and Agent Prompt Design.
```

`contexts/panel.md:20-21`(全部,原文):

```
## Subagent Fleet Operations
- **Resident Subagent Availability**: The three specialized subagents (Clotho,
  Lachesis, Atropos) function as persistent, background-registered entities
  accessible at all times through native subagent dispatching tools. No status
  queries or initialization commands are needed to interact with them.
```

CLI 那份回答了「派谁、什么活派给谁、怎么派」;面板那份只回答了「她们在」。
**「accessible through native subagent dispatching tools」是一句可用性声明,
不是一条操作规则**——它不告诉模型任何可执行的路由判断。

### 3. 行为实测(2026-08-15,四次会话,全部 `entrypoint: "sdk-py"` 即面板路)

证据存放:`C:\Users\test\.claude\projects\D--coding-skills-segment-prompt-t2\`
下的会话转录(权威账本,非界面观察)。

| 测试 | 问法 | 派工结果 |
|---|---|---|
| 1 审查题 | 「这份 prompt 合不合模版纪律」 | 零派工,自己答 |
| 2 改写题 | 「按模版纪律改写这个文件」 | 零派工,自己改(23 次 tool_use 全在主线,无 `subagents/` 目录) |
| A 命令派工 | 「请派给 Clotho,不要自己做」 | **形成了正确意图**,先派 `Explore` 做前置检索,turn 在此中断,Clotho 那一步未发生 |
| B 纯专长题 | 一道正中 clotho 专长的纯设计题,不给提示 | **零工具调用**,连知识库都没查,直接凭脑子交卷 |

测试 A 的推理链原文(转录 rec3/rec4/rec18):
「The user wants me to dispatch a task to Clotho ... Let me first understand the
current state ... then dispatch to Clotho」/「我来先了解一下当前 skill 和
`phases/segment` 的现状,再完整地派给 Clotho」/「Now let me check the knowledge
base for the cognitive prompt template discipline that Clotho needs to follow」。

**结论边界(重要)**:测试 A 证明「被明确指名时,面板路上的 MoirAI 能形成正确的派工
意图」——它不是路由错误。真正没有出现的是**自发派工**(测试 1/2/B 三次零派工)。

### 4. 派工机制本身没有被任何东西挡住

随包 CLI 二进制里 `Agent` 工具自带一个无条件 `allow` 的 `checkPermissions`;
把「没人管的工具」兜底成 `ask` 的分支条件是 `behavior === "passthrough"`,
Agent 有自己的结论所以走不到兜底,Studio 的 `can_use_tool` 回调不会被调用。
行为侧印证:测试 A 真派了一次工,全程 **0 个** `tool_approval_required`。
**派工是静默直放,没有任何机制拦着。**

### 5. 测试 A 的中断已排除,不是产品缺陷

首轮测试 A 的 turn 在子 agent 返回后中断,当时列为未决。**已定位:是测试脚手架
造成的**——A、B 两个会话被背靠背发到同一个 sidecar 上并发。单独重跑同一道题,
转录从 20 条变成 48 条,完整跑完并交付。

(并发本身是否真有干扰是另一个命题:#802 保证的是每标签独立会话,这次是两个
WebSocket 客户端打同一 sidecar 的两个 session_id。要判定需单独设计对照,
本次不作证据。)

单跑测试 A 的权威转录:`subagent_type = "clotho"`、
`description = "Design segment agent prompt skeleton"`、审批事件 0。
**面板路上派工能完整走通,包括正确的 subagent_type。**

### 6. 第一版规则的实测:识别修好了,行动没修好

按 D-2 补完三条规则后重跑测试 B(纯专长设计题、不给提示、单跑),
结果仍是 8 条记录、零工具、零派工——**验收判据 2 未过**。

但它的思考(转录 rec4 原文)证明规则并非无效:

> This is a design task - **I should use the Agent tool with atropos or clotho**
> since this involves domain analysis and agent prompt design. ...
> **Agent prompt design is Clotho's domain. But wait** - the user explicitly said
> "不要写代码、不要改任何文件、不要跑编译". ... **They just want a design
> discussion/output.**

对照首轮(同一道题、无这些规则):它**从未提及**派工或任何一位女神。所以
「哪位女神管这件事」这一层是新规则带来的,识别成立;卡点转移到了下一层——
**它把「派工」和「写文件/跑编译」归为同一类"动作",用户说不要动作,它把派工
一并压掉了。**

第一版第三条规则(当时标题 "Fates Are Read-Only")写成了限制式表述
(「她们不能写文件」),不但没拆开这个误解,反而把派工与写文件绑得更紧。
第二版改为正向表述:**派工是一次只读咨询,不是对工作区的动作**;
"用户只要设计、不要改动" 是**该派**的理由,不是自己答的理由。

## 决策

### D-1 派工操作规则按运行位分写,各用各的机制语言

`roles/moirai.md`(何时派)与 `operating-manual.md`(通用纪律)保持运行位无关,
不写任何机制细节。**「怎么派」一律下沉到 context delta**,每条运行位一份,
用该运行位真实存在的机制表述:

- `contexts/cli.md` 保持现状(`ah ask <id> --wait` + id 对照表),它已经正确。
- `contexts/panel.md` 补一节等价的派工操作规则,用 SDK 原生 subagent 的语言。

判据:把任一份 context delta 单独拿给一个没有其它上下文的模型,它应当能据此
完成一次正确派工。现在 `cli.md` 过关,`panel.md` 不过关。

### D-2 面板那份写「路由策略」,不写「名册」

名册(有哪几位、各自一句话描述)由 SDK 在会话开场以 `agent_listing_delta`
附件形式送达,面板路实测可见:
`addedTypes: ["atropos","clotho","Explore","general-purpose","lachesis","Plan","statusline-setup"]`,
且描述来自 `copilot.py:877-891` 的 `_GODDESS_DESCRIPTIONS`(clotho 那条明确写着
"agent prompt design")。**基座已经给的不重写**(spec 的基座+delta 纪律)。

面板 delta 要补的是名册**没有**给的那部分:

1. **技能归属**:哪几项 skill 归哪位女神。权威源是
   `apps/studio/backend/app/agents/agent-skill-map.json`,模型从未见过这张表——
   名册里的一句话描述不等价于它。
2. **优先级**:同一份清单里还并列着通用 agent(`Explore` / `general-purpose` /
   `Plan`)。要写明:**领域判断类子任务的路由目标是三位女神;通用 agent 只用于
   机械检索与文件定位这类不含领域判断的前置活。** 测试 A 里 MoirAI 自发用
   `Explore` 做前置检索、准备派给 Clotho——那个编排是对的,规则应当确认它,
   而不是禁止它。
3. **派工的代价定性**(第二版新增,依据 §6 实测):明确写出**派工是只读咨询,
   不是对工作区的动作**。三位女神全部只读(clotho/atropos 只有 Read/Glob/Grep,
   lachesis 多两个只读 MCP),派一次工不改动用户的任何东西。因此「用户说不要写
   文件、不要跑编译」**不排除**咨询女神——恰恰因为只要设计,才更该派。
   这条不是可有可无的补充:实测里模型正是在这一步把派工误归为"动作"而压掉的。

### D-3 不动 `roles/moirai.md` 的派工判据

`roles/moirai.md:19` 那条「sole criterion ... perfectly aligns ... otherwise I
perform it myself」目前**没有证据**表明它是自发派工缺失的原因——测试 A 证明指名
时意图能正确形成,而测试 B 的零派工同样可以由「没有技能归属表、无从判断是否
perfectly aligns」解释。**先补 D-2 的规则,再用同一组测试复测;复测仍不派工,
才谈改判据。** 无证据就改行为判据,是拿猜测当根因。

## 不做什么

- **不改 agent 注册**:不尝试从清单里摘掉通用 agent。测试 A 表明用 `Explore`
  做前置检索是正确编排,摘掉它反而会逼 MoirAI 自己干检索活。
- **不把 `agent-skill-map.json` 的内容复制进 `panel.md`**:delta 里写归属关系的
  自然语言表述,权威源仍是那份 json;两处都要改的字段不引入。
- **不碰 `contexts/cli.md`**:它已经过 D-1 的判据。
- **不在本决议里修 turn 中断**:那是独立缺陷,单独立项。

### 7. 技能挂载漂移:已修,但它不是派工缺失的原因(实测否定)

审计两条运行位的技能挂载时发现第二处、也是更靠底的分叉:

| | 怎么挂 | 结果 |
|---|---|---|
| CLI(ah) | `lib.rs:2154` `skills_for_agent(&map, "moirai")` | 只有 `moirai-intro`,合规 |
| SDK 面板 | `copilot.py:792` `agent_assets.skill_names()` | **全池 7 个**,含 `agent-prompt-design` |

规格 `requirements.md:89` 原文:「默认映射:**moirai=moirai-intro**;clotho=
domain-analysis+graph-design+agent-prompt-design;……」。`agent-skill-map.json`
里的 `"moirai": ["moirai-intro"]` 那一行在面板路上**从未被使用**——`skill_map`
只在 `copilot.py:919` 给三位女神用。按 AGENTS.md「MVP1 design = source of truth,
代码和设计打架时改代码」,SDK 侧是漂移,已改(先写 RED 测试
`test_chat_skills_are_moirai_s_row_of_the_skill_map` 再改生产代码)。

**当时的假设是:她身上挂着 Clotho 的看家技能,所以按 `moirai.md:19` 的判据
「不完美契合就自己干」,每次都该自己干。这个假设被对照实验否定了。**

同一探针、同一模型、同一份规则,各连跑 5 次(串行):

| 组 | 女神派工 |
|---|---|
| 基线(全池技能) | 1/5 |
| 技能收窄后(只挂 moirai-intro) | 1/5 |

**未能测出差别。** 注意表述边界:n=5 对 n=5,真实差异若是 20% vs 40% 也大概率
测不出,所以这是「未测出差别」,不是「证明无差别」。

技能收窄这一改动**独立成立**(修的是对规格的漂移),但**不得**再被当作
派工缺失的解法。另需记录一条限度:SDK 的 `skills` 参数文档
(`claude_agent_sdk/types.py:1819-1822`)写明它是 **context filter, not a sandbox**
——未列出的技能只是从清单里隐藏、Skill 工具会拒绝,**文件仍在盘上、可被
Read/Bash 读到**。物化必须保持全量(女神在同一 workspace 里跑),所以这条路
封不掉,也不该封。

### 8. 结论:非结构性手段已穷尽,剩下的杠杆是分配判据本身

到此两条非结构性手段都测过、都未测出效果:prompt 文本规则(两版)、
技能挂载配置。基线派工率两侧同为 ~20%。

`roles/moirai.md:19` 原文:

> The **sole criterion** for allocating a task is whether the scope of the
> subtask **perfectly aligns** with that sister's unique specialty. If it does
> not perfectly align, I either divide the task further or **perform it myself**.

这条在语义上偏向自己干:门槛设成 "perfectly",且把不满足时的默认出口写成
"perform it myself"。要让派工成为常态,要改的是它——**改变代理人行为模型,
属结构性变更,须先呈方案、用户确认后才动手**(仓规实施节奏)。本决议不含此项。

## 验收判据

1. **静态**:`contexts/panel.md` 补入的小节,单独拿给一个零上下文模型,它能说出
   一道「设计 agent 节点 prompt」的任务该派给哪位女神、以及派工包放什么。
2. **行为——已测,未达成,本决议不再声称达成。** 原判据是「重跑测试 B 应出现
   `subagent_type` 为 `clotho` 的派工」。实测 1/5,与基线 1/5 无可测差别(§7)。
   本决议交付的是**规则对等与规格对齐**,不交付派工率提升;后者的杠杆在
   `moirai.md` 的分配判据上,须另立结构性方案(§8)。

   测量方法本身固化下来,供后续复用:同一探针**连续**跑 N 次数派工率
   (脚本 `dispatch-rate.sh`),**串行不并发**(并发会截断 turn,已实证);
   证据取会话转录,不取界面观察;判「有没有派工」看 `tool_use` 的工具名,
   **不看 `isSidechain`**(实测:真派工那轮父转录里 `isSidechain` 仍全为 false)。
   **n=1 不足以判断任何 prompt 改动的效果**——本次就是拿单次运行连续误判了三次
   (v1「起作用了」/ v2「改坏了」/「出现 Agent 调用即进展」,后者实为派给
   `Explore` 的前置检索),三条均已收回。
3. **回归**:`apps/studio/backend/tests/services/test_agent_assets.py` 与
   `apps/studio/tauri` 的装配断言全绿(两条装配链共用这些资产)。

---

## 第二轮:用户裁决落地与对等审计(2026-08-15 下午)

### 9. 用户裁决:两条运行位是两种机制,要两套操作规则

用户原话:「Moirai的规则得是拼合成的,sdk和cli是两种机制,需要两种操作规则」。

D-1 已经按这条写过一轮,但只补了面板侧。这一轮反过来查 CLI 侧缺什么,查到一条
**同一句话在两条路上真值相反**的规则——正好是这条裁决的最硬证据:

D-2 第 3 点写进 `panel.md` 的「派工是只读咨询,不是对工作区的动作」,在面板侧成立,
在 CLI 侧**是假的**:

- 面板侧女神工具面由代码钉死只读:`copilot.py` `_GODDESS_TOOLS`——
  clotho/atropos 只有 `Read`/`Glob`/`Grep`,lachesis 多两个只读 MCP。
- CLI 侧 Studio 生成的 ah.toml 里 `[agents.clotho]`/`[agents.lachesis]`/
  `[agents.atropos]` 只有 provider / skills / 可选 env 三个键
  (`apps/studio/tauri/src/lib.rs` 的 `transient_ah_config_content` 格式串),
  **没有 cmd 覆盖**;ah 的 `AgentConfig` 本身也无 `cmd` 字段。于是女神吃 provider
  默认启动命令,而 ah 的 claude provider manifest 是
  `command: &["claude", "--dangerously-skip-permissions"]`。她可写、可执行、零审批。
- 对照:master 反而**显式丢掉** skip-permissions,并有单测锁死(`lib.rs` 中
  `assert!(!config.contains("--dangerously-skip-permissions"))`,PR #536 注明理由是
  「用户就坐在这个会话前面,claude 自己的审批提示就是人闸」)。

所以 CLI 侧的对应规则不是同一句话的翻译,而是**相反的一句**:派工在那里是对工作区的
动作,包里必须自带边界。已写入 `contexts/cli.md` 的
`A Dispatched Fate Acts on This Workspace`。

注意 `cli.md` 被无差别拼进四份 `.ah/rules/*.md`(master + 三 worker),所以这条按
「本工作区的派工语义」陈述,worker 读到也成立,不写成只对 master 说的话。

### 10. 规格自相矛盾的判读:R5.4 与 R7.5

审计报了一条「漂移-规格明确」:`contexts/cli.md` 没有提供编队状态查询动词
`ah ps`,违反 R5.4(`requirements.md`「编队状态查询动词由 contexts 提供
(cli=`ah ps`;…)」)。对抗核验推翻了这个判定,理由是 R7.5 —— 规格里**唯一一条
专门裁定 `cli.md` 该装什么**的条款——写着「仅承载…女神 agent id 绑定…与工作区
事实;shall **不复述 ah 命令语法、不做命令可用性断言**」,并给了理由:ah 自己注入的
内置技能才是 CLI 侧命令事实的权威基座,复述可用性必然随 ah 升级漂移。两条同属一次
提交,不存在新旧关系。

**裁决(用户 2026-08-15:「这是人类语义表述错误,应该是怎么样是合理的,你应该能
判断出来」——按合理意图自行判断,不上升)**:

R5.4 的规范意图是**「moirai-intro 必须表面中立」**;括号里那对例子是在解释「动词
由表面层提供」在两路各长什么样,不是「`cli.md` 必须逐字写 `ah ps`」的落地条款。
R7.5 是针对 `cli.md` 的封闭清单且自带理由,冲突时以它为准。合理终态:

1. `moirai-intro` 去掉两路动词硬编码 —— 这半边是**真漂移**,`design.md` 明写
   「无表面维度(intro 已中立)」,而技能正文里却列着「*CLI Mode*: Run `ah ps`」
   与「*Panel Mode*: …resident…」。已改为中立表述。
2. `cli.md` **不补** `ah ps`。CLI 侧编队状态由 ah 自身注入的内置技能承载。
3. `requirements.md` R5.4 的措辞已订正,不再举一个 R7.5 禁止的例子。设计源内部
   打架就地消除,而不是留着让下一个人再撞一次。

门禁化:`test_moirai_intro_skill_carries_no_runtime_surface_verb`(共享技能里不得
出现任何 `ah` 命令或 `CLI Mode`/`Panel Mode` 分支)与
`test_cli_context_names_only_the_one_command_the_spec_allows`(`cli.md` 里出现的
`ah` 命令集合必须恰好是 `{ask}`)。后者是**预防性门禁**:改动前的 `cli.md` 本来
就合规,这条锁的是审计当时建议的那个方向——把 `ah ps` 写进去。

### 11. 实测发现的真缺陷:被派出去的女神读错知识库

R3.8 要求「被派遣的女神在任务包内自主 research,**不得因拼装组合差异而丢失知识库
入口**」。审计判面板侧丢失入口,对抗核验以 R4.4「SDK 路经 `add_dirs` 挂载 /
ah 路经 `cli.md` 声明路径」反驳为「应有差异」,但双方都没核验**挂载到底告不告诉
女神目录在哪**。

机制事实:`add_dirs` 是**会话级** CLI 参数(SDK `_internal/transport/subprocess_cli.py`
把它渲染成 `--add-dir`),而 `AgentDefinition` **没有这个字段**(SDK `types.py`)。
所以挂载是**读权限**,不是**地址**。女神的 prompt 是 role + manual,拿不到
`contexts/panel.md`,于是她只能猜。

行为实测(探针:派 Clotho 去找 `KB-00-hub.md`,让她回 `FOUND=<绝对路径>`):

- **修复前**:`FOUND=D:\coding\skills\segment-prompt-t2\.ah\knowledge\KB-00-hub.md`
  —— 她 Glob 了三次,找到的是 **CLI 路物化在工作区里的那份副本**。该副本整整少一篇
  `KB-14-artifacts-persistence.md`,且 `KB-02-io-dataflow.md` 缺失 PR #817 刚补进去的
  「输入切片怎么到达模型」整节。**面板侧派出去的女神在读一份陈旧的知识库。**
- **修复后**:`FOUND=…\apps\studio\backend\app\agents\knowledge\KB-00-hub.md`,
  且动作从 Glob 摸索变成 Read 直达。

A/B 的混杂因素受控:同一工作区、同一探针,盘上那份陈旧副本**原封不动仍在**,唯一
变量是注入的地址。

**修法**:`agent_assets.knowledge_location_note()` 生成一句带解析后绝对路径的运行时
事实,`copilot.py` 的 `_with_knowledge_location()` 把它拼进面板侧仅有的两个装配
产物——主线程 append 与三女神 `AgentDefinition.prompt`。这句里同时写明「不要用盘上
别处找到的 `KB-*` 文件替代,工作区里可能留着 CLI 路的副本且可能陈旧」。

**为什么注入而不是写进 `contexts/panel.md`**:那是随安装位置变化的绝对路径,属于资产
文件头自己声明排除的
「no tool mechanics (enforced in code)」。写进散文既写不对,也会和代码形成两份真相。

门禁化:`test_dispatched_fate_can_resolve_a_knowledge_link` 断言解析出的真实目录路径
出现在 append 与每一位女神的 prompt 里。

### 12. SDK/CLI 对等审计的处置台账

三路并行审计 + 三路对抗核验,共 32 条分叉。处置分四档:

| 档 | 条数 | 处置 |
|---|---|---|
| 应有差异(规格逐字钉住两侧各自形状) | 7 | 不动。装配形状、挂载 vs 物化、免审批名单 21/21 全等、MCP 工具面 42 vs 40 均属此类 |
| 已登记的已知差距 | 3 | 不动,已有书面裁定:R8.8「ah 路的等价强制 shall 记录为已知差距与后续项,本期不在 Studio 层造次优 workaround」;`design.md` Non-Goals 列「ah 侧强制沙箱/hooks」 |
| 本决议修 | 3 | §10 的 `moirai-intro` 中立化 + R5.4 措辞订正;§9 的 `cli.md` 派工语义;§11 的知识库定位 |
| 留待后续 | 其余 | 见下 |

**对抗核验推翻了审计的四条判定**,记在这里以免下一轮重复踩:

1. 「`cli.md` 缺 `ah ps` = 漂移-规格明确」→ 实为规格自相矛盾,且按 R7.5 **不该补**
   (§10)。审计把它列为「最该先处理的第一条」,照做会直接违反 R7.5。
2. 「codex 整条审批链被 flag 关闭 = 漂移」→ 已登记差距,非漂移。但核验附带指出一条
   **审计和辩方都没走到的追问**:被接受的那条差距,其前提是「靠沙盒物理隔离兜底」
   (`ah-orchestration-design.md`),而 codex 恰恰带
   `--dangerously-bypass-approvals-and-sandbox` 关掉自身沙箱——**兜底前提不成立**。
   这一条值得单开任务,不在本 PR。
3. 「派工工具 `Task` 不在免审批名单,因此每次派工都挂起审批」→ 事实错误。工具名是
   `Agent`,随包 CLI 二进制对它无条件 `allow`,`can_use_tool` 压根不被调用,实测 0 张
   审批卡(§4)。真实缺口方向相反:派工现在**无闸**,且无门禁登记这一档。
4. 「SDK 女神丢失知识库入口 = 漂移-规格明确」→ verdict 方向判反(R4.4 明写两路不同
   机制),但**结论歪打正着**:入口确实丢了,只是丢在「挂载给读权限不给地址」这一层,
   两边都没查到(§11)。

**留待后续,不在本 PR**:

- CLI 侧三位 worker 拿不到 MCP,却读着同一份声称「`studio` 工具可用」的 `cli.md`。
- `web-research` 技能在 `agent-skill-map.json` 里无归属,CLI 四席位都装不上。
- atropos 在面板侧被派工时拿不到 `<judge_context>` 契约(该契约只在 `panel.md`,
  而女神 prompt 是 role + manual)。当前由主线程读文件后转述,尚未证明是缺陷。
- 上面第 2 条的 codex 沙箱兜底前提。

### 13. D-3 的状态

D-3(不动 `roles/moirai.md` 的分配判据)**维持**,理由不变:改行为判据必须先有测得出
的因果,而目前只有「20% 派工率」这个现象,没有证据表明判据措辞是它的原因。§7 已经
有过一次教训——技能挂载漂移看着像根因,实测 1/5 vs 1/5,无差别。

下一步是**先测再改**:用 `dispatch-rate.sh` 对「把 scope 契合改成可对照技能映射表
机械核对」的措辞跑 n≥5 的 A/B。这是一件独立的任务,不夹进本 PR。
