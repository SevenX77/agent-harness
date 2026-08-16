# 决议:相位的输入块按「它自己在不在」投递,不看「有没有人说过话」

- 日期:2026-08-16
- 范围:`packages/graph-agent/src/graph_agent/middleware/runtime_input.py`
- 触发:决议 `.kiro/specs/decision-2026-08-16-a-phase-opens-its-own-conversation.md`
  「已知遗留」第 1 条(PR #838,commit `01f5cdde`)
- 现场证据:真跑 `D:/coding/skills/story-deconstruction-v3-lab/.workspace/runs/2026-08-15T12-40-22_bb6e358a`
  (DeepSeek V4 Flash)

## 决策

`RuntimeInputMiddleware` 是否投递本相位声明的输入 JSON 块,判据从
**「这段历史里有没有出现过 HumanMessage」** 换成
**「这一次请求里已经有没有这一块本身」**——用块自己的内容作身份。

投递因此回到它本来的节奏:**每一次模型调用都投一遍**。
事件 `runtime_input_injected` 跟着改为**每次真投递发一条**,跳过不发。

## 论据一:每次调用都要重投,是这个中间件的机制决定的,不是新选择

`RuntimeInputMiddleware` 挂在 `wrap_model_call` 上。这个钩子只改**这一次请求**,
它插进去的消息**不写回 state**。langchain 1.3.10 源码三处连起来就是完整因果链
(`.venv/Lib/site-packages/langchain/agents/factory.py`):

`:1409-1418` —— 每次进模型节点,`messages` 都从 state 重新造:

```python
        request = ModelRequest(
            model=model,
            tools=default_tools,
            system_message=system_message,
            response_format=initial_response_format,
            messages=state["messages"],
```

`:1424` —— 中间件改过的 request 只流向模型执行函数:

```python
        result = wrap_model_call_handler(request, _execute_model_sync)
```

`:1389-1393` + `:1398-1404` —— 改过的 messages 只用来发一次调用,回收的
`ModelResponse.result` 里只有**模型自己的输出**(`_handle_model_output` 在 `:1173`
返回 `{"messages": [output]}`):

```python
        messages = request.messages
        if request.system_message:
            messages = [request.system_message, *messages]

        output = model_.invoke(messages)
```

所以每一轮的请求天然不含上一轮注入的块,中间件**必须**每轮重投。

**这一点不是只读源码推出来的,现场数据独立复现了它。** 从
`trace.jsonl` 按相位统计 `llm_call` 与 `runtime_input_injected`:
凡是一次都没被 nudge 过的相位,两个数**完全相等**——
`stitch` 8/8、`aggregate` 7/7、`segment` 4/4、`entity_and_characters` 4/4、
`discover_dimensions` 3/3、`global_analysis` 2/2。
如果注入会持久化,第二轮起就该跳过,不可能次次相等。

## 论据二:旧判据是代理指标,而代理物由别的中间件生产

旧判据(`runtime_input.py:64`,本 PR 前):

```python
        if not any(isinstance(m, HumanMessage) for m in messages):
```

它想问的是「我这块投过没有」,实际问的是「有没有人以人类身份说过话」。
而 nudge / dead-end 警告 / 死循环诊断**全部**以 HumanMessage 写进共享通道
(逐点 grep 核实):

| 发出点 | 代码 |
|---|---|
| `middleware/exit_control.py:209` | `return {"jump_to": "model", "messages": [HumanMessage(content=decision.text)]}` |
| `middleware/exit_control.py:306` | `"messages": [HumanMessage(content=decision.text)],` |
| `middleware/exit_control.py:327` | `"messages": [HumanMessage(content=decision.text)],` |
| `middleware/execution_control.py:241` | `return {"messages": [HumanMessage(name="dead_end_warning", content=warning)]}` |
| `middleware/loop_detection.py:134` | `HumanMessage(name="loop_detection_diagnostic", content=diagnostic,)` |

(#838 决议里记的 `execution_control.py:271` 是旧行号,现行是 `:241`。)

于是:**一个相位只要被 nudge 过一次,它自己后续每一轮都再也拿不到输入块。**
同一份 trace 里,凡被 nudge 过的相位,无论跑多少轮,注入数都定格在 1:

| 相位 | llm_call | runtime_input_injected | nudge |
|---|---|---|---|
| `review` | 15 | 3 | 6 |
| `system` | 6 | 1 | 1 |
| `foreshadow` | 5 | 1 | 1 |
| `prop` / `spatiotemporal` / `tension` | 4 | 1 | 1 |
| `arc` / `retroactive` | 2 | 1 | 1 |

全 run 77 次模型调用、38 次投递。差额 39 = **32 次因本相位被 nudge**(上表)
+ 7 次因跨相位继承(`settings` 3、`continuity` 4,已由 #838 修掉)。
两项相加正好等于差额,说明成因已被穷尽,没有第三种。

## 说准确:丢的是引擎那份结构化副本,不是数据本身

相位并没有瞎跑。同一个中间件的**前半段**在做另一件事——把系统提示词里作者写的
`{字段}` 占位符按黑板视图插值(`_safe_render_template`)。作者只要在 SKILL.md 里
写了 `{text}`,数据照样到模型眼前。

丢掉的是**引擎自己那份声明式输入的 JSON 块**:它按 `io.inputs.properties` 全量投递,
不依赖作者记得在提示词里引用每一个字段。作者漏写哪个字段,哪个字段就只能靠这块送达。

## 修在哪一层,以及为什么不是另一层

修在中间件的判据本身,不在上游三个发出点。

三个发出点写 HumanMessage 是**正确的**:nudge 就是以用户身份对模型说话,
这是 langchain agent 的常规表达。要它们改用别的消息类型,是让五个正确的调用方
去迁就一个错误的判据,而且下一个往对话里写 HumanMessage 的新中间件会再次踩中
(呼应仓规 first-principles fixes:问「这个状态为什么能存在」)。

也不是在 `graph_assembler.py` 的装配顺序上做文章。链上顺序
(`graph_assembler.py:2141-2149`,RuntimeInput 排在元组第一位即最外层)本来就是对的,
缺陷与顺序无关。该处注释 `:2139` 原写「first-turn input seeding」,措辞随本次契约一并订正。

## 判据用什么做身份:内容,不是新加的标记字段

候选一(采纳):**块自己的内容**。中间件先算出这一次要投的 `content`,
再看请求里有没有一条 HumanMessage 内容与之逐字相同。

候选二(拒绝):给块打 `name="runtime_input"` 之类的标记。拒绝理由有二:

1. `name` 是**会发给 provider** 的字段——同仓 `execution_control.py:241` 的
   `name="dead_end_warning"` 就是这么发出去的。要让标记能区分相位就得把相位名
   编进去,而相位名的字符集不受 provider 的 `name` 约束管辖(OpenAI 侧对该字段
   有字符集限制),等于给自己埋一类只在特定相位名下才炸的故障。
2. 标记是**第二份真相**:块的内容和它的标记必须永远同步,而两者由同一个函数
   在同一处生成——多出来的这一份同步义务没有换来任何判别力。

内容判据的另一个好处是幂等性**结构上成立**而不是靠约定:同一个函数产出候选块与
既有块,不存在空白/序列化漂移的可能,`f(f(x)) == f(x)` 是恒等式。

**边界如实写**:两个相位若声明了完全相同的输入键、且值也完全相同,产出的块逐字相同,
后者会被判为"已投递"而跳过。这正是幂等要的行为——一次请求里出现两份逐字相同的
输入块是纯浪费。相位各有自己的 agent,同一次请求里本来也不会出现两个相位的块。

## 借了什么、拒绝了什么

**借的是 HTTP 幂等键 / Kubernetes `kubectl apply` 的声明式收敛语义**:操作方先算出
"目标状态应该长什么样",再与现状比对,一致就什么都不做——幂等性来自**比对目标本身**,
而不是来自另存一个"我已经做过了"的标志位。选它是因为标志位与目标之间的同步是额外的
失败面,而这里目标(块的内容)本身就是可比对的、廉价的、且天然唯一。

**拒绝的是数据库式的 dirty-flag / 版本号**:那套方案的前提是"目标状态昂贵到不值得
每次重算或比对"。这里的目标是一个几百字节的 JSON 串,每轮本来就要算一遍(要发给模型),
比对成本等于一次字符串相等——前提不成立,所以只取声明式收敛那一半。

**同样拒绝把 nudge 改成非 HumanMessage**:见上一节。

## 事件语义:每次真投递发一条,跳过不发

依据是 glass-box 决议原文
`docs/design/2026-08-13-trace-goes-glass-box-decision.md:199-205`:

> ### D4 · 内部机器自述:发「决定」不发「路过」(E3)
>
> 每个「做了**影响执行的决定**」的内部步骤发语义事件 [...]
>
> **防噪音原则**:发「决定」不发「路过」—— 修了数据、拦了循环、**注了输入**、吞了错误、
> 下了校验结论才发;纯透传不发。这条原则是 D4 不退化成日志洪水的边界。

「注了输入」被 D4 **点名列进"决定"清单**。据此:

- **真投递 = 决定**(它改变了模型这一轮看见什么)→ 每次发一条;
- **判定已存在而跳过 = 路过** → 不发。

这样事件条数恒等于模型实际收到输入块的轮数,trace 读者据此能重建"模型每一轮看见了什么"。
反过来若沿用"只发首轮",第 5 轮投了却没有事件,trace 就在**少报**。

噪音方面按同一份 run 估算:38 → 77 条,与 `llm_call` 同数量级,远不是 D4 所防的日志洪水。

原事件文案自称 "Seeded the **first** model turn",与新语义矛盾,一并改写;
`callbacks/events.py` 的事件 docstring 同改。

## 同批订正的派生文档

`apps/studio/backend/app/agents/knowledge/KB-02-io-dataflow.md:31` 原文
「when the conversation carries no human message yet」直接复述了旧判据,已改写为
每次调用投递 + 幂等跳过。(同文件 `:29` 早已写着 "does two separate things on every
model call",`:34` 写着 "every copy is paid for on every turn"——文档的其余部分本来
就按每轮投递描述,只有这一句跟着代码错了。)

## 验收判据

新测试 `packages/graph-agent/tests/middleware/test_runtime_input_delivery_criterion.py`:

| 判据 | 测试 |
|---|---|
| a. 被 nudge 后仍拿得到输入块 | `test_every_interruption_shape_still_gets_the_block`(三种真实中断形状逐一)、`test_a_tool_conversation_in_progress_still_gets_the_block`、集成 `test_a_phase_still_has_its_inputs_on_the_turn_after_a_nudge` |
| b. 一次请求里不重复出现 | `test_running_the_hook_over_its_own_output_adds_no_second_block`、集成 `test_the_block_appears_once_per_turn` |
| c. 同步/异步一致 | `test_the_async_hook_delivers_exactly_what_the_sync_hook_delivers` |
| d. 事件语义 | `test_each_delivery_is_its_own_event`、`test_a_skipped_delivery_says_nothing` |
| 判据不被别人的块顶替 | `test_a_different_block_does_not_count_as_mine` |

集成测试复用 #838 的做法:真跑 `run_skill`,让相位第一轮只出文本不调工具,
由**真的 `ExitControlMiddleware`** 产出 nudge,而不是手搭一条假消息。

既有测试 `test_remaining_machinery_speaks.py::test_a_turn_that_already_has_input_emits_nothing`
断言的正是本次要修的行为(任意一条 `HumanMessage(content="already here")` 就压住事件),
按仓规 no-backward-compat **原地改写**为新判据下的"路过不发事件",不留双轨。

## 已知遗留(明写,不装作解决)

1. **本 PR 只交离线证据。** 修复后没有重跑
   `story-deconstruction-v3-lab` 复核 77/77。真跑要花钱和时间,且需要 W2-18 一并在册,
   留给后续的真机复核任务。上面所有现场数字都来自**修复前**那份 trace。
2. **投递位置固定在消息列表最前(`insert(0, ...)`),没有为"提醒式尾插"做取舍论证。**
   保持原有位置是最小改动;若将来发现长对话里模型会遗忘开头的输入块,
   "首插还是尾插"需要单独的证据和裁决,本次不预判。
3. **`review` 相位 15 次调用只投 3 次、却有 6 次 nudge**,与"一次 nudge 后定格在 1"
   的模式不完全吻合——它有 4 次相位执行(见 trace 统计),3 次投递大致对应
   未被 nudge 的那几次开场。本决议未逐轮还原它的时序;这不影响结论
   (无论几次,判据都错),但也不该被当成已经解释清楚。
4. 上游决议的另一条遗留 —— `flow.working_memory` 是第二条跨相位通道 —— **本次不动**,
   仍待单独裁决。
