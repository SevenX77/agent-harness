---
doc: change-invalidation-model
status: 留底（轴① 决策档案;实现 SSOT 已迁 05-invalidation/06-golden-eval;§2 含反转前旧内容,勿当现状）
owns: 跨关注点"源变更 → 派生物失效"的统一模型(golden 09 / checkpoint 10 / compile-cache 12 共享)
related:
  - 09-golden-eval（golden 失效 = 编译期硬错误）
  - 10-iteration-and-resume（checkpoint 失效 = resume 置灰）
---
> 🔖 **本文 = 轴① 决策留底(workflow archive),非实现 SSOT。** 实现真相已迁入 [`05-invalidation`](../../01-contract/05-invalidation/mvp1-alignment.md)(变更轴 + 消费者矩阵,**已按 golden→workspace 反转调整为 eval 期**)+ [`06-golden-eval`](../../02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment.md)。本文保留完整决策上下文,但 **§2 含反转前旧内容(golden 失效 = 编译期硬错误 `[F-v3-golden-stale-fields]`),已废——现状是 eval 期失效,勿当现状引用。**
<!-- 核对进度:已迁 6 块 / 未迁 1 块 / 2026-06-04 -->

~~# 统一"变更 → 失效"模型(C3)~~ → ✅[已迁入](../../01-contract/05-invalidation/mvp1-alignment.md#1-定义)

> **缘起(Task 2 C3)**:09 的 golden 失效、10 的 checkpoint 失效被随口称"同概念",但实际**粒度/时机/后果都不同**。含糊一句会让实现者造两个发散的 staleness 检测器,或把规则张冠李戴。本文**定义一套变更轴,再用矩阵把每个消费者映射到它关心的轴 + 后果** —— 让"同概念"落到"共享同一套变更轴定义,各取所需",而非"同一个检测器"。

~~## 1. 变更轴(taxonomy:一个 skill/节点可能发生的变更)~~ → ✅[已迁入](../../01-contract/05-invalidation/mvp1-alignment.md#1-定义)

| 轴 | 含义 | 是否动 IO 契约 |
|---|---|---|
| **A1** prompt / 节点内部设置(prompt 文本、model、params、tools) | 改"怎么算" | 否 |
| **A2a** `io.outputs` **必填**字段 增 / 删 | 改输出契约(必填集) | 是 |
| **A2b** `io.outputs` 字段**类型** 改 | 改输出契约(类型) | 是 |
| **A2c** `io.outputs` **非必填**字段 增 / 删 | 弱改输出契约 | 弱 |
| **A3** `io.inputs` schema 改 | 改输入契约 | 是 |
| **A4** 上游节点输出 改(本节点依赖的节点变了) | 改上游产物 | 间接 |
| **A5** 拓扑改(`depends_on` / 节点 增删改名) | 改图结构 | 是 |

<!-- ⚠️ 未迁入（仅摘要迁入且正式文档已因 golden→workspace 反转改为 eval 期；源文档里的“编译期硬错误 [F-v3-golden-stale-fields]”未等价承载） → 应归入:01-contract/05-invalidation + 02-mechanism/05-run-inner/06-golden-eval -->
## 2. 消费者 × 关心的轴 × 后果(核心矩阵)

| 消费者 | 关心的轴 | 时机 | 后果 | **刻意不管** |
|---|---|---|---|---|
| **golden 失效**(09 G2) | **仅 A2a**(必填字段增,致 golden 缺该字段) | **编译期** | **硬错误** `[F-v3-golden-stale-fields]`,补齐才能 predict | A1 / A2b / A2c / A3 / A4 / A5 |
| **checkpoint 失效**(10 §4) | **A2(本节点输出契约)/ A4(上游)/ A5(拓扑)** | **resume 期** | 下游 checkpoint 置脏 → 前端 **[Resume] 置灰**(软,非错误) | A1(prompt 改不影响"已存状态结构能否安全续") |
| **compile cache**(12 / `compiler.py:38` cache) | **任意源改**(最粗,源 hash) | 编译期 | **透明重编译**(无感) | — |
| predict | = golden(经 golden 失效) | predict 期 | golden 缺 → 该节点 predict 不可跑 | 同 golden |

**读法**:三个消费者**共享上面 §1 的轴定义**,但**各取不同子集 + 不同后果**:
- golden 只盯 **A2a**(最窄,因为 golden = 按必填字段对齐的期望输出;prompt 改/类型改不使"已填的期望值"失效,故 09 G2 刻意只 block 缺必填字段)。
- checkpoint 盯 **A2/A4/A5**(较宽,因为 checkpoint = 一段在旧图下产生的状态;上游/拓扑/输出契约变了,旧状态喂下游就不安全)。
- compile cache 最粗(任意源变就重编)。

→ 它们**不是同一个检测器**,但也不该各写各的"什么算变"。

~~## 3. 一处定义、各取所需(实现原则)~~ → ✅[已迁入](../../01-contract/05-invalidation/mvp1-alignment.md#1-定义)

实现**一个变更检测模块**:`diff_skill(old, new) -> set[ChangeAxis]`(算出 A1–A5 哪些轴变了)。然后:
- golden 编译校验:`if A2a in changes(node): emit [F-v3-golden-stale-fields]`。
- checkpoint 置灰:`if {A2,A4,A5} ∩ changes(downstream-of node): mark checkpoint stale`。
- compile cache:源 hash 变即失效(不依赖 axis 细分,但可复用同一 diff 做更细的"只重编受影响 phase")。

**好处**:轴定义单一真相源,新增消费者(如未来"重测建议")只需声明关心哪几轴,不重造"什么算变"。

~~## 4. 退役项~~ → ✅[已迁入](../../01-contract/05-invalidation/mvp1-alignment.md#1-定义)
- 旧 `io_outputs_schema_hash` 整哈希漂移检测(`runner.py:127-160` `_warn_on_stale_golden_hashes_sdk`,只 warn):**退役**。它把 A1/A2a/A2b/A2c 混成一个 hash,粒度太粗(改 prompt 也可能变 hash → 误报),正是 09 G2 要用"只看 A2a"取代的对象。

~~## 5. 与其他文档~~ → ✅[已迁入](../../01-contract/05-invalidation/mvp1-alignment.md#1-定义)
- golden 失效细节 → 09-golden-eval §G2(本文是其"为什么只看必填字段"的上位模型)。
- checkpoint 失效 → 10-iteration §4(本文统一其"什么变更触发置灰")。
- 错误码 `[F-v3-golden-stale-fields]` 带轴(phase_id + field_path=缺的必填字段)→ Task 3 错误码定位审计。

~~## 6. 待办~~ → ✅[已迁入](../../01-contract/05-invalidation/mvp1-alignment.md#1-定义)
1. `ChangeAxis` 枚举 + `diff_skill` 实现(实施期,TDD)。
2. checkpoint 置灰的"下游"判定 = 拓扑依赖分析(A5 变时尤其);与 12 编译期 DAG 分析复用。
