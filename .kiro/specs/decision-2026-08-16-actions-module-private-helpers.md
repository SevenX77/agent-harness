# 决议:`actions:` 声明清单是 action 注册表,模块里其余函数是普通私有 helper

- 日期:2026-08-16
- 范围:engine(`packages/graph-agent/src/graph_agent/core/loader.py`、`core/cache.py`)
- 状态:已实施

## 1. 问题

2026-08-16 编译 `D:/coding/skills/story-deconstruction-v3-lab` 报出:

```
action '_addressable_units' must accept exactly one inputs parameter
action '_entity_ids' must accept exactly one inputs parameter
```

这两个名字**既不在**各自 `LOGIC.md` 的 `actions:` 清单里,**也从未**被当作 action 调用。
它们是作者写的普通私有 helper。后果是:**skill 作者不能在 `actions/*.py` 里写模块级
私有函数**——凡是签名不是 `(inputs)` 的都会被当成 action 拒绝。

作者已经在自己踩出绕法:`assemble_batch.py:49` 的 `_normalized_accumulator_state`、
`prepare_batch.py:25` 的同名函数、`build_scene_stream.py:9` 的 `_entity_ids`,今天全部
**嵌在 action 函数体内部**(缩进的 `def`)。而 `prepare_chapter.py:78` 的
`_resolve_chapter(inputs)` 留在模块级并通过编译,**纯粹因为它恰好只有一个叫 `inputs`
的参数**——一个和它是不是 action 毫无关系的巧合。

## 2. 三问举证

### 2.1 `actions:` 清单是不是"哪些函数是 action"的权威?是。未声明函数不可能被派发

**派发唯一入口**是 `core/graph_assembler.py:1560,1566-1567`:

```python
action_names = phase_ast.actions
...
for action_name in action_names:
    action = compiled.actions.resolve(phase_id, action_name)
```

`compiled.actions.resolve` 是 `ActionRegistry` 唯一的执行取值口(`core/actions.py:33-42`),
全仓只有这一处调用它。喂给它的名字只来自 `phase_ast.actions`。

**声明本身是被钉死的**:`loader.py:2802-2809` `_validate_logic_actions_declared` 要求
frontmatter `actions:` 与 body `<action>` 序列**完全相等**(顺序也要一致),否则编译失败。
所以"声明清单"不是一个松散提示,而是一份精确、有序、双份互校的名单。

结论:**一个不在 `actions:` 里的函数,在引擎里没有任何可达路径。** 拿 action 的签名规则
去校验它,是对一个永远不会被当作 action 使用的对象施加 action 的约束——越权。

### 2.2 设计源有没有说 actions 模块是"只放 action 的扁平命名空间"?没有。而且它把规则**限定到了声明名**

格式真相源是 `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`——
`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:26-30` 明写"如果本文、
baseline、fixture、代码注释或历史迁移文档与 `skill-spec/00-FORMAT-GROUND-TRUTH.md` 冲突,
以 `skill-spec/00` 为准"。该文件 §3 `LOGIC.md`:

> \| `actions` \| yes \| list[string] \| action 名注册表 \|
>
> LOGIC action 源文件位于 `phases/<phase_id>/actions/<action_name>.py`。文件必须导出
> 同名函数,签名严格为 `def <action_name>(inputs) -> dict`。

两件事:`actions` 被定义为**注册表**(registry,即"名单");签名规则的主语是
**`<action_name>`**——那个被声明的名字,不是"文件里的每个函数"。

我另外查了 `docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md:25`
(`actions/<action_name>.py  # LOGIC 本地 action(可选)`)、
`03-compile-rules/mvp1-alignment.md` 的决策 CR2(:388)与 LE1-3(:391)、以及
`02-skill-syntax/mvp1-alignment.md` 全文:**没有任何一句**说 `actions/` 是只允许放
action 的扁平命名空间,也没有任何一句禁止模块级 helper。所以现状**不是** as-designed,
是实现漂移。

反过来,**purity 的范围设计源说得很清楚,而且是文件级**——
`03-compile-rules/mvp1-alignment.md:79`:

> \| Purity 校验 \| **action/tool Python 文件** \| purity report \| action 必须纯 … \|

主语是**文件**。所以 helper 一样要被 purity 扫描——helper 和 action 一样能写文件。

### 2.3 现在这条报错信息是误导的

它把 `_addressable_units` 称作 "an action",而作者从未把它声明为 action。更糟的是它用的
错误码 `[F-v3-logic-action-entrypoint-missing]` 在注册表里的定义是
(`03-compile-rules/mvp1-alignment.md:288`)"action 无 `run()`"——即**声明了的 action
找不到入口**。用一个"东西缺失"的码去报告"这个我们本不该看的函数签名不对",标签和事实
方向相反。

## 3. 根因

`loader.py` 修复前:

- `:1419-1420` `_load_action_dir` 对 `_module_functions(module)` 的**每一个**函数调用
  `_validate_action_signature` 并注册成 `ActionDef`;
- `:1494-1499` `_module_functions` 返回模块内定义的全部函数,含 `_` 开头的私有函数;
- `:1502-1519` `_validate_action_signature` 于是对 helper 报出上面那条消息。

也就是说,注册表**由文件系统推导**(扫出什么就是什么),而设计里注册表**由声明给定**。
真正坏掉的是这一层的信息流向,不是签名校验本身。

## 4. 决定

**注册表以声明为准。** `_load_action_dir` 改为接收本相位声明的 `actions:` 清单:

1. 只有名字出现在声明清单里的模块级函数,才做 `_validate_action_signature` + 注册
   `ActionDef`;其余函数直接跳过,不当作 action。
2. `_raise_on_purity_violations(path)` **位置不动**,仍在进入函数循环之前对整个文件执行
   ——按 §2.2 的设计,purity 是文件级的。
3. 补上对称的一半:**声明了却找不到同名函数**,编译期 FATAL
   `[F-v3-logic-action-entrypoint-missing]`,消息写明"声明了 X 但 `actions/` 里没有名为
   X 的函数"。诊断锚点优先落在 `actions/<name>.py`(设计规定的文件名),该文件不存在时
   落在 `actions/` 目录。

第 3 条不是搭车改动,是第 1 条的必要另一半。把注册表从"文件系统推导"改成"声明给定"之后,
"声明了但没实现"从一个**不可表示的状态**变成了一个**可表示且静默**的状态:改动前它靠
"什么都注册"碰巧不会静默,改动后如果不补这一条,作者把 `foo` 写成 `Foo` 就只会在运行期
拿到 `KeyError: unknown action 'foo'`。仓规「Fail fast,在边界校验」「能在编译期挡住的
错误,不留给运行期」要求它落在编译期。它同时让 `[F-v3-logic-action-entrypoint-missing]`
第一次真正表达注册表里写的那个意思(见 §2.3)。

**顺带收敛的重复参数**:`_discover_actions_and_tools(skill_root, discovered)` 的
`discovered`(`list[tuple[phase_id, path, mode]]`)与 `phase_docs` 是同一批数据的两份
形状——`cache.py` 里那份甚至就是 `[(node.phase_name, node.path, node.mode) for node in nodes]`
现搓出来的。既然要拿 `doc.ast.actions`,就直接传 `phase_docs`,把 `discovered` 参数删掉,
而不是新增第三个并行参数。`loader.py:285-293,388-389` 保证到调用点时 `phase_docs` 与
`discovered` 一一对应且非空——任一相位文档解析失败会在 `:388` 先行 raise。

相位分支判据同时由 `mode == "logic"` 改为 `isinstance(doc.ast, LogicNodeAST)`:类型本身
就承载了 mode,这样取 `doc.ast.actions` 不需要 `assert` 之类的防御性窄化。

### 4.1 一并修正的 fixture 漂移

新诊断上线后立刻抓到一处存量缺陷:`packages/graph-agent/tests/test_graph_io_target_declaration.py`
的 fixture 声明 `actions: [draft]`,而 action 文件里写的是 `def run(inputs)`——**mvp0**
的入口约定(`docs/engine/mvp0/skill-spec/03-logic-md-spec.md:94`「action 模块无 `run`」)。
按 AGENTS.md「MVP1 design = source of truth」,改 fixture 对齐设计(`def draft(inputs)`),
不是放宽检查。这个 skill 一旦真跑就会 `KeyError`,只是该测试只编译不执行,以前谁也没发现。
全仓 `packages/graph-agent/tests` 下只有这一处。

## 5. 参考的成熟做法

- **Python 自己的 `__all__` / `_` 前缀约定**:模块的**公开面由显式声明决定**,模块里其余
  名字是实现细节。**借的就是这一件事**:一个命名空间同时容纳"对外契约"和"内部 helper"
  是常态,区分二者的是声明而不是"文件里有什么"。
- **pytest 的收集规则**:`test_*` 前缀决定哪些函数是测试项,同一文件里的其他函数是
  fixture 和 helper,收集器不对它们施加测试项的签名要求。**借的是"只对被选中的对象施加
  该角色的规则"**。
- **拒绝了 pytest 的"按命名模式选中"**:pytest 靠前缀约定隐式选中,本仓不这么做——
  `actions:` 已经是一份**显式的、与 body 双份互校的**名单,再叠一层"`_` 开头即 helper"
  的隐式规则就有两个真相源。**判据只有一个:名字在不在声明清单里。** 一个声明为
  `_internal_step` 的 action 照样是 action(虽然没人该这么写),因为它被声明了。
- **同一份 loader 里的既有先例**:`loader.py:315-338` 对 `validator.py` 的检查就是这个
  形状——`validator: true` 声明在先,然后检查文件里是否存在**顶层名为 `validate` 的
  函数**,不存在就报 `[F-v3-logic-validator-entrypoint-missing]`。§4 第 3 条是把同一条
  纪律补到 action 上。

## 6. 明确不在本次范围内

- **文件名与 action 名的绑定不做强制。** 设计源说 action 应在
  `actions/<action_name>.py`,但 loader 一直是 glob 整个目录、按**函数名**匹配,与文件名
  无关;仓内 fixture(如 `tests/core/test_action_registry_v030.py:59`)也依赖这一点。
  强制文件名是另一条独立的漂移,该单独立项。
- **相位声明了 `actions:` 却整个 `actions/` 目录都不存在**,今天没有任何诊断
  (`loader.py:955` 的 `if actions_dir.exists()` 是唯一入口)。改动前后行为一致,不构成
  回归;这是 `[F-v3-logic-action-dir-missing]` 该覆盖而未覆盖的既有缺口,单独立项。

## 7. 验收判据

`packages/graph-agent/tests/core/test_action_module_private_helpers.py`:

1. `test_module_level_private_helper_is_not_validated_as_an_action` —— lab skill 的原始
   形状(模块级 `def _entity_ids(rows, id_key)` 与声明的 action 并列),编译必须通过,
   且 `compiled.actions.for_phase("logic") == ["compute"]`。修复前实测报出与真实 skill
   **逐字相同**的 `action '_entity_ids' must accept exactly one inputs parameter`。
2. `test_undeclared_helper_never_reaches_the_graph` —— 零参数 helper 不被注册,图能跑通
   并产出正确结果。
3. `test_declared_action_with_a_bad_signature_is_still_compile_fatal` —— 护栏:被**声明**
   的 action 签名错了,仍然编译期 FATAL(修复前后都绿,防止改动越界)。
4. `test_declared_action_without_a_matching_function_is_compile_fatal` —— §4 第 3 条;
   修复前实测 `DID NOT RAISE`(即静默放行)。
5. `test_helper_impurity_is_still_a_compile_fatal` —— helper 里 `open(...,'w')` 仍触发
   `[F-v3-logic-action-purity-violation]`,证明 purity 保持文件级范围。

真实 skill 上的因果闭环(scratchpad 副本,`text-segmentation` 子图 + 补回模块级
`_entity_ids`):旧 loader → `[F-v3-logic-action-entrypoint-missing] ... action
'_entity_ids' must accept exactly one inputs parameter`;新 loader → `COMPILE OK`。
