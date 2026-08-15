# 决议:`depends_on` 多前驱 = 汇合闸,不是多条触发线

- 日期:2026-08-15
- 范围:engine(`packages/graph-agent`)
- 状态:已实施
- 相关:`decision-2026-08-15-engine-parallel-fanout-state-channels.md`(同一批并行支持修复的第 5 项)

## 1. 问题

`GRAPH.md` 里写 `<phase depends_on="a,b,c">join</phase>`,语义是**汇合**:`join` 在
`a`、`b`、`c` 全部产出之后跑**一次**。

引擎过去把它翻译成三条各自独立的边:

```python
for dep in graph_deps:
    builder.add_edge(dep, phase_id)
```

LangGraph 里一条普通边是**触发线**,不是**栅栏**。目标节点订阅了三个通道,任何一个
通道被写入就会把它排进下一个超步。于是 `join` 的真实行为是:

1. 哪个前驱**最先**提交,`join` 就在那之后立刻跑一次——此时另外两个前驱的输出还
   不在黑板上;
2. 后面每个前驱落地时,`join` **再跑一次**。

## 2. 为什么一直没被发现

只有当所有前驱**恰好在同一个超步结束**时,这两种写法才等价。最常见的图形——从一个
节点扇出、下一层立刻扇入的菱形——正好满足这个条件:三个前驱同层完成,`join` 被同一
个超步的三次写入触发一次,黑板也是齐的。

缺陷只在**前驱深度不齐**时暴露。story-deconstruction 的 `batch-analysis` 子图就是这个
形状(`subgraph/story-analysis/subgraph/batch-analysis/GRAPH.md`):

```
<phase depends_on="entity_and_characters">tension</phase>      ← 深度 1
... system / prop / arc / foreshadow / spatiotemporal          ← 深度 1
<phase depends_on="entity_and_characters">format_continuity</phase>  ← 深度 1
<phase depends_on="format_continuity">continuity</phase>       ← 深度 2
<phase depends_on="tension,...,continuity" output>assemble</phase>
```

六个维度相位在深度 1 完成,`continuity` 要到深度 2。实测执行序(operator 探针,
`predict` 路径)决定性地印证了这一点:

```
[IN ] assemble        ← assemble 起跑
[IN ] continuity      ← continuity 同一超步才起跑
[OUT] continuity
RAISED: phase required input fields missing from blackboard: continuity_warnings
```

`assemble` 与它自己的前驱 `continuity` **同时**起跑,读不到 `continuity_warnings`,
致命退出。

## 3. 依据

LangGraph 自己把两种形式的语义写在 `StateGraph.add_edge` 的文档里
(`langgraph/graph/state.py:915-920`):

> When a single start node is provided, the graph will wait for that node to complete
> before executing the end node. When multiple start nodes are provided,
> the graph will wait for ALL of the start nodes to complete before executing the end node.

实现上也是两条不同的路:单个起点进 `self.edges`(`:953`),起点列表进
`self.waiting_edges`(`:966`)。也就是说**栅栏语义本来就有现成表达**,引擎只是没用。

## 4. 决定

多前驱一律用列表形式下边,单前驱保持单边:

```python
if not graph_deps:
    builder.add_edge(START, phase_id)
elif len(graph_deps) == 1:
    builder.add_edge(graph_deps[0], phase_id)
else:
    builder.add_edge(graph_deps, phase_id)   # 栅栏
```

`AssembledGraph.edges` 对外仍然逐条列 `(dep, phase_id)`——它描述的是数据依赖关系,
不是 LangGraph 的内部触发机制,消费方(可视化、拓扑断言)不需要跟着变。

## 5. 关键设计决定

- **不在相位节点里自己补等待逻辑。** 让节点先跑起来、发现前驱缺数据再挂起重排,等于
  在引擎里手写一套调度器,和底层 Pregel 抢 owner。栅栏是编排层的职责,表达在边上。
- **不靠"把图拍平成同深度"绕过。** 那要求 skill 作者手工插空相位来对齐深度,把引擎
  的调度缺陷变成作者的负担,且任何一次改图都可能重新踩中。
- **重复执行也是缺陷,不只是崩溃。** 深度不齐时旧行为会让汇合相位跑 N 次。崩溃只是
  运气好的那一半:如果汇合相位的必填输入恰好在第一次触发时就齐了,它会**静默**地
  多跑几次,在 run 路径上就是多烧几次真 token、后一次结果覆盖前一次。所以验收判据
  同时锁"跑通"和"只跑一次"。

## 6. 验收判据

`packages/graph-agent/tests/core/test_multi_dependency_join.py`,用一个前驱深度不齐的
最小图(`seed → {fast, slow_a} → slow_b`,`join depends_on="fast,slow_b"`):

1. `test_join_waits_for_the_deeper_branch` —— predict 成功,`join` 的输出进入
   最终 context;修复前报 `phase required input fields missing from blackboard:
   slow_b_result`。
2. `test_join_runs_exactly_once` —— `result.phases` 里 `join` 恰好出现 1 次。

外加引擎全量套件不回归。
