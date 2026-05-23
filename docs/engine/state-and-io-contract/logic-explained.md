# state-and-io-contract V0.3.0 代码逻辑翻译

本文解释 V0.3.0 完成态下 `state-and-io-contract` 子模块具体做什么、为什么这样做、每个状态字段和 IO 边界如何校验。它不是 baseline 的现状盘点, 也不是 mvp0-alignment 的改造路线; 它把 `BlackboardState`、`StateMapper`、`PhaseWrapper`、child graph 沙盒和 builtin reference reader 沙盒翻译成自然语言。

核心源码锚点:

- `BlackboardState` 和 `shallow_dict_merge()` 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:13`, `packages/graph-agent/src/graph_agent/runtime/state.py:35`。
- `schema_properties()`, `filter_runtime_inputs()`, `StateMapper`, `PhaseWrapper`, `ReaderSandboxState` 定义在 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:15`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:24`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:34`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:70`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:91`。
- LangGraph 以 `StateGraph(BlackboardState)` 装配运行状态: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:77`。
- 每个有 `io` 的 phase 都通过 `_wrap_phase_runtime_node()` 套 `PhaseWrapper(StateMapper(io.inputs, io.outputs))`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:158`。
- builtin reference reader 的输入输出和 WARN fallback 定义在 `docs/engine/skill-spec/09-builtin-modules-spec.md:5`, `docs/engine/skill-spec/09-builtin-modules-spec.md:52`。
- state/io 相关错误码集中在 `docs/engine/skill-spec/11-error-code-spec.md:89`, `docs/engine/skill-spec/11-error-code-spec.md:138`, `docs/engine/skill-spec/11-error-code-spec.md:159`。

## 这个模块的边界

`state-and-io-contract` 只负责运行时黑板形状和 IO 过边规则: 外部输入如何进入 `data`, phase 看到哪一片 state, phase 输出能写回哪些字段, child graph 如何隔离父图黑板, builtin reader 如何在装配期独立运行。

它不解析 Markdown, 不决定 DAG 是否成环, 不选择 LLM, 不解析 `target_skill` 本身, 也不执行业务 action。对应分工是:

| 事项 | 归属 |
|---|---|
| `GRAPH.md io.inputs` / phase `io.outputs` 的结构来源 | skill-compilation |
| `target_skill -> skill root Path` | skill-resolution |
| `StateGraph(BlackboardState)` 和 node 执行 | execution-runtime |
| `phase_input` / `phase_output` 切片、封装、失败归一 | state-and-io-contract |
| reference reader 失败事件展示 | tracing-and-observability |

难点 1: **分水阀**。编译产物告诉 runtime 有哪些字段可流动, StateMapper 决定本次执行时哪些字段真的过阀。这个阀门太宽会泄漏全黑板, 太窄会让合法 phase 拿不到输入。

## BlackboardState: LangGraph 运行态黑板

`BlackboardState` 是 `TypedDict(total=False)`, 运行时仍是普通 dict, 但 LangGraph 和类型检查能看到固定 key: `data`, `flow`, `messages`, `run_id`: `packages/graph-agent/src/graph_agent/runtime/state.py:35`。`data` 和 `messages` 通过 `Annotated` 绑定 reducer, `flow` 和 `run_id` 没有自定义 reducer。

### BlackboardState 字段

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `data` | 业务数据黑板, 存 root inputs、phase outputs、临时 action 结果 | 不校验会让 phase 读取或写入未声明字段, 子图也可能污染父图 | 类型应为 `dict[str, Any]`; 在 `BlackboardState` 中绑定 `shallow_dict_merge` reducer | `[F-v3-runtime-state-mapping-failed]`; reducer 冲突当前用 `[F-v3-state-conflict]` |
| `flow` | 控制态, 存 retry、depth、finish_task_result、critic_metrics 等运行控制信息 | 业务字段混入 flow 会绕过 IO schema, child 调用也会共享不可预期控制状态 | 类型应为 dict; `StateMapper.build_phase_input()` 对它 `deepcopy`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:43` | `[F-v3-runtime-state-mapping-failed]` |
| `messages` | LLM 对话历史 | 不隔离会让 child graph 或 reader 继承父 Agent prompt history | 类型是 `list[AnyMessage]`; 绑定 LangGraph `add_messages` reducer: `packages/graph-agent/src/graph_agent/runtime/state.py:40` | `[F-v3-runtime-state-mapping-failed]` |
| `run_id` | 本次运行的追踪 id | 没有稳定 id, trace、subagent child run 和错误定位难关联 | `str | None`; phase slice 原样复制: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:45` | `[F-v3-runtime-state-mapping-failed]` |

### 完成态 data 分区

V0.3.0 的语义目标是把旧扁平 `data` 收敛成三个区: `inputs`, `phase_outputs`, `scratch`。当前源码的 `BlackboardState.data` 仍是一个 dict, 但 `StateMapper` 已经用 phase IO schema 在入口和出口收口。

| data 子区 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `data.inputs` | 保存 Runtime Input Funnel 后的根输入 | 根输入是全图数据源, 被业务 phase 覆盖会破坏可追溯性 | 只来自 `GRAPH.md io.inputs` 过滤后的 canonical inputs | `[F-v3-runtime-state-mapping-failed]` |
| `data.phase_outputs` | 按 `phase_id` 命名空间保存 phase 输出 | 顶层平铺会触发覆盖冲突, 也无法区分同名字段来源 | key 是 phase id, value 满足该 phase `io.outputs` | `[F-v3-runtime-state-mapping-failed]` |
| `data.scratch` | 单 phase 临时工作区 | 临时中间态不应进入最终输出或被下游误读 | 可选 dict; 不作为 graph output 来源 | `[F-v3-runtime-state-mapping-failed]` |

## shallow_dict_merge(): reducer 是最后一道并发防线

`shallow_dict_merge(left, right)` 是 `data` 的 LangGraph reducer: `packages/graph-agent/src/graph_agent/runtime/state.py:13`。它只做顶层合并, 不递归深合并。当前代码规则是: 左空返回右拷贝, 右空返回左拷贝, 两边都存在时如果 `right` 的 key 已在 `left` 中, 直接抛 `GraphAgentFatalError("[F-v3-state-conflict] ...")`: `packages/graph-agent/src/graph_agent/runtime/state.py:19`, `packages/graph-agent/src/graph_agent/runtime/state.py:26`。

### reducer 输入字段

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `left` | 当前已合并的 `data` 状态 | 非 dict 或可变引用泄漏会让 reducer 结果不可预测 | `None` 或空值按 `{}` 处理; 非空时浅拷贝为 `merged` | `[F-v3-runtime-state-mapping-failed]` |
| `right` | 当前 node 返回的 `data` delta | node 返回值是黑板写入入口, 必须限制为 dict delta | `None` 或空值不改变 left; 非空时逐 key 合并 | `[F-v3-runtime-state-mapping-failed]` |
| `key` | 顶层业务字段名 | 同一 super-step 多分支写同名 key 会产生不可排序结果 | 当前只要 `key in merged` 就冲突; 完成态应区分顺序覆盖和并行冲突 | 当前 `[F-v3-state-conflict]`; spec 汇总为 `[F-v3-runtime-state-mapping-failed]` |
| `value` | 新写入字段值 | 不可序列化或嵌套可变对象会污染 checkpoint / trace | 当前源码不做 JSON 化校验; wrapper 层应先 schema validation / copy | `[F-v3-runtime-state-mapping-failed]` |
| return `merged` | LangGraph 下一步看到的 `data` | 合并结果必须稳定, 否则下游 phase 输入不稳定 | 无冲突后返回新 dict, 不原地改 left | 无 |

难点 2: **分岔闸**。reducer 要挡住并行 fan-in 的同 key 写入, 但不应该挡住拓扑顺序上的合法覆盖。当前源码把两者都看成顶层 key 冲突; V0.3.0 的完成语义要靠 StateMapper 命名空间和运行上下文把这两类写入区分开。

## schema_properties() 和 filter_runtime_inputs(): 输入漏斗

`schema_properties(schema)` 从 JSON Schema 的 `properties` 中取出字符串 key 集合: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:15`。`filter_runtime_inputs(raw_inputs, schema)` 用这个集合过滤运行输入: 如果 schema 没有可识别 properties, 就返回原始输入浅拷贝; 如果有, 就只保留 schema 声明且 raw inputs 中存在的字段: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:24`。

### 输入漏斗字段

| 字段 / 函数 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `schema` | 根或 phase 的 inline `io.inputs` schema | runtime 不能从物理 `io/inputs.json` 猜输入契约 | `None` 或非 dict 时视作无 properties; 完成态应由编译期保证 object schema | `[F-v3-graph-io-schema-invalid]` / `[F-v3-runtime-state-mapping-failed]` |
| `properties` | 允许通过漏斗的字段集合 | 未声明字段如果进入 phase, 就绕过了 IO contract | 必须是 dict; key 必须是字符串; 非 dict 返回空集合 | `[F-v3-runtime-state-mapping-failed]` |
| `raw_inputs` | 外部调用 `run_skill` 或父 phase 传入的原始 dict | 入口不校验会让 typo 字段、越权字段、缺 required 字段进入黑板 | 当前按 key 过滤; 完成态还要校验 required、type、default/coercion | `[F-v3-runtime-state-mapping-failed]` |
| return canonical dict | 写入 phase-local state 的输入 | 下游 action/Agent 只应看到 canonical 输入 | 有 properties 时只保留交集; 无 properties 时保留 raw copy | `[F-v3-runtime-state-mapping-failed]` |

这里的 current source 行为只做字段过滤, 不执行完整 JSON Schema validation。完整类型、required、默认值策略属于 V0.3.0 完成态的 runtime funnel 语义, 错误统一归入 `[F-v3-runtime-state-mapping-failed]`。

## StateMapper: phase 输入切片和输出封口

`StateMapper(input_schema=None, output_schema=None)` 是 phase-local 状态映射器: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:34`。它有两个方法: `build_phase_input()` 构造局部 `BlackboardState`, `wrap_phase_output()` 校验 node 返回值是否写了未声明字段。

### StateMapper 字段和方法

| 字段 / 方法 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `input_schema` | 当前 phase 可读字段 schema | 没有读边界, LOGIC/Agent/SUBGRAPH 都会退回全黑板读取 | 可选 dict; 传给 `filter_runtime_inputs()` | `[F-v3-runtime-state-mapping-failed]` |
| `output_schema` | 当前 phase 可写字段 schema | 没有写边界, action 或 finish_task 可污染未声明字段 | 可选 dict; `wrap_phase_output()` 读取 properties | `[F-v3-runtime-state-mapping-failed]` / `[F-v3-logic-output-field-undeclared]` |
| `build_phase_input(state)` | 把全局 state 变成 phase-local state | phase 只应看到被授权字段, child 不应共享可变对象 | `data` 按 input schema 过滤; `flow` deep copy; `messages` list copy; `run_id` 复制 | `[F-v3-runtime-state-mapping-failed]` |
| phase-local `data` | phase 实际可读业务字段 | 如果包含未授权 key, Agent prompt 和 action 都可能越权 | 来自 `filter_runtime_inputs(dict(state.get("data", {})), input_schema)`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:42` | `[F-v3-runtime-state-mapping-failed]` |
| phase-local `flow` | phase 可读写的控制态副本 | 子调用不能原地污染父 flow | `deepcopy(state.get("flow", {}))`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:43` | `[F-v3-runtime-state-mapping-failed]` |
| phase-local `messages` | phase 的消息列表快照 | list 原对象共享会让 prompt history 意外串写 | `list(state.get("messages", []))`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:44` | `[F-v3-runtime-state-mapping-failed]` |
| `wrap_phase_output(output)` | 校验 node 返回的 `data` key | 输出是全局 state 的写入口, 必须在写回前封口 | `output["data"]` 非 dict 或无 allowed 时当前直接放行; 有 allowed 时检查 key 子集 | `[F-v3-runtime-state-mapping-failed]` |
| nested output special case | 允许 `{"data": {phase_id: {...}}}` 这类命名空间输出 | Agent `finish_task` 当前把结果写到 `data_updates[phase_id]` | 当 `data` 只有一个 key 且嵌套 dict 的 key 都属于 allowed 时放行: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:56` | `[F-v3-runtime-state-mapping-failed]` |
| `invalid` | 未声明输出字段列表 | 需要给 Studio/trace 标出具体违规 key | `sorted(key for key in data if key not in allowed)` 非空即 FATAL | `[F-v3-runtime-state-mapping-failed]` |

## PhaseWrapper: 三类 runtime phase 的统一拦截器

`PhaseWrapper(mapper)` 是统一调用壳: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:70`。`wrap(node)` 返回 `_wrapped(state)`, 先用 `mapper.build_phase_input(state)` 切片, 再执行原 node, 最后用 `mapper.wrap_phase_output(result)` 封口。已是 `GraphAgentFatalError` 的错误原样抛出, 其他异常包装成 `[F-v3-runtime-state-mapping-failed]`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:75`。

`graph_assembler.py` 当前对 LOGIC、SUBGRAPH、Agent/SKILL 三类 runtime phase 都调用 `_wrap_phase_runtime_node()`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:129`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:131`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:142`。如果 AST 没有 `io`, node 原样返回; 如果有 `io`, 就走 wrapper: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:158`。

### PhaseWrapper 字段

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `mapper` | 保存当前 phase 的 StateMapper | wrapper 不应自己理解 schema, 只委托 mapper | 必须有 `build_phase_input()` 和 `wrap_phase_output()` | `[F-v3-runtime-state-mapping-failed]` |
| `node` | 原始 LangGraph node callable | wrapper 的目标是拦截边界, 不是替代业务执行 | callable 接收 `BlackboardState`, 返回 dict | `[F-v3-runtime-phase-failed]` / `[F-v3-runtime-state-mapping-failed]` |
| `_wrapped(state)` | LangGraph 实际调用的 node | 所有有 IO 的 phase 必须从这里进入 | try 块内切片、执行、封口 | `[F-v3-runtime-state-mapping-failed]` |
| `GraphAgentFatalError` passthrough | 保留更精确错误码 | 如果把细分错误全包成 state mapping, Studio 定位会变差 | 捕获后直接 `raise`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:80` | 原错误码 |
| generic exception wrapping | 把非契约异常归一到 runtime state mapping | 否则任意 Python 异常会漏出无结构消息 | `except Exception as exc` 包装为 `GraphAgentFatalError` | `[F-v3-runtime-state-mapping-failed]` |

## 四类调用边界: Agent、LOGIC、SUBGRAPH、builtin reader

V0.3.0 的 Phase Wrapper 概念覆盖四类边界。前三类是 runtime graph phase, 当前源码用同一个 `PhaseWrapper` 处理; 第四类 builtin reference reader 发生在装配期, 通过 `ReaderSandboxState` 和 builtin spec 定义同样的沙盒边界。

### 四类 wrapper 语义

| Wrapper 类型 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| Agent phase wrapper | 让 Agent 只看到 `phase.io.inputs`, 只通过 `finish_task` 写 `phase.io.outputs` | LLM 不应看到全黑板或写任意顶层 key | `_build_skill_node()` 被 `_wrap_phase_runtime_node()` 包住; finish_task 成功写 `data_updates[phase_id]`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:346` | `[F-v3-agent-io-schema-invalid]` / `[F-v3-runtime-state-mapping-failed]` |
| LOGIC phase wrapper | 让确定性 action 只读 state slice, 只写声明输出 | Python action 权限太大, 必须用 schema 收口 | `_build_logic_node()` 返回 `{"data": updates}` 后由 StateMapper 校验输出 key: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:176` | `[F-v3-logic-output-field-undeclared]` / `[F-v3-runtime-state-mapping-failed]` |
| SUBGRAPH phase wrapper | 把父 phase input 送进 child graph, 再把 child output 包成父 phase output | 子图不能直接 touch 主图全量 `data/flow` | 当前 `_build_subgraph_node()` 仍用 `before_data`; 完成态应先用 parent phase input, 再走 child root funnel: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:209` | `[F-v3-subgraph-io-mismatch]` / `[F-v3-runtime-state-mapping-failed]` |
| Builtin reference reader wrapper | 装配期读取 references 并生成 knowledge_base markdown | reader 是质量增强模块, 不应读取父 runtime blackboard 或阻塞主图 | 用 `ReaderSandboxState.to_blackboard()` 构造独立黑板; spec 定义超时/异常/输出非法 WARN fallback | `[F-v3-reference-reader-input-invalid]` / `[F-v3-reference-reader-failed]` |

## LOGIC 输出: Context delta 与 schema 封口

LOGIC node 执行时先复制 phase-local `state.data`, 再创建 `Context(data, phase_id=..., run_id=...)`, 执行业务 action, 最后用 `_dict_delta(before, data)` 找出 Context 被改动的字段: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:176`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:181`。如果 action 直接返回 dict, 还会做 legacy 输出 key 校验并合入 updates: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:182`。

### LOGIC state 字段

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `before` | action 执行前的数据快照 | 没有快照就无法区分 action 真正写了什么 | `dict(state.get("data", {}))` | `[F-v3-runtime-state-mapping-failed]` |
| `data` | 给 `Context` 的可变工作副本 | action 需要可写局部对象, 但不能直接改全局 state | `dict(before)` 浅拷贝 | `[F-v3-runtime-state-mapping-failed]` |
| `Context` | LOGIC action 的读写 facade | 让 action 拿到 phase_id/run_id, 而不是直接操作 LangGraph state | `Context(data, phase_id=phase_id, run_id=...)` | `[F-v3-runtime-state-mapping-failed]` |
| `result` | action 显式返回值 | 返回 dict 是直接写回输出的一条路径 | `isinstance(result, dict)` 时校验 key 后合入 updates | `[F-v3-actions-keys]` / `[F-v3-logic-output-field-undeclared]` |
| `updates` | 最终 `data` delta | 只应写回 action 改动或返回的字段 | `_dict_delta(before, data)`, 再 `updates.update(result)` | `[F-v3-runtime-state-mapping-failed]` |

## Agent 输出: finish_task 写入 phase 命名空间

Agent phase 的输出不来自直接返回业务 dict, 而来自 LLM 调用 `finish_task`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:281`。当 `finish_task` 返回 `{"ok": true, "data": ...}` 时, runtime 写 `data_updates[phase_id] = result.get("data", {})`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:346`。这就是 `StateMapper.wrap_phase_output()` 允许单 key nested dict 的原因: Agent 输出常以 phase id 作为命名空间。

### Agent state 字段

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `flow` | 保存 finish_task_result、critic_metrics 等控制结果 | 控制态不能被当作业务输出进入 data | `_skill_node()` 复制 `dict(state.get("flow", {}))`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:298` | `[F-v3-runtime-state-mapping-failed]` |
| `messages` | Agent 本轮对话历史 | Prompt history 影响 LLM 行为, 必须明确是否继承 | 初始为 SystemMessage + phase-local messages: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:299` | `[F-v3-runtime-state-mapping-failed]` |
| `finish_task_result` | 保存最终工具调用结果 | trace 和后续诊断需要知道终止原因 | 写入 `flow["finish_task_result"]`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:347` | `[F-v3-runtime-state-mapping-failed]` |
| `data_updates[phase_id]` | Agent 输出命名空间 | 防止 Agent 直接覆盖 root input 或其他 phase 输出 | 仅当 result dict 且 `ok` 为真时写入 | `[F-v3-runtime-state-mapping-failed]` |
| `critic_metrics` | critic/reviewer 工具统计 | 控制指标不应混入业务 data | 写入 `flow.setdefault("critic_metrics", {})`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:350` | `[F-v3-runtime-state-mapping-failed]` |

## SUBGRAPH 和 subagent: 子图黑板沙盒

子图隔离有两层: 固定 SUBGRAPH phase 和 Agent 动态 subagent tool。当前 `_build_subgraph_node()` 会把父图 `before_data` 作为 child `data` 传入, 再把 child result diff 回父图: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:209`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:220`。当前 `_invoke_subagent_once_t23()` 也会构造 `{**before_data, **input_data}` 作为 child data: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:582`。

V0.3.0 完成态的契约更严格: child graph 的初始 `data` 只来自显式输入经过 child root `GRAPH.md io.inputs` 漏斗后的 canonical dict, 不继承 parent data; child result 作为 tool result 或 SUBGRAPH phase output 返回, 不自动 patch 父图扁平黑板。

### child graph 隔离字段

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `target_skill` | 找到 child graph skill | child schema 只有解析到目标 skill root 后才知道 | 通过 `SkillResolverProtocol` 解析, 目录必须含 `GRAPH.md` | `[F-v3-skill-not-registered]` / `[F-v3-resolver-path-invalid]` |
| child `GRAPH.md io.inputs` | child input funnel 的 schema | 父图不能凭自己的 schema 猜 child 需要什么 | 必须是 object schema; 字段集合与父调用 IO 对齐 | `[F-v3-graph-io-schema-invalid]` / `[F-v3-subgraph-io-mismatch]` |
| explicit input | 父 phase 或 LLM 明确传给 child 的参数 | 防止 child 偷读父图全量黑板 | 必须满足 child root input schema | `[F-v3-runtime-state-mapping-failed]` |
| `child.data` | child graph 初始业务黑板 | 读隔离的核心, 不应含 parent data 其他字段 | 完成态只等于 canonical explicit input; 当前源码仍继承父 data | `[F-v3-runtime-state-mapping-failed]` |
| `child.flow` | child 控制态 | child retry/depth 不能原地污染父 flow | deep copy parent flow, 写入 subagent depth / child run metadata | `[F-v3-runtime-state-mapping-failed]` |
| `child.messages` | child LLM 历史 | child graph 不应继承父 Agent 对话 | 固定从 `[]` 开始: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:215`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:588` | `[F-v3-runtime-state-mapping-failed]` |
| child result | 返回父图的结果 | 写隔离要求父图只接收声明输出 | SUBGRAPH 包成 phase output; subagent 包成 tool result | `[F-v3-subgraph-io-mismatch]` / `[F-v3-runtime-state-mapping-failed]` |

难点 3: **玻璃罩**。child graph 可以完整运行自己的图, 但它看到的是显式输入构成的透明罩内环境, 不是父图整块黑板。这样 child 的读取、写回、trace 都能和父图分开定位。

## ReaderSandboxState: builtin reference reader 的装配期沙盒

`ReaderSandboxState` 是给 builtin reference reader 准备的隔离状态 envelope: `skill_id`, `phase_id`, `root`, `timeout_s`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:91`。`to_blackboard()` 生成一个新的 `BlackboardState`, data 只含 `skill_id` 和 `phase_id`, flow 只含 `timeout_s`, messages 为空, run_id 为 `None`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:99`。

### ReaderSandboxState 字段

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `skill_id` | 标识当前 graph skill | reader 输出和 WARN 需要定位来源 skill | 必填 string; 进入 `data.skill_id` | `[F-v3-reference-reader-input-invalid]` |
| `phase_id` | 标识当前 Agent phase | 同一 skill 可能有多个 Agent references registry | 必填 string; 进入 `data.phase_id` | `[F-v3-reference-reader-input-invalid]` |
| `root` | 当前 skill root | reader 读取 reference path 时必须以 skill root 为边界 | `Path`; 当前 `to_blackboard()` 不写入 data, 但执行层应用它校验 path | `[F-v3-resource-reference-path-invalid]` |
| `timeout_s` | reader 最大执行时间 | 装配期增强不能无限阻塞主图 | int, 默认 `60`; 写入 `flow.timeout_s` | `[F-v3-reference-reader-failed]` WARN |
| `data` | reader 业务输入区 | 不应继承父 runtime data | `{"skill_id": ..., "phase_id": ...}`; 完成态还应加入 references 列表 | `[F-v3-reference-reader-input-invalid]` |
| `flow` | reader 控制态 | reader 超时/降级策略需要控制参数 | `{"timeout_s": timeout_s}` | `[F-v3-reference-reader-failed]` WARN |
| `messages` | reader LLM 历史 | reader 不是父 Agent 的一轮对话 | 固定 `[]` | 无 |
| `run_id` | reader 黑板运行 id | 装配期 reader 可由 trace 单独记录, 不复用 runtime run_id | 当前为 `None` | 无 |

### builtin reader JSON 契约

| 字段 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| input `skill_id` | trace 定位来源 skill | reader 失败需要回到具体 graph skill | string, 必填 | `[F-v3-reference-reader-input-invalid]` |
| input `phase_id` | trace 定位来源 Agent phase | 多 Agent 共用 references 时必须区分 | string, 必填 | `[F-v3-reference-reader-input-invalid]` |
| input `references` | reader 要处理的资料集合 | 没有 registry 限制会读到未声明文件 | list, 默认 `[]`; 每项含 `id/path/summary/content` 或可读 path | `[F-v3-reference-reader-input-invalid]` |
| input `max_output_tokens` | 控制 knowledge_base 注入体积 | 过大污染 prompt, 过小丢失关键信息 | integer, 默认 `3000`, 范围 `500 <= n <= 12000`: `docs/engine/skill-spec/09-builtin-modules-spec.md:22` | `[F-v3-reference-reader-input-invalid]` |
| input `language` | 控制报告语言 | 语言只影响表达, 不应影响资料读取 | string, 默认 `"zh"` | 无 |
| output `markdown` | 注入 cognitive template 的资料报告 | 空输出会让 reference reader 失去意义 | 非空 Markdown | `[F-v3-reference-reader-output-invalid]` |
| output `used_reference_ids` | 记录实际使用了哪些资料 | trace 需要证明输出来自哪些 reference | list[string], 必须是输入 references id 子集 | `[F-v3-reference-reader-output-invalid]` |
| output `warnings` | 记录截断或非阻塞问题 | 不应把所有质量问题升级为 FATAL | list[string], 默认 `[]` | 无 |

reader 超时、抛异常或输出非法是装配期 WARN, 使用原文 excerpt fallback, 错误码 `[F-v3-reference-reader-failed]`: `docs/engine/skill-spec/09-builtin-modules-spec.md:56`。单个 reference path 不可读是编译期 FATAL, 不进入 reader: `docs/engine/skill-spec/09-builtin-modules-spec.md:58`。

## SkillResolver 接轨: 先 resolve, 再 funnel

StateMapper 不负责解析 `target_skill`, 但 child graph 输入漏斗依赖解析结果。完成态顺序必须是: `target_skill` 通过 `SkillResolverProtocol` 解析到 child root, 编译 child `GRAPH.md`, 取 child root `io.inputs`, 再把父图显式 input 过滤/校验成 `child.data`。

### resolver 接轨字段

| 字段 / 步骤 | (a) 干什么用 | (b) 为什么必须校验 | (c) 校验通过 / 失败判定 | (d) 错误码 |
|---|---|---|---|---|
| `skill_resolver` | 外部注入的 child skill 解析能力 | Engine 不应从相对路径猜 Studio registry | 入口传入并透传到 compile/assemble child graph | `[F-v3-resolver-missing]` |
| `target_skill` | child skill registry id | child root 是 child IO schema 的来源 | 合法 skill id, resolver 可解析 | `[F-v3-resolver-skill-id-invalid]` / `[F-v3-skill-not-registered]` |
| child root `GRAPH.md` | child 输入输出契约真相源 | 没有 child schema 就不能做 1:1 IO 对齐 | root 是目录且含 `GRAPH.md` | `[F-v3-resolver-path-invalid]` |
| child `io.inputs` | explicit input 的漏斗规则 | 父图字段名和 child 形参必须严格闭合 | object schema; required/properties 合法 | `[F-v3-graph-io-schema-invalid]` |
| parent SUBGRAPH `io.inputs` | 调用方声明的实参形状 | 防止父图传多、传少或类型错 | 与 child `io.inputs` 字段集合和同名 schema 对齐 | `[F-v3-subgraph-io-mismatch]` / `[F-v3-subgraph-io-schema-incompatible]` |

## 错误码全清单

| 错误码 | 阶段 | 触发条件 | 修复方向 | 来源 |
|---|---|---|---|---|
| `[F-v3-state-conflict]` | 运行期 | 当前 `shallow_dict_merge()` 发现 `right` key 已存在于 `left` | 拆分 phase 输出命名空间, 或区分顺序覆盖与并行冲突 | 当前源码 `packages/graph-agent/src/graph_agent/runtime/state.py:28` |
| `[F-v3-runtime-state-mapping-failed]` | 运行期 | StateMapper 切片、输出封口、child input funnel 或 wrapper 包装异常失败 | 检查 phase IO、上游输出、node 返回结构 | spec `docs/engine/skill-spec/11-error-code-spec.md:159` |
| `[F-v3-graph-io-not-object]` | 编译期 | 根 IO 顶层不是 object schema | 修正 `GRAPH.md io.inputs/io.outputs` | spec `docs/engine/skill-spec/11-error-code-spec.md:68` |
| `[F-v3-graph-io-schema-invalid]` | 编译期 / 运行前 | 根 IO JSON Schema 非法或 child root IO 不合法 | 修 schema required/properties/type | spec `docs/engine/skill-spec/11-error-code-spec.md:69` |
| `[F-v3-graph-io-physical-file-deprecated]` | 编译期 | 继续使用旧 `io/inputs.json` / `io_outputs_ref` | 改为 `GRAPH.md` inline IO | spec `docs/engine/skill-spec/11-error-code-spec.md:70` |
| `[F-v3-logic-output-field-undeclared]` | 运行期 | LOGIC action 返回未声明输出字段 | 更新 `io.outputs` 或删除返回字段 | spec `docs/engine/skill-spec/11-error-code-spec.md:79` |
| `[F-v3-subgraph-io-schema-invalid]` | 编译期 | SUBGRAPH phase IO schema 非法 | 修正 SUBGRAPH `io` object schema | spec `docs/engine/skill-spec/11-error-code-spec.md:89` |
| `[F-v3-subgraph-io-mismatch]` | 编译期 / 运行前 | 父 SUBGRAPH IO 与 child GRAPH IO 字段不一致 | 对齐父 phase 和 child graph IO | spec `docs/engine/skill-spec/11-error-code-spec.md:90` |
| `[F-v3-subgraph-io-schema-incompatible]` | 编译期 / 运行前 | 父子同名字段 schema 不兼容 | 统一同名字段类型和约束 | spec `docs/engine/skill-spec/11-error-code-spec.md:91` |
| `[F-v3-reference-reader-input-invalid]` | 装配期 | reader 输入 JSON 缺字段或类型非法 | 检查 references registry 和 reader input | spec `docs/engine/skill-spec/11-error-code-spec.md:156` |
| `[F-v3-reference-reader-output-invalid]` | 装配期 | reader 输出缺 `markdown` 或 id 集合非法 | 修 builtin reader 输出 | spec `docs/engine/skill-spec/11-error-code-spec.md:157` |
| `[F-v3-reference-reader-failed]` | 装配期 WARN | reader 超时、抛异常或输出非法后降级 | 查看 trace; fallback 后主图仍可运行 | spec `docs/engine/skill-spec/11-error-code-spec.md:138` |
| `[F-v3-resource-reference-path-invalid]` | 编译期 / 运行期 | reference path 不可读或逃逸 skill root | 修正 reference path | spec `docs/engine/skill-spec/11-error-code-spec.md:128` |
| `[F-v3-resolver-missing]` | 运行期 | child graph 需要 resolver 但未注入 | 在 compile/run/assemble 入口传入 resolver | spec `docs/engine/skill-spec/11-error-code-spec.md:149` |
| `[F-v3-skill-not-registered]` | 编译期 / 装配期 | resolver 查不到 child skill | 在 Studio 导入或注册 skill | spec `docs/engine/skill-spec/11-error-code-spec.md:146` |

## V0.3.0 四个改造点如何落地

| 改造点 | 完成态代码语义 |
|---|---|
| C7 | Runtime Input Funnel 只消费 `GRAPH.md` inline `io.inputs`; 旧 `io/inputs.json` 和 `io_inputs_ref` 不再作为运行入口契约。 |
| C8 | Agent、LOGIC、SUBGRAPH、builtin reference reader 四类调用边界都经过 wrapper/sandbox; 前三类由 `PhaseWrapper(StateMapper(...))` 拦截, reader 由 `ReaderSandboxState` 和 builtin JSON 契约隔离。 |
| NEW-1 | builtin reference reader 不继承父 graph `data/flow/messages`; 装配期独立黑板, 失败走 WARN `[F-v3-reference-reader-failed]` 和 raw excerpt fallback。 |
| NEW-2 | child graph 先通过 `SkillResolverProtocol` 解析 `target_skill`, 再读取 child `GRAPH.md io.inputs` 做 explicit input funnel, 实现读写双向隔离。 |

读代码时建议先看 `state.py` 的 `BlackboardState` 和 reducer, 再看 `state_mapper.py` 的 `StateMapper` / `PhaseWrapper`, 然后看 `graph_assembler.py` 中 `_wrap_phase_runtime_node()` 如何包住三类 runtime phase, 最后用 builtin spec 对照 `ReaderSandboxState` 的装配期沙盒语义。
