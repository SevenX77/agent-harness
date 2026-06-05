# 设计文档写作规范

> 怎么**写**。三轴心智见 [`00-three-axes.md`](./00-three-axes.md);怎么**审**见 [`02-audit-standard.md`](./02-audit-standard.md);**范例**见 [`example/`](./example/)。**通用 + 自包含**:不引规则文件夹外的文件。

## 0. 文档体系(三轴 → 载体)
- **workflow(轴①)= 决策留底**:atom action 决策表(PM 原话 + 每动作涉及的能力模块);模板见 §3。
- **能力模块(轴②)= `baseline` + `alignment`**:自包含 SSOT(实现 + 就近决策原话);模板见 §4 / §5。
- **设计单元(轴③)= `INDEX`**:横跨 / 锁映射枢纽;结构见 `02` R8。
- **baseline 迭代期定义**:baseline 对齐**当前代码** = **上一版 MVP + 本版已写增量**(若 mvp0 则 = 零);**边设计边写、写多少代码 baseline 就对齐多少**(原子闭环上先设计后实现,整体并行增量)。

## 1. 文档状态与锁机制
### 1.1 文件级四态(frontmatter `status`)
`drafted`(在写,自由改)· `FROZEN`(审计全 PASS + owner 盖章,锁定,改动需 exemption)· `superseded`(被新版取代中,不再当 SSOT)· `deprecated`(新版零引用后,可删)。

### 1.2 流转
```
drafted ──审计全 PASS + 盖章──▶ FROZEN ──改动需 exemption(否则哈希锁拦)
任何 ──被新版取代──▶ superseded ──新版零引用旧版──▶ deprecated(可删)
```

### 1.3 锁载体
`status` frontmatter(人读);`FROZEN` 文档额外上 SHA-256 哈希锁(改动触发测试,须 exemption)。盖章 = owner 确认审过 → 改 status + 哈希入表。

### 1.4 为什么"审计后才锁"
FROZEN 是**审计通过的背书,不是起点**:drafted 期自由改,审过+盖章才 FROZEN+上锁。锁 = 质量背书,不是改动障碍。

### 1.5 典型迁移序(旧版 → 新版 · 通用)
旧版去 FROZEN → `superseded` → 新版零引用旧版(审计 R1)→ 旧版 `deprecated` → 新版严格审计全 PASS → 盖 `FROZEN`。(项目具体执行序登记在项目 INDEX。)

### 1.6 单元级锁(横切设计单元)
横切设计单元(横跨多能力模块)在 INDEX 有自己的锁态 `unit-lock ∈ {drafted, locked}`:
- **单元 `locked`**:该单元审过、锁住(涉及的各模块切面再改走 exemption),**不必等同文件里别的单元**。
- **文件级 `FROZEN`** = 该文件承载的**所有**单元切面都 `locked`(全 ready)。
- 能力模块文件 frontmatter 标 `units:`(它承载哪些单元切面),锁态以 INDEX 为准。
- **`units:` 含 owner 切面 + 消费/引/落点切面**(消费方"承载"的是该单元的消费切面);**非 owner 切面必须在 §5/正文标 `(消费)/(引)/(落点)` + owner 模块**。owner 唯一性(R8 去重)以 INDEX spans 为准——frontmatter 列消费切面**不算** R8 污染。
> 解决:横切单元(如子图)ready 了能**先锁防漂移**,即使所在文件还有别的真空单元。

## 2. 引用拓扑(防 drift)
- **能力模块自包含**:实现 + 就近 PM 决策原话(§4 §5),读它就够、**不跳 workflow 取决策**。
- **轴② 内直接双向**:`baseline↔alignment`(frontmatter `binds_*`)· 能力模块间实现引用 · `代码↔baseline`(代码注释标 baseline;baseline 用 `文件:符号名` 为主、行号辅,抗漂移)。
- **横跨 / 锁** → INDEX 登记(轴③),文件只标"属于哪个单元";workflow 留底独立。
- **不跨轴两两互引**。

## 3. workflow 文档模板(轴① 决策留底)
```markdown
# <Node N>: <设计决策旅程步骤>
> Tier: workflow · 涉及能力模块: <链接>
## 1. 旅程目标(这步拍哪些决策)
## 2. atom action 决策表
| 原子动作 | 决策 / 锁状态 | 涉及能力模块(链接,实现 SSOT 在此) | PM 原话依据 |
## 3. 设计决策基础(PM 原话留底)
## 4. 节点间流转(上游 / 下游)
## 5. 测试关键点
```

## 4. baseline 标准模板(轴②)
```markdown
---
module: <模块路径>
doc: baseline
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
- 实现自写完整、不引弃用文档当 SSOT;**决策原话就近写**(防误解,允许 workflow 留底冗余)。
- 横切单元在 INDEX 登记 + 单元锁;新文档 `drafted` 起,审过 + 盖章才 `FROZEN` / 单元 `locked`。
- 引用挂 `文件:符号名`(抗漂移)/ 原话证据。
- **审计 ≠ 改代码**:审计发现的代码债(空壳 / 坏味道 / 代码-文档背离)→ **如实写回 baseline + 🚨 警告**,归 refactor-target(kiro);**不在文档审计里顺手改代码**(重构是独立任务)。
