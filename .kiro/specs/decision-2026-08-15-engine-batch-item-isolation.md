# 决议:一个 batch 条目是一次独立的调用,不是同一段对话里的下一轮

- 日期:2026-08-15
- 范围:engine(`core/graph_assembler.py`、`middleware/exit_control.py`)
- 状态:已实施
- 相关:同一天那批引擎缺陷(`decision-2026-08-15-engine-*.md`)。这一条是**第一次真跑**
  才暴露出来的,前面那些全部修完、predict 全绿之后它依然在。

## 1. 现场

真跑 `.workspace/runs/2026-08-15T10-19-55_df555c19`(skill `story-deconstruction-v3-lab`,
DeepSeek V4 Flash,2 章输入)。`segmentation` 子图按 `iterate.mode=batch` 跑 2 个章节。

**症状一 —— 迭代计数器不归零,预算被上一个条目花光:**

```
17:19:59 phase_start  segment            ← 条目 1(第 1 章)
17:19:59 agent_loop_iteration  1
   …4 次 finish_task rejected,planning nudge #1,loop_detected,standard nudge #1…
17:21:53 phase_end    segment  outputs=None      ← 条目 1 失败
17:21:54 phase_start  segment            ← 条目 2(第 2 章)
17:21:54 agent_loop_iteration  9         ← 没有归零
17:23:16 run_ended    crashed
```

```
[F-v3-agent-exit-control-failed] Phase 'segment' failed: nudge budget exhausted
(counts={'planning': 1, 'selfcheck': 0, 'standard': 1, 'total': 2}, max_nudges=1)
after 8 iteration(s) without a valid finish_task marker.
```

**症状二(更严重)—— 条目 2 交出条目 1 的答案,而且被正常接受:**

```
17:22:17 phase_end segment(条目 2)
  in.chapter_number            = 2                    ← 输入对
  in.chapter_with_line_numbers = "   1| 夜幕降临…"      ← 第 2 章原文,对
  ctx.phase_outputs.segment.parsed_segments[0].description =
    "主角在现实世界中与张超会合、驱车前往露营地…获得一枚旧铜镜"   ← 第 1 章剧情
```

下游 `review` 拿这份「标题第 2 章、内容第 1 章」的摘要去对照第 2 章原文。
**全程没有一处红灯。** 症状一会报错,症状二不会——它只是把错数据写下去。

污染层次可以钉死:那句「# 第 2 章分段总览」是 `segment/validator.py` 用
`f"# 第{chapter_number}章分段总览"` 渲染的,`chapter_number` 取到的是 2(正确),
正文来自 `parsed_segments`(第 1 章的)。所以串台发生在**模型提交的那一层**。

## 2. 根因:批处理条目没有身份

相位级 batch 的执行路径是
`_wrap_phase_runtime_node` → `_build_iterate_wrapped_phase` → `_build_batch_iterate_phase`
→ `_phase_batch_payload` → `_phase_batch_runner`。而 `_phase_batch_runner` 原本这样调子节点:

```python
    async def _invoke_child(index: int, child_state: WorkflowState) -> Any:
        return await _run_with_branch_index_async(          # ← 只设 branch index
            index,
            lambda: asyncio.to_thread(node, child_state),
        )
```

`_run_with_branch_index_async` 只设 `active_branch_index_var`——那个变量只用来给事件打标签
(`graph_assembler.py:802`)。它**没有**设 `active_outer_ns`。

对比它的图级孪生兄弟 `_graph_batch_runner`,同一个文件里:

```python
        return await _run_with_iteration_context_async(     # ← 两个都设
            index,
            _iteration_namespace(index),
            lambda: asyncio.to_thread(graph.invoke, child_state, config=_iteration_config(config, index), ...),
        )
```

于是在相位级 batch 上,`active_outer_ns` 始终为空,而 `_skill_node` 又把命名空间写死:

```python
        thread_id = inner_configurable.get("thread_id") or state["flow"].thread_id or "default"
        inner_configurable["checkpoint_ns"] = f"agent:{phase_id}"
```

`thread_id` 是**整次 run 的常量**(`runner.py:2109` 一次性设为 `run_id`)。
所以每个条目递给 agent 图的 `(thread_id, checkpoint_ns)` **完全相同**。两个消费者因此塌缩:

1. **checkpointer** —— `inner_checkpointer = checkpointer or InMemorySaver()` 是装配期建立、
   被 `_skill_node` 闭包捕获的**同一个对象**。同一个 key 意味着条目 2 的
   `agent_graph.invoke` **恢复了条目 1 的检查点**,连同它整段消息历史。
   模型看着条目 1 的 10 条对话,再交一次条目 1 的答案。
2. **`ExitControlMiddleware`** —— 一个相位一个实例(装配期 `build_middleware_chain`
   建立,`create_agent` 烘进图里),它的两个预算字典按同一个 key 索引,
   于是条目 2 拿到条目 1 用剩的迭代计数与 nudge 预算。

`exit_control.py` 里那条注释「one policy instance per thread key = fresh nudge budget per
invoke」把假设写在了明处:**一次 invoke = 一个 thread key**。批处理条目让这个前提不成立。

## 3. 参考的成熟做法(借了什么、拒了什么)

- **本仓自己的既有解法优先**。`_graph_batch_runner`(图级 batch)已经这么做了;
  子技能调用 `skill_tool_factory.py:100` 每次 sub-invoke 组一个新 `thread_id`;
  `parallel_map.py:311` 传 `thread_id=sub_run_id`。**三处既有实现都给每个并发执行单元
  一个独立身份**,只有相位级 batch 这一条路漏了。借的就是这个既有形状,不另发明。
- **LangGraph 的 `checkpoint_ns` 语义**:命名空间本来就是用来隔离同一 thread 内不同
  子图/迭代的状态谱系的。这里是**回到它的正常用法**,不是在它之上另加一层。
- **拒绝**「给每个条目换一个 `thread_id`」:`thread_id` 在本仓是 run 的对外标识
  (run_id),检查点、恢复、事件全按它归集;换掉它会把一次 run 拆成 N 条互不相干的线,
  代价远大于收益。命名空间才是为"同一线内的分支"准备的字段。
- **拒绝**「给 `ExitControlMiddleware` 每个条目建一个新实例」:实例是装配期烘进
  `create_agent` 的,要换实例就要改图的装配时机;而且预算的**作用域**问题应该在
  「什么算一次调用」这个定义上解决,不是靠对象生命周期绕过去。

## 4. 决定(三处,一条规则)

规则:**批处理条目是一次独立调用,它必须有自己的迭代身份,并且这个身份要一路可见。**

1. `core/graph_assembler.py` `_phase_batch_runner` —— 改用
   `_run_with_iteration_context_async(index, _iteration_namespace(index), …)`,
   与图级孪生一致。**同一处漏洞在相位级 loop 上也存在**(`_loop_phase` 里
   `_run_with_branch_index(index, _invoke_node)`,而图级 loop 用的是
   `_run_with_iteration_context`),一并改掉——同一条规则的第二个漏点,
   分开修等于把已知缺陷留在树上。实测未修时 loop 第 2 轮开局 4 条消息、
   第 1 轮 2 条。
2. `core/graph_assembler.py` `_skill_node` —— 把当前迭代命名空间并进它写的
   `checkpoint_ns`:`f"{outer_ns}.agent:{phase_id}"`,让每个条目有自己的检查点车道。
   `NamespaceCheckpointer._wrap_config` 在保存时也会前缀同一个值,并且自带
   `startswith` 防重。同一份身份再写一份到自定义键 `agent_invocation_id`(理由见下)。
3. `middleware/exit_control.py` —— 预算键从 `thread_id` 改成
   `f"{thread_id}|{agent_invocation_id}"`,两个字典与那个方法一并按「invocation」重命名
   (`_iterations_by_invocation` / `_nudge_policy_by_invocation` / `_invocation_key`),
   让名字说出它到底按什么分桶。

非迭代相位的行为不变:那里 `outer_ns` 为空,身份仍是 `agent:{phase_id}`,
键多了一个恒定后缀而已。

### 为什么身份要另走一个键,而不是直接读 `checkpoint_ns`

第一版就是直接读 `checkpoint_ns` 的,**它让 6 个既有测试变红**——不是回归,是设计错了:
预算再也攒不起来,本该因超预算而失败的 run 全部变成成功。

实测(给 `_invocation_key` 打桩,打印它看到的配置):

```
('c1e9c247', 'ExitControlMiddleware.before_model:ece7d6f5-7658-fcf9-b28e-68a14059c423')
('c1e9c247', 'ExitControlMiddleware.after_model:c2fb7a4e-43e1-4824-3f89-a22ebb3e5e15')
('c1e9c247', 'ExitControlMiddleware.before_model:a31f8463-c74b-cf59-c9c0-4b81a10fbd22')
```

LangGraph 递给中间件 hook 的 `checkpoint_ns` 是**这一次 hook 调用**的命名空间,
每次一个新 uuid;`_skill_node` 写进 invoke 配置的那个值到不了这里。所以身份必须走
一个自定义 `configurable` 键。选 `agent_invocation_id` 而不是别的机制,是因为
**同一个方法下面三行就有现成先例**:`max_iterations` 正是这样从 `_skill_node`
传到中间件的,已经工作了很久——照抄一条被验证过的通路,不新发明。

## 5. 验收判据

`packages/graph-agent/tests/core/test_batch_item_isolation.py`,一个单相位、
`iterate.mode=batch over items` 的最小 skill,配一个记录**每次调用收到的完整消息列表**
的假 provider(前 2 次故意提交缺字段的载荷,让条目 1 烧迭代):

1. `test_a_batch_item_does_not_see_the_previous_item_conversation` —— 条目 2 的首次模型
   调用,消息条数必须与条目 1 的首次调用相同,且历史里不得出现条目 1 的标记。
   修复前实测:**条目 1 开局 2 条,条目 2 开局 12 条**,且条目 1 的标记在其中。
   这一条用 `max_iterations=20` 跑,因为**预算宽裕时这个污染是完全静默的、run 报成功**。
2. `test_a_batch_item_gets_its_own_iteration_budget` —— `max_iterations=3`,整次 run 必须
   成功。修复前实测:`[F-v3-agent-exit-control-failed] max iterations (3) reached`。
3. `test_a_loop_round_does_not_see_the_previous_round_conversation` —— `iterate.mode=loop`
   的第 2 轮开局消息数必须与第 1 轮相同。修复前实测:第 1 轮 2 条,第 2 轮 4 条。
   这一条**故意不断言标记**:loop 的累积器**本来就该**把第 1 轮的结果带进第 2 轮,
   它作为声明输入出现在种子轮里是正确行为;消息条数才是区分「累积器流过来了」和
   「对话被继承了」的判据。
4. `test_a_lone_item_is_the_control` —— 同一相位同一预算只跑一个条目,必须成功且只有
   1 次模型调用。这是防止前几条断言变成 fixture 自身的产物。

**一处方法论记录**:这个测试的第一版**通过了未修复的引擎**——因为它只扫消息的
`.content`,而上一个条目的答案躺在 `tool_calls[*].args` 里,`content` 是空串。
断言写在错的字段上,和没有断言等价。现在的 `_text_of` 连 tool-call 参数一起扫,
并且加了「消息条数」这条更钝但更难骗过的判据。
