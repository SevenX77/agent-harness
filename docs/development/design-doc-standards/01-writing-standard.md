---
doc: writing-standard
status: living（怎么写的规范，随实践反馈持续演进，不进入 FROZEN 流水线）
role: guide
---

# 设计文档写作规范

> 怎么**写**。三轴心智见 [`00-three-axes.md`](./00-three-axes.md);怎么**审**见 [`02-audit-standard.md`](./02-audit-standard.md);**范例**见 [`example/`](./example/)。**通用 + 自包含**:不引规则文件夹外的文件。

## 0. 文档体系(三轴 → 载体 → `role:`)
- **workflow(轴①)= 决策留底**:atom action 决策表(PM 原话 + 每动作涉及的能力模块);模板见 §3。
- **能力模块(轴②)= `baseline` + `alignment`**:自包含 SSOT(实现 + 就近决策原话);模板见 §4 / §5。
- **设计单元(轴③)= `INDEX`**:横跨 / 锁映射枢纽;结构见 `02` R8。
- **baseline 迭代期定义**:baseline 对齐**当前代码** = **上一版 MVP + 本版已写增量**(若 mvp0 则 = 零);**边设计边写、写多少代码 baseline 就对齐多少**(原子闭环上先设计后实现,整体并行增量)。
- **载体角色显式化(frontmatter `role`)**:上面三轴的载体划分此前只隐含在路径 / 文件名 / 正文里(如"Tier: workflow"这类散文),读者分不清"这份是权威"还是"这份是它的摘要",也没有任何机制能校验。`role` 把这一维钉成 frontmatter 闭集字段,取值只有以下 6 个:
  - `workflow-record`(轴① 决策留底,§3 模板)
  - `baseline`(轴② 与代码同步的现状,§4 模板)
  - `alignment`(轴② 设计与目标,权威,§5 模板)
  - `index`(轴③ 设计单元枢纽——特指横跨模块的 R8 索引本身,例如 `DESIGN_UNITS_INDEX.md`;一个目录自己的导航目录/README 不算,归 `guide`)
  - `summary`(摘要 / 导航,**非权威**——它压缩、复述或导览另一份文档;必须同时带 `authority:` 字段,指向真正权威的那份文件,且该文件必须存在。这是给"摘要滞后于权威、读者却只读了摘要"这个真实发生过的失误上的机器锁:一份声明 `role: summary` 的文档,其 `authority:` 指针必须能解析到磁盘上的真实文件)
  - `guide`(工程手册 / 操作指南,例如 `docs/development/CROSS_PLATFORM.md`,或本目录里的三份规范自身)

## 1. 文档状态与锁机制
### 1.1 文件级状态机(frontmatter `status`)
`drafted`(在写,自由改)· `audited-ready`(语义已过审计 R0–R8/Q1–Q5,owner 尚未盖章 / 机器哈希锁尚未落表——**已审但未锁**的过渡态,详见 §1.4;这不是新发明的状态,`02-audit-standard.md` M8 早已把它作为"没机器就别冒用 FROZEN"的正确落点)· `FROZEN`(审计全 PASS + owner 盖章 + SHA-256 哈希锁落表,锁定,改动需 exemption)· `superseded`(被新版取代中,不再当 SSOT)· `retired`(新版零引用后,可删;`deprecated` 一词已废弃——项目正文一律用"退役"对应 `retired`,一个状态只保留一个名字)· `living`(持续维护、永不冻结——台账、INDEX、本规范自身这类文档没有"审计通过即完稿"的终点,`FROZEN`/`audited-ready` 对它们不适用)。

状态值可带括号注解(如 `status: drafted（现状对齐 pinned 代码 abc1234；...）`),注解自由,但状态词本身必须原样落在这个闭集里,机器按注解前的第一个词判定。

### 1.2 流转
```
drafted ──审计全 PASS──▶ audited-ready ──owner 盖章 + 哈希落表──▶ FROZEN ──改动需 exemption(否则哈希锁拦)
任何 ──被新版取代──▶ superseded ──新版零引用旧版──▶ retired(可删)
living ──不进入上面任何一条链路;持续维护到该文档本身退役为止
```

### 1.3 锁载体
`status` frontmatter(人读);`FROZEN` 文档额外上 SHA-256 哈希锁(改动触发测试,须 exemption)。盖章 = owner 确认审过 → 改 status + 哈希入表。

### 1.4 为什么"审计后才锁"
FROZEN 是**审计通过的背书,不是起点**:drafted 期自由改,审过之后先落 `audited-ready`(语义已审,但哈希锁这层机器强制还没接上),owner 盖章 + 哈希入表才真正 FROZEN+上锁。`audited-ready` 存在的意义是不让"语义已审"和"机器已锁"这两件事被同一个状态词混为一谈——把"审过了、还没锁"这段窗口如实标出来,而不是提前冒用 `FROZEN` 制造假信心(呼应 `02-audit-standard.md` M8)。锁 = 质量背书,不是改动障碍。

### 1.5 典型迁移序(旧版 → 新版 · 通用)
旧版去 FROZEN → `superseded` → 新版零引用旧版(审计 R1)→ 旧版 `retired` → 新版严格审计全 PASS → 先 `audited-ready` → owner 盖章 + 哈希落表 → 盖 `FROZEN`。(项目具体执行序登记在项目 INDEX。)

### 1.6 单元级锁(横切设计单元)—— owner-scoped 三态
横切设计单元(横跨多模块)在 INDEX 有锁态。多子系统 monorepo 里各子系统(studio / engine / gateway)**独立冻结**,故单元锁按"**本系统自有切面**"判定,**不被外部系统的冻结节奏卡死**。锁态拆三维:
- **`owned-lock` ∈ {drafted, locked}**:本系统(studio)**自有 / 消费 / 适配 / 落点**切面是否审过 + 盖章 + 落在已 `FROZEN` 哈希锁文档里。`locked` 只背书"本系统自己那半"。
- **`external-binding` ∈ {none, floating-draft, pinned-draft, frozen-pinned, stale}**:本单元对外部系统切面(标 `(引)`,owner=`engine:*` / `gateway:*`)的绑定状态。`none`=无外部依赖;`floating-draft`=有外部依赖但外部仍 drafted、未 pin(当前默认);`pinned-draft`=已 pin 外部 SHA 但外部仍 draft;`frozen-pinned`=外部已 FROZEN 且 pin;`stale`=pin 的外部已漂移待复核。
- **`integration-lock` ∈ {unverified, locked}**(派生):`locked` ⟺ `owned-lock=locked` **且** `external-binding ∈ {none, frozen-pinned}`。即只有"自有锁 + 外部要么没有要么已冻结钉死"才算端到端锁定;有 `floating-draft` / `pinned-draft` 外部依赖的单元 = `unverified`,**不得宣称端到端 locked**。
- **文件级 `FROZEN`** = 该文件承载的所有单元的 **owned 切面**都 `owned-lock=locked`(本系统控得住的部分);**不要求**外部依赖也冻结。
- 能力模块文件 frontmatter 标 `units:`(承载哪些单元切面),锁态以 INDEX 为准。
- **`units:` 含 owner 切面 + 消费/引/落点切面**;**非 owner 切面必须在 §5/正文标 `(消费)/(引)/(落点)` + owner 模块**。owner 唯一性(R8 去重)以 INDEX spans 为准——frontmatter 列消费切面**不算** R8 污染。
- **防假信心**:`owned-lock` 只锁字节,挡不住"外部契约漂了、本系统文档没变"。外部依赖的语义防漂移靠 `external-binding` 的 pin 机制(外部引用台账;外部系统稳定后逐个 `floating-draft`→`pinned-draft`→`frozen-pinned`)。
- **锁态机器强制**:INDEX 是活注册表(可加新单元)、**不整文件入哈希锁**;但已 `locked` 单元的锁态 / owner / spans 由**锁态快照**(`_design-unit-lock-snapshot.json`,入哈希锁)+ 快照测试保护,防静默回退 / 换 owner / 删行。
> 解决:横切单元 ready 了能**先锁自有切面防漂移**,不必等外部系统冻结;同时用三态**诚实区分**"自有锁定"与"端到端锁定",不制造假信心。

## 2. 引用拓扑(防 drift)
- **能力模块自包含**:实现 + 就近 PM 决策原话(§4 §5),读它就够、**不跳 workflow 取决策**。
- **轴② 内直接双向**:`baseline↔alignment`(frontmatter `binds_*`)· 能力模块间实现引用 · `代码↔baseline`(代码注释标 baseline;baseline 用 `文件:符号名` 为主、行号辅,抗漂移)。
- **横跨 / 锁** → INDEX 登记(轴③),文件只标"属于哪个单元";workflow 留底独立。
- **不跨轴两两互引**。

## 3. workflow 文档模板(轴① 决策留底)
```markdown
---
role: workflow-record
---
# <Node N>: <设计决策旅程步骤>
> Tier: workflow · 涉及能力模块: <链接>
## 1. 旅程目标(这步拍哪些决策)
## 2. atom action 决策表
| 原子动作 | 决策 / 锁状态 | 涉及能力模块(链接,实现 SSOT 在此) | PM 原话依据 |
## 3. 设计决策基础(PM 原话留底)
## 4. 节点间流转(上游 / 下游)
## 5. 测试关键点
```

> 若这份 workflow 文档本身只是**导览 / 摘要**、细粒度权威另在别处(例如一条旅程节点的高层走查,细节由同目录另一份 PM 口述规格承载),把 `role: workflow-record` 换成 `role: summary` 并加一行 `authority: ./<权威文件>.md` 指向真正权威的那份——不能两者都不写,更不能只在正文里提一句就算数(§0)。

## 4. baseline 标准模板(轴②)
```markdown
---
module: <模块路径>
doc: baseline
role: baseline
status: drafted（现状对齐 pinned 代码 <commit>；<一句话状态>）
binds_alignment: ./<milestone>-alignment.md
binds_code: <文件:符号名 为主、行号辅,如 core/x.py:fn>
units: [<unit-a>]                 # 本文承载的设计单元切面(在 INDEX 登记)
---
# <模块> — Baseline(当下代码实现逻辑)
> Scope / 现状一句话(+ ⚠️ 被反转/stale 标注)
## UI/UX · 前端逻辑 · 后端功能(分小节,每条挂 文件:符号名,术语首现定义)· API · Data Model/State
## 当前边界(这个模块现在不是什么)
## baseline / alignment 差异(测试锚点)  | 维度 | 现状 | 目标 |  + 验"是否按目标改了"
## 读代码主路径提示
## 交叉引用  ── alignment(配对双向) + 轴②内跨模块双向
```

## 5. alignment 标准模板(轴②)
```markdown
---
module: <模块路径>
doc: <milestone>-alignment
role: alignment
status: drafted（<状态>）
binds_baseline: ./baseline.md
units: [<unit-a>]
aligns_with: <架构总览§x>
---
# <模块> — <milestone> Alignment
> Tier · Owns · 现状 · Related
## 1. 定义
## 2. 数据流 / 机制   ← 含设计细节(签名/字段/步骤/错误码),非只方向
## 3. 接口契约
## 4. 设计决策基础(PM 原话)  ← 就近写原话(隐含假设护栏,防 AI 误解)
## 5. 决策 + 动机
## 6. 测试关键点 · 7. region/platform · 8. gaps/报警(🚨 真空;实施归 kiro)
## 交叉引用 ── baseline(配对双向) + 轴②内跨模块双向
```

## 6. 写作铁律
- baseline 对代码(迭代期 = 上一版 + 增量)、alignment 对决策,不混。
- 实现自写完整、不引已退役(`retired`)文档当 SSOT;**决策原话就近写**(防误解,允许 workflow 留底冗余)。
- 横切单元在 INDEX 登记 + 单元锁;新文档 `drafted` 起,审过先 `audited-ready`,盖章 + 哈希落表才 `FROZEN` / 单元 `locked`。
- 引用挂 `文件:符号名`(抗漂移)/ 原话证据。
- **每份文档的 frontmatter 必须同时带 `status:`(§1.1 闭集)与 `role:`(§0 闭集)**;`role: summary` 必须带 `authority:` 且指向真实存在的文件。
- **审计 ≠ 改代码**:审计发现的代码债(空壳 / 坏味道 / 代码-文档背离)→ **如实写回 baseline + 🚨 警告**,归 refactor-target(kiro);**不在文档审计里顺手改代码**(重构是独立任务)。
