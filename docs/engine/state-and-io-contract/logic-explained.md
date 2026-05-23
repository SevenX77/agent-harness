# state-and-io-contract V0.3.0 代码逻辑翻译

本文解释 V0.3.0 完成态下 `state-and-io-contract` 的运行机制。这个模块的核心不是"有一个 state dict", 而是: 全图共享的 `BlackboardState` 如何被切成每个 phase 可见的 `phase_input`, phase 返回后如何按 `phase_output` 规则封口, child graph 和 builtin reference reader 如何避免继承父图黑板。本文按 v1 原则写: 字段级颗粒度, 每个关键字段都说明四件事: (a) 干什么用, (b) 为什么必须校验, (c) 判定逻辑, (d) 错误码。

核心源码锚点:

- `BlackboardState` 与 `shallow_dict_merge()` 在 `packages/graph-agent/src/graph_agent/runtime/state.py:13`, `packages/graph-agent/src/graph_agent/runtime/state.py:35`。
- `schema_properties()`, `filter_runtime_inputs()`, `StateMapper`, `PhaseWrapper`, `ReaderSandboxState` 在 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:15`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:24`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:34`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:70`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:91`。
- LangGraph 以 `StateGraph(BlackboardState)` 装配全图运行态: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:77`。
- 有 `io` 的 phase 通过 `PhaseWrapper(StateMapper(io.inputs, io.outputs)).wrap(node)` 进入切片/封口路径: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:158`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:162`。

## 模块边界

`state-and-io-contract` 负责运行时数据边界: 输入进来后放在哪里, phase 能看到哪一片 `data`, phase 能写回哪些 key, child graph 是否能继承父图状态, reader 是否能继承父 Agent 对话。它不解析 Markdown, 不选择模型, 不解析 `target_skill`, 不决定 DAG 顺序。

和其它模块的边界:

- skill-compilation 产生 `GRAPH.md io.inputs`、phase `io.inputs` / `io.outputs` 和 AST。
- execution-runtime 调用 node 并把 node 包进 `PhaseWrapper`。
- skill-resolution 解析 `target_skill -> skill root Path`; state/io 只消费解析后的 child IO 契约。
- tracing-and-observability 记录已经切片后的 input/output, 不应该记录全量父黑板。

难点名词只用一个: **配料员**。`StateMapper` 像配料员: 不执行业务, 不决定 DAG, 只按 `io.inputs` 取料, 按 `io.outputs` 验收。

## BlackboardState 字段

`BlackboardState` 是全图共享状态。它是 `TypedDict(total=False)`, 运行时仍是普通 dict, 但 LangGraph 和类型检查能看到四个固定 key: `data`, `flow`, `messages`, `run_id`: `packages/graph-agent/src/graph_agent/runtime/state.py:35`。

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `data` | 承载业务数据: root inputs、LOGIC action 更新、SUBGRAPH delta、Agent `finish_task` 输出 | 不校验会让 phase 读写未声明业务字段, child graph 也可能污染父图 | 类型语义是 `dict[str, Any]`; LangGraph 合并时走 `shallow_dict_merge` reducer | 当前冲突为 `[F-v3-state-conflict]`; 切片/回写失败归 `[F-v3-runtime-state-mapping-failed]` | `runtime/state.py:38` |
| `flow` | 承载控制态: retry、depth、`finish_task_result`、critic metrics | 业务数据混入 flow 会绕过 IO schema; 可变引用共享会污染父状态 | `dict[str, Any]`; `StateMapper.build_phase_input()` 对它 `deepcopy` | `[F-v3-runtime-state-mapping-failed]` | `runtime/state.py:39`, `runtime/state_mapper.py:43` |
| `messages` | 承载 LLM 对话历史 | child graph 或 reader 继承父 Agent prompt history 会污染推理上下文 | `list[AnyMessage]`; LangGraph 用 `add_messages` reducer; StateMapper 只复制 list 容器 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state.py:40`, `runtime/state_mapper.py:44` |
| `run_id` | 标识本次 graph run, 供 trace 和 child metadata 关联 | 没有稳定 id, subagent child run 和父 run 难关联 | `str | None`; phase input 中原样复制 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state.py:41`, `runtime/state_mapper.py:45` |

V0.3.0 完成态中, `data` 的语义应进一步收敛为 `inputs`、`phase_outputs`、`scratch` 三类区域。当前源码仍是扁平 dict, 所以 `StateMapper` 的切片和输出封口是阻止全局变量化的关键边界。

## data reducer: shallow_dict_merge

`shallow_dict_merge(left, right)` 是 `data` 的 reducer。它只合并顶层 key, 不做深层递归合并: `packages/graph-agent/src/graph_agent/runtime/state.py:13`。

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `left` | 当前已经合并出的 `data` 状态 | 不是 dict 或可变引用不清晰时, 后续冲突判断不可信 | `None` 或空值按 `{}` 处理; 非空时浅拷贝成 `merged` | `[F-v3-runtime-state-mapping-failed]` | `runtime/state.py:14`, `runtime/state.py:19` |
| `right` | 当前 node 返回的 `data` delta | node 返回值是写回入口, 必须能被稳定合并 | `None` 或空值不改变 left; 非空时遍历 `right.items()` | `[F-v3-runtime-state-mapping-failed]` | `runtime/state.py:15`, `runtime/state.py:21` |
| `key` | 顶层业务字段名 | 并行分支写同一个 key 时, runtime 不知道哪个值应该赢 | 如果 `key in merged`, 立即抛 `GraphAgentFatalError` | `[F-v3-state-conflict]` | `runtime/state.py:25`, `runtime/state.py:27` |
| `value` | 新写入的字段值 | value 会进入后续 phase 和 trace, 不应是不可追踪的隐式对象 | 当前 reducer 不做 JSON validation; 完成态应由 StateMapper/schema 先封口 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state.py:31` |
| return `merged` | 给 LangGraph 下一步看到的新 `data` | 合并结果必须是新 dict, 避免原地改旧状态 | 无冲突后返回 `merged` | 无 | `runtime/state.py:32` |

这里的 Fail-fast 是有意的。它宁可在同 key 写入时失败, 也不静默覆盖。mvp0-alignment 中的 P0-3 要把这个 reducer 升级成能区分同一 super-step 并发冲突和顺序覆盖的 smart reducer; 在完成态文档里仍要保留"并发同 key 写入必须失败"这个业务意图。

## 输入漏斗: schema_properties 与 filter_runtime_inputs

当前源码的输入漏斗是轻量实现: 只按 JSON Schema 的 `properties` key 做字段过滤, 不执行完整 Draft validation。

| 字段 / 函数 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `schema` | 提供允许通过漏斗的字段声明 | runtime 不能从全量黑板猜 phase 要什么 | `schema_properties()` 只接受 `dict`; 非 dict 返回空集合 | 编译期 schema 错误归 `[F-v3-graph-io-schema-invalid]`; runtime 失败归 `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:15`, `runtime/state_mapper.py:16` |
| `properties` | JSON Schema 中的字段集合 | 未声明字段如果进入 phase, 就绕过 IO contract | 必须是 dict; key 必须是字符串; 非 dict 返回空集合 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:18`, `runtime/state_mapper.py:21` |
| `raw_inputs` | 外部输入或父 phase data | 原始 dict 可能带 typo、越权字段、未声明上下文 | `filter_runtime_inputs()` 先用 `dict(state.get("data", {}))` 或调用方 dict 规整 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:24`, `runtime/state_mapper.py:42` |
| `keys` | schema properties 的 key 集合 | 决定哪些字段能进入 phase-local `data` | `keys` 为空时当前返回 raw copy; 非空时只保留交集 | 完成态 unknown/required/type 应归 `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:27`, `runtime/state_mapper.py:28` |
| return dict | 生成 canonical phase input data | 后续 LOGIC/Agent/SUBGRAPH 只应看到这个切片 | `{key: raw_inputs[key] for key in keys if key in raw_inputs}` | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:30` |

C7 决策要求 Runtime Input Funnel 迁移到 `GRAPH.md` inline `io.inputs`, 不再读取旧物理 `io/inputs.json`。因此完成态中, root 输入和 phase 输入都应该从已编译的 inline schema 来, runtime 不再猜 schema 来源。

## StateMapper 字段与方法

`StateMapper` 是 phase 边界的核心类。它有两个配置字段, 两个行为方法: `input_schema`, `output_schema`, `build_phase_input()`, `wrap_phase_output()`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:34`。

### StateMapper 配置字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `input_schema` | 描述当前 phase 可读取的 `data` 字段 | 没有读边界, phase 会退化成全黑板读取 | `dict[str, Any] | None`; 传给 `filter_runtime_inputs()` | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:37` |
| `output_schema` | 描述当前 phase 可写回的 `data` 字段 | 没有写边界, action 或 Agent 可污染未声明字段 | `dict[str, Any] | None`; `wrap_phase_output()` 从中取 `properties` | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:38` |

### build_phase_input 输出字段

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| phase-local `data` | 当前 phase 的业务输入切片 | 防止 phase 读取全局黑板或隐式依赖未声明上游字段 | 从全局 `state.data` 复制 dict, 再按 `input_schema.properties` 过滤 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:41`, `runtime/state_mapper.py:42` |
| phase-local `flow` | 当前 phase 的控制态副本 | 防止 phase 内部修改 nested flow 对象污染父 graph | `deepcopy(state.get("flow", {}))` | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:43` |
| phase-local `messages` | 当前 phase 的消息列表快照 | 防止直接共享 list 对象造成 prompt history 串写 | `list(state.get("messages", []))` | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:44` |
| phase-local `run_id` | 当前 phase 的 run 标识 | trace 和错误定位要沿用父 run id | `state.get("run_id")` 原样复制 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:45` |
| return `phase_state` | 交给原始 node 执行的局部 state | node 不应直接拿全局 state | 返回 `BlackboardState` 形状 dict | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:47` |

### wrap_phase_output 校验字段

| 字段 / 分支 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `output` | node 返回的 state patch | 这是写回全图前最后一个拦截点 | 必须是 dict-like; wrapper 调用该方法处理 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:49` |
| `data` | node 试图写回的业务数据 | 业务数据写回必须受 `io.outputs` 控制 | `output.get("data")`; 非 dict 时当前直接放行 | 完成态应归 `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:50`, `runtime/state_mapper.py:51` |
| `allowed` | output schema 允许的字段集合 | 没有 allowed 集合就无法判断越界写入 | `schema_properties(self.output_schema)`; 空集合时当前放行 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:53`, `runtime/state_mapper.py:54` |
| nested output | 兼容 Agent `data_updates[phase_id]` 形状 | Agent 输出常挂在 phase id 下, 但内部业务字段仍需验证 | `len(data)==1` 且 nested dict keys 是 allowed 子集时放行 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:56`, `runtime/state_mapper.py:58` |
| `invalid` | 未声明输出字段列表 | 需要给 Studio/trace 定位具体越界 key | `sorted(key for key in data if key not in allowed)` 非空即 fatal | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:60`, `runtime/state_mapper.py:62` |
| return `output` | 验证通过后的 state patch | 只有验证后的 patch 才能回到 LangGraph | 无 invalid 后原样返回 | 无 | `runtime/state_mapper.py:66` |

## PhaseWrapper 字段与执行链路

`PhaseWrapper` 是把 `StateMapper` 接入 execution-runtime 的薄壳。它不理解业务, 只保证原始 node 执行前后都经过 mapper。

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `mapper` | 保存当前 phase 的 `StateMapper` | wrapper 不应该自己解析 schema, 避免两套规则 | dataclass 字段, 由 `_wrap_phase_runtime_node()` 传入 | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:73` |
| `node` | 原始 LangGraph node callable | wrapper 只负责边界, 业务执行仍属于 node | `wrap(node)` 接收 callable | `[F-v3-runtime-phase-failed]` / `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:75` |
| `_wrapped(state)` | LangGraph 实际调用的包装函数 | 所有有 IO 的 phase 都要从这里进入 | 先 `build_phase_input()`, 再执行 node, 再 `wrap_phase_output()` | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:76`, `runtime/state_mapper.py:78` |
| `GraphAgentFatalError` passthrough | 保留更具体的错误码 | 不能把 `[F-v3-state-conflict]` 等细分错误都抹成泛化错误 | 捕获后直接 `raise` | 原错误码 | `runtime/state_mapper.py:80` |
| generic exception wrapping | 把非契约异常变成 runtime state mapping failure | 普通 Python 异常不能带着脏 state 继续运行 | `except Exception as exc` 后包装为 `GraphAgentFatalError` | `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:82`, `runtime/state_mapper.py:83` |

C8 决策要求 Phase Wrapper 覆盖 Agent、LOGIC、SUBGRAPH、builtin reference reader 四类调用边界。当前源码已通过 `_wrap_phase_runtime_node()` 覆盖有 `io` 的 LOGIC / SUBGRAPH / Agent runtime node: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:129`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:131`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:142`。

## graph_assembler 中的真实读写字段

StateMapper 的价值要放到真实 node 上看。下面列出 LOGIC、SUBGRAPH、Agent、subagent 当前怎样读写 state, 以及完成态为什么要继续收紧。

### LOGIC phase

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `before` | action 执行前的数据快照 | 没有快照就无法计算 action 改了什么 | `dict(state.get("data", {}))` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:177` |
| `data` | 给 `Context` 的可变工作副本 | action 需要局部可写对象, 但不能直接改全局 state | `dict(before)` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:178` |
| `Context` | LOGIC action 的读写 facade | action 需要 phase_id/run_id, 不能直接操作 LangGraph state | `Context(data, phase_id=phase_id, run_id=...)` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:179` |
| `result` | action 显式返回值 | 返回 dict 是写业务输出的一条路径 | `isinstance(result, dict)` 时校验 key 后合入 updates | `[F-v3-actions-keys]` / `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:180`, `graph_assembler.py:182` |
| `updates` | 最终写回的 data delta | 只应写 action 变更或声明返回字段 | `_dict_delta(before, data)`, 再 `updates.update(result)` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:181`, `graph_assembler.py:184` |

### SUBGRAPH phase

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `before_data` | 子图执行前的父图数据快照 | child result 需要和父图执行前状态比较 | 当前 `dict(state.get("data", {}))` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:210` |
| child `data` | 子图初始业务黑板 | 完成态不能默认继承父图全量 data | 当前传 `before_data`; 完成态应传 explicit input funnel 结果 | `[F-v3-runtime-state-mapping-failed]` / `[F-v3-subgraph-io-mismatch]` | `graph_assembler.py:213` |
| child `flow` | 子图控制态 | 子图不应原地污染父 flow | 当前传 `state.get("flow", {})`; 完成态应 deep copy | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:214` |
| child `messages` | 子图 LLM 历史 | 子图不应继承父 Agent 对话 | 固定 `[]` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:215` |
| child `run_id` | 子图 run 标识 | trace 需要关联父图 run | 当前传 `state.get("run_id")` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:216` |
| `data_updates` | 子图返回父图的业务 delta | 父图只能接收声明输出, 不能让 child 临时字段泄漏 | 当前 `_dict_delta(before_data, result_data)`; 完成态应经 `io.outputs` 封口 | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:220`, `graph_assembler.py:223` |

### Agent phase

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `flow` | 保存本 Agent 的控制态 | `finish_task_result` 和 critic metrics 不应写入业务 data | `dict(state.get("flow", {}))` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:298` |
| `messages` | 本轮 Agent 对话历史 | Prompt 输入影响模型行为, 必须可定位来源 | `SystemMessage(...) + state.get("messages", [])` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:299` |
| `finish_task_result` | 保存最终工具调用结果 | runtime 和 trace 需要知道 Agent 如何结束 | tool 名为 `finish_task` 时写入 flow | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:346`, `graph_assembler.py:347` |
| `data_updates[phase_id]` | Agent 业务输出命名空间 | 防止 Agent 直接覆盖 root input 或其它 phase 输出 | `result` 是 dict 且 `ok` 为真时写入 | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:348`, `graph_assembler.py:349` |
| `critic_metrics` | reviewer/critic 工具统计 | 这是控制指标, 不是业务输出 | 写入 `flow.setdefault("critic_metrics", {})` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:350` |

### subagent child graph

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `input_data` | LLM 调 subagent tool 时显式传入的参数 | child graph 应以显式参数为输入来源 | 当前与 parent `before_data` 合并 | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:579`, `graph_assembler.py:583` |
| `child_data` | subagent child graph 初始 data | 默认继承父图全量 data 会破坏读隔离 | 当前 `{**before_data, **input_data}`; NEW-2 完成态应只用 child input funnel 结果 | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:583`, `graph_assembler.py:586` |
| child `messages` | child graph 的对话历史 | child 不应继承父 Agent prompt history | 当前固定 `[]` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:588` |
| `data_delta` | child 相对父图的结果差量 | tool result 需要可解释, 但不能自动污染父图 | 当前 `_dict_delta(before_data, result_data)` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:593`, `graph_assembler.py:594` |
| `parent_run_id` | child trace 关联父 run | 并行 child run 必须能回到父 run | 从 `parent_state` 或 metadata 取值 | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:675`, `graph_assembler.py:678` |
| `subagent_depth` | child 调用深度 | 防止递归 subagent 失控 | metadata 写 `depth + 1` | `[F-v3-runtime-state-mapping-failed]` | `graph_assembler.py:679` |
| child `run_id` | 每个 child item 的独立 run id | 并行 child 需要独立定位 | `uuid.uuid4()` | 无 | `graph_assembler.py:684` |

NEW-2 的核心是"先 resolve, 再 funnel": 先通过 `SkillResolverProtocol` 找到 child skill root, 再读取 child `GRAPH.md io.inputs`, 最后把 explicit input 过滤成 child canonical input。StateMapper 不负责解析 `target_skill`, 但它负责 child input 进入执行前的隔离语义。

## ReaderSandboxState 字段

`ReaderSandboxState` 是 builtin reference reader 的装配期沙盒。它不是 runtime phase, 但它遵守同样的黑板隔离思想: 不继承父 graph `data`, 不继承父 Agent messages。

| 字段 | (a) 干什么用 | (b) 为什么校验 | (c) 判定逻辑 | (d) 错误码 | src |
|---|---|---|---|---|---|
| `skill_id` | 标识当前 graph skill | reader 输出和 WARN 需要定位来源 skill | dataclass 必填 string; `to_blackboard()` 写入 `data.skill_id` | `[F-v3-reference-reader-input-invalid]` | `runtime/state_mapper.py:94`, `runtime/state_mapper.py:101` |
| `phase_id` | 标识当前 Agent phase | 同一 skill 可能多个 Agent phase 使用 references | dataclass 必填 string; `to_blackboard()` 写入 `data.phase_id` | `[F-v3-reference-reader-input-invalid]` | `runtime/state_mapper.py:95`, `runtime/state_mapper.py:101` |
| `root` | 当前 skill root | reader 读取 reference path 时必须以 skill root 为边界 | dataclass 必填 `Path`; 当前 `to_blackboard()` 不写入 data, 执行层应用它做 path 边界 | `[F-v3-resource-reference-path-invalid]` | `runtime/state_mapper.py:96` |
| `timeout_s` | reader 最大执行时间 | 装配期增强不能无限阻塞主图 | 默认 `60`; `to_blackboard()` 写入 `flow.timeout_s` | `[F-v3-reference-reader-failed]` WARN | `runtime/state_mapper.py:97`, `runtime/state_mapper.py:102` |
| sandbox `data` | reader 的业务定位输入 | reader 不应读取父 runtime data | 当前只含 `skill_id`, `phase_id`; 完成态还应加入 references registry | `[F-v3-reference-reader-input-invalid]` | `runtime/state_mapper.py:100`, `runtime/state_mapper.py:101` |
| sandbox `flow` | reader 的控制态 | reader 超时/降级策略需要控制参数, 但不能继承父 flow | 当前只含 `timeout_s` | `[F-v3-reference-reader-failed]` WARN | `runtime/state_mapper.py:102` |
| sandbox `messages` | reader 的 LLM 历史 | reader 不是父 Agent 的一轮对话 | 固定 `[]` | 无 | `runtime/state_mapper.py:103` |
| sandbox `run_id` | reader 黑板 run 标识 | 装配期 reader 可单独 trace, 不复用 runtime run id | 当前 `None` | 无 | `runtime/state_mapper.py:104` |

NEW-1 决策要求 builtin reference reader 使用独立黑板沙盒。reference path 不合法是编译期 FATAL; reader 超时、远端失败或输出非法是装配期 WARN `[F-v3-reference-reader-failed]`, 主图继续用 fallback excerpt。

## V0.3.0 四个改造点

| 改造点 | 字段级落点 | 为什么这么改 | 错误码 |
|---|---|---|---|
| C7 Runtime Input Funnel 迁移到 inline 根 IO | `GRAPH.md io.inputs`, raw inputs, canonical inputs | 旧 `io/inputs.json` 会让 schema 漂移; 完成态只消费编译后的 inline IO | `[F-v3-graph-io-physical-file-deprecated]`, `[F-v3-runtime-state-mapping-failed]` |
| C8 四类调用边界都经 wrapper/sandbox | Agent, LOGIC, SUBGRAPH, builtin reader | 统一读切片和写封口, 避免每类 node 自己发明 IO 行为 | `[F-v3-runtime-state-mapping-failed]`, reader WARN code |
| NEW-1 builtin reference reader 黑板沙盒 | `ReaderSandboxState.skill_id/phase_id/root/timeout_s`, sandbox data/flow/messages | reader 是装配期辅助模块, 不能继承父 graph 黑板或 prompt history | `[F-v3-reference-reader-input-invalid]`, `[F-v3-reference-reader-failed]` |
| NEW-2 child graph 先 resolve 再 funnel | `target_skill`, child root `io.inputs`, explicit input, child data | child schema 只有解析到目标 skill root 后才知道; 不能默认继承父 data | `[F-v3-skill-not-registered]`, `[F-v3-runtime-state-mapping-failed]`, `[F-v3-subgraph-io-mismatch]` |

## 错误码清单

| 错误码 | 触发边界 | 字段/对象 | 修复方向 | 来源 |
|---|---|---|---|---|
| `[F-v3-state-conflict]` | reducer 合并 | `data` top-level key | 拆分输出命名空间, 或避免并行分支写同一 key | `runtime/state.py:27` |
| `[F-v3-runtime-state-mapping-failed]` | 输入切片 / 输出封口 / wrapper 包装异常 | `input_schema`, `output_schema`, phase `data`, child `data` | 检查 phase IO、上游输出、node 返回结构 | `runtime/state_mapper.py:62`, `docs/engine/skill-spec/11-error-code-spec.md:159` |
| `[F-v3-graph-io-physical-file-deprecated]` | 编译期 root IO | `io_inputs_ref`, `io_outputs_ref`, `io/*.json` | 改为 `GRAPH.md` inline IO | `mvp0-alignment.md` C7 |
| `[F-v3-subgraph-io-mismatch]` | 父子图 IO 对齐 | SUBGRAPH input/output 与 child GRAPH IO | 对齐父 phase 和 child graph schema | `mvp0-alignment.md` NEW-2 |
| `[F-v3-reference-reader-input-invalid]` | reader sandbox 输入 | `skill_id`, `phase_id`, references | 修 references registry 或 reader input | `docs/engine/skill-spec/11-error-code-spec.md:156` |
| `[F-v3-reference-reader-output-invalid]` | reader 输出 | `markdown`, `used_reference_ids` | 修 builtin reader 输出结构 | `docs/engine/skill-spec/11-error-code-spec.md:157` |
| `[F-v3-reference-reader-failed]` | reader WARN fallback | `timeout_s`, remote error, invalid output | 查看 trace; 主图使用 fallback 内容继续 | `docs/engine/skill-spec/11-error-code-spec.md:138` |
| `[F-v3-resource-reference-path-invalid]` | reference path 边界 | `ReaderSandboxState.root`, reference path | 修正 path, 禁止越过 skill root | resource spec / runtime reader边界 |
| `[F-v3-skill-not-registered]` | child skill 解析 | `target_skill` | 在 Studio registry 注册或导入 child skill | skill-resolution |

## 读代码顺序

先看 `runtime/state.py`: `shallow_dict_merge()` 定义 data 合并失败规则, `BlackboardState` 定义全图状态四个区。

再看 `runtime/state_mapper.py`: `schema_properties()` 和 `filter_runtime_inputs()` 是输入漏斗, `StateMapper` 是切片/封口, `PhaseWrapper` 是接入点, `ReaderSandboxState` 是装配期沙盒。

最后看 `core/graph_assembler.py`: `StateGraph(BlackboardState)` 是 graph 入口, `_wrap_phase_runtime_node()` 决定哪些 phase 经过 mapper, LOGIC/SUBGRAPH/Agent/subagent 节点展示真实 state 读写路径。
