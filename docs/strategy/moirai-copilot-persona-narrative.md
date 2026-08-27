---
doc: moirai-copilot-persona-narrative
role: guide
status: living
updated: 2026-08-27
---

# MoirAI — copilot 人格叙事 & 选名研究(完整版)

> **日期**: 2026-07-03
> **用途**: Studio copilot 的 agent 人格「MoirAI」的**完整命名叙事** + **选名过程全记录**(候选、取舍、词源、读音、重名排查、研究方法)。
> **权威边界**: 本文只回答“为什么叫 MoirAI、三位人格怎样形成这套叙事”，不是能力、实现、工具数量或交付状态的真相源。当前能力与完成状态以
> [requirements](../../.kiro/specs/studio-moirai-agent-system/requirements.md)、
> [design](../../.kiro/specs/studio-moirai-agent-system/design.md)、
> [tasks](../../.kiro/specs/studio-moirai-agent-system/tasks.md)、
> [golden authoring decision](../../.kiro/specs/studio-moirai-agent-system/decision-2026-08-07-golden-case-authoring.md)、
> [terminal output decision](../../.kiro/specs/studio-moirai-agent-system/decision-2026-08-07-run-terminal-output-contract-and-cli-read-tier.md)与
> [runtime dispatch decision](../../.kiro/specs/studio-moirai-agent-system/decision-2026-08-15-per-runtime-dispatch-operating-rules.md)为准；活资产在 `apps/studio/backend/app/agents/`。独立 runtime 的未来集成目标见
> [Graph Skill Runtime v1 alignment](../engine/graph-skill-runtime/v1-alignment.md)，该目标仍是 `drafted`。
> **和 Studio 设计源的关系**: 身份标、开合交互等 UI 硬约束在
> `docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md` 的 **F1·R5-E** 约束条目。本文是叙事与研究档案；要查当前产品行为，应沿上述权威指针核验，不从叙事推断实现状态。
> **配套**: `investor-pitch-positioning.md`(产品对外定位)· `2026-05-30-build-vs-adopt-decision.md`(竞品/护城河)。

---

## 一、一句话

**MoirAI** 是 Graph Studio 里陪着一条 skill 走完一生的 copilot 人格,取自古希腊命运三女神 **Moirai**;名字本身藏着 **Moir-AI**——词尾就是 AI。

---

## 二、完整叙事

> 以下是一段可独立对外的完整叙事,可整段复制。

每一个 skill,都是一条线。它从一团散落的意图开始——你想让它做什么、分成几步、每一步交给谁。MoirAI 把这团意图纺成一条能运行的线:一份 GRAPH.md 加一组 phases,一条从输入到输出、节点接着节点的生产流水线。纺出来还要量:编译得过、bug 修得顺、每个节点都对得上它该有的样子。量准之后要跑、要审判:整张图跑出来的结果,究竟达不达标;而这一判的结论,又回流到起点,让这条线重新被纺一遍。一条 skill 的一生,就是这样一个循环——纺,量,剪,再纺。

MoirAI 这个名字,取自古希腊命运三女神 Moirai。神话里,每个生命都是一根线,由三姐妹分工掌管:Clotho 纺出这根线,Lachesis 量它的长短,Atropos 剪断它。这套分工,恰好是一条 skill 走完一生要经过的三段,于是三姐妹在 MoirAI 里各自对应一个 agent——Clotho 负责设计 skill,把散落的意图纺成 GRAPH.md 和 phases;Lachesis 负责编译与修 bug,比照 skill 该有的样子把它量准、修顺;Atropos 负责整体 eval,对整张图跑出来的结果下一次不可撤销的终判:达标放行,不达标否决,终判再回流给 Clotho,开始下一轮设计。

名字里还藏着一层意思:Moir-AI——词尾正好是 AI。三位女神纺的、量的、剪的那根线,在这里就是一条由 AI 驱动、既能被设计也能被审判的生产流水线。

在这套人格叙事中，MoirAI 是三姐妹的统称与对话入口：Clotho 对应“纺”，Lachesis 对应“量”，Atropos 对应“剪”。角色当前是否落地、由哪些 tools 与 skills 支撑、界面显示哪一种身份，属于会随实现变化的产品事实，必须查本文开头指向的当前能力权威，不能由这段叙事推断。

---

## 三、三位一体:命运三女神 → 三个 agent

神话里,每个生命都是一根线,命运三女神分工掌管它:

| 女神 | 神话职能 | 映射到一条 skill 的一生 |
|---|---|---|
| **Clotho**(克洛托) | **纺**出这根线 | **设计 skill**——把散落意图纺成 `GRAPH.md` + phases |
| **Lachesis**(拉刻西斯) | **量**它的长短 | **编译 + 修 bug**——比照它该有的尺寸,量准、修顺 |
| **Atropos**(阿特罗波斯) | **剪**断它 | **整体 eval**——对整张 graph 跑出来的结果下**不可撤销的终判** |

这套分工和一条 skill 的生命周期**同构**,所以它不是牵强的比喻,而是把"谁管哪一段"讲清楚。Atropos 的终判**不是** golden eval 的逐样例对拍,而是对**整张图运行结果**的整体评估;终判反馈**回流 Clotho**,让 skill 被重新设计——这就闭成了**迭代循环**。

> **叙事与状态分离**：三位角色的神话映射是稳定的命名决定；角色是否可调度、当前 UI 如何呈现、具体能力是否完成是时态事实。后者只由当前 requirements/design/tasks、dated decisions 与活代码证明，本文不维护一份并行状态表。

---

## 四、名字的双关与读音

- **双关**:**Moir-AI** —— 词尾正好是 **AI**。
- **读音**:
  - **MoirAI** ≈ 「莫伊莱」 /ˈmɔɪraɪ/(Moirai = 三女神的希腊语**统称**)
  - Clotho /ˈkloʊθoʊ/(克洛托)
  - Lachesis /ˈlækɪsɪs/(拉刻西斯)
  - Atropos /ˈætrəpɒs/(阿特罗波斯)——本义「**不可转 / 不可逆**」,呼应"终判"

选 **Moirai(希腊语统称)** 而不是 **The Fates(英译)**:前者更原味,且天然带出 **Moir-AI** 双关;后者只是普通英文词,没有这层 AI 谐音。

---

## 五、选名研究全记录(候选 → 取舍)

命名不是一步到位的,经历了 **"织女 → The Fates → MoirAI"** 的演进。以下是所有认真考虑过的候选,连同词源、读音、去留原因:

| 候选 | 词源 / 意象 | 读音 | 去留 & 原因 |
|---|---|---|---|
| **织女 Zhinü** | 中国神话织造女神,把散落丝线织成云锦天衣;同构于"把散落 phase 织成 DAG" | zhī nǚ | **弃**。用户要的是**神话人物的名字**(人名),不是"织神/织女"这种**职能直译**;且当时配的 `Waypoints` 图标"和织造没关系"。(最早在 PR #299 落过,后被 MoirAI 取代。) |
| **Neith** | 埃及织造 / 战争女神,司纺织 | /niːθ/ | **弃**。用户「读起来不顺口」。 |
| **Aria** | 意大利语"咏叹调";顺口、柔和 | /ˈɑːriə/ | **未选**。用户觉得比 Neith 顺口,一度考虑;但太常见(大量 AI 助手都叫 Aria)、缺神话/线的叙事锚。 |
| **Ariadne 阿里阿德涅** | 希腊神话:给忒修斯**一根线**,让他走出弥诺陶洛斯的迷宫(**Ariadne's thread**);"线 = 在迷宫/图里寻路" 与 DAG 寻路同构 | /ˌæriˈædni/ | **入围后让位**。叙事很贴(线 + 寻路),但"线"在她这里是**寻路工具**,不像三女神那样覆盖"纺→量→剪"整条生命周期。 |
| **Vega 织女星** | 天琴座主星,中文即"**织女星**",把"织"的意象升到星空 | /ˈviːɡə/ | **未选**。和 Clotho 一起被点名比较过;意象好但和"织女"一样偏"织"这单一动作。 |
| **Clotho 克洛托** | 命运三女神里**纺线**的那位 | /ˈkloʊθoʊ/ | **入围后上升**。生平查过;单取 Clotho 只覆盖"纺"(设计)一段。用户由此提出:与其取一位,不如把**三女神整体**作为编制 → 催生 The Fates / MoirAI。 |
| **The Fates** | 三女神的英文统称 | — | **中间态**。用户拍板:产品/copilot 用三女神概念,**Clotho / Lachesis / Atropos = 三个 agent**(设计 / 编译修 bug / eval)。这一步把"一个名字"升级为"三个 agent 的编制"。 |
| **MoirAI 莫伊莱** | 三女神的**希腊语统称 Moirai** + **Moir-AI** 双关 | /ˈmɔɪraɪ/ | **✅ 定名**。比 The Fates 更原味,天然带 AI 谐音;作为**产品内 agent 人格名**(非产品名/公司名)使用。 |

**演进主线**:一开始想直接用"织"的职能名(织女 / Vega / Neith),用户纠正"要**人名**、且要**顺口 + 有寓意**";于是转向希腊命运女神(Ariadne / Clotho);再从"取一位"上升到"三女神 = 三个 agent 的编制";最终用**统称 Moirai** 落地成 **MoirAI**,一名之内同时装下**三女神叙事**和 **AI 谐音**。

---

## 六、重名 / 竞品排查

- **同名产品**:市面上存在与 "Moirai" 相关的名字,例如 Salesforce 的 **MoiraiAgent**、**moirai-solutions** 等。
- **结论(用户 2026-07-02 拍板)**:MoirAI 在这里是**产品内 agent 的人格名**,**不是产品名、也不是公司名**,因此与上述同名者**不构成商标或市场定位冲突**——它出现的语境是"Studio 里那个叫 MoirAI 的 copilot",而非对外的产品/公司招牌。
- **搜索面**:候选名的神话/词源、GitHub、同类 AI 产品都做过检索,未发现"作为 AI copilot 人格名"的直接冲突。

> 一句话:**改的是 agent 的人格名,不是系统术语。** 功能域名称——Settings 里的 Copilot tab、`copilot_*` 的 role key、API 路径——**一律不动**。

---

## 七、边界纪律(防止叙事越权成产品契约)

1. **叙事不声明实现状态**：UI 显示哪些角色、调度如何工作、工具是否可用，以当前产品设计与活代码为准。
2. **命名不改系统术语**：历史命名决定没有自动改写 Copilot tab、`copilot_*` role key 或 API 路径；若未来要改，必须在相应契约中单独裁决。
3. **身份标只记录意象**：一形三读的自绘 SVG——**仙后座(Cassiopeia)五星连线**，同时读作字母 **M**、星座、节点与边的图。具体图标、画布 FAB、开合动画等交互硬约束以 Studio 设计源 **R5-E** 为准，本文不复制。

---

## 八、研究方法(留痕)

- **检索工具**:用 Studio 内配置的 **`gemini-official`** 凭证走 **Gemini**,对候选名做神话/词源检索与重名排查;辅以 GitHub、同类产品搜索。
- **决策归属**:名字方向与最终定名由**用户拍板**(需求 + 方向归 PM);本文档负责把过程与依据**记录留痕**,避免下次再从零讨论。它不据此取得能力设计或交付状态的所有权。
- **为什么单独立档**:设计源里 R5-E 只存压缩结论(一句话塞进约束条目),**叙事全文和选名研究一旦不落档就会随对话丢失**——本文即为此而设,后续命名/叙事的补充都往这里写。
