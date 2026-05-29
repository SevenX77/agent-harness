# Round 29 Research - C901 Complexity Gate

## §1 现状调研
经 ruff 分析与人工核对，当前引擎核心保留了 13 个 C901 violation 函数：
1. `execute` (packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:80) - 复杂度 44。核心状态机流转。
2. `run` (packages/graph-agent/src/graph_agent/core/harness.py:454) - 复杂度 25。Harness 顶层启动。
3. `_wrap_tool_for_langchain` (packages/graph-agent/src/graph_agent/core/tool_wrapper.py:82) - 复杂度 24。兼容层包装。
4. `_run_skill_dict` (packages/graph-agent/src/graph_agent/core/runner.py:233) - 复杂度 24。执行流控制。
5. `legacy_context_from_state` (packages/graph-agent/src/graph_agent/core/state.py:167) - 复杂度 21。遗留上下文适配。
6. `_value_for_schema` (packages/graph-agent/src/graph_agent/core/_predict_internal/stub.py:29) - 复杂度 17。Cognitive 模拟。
7. `to_jsonable_dict` (packages/graph-agent/src/graph_agent/callbacks/serialize.py:52) - 复杂度 16。序列化工具。
8. `resolve_skill_resource` (packages/graph-agent/src/graph_agent/core/skill_builder.py:490) - 复杂度 16。资源解析。
9. `on_event` (packages/graph-agent/src/graph_agent/callbacks/base.py:139) - 复杂度 14。事件派发中心。
10. `_build_skill_node` (packages/graph-agent/src/graph_agent/core/graph_assembler.py:259) - 复杂度 14。Graph 节点装配。
11. `resume` (packages/graph-agent/src/graph_agent/core/harness.py:979) - 复杂度 13。状态机恢复。
12. `parse_output_example` (packages/graph-agent/src/graph_agent/tools/dynamic_schema.py:71) - 复杂度 12。工具 Schema 解析。
13. `_violation_for_call` (packages/graph-agent/src/graph_agent/core/purity.py:130) - 复杂度 11。AST 规则检查。

## §2 历史决策
通过历史记录调研，在 P0-2 系列阶段（如之前完成的 PR α Gateway分离 / PR β Middleware重构 / PR γ2 State/IO隔离等，详见 `00-PROGRESS-STATUS.md`），重点聚焦底层框架分层隔离和接口契约收敛，并未强行开启 McCabe 门禁。这种阶段性取舍将复杂度债遗留到了本轮（Round 29）。

## §3 PR-8 实际状态 (重要事实)
经 grep 确认，历史 PR-8 实际状态存在误判。虽然 `65d3899` merge commit 删除了 `_sync_tool_state` 等部分 transitional layer，但是 **`legacy_context_from_state` (state.py:167) 和 `_wrap_tool_for_langchain` (tool_wrapper.py:82) 均依然存在于代码中**。
因此 `design.md` 中指出的“等 PR-8 优先 ship 就不需重构”是严重的 Hallucination，我们不能依赖并不彻底的 PR-8，必须在本轮硬重构这两个残余的兼容函数。

## §4 业内对标
业界顶尖的 Agentic Workflow / Orchestration 框架（如 LangGraph, Temporal, Prefect）内部核心执行引擎对圈复杂度控制极为严苛。通常均遵循 `max-complexity=10` 的红线。
复杂的分支逻辑（`C > 10`）不仅大幅降低了状态迁移的可读性，更严重破坏了 Workflow 的 Deterministic Replay 能力，不利于分布式 Tracing。因此当前对齐 max=10 标准是合理且必要的。

## §5 13 函数测试 coverage 数据
这 13 个函数的覆盖率情况处于极端两极分化状态：
- **4 个高覆盖**：`run` (832 次命中), `execute` (81 次), `on_event` (28 次), `resume` (21 次)。这 4 个核心调度函数具备完善保护网。
- **1 个低覆盖**：`_wrap_tool_for_langchain` (仅 2 次命中)。
- **8 个零覆盖**：`_run_skill_dict`, `legacy_context_from_state`, `_value_for_schema`, `to_jsonable_dict`, `resolve_skill_resource`, `_build_skill_node`, `parse_output_example`, `_violation_for_call` 完全没有任何测试覆盖。
对于这 9 个（8零+1低）函数，重构前必须按 Test-first 原则补充回归测试。
