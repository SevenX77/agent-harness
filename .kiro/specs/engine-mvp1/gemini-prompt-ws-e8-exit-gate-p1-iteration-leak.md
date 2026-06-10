---
ws_id: WS-E8-exit-gate
artifact: gemini-prompt
status: review-fix-needed
created: 2026-06-09
related_task: .kiro/specs/engine-mvp1/task-ws-e8-exit-gate.md
requirements: .kiro/specs/engine-mvp1/requirements-ws-e8-exit-gate.md
review_finding: P1 ExitControl iteration budget leaks across reused graph invocations
---

# Gemini Prompt - WS-E8 P1 Iteration Leak Fix

```text
你是 /Users/sevenx/Documents/coding/agent-harness/.worktrees/engine-mvp1-ws-e8-exit-gate 工作区的 engine 模块实现者。当前 WS-E8 显式接线方向已通过主体复审，但 Codex 最终复审发现一个 P1 运行时状态问题：ExitControlMiddleware 把迭代预算计数放在中间件实例字段 `_iteration` 上，导致同一个 compiled graph 被复用时，新 run / 新 thread_id 会继承上一次调用的预算消耗。

请按严格 TDD 修复：先补 RED，确认失败形态正确，再做最小 GREEN。不要先改生产代码。

工作区：
/Users/sevenx/Documents/coding/agent-harness/.worktrees/engine-mvp1-ws-e8-exit-gate

必须先读：
- .kiro/specs/engine-mvp1/requirements-ws-e8-exit-gate.md
- .kiro/specs/engine-mvp1/task-ws-e8-exit-gate.md
- packages/graph-agent/src/graph_agent/middleware/exit_control.py
- packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py
- packages/graph-agent/src/graph_agent/middleware/factory.py
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py

当前已知通过：
- uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py -p no:cacheprovider -q
  当前主体应为 5 passed。

Codex 复审发现的 P1：
- packages/graph-agent/src/graph_agent/middleware/exit_control.py 当前在 `__init__` 中保存 `self._iteration = 0`。
- `before_model` 每次调用都累加这个实例字段。
- `after_agent` 用这个实例字段判断是否达到 `max_iterations`。
- 编译后的 graph 和 middleware 实例可能被复用，因此第二次 `graph.invoke(...)` 会继承第一次的 `_iteration`。

只读复现实验现象：
1. 构造一个 max_iterations=2 且声明 finish_task 的 AGENT skill。
2. 同一个 compiled graph 第一次 invoke：模型调用 finish_task，成功结束。
3. 同一个 graph 第二次 invoke，使用新的 thread_id：模型不调用任何 tool。
4. 正确行为：第二次 run 应该拿到完整预算，模型应被调用 2 次后才因无合格 finish_task marker 耗尽失败。
5. 当前错误行为：第二次 run 只调用模型 1 次就失败，因为继承了第一次成功调用留下的 `_iteration=1`。

你必须先新增 RED 测试：
- 文件：packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py
- 建议测试名：
  `test_exit_gate_iteration_budget_is_scoped_to_each_graph_invoke`
- 测试应使用真实 `compile_skill + assemble_graph + graph.invoke` 路径。
- 测试应复用同一个 `graph` 实例连续调用两次：
  - 第一次输入 thread_id="run-1"，模型返回合格 finish_task，断言成功输出可见。
  - 第二次输入 thread_id="run-2"，模型不返回 tool_calls / 不返回 finish_task。
  - 第二次应抛出或产生明确失败，且模型第二次 run 应拿到完整 max_iterations 预算。
- 一个简单可观测断言：
  - 模型总调用次数应为 3：第一次成功 1 次 + 第二次耗尽 2 次。
  - 当前错误实现通常只会得到总调用次数 2，因此 RED 会失败在预算泄漏。
- 测试还应确认失败信息包含 `[F-v3-agent-exit-control-failed]` 或等价已注册 exit-control fatal 语义。

RED 命令：
uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py -p no:cacheprovider -q

修复要求：
1. 不得再把迭代预算作为裸中间件实例字段跨 run 累加。
2. 预算计数必须限定在单次 graph invoke / thread / phase 的运行作用域内。
3. 可以从当前 run 的 state/message history 推导迭代数；也可以把计数写入并读取 graph state 中的 phase-scoped 数据；如确实需要实例缓存，必须按 thread/run 明确隔离并在新 run 起点重置。优先选择状态驱动或可解释的最小方案。
4. 不能引入 `sys._getframe`、`inspect.stack`、测试名豁免、import-time monkeypatch，不能用调用栈猜测。
5. 不得削弱既有 5 条 WS-E8 RED 断言。
6. 不得恢复 CognitiveFlow 直接 `goto=END` 绕过 after_agent gate。
7. 不得扩大到 checkpoint/state/runner/result/callbacks/studio/gateway 等非本问题范围。

允许修改：
- packages/graph-agent/src/graph_agent/middleware/exit_control.py
- packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py
- 如 Ruff import/order 需要，可最小整理相关测试 import。

原则上不需要修改：
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- packages/graph-agent/src/graph_agent/middleware/factory.py
- packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py
- packages/graph-agent/src/graph_agent/middleware/__init__.py
- packages/graph-agent/src/graph_agent/core/error_registry.py

如果你认为必须修改上述“原则上不需要修改”的文件，先停下汇报原因，等待复审批准。

禁止修改：
- packages/graph-agent/src/graph_agent/core/checkpointer.py
- packages/graph-agent/src/graph_agent/core/state.py
- packages/graph-agent/src/graph_agent/core/runner.py
- packages/graph-agent/src/graph_agent/core/exceptions.py
- packages/graph-agent/src/graph_agent/core/result.py
- packages/graph-agent/src/graph_agent/callbacks/events.py
- packages/graph-agent/src/graph_agent/callbacks/emit.py
- packages/graph-agent/src/graph_agent/middleware/tracing.py
- packages/graph-agent/src/graph_agent/middleware/tool_error.py
- packages/graph-agent/src/graph_agent/middleware/loop_detection.py
- apps/studio/**
- packages/graph-agent-gateway/**
- docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/baseline.md

验证命令：
1. 新增 RED 后先确认失败：
   uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py -p no:cacheprovider -q
2. GREEN 后复跑：
   uv run pytest packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py -p no:cacheprovider -q
3. 复跑回归：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_gamma0_contract_tdd.py -q
   uv run pytest packages/graph-agent/tests/core/test_gamma2_child_graph_isolation.py packages/graph-agent/tests/runtime/test_gamma2_state_io_red.py -q
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q
   uv run pytest packages/graph-agent/tests/middleware/test_chain_topology.py packages/graph-agent/tests/middleware/test_beta_cognitive_flow_schema_gate.py packages/graph-agent/tests/core/test_nudge_injector.py -q
4. 目标文件 Ruff：
   uv run ruff check packages/graph-agent/src/graph_agent/middleware/exit_control.py packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py
5. Scope / hygiene：
   git diff --check -- packages/graph-agent/src/graph_agent/middleware/exit_control.py packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py
   git diff -- packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/core/exceptions.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py
   git status --short -- apps/studio packages/graph-agent-gateway

回报格式：
1. 新增 RED 测试名、RED 失败摘要。
2. 修复方案：计数现在如何限定在单次 run/thread/phase，不再跨 graph.invoke 泄漏。
3. 修改文件列表。
4. 每条验证命令结果。
5. 明确说明没有使用栈帧、测试名豁免、全局 monkeypatch。
6. 明确说明 baseline.md 未修改，forbidden files / apps/studio / gateway 未被触碰。
```
