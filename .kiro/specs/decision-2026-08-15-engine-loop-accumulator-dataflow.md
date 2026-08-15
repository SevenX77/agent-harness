# 决议:loop 相位向下游提供的是累积器,不是它的 `io.outputs`

- 日期:2026-08-15
- 范围:engine(`packages/graph-agent`)
- 状态:已实施
- 相关:`decision-2026-08-15-engine-multi-dep-join-waits-for-all.md`(同一批并行/循环支持修复的第 6 项)

## 1. 问题

一个 `iterate.mode=loop` 的相位,编译期和运行期对"它给下游留下什么"给出两个互相矛盾
的答案,而作者**没有任何写法能同时满足两边**。

**运行期**(`core/graph_assembler.py:_build_loop_iterate_phase`):每一轮把当前累积值
喂进相位体,从本轮输出里取 `accumulate.from` 合进累积器;所有轮跑完后:

```python
final_payload = {accumulate.var: acc}
return _phase_outputs_delta({phase_id: final_payload})
```

也就是说,落到黑板上的**只有** `accumulate.var` 一个字段。这与设计源一致
(`docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md:48`):

> 后一轮能读到前一轮累积结果;最终只把 `accumulate.var` 写回 blackboard 与
> `phase_outputs[phase_id]`。

同时,`io.outputs` 在 loop 相位上是**每一轮的契约**:相位体每跑一轮都按它校验,而且
必须包含 `accumulate.from`,否则 `_iterate_merge_fatal` 报 `loop iterate output missing
accumulate.from`。

**编译期**(`core/loader.py:_validate_static_dataflow`)则一律把 `io.outputs` 当作
"这个相位提供什么":

```python
available_after[phase_name] = available | set(_schema_property_paths(_phase_output_schema(doc)))
```

两个后果同时成立,构成一个无解的夹角:

| 作者怎么写 `io.outputs` | 编译期 | 运行期 |
|---|---|---|
| 只写每轮产出(不含累积器) | 下游消费累积器 → `[F-v3-graph-dataflow-source-missing]` 编译失败 | 正确 |
| 加上累积器名字 | 通过 | 每一轮输出校验都缺这个字段 → `phase output schema validation failed` |

story-deconstruction 的 `analyze_batches` 两种都撞过:先是第二种(2026-08-15 实测
`phase output schema validation failed: 'analysis_state' is a required property`),
按第二种改掉之后立刻变成第一种(`phase 'finalize' input 'analysis_state' has no root,
upstream, runtime input, or iterator provider`)。

## 2. 决定

编译期的"提供集"改为按相位类型区分,与运行期实际写回黑板的东西一致:

```python
def _phase_blackboard_output_keys(doc: PhaseDocument) -> set[str]:
    iterate = getattr(doc.ast, "iterate", None)
    if getattr(iterate, "mode", None) == "loop":
        accumulate = getattr(iterate, "accumulate", None)
        return {accumulate.var} if accumulate is not None else set()
    return set(_schema_property_paths(_phase_output_schema(doc)))
```

一句话:**loop 相位提供且只提供 `accumulate.var`**;其余相位不变。

## 3. 关键设计决定

- **改编译期去对齐运行期,不是反过来。** 备选是让 loop 相位在结束时把最后一轮的
  `io.outputs` 也写回黑板。否决:那会让"循环的产出"变成"最后一轮的产出",既与设计源
  `baseline.md:48` 冲突,也让批次之间的语义依赖轮次顺序——一个循环的意义就在于累积,
  不在于最后一轮碰巧是什么。
- **不给 `io.outputs` 加一个"哪些字段是累积器"的旁注字段。** 那是把同一件事声明两遍
  (违反 SSOT),而且 `accumulate.var` 已经把它说清楚了。
- **这条修复同时收紧了另一半。** 下游相位如果消费 loop 相位的**每轮**输出字段
  (本例的 `round_result`),从前编译期放行、运行期读不到;现在编译期直接报
  `[F-v3-graph-dataflow-source-missing]`。这不是附带损伤,是同一个错位的另一面。
- **batch 模式不动。** `_phase_batch_payload` 按 `io.outputs` 的键聚合每项结果写回,
  编译期与运行期本来就一致,没有需要修的错位(KISS/YAGNI:没有失败证据就不改)。
- **loop 但没写 `accumulate` 的相位提供空集。** 这个状态已经由
  `_validate_iterate_compile_contracts` 报 `[F-v3-iterate-accumulate-fields-missing]`
  致命错(`loader.py:2117`,且它在 dataflow 校验之前跑、共用同一份 collect-all 诊断
  列表),这里不再重复造一个新错误码。

## 4. 验收判据

`packages/graph-agent/tests/core/test_loop_accumulator_dataflow.py`,一个两相位最小
skill(`crunch` 是 loop、累积器 `tally`、每轮产 `round_result`;`finalize` 在其下游):

1. `test_downstream_may_consume_the_accumulator` —— `finalize` 读 `tally` 必须编译通过;
   修复前报 `phase 'finalize' input 'tally' has no root, upstream, runtime input, or
   iterator provider`。
2. `test_downstream_may_not_consume_a_per_round_output` —— `finalize` 读 `round_result`
   必须编译失败并带 `[F-v3-graph-dataflow-source-missing]`;修复前静默放行。

外加引擎全量套件不回归。
