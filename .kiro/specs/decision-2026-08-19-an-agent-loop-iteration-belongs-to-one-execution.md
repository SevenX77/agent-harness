# 决议：一次 agent-loop 迭代属于相位的某一次执行

- 日期：2026-08-19
- 状态：已裁决，随本 PR 落地
- 模块：engine（`packages/graph-agent`）

## 决策

`AgentLoopIterationEvent.iteration` 报告的是**这一次相位执行**内部花掉的模型轮次，
从 1 开始，每一次执行各数各的。batch 的每个条目、loop 的每一轮、resume 的每一次，
都是各自独立的一次执行，因此各自从 1 开始数。

"哪一次执行"这件事在引擎里**只有一个定义**，写在
`middleware/invocation_scope.py` 的 `agent_invocation_key()`：装配器盖在
`agent_graph.invoke` 配置上的 `agent_invocation_id`，加上 `thread_id`。凡是中间件
需要按"这一次执行"隔离的状态（轮次计数、nudge 预算），一律用它作键。

## 事实与证据

**契约原文（引擎自己写的）**——`packages/graph-agent/src/graph_agent/callbacks/events.py:56-62`，
`PhaseStartEvent.phase_execution_id` 的字段注释：

> Which execution of this phase — an outer iterate/batch loop runs the same
> phase several times, and each run is its own segment. Distinct from
> `AgentLoopIterationEvent.iteration`, which counts model turns INSIDE one
> execution (decision 2026-08-15 edge-as-run-segment, D2).

`AgentLoopIterationEvent` 自己的类注释（同文件 `:613-622`）说明它为什么存在：

> Gives Studio a per-iteration anchor so subsequent LLMCall / ToolCall events
> emitted during that iteration can be grouped, rather than just relying on
> timestamp order (which breaks once parallel_map sub-runs interleave events).

**现场（真跑，不是推断）**——run `2026-08-19T01-56-15_d0733362`，skill
`story-deconstruction-v3-lab`。`event-extraction` 子图的 `review` 相位按章节
batch 跑 2 个条目，两次执行在 `trace.jsonl` 里的 `agent_loop_iteration` 编号是：

| 时刻 | phase_execution_id | iteration |
|---|---|---|
| 08:59:24.361 | 5a39ce5b74ad | 1 |
| 08:59:29.921 | 5a39ce5b74ad | 2 |
| 08:59:36.044 | 5a39ce5b74ad | 3 |
| 09:00:11.412 | 162fc326a6cc | **4** |
| 09:00:17.762 | 162fc326a6cc | 5 |
| 09:00:25.891 | 162fc326a6cc | 6 |
| 09:01:04.101 | 162fc326a6cc | 7 |
| 09:01:24.006 | 162fc326a6cc | 8 |

第二次执行的第一个模型轮次报成了 4。同一份 trace 里 `segment` / 文本分段的
`review` / `aggregate` 三个相位是同样的形状（1,2 之后接 3,4）。事件恰好在它被设计
来解决的那个场景——两个条目并发、事件交错——上给不出正确的锚点。

**根因（代码，不是印象）**——`middleware/execution_control.py` 修复前把轮次记在
实例属性上：

```python
self._iteration = 0
...
def before_model(self, state, runtime):
    self._iteration += 1
    self._emit_iteration_event()
```

而 `build_middleware_chain(...)` 在**装配期**、按相位节点调用一次
（`core/graph_assembler.py:2152`），装好的图随后被每个 batch 条目 / loop 轮次 /
resume 重新 invoke 一遍。于是一个实例的计数器横跨了多次执行。

同一条中间件链里的 `ExitControlMiddleware` **早就解过这个问题**：它的迭代预算和
nudge 预算都按 `agent_invocation_id` 分桶，注释里还留着现场证据
（run `2026-08-15T10-19-55_df555c19`，"counter 1..8 for chapter 1 then 9 for
chapter 2"）。两个中间件对"哪一次执行"给了两个答案，其中一个是对的——这正是把
定义收敛到一处的理由。

## 关键设计决定

1. **借的是同一条链里已经验证过的做法，不另发明。** 隔离键沿用
   `ExitControlMiddleware` 已在用的 `agent_invocation_id`：它由装配器盖在
   invoke 配置上，和 `max_iterations` 走同一条通道，因此**已被证明**能到达中间件
   钩子。放弃的替代项是 `checkpoint_ns`——LangGraph 交给钩子的是**每钩子**命名
   空间（实测形如 `ExitControlMiddleware.before_model:<uuid>`，每次调用一个新
   uuid），拿它作键会每轮重置。
2. **一个规则一处定义。** 新增 `middleware/invocation_scope.py`，
   `ExitControlMiddleware` 与 `ExecutionControlMiddleware` 同用
   `agent_invocation_key()`。不这么做的代价这次已经付过了：规则复制了一份，只有
   一份被修好，另一份继续错了三个月。
3. **不在图里跑时也有确定答案。** 中间件钩子被直接调用（单元测试就是这么调的）
   时 `get_config()` 抛 `RuntimeError`。这不是坏状态：图外**就是**只有一次执行，
   所以返回常量键 `NO_RUNNABLE_CONTEXT`，语义等价于原来的"每实例计数"。这里的
   `try/except` 捕的是"我不在图里"这个可判定事实，不是把错误吞掉。
4. **本次不动事件字段。** 让 `AgentLoopIterationEvent` 也带上
   `phase_execution_id`（这样交错的两次执行在消费端才能真正分开）是**另一件事**，
   需要先坐实该 id 在中间件钩子的上下文里可达。本 PR 只修"计数横跨执行"，不夹带。

## 验收判据

- RED：`packages/graph-agent/tests/core/test_agent_loop_iteration_is_per_execution.py`
  在修复前给出 `[1, 2, 3, 4]`（现场形状的最小复现），修复后给出每个条目各自的
  `1, 2`。
- 门禁：engine 全套 + gateway 全套 + studio backend 全套 + ruff + mypy --strict 全绿。
