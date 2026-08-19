# 决议 2026-08-19:一份 schema 的模型名,只由这份 schema 决定

状态:已实施(本 PR)
影响模块:engine(`packages/graph-agent`)
发现方式:后台任务提示「Fix nondeterministic generated schema model name」,
由用户在 2026-08-19 指派修复

---

## 一、决策

`SchemaEngine` 给它建的每个 Pydantic 模型命名为 `<schema_name>_<digest>`。
**digest 必须是这份 schema 身份的函数,不是它某次渲染的函数。**

具体两条:

1. digest 改为对一份**规范化的 key** 取 sha256,不再对 `repr(schema)` 取。
   规范化 key 由 `_canonical_schema_key` 显式构造:无序容器排序、映射按键排序、
   类型用 `module.qualname` 命名,最后经 `json.dumps(..., ensure_ascii=True,
   separators=(",", ":"))` 序列化。
2. key **只读参与相等判定的字段**。`raw_schema_dict` 被 dataclass 标了
   `compare=False, hash=False`,因此它不属于身份,不进 key。

---

## 二、论据

### 2.1 缺陷现场(先复现,再动手)

修前 `packages/graph-agent/src/graph_agent/core/schema_engine.py:648-651`:

```python
def _model_name_for_schema(schema: SchemaObject) -> str:
    base = schema.schema_name if _SCHEMA_NAME_RE.match(schema.schema_name) else "BusinessSchema"
    digest = hashlib.sha256(repr(schema).encode("utf-8")).hexdigest()[:8]
    return f"{base}_{digest}"
```

同一份 schema、六个不同的 `PYTHONHASHSEED`,得到**六个不同的名字**(本机实测原样):

```
0 Segment_aca0db6a
1 Segment_d66e4cc3
2 Segment_0b54a852
3 Segment_dad8e6f1
4 Segment_63e5a222
5 Segment_d7700148
```

### 2.2 为什么是 `repr`

`SchemaObject` 是 `@dataclass(frozen=True)`(`schema_engine.py:35-52`),它的
`__repr__` 由 dataclass 生成。两处东西因此进了 digest:

1. **`required_fields: frozenset[str]`**(`:46`)。frozenset 的迭代顺序由元素的
   哈希决定,而 str 哈希**逐进程随机**(`PYTHONHASHSEED`)。独立验证,同一个
   五元素集合在四个种子下的 repr:

   ```
   frozenset({'paragraph_indices', 'location', 'summary', 'title', 'event_type'})
   frozenset({'location', 'title', 'summary', 'paragraph_indices', 'event_type'})
   frozenset({'location', 'paragraph_indices', 'summary', 'title', 'event_type'})
   frozenset({'paragraph_indices', 'title', 'location', 'summary', 'event_type'})
   ```

2. **`raw_schema_dict`**(`:48`)标了 `compare=False, hash=False` —— 即作者已经
   裁定它**不属于这个对象的身份**;但 dataclass 的 repr 仍然打印它(排除 repr 要
   另加 `repr=False`)。后果:两个 `==` 的 `SchemaObject` 可以拿到两个不同的模型名。
   这一条在**单进程内**就能观测,不需要动哈希种子。

### 2.3 说准确:这不是"哈希随机化的锅"

`PYTHONHASHSEED` 随机化是 Python 的既定行为(抵御哈希碰撞 DoS),不是缺陷。
缺陷是**拿一个顺序不稳定的渲染去做内容寻址**。同一条错误也不限于 frozenset:
只要 key 的构造依赖任何无序容器的迭代顺序,结论都一样。所以修法不是"把
frozenset 换成 tuple",而是**在算 key 的地方就把顺序定下来**。

---

## 三、修在哪一层,为什么不是另一层

修在 `_model_name_for_schema` 取 digest 的那一步,即**唯一**用得着规范化的地方。

**拒绝**把 `required_fields` 的类型从 `frozenset` 改成有序容器:那会改掉一个
被 `lru_cache` 当键用的公开数据结构(`schema_engine.py:37-43` 的 docstring 明写
"safe as an `lru_cache` key"),为了一个命名问题去动身份类型,代价与收益不成比例;
而且 frozenset 语义本身是对的 —— 必填字段就是一个集合。

**拒绝**给 `SchemaObject` 加 `repr=False` 到 `raw_schema_dict`:那只解决第二条,
frozenset 那条纹丝不动,且会让调试输出变哑。

**拒绝**"把 digest 去掉、只用 `schema_name`":`_SCHEMA_NAME_RE` 不匹配时会退到
`BusinessSchema`,不同 schema 会撞名。第三条测试
`test_different_schemas_still_get_different_model_names` 就是钉住这条捷径的。

---

## 四、借了什么,拒了什么

**借 JSON Canonicalization Scheme(RFC 8785)**:先给成员定死顺序,再经 JSON
序列化,让**编码本身是单射的**。第二半和第一半同样重要 —— 只排序不管分隔,
用一个"应该不会撞"的分隔符把片段拼起来,仍然可能让两份不同的 schema 拼出同一个串
(本 PR 的中间版本正是这么写的,随后被推翻)。

**拒绝** RFC 8785 的数字规则、Unicode 规则与互操作承诺:这个 key 从不被解析回来、
从不落盘、也从不跨本模块的版本比较,它只需要在一次构建之内单射且稳定。

**拒绝** git 那种"内容寻址即持久身份"的取舍:git 的 object id 要跨仓库跨年份稳定,
所以格式必须冻结;这里的名字活在一个进程的类型对象上,冻结格式只会换来一份
永远不能改的规范。

---

## 五、验收判据与实测

| # | 判据 | 修前 | 修后 |
|---|---|---|---|
| a | 同一 schema 在四个不同 `PYTHONHASHSEED` 的**新解释器**里得到同一个名字 | FAILED | passed |
| b | 两个 `==` 但 `raw_schema_dict` 不同的 schema 得到同一个名字 | FAILED(`Article_eab1b5b3` vs `Article_26a1236c`) | passed |
| c | 字段名/必填性/字段类型任一不同的四份 schema 仍得到四个不同的名字 | passed | passed |

RED 实测原样:`2 failed, 1 passed`。GREEN:`3 passed`。
全套引擎测试 `1580 passed, 2 skipped, 4 xfailed, 2 xpassed`,零回归;
`ruff` All checks passed;`mypy --strict` 114 files Success。

判据 a 只能靠子进程观测 —— `PYTHONHASHSEED` 只在解释器启动前可设。
测试用 `sys.executable` 直接起子进程(不经 `uv run`),四个种子约 8 秒。

---

## 六、已知遗留(明写,不装作解决)

1. **`_canonical_key` 对它不认识的值退回 `repr(value)`。** 今天走到这一支的只有
   标量与 `None`(`field_defaults` 来自 `<output_example>` 的 JSON/YAML,产出
   dict/list/str/int/bool/None,已各有分支)。若将来有人往描述符里放一个自定义
   对象,它的 repr 若含内存地址,同一个病会以新形态回来。**没有**为此加防御:
   那要求给每种可能的值定义规范形式,而现在并不存在这样的值(YAGNI)。
2. **本 PR 没有考证"名字到底流到哪里"。** 后台任务提示说它让 run trace 不可复现;
   我核实到的是**名字确实随进程变**(§2.1),但没有逐条追它进入 prompt / trace /
   错误消息的路径。修的理由不依赖那条:一个内容寻址的名字随进程变化,本身就是缺陷。
3. **`SchemaObject.__repr__` 仍然打印 `raw_schema_dict`。** 本 PR 只让 digest 不看它;
   repr 是否该排除它是另一个问题(会影响调试输出),没动。
