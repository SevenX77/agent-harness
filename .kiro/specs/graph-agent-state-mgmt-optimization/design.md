# Graph-Agent State Management Optimization — Design

**Spec**: graph-agent-state-mgmt-optimization
**Status**: Design (Kiro Step 3/3)
**Date**: 2026-05-16
**Author**: a2 (Gemini, resident architect)
**Base**: V2.1 Hard Cutover commit `a53e72c` (PR #45 merged 2026-05-16)

## 1. 整体架构变更概览

本次更新不触及 LangGraph 底层的状态机运转模型，而是通过显式的 Reducer 注入与 Parser 的静态阻截，在不牺牲单线性能的前提下，确保所有写入全局字典 `BlackboardState.data` 的数据都不会在并发（Fan-out）阶段出现覆盖或脏读。

## 2. R1.1 实施契约 (The Reducer)

- **涉及文件**: `packages/graph-agent/src/graph_agent/runtime/state.py`
- **代码重构**:
  ```python
  from typing import Annotated, Any, TypedDict
  from langchain_core.messages import AnyMessage
  from langgraph.graph.message import add_messages
  from graph_agent.core.exceptions import GraphAgentFatalError

  def shallow_dict_merge(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
      """Merge dictionaries shallowly, raising FATAL on key conflicts.
      
      Time Complexity: O(K) where K is number of top-level keys in right.
      Raises:
          GraphAgentFatalError: If left and right share any top-level key.
      """
      if not left: return dict(right or {})
      if not right: return dict(left)
      
      left_dict = dict(left)
      for key, value in right.items():
          if key in left_dict:
              raise GraphAgentFatalError(
                  f"[F-v21-state-conflict] data key {key!r} written by multiple branches: "
                  f"{left_dict[key]!r} vs {value!r}. Use phase_id for namespace isolation."
              )
          left_dict[key] = value
      return left_dict

  class BlackboardState(TypedDict, total=False):
      """Shared LangGraph blackboard state for V2.1 skills."""
      data: Annotated[dict[str, Any], shallow_dict_merge]
      flow: dict[str, Any]
      messages: Annotated[list[AnyMessage], add_messages]
      run_id: str | None
  ```

## 3. R1.2 Actions 契约与 Parser 静态校验

- **涉及文件**: 
  - `packages/graph-agent/src/graph_agent/core/actions.py`
  - `packages/graph-agent/src/graph_agent/core/loader.py`
- **校验逻辑**:
  - `loader.py` 在加载某个 Skill 时，提取 `outputs.schema.json` 中声明的 properties (即 Keys)。
  - 在 `graph_assembler.py:79` (`_build_logic_node` 闭包) 包装 Action 的返回逻辑，加入运行时的返回 Key 验证（因为 Python 缺乏完美的静态字典返回推导）。
  ```python
  # In graph_assembler.py _logic_node
  result = action(ctx)
  if isinstance(result, dict):
      for key in result:
          if key not in output_schema_keys:
              raise GraphAgentFatalError(f"[F-v21-actions-keys] Action returned undeclared key {key!r}. Must be declared in outputs.schema.json.")
      data.update(result)
  ```

## 4. R1.3 `batch-analysis` GRAPH.md Diff

- **涉及文件**: `skills/batch-analysis/GRAPH.md`
- **变更 (Diff)**:
  ```diff
  --- a/skills/batch-analysis/GRAPH.md
  +++ b/skills/batch-analysis/GRAPH.md
  @@ -6,6 +6,6 @@
   ---
   <input src="io/inputs.json" />
   <output src="io/outputs.json" />
   <phase id="prepare" src="phases/prepare" depends_on="" />
   <phase id="entity_and_characters" src="phases/entity_and_characters" depends_on="prepare" />
  -<phase id="parallel_analysis" src="phases/parallel_analysis" depends_on="entity_and_characters" />
  -<phase id="continuity" src="phases/continuity" depends_on="parallel_analysis" />
  -<phase id="assemble" src="phases/assemble" depends_on="continuity" />
  +<phase id="parallel_analysis" src="phases/parallel_analysis" depends_on="prepare" />
  +<phase id="continuity" src="phases/continuity" depends_on="prepare" />
  +<phase id="assemble" src="phases/assemble" depends_on="entity_and_characters, parallel_analysis, continuity" />
  ```

- **验收标准 (跟 R3.2 对齐)**:
  - batch-analysis 复原 fan-out 后, **装配测试**通过 (LangGraph 产出 `entity_and_characters` / `parallel_analysis` / `continuity` 三路并入 `assemble` 的多入 edge)
  - **reducer 三路合并**通过 (三 phase 各自写 `data[phase_id]` namespace, 不触发 `[F-v21-state-conflict]`)
  - **不强求** `pytest skills/batch-analysis e2e` 业务级输出正确 (那是后续 V2.x 业务迭代, 不在本 spec)

## 5. R1.4 Canvas 联调测试设计

- **测试文件**: `packages/graph-agent/tests/core/test_v21_graph_assembly_fanout.py`
- **假测试物料 (Fake Skill Root)**:
  在 `tests/fixtures/fake_canvas_fanout/GRAPH.md` 中构建如下结构:
  ```markdown
  <phase id="start" src="..." depends_on="" />
  <phase id="branch_a" src="..." depends_on="start" />
  <phase id="branch_b" src="..." depends_on="start" />
  <phase id="merge" src="..." depends_on="branch_a, branch_b" />
  ```
- **断言逻辑**:
  1. `branch_a` 返回 `{"a_out": 1}`, `branch_b` 返回 `{"b_out": 2}`。
  2. 调用执行直至完毕，断言 `BlackboardState.data` 包含 `{"a_out": 1, "b_out": 2}` 且未抛错。
  3. 修改 `branch_b` 返回 `{"a_out": 2}`，断言抛出带有 `[F-v21-state-conflict]` 字样的 `GraphAgentFatalError`。

## 6. FATAL Namespace 新增

- `[F-v21-state-conflict]`: 多分支向 `data` 写入重叠 Key 时触发。
- `[F-v21-actions-keys]`: LOGIC 节点返回了未在 `outputs.schema.json` 声明的属性名。

## 7. 实施 Phase 拆分与估时

- **Phase A**: Reducer 函数的编写、单测与 `state.py` 注入。（工时估算：S）
- **Phase B**: Actions AST 静态校验 + parser 改动。（工时估算：M）
- **Phase C**: Canvas fanout 测试 + reducer/actions FATAL fixture 测试 (R3.1 验收)。（工时估算：M）
- **Phase D**: **batch-analysis fan-out 复原 (single reference)** — 只需 GRAPH.md depends_on diff + 跑装配测试 + 运行时三路合并正确，**不修其他 skill**。（工时估算：S）

## 8. 现有 skill 在新契约下的状态分类 (按原型哲学，不强求修)

1. **`reference` (改对作 V2.2 真源)**:
   - `batch-analysis` — R1.3 复原 fan-out 三路 + assemble 多入 (GRAPH.md only, 零 Python 改动)，是 reducer 行为的端到端 demo。

2. **`naturally-compliant` (天然合规, 单线 / 纯 SKILL ReAct, 不触发新 FATAL)**:
   - `global-synthesis` — `phases/scene_assembly/actions/build_scene_stream.py:24` 写入的 `unified_event_stream` 等已在 `io/outputs.json` 声明，无未声明覆盖。
   - `hello-world` — 单 phase SKILL ReAct，无 LOGIC action，无 `data.update`。
   - `producer` — 纯 SKILL ReAct 接管，无 LOGIC action。
   - `product-manual` — 无 Python action。
   - `examples/subgraph-sample/story-deconstruction` — 全部走 `SUBGRAPH` 委派，无 Python action。

3. **`negative-corpus` (反例, 触发新 FATAL, 留着不修)**:
   - `text-segmentation` — 触发 `[F-v21-actions-keys]`。`phases/setup/actions/prepare_chapter.py:16` 通过 `context.update(...)` 注入了 `chapter_lines` 等未在 `io/outputs.schema.json` 声明的 keys。
   - `event-extraction` — 触发 `[F-v21-actions-keys]`。`phases/setup/actions/format_segments_for_prompt.py:13` 注入了 `formatted_paragraphs` 等未在 Schema 声明的 keys。

4. **`pending-migration` (复杂未决, V2.x 后续 spec 处理)**:
   - (暂无此分类)