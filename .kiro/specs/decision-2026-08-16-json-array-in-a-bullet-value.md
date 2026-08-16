# 决议 2026-08-16:bullet 值里的 JSON 数组是一个数组,不是逗号列表

状态:已实施(本 PR)
影响模块:engine(`packages/graph-agent`)
发现方式:`story-deconstruction-v3-lab` 在带 #838/#843/#844 的 main 上真跑,
第 23 个相位 `discover_dimensions` 死亡(run `485af68a-9bfa-4667-902a-674db5fd19d2`)

---

## 一、决策

**一句话**:Markdown 里"被声明为 list 的那个值"怎么读,全仓只允许一个定义;
这个定义把"宣告了结构的值"(带栅栏的、或首尾都是 JSON 括号的)按 JSON 读,
其余按逗号列表读,而**宣告了结构却解析不出来的值原样返回**,绝不降级切碎。

具体三条:

1. 值首尾都是 JSON 字面量的界符(`[`…`]` / `{`…`}`),或以 ``` 栅栏开头 →
   按 JSON 解析,解析出什么就是什么。
2. 其余值 → 按逗号切分(这是出口契约现在教给模型的形态,见论据 §2.1)。
3. 第 1 条触发但 `json.loads` 失败 → **原样返回那段文本**,交给 schema 校验去拒绝。
   不回落到逗号切分。

第 3 条是整件事的要害。`["a", "b", "c"]` 按逗号切出来是
`['["a"', '"b"', '"c"]']` —— 三个带着方括号和引号残渣的字符串,**完美满足
`list[str]`**,于是校验放行、错误数据继续往下流。原样返回则让校验说出
"这不是一个列表",模型收到的是一条能照着改的反馈。

**唯一权威定义落在**
`packages/graph-agent/src/graph_agent/tools/md_value.py`(新增,纯函数、零内部依赖),
三个调用点全部委托给它。

---

## 二、论据

### 2.1 bullet `- key: value` 是设计承认的第一形态,不是历史宽容

这一步是任务要求先查清的三选一(①并列支持 ②历史遗留宽容 ③从未被文档承认)。
答案是 **①,而且是主推形态**。

`packages/graph-agent/src/graph_agent/cognitive/prompt.py:61-69`
(#825,2026-08-15 合入)渲染进 `<exit_contract>` 的骨架:

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

`packages/graph-agent/src/graph_agent/cognitive/finish_task.py:26-34`,同一 PR:

```python
    business_data_md: str = Field(
        ...,
        description=(
            "Final business output as Markdown. Every '## ' heading starts ONE "
            "complete object matching the phase output schema, with that "
            "object's fields written under it as '- name: value' bullets (or as "
            "a single JSON object in a fenced block). Write one '## ' block per "
            "object — never one per field."
        ),
    )
```

即:**bullet 是主形态,json 栅栏是"整个对象"的替代形态**。任务 brief 里
"W2-11(#825)已经把『一个 `## ` 标题块 + 块内一个 json 代码栅栏』写进提示词与
出口契约"这句话只对了一半 —— 栅栏是被写进去了,但它是**并列的第二选择**,
bullet 骨架才是先渲染出来的那一份。所以修法不能是"废掉 bullet 形态"。

至于 bullet 的**值**允许什么形态,`docs/engine/skill-spec/` 与
`docs/engine/mvp1/` 里**没有任何一句话规定**。我查过的位置与结果:

- `docs/engine/skill-spec/` 全目录 grep `business_data_md` → 0 命中;
  grep `output_example` → 0 命中。
- `docs/engine/mvp0/skill-spec/00-FORMAT-GROUND-TRUTH.md:269-270` 只写到
  「business_data_md 经 md_to_json 强校验」,没写值形态。
- `docs/engine/mvp1/` 下 `business_data_md` 的 17 处命中全部是 io.outputs
  取原文、finish_task schema 对齐这类话题,同样不涉及值形态。

**结论:值形态没有权威文档,只有代码里的事实。** 代码里的事实有两条:
`tools/md_to_json.py:672-675` 把 `list[str]` 的约束串渲染成
`"[列表，缩进子行或逗号分隔]"`(但 `schema_to_type_dict` 在 `src/` 里零调用点,
只能算作者意图的旁证);出口契约实际教出去的只有 `- name: <值>` 这一行,
**没有告诉模型 list 该怎么写**。模型写 JSON 数组因此不是违规,是在填空。

### 2.2 现在的实现:同一条规则有三份拷贝,其中两份是错的

三份都是"把一个 Markdown 值读成 list"这同一条业务规则:

| # | 位置 | 改前代码 | 对错 |
|---|---|---|---|
| 1 | `tools/md_to_json.py:471` `_coerce_scalar` | `return [v.strip() for v in raw_val.split(",") if v.strip()]` | ❌ 完全不认 JSON |
| 2 | `tools/dynamic_schema.py:392` `coerce_list` | `raw_values = value if isinstance(value, list) else str(value).split(",")` | ❌ 同上 |
| 3 | `cognitive/md2json.py:92-99` `_coerce_value` | `if _looks_like_json(value): return _coerce_json_like(value)` 在逗号切分之前 | ✅ JSON 优先 |

**#1 是真跑里死掉的那条。** 活路径证据:
`middleware/cognitive_flow.py:960` `return model, parse_md(business_data_md, model)`,
放行判词出自同一个中间件 `cognitive_flow.py:659`
`f"{accepted_count} item(s) passed schema and business validation."`
—— 与真跑 trace 里 `finish_task_verdict` 的原文
「1 item(s) passed schema and business validation」逐字一致。

**#2 也是活的,不是死代码。** `dynamic_schema` 在 `src/` 里只有
`parse_output_example` / `OutputExampleParseError` 被引用
(`core/schema_engine.py:19`),但 `parse_output_example` 造出来的
`coerce_fn` 会被 `core/schema_engine.py:375-383`
`_coerce_output_example_default` 调用,用来强制转换**可选字段的声明默认值**。
本机实跑证据:

```
$ uv run python -c "... _parse_output_example_to_schema('''<output_example name="Demo">
## item-1
- title (str): the title
- tags (list[str], optional, default=["a","b"]): labels
</output_example>''') ..."
defaults -> (('tags', ['["a"', '"b"]']),)
```

作者写 `default=["a","b"]`,编译出来的默认值是 `['["a"', '"b"]']`。同一个病。

(`parse_md_simple`,任务里点名的那个,在 `src/` 里**零调用点**;而且它压根不做
逗号切分 —— 它只把 bullet 的值原样存成字符串(`dynamic_schema.py:194`),
切分发生在 `coerce_list`。所以"第二份拷贝"的准确坐标是 `coerce_list`,不是
`parse_md_simple`。)

**#3 已经是对的,这恰恰证明规则不是我发明的**:同一个仓、同一份
`business_data_md`,另一个解析器早就裁定"看起来像 JSON 就按 JSON 读"
(`cognitive/md2json.py:158-162` 的 `_looks_like_json` + `107-111` 的
`_coerce_json_like`,失败时返回原文)。`md_to_json.py:340-360` 的
`_parse_json_block` 在**块级**也是同一套(首尾括号 → `json.loads`,失败则回落)。
所以本次不是引入新语义,是把已有裁定推到它缺席的那一层,并消除两份互相打架的定义。

### 2.3 有既有测试锁死了错误行为吗?有,一条

`packages/graph-agent/tests/cognitive/test_md2json_characterization.py:36`(改前):

```python
        ("```json\n[1, 2]", {"type": "array"}, ["```json\n[1", "2]"]),
```

它**断言**一个没闭合的 ```json 栅栏被切成 `['```json\n[1', '2]']`。

当初为什么这么写:该文件由 `7a25b5d8`(2026-05-29)
`feat(round-29): C901 complexity gate + 13 helper refactor — internal cleanup`
引入,commit body 原话「Add 8 characterization tests (100 cases) locking 9 helper
baselines」。characterization test(表征测试)的职责是**在重构前把当时的行为原样
钉住**,用来证明重构没改变行为 —— 它记录代码"当时做了什么",不主张"应该做什么"。
那次重构的目标是把 `_coerce_value` 的圈复杂度从 11 降到 ≤10,顺手钉住的行为里
就带上了这条 bug。

按 no-backward-compat,本 PR **原地改写**这一行为 `"```json\n[1, 2]"`,并在文件
顶部写清它的来历与本次改写的理由。注意它本来就在名为
`test_coerce_value_current_fallbacks_return_original_stripped_text`
(回落时返回原始文本)的用例组里 —— 改写之后它才真正名副其实。

---

## 三、修在哪一层,为什么不是另一层

**修在 engine 的解析层**(`tools/md_value.py` + 三个调用点),因为非法状态就是在
那里被制造出来的:解析器把一个语义唯一的值切成碎片,碎片恰好满足类型,于是
"类型对、语义错"的数据被生产出来并通过了边界校验。仓规「Fail fast,在边界校验」
「让非法状态不可表示」指的正是这一层。

**为什么不是提示词层**(去教模型"list 必须写成逗号分隔"):那是把解析器的缺陷
转嫁给生成方。#825 已经证明"没告诉模型形态"是真问题并补上了骨架,但即便骨架
再详细,只要解析器遇到 `["a","b"]` 仍然切碎并放行,下一次同类输入照样静默出错。
提示词能降低概率,消不掉"错误数据能通过校验"这个状态。

**为什么不是 skill 的相位校验器层**:真跑里正是 skill 自己的 snake_case 校验器
抓到了 `["mirror_connection"`。那纯属运气 —— 它恰好检查格式。换一个不检查格式的
字段,这份垃圾会一路流进最终产物。让每个 skill 各自防御解析器的缺陷,是仓规明禁的
"层层重复防御"。

**为什么不是事后 strip 掉碎片上的 `[` 和 `"`**:那是仓规点名的 symptom patch
(post-hoc fixups of wrong data)。要问的是"这个状态为什么能存在",答案是
"解析器在不该猜的地方猜了",所以改的是判据本身。

**为什么改 `cognitive/md2json.py`(它本来是对的)**:仓规「DRY,但三次成律」——
同一条业务规则,这是第三处,而且三处之间已经**互相矛盾**。留下第三份独立实现,
下一次改动仍然要在两个地方同时想对。它改后有两处行为变化,都是向唯一规则收敛的
结果,已单独列在 §五验收判据里。

---

## 四、借了什么、拒了什么、为什么

### 借:YAML 1.2 的「flow indicator」判据

YAML 1.2 规范 §7.3.3(Plain Style)规定:plain scalar(不加引号的标量)**不允许以
`[`、`]`、`{`、`}` 这些 flow indicator 开头** —— 一旦出现在开头,它就是 flow
collection(行内集合)的信号,不是普通文本;而一个**格式错误的 flow collection 是
解析错误**,不会被宽容地降级成字符串。

**借来的取舍**:界符出现在边缘 = 这是结构声明,不是文本;结构声明坏掉 = 错误,
不是"尽力而为"。这正是本决议第 1、3 条。

**拒掉的部分,以及本仓哪条前提让它不成立**:

- YAML 禁止 plain scalar 里出现逗号,要用引号或显式 flow 语法。本仓**不能照搬**:
  出口契约现在教给模型的就是裸的 `- name: <值>`(§2.1 引文),要求加引号等于推翻
  #825 刚立下的形态,而且生成方是 LLM,不是会读规范的人。所以逗号列表保留。
- YAML 直接抛解析错误。本仓**不能照搬**:`parse_md` 的契约明写不抛
  (`tools/md_to_json.py:296` 原文 "Unrecognised lines are logged at WARNING level
  and skipped — never raised"),而且这里的生产者是 LLM,它唯一的反馈通道是
  schema 校验的诊断回环(`diagnose()` → `DiagnosticReport` → 重新提交)。
  解析器里硬抛会绕过这条回环,把可恢复的错误变成崩溃。所以改成**把原文交给校验**
  —— 拒绝的语义保住了,拒绝的**送达方式**换成本仓已有的那条。

### 借:`json.loads` 的全有全无

标准库 `json` 从不"部分解析":输入坏了就抛,不返回尽力而为的片段。
**借**:解析要么给出完整结果,要么什么都不给。
**拒**:抛异常本身,理由同上。

### 为什么"首尾都要是括号",不是"以 `[` 开头就算"

判据放宽到"以 `[` 开头"会误伤真正的逗号列表,例如
`- refs: [a](u1), [b](u2)`(markdown 链接列表)—— 它以 `[` 开头但整体不是 JSON,
放宽后会被判为"宣告结构却解析失败"而遭拒绝,而现状把它切成两个链接是对的。
"首尾都是界符"这条线不是我定的:`cognitive/md2json.py:158-162` 和
`tools/md_to_json.py:350-353` 两处既有代码本来就是这么划的,本次沿用。
代价见 §六已知遗留。

---

## 五、验收判据

| # | 判据 | 覆盖用例 |
|---|---|---|
| a | bullet 值是 JSON 数组 → 解析成真正的元素,且原样通过 schema 校验 | `test_json_array_bullet_value_parses_into_its_real_elements`、`..._survives_schema_validation_intact` |
| b | 真正的逗号列表不回归(含空段 `a, b,, c`、单元素、中文) | `test_plain_comma_list_bullet_value_is_unchanged`(4 参数) |
| c | 值里含逗号但整体是 JSON 对象数组 / 嵌套数组 → 结构保住 | `test_json_object_array_bullet_value_parses_into_objects_not_fragments`、`test_nested_json_array_bullet_value_keeps_its_nesting` |
| c' | 首尾是括号但解析不出来 → **被拒绝**,不切碎 | `test_bracketed_value_that_is_not_valid_json_is_refused_not_fragmented`、`test_json_object_for_a_list_field_is_rejected_instead_of_being_split` |
| d | 第二份拷贝(`dynamic_schema.coerce_list`,经 `schema_engine` 默认值路径)同规则 | `test_output_example_list_default_written_as_json_is_not_fragmented` |
| d' | 第三份拷贝(`cognitive/md2json`)同规则 | `test_finish_markdown_array_value_that_opens_an_unclosed_fence_is_refused` |

测试文件:`packages/graph-agent/tests/tools/test_md_list_value_reading.py`(13 条)。

**因本次收敛而改变的既有行为**(两条,均为向唯一规则收敛):

1. `cognitive/md2json._coerce_value`,array 字段、值为未闭合栅栏 `` ```json\n[1, 2] `` →
   改前 `['```json\n[1', '2]']`,改后原文 `` '```json\n[1, 2]' ``。既有表征测试已原地改写。
2. `cognitive/md2json._coerce_value`,array 字段、值为无逗号单值 `solo` →
   改前 `"solo"`(字符串,jsonschema 报 not of type array),改后 `["solo"]`。
   这一条使它与 `md_to_json._coerce_scalar` 对同一输入的判读一致 —— 后者一直是 `["solo"]`。

---

## 六、已知遗留(明写,不装作解决)

1. **未闭合的数组 `- tags: [a, b` 仍按逗号列表读**,得到 `['[a', 'b']`,第一段带着
   多余的 `[`。原因见 §四末:判据是"首尾都是界符",这个值没有闭合,所以不触发 JSON
   分支。放宽到"以 `[` 开头"会误伤 `[a](u1), [b](u2)` 这类合法逗号列表,两害相权
   保留现状。该行为由
   `test_unterminated_bracket_value_is_still_read_as_a_comma_list` 显式钉住并在
   docstring 里写明它是 gap 而非期望 —— 与 §2.3 那条**没说自己是 gap** 的表征测试
   的区别就在这里。
2. **值形态仍然没有写进出口契约。** 模型看到的骨架只有 `- name: <值>`,不知道
   list 该写成逗号还是 JSON 数组。本 PR 让两种写法都被正确读取,但没有去改提示词
   —— 那是 `cognitive/prompt.py` 的事,属于 #825 的延长线,应当单独立项,不夹带。
3. **`cognitive/md2json._coerce_value` 对非 array 字段仍然无条件 JSON 化**
   (`looks_like_json_literal` → `_coerce_json_like`):一个 `str` 字段收到
   `["a","b"]` 会被解析成 list 然后被 jsonschema 拒绝,而 `md_to_json._coerce_scalar`
   对 `str` 字段是原样保留。两者在**非 list 字段**上仍不一致。本 PR 不动它:没有
   实测缺陷驱动,改它属于 YAGNI 且会扩大 blast radius。
4. **`dynamic_schema` 的 `parse_md_simple` / `coerce_item_against_dynamic_schema` /
   `validate_against_dynamic_schema` / `render_dynamic_schema_output_format` 在
   `src/` 里零调用点**(只有测试到得了)。按 no-backward-compat 它们该被删,但删死
   代码是另一件事,一个 PR 一个任务,不夹带。
