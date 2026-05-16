# Graph-Agent State Management Optimization — Requirements

**Spec**: graph-agent-state-mgmt-optimization
**Status**: Requirements (Kiro Step 1/3)
**Date**: 2026-05-16
**Author**: a2 (Gemini, resident architect)
**Base**: V2.1 Hard Cutover commit `a53e72c` (PR #45 merged 2026-05-16)
**Related**: V2.1 Hard Cutover (PR #45), studio-canvas-v1

## R0. 范围声明 + 主控决策记录

本次 Spec 旨在打通 V2.1 引擎的 Fan-out 并发链路，解决 BlackboardState 并发写冲突问题，并联调 Canvas-v1 的多入连线行为。

**主控决策记录 (已拍板):**
1. **决策 A (Reducer 冲突策略)**: 严格 FATAL raise。使用浅合并 (`shallow_dict_merge`)，若多分支写入同名 Top-level key 产生冲突，直接抛出 FATAL 异常，绝不兼容隐式丢数据的坏行为。
2. **决策 B (actions 契约收紧)**: LOGIC Action 返回的 Keys 必须在 `outputs.schema.json` 中声明。本规则随 Reducer 一同上线，通过 Parser 静态阻断无隔离的黑板覆写。
3. **决策 C (Spec 定名)**: 本次 Spec 命名为 `Graph-Agent State Management Optimization`，且暂不包含 `tasks.md` 的输出。
4. **决策 D (不护短原则)**: 实施期间触发 FATAL 的现役 Skill，必须直接修改 Skill 自身（修改 output Schema 或拆分 Phase）使其合规，绝对禁止在引擎代码中预留 Feature Flag 或兼容老行为的 Backdoor。

## R1. 功能需求 (Functional Requirements)

**R1.1: `BlackboardState.data` 引入严格的 Shallow Reducer**
- **描述**: `packages/graph-agent/src/graph_agent/runtime/state.py:14` 处的 `data: dict` 必须增加 Reducer 注解。如果并发的 Left 和 Right 参数出现同名 Top-level Key 冲突，立刻抛出 `GraphAgentFatalError`（附带 `[F-v21-state-conflict]`）。
- **验收标准**: Fan-out 拓扑下两个分支写入不同 Key 时能成功合并；写入相同 Key 时，执行过程当场崩溃。

**R1.2: Actions 返回 Keys 强制验证 (Parser 静态校验)**
- **描述**: 修改 `packages/graph-agent/src/graph_agent/core/loader.py` 或 AST 模型，对 `phases/*/LOGIC.md` 引用的 Python Action 返回的字典 Key 进行静态溯源（结合类型提示或强制运行时首跑）。任何未在 `outputs.schema.json` 中声明的 Key，触发 `[F-v21-actions-keys]` FATAL 拦截。
- **验收标准**: 在 Action 中 `return {"undeclared_key": "val"}`，被系统无情拦截并报出对应 File 与 Line。

**R1.3: `batch-analysis` 拓扑 Fan-out 复原**
- **描述**: 修改 `skills/batch-analysis/GRAPH.md:8-10`，将当前因缺少 Reducer 妥协出的串行链，一字不改业务代码，仅修改 `depends_on` 改回三路并发。
- **验收标准**: `pytest packages/graph-agent/tests/e2e/` 跑通 Batch-Analysis 全流程，且并行耗时理论上下降，最终装配阶段能读到三路分支的所有数据。

**R1.4: `studio-canvas-v1` 多入连线联调验证 (Engine 侧)**
- **描述**: 在 `packages/graph-agent/tests/core/test_v21_graph_assembly.py` 中新增一个测试夹具。提供一个最小化的 `GRAPH.md`，模拟 Canvas 生成的一个 Phase 被多个 Phase 依赖（多出），以及一个汇聚 Phase 依赖多个 Phase（多入）的拓扑。
- **验收标准**: 能够编译成功，执行并正常触发 `R1.1` 的浅合并行为。

## R2. 非功能需求 (NFR)

- **R2.1: 兼容性**: 针对非并发的单线旧技能执行链路，由于 Reducer 每次只合并一个新字典与先前的合并集，Left/Right 不会产生同轮并发同层碰撞，行为应当与原本 100% 兼容。
- **R2.2: 性能**: Reducer 的性能消耗必须维持在 $O(K)$（其中 $K$ 是被合并的 Top-level Keys 数量）。禁止引入递归搜索和深度比对逻辑。
- **R2.3: 可观测性**: 当由于并发执行命中同 Key 而引发 FATAL (R1.1) 时，Error 信息必须包含具体的 Key 名称以及触发冲突的 Phase IDs 提示。

## R3. 验收标准全集

- **R3.1 (规则真能 catch 违规)**: 故意构造的 fan-out 冲突 fixture, reducer 抛 `[F-v21-state-conflict]` FATAL 含 key + 冲突 branch ids; 故意构造 actions 返回 undeclared key 的 fake skill, parser AST 阶段抛 `[F-v21-actions-keys]` FATAL 含 file:line.
- **R3.2 (reference 改对)**: `batch-analysis` 改成 fan-out 对的形态后, 装配产出多入 edge + 运行时三路并发写各自 namespace 后正确合并 (装配 + reducer 行为对, **不强求业务级输出语义正确**).
- **R3.3 (反例 corpus 行为预期)**: 其他现役 skill 在新契约下触发 FATAL 是**预期行为**, 这些 skill **不强求修复**; `tests/e2e/test_v21_all_skills_smoke.py` **可能因 FATAL 拦截出现失败用例**, 这些失败本身是验收的一部分 (xfail 标 + 备注 "原型阶段 broken skill, 反例 corpus").

## R4. 范围外 (Non-goals)

- **Deep Merge (深合并)**: 坚决不做深合并，仅处理浅层；嵌套结构的深坑不入。
- **前端 Canvas 改动**: 本次优化全在 Backend/Engine。前端代码按计划不动。
- **LWW 兼容模式**: **绝无**容忍遗留隐式覆盖行为的 "Loose Mode" Feature Flag。
- **让所有现役 V2.1 skill 在新契约下都能跑**: 按原型阶段哲学，失败 skill 是错例 corpus，不强求修复。
- **skill 大规模迁移 / 适配工程**: 本 spec 只交付 reducer + actions 静态校验 + 一个 reference skill (batch-analysis fan-out 复原)，其他 skill 改对留 V2.x 渐进迁。