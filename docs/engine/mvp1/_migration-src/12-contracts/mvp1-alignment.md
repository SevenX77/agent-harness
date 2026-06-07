---
module: 12-contracts
doc: mvp1-alignment
status: drafted（Phase C 第 1 域,2026-06-03)
aligns_with: ../00-architecture-overview.md（§4 模块 1）
---
<!-- 核对进度:已迁 9 块 / 未迁 0 块 / 2026-06-04 -->

~~# 12-contracts — MVP1 Alignment(目标设计)~~ → ✅[已迁入](../../01-contract/04-data-contracts/mvp1-alignment.md#1-定义)

> **Tier**: L0 叶(共享词汇) | **Owns**: 类型 · 异常树 · 错误码契约 · state schema · result 类 · validator 契约 | **关键性质**: **不依赖任何内部模块**(去环基石) | **Related**: state-checkpoint(state schema)· Task3(错误码定位)· api §2/§5(result/异常契约)

~~## 1. 定义~~ → ✅[已迁入](../../01-contract/04-data-contracts/mvp1-alignment.md#1-定义)

contracts = Graph Agent 的**共享词汇**:所有模块都 import 它,它**不允许 import 任何内部模块**(L0 叶)。这是把 `core` 上帝包**去环**的基石——现在这些类型埋在 `core/` 里、与上层循环纠缠;抽成 leaf `contracts` 后,依赖图才可能无环(00-overview §5)。

~~## 2. 内容 + V4 处置(♻️沿用 / V4 delta / → SSOT)~~ → ✅[已迁入](../../01-contract/04-data-contracts/mvp1-alignment.md#1-定义)

contracts 大部分是**稳定 V0.3.0,♻️ 沿用**;本域只**汇总 + 标权威源**,不复制各专文的设计。

| 契约 | V4 处置 | 权威 SSOT |
|---|---|---|
| 异常树 `GraphAgentError…` | ♻️ 沿用 | `core/exceptions.py` |
| `ErrorPayload` + 注册表 | **V4 delta**:加 domain `golden`/`iterate`(Task1 Q1=A);加定位轴 `line`、emit 处填全 phase/field/source/level | Task1 解冻台账 · Task3 错误码审计 |
| result 类 `RunResult`/`PhaseRecord`/`PathDiff` | ♻️ + 显式接口契约 | api-engine-studio-contract §2 |
| state schema `BusinessData`/`FrameworkState`/`WorkflowState` | ♻️ 形状;**V4**:`data` 通道补 delta reducer、`_` 前缀不变量保持 | records/state-checkpoint-storage-model §2 |
| `Phase` AST | ♻️ 沿用 | `core/types.py` |
| validator 契约(签名 + 码) | ♻️ γ0 占位;运行时 validator 加载属 **execution 域** | `core/validator_contract.py` |
| 公开 `__all__` surface | ♻️ 稳定;增删须过 public-api 契约(`test_public_api_contract`) | runtime 域 |

~~## 3. 设计决策基础(用户原话)~~ → ✅[已迁入](../../01-contract/04-data-contracts/mvp1-alignment.md#1-定义)

> PM:"mvp1 不应该只是部分优化的文档,而是完整记录整个 engine 设计决策的文档,不变的地方可以复用 mvp0,但是不能不写。"

contracts 正是"♻️ 沿用为主"的典型:绝大部分稳定,但**必须在架构地图上有位、标清 V4 deltas + 权威源**,不能因"基本没变"就缺写。

~~## 4. 决策 + 动机~~ → ✅[已迁入](../../01-contract/04-data-contracts/mvp1-alignment.md#1-定义)

| ID | 决策 | 动机 |
|---|---|---|
| CT1 | contracts = L0 叶,**零内部依赖** | 去 `core` 循环依赖的基石;依赖图无环的前提 |
| CT2 | 错误码 / state schema / result 的权威设计**在各专文**,本域只汇总 + 标 SSOT | 防多处复制漂移(SSOT) |
| CT3 | `ErrorPayload` 加 `line` 轴(Task3)+ `golden`/`iterate` domain(Task1)= contracts 的 V4 实质改动 | 前端 3 处精准放标记 + mvp1 新一等概念 |

~~## 5. 测试关键点~~ → ✅[已迁入](../../01-contract/04-data-contracts/mvp1-alignment.md#1-定义)

1. **acyclicity guard**:`contracts` 模块 import 图**不含任何其他 engine 内部模块**(抽出 `core` 后加守卫测试)。
2. `ErrorPayload.code` 必须 ∈ `ERROR_REGISTRY`(现已校验);新增 golden/iterate 码须进注册表且带全四轴(Task3)。
3. `BusinessData` 拒 `_` 前缀字段(现 `state.py:137` 已校验)。
4. 公开 `__all__` 符号集稳定(现有 `test_public_api_contract`;改动须显式过契约)。

~~## 6. 涉及 region / platform~~ → ✅[已迁入](../../01-contract/04-data-contracts/mvp1-alignment.md#1-定义)

engine 全权;公开 `__all__` surface 被 studio / 外部消费者依赖(public-api 契约)。

~~## 7. gaps / 待设计~~ → ✅[已迁入](../../01-contract/04-data-contracts/mvp1-alignment.md#1-定义)

1. contracts 物理抽出 `core/`(→ 模块重排,kiro #10)。
2. `ErrorPayload` 加 `line` 字段 + emit 处填全定位轴(Task3 实施)。
3. `data` 通道 delta reducer(state-checkpoint §2.4,实施)。

~~## 交叉引用(链接,不复制)~~ → ✅[已迁入](../../01-contract/04-data-contracts/mvp1-alignment.md#1-定义)
00-architecture-overview §4 · records/state-checkpoint-storage-model · Task1 解冻台账 · Task3 错误码审计 · api-engine-studio-contract §2/§5
