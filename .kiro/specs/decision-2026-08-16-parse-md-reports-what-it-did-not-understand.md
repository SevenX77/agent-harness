# 决议 2026-08-16:parse_md 说得出它没读懂哪几行

状态:已实施(本 PR)
影响模块:engine(`packages/graph-agent`)
发现方式:`story-deconstruction-v3-lab` 用 DeepSeek V4 Flash 真跑 `segmentation` 相位
(run `09f67b86-eb65-4c97-ba60-deb05e58ce22`,trace
`C:/Users/test/AppData/Local/Temp/cmp_exp_xd8m4g5z/ws/runs/09f67b86-eb65-4c97-ba60-deb05e58ce22/trace.jsonl`)

---

## 一、决策

**一句话**:`parse_md` 读不进任何字段的行,不再只写一条 `logger.warning` 然后丢掉;
它把这些行连同行号、原文、原因记在 `ParsedBlock.meta.unread` 上,
`CognitiveFlowMiddleware` 据此**驳回**这次 finish_task 提交,并把每一行原样点给模型。

具体四条:

1. **不发明第三种输入形态。** 嵌套 bullet 里再写一层缩进子键
   (`- key:` → `  - index: 1` → `    type: B`)**不被支持**,本 PR 也**不**去支持它。
   解析器只有两种结局:读懂,或者说清楚没读懂哪几行。
2. **"没读懂"的判据是"这一行有没有宣告结构"**,不是"这一行想表达什么"。
   带 bullet 记号且后面有内容的行、以 `名字:` 开头的行 —— 这是本格式书写数据的
   两种记号 —— 未被任何字段接收时,一律记为 unread。散文、表格行(`|` 开头)、
   HTML 注释(`<`)、小标题(`#`)、分隔线(`---`)什么也没宣告,解析器从未承诺读它们,
   点名只会制造噪声,一律忽略。
3. **解析没吃完整份输入时,先报这件事,不报由残缺数据推出的判读。** schema 校验与
   业务校验在这一轮**不运行**,因为它们判的是模型根本没写过的东西(论据 §2.1)。
4. **驳回理由带行号。** 同一份 markdown 里同一行文本可以出现多次,只贴原文定位不到;
   行号按整份 `business_data_md` 从 1 数起,模型可以直接照着改。

**唯一权威定义落在** `packages/graph-agent/src/graph_agent/tools/md_to_json.py`:
新增 `UnreadLine` 数据类 + `_RE_ANNOUNCES_STRUCTURE` 判据,三处丢弃点全部改为记账。

---

## 二、论据

### 2.1 现在的实现:丢一半的行,然后报告成功

改前 `packages/graph-agent/src/graph_agent/tools/md_to_json.py` 有三个"看不懂就跳过"的点:

| # | 位置(改前行号) | 改前代码 |
|---|---|---|
| 1 | `_parse_block_data:405` | `logger.warning("parse_md: indented child outside nested field, skipping: %r", line)` |
| 2 | `_parse_block_data:418` | `logger.warning("parse_md: unrecognised line, skipping: %r", line)` |
| 3 | `_parse_at_key_lines:260-263` | `logger.warning("parse_md: non-@key line in nested sub-object context, skipping: %r", stripped)` |

而 `parse_md` 的 docstring(改前 `md_to_json.py:297`)把这条策略写成了契约:

```
    Unrecognised lines are logged at WARNING level and skipped — never raised.
```

**日志不是生产方能听见的通道。** 这里的生产方是 LLM,它唯一的反馈回路是
finish_task 判决(`middleware/cognitive_flow.py:1027-1044` `_reject_finish` 把
`errors` 逐行拼进退回给模型的 `ToolMessage`)。`logger.warning` 进不了那条回路,
所以"我没读懂五行"这件事,模型一个字都看不到。

本机复跑(改前代码,输出原样):

```
$ uv run python -c "... parse_md(md, S) ..."
parse_md: unrecognised line, skipping: '    type: B'
parse_md: unrecognised line, skipping: '    start_line: 1'
parse_md: indented child outside nested field, skipping: '  - index: 2'
parse_md: unrecognised line, skipping: '    type: B'
parse_md: unrecognised line, skipping: '    start_line: 6'
[ParsedBlock(meta=BlockMeta(id='item-1'), data={'parsed_segments': ['index: 1'], 'segments_summary': '两段'})]
```

八行输入丢掉五行,`parsed_segments` 只剩一个字符串 `'index: 1'`,
**而 `parse_md` 返回一个看起来正常的 ParsedBlock**。

**最坏的一档不是"死得莫名其妙",是"根本不死"。** 本 PR 的 RED 实测(改前代码,
`tests/middleware/test_finish_task_names_unread_lines.py`,schema 为
`parsed_segments: list[str]`):

```
E       AssertionError: assert 'accepted' == 'rejected'
E         - rejected
E         + accepted
```

残缺的 `['index: 1']` **完美满足 `list[str]`**,于是判决是 `accepted`,
`1 item(s) passed schema and business validation`,错误数据带着"通过校验"的标签
流进下游。这与 #848 里"逗号切碎的片段完美满足 `list[str]`"是同一种病的另一层:
**类型对、语义错的数据被生产出来并通过了边界校验**。

真跑里那条 `list[dict]` 的字段没这么走运,它一路走到相位校验器才死:

```
[F-v3-agent-validator-failed] phase validator failed:
ValueError: No segments produced. Re-analyze the chapter text.
phase_id='segment'
```

**这条诊断把模型指向了一个不存在的问题。** 章节分析得好好的,坏的是输出格式没被读懂;
模型照着"重新分析章节文本"只会一遍遍重新分析、一遍遍写同一种格式。该 run
6 次模型调用、29,401 in / 7,548 out、4 次 finish_task_verdict,全部 route
`ark-official:deepseek-v4-flash-260425`,最后烧完预算死掉。
**这就是"报告成功"的真实代价:系统让模型去修一个不存在的问题。**

### 2.2 嵌套 bullet 到底被支持到什么程度:①②③ 三选一的答案

任务要求先查清:嵌套 bullet(`- key:` 后跟缩进子项)是不是设计承认的形态。
答案要分两层说,因为这里有两种不同的"嵌套"。

**第一层(一层缩进)是代码承认的,共三种,全部有测试钉住**
(`tests/tools/test_md_to_json_helpers_characterization.py`,改前 33-90 行):

| 字段声明 | 子项形态 | 结果 | 代码 |
|---|---|---|---|
| `list[BaseModel]` | `  - @speaker: narrator` | 解析成对象列表 | `_parse_list_nested_children` → `_parse_at_key_lines` |
| `list[str]` | `  - first` | 解析成字符串列表 | `_parse_list_nested_children` 末行 |
| 非 list | `  - line one` | 逗号拼成一个字符串 | `_flush_nested_field` else 分支 |

**第二层(缩进子项自己再带子键)从来不被支持**。真跑里模型写的正是这一层:

```
- parsed_segments:
  - index: 1
    type: B          ← 这一行没有 bullet,`_RE_INDENTED_CHILD` 不认,`_RE_FLAT_FIELD` 也不认
```

**文档层面:三个方向都查过,零命中。**

- `docs/engine/skill-spec/` 全目录 grep `@speaker` / `@key` / `缩进子行` / `indented` → 0 命中
- `docs/engine/mvp1/` 同样四个词 → 0 命中
- `docs/engine/mvp0/` 同样四个词 → 0 命中
- `docs/engine/mvp0/skill-spec/00-FORMAT-GROUND-TRUTH.md:269-270` 只写到
  「business_data_md 经 md_to_json 强校验,失败会收到错误反馈」,没写值/嵌套形态

模型看到的出口契约同样没有嵌套的一个字。`cognitive/prompt.py:61-70`
(#825,2026-08-15 合入)渲染进 `<exit_contract>` 的全部内容是:

```python
    lines = [
        "```markdown",
        f"## {_BUSINESS_DATA_MD_ITEM_HEADER}",
    ]
    lines.extend(f"- {name}: <值>" for name in properties)
    lines.append("```")
    lines.append(
        "（也可以把整个对象写成一个 JSON 对象，放在 `## ` 标题下的 ```json 代码块里。）"
    )
```

即:**一个 `list[dict]` 字段,模型只被告知写 `- parsed_segments: <值>`,
没有任何一句话说这个 `<值>` 该长什么样。** 模型写嵌套 bullet 不是违规,是在填空。

**所以三选一的答案是:一层缩进 = ①(支持,且本 PR 未触碰其行为);
两层缩进 = ③(从未被文档规定,也从未被代码实现)。**
既然是 ③,就**不能**顺手"猜着支持"——那是在解析器里发明第三种输入形态,
而且是发明一种连出口契约都没教给模型的形态。正确的做法是把这件事说出口。

### 2.3 有既有测试锁死了"悄悄丢掉"吗?有,一条

`packages/graph-agent/tests/tools/test_md_to_json_helpers_characterization.py:93-103`(改前):

```python
def test_parse_block_data_skips_orphan_children_and_unrecognised_lines() -> None:
    parsed = _parse_block_data(
        [
            "  - orphan",
            "plain text",
            "- title: kept",
        ],
        {"title": str},
    )

    assert parsed == {"title": "kept"}
```

它**断言**孤儿子项与无法识别的行被静默丢弃。

来历与 #848 改写的那条同源:该文件由 `7a25b5d8`(2026-05-29)
`feat(round-29): C901 complexity gate + 13 helper refactor` 引入,commit body 原话
「Add 8 characterization tests (100 cases) locking 9 helper baselines」。
表征测试(characterization test)的职责是**在重构前把当时的行为原样钉住**,
用来证明重构没改变行为——它记录代码"当时做了什么",不主张"应该做什么"。
按 no-backward-compat,本 PR **原地改写**这条为
`test_parse_block_data_names_orphan_children_and_unreadable_field_lines`,
并在文件顶部写清它的来历与两处改动的理由。

---

## 三、修在哪一层,为什么不是另一层

### 3.1 这一条和 #848 的边界

#848(`.kiro/specs/decision-2026-08-16-json-array-in-a-bullet-value.md`)修的是
**一个 bullet 的值怎么读**:`- tags: ["a","b"]` 被逗号切碎成
`['["a"', '"b"]']`。它新增 `tools/md_value.py` 作那条规则的唯一权威定义,
三个调用点委托过去。

**本条修的是行级解析器的归属策略**:一行文本能不能落到某个字段上,
落不上时怎么办。两者的分界线很干净:

| | #848 | 本 PR |
|---|---|---|
| 对象 | 已经归属到某个字段的**值** | 尚未归属到任何字段的**行** |
| 入口 | `_coerce_scalar` → `parse_list_value` | `_parse_block_data` 的分类循环 |
| 失败时 | 值原样返回,交给 schema 拒绝 | 行记成 `UnreadLine`,交给判决拒绝 |

`- parsed_segments:` 这一行在 #848 之后仍然被读成"开启一个嵌套字段",
`  - index: 1` 仍然被读成它的一个子项,而 `    type: B` **从来没走到 #848 那条路上**
——它连"是哪个字段的值"都没确定,`parse_list_value` 见不到它。所以 #848 没有、
也不可能覆盖本条。

**共享的是同一条更上位的原则**,而且是 #848 先立的:
「宣告了结构却解析失败的东西,原样交给下一道关卡去拒绝,绝不降级、绝不静默」。
#848 把它用在值上,本 PR 把它推到行上。

### 3.2 为什么修在 engine 的解析层 + 中间件判决层

**修在解析层**(`tools/md_to_json.py`),因为非法状态在那里被制造:
解析器读进一半、丢掉一半,却返回一个与"全部读懂"无法区分的 `ParsedBlock`。
仓规「让非法状态不可表示」指的就是这个——"读了一半"必须是数据结构里能看见的状态,
不能只存在于日志里。

**修在判决层**(`middleware/cognitive_flow.py`),因为解析器不许抛异常
(`parse_md` 契约,§2.1 引文),而模型唯一听得见的通道是 finish_task 判决。
记账在解析层,送达在判决层,这是两件事,分别归位。

### 3.3 为什么不是别的层

**为什么不是"支持这种嵌套形态"**:见 §2.2,两层缩进是 ③——文档没规定、代码没实现、
出口契约没教。在解析器里猜出一套嵌套语义,等于给这个格式偷偷加一条谁都没写下来的
规则,下一个模型写出第四种形态时还要再猜一次。仓规「先看成熟工程怎么解」的反面
教材就是这个:说不出参考对象,就是在凭直觉发明。

**为什么不是提示词层**(去教模型"list 字段要写成 X"):那件事该做,而且 #848 的
§六已经把它单独立项了(「值形态仍然没有写进出口契约……属于 #825 的延长线,应当单独
立项,不夹带」)。但即便契约写得再详细,模型仍然会写出契约没覆盖的形态——那时候
解析器要么读懂,要么说出来,不能第三次悄悄丢掉。提示词能降低概率,消不掉
"丢了却报成功"这个状态。

**为什么不是相位校验器层**:真跑里正是 skill 自己的校验器抛出
`No segments produced.`,而它指错了方向。让每个 skill 各自去防御解析器的沉默,
既是仓规明禁的"层层重复防御",也做不到——校验器看到的是解析后的数据,
它根本不知道有五行没进来。

**为什么不是"事后把丢掉的行拼回去"**:那是仓规点名的 symptom patch
(post-hoc fixups of wrong data)。要问的是"这个状态为什么能存在",
答案是"解析器把'我没读懂'当成了自己的私事",所以改的是它对外的表达。

---

## 四、借了什么、拒了什么、为什么

### 借:`configparser.ParsingError` 的"把读不了的行攒起来一起报"

Python 标准库 `configparser` 解析到不符合语法的行时,不猜、不跳过,而是把每一条
`(lineno, line)` 累进 `ParsingError.errors`,最后**一次性**报出
"Source contains parsing errors" 加全部行号与原文。

**借来的三点取舍**:

1. **报行号 + 原文,不报"大概在某处"** —— 同一份文本里同一行可以重复出现,
   只贴原文定位不到,`UnreadLine.line_number` 就是它的 `lineno`。
2. **全量攒完再报,不是遇到第一条就停** —— 模型改一行、再提交、再被告知下一行,
   是把一次往返变成 N 次。这也正是仓规「全量聚合」在 compile 诊断上的同一条道理。
3. **"什么算可忽略"由白名单定死,不靠猜** —— configparser 的答案是:空行,
   以及带声明前缀(`#`/`;`)的注释行;其余不合语法的行一律是错误。
   本 PR 的对应答案是 `_RE_ANNOUNCES_STRUCTURE`:宣告了结构的行才算"该读没读进",
   其余不算(§一第 2 条)。

**拒掉的部分,以及本仓哪条前提让它不成立**:

- **configparser 抛 `ParsingError`。本仓不能照搬。** `parse_md` 的契约明写不抛
  (§2.1 引文),而且生产方是 LLM,它唯一的反馈回路是判决。解析器里硬抛会绕过这条
  回路,把一个"改写几行就能恢复"的可恢复错误变成崩溃。所以**拒绝的语义保住,
  拒绝的送达方式换成本仓已有的那条** —— 与 #848 拒绝 YAML「raise-on-error」时
  给出的理由完全一致,这是同一条约束的第二次生效。

  **一处交叉引用要说在前面**:#848 的决议 §四(`decision-2026-08-16-json-array-in-a-bullet-value.md:213-214`)
  引用的正是 `parse_md` 这句 docstring(它当时的行号是 `:296`)。本 PR **改写了这句话**
  ——"Unrecognised lines are logged at WARNING level and skipped" 这半句已经不成立了,
  行不再被 skip 而是被记账。**但它依赖的那一半原封不动**:新 docstring 末句仍是
  "Nothing is raised."。#848 的决议是一份有日期的裁决记录,记的是它当时看到的事实,
  不回头改;这条交叉引用写在这里,是为了让下一个读 #848 的人知道该去哪儿看现行契约。
- **configparser 的注释前缀是配置项(`comment_prefixes`)。本仓不设。** 这里没有
  "注释语法"这回事:`business_data_md` 是模型写给解析器的数据,不是人写的配置文件,
  多一个可配置项就是多一条 YAGNI 的将来债(仓规 KISS/YAGNI)。

### 借:`git apply --reject` 的"说清我做不到哪几块"

`git apply` 打不上补丁时,不是静默成功也不是全盘回滚,而是把打不上的 hunk
原样写进 `.rej` 文件,交给人去处理。**借**:部分成功必须把"没成功的那部分"
交出去,而不是让调用方从结果里反推。**拒**:落盘成文件——本仓的"交出去"就是
判决里的那几行,不需要第二个产物。

### 为什么判据是"宣告结构",不是"任何非空行"

放宽到"任何未被消费的非空行都算 unread",会让模型在 `## ` 块里写一句
「以下是本章的分段结果」就被驳回一次——一次白白的往返,而那句话确实什么也没丢。
收紧到"只认孤儿 bullet",又会漏掉真跑里那三行 `    type: B` / `    start_line: 1`
——它们没有 bullet,却正是丢失的数据本身。

`- ` 记号与 `名字:` 头是这套格式书写数据的**全部**两种记号
(`_RE_FLAT_FIELD` / `_RE_NESTED_FIELD` / `_RE_INDENTED_CHILD` 三条正则加起来
就只用到这两种),所以"带了记号却没落到字段上"是一个机械可判、不含意图猜测的判据。
代价写在 §六。

---

## 五、验收判据

| # | 判据 | 覆盖用例 |
|---|---|---|
| a | 复现输入的五行被逐行指名(原文 + 行号 + 原因) | `test_nested_bullet_object_lines_are_named_not_silently_dropped`、`test_each_unread_line_carries_its_line_number_in_the_whole_markdown`、`test_each_unread_line_says_why_it_could_not_be_read` |
| a' | 该反馈到得了模型:提交被驳回,`errors` 里逐行带原文与行号 | `test_unread_lines_reject_the_submission_and_name_themselves_to_the_model` |
| a'' | 该反馈进得了 verdict 的 `details`(trace 侧叙述) | `test_the_verdict_details_narrate_the_parse_gap` |
| a''' | 残缺数据推出的 schema/业务判读不与之同时上报 | `test_a_parse_gap_is_reported_instead_of_the_errors_derived_from_the_truncated_data` |
| b | 合法输入零回归:单层 bullet、`@key` 子对象、纯字符串子项、json 栅栏 | `test_flat_bullets_report_nothing_unread`、`test_plain_indented_children_of_a_list_field_report_nothing_unread`、`test_a_json_fenced_block_reports_nothing_unread`、`test_a_fully_read_submission_still_passes`,外加 `test_md_to_json_helpers_characterization.py` 全部 6 条正向用例断言 `unread == []` |
| c | 空行 / 散文 / 表格 / HTML 注释 / 小标题 / 分隔线不算"没读懂" | `test_blank_lines_prose_tables_comments_and_subheadings_are_not_unread` |
| 其余丢弃点 | 孤儿缩进子项、`@key` 块里的非 `@key` 行同样开口说话 | `test_an_orphan_indented_bullet_is_named`、`test_a_non_at_key_child_inside_an_at_key_field_is_named` |

测试文件:
- `packages/graph-agent/tests/tools/test_md_unread_lines.py`(9 条)
- `packages/graph-agent/tests/middleware/test_finish_task_names_unread_lines.py`(4 条)

**判据 d(第二份拷贝)的结论:`cognitive/md2json.py` 与 `tools/dynamic_schema.py`
本次不改,理由如下,不是漏了。**

- **`cognitive/md2json.py` 没有"行归属"这条规则可言。** 它的
  `_parse_bullets`(`md2json.py:83-91`)只有一条正则 `_BULLET_RE`,没有嵌套字段、
  没有缩进子项、没有 `@key` 子对象的概念;不匹配的行 `continue` 掉之后,
  `_parse_markdown_to_dict:59-62` 还有一条兜底——标题名本身命中 schema 属性、
  或一条 bullet 都没解析出来时,**整段 body 原样作为值**存进去。也就是说
  它压根不是"读一半丢一半"的形状。#848 抽出 `md_value.py` 是因为"值怎么读"
  在三处**同时存在且互相矛盾**;这里不存在第二份"行怎么归属"的实现,
  为一条不存在的重复去抽公共层,正是仓规「DRY,但三次成律」警告的
  "错误的抽象比重复更贵"。
- **而且它在运行期到不了。** `middleware/cognitive_flow.py:451` 的
  `wrap_tool_call` 在 `_INTERCEPTED_TOOLS`(`cognitive_flow.py:111`,含
  `finish_task`)命中时直接走 `_handle_finish_task`,
  `core/graph_assembler.py:2451-2456` 装配出来的那个 StructuredTool 函数体
  (它才调 `parse_finish_markdown`)不执行。给一个跑不到的解析器加一套报告机制
  是纯粹的 YAGNI。
- **`tools/dynamic_schema.py` 的 `parse_md_simple` 在 `src/` 里零调用点**,
  #848 决议 §六第 4 条已经记过这一笔("按 no-backward-compat 它们该被删,
  但删死代码是另一件事")。本 PR 同样不夹带。

---

## 六、已知遗留(明写,不装作解决)

1. **散文里恰好带 ASCII 冒号的句子会被点名。** `注意: 本章共 8 行` 这类行会命中
   `_RE_ANNOUNCES_STRUCTURE` 的 `名字:` 分支,于是被报成 unread 并驳回一次。
   判据换来的是真跑里那三行 `    type: B` 被抓住;两害相权取后者。
   注意这不是新增的严格度:同一句话写成 `- 注意: 本章共 8 行`(带 bullet)时,
   改前改后都会被 Pydantic 以 `extra_forbidden` 驳回,本 PR 只是让**没带 bullet**
   的同一句话得到同样的待遇,而不是被吞掉。
2. **表格与 HTML 注释里的真实数据仍然会被丢掉,且不被点名。** 模型若把整个输出
   写成一张 markdown 表格,`## ` 块解析出零个字段,schema 会以"每个必填字段都缺失"
   驳回——**误导,但不是静默**,模型至少知道这个对象是空的。与本 PR 修掉的
   "丢了一半却报成功"不是同一档,所以留在判据外(§一第 2 条)。
3. **`_data_from_json_block` 那条丢弃点没纳入。** `md_to_json.py:375-379`:
   `## ` 块里是一个合法 JSON 但不是对象、且标题名不是字段时,返回 `{}` 并只写
   `logger.warning`。它是**块级**丢弃,不是行级,且后果同上一条——`{}` 会让每个
   必填字段报 missing,不会伪装成功。一个 PR 一个任务,单独立项。
4. **值形态仍然没有写进出口契约。** 模型看到的骨架只有 `- name: <值>`,
   仍然不知道一个 `list[dict]` 字段该怎么写(§2.2 引文)。本 PR 让"写错了"这件事
   变得可见可改,但没有去教模型怎么写对——那是 `cognitive/prompt.py` 的事,
   #848 §六第 2 条已经把它立成待办,本 PR 不夹带。
   **这两条合起来才是完整的闭环,本 PR 只是其中"说实话"的那一半。**
5. **md-patch 那条支路不消费 `unread`。** `tools/md_to_json.md_to_json()`(parse →
   diagnose → 交 md-patch skill 修)与它调用的
   `skills/builtin/md-patch/script/patch_tools.py:75` `add_missing_item` 都只取
   `ParsedBlock.data`,新加的 `meta.unread` 在那条路上无人查看。**它整条都到不了**:
   `md_to_json(` 在 `packages/graph-agent/src` 与 `apps/studio/backend/app` 里
   零调用点(逐目录 grep 已核,命中的全是 docstring 与提示词文案),活的 finish 路径是
   `CognitiveFlowMiddleware`。给一条跑不到的支路补机制是 YAGNI;要动它,该动的是
   "把这条支路删掉还是接回来"这个更上位的问题,不在本 PR 范围。
6. **`_validate_finish_args` 顺手抽出了 `_business_stage_validation`。**
   加入 parse-gap 这一段后该函数圈复杂度 11 > 10,撞上 ruff C901 门禁
   (实测报文:``error[C901]: `_validate_finish_args` is too complex (11 > 10)``)。
   抽的是业务校验那一段,抽法与新加的 parse-gap 一致——每个会驳回的阶段都返回
   `_FinishValidation | None`,主体读起来就是它本来的样子:一串顺序执行的阶段。
   这不是夹带无关重构,是本次改动逼出来的、且让函数更整齐的那一种。
