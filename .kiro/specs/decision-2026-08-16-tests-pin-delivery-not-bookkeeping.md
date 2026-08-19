# 决议 2026-08-16:parse-gap 的测试要钉住"送到模型手里",不是"记下来了"

状态:已实施(本 PR)
影响模块:engine(`packages/graph-agent`)——**只改测试,生产代码零改动**
适用对象:#850(`59e74020`)新增的 13 条测试
前置决议:`.kiro/specs/decision-2026-08-16-parse-md-reports-what-it-did-not-understand.md`

---

## 一、决策

**一句话**:#850 立的论点是「日志不是生产方能听见的通道,模型唯一的反馈回路是
finish_task 判决拼进退回它的那条 ToolMessage」,但它的 13 条测试没有一条断言过那条
ToolMessage。本 PR 把中间件侧的测试改成**以退回模型的 ToolMessage 为断言对象**,
并给那条空转的否定断言配上正向前置。

具体四条:

1. **断言对象换成回路本身。** 中间件测试不再只读 `FinishTaskVerdictEvent`
   ——那是 trace 侧的账本;改为读 `CognitiveFlowMiddleware.wrap_tool_call` 返回的
   `Command`:它的 `goto`、它 `update["messages"]` 里那条 `ToolMessage` 的
   `status` 与 `content`。账本另有一条测试管,但**账本不代表送达**。
2. **否定断言必须有正向前置。** 「残缺数据推出的判读没有一起上报」这件事,只有在
   「gap 确实上报了」被先证明之后才有意义。前置具体到**行号与原文**,否定项换成一条
   **会被真的触发**的业务校验判词,并直接断言业务校验器**这一轮没被调用**。
3. **`list[str]` 那一档单独立一条测试,并把"schema 拦不住"先证出来。**
   `parse_md` 读残后的 `['index: 1']` 通过 `SchemaEngine.validate`,这一步在测试里
   是**被断言的事实**,不是注释里的说法;挡在"错误数据带着通过标签流进下游"前面的
   只有 parse-gap 这一道,所以它必须被单独钉住。
4. **只动测试。** 生产代码一行未改(§五判据 d 的 `git diff --stat` 佐证)。
   变异分析过程中发现了一处**与本缺陷无关**的生产侧问题(§六第 1 条),按"一个 PR
   一个任务"另行立项,不夹带。

改动落在一个文件:
`packages/graph-agent/tests/middleware/test_finish_task_names_unread_lines.py`
(4 条 → 6 条)。`packages/graph-agent/tests/tools/test_md_unread_lines.py` 的 9 条
解析器测试**不动**,理由见 §四第 3 条。

---

## 二、论据

论据分三层:先说清测试在验什么(§2.1),再用变异体证明它验不出什么
(§2.2 - §2.4),最后说清为什么这是缺陷而不是洁癖(§三)。

### 2.0 方法与"这次跑的确实是那份代码"

变异分析在**仓库之外**的一次性副本里做:
`C:/Users/test/AppData/Local/Temp/claude/.../scratchpad/lab/graph-agent`
(整份 `packages/graph-agent` 的拷贝)。

这一步不是洁癖,是必须的:本仓根 `pyproject.toml:42-51` 的
`pythonpath = ["packages/graph-agent/src", ...]` 会把**仓根**的 src 插进
`sys.path`,而 venv 里 `graph_agent` 也解析到仓根。实测(副本目录下裸 `python -c`,
没有 pytest 的 pythonpath):

```
$ python -c "import graph_agent.middleware.cognitive_flow as m; print(m.__file__)"
cognitive_flow: D:\coding\agent-harness\packages\graph-agent\src\graph_agent\middleware\cognitive_flow.py
```

——**加载的是已修好的仓根源码**,在这上面跑"变异体"只会拿到假绿。
所以每一轮矩阵都先跑一条 provenance 断言,证明加载的是副本:

```
LOADED: C:\Users\test\...\scratchpad\lab\graph-agent\src\graph_agent\middleware\cognitive_flow.py
.
1 passed in 0.05s
```

副本自带 `packages/graph-agent/pyproject.toml:60-62`
(`testpaths = ["tests"]` / `pythonpath = ["src"]`),所以在副本目录下运行时
rootdir 是副本,`src` 指的是副本的 src。

工作树里**始终没有未提交的生产代码改动**:变异只发生在副本上,`git status`
全程只有一个测试文件与三份文档(本决议、被订正的 #850 决议、台账),
生产代码一行没动(§五判据 d)。

**基线说明**:下文所有变异体的基线写的是 `b44c2b71`,那是本 PR 开工时的 `main`。
过程中 `main` 前进过两次,本分支跟着 rebase 了两次,但被变异的三个文件
——`middleware/cognitive_flow.py`、`tools/md_to_json.py`、`cognitive/prompt.py`
—— 在 `b44c2b71` 与 rebase 后的 `main` 之间**逐字节相同**
(`git diff b44c2b71 origin/main -- <三个文件>` 输出为空),所以基线标签仍然精确;
矩阵在 rebase 之后也重跑过一次,逐格结果与下表完全一致。

### 2.1 #850 的中间件测试断言的是账本,不是回路

`packages/graph-agent/tests/middleware/test_finish_task_names_unread_lines.py`
(修前,`b44c2b71`)4 条测试的断言对象**全部**是
`recorder.verdicts()` 取出的 `FinishTaskVerdictEvent`:

| 测试 | 断言对象 | 断言内容 |
|---|---|---|
| `test_unread_lines_reject_the_submission_and_name_themselves_to_the_model` | `verdict.verdict` / `verdict.errors` | 判 rejected;errors 里有 5 行原文与行号 |
| `test_the_verdict_details_narrate_the_parse_gap` | `verdict.details` | 含 `"5"` |
| `test_a_parse_gap_is_reported_instead_of_the_errors_derived_from_the_truncated_data` | `verdict.errors` | 不含 `"segments_summary"` |
| `test_a_fully_read_submission_still_passes` | `verdict.verdict` | 判 accepted |

而它的 `_submit`(修前 `:63-70`)**把 `wrap_tool_call` 的返回值丢掉了**:

```python
def _submit(middleware: CognitiveFlowMiddleware, md: str) -> None:
    middleware.wrap_tool_call(
        _request(...),
        _handler,
    )
```

返回值就是那条回路:`middleware/cognitive_flow.py:1046-1069` `_reject_finish`
返回的 `Command` 里,`update["messages"]` 那条 `ToolMessage(status="error")`
是模型实际读到的东西,`goto="model"` 是把这一轮交回模型的动作。
**测试把它丢在地上,所以"模型收到了什么"在这套测试里根本不可见。**

`FinishTaskVerdictEvent` 是另一回事:`cognitive_flow.py:163-188` `_say_verdict`
把它发给 `callbacks`,它的归宿是 trace(glass-box D4)。它**记录**同一件事,
但它不是模型的输入。

### 2.2 变异体 M1:保留记账、只切断投递 —— 改前只有 1 条转红

外科式反证,只动一处、且刻意**不动**记录与叙述:

```python
        parse_gap = _parse_gap_validation(blocks, story)
        if parse_gap is not None and False:  # MUTANT M1
            return parse_gap
```

`_parse_gap_validation`(`cognitive_flow.py:1256-1300`)照常被调用,
`ParsedBlock.meta.unread` 照常被记满,而且它**就地**往 `story` 里追加叙述
(`:1281-1284`,`story` 是调用方传进来的 list),所以那句
`parse_md left 5 line(s) ... unread` 照样进 `details`。变的只有一件事:
`_FinishValidation` 没有被返回,于是执行继续往下走 schema 与业务校验,
判决变成 `accepted`,**模型一个字都收不到**。

改前 13 条测试的实测输出(原样):

```
.........F...                                                            [100%]
=========================== short test summary info ===========================
FAILED tests/middleware/test_finish_task_names_unread_lines.py::test_unread_lines_reject_the_submission_and_name_themselves_to_the_model
1 failed, 12 passed in 0.08s
```

**13 条里只有 1 条转红。** 其中
`test_the_verdict_details_narrate_the_parse_gap` **仍然 PASSED** —— 因为
`_parse_gap_validation` 在 return 之前就地 append 了 story,叙述照样进 details。
**#850 要治的病在它自己的测试里复发了:记账做了,送达没做,而测试只看记账。**

改后 15 条的实测输出:

```
.........FFFFF.                                                          [100%]
=========================== short test summary info ===========================
FAILED tests/middleware/test_finish_task_names_unread_lines.py::test_the_parse_gap_comes_back_to_the_model_as_a_failed_tool_call
FAILED tests/middleware/test_finish_task_names_unread_lines.py::test_the_reply_to_the_model_quotes_every_unread_line_with_its_number
FAILED tests/middleware/test_finish_task_names_unread_lines.py::test_the_verdict_details_narrate_the_parse_gap_on_a_rejected_verdict
FAILED tests/middleware/test_finish_task_names_unread_lines.py::test_the_business_verdict_derived_from_truncated_data_never_reaches_the_model
FAILED tests/middleware/test_finish_task_names_unread_lines.py::test_truncated_data_that_satisfies_the_schema_is_refused_anyway
5 failed, 10 passed in 0.10s
```

**1 条 → 5 条。** 第 6 条(对照组)不转红是它该有的结果,见 §四第 2 条。

### 2.3 变异体 M2:回退到 #850 的父提交 —— 改前那条否定断言空转

M2 把 `middleware/cognitive_flow.py` 与 `tools/md_to_json.py` 两个文件整份换成
`49f7ad0d` 的版本,测试保持现状。

改前 13 条:

```
FFFFFFFFFF...                                                            [100%]
10 failed, 3 passed in 0.09s
```

三条幸存者里,两条是**真问题**:

- `test_a_parse_gap_is_reported_instead_of_the_errors_derived_from_the_truncated_data`
  ——全文只有一句否定断言 `assert "segments_summary" not in joined`。回到修前代码时
  判决是 `accepted`、`errors` 是空 list、`joined` 是空串,**否定断言空转成立**。
  它同样在 M1 下 PASSED。**一条在"功能完全没实现"时也成立的断言没有区分力**:
  它区分不了「gap 单独上报」与「gap 根本没上报」。
- `test_the_verdict_details_narrate_the_parse_gap` —— 断言 `"5" in joined`。
  在 M2 下它**时红时绿**,原因见 §六第 1 条:`details` 里那句
  `Schema check against 'BusinessSchema_<8位十六进制>'` 的哈希后缀**逐进程随机**,
  哈希里恰好出现数字 `5` 时这条断言就凭空成立。同一格跑了 6 次(1 次首轮矩阵
  + 5 次重跑),`10 failed, 3 passed` 出现 **2** 次(首轮与第 5 次重跑,即这条断言
  **通过**),`11 failed, 2 passed` 出现 **4** 次(即这条断言**失败**);上面那段
  引文就是 `10 failed, 3 passed` 的那一次,其中 3 = 这一条 + 上一条空转的否定断言
  + 对照组。**这不只是弱断言,是一枚硬币** —— 同一份代码、同一条测试,
  结果取决于一个哈希后缀里有没有数字 5。

第三条幸存者 `test_a_fully_read_submission_still_passes` 是对照组,幸存是对的
(§四第 2 条)。

改后 15 条,6 次运行**每次都是同一结果**:

```
FFFFFFFFFFFFFF.                                                          [100%]
14 failed, 1 passed in 0.12s
```

唯一幸存的就是对照组。**空转的否定断言与那枚硬币都被消掉了。**

### 2.4 变异体 M3:账本全量、送达只发第一条 —— 改前全绿

M3 只改一个字符级的切片,`cognitive_flow.py:1047`:

```python
        content = self._REJECTION_PREFIX + "\n" + "\n".join(errors[:1])  # MUTANT M3
```

`errors` 有 6 条(1 条总说明 + 5 条逐行点名),`_say_verdict` 收到的仍然是完整 6 条,
只有拼给模型的 `content` 被截成第 1 条 —— **模型看到"有 5 行没读进来",
但一行都没被点名**,正是 #850 从 configparser 借来的"全量攒完一次报"被废掉的样子。

改前 13 条:

```
.............                                                            [100%]
13 passed in 0.07s
```

**全绿。** 因为那 5 行原文与行号只在 `verdict.errors` 里被检查,而账本是全的。

改后 15 条:

```
..........F.F..                                                          [100%]
FAILED tests/middleware/test_finish_task_names_unread_lines.py::test_the_reply_to_the_model_quotes_every_unread_line_with_its_number
FAILED tests/middleware/test_finish_task_names_unread_lines.py::test_the_business_verdict_derived_from_truncated_data_never_reaches_the_model
2 failed, 13 passed in 0.09s
```

M3 是本次分析的**额外发现**:任务书只点名了 M1 与 M2,而 M3 说明"账本 vs 送达"
这条裂缝不止一种走法 —— 只要断言留在账本上,送达可以任意缩水而不被察觉。

### 2.5 全矩阵(1 次首轮 + 5 次重跑,共 6 次;逐格结果)

| 变异体 | 改前 13 条 | 改后 15 条 |
|---|---|---|
| 无(`b44c2b71`) | 13 passed | 15 passed |
| M1 切断投递 | **1 failed**, 12 passed | **5 failed**, 10 passed |
| M2 回退到 `49f7ad0d` | **不稳定**:6 次里 4 次 `11 failed, 2 passed`、2 次 `10 failed, 3 passed` | **14 failed**, 1 passed(6 次全同) |
| M3 只送第一条错误 | **0 failed**(全绿,变异体存活) | **2 failed**, 13 passed |

---

## 三、为什么这是缺陷,不是洁癖

**一条杀不掉变异体的测试,和没有测试的区别只在于它让人以为有测试。**
这不是修辞,§2.4 就是它的实物:M3 这个变异体让"逐行点名"这个 #850 的核心承诺
彻底失效,而改前那套测试**一条都没红**。谁在重构 `_reject_finish` 时手滑,
7 道必需门禁会全绿放行。

更具体地说,三条理由:

1. **#850 的正文论点与它的测试对象不一致。** 决议正文(§2.1)写的是
   「`logger.warning` 进不了那条回路,所以"我没读懂五行"这件事,模型一个字都看不到」
   —— 它反对的正是"记录了但没送达"。而它的验收判据 a' 写着
   「该反馈到得了模型:提交被驳回,`errors` 里逐行带原文与行号」,落地成的测试断言的
   却是 `FinishTaskVerdictEvent.errors`,那是 trace 的字段,不是模型的输入。
   **判据的文字是对的,测试的落点错了一层。**
2. **这条裂缝在这份代码里格外滑。** `_parse_gap_validation` 用**就地修改** `story`
   的方式做叙述,用**返回值**做投递 —— 两件事在同一个函数里,但一个是副作用、
   一个是返回值。副作用永远发生,返回值可以被忽略。M1 正是踩在这条缝上:
   一行代码的改动,让叙述与投递分家,而只看叙述的测试一无所知。
3. **代价是真实发生过的。** #850 决议 §2.1 记的真跑 `09f67b86`:6 次模型调用、
   29,401 in / 7,548 out,模型被 `No segments produced. Re-analyze the chapter text.`
   指向一个不存在的问题,重复分析同一章直到烧完预算。那次事故的机制就是
   "系统知道、模型不知道"。用只检查"系统知道"的测试去守护它,是同一个错误的第二次。

---

## 四、借了什么、拒了什么、为什么

### 借:变异测试(mutation testing)的**判据**,不是它的工具链

参考对象两个,都指名道姓:

- **PIT / pitest(Java,`https://pitest.org/`)** —— 变异测试的事实标准实现。
  它对自己解决的问题的表述是:传统覆盖率只度量哪些代码被执行了,不检查测试是否
  真的能发现被执行代码里的缺陷。做法是把故障自动种进代码再跑测试。
- **cosmic-ray(Python,`https://cosmic-ray.readthedocs.io/`)** —— 同类工具的
  Python 实现。它的核心判据一句话:测试套件在被变异过的代码上通过,就说明测试与
  功能之间存在错配。
- (**mutmut**,`https://mutmut.readthedocs.io/`,同为 Python 实现,本次只用作
  "Python 生态确有成熟实现"的旁证,没有从它借具体取舍。)

**借来的三点取舍:**

1. **判据本身**:制造一个**改变行为**的变异体,测试套件杀不掉它,就是覆盖空洞。
   §2.2 - §2.4 三个变异体就是按这条判据造的,而且每一个都对应 #850 决议里的一句
   具体主张 —— M1 对应「记录不等于送达」,M2 对应「这套行为是 #850 才有的」,
   M3 对应「全量攒完一次报」。
2. **变异算子是**选**出来的,不是穷举的**。PIT 的默认算子只有 7 个,其余明确关掉,
   理由分三类:与默认算子**高度重叠**(Remove Conditionals)、**不稳定**到弱测试
   套件下也会抛空指针因而只产噪声(Constructor Calls / Non-Void Method Calls)、
   **极易产生等价变异体**(实验性的 Member Variable,变量本就初始化为默认值时,
   变异前后行为相同)。本 PR 学的就是这条:三个变异体是**挑**的,挑的标准是
   "它对应决议里的哪一句话",不是"AST 上还能改哪里"。
3. **不追求 100%**。等价变异体(改了代码但行为不变,因而**永远**杀不掉)是这门技术
   的已知硬边界,所以满分不是目标。对照组
   `test_a_fully_read_submission_still_reaches_the_model_as_phase_complete`
   在 M1 与 M2 下都 PASSED,**这正是它该有的结果** —— 它钉的是"合法输入零回归"
   这一存量行为,而两个变异体都没碰这条路径。要求每条测试杀掉每个变异体,就是把
   对照组当实验组用。

**拒掉的部分,以及本仓哪条前提让它不成立:**

- **拒绝引入变异测试框架当门禁。** 这类工具的工作方式是"每个变异体重跑一次测试
  套件",成本随变异体数量线性膨胀;`packages/graph-agent` 的套件规模摆在那里,
  本仓 CI 已有 7 道必需检查,再挂一道分钟级到小时级的作业不现实。更要紧的是本仓
  自己的教训:AGENTS.md 记着 SonarCloud「1535 open issues (9 BLOCKER)……
  a gate that is always red is a gate nobody reads」。**一道跑不完或读不完的门禁,
  和没有门禁等价。**借判据、不借工具链,是同一条经验的正面用法。
- **拒绝报告"变异得分"这个数字。** PIT / cosmic-ray 的得分是对**自动生成**的算子
  集合算比例;本 PR 的三个变异体是手挑的,分母没有意义,"3/3 杀死"是一个没有
  denominator 的数。所以 §2.5 交的是**逐变异体、逐测试的结果表**,不是一个比率。
- **诚实地说清自动化本来能做到多少。** M1 与 PIT 的默认算子 Negate Conditionals
  相当接近(把 `if parse_gap is not None` 翻过来),自动工具**很可能**也会生成它
  —— 手挑不是必要条件,这一点不夸大。但 **M2 不是任何算子能生成的**:它是
  "回退到某个具体历史提交"这种**历史变异体**,而恰恰是它抓出了空转的否定断言与
  那枚哈希硬币。自动算子看不见"这段行为是哪个 PR 引入的",人能看见。

### 拒:不改生产代码

本 PR 的默认立场是只动测试,且实际做到了(§五判据 d)。§2.2 揭示的
"副作用做叙述、返回值做投递"这条设计缝隙,今天**没有可观察的缺陷** —— 返回值确实
被用了。把它改成"叙述也由返回值携带"是一次结构性重构,应当有它自己的 PR 与论证;
在一个以"钉住现有行为"为目的的 PR 里顺手改被测对象,会让"改后杀得掉变异体"这个
结论失去意义(测试与实现同时变,证不出是哪一边起的作用)。

### 为什么解析器侧那 9 条测试不动

`tests/tools/test_md_unread_lines.py` 的 9 条断言的是 `parse_md` 的返回值
`block.meta.unread` —— 那是**它自己的输出**,不是"某处记了一笔"。M2 下 9 条全部转红
(§2.3),M1 是中间件侧的变异体,与它们无关。它们没有"账本 vs 送达"这个问题可犯:
解析器不负责送达,送达是中间件的职责。**边界清楚的测试不需要为别人的职责作证。**

---

## 五、验收判据

| # | 判据 | 结论 | 证据 |
|---|---|---|---|
| a | 切断投递的变异体被至少一条测试杀死,且该测试的断言对象是退回模型的 ToolMessage | **达成**,5 条杀死 | §2.2 实测输出;`test_the_parse_gap_comes_back_to_the_model_as_a_failed_tool_call` 断言 `reply.status == "error"` / `command.goto == "model"` / `set(command.update) == {"messages"}` |
| b | 回退到 `49f7ad0d` 的变异体被每一条相关新测试杀死,不再有空转的否定断言 | **达成**,14 failed / 1 passed,5 次重跑全同 | §2.3;唯一幸存者是对照组,理由 §四第 3 条 |
| c | `list[str]` 那一档有测试钉住,且同样杀得掉上述变异体 | **达成** | `test_truncated_data_that_satisfies_the_schema_is_refused_anyway`,M1 与 M2 下均转红 |
| d | 生产代码一行未改 | **达成** | `git diff --stat` 只有一个测试文件(§五末) |
| e | 逐条记下"改前实测杀不掉 / 改后实测杀得掉"的原始输出 | **达成** | §2.2 / §2.3 / §2.4 逐段贴出 pytest 原样输出,§2.5 汇总 |
| f | 额外:送达被截断(只发第一条错误)也要被杀死 | **达成** | §2.4,改前全绿、改后 2 条转红 |

改后 6 条测试与它们各自钉住的东西:

| 测试 | 钉住什么 | M1 | M2 | M3 |
|---|---|---|---|---|
| `test_the_parse_gap_comes_back_to_the_model_as_a_failed_tool_call` | 这一轮以失败的工具调用交回模型,且不写 `data`/`flow` | 杀 | 杀 | 活(送达形状没变) |
| `test_the_reply_to_the_model_quotes_every_unread_line_with_its_number` | 模型读到的正文里,每一行的**行号与原文同处一行** | 杀 | 杀 | 杀 |
| `test_the_verdict_details_narrate_the_parse_gap_on_a_rejected_verdict` | trace 侧叙述存在,**且它挂在 rejected 判决上** | 杀 | 杀 | 活(账本没被动) |
| `test_the_business_verdict_derived_from_truncated_data_never_reaches_the_model` | 先证 gap 上报了,再证业务校验器**没被调用**、它的判词没回给模型 | 杀 | 杀 | 杀 |
| `test_truncated_data_that_satisfies_the_schema_is_refused_anyway` | 残缺数据**通过** schema 校验(被断言的事实),但提交仍被退回 | 杀 | 杀 | 活(仍是拒绝) |
| `test_a_fully_read_submission_still_reaches_the_model_as_phase_complete` | 对照组:合法输入照旧 `PHASE_COMPLETE` | 活 | 活 | 活 |

`git diff --stat`(推送前实测):

```
 .../test_finish_task_names_unread_lines.py         | 211 +++++++++++++++++----
 1 file changed, 171 insertions(+), 40 deletions(-)
```

前端零改动,故不跑前端门禁;`git status` 佐证工作树只有一个测试文件与三份文档
(本决议、被订正的 #850 决议、台账)。

本地全门禁实测。`main` 在本 PR 开工后前进过两次,本分支跟着 rebase 了两次,
所以全门禁也跑了三轮:第一轮在 `b44c2b71`,第二轮在 `34bff961`(#853 合入后),
第三轮在 `5b1b924d`(#855 合入后,即最终推送的那个基)。**三轮全绿**,
下表是第三轮的数字,括号里是第一轮:

| 门禁 | 结果 |
|---|---|
| `ruff check packages/graph-agent` | All checks passed! |
| `mypy --strict packages/graph-agent/src` | no issues in 114 source files |
| `mypy --strict packages/graph-agent-gateway/src` | no issues in 59 source files |
| `mypy apps/studio/backend/app` | no issues in 134 source files |
| `pytest packages/graph-agent/tests`(全套) | 1579 passed, 2 skipped, 4 xfailed, 2 xpassed(第一轮 1574 passed) |
| `pytest packages/graph-agent-gateway/tests` | 618 passed, 1 xfailed(三轮同) |
| `pytest apps/studio/backend/tests`(全套) | 1733 passed, 5 skipped(第一轮 1731 passed) |
| `pip-audit` | No known vulnerabilities found |

第一轮与后两轮的 passed 数差额来自 rebase 带进来的 `main` 侧新测试,不是本 PR
的改动 —— 本 PR 只往 `packages/graph-agent/tests` 加了 2 条(4 条改成 6 条);
第二轮与第三轮数字相同。

**studio backend 全套的第一次运行报过一次 ERROR,原样记在这里,不装作没看见**:

```
ERROR apps\studio\backend\tests\routers\test_llm_registry_api.py::test_role_test_probes_thinking_on_supported_route_with_reasoning_enabled
1730 passed, 5 skipped, 2 warnings, 1 error in 250.59s (0:04:10)
```

判断依据两条,都是实测:①**其后三次全套运行都没有复现**(1731 / 1733 / 1733 passed,
零 error);②**单独跑该文件全绿**(`131 passed`)。而本 PR 改的是
`packages/graph-agent/tests` 下的一个文件与三份文档,studio backend 的测试树
不导入它。所以这是一条与本 PR 无关的既存 full-suite-only flaky,与仓内已立账的
W2-23(`test_publish` 的 git 历史用例)同族但**不是同一条**;本 PR 不夹带它的
排查,也不替它下结论——只留下这几次实测供下一个撞到的人接。

---

## 六、顺带订正:#850 决议里一处已变假的措辞

`.kiro/specs/decision-2026-08-16-parse-md-reports-what-it-did-not-understand.md`
的 §2.2 与 §六第 4 条说模型看到的出口契约"只被告知写 `- parsed_segments: <值>`"、
"骨架只有 `- name: <值>`"。**复核实测不成立**:同一个函数
`cognitive/prompt.py:48-70` `_render_business_data_md_skeleton` 在 `:65` 渲染 bullet
骨架之后,`:67-69` 还并列渲染了第二种整体形态:

```
    lines.append(
        "（也可以把整个对象写成一个 JSON 对象，放在 `## ` 标题下的 ```json 代码块里。）"
    )
```

这三行由 #825(`f9a32905`)引入,早于 #850 写作时的 HEAD `59e74020`(实测
`git show 59e74020:.../prompt.py` 的 61-70 行含这三行),所以它是**写作当时就存在**
的事实,不是后来才变的。#850 §2.2 的**代码引文本身是完整的**(它包含了这三行),
不准确的是紧随其后的那句散文小结。

**该决议要立的实质论点不受影响**:两种形态都只说到"这里放一个值"为止,一个
`list[dict]` 字段该长什么样,契约里仍然一个字都没有。已按事实订正措辞、保留论点,
并在该文件新增 §七校订记录写清动了哪一句、为什么动、以及它与"有日期的裁决记录
不回头改"这条原则为何不冲突(改的是当时就不准确的描述,不是追改当时正确的记述)。

---

## 七、已知遗留(明写,不装作解决)

1. **同一份 schema 在不同进程里生成出不同的模型类名 —— 与本缺陷无关的生产侧问题,
   本 PR 不修。** 这是 §2.3 那枚"硬币"的根因,查到底了,原样记在这里。

   `core/schema_engine.py:648-651`:

   ```python
   def _model_name_for_schema(schema: SchemaObject) -> str:
       base = schema.schema_name if _SCHEMA_NAME_RE.match(schema.schema_name) else "BusinessSchema"
       digest = hashlib.sha256(repr(schema).encode("utf-8")).hexdigest()[:8]
       return f"{base}_{digest}"
   ```

   `repr(schema)` 里含 `required_fields=frozenset({...})`,而 `frozenset` 的 repr
   顺序取决于元素哈希 —— Python 默认开启字符串哈希随机化,于是**同一份 schema、
   同一份代码,不同进程得到不同的 digest**。三次连跑实测(原样):

   ```
   BusinessSchema_316d962c | ... required_fields=frozenset({'segments_summary', 'parsed_segments'}) ...
   BusinessSchema_0528e101 | ... required_fields=frozenset({'parsed_segments', 'segments_summary'}) ...
   BusinessSchema_316d962c | ... required_fields=frozenset({'segments_summary', 'parsed_segments'}) ...
   ```

   影响面已核:这个名字通过 `_validate_finish_args` 的
   `schema_label = getattr(model, "__name__", ...)` 进入 `story` → 判决事件的
   `details` → trace,**不进退回模型的 `errors`**。所以后果是 trace 叙述不可复现
   (同一次逻辑相同的运行,两次跑出两个名字),不是模型侧行为差异。
   **不在本 PR 修的理由**:它与"测试钉住送达"是两件事,一个 PR 一个任务;而且
   修它要动 `packages/graph-agent` 的生产代码(把 `repr` 换成顺序无关的规范化摘要),
   属于另一次改动的范围。已另行立项。

   顺带说清:本 PR 改后的那条 details 测试不受它影响 —— 断言换成了
   `any("5" in detail and "unread" in detail for detail in verdict.details)`,
   要求 `"5"` 与 `"unread"` **出现在同一条 detail 里**,而含 `unread` 的那句
   `parse_md left 5 line(s) ... unread` 是 `_parse_gap_validation` 自己写的、
   与 schema 名无关。M2 下 6 次运行结果完全一致(§2.3),就是这条断言不再掷硬币的
   直接证据。

2. **本 PR 没有把变异分析变成可重复的仓内资产。** 那份矩阵脚本留在 scratchpad 的
   一次性副本里,随会话消失。这是刻意的(§四"拒绝引入变异测试框架当门禁"),
   代价是下一个人想复核这三个变异体,得照 §2.0 - §2.4 的描述自己再搭一次。
   要不要把"某个决议的核心承诺配一个具名变异体"变成常规做法,是一个更上位的问题,
   不在本 PR 范围。

3. **只覆盖了 parse-gap 这一条判决通道。** `_validate_finish_args` 里其余会驳回的
   阶段(空 `business_data_md`、零 `##` 块、markdown 解析异常、schema 错误、
   业务校验错误)的测试是否同样只断言账本,本 PR **没有逐条核过**,不声称它们没问题。
   本 PR 修的是 #850 那 13 条;把同一把尺子量到整个 `cognitive_flow` 测试面,
   是另一件事。
