# Graph-Agent State Management Optimization — Research

**Spec**: graph-agent-state-mgmt-optimization
**Status**: Research (Kiro Step 2/3)
**Date**: 2026-05-16
**Author**: a2 (Gemini, resident architect)

## 1. 现状基线

- **代码基准**: 基于 `a53e72c` (V2.1 Hard Cutover, PR #45)。
- **黑板状态 (BlackboardState)**: 位于 `packages/graph-agent/src/graph_agent/runtime/state.py:14`。目前包含四项字段 `data`, `flow`, `messages`, `run_id`。其中 `data` 为纯 `dict[str, Any]`，在 LangGraph 的处理机制中，**无 Reducer 等同于 Last-Write-Wins (LWW)**，多分支写入不同的 Keys 最终会被最后一个写入的分支整体覆盖丢弃。
- **并行反例 (Batch-Analysis)**: 为了回避上述丢数据的问题，实施者在 `skills/batch-analysis/GRAPH.md` 将本该并发的阶段（实体分析、连续性分析等）改成了 `prepare → entity_and_characters → parallel_analysis → continuity` 的纯串行链。
- **Canvas-v1 联调**: UI 侧 (P1-1 / P2-2) 在设计多入多出连线时，是以 `depends_on` 属性作为图编排的唯一真相 (Single Source of Truth)。Engine 层支持多分支后，整个模型方才真正实现端到端的一致性。

## 2. 设计决策 (Axiom 延续 / Amendment 新增)

- **Axiom 4 延续 (Global Blackboard)**: 维持全局统一的 LangGraph State 字典设计，不引入多级私有黑板。
- **Amendment #11 (新)**: `BlackboardState.data` 必须显式声明为一个支持 Shallow Dictionary Merge (浅层合并) 的类型，并且各阶段更新需由 `phase_id` Namespace 严格隔离。出现 Top-level key 碰撞时直接 FATAL (`[F-v21-state-conflict]`)。
- **Amendment #12 (新)**: `LOGIC.md` 引用的 Python Action 如果操作 `data`，其返回的 Top-level Keys **必须**在当前技能的 `outputs.schema.json` 中被完整声明。否则，触发编译时或运行时的静态阻断 (`[F-v21-actions-keys]`)。

## 3. 备选方案对比 (Reducer 设计)

针对并发数据合并，主要存在三种方案：
1. **Shallow Merge (Right-Wins)**: 浅层合并 `{**left, **right}`，Key 冲突时后写覆盖前写。
    - *利*: 简单、性能极高。
    - *弊*: 虽然防止了整词典替换，但同 Key 冲突依然会默默丢失数据，违背"不兼容坏事"的原则。
2. **Deep Merge**: 递归遍历字典和列表深入合并。
    - *利*: 最大程度保留数据。
    - *弊*: 性能存在深渊陷阱，极容易掩盖开发者不严谨的 Namespace 设计，诱发脏数据漂移。
3. **Shallow Merge w/ FATAL Raise (主控拍板决议)**: 浅合并，如果 Left 和 Right 的 Keys 出现交集，直接崩溃报错。
    - *利*: **强迫降维打击**。用极其严厉的手段倒逼业务线在 `outputs.schema.json` 阶段就把 Namespace 设计好。单线流转由于串行调用天然不存在左右字典交并集问题，所以 100% 兼容。
    - *弊*: 迁移阵痛期可能会有大量失败拦截，引发业务停摆报警。

**结论**: 采纳 **方案 3** (A 决策)。宁愿当场崩溃，也不要带着污染的上下文执行。

## 4. 风险盘点与应急预案

- **停摆风暴风险**: 由于采用了严格的 FATAL 策略，部分习惯了 `data.update({"summary":...})` 的通用 Action 可能在多路并发时引发连锁 Crash。
- **不护短的应急措施 (D 决策)**: 坚决不设 "宽松模式"，不留 Feature Flag 或 `rollback to V2.1` 回退阀门。唯一解法：修改崩溃的 Skill 本身，迫使其将变量隔离入 `data["phase_a_summary"]`。
- **性能评估**: $O(K)$ 复杂度。因采用浅合并，对于日常 $<50$ 个 Top-level key 的技能来说，合并操作耗时接近物理极限 ($<1ms$)，远低于网络 IO。

## 5. 测试矩阵

- **Unit 测试**: 测试 Reducer 函数本身对于无交集字典的正确合并，以及针对有交集字典严格引发 `GraphAgentFatalError` 的行为。
- **Assembly 测试**: `test_v21_graph_assembly.py` 新增对 Fan-out 拓扑装配出来的 LangGraph Edge 结构的校验。
- **E2E 测试**:
    - **`skills/batch-analysis`**: 真实执行由于恢复 Fan-out 带来的并发操作。
    - **Canvas 联调用例**: 构建一个 `fake-canvas-GRAPH.md`，使用纯 Python Action 并行写入不同字段，验证最终输出符合预期且未抛错。

## 6. 关键 file:line 取证清单

- **`packages/graph-agent/src/graph_agent/runtime/state.py:14`**: `data: dict` 需要增加注解。
- **`packages/graph-agent/src/graph_agent/core/graph_assembler.py:79`**: 当前 Action 的无脑 `data.update(result)`。
- **`packages/graph-agent/src/graph_agent/core/graph_assembler.py:160`**: `finish_task` 现存的合规 Namespace (`data[phase_id] = result.get("data", {})`)。