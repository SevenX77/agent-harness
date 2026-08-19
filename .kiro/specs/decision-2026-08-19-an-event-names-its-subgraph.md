# 决议：一条事件说得出它跑在哪个子图里

- 日期：2026-08-19
- 状态：已裁决（用户 2026-08-19 指示「做」），随本 PR 落地
- 模块：engine（`packages/graph-agent`）+ studio backend（run 报告）

## 决策

`_EventBase` 新增 `subgraph_path: str | None`——发射这条事件的代码所处的
SUBGRAPH 相位链，根起点点号连接（如 `event_timeline.extrac`），根层为 None。
盖章集中在发射漏斗 `_safe_emit_event`：`_build_subgraph_node` 在 invoke 子图
前后用 contextvar 维护当前链，所有 33 类事件一次性获得该身份。
run 报告的节点行改按 `subgraph_path/phase_name` 记账。

## 事实与证据

现场（真跑 `2026-08-19T01-56-15_d0733362`，skill `story-deconstruction-v3-lab`）：
text-segmentation 子图和 event-extraction 子图**各有一个**叫 `review` 的相位。
trace 里 18 条 `phase_start` 的 `phase_name` 只有裸名，报告按裸名聚合——
两个不同节点的 `review` 并成一行（13 次 LLM 调用），event-extraction 的
`setup` 整行消失（并进了 segmentation 的 `setup`）。报告拿不到事件没说的
东西：`run_report._event_node` 只读 `phase_name`/`current_phase`/`to_phase`。

相位重名不是 skill 的命名事故：子图是可复用单元，单元内部用常规名
（setup/review）是正当的。身份必须由引擎随事件带出来。

## 关键设计决定

1. **盖章在发射漏斗，不在每个发射器。** OB6 说"谁干活谁发事件"——本字段不
   转移发射所有权，只是把**环境作用域**（ambient scope）标注上去，与
   `sub_run_id`/`group_key` 由 `parallel_map` 标注同构。发射器有几十个，逐个
   改必然漏；`_safe_emit_event` 是全部生产发射器已经路过的唯一漏斗。
2. **contextvar 而非穿参。** 子图节点 invoke 子图是同步同上下文调用，
   asyncio 任务继承 context 拷贝（batch 条目在子图内仍有正确作用域）；
   `parallel_map` 的线程池子 run 是独立 sub_run（有 `sub_run_id` 标识），
   不经过这条链，边界明确。
3. **只盖未设值（None）的事件。** `parallel_map` 从子上下文转发的事件已带
   子上下文的章，漏斗不覆写。
4. **报告聚合语义保持**：同一节点的多次 iterate 执行仍并一行（W2-33 的
   phase_execution_id 管"第几次执行"，本字段管"哪一个节点"，两轴正交）；
   根层相位与转移行的裸标签不变；子图内的转移行同样带作用域前缀。

## 验收判据

- 引擎测试：双子图同名 `review` 真跑（logic 相位），两条 `phase_start` 的
  `subgraph_path` 分别为 `alpha`/`beta`，根层相位为 None；撤销 src 修复 RED。
- 报告测试：同名两子图两行、iterate 聚合一行、根层裸标签、子图内转移行带
  前缀，四条全绿。
- 门禁：引擎 1584 + backend 1742 + gateway 618 全绿，ruff / mypy ×3 全绿。
