# 决议:引擎自己说出它往 checkpoint 里放了哪些类型

日期:2026-08-18
分支:`fix/engine-state-types-in-the-msgpack-allowlist`
台账行:W2-27

---

## 一、决策

引擎在 `packages/graph-agent/src/graph_agent/core/checkpointer.py` 里**显式声明**它会
写进 checkpoint 的自有类型,并把这份声明装到**每一个由引擎自己造出来的 checkpointer**
上。声明只有一处:

```python
# checkpointer.py:35
CHECKPOINT_STATE_TYPES: tuple[type[BaseModel], ...] = (BusinessData, FrameworkState)
```

三条落地:

1. `checkpoint_serde()`(checkpointer.py:53)返回一个**带显式白名单**的
   `JsonPlusSerializer`。显式白名单会让 langgraph 完全**不看** `LANGGRAPH_STRICT_MSGPACK`
   这个进程级环境变量——引擎是纯 SDK,不替宿主决定进程环境,也不允许自己的 checkpoint
   因为宿主怎么设环境变量而有两种回读结果。
2. `checkpointer_context()` 的三条后端路径全部装上它:memory 走构造参数
   (checkpointer.py:120),sqlite / postgres 走 `_adopt_checkpoint_serde()` 赋值
   (checkpointer.py:133、148),因为这两条后端由 `from_conn_string` 建,那个类方法自己
   管连接、不转发 serializer。
3. `graph_assembler._build_skill_node` 里那个"调用方没给 checkpointer 就自己造一个"
   的兜底同样装上(graph_assembler.py:2196)。规则是一致的:**引擎造出来的 saver,
   引擎就得告诉它引擎的状态类型**,因为没人能预判后面会往它里面写什么。

同时**明确不做**一件事:引擎不去改调用方递进来的 checkpointer(理由见第三节)。给
自建 saver 的宿主留的口子是公开的 `checkpoint_serde()`——
`InMemorySaver(serde=checkpoint_serde())` 装得下引擎状态,裸 `InMemorySaver()` 装不下。

---

## 二、论据

### 2.1 现场:状态过一次 checkpoint 就丢类型

在 `origin/main`(59e74020)上,开严格模式跑引擎全套(实测原样):

```
$ LANGGRAPH_STRICT_MSGPACK=true uv run pytest packages/graph-agent/tests -q

>       assert res["flow"].subagent_validation_retries == {"call_subagent_child_expert": 2}
E       AttributeError: 'dict' object has no attribute 'subagent_validation_retries'
packages\graph-agent\tests\core\test_ws_e1_create_agent_step1.py:935: AttributeError

1 failed, 1571 passed, 2 skipped, 4 xfailed, 2 xpassed in 91.00s
```

`res["flow"]` 存进去时是 `FrameworkState`,取回来是**裸 dict**,于是第一次属性访问当场
炸。不开严格模式时不炸,但每个进程都会刷警告(同一次全套跑的实测捕获):

```
Deserializing unregistered type graph_agent.core.state.BusinessData from checkpoint.
This will be blocked in a future version. ...
Deserializing unregistered type graph_agent.core.state.FrameworkState from checkpoint. ...
```

### 2.2 机制:langgraph 的三档语义

`.venv/Lib/site-packages/langgraph/checkpoint/serde/jsonplus.py:107-118`,
`JsonPlusSerializer.__init__` 在没传 `allowed_msgpack_modules` 时按环境变量分岔:

```python
if allowed_msgpack_modules is _lg_msgpack._SENTINEL:
    if _lg_msgpack.STRICT_MSGPACK_ENABLED:
        # Strict: only SAFE_MSGPACK_TYPES are allowed.
        allowed_msgpack_modules = None
    else:
        # Permissive (default): all types allowed with a warning.
        allowed_msgpack_modules = True
```

真正判定在 `jsonplus.py:559-609` 的 `_check_allowed`,一共三档:

| `allowed_modules` 的值 | 安全表内的类型 | 其它类型 |
|---|---|---|
| `True`(宽松,**当前默认**) | 重建 | 重建 + 每进程每类型警告一次 |
| `None`(严格,即设了环境变量) | 重建 | **拒绝重建,原样返回 payload dict** + 警告 |
| 一个有限集合(**显式传入**) | 重建 | 集合内重建;集合外拒绝 + 警告 |

第三档不看环境变量。这就是决策 1 的全部依据:**只有显式传白名单,行为才与宿主环境
无关**。安全动机是 langgraph 自己写在 `jsonplus.py:56-62` 的类文档里:能往
checkpoint 库里写数据的人,否则可以点名任意可导入的类型让加载器去构造。

`STRICT_MSGPACK_ENABLED` 在 `_msgpack.py:12` **模块导入时**读一次环境变量,所以严格
模式无法在已经导入过 langgraph 的进程里打开——第五节的探针必须开子进程,原因就在这。

### 2.3 声明表是完整的(实证,不是推断)

不靠通读代码猜"引擎到底往 checkpoint 里放了什么",直接量:给 pytest 挂一个 handler,
把 `langgraph.checkpoint.serde.jsonplus` logger 的每一条相关警告落盘,跑**全套 1572 条
测试**。修复前、宽松模式下的去重结果,全仓只有两条:

```
Deserializing unregistered type graph_agent.core.state.BusinessData ...
Deserializing unregistered type graph_agent.core.state.FrameworkState ...
```

严格模式下同样只有这两条(措辞变成 `Blocked deserialization of ...`)。`messages` 通道
里的 langchain 消息模型不出现,是因为 `_msgpack.py:56-73` 的 `SAFE_MSGPACK_TYPES` 已经
内置覆盖了它们。所以 `CHECKPOINT_STATE_TYPES` 取 `(BusinessData, FrameworkState)` 是
量出来的,不是猜的;也因此换成有限白名单**不会误伤**任何别的类型(第五节复测为零)。

---

## 三、为什么修在这一层,而不是另一层

### 3.1 为什么是 checkpointer 工厂,而不是 Studio 适配层

因为生产路径**百分之百**从工厂出:

- 引擎自跑:`runner.py:2134` `active_checkpointer = resolve_checkpointer(checkpointer_spec)`。
- Studio 续跑:`apps/studio/backend/app/core/adapters/runtime_state_store_local.py:274-276`
  `from graph_agent.core.checkpointer import resolve_checkpointer` → `resolve_checkpointer(checkpointer_arg)`,
  参数是 `"sqlite:<path>"` 这样的字符串 spec,进 `_parse_and_get_checkpointer` 再进
  `checkpointer_context`。

机械核对:`grep -rn "InMemorySaver|SqliteSaver|PostgresSaver|MemorySaver" --include=*.py
apps/ packages/graph-agent-gateway` **零命中**。引擎核心之外没有任何地方自己造 saver,
所以工厂这一处修完,生产侧不需要任何改动——Studio 一行没动。

### 3.2 为什么不在 `assemble_graph` 边界上给调用方的 checkpointer 打补丁

langgraph 提供了正好干这件事的 API:`BaseCheckpointSaver.with_allowlist`
(`base/__init__.py:713-722`,"Return a shallow clone with a derived msgpack allowlist"),
它还会正确处理 `EncryptedSerializer` 包装(`base/__init__.py:730-736`)。看上去它比
工厂方案更"覆盖得广",而且用上它就能免掉本 PR 里那 6 个测试文件的改动。**否掉它,有
两条硬理由:**

**理由一:它返回的是克隆,会把同一份 checkpoint 劈成两种读法。** 触发本缺陷的那条用例
自己就是证据——`test_ws_e1_create_agent_step1.py:913-931`,它把 saver 递给
`assemble_graph`,然后**用自己手里那个 saver 对象**回读:

```python
saver = InMemorySaver()
graph = graph_assembler.assemble_graph(..., checkpointer=saver).graph
graph.invoke(...)
checkpoint_state = saver.get_tuple({"configurable": {"thread_id": "run-1"}})
res = checkpoint_state.checkpoint["channel_values"]
```

如果 `assemble_graph` 内部克隆一份带白名单的 saver,图自己读得对,而调用方手上这个
对象读同一批数据仍然拿回裸 dict。这不是假想:Studio 就是这么用的——
`apps/studio/backend/app/core/adapters/engine.py:1192` 拿自己那个 checkpointer 去
`_runtime_state_latest_checkpoint_state(...)` 做带外回读。**同一份 checkpoint 因为你
用哪个把手去问而反序列化出不同结果,比干脆读不出来更坏**,因为它不报错。

**理由二:宽松模式下它是空操作。** `jsonplus.py:133-134`:

```python
base_allowlist = self._allowed_msgpack_modules
if base_allowlist is True or base_allowlist is False:
    return self
```

宽松档的底集就是 `True`,合并任何"额外允许"都返回原对象。所以在 CI 实际跑的默认模式
下,`with_allowlist` 一个字都改不了,`Deserializing unregistered type` 照刷——验收判据
(c) 直接不成立。

反过来"直接改调用方 saver 的 `.serde`"更不行:那会把调用方自己包的东西(加密就是典型)
无声丢掉。所以边界上什么都不做,把 `checkpoint_serde()` 公开出去,让自建 saver 的宿主
拿一个**唯一的**序列化器,自己装到自己的对象上。这条取舍写在代码注释里
(checkpointer.py:84-95),不留在聊天记录里。

### 3.3 为什么 sqlite/postgres 是赋值而不是构造参数

`SqliteSaver.__init__` 收 `serde`(`sqlite/__init__.py:85-95`),但
`SqliteSaver.from_conn_string`(:97-124)不转发——它自己 `sqlite3.connect` 并管着连接
生命周期。自己接管连接去换构造参数,等于把 langgraph 的连接配置(`check_same_thread=False`
等)抄一份到本仓,抄错了还没人发现。`.serde` 是被支持的写入位:langgraph 自己在
`base/__init__.py:719` 的 `with_allowlist` 里就是 `clone.serde = maybe_add_typed_methods(serde)`。
另外已核实:langgraph 没有任何按环境变量自动包加密 serde 的逻辑(全仓 grep
`EncryptedSerializer` 只有 `base/__init__.py` 的 `with_allowlist` 分支和它自己的模块),
所以这里赋值不会覆盖掉任何东西。

---

## 四、上一轮半成品:留了什么、推翻了什么

上一位实现席断线时留下 8 改 2 新。逐项审过:

**留下(站得住)**

- `CHECKPOINT_STATE_TYPES` + `checkpoint_serde()` + `_adopt_checkpoint_serde()` 的整体
  形状。第二节的实证支持它:两个类型确实是全集,显式白名单确实是唯一与环境无关的档位。
- `graph_assembler.py` 那一行。**它不是绕报错的症状补丁**:那是引擎"调用方没给就自己
  造"的兜底 saver(`checkpointer or InMemorySaver(...)`),属于"引擎造的"那一类,与工厂
  适用同一条规则。改动只有构造参数,没有动任何控制流。
- 6 个既有测试文件的改动。**逐个核对过不是把断言改松**:机械检查
  `git diff -- packages/graph-agent/tests/ | grep -E "^[-+].*assert"` **零输出**——一条
  断言都没被碰过,改的全是 saver 的构造方式。其中 5 个文件把 `InMemorySaver()` 换成
  `InMemorySaver(serde=checkpoint_serde())`,1 个文件
  (`test_v030_deltachannel_checkpoint.py`)把直接 `SqliteSaver.from_conn_string` 换成
  引擎自己的 `checkpointer_context`。保留的理由:测试里那个自建 saver 就是在扮演"自建
  saver 的宿主",裸 saver 是生产里不存在的配置,让测试用受支持的构造方式是**对齐契约**,
  不是为求变绿。
- `_engine_checkpoint_roundtrip_probe.py`。**它不是遗留垃圾,是正式测试的一部分**:
  `test_checkpoint_state_type_registry.py` 用子进程跑它,而子进程是必需的——第 2.2 节已
  给出依据,`LANGGRAPH_STRICT_MSGPACK` 在 `_msgpack.py:12` 于**导入时**读取,pytest 进程
  早就导入过 langgraph,进程内改环境变量无效。文件名前导下划线避开 pytest 的
  `test_*.py` 收集(仓内 pytest 配置未自定义 `python_files`,走默认)。

**推翻/改掉**

- `packages/graph-agent/spec/round28-manifest-schema.yaml` 的改动:`git diff
  --ignore-cr-at-eol` 输出为空,纯 CRLF 幽灵 diff,已 `git checkout --` 丢弃。
- `graph_assembler.py` 里那个函数内的局部 import 改到模块顶层(:52)。已核实无环:
  `checkpointer.py` 只依赖 `core.state`,而 `core/state.py` 的 import 里没有引擎模块。
  该文件本来就有 40 多条顶层 `graph_agent.core.*` import,局部 import 是不必要的例外。
- `_adopt_checkpoint_serde` 的文档串重写。原文只写了"不动调用方的 saver,因为会丢加密",
  漏掉了真正的决定性理由(第 3.2 节的两条),也没记下 `with_allowlist` 这个被否掉的
  备选。取舍不写下来等于没做过取舍。
- 新测试里 `_already_walked` 的 `seen` 从 `set[int]` 改成 `dict[int, Any]`。只存 id 不
  存对象,CPython 可以把已回收对象的 id 分配给新对象,于是一棵没走过的子树被当成走过
  ——**这个门禁一旦失效是"漏过去"而不是"报错"**,是它最不能有的失效方向。
- 新测试的 `_reachable_models` 拆成三个小函数。原版圈复杂度 11,踩 ruff C901(仓内
  `packages/graph-agent/pyproject.toml:71` 显式 `extend-select = ["C901"]`)。拆完复跑
  第五节的变异验证,门禁照样咬得住。
- 探针子进程补 `PYTHONIOENCODING=utf-8`。子进程的 stdout/stderr 是管道,CPython 会用
  本机 locale 代码页(本机是 cp936)编码,而父进程按 utf-8 解码——`CROSS_PLATFORM.md`
  的显式编码铁律正是为这种情况。

---

## 五、验收判据与实测

| 判据 | 结果 |
|---|---|
| (a) 严格模式下带 checkpoint 往返的相位执行,`flow` 仍是 `FrameworkState`、`data` 仍是 `BusinessData` | 达成。探针实测输出 `memory data=BusinessData flow=FrameworkState` / `sqlite data=...`,两种 msgpack 模式各一遍 |
| (b) 第 2.1 节那条实测失败用例在严格模式下通过 | 达成。`LANGGRAPH_STRICT_MSGPACK=true` 跑全套:`1577 passed, 2 skipped, 4 xfailed, 2 xpassed`(修复前是 `1 failed, 1571 passed`) |
| (c) 非严格模式下不再打印 `Deserializing unregistered type ...` | 达成。宽松模式全套 + 警告嗅探 handler,去重后**零条**(修复前两条);并由 `test_checkpoint_round_trip_logs_no_serde_complaint` 长期钉住 |
| (d) 三种后端凡能注入的都注入了 | memory / sqlite / postgres **三条全部注入**(checkpointer.py:120/133/148),没有拿不到注入点的路径。postgres 的**运行验证**缺席,见第六节 |
| (e) 门禁里有能长期盯住它的东西 | 达成,两道,见下 |

**判据 (e) 的两道门,以及"下次谁会红"**:

1. **声明门** `test_checkpoint_state_type_registry_names_every_engine_state_model`:从
   `WorkflowState` 出发走遍类型注解,收集所有引擎自有的 pydantic 模型,断言这个集合与
   `CHECKPOINT_STATE_TYPES` **相等**。有人往状态里加了新模型却忘了登记,红的是这条,
   并会直接点名那个类。它还顺带断言外来模型只来自 `langchain_core`,所以状态里混进
   第三方新包也会红。
2. **行为门** `test_engine_state_types_survive_a_checkpoint_round_trip` /
   `test_checkpoint_round_trip_logs_no_serde_complaint`:子进程真跑一次 checkpoint 往返,
   **两种 msgpack 模式各一遍**,断言取回的类型正确、且 stderr 里既无 `Deserializing
   unregistered type` 也无 `Blocked deserialization of`。严格模式由测试自己设进子进程
   环境,不依赖任何人手工设环境变量。

**门禁咬得住是变异验证过的,不是声称的**:

- 把 `checkpoint_serde()` 改回裸 `JsonPlusSerializer()` → 5 条里 **3 条红**
  (`[strict]` 的类型存活 + 两种模式的静默断言)。
- 往 `FrameworkState` 加一个未登记的 `_MutantNote` 模型 → 声明门红,报文直接列出
  `Extra items in the left set: <class 'graph_agent.core.state._MutantNote'>`。
  拆函数重构之后**又复跑了一次**这个变异,仍然红。

---

## 六、已知遗留

1. **postgres 后端只有代码路径注入,没有运行验证。** 它与 sqlite 共用同一个
   `_adopt_checkpoint_serde` 赋值(checkpointer.py:148),但本机与 CI 都没有 postgres
   服务,探针只覆盖 memory + sqlite。要真验证需要一个起得来的库。
2. **调用方自建的 checkpointer 不受引擎保护,这是刻意的**(理由见 3.2)。今天没有这样的
   生产调用方(3.1 已机械核对),但 `assemble_graph` / `run_skill` / `resume_skill` 的
   `checkpointer=` 参数在 SDK 契约上允许。宿主自建 saver 时必须自己用
   `checkpoint_serde()`,引擎不会替它兜。
3. **`NamespaceCheckpointer` 的 `.serde` 是装饰性的。** 它(graph_assembler.py:1763-1766)
   把所有存取都委托给 `base_checkpointer`,真正序列化发生在内层 saver 里;已核实 langgraph
   的 Pregel 不直接用 `checkpointer.serde`(`grep -rn "\.serde\b" langgraph/pregel/` 无命中)。
   本仓内部一律先给内层 saver 装白名单再包装,所以不受影响;但如果将来有人对着
   `NamespaceCheckpointer` 调 `with_allowlist`,那会是一次静默的空操作。
4. **langgraph 已预告要收紧默认档**(警告原文 "This will be blocked in a future version")。
   本 PR 之后引擎不依赖那个默认档,升级不会因此破;但升级时仍应复跑第 2.3 节那次嗅探,
   确认没有新类型混进 checkpoint。
