# 决议:校验器强制的 Markdown 形状,必须讲给要满足它的那一方听

- 日期:2026-08-15
- 范围:engine(`cognitive/prompt.py`、`cognitive/finish_task.py`)
- 状态:已实施
- 相关:同一天那批引擎缺陷(`decision-2026-08-15-engine-*.md`)。这一条是
  `decision-2026-08-15-engine-batch-item-isolation.md` 修完、批处理条目隔离生效、
  真跑往前推进两个子图之后,**下一堵墙**。

## 1. 现场

真跑 `.workspace/runs/2026-08-15T11-35-15_55b58e42`(skill `story-deconstruction-v3-lab`,
DeepSeek V4 Flash,2 章输入)。`segmentation` 子图两个章节全部跑完并正确产出
(条目串台已消失,见上一条决议),流程推进到 `event_timeline` 子图下的 `extrac`
(L2,双分支并行),在相位 `aggregate` 上 233.967 秒时崩掉:

```
[F-v3-agent-exit-control-failed] Phase 'aggregate' failed: nudge budget exhausted
(counts={'planning': 0, 'selfcheck': 0, 'standard': 1, 'total': 1}, max_nudges=1)
after 10 iteration(s) without a valid finish_task marker.
```

打回的理由每一次都是同一个形状(`finish_task_verdict` 事件原文):

```
item parsed_events:   parsed_events:   Field required
item parsed_events:   event_timeline:  Field required
item parsed_events:   events_raw:      Field required
item event_timeline:  parsed_events:   Field required
item event_timeline:  events_raw:      Field required
item events_raw:      parsed_events:   Field required
item events_raw:      event_timeline:  Field required
item events_raw:      events_raw:      Input should be a valid string
```

读法:模型把**一个字段写成了一个 `##` 块**。`parse_md` 于是把三个字段名当成三个
**对象**,每个对象自然缺掉全部三个字段。另有两次是另一种猜法——整份 JSON 直接交,
一个 `##` 都没有,得到「未在 business_data_md 中检测到任何 `##` 块」。
两种错法都不是随机的,都是「不知道该长什么样」时的合理猜测。

## 2. 根因:契约只说了 what,没说 how

`finish_task(business_data_md=...)` 的载荷交给
`graph_agent.tools.md_to_json.parse_md` 解析。那份解析器的契约写在它的模块
docstring 里(`md_to_json.py:1-4`):

> "Converts LLM-generated Markdown (## item boundaries, bullet fields) into
> validated Pydantic model instances"

即:**一个 `## ` 标题 = 一个完整的输出对象**,字段写在标题下面。

而模型收到的提示词里,关于 `business_data_md` 只有两处话,都不含这条规则:

1. `cognitive/prompt.py:25-29`,`<exit_contract>` 的正文:
   > 「回答必须调用 finish_task,输出符合下方 Schema 的结构化结果。
   > business_data_md 遵循 output_schema **列业务字段**;diagnostics_md 写自检诊断。
   > 强制输出 Schema:」

   后面紧跟一份**原始 JSON Schema**。"列业务字段" + 一份列着三个 property 的
   schema + 一个名字以 `_md` 结尾的参数——把「一个字段一个 `##` 块」当成正解,
   是这句话本身教出来的读法,不是模型乱来。

2. `cognitive/finish_task.py:26`,工具参数描述:
   > `description="Final structured/unstructured business markdown output."`

   同样一个字没提 `##` 块。

实测证据(从该次 run 的 `prompt_captured` 事件里取 `aggregate` 相位收到的完整
提示词,搜 `每块对应` 与 ```` ```markdown ````):**两者皆无**。整份提示词从头到尾
没有出现过一次示范性的 `##` 结构。

**引擎里本来有一个函数是专门说这件事的**——`tools/dynamic_schema.py:253`
`render_dynamic_schema_output_format`,它渲染的正文是:

```
请按以下结构输出 business_data_md（一个或多个 `##` 块，每块对应一个 X 实例）：
```markdown
## <item_header>
- <字段>: <值>
```

**它在 `src/` 下没有任何调用点**(全仓 grep 只命中定义处与 `__all__`)。
两种写法(`<output_example>` 与 JSON `output_schema`)经
`core/schema_engine.py:139` 汇成同一个 JSON Schema 交给提示词,所以**没有任何相位
被告知过这个形状**——不是「两条路只有一条讲了」,是一条都没讲。

这就是为什么先前 `segment` / `review` 两个相位是靠**手改 skill 里的
`<example id="OutputFormat">`**才跑通的:那是在 skill 侧一份一份地补引擎该说的话。
补一个相位过一个相位,`aggregate` 立刻又踩同一颗雷——典型的「症状补丁」,
这次改到它真正该在的那一层。

## 3. 参考的成熟做法(借了什么、拒了什么)

- **借:本仓自己已有的正确表达。** `render_dynamic_schema_output_format`
  已经把话说对了(「一个或多个 `##` 块,每块对应一个实例」+ 骨架 + 字段列表),
  只是从没被接上。新渲染器沿用它的措辞与骨架形状,不另发明说法。
- **借:OpenAI structured outputs / JSON Schema 工具生态的既有取舍**——
  把「输出长什么样」放进**工具参数描述**里,而不是只放在系统提示词的末尾:
  参数描述随工具 schema 一起进入每一次请求,不会被长上下文挤走。所以这次
  两处都改:系统提示词的 `<exit_contract>`(给出带本相位真实字段名的骨架)
  与 `FinishTaskInput.business_data_md` 的 description(给出规则本身)。
- **拒:把 `item_header` 从 `SchemaObject` 一路穿到提示词里。**
  `SchemaObject.item_header`(`core/schema_engine.py:52`)确实记着作者写的标题名,
  但 `parse_md` 只把标题文本存进 `BlockMeta.id`,**不参与校验**;为了让骨架里的
  标题名更像作者的原意而新增一条跨三层的传参,收益是零(YAGNI)。骨架统一用
  `## item-1`。
- **拒:在 `md_to_json` 侧「宽容解析」——把「每个字段一个 `##` 块」也当成合法输入
  合并成一个对象。** 那会让「三个对象」与「一个对象的三个字段」不可区分,
  真正想输出三个对象的相位从此无法表达;而且它是在解析器里给提示词的缺陷擦屁股
  (呼应仓规「先问这个状态为什么能存在」)。缺的是一句话,不是一个兼容分支。

## 4. 决定(两处,一条规则)

规则:**校验器强制的形状,必须由引擎在契约里明说,并且这句话要由校验器本身
证明其正确。**

1. `cognitive/prompt.py` —— `<exit_contract>` 在 `<output_schema>` 之后追加
   「Markdown 结构说明」:一句规则(`_BUSINESS_DATA_MD_SHAPE_RULE`)+ 一段用
   **本相位真实字段名**渲染出来的骨架(`_render_business_data_md_skeleton`)。
   schema 里没有顶层 `properties` 时不渲染骨架(没有字段可列),规则句也随之省略。
   同时把正文里那句 "遵循 output_schema **列业务字段**" 改掉——它是错误读法的
   直接来源,留着就是让契约自相矛盾。
2. `cognitive/finish_task.py` —— `FinishTaskInput.business_data_md` 的 description
   从 "Final structured/unstructured business markdown output." 改为完整陈述
   `##` 块规则的一句话。

## 5. 验收判据

`packages/graph-agent/tests/runtime/test_exit_contract_business_data_md_shape.py`,
用真跑里崩掉的那份 schema(`parsed_events` / `event_timeline` / `events_raw`):

1. `test_exit_contract_says_one_heading_is_one_object_not_one_field` ——
   契约里必须出现 `## ` 与本相位的每个字段名。修复前实测:整段 `<exit_contract>`
   里没有 `## `。
2. `test_the_skeleton_it_teaches_parses_as_exactly_one_complete_object` ——
   **防漂移的那一条**:把渲染出来的骨架**喂进真正的 `parse_md`**,必须解析成
   **恰好 1 个** block,且它的字段集合等于 schema 的 property 集合。
   一句散文规则会和解析器悄悄漂开;让解析器自己给这句话背书,才是不漂的做法。
   修复前实测:契约里根本没有 ```` ```markdown ```` 骨架可喂。
3. `test_a_phase_without_an_output_schema_gets_no_skeleton` —— 无 schema 的相位
   不得凭空多出一段骨架。

**一处遗留观察**(不在本次改动范围内):`render_dynamic_schema_output_format`
仍是 `src/` 下的死代码(仅 `__all__` 导出)。本次没有删它,因为删一个公开导出
是另一件事、另一个 PR;记在这里,免得下一个人再把它当成"已经在起作用的东西"。
