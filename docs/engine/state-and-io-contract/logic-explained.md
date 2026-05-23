# state-and-io-contract V0.3.0 代码逻辑翻译

本文解释 V0.3.0 完成态下 `state-and-io-contract` 子模块具体在做什么: 它如何把整张图的运行状态收口到 `BlackboardState`, 如何让 `StateMapper` 按 phase 的 `io.inputs` 做数据切片, 如何在 phase 返回后按 `io.outputs` 封住写回边界, 以及为什么这些动作必须 Fail-fast。它不是 baseline 的现状复盘, 也不是 mvp0-alignment 的待办清单; 它是对当前源码中 state / mapper 机制的自然语言翻译, 并标明完成态语义应如何理解。

核心源码锚点:

- `BlackboardState` 和 `shallow_dict_merge()` 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 与 `packages/graph-agent/src/graph_agent/runtime/state.py:35`。
- `schema_properties()`, `filter_runtime_inputs()`, `StateMapper`, `PhaseWrapper`, `ReaderSandboxState` 定义在 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:15`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:24`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:34`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:70`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:91`。
- LangGraph 装配时用 `StateGraph(BlackboardState)` 作为全图状态类型: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:77`。
- 每个带 `io` 的 phase 会被 `_wrap_phase_runtime_node()` 套上 `PhaseWrapper(StateMapper(io.inputs, io.outputs))`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:158`。
- LOGIC、SUBGRAPH、Agent/subagent 都在 `graph_assembler.py` 中读写这份 state, 关键位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:176`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:209`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:290`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:576`。

## 模块边界

`state-and-io-contract` 只管运行时数据能不能流动、能流到哪里、写回来之前要不要拦。它不解析 Markdown, 不判断 DAG 是否成环, 不选择模型, 不解析 `target_skill`, 也不执行业务 action。那些事情分别属于 skill-compilation、execution-runtime、graph-agent-gateway 和 skill-resolution。

它的核心对象只有几个:

- `BlackboardState`: 全图共享状态容器。
- `shallow_dict_merge`: `data` 的 LangGraph reducer, 用来合并 node 返回的业务数据。
- `StateMapper`: phase 执行前后的数据切片和输出封口机制。
- `PhaseWrapper`: 把 `StateMapper` 套到 LOGIC / SUBGRAPH / Agent 节点外层。
- `ReaderSandboxState`: builtin reference reader 的装配期隔离黑板。

这里唯一需要的形象名词是 **配料员**: `StateMapper` 不做菜, 也不决定菜谱; 它只按 phase 声明的 `io.inputs` 从全局黑板取料, 再按 `io.outputs` 检查成品能不能端回去。

## BlackboardState 是全图黑板

`BlackboardState` 是 `TypedDict(total=False)`, 运行时仍是普通 dict, 但类型层面固定了四个 key: `data`, `flow`, `messages`, `run_id`: `packages/graph-agent/src/graph_agent/runtime/state.py:35`。LangGraph 在 `StateGraph(BlackboardState)` 中使用它, 所以每个 node 返回的 patch 最后都会落到这四个区域之一: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:77`。

`data` 是业务数据区。它保存外部输入、LOGIC action 的返回、SUBGRAPH child result 的 delta、Agent `finish_task` 产出的业务结果。源码把它声明为 `Annotated[dict[str, Any], shallow_dict_merge]`: `packages/graph-agent/src/graph_agent/runtime/state.py:38`。这意味着 `data` 不是普通覆盖, 而是由 `shallow_dict_merge()` 负责合并。完成态里, 业务语义应收敛为 root inputs 和 phase outputs 的可追踪集合; 当前源码仍是一个扁平 dict, 但 `StateMapper` 已经开始用 `io.inputs` / `io.outputs` 在 phase 边界切片和封口。

`flow` 是控制态, 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:39`。它不是业务输出, 适合放 `finish_task_result`, subagent retry count, critic metrics, subagent depth 之类的运行控制信息。`StateMapper.build_phase_input()` 会对它做 `deepcopy`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:43`。这个 copy 很重要: phase 内部改控制态时, 不应该通过同一个 dict 引用悄悄污染父状态。

`messages` 是 LLM 对话历史, 使用 LangGraph 的 `add_messages` reducer: `packages/graph-agent/src/graph_agent/runtime/state.py:40`。Agent node 会把 system prompt 和已有 messages 组合成本轮对话入口: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:299`。SUBGRAPH 和 subagent child graph 则从空 messages 启动, 防止子图继承父 Agent 的 prompt history: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:215`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:588`。

`run_id` 是运行标识, 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:41`。`StateMapper` 原样复制它: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:45`。subagent item 会额外得到新的 child `run_id`, 并在 metadata 中保留 `parent_run_id` 和 `subagent_depth`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:676`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:682`。

## data reducer 的 Fail-fast 语义

`shallow_dict_merge(left, right)` 是 `data` 的最后一道合并防线。它只看顶层 key, 不做递归深合并: `packages/graph-agent/src/graph_agent/runtime/state.py:13`。左侧为空时返回右侧浅拷贝, 右侧为空时返回左侧浅拷贝: `packages/graph-agent/src/graph_agent/runtime/state.py:19`, `packages/graph-agent/src/graph_agent/runtime/state.py:21`。

真正的关键在冲突分支: 遍历 `right.items()` 时, 只要 `key in merged`, 就抛 `GraphAgentFatalError("[F-v3-state-conflict] ...")`: `packages/graph-agent/src/graph_agent/runtime/state.py:24`, `packages/graph-agent/src/graph_agent/runtime/state.py:27`。这不是温和覆盖, 而是 Fail-fast。原因是 LangGraph fan-in 时如果两个分支都写同一个业务字段, runtime 无法知道哪个值应该赢。直接失败比静默覆盖安全。

完成态语义需要更精细地区分"并行分支冲突"和"拓扑顺序上的合法覆盖"。当前 reducer 还没有 super-step 上下文, 所以它看到同名 key 就失败。StateMapper 的职责就是尽量让每个 phase 写到明确的输出命名空间, 减少 reducer 在最后一步才发现冲突。

## schema_properties 与输入漏斗

`schema_properties(schema)` 是最小 schema 读取函数。它只认 JSON Schema 顶层 `properties` 下的字符串 key: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:15`。如果 `schema` 不是 dict, 或 `properties` 不是 dict, 它返回空集合: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:16`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:18`。这说明当前源码做的是字段名级别的过滤, 不是完整 JSON Schema validation。

`filter_runtime_inputs(raw_inputs, schema)` 用这些 property keys 过滤输入: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:24`。如果 schema 没有可识别的 keys, 它返回 `dict(raw_inputs)`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:27`。如果 keys 非空, 它只保留同时出现在 schema 和 raw inputs 里的字段: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:30`。

这就是运行时输入漏斗的源码基础。完成态里, root `GRAPH.md io.inputs` 和 phase `io.inputs` 应该在编译期已经被验证成 object schema; runtime 再用这个 schema 过滤 unknown fields、检查 required 和类型。当前源码先实现了最关键的一步: phase 不再默认看到整张 `data`, 而是只拿 schema properties 中声明过的那部分。

如果没有这一步, 一个 LOGIC action 或 Agent prompt 可能隐式读取上游没有声明给它的字段。短期看这样很方便, 长期会让 graph 的数据流变成不可审计的全局变量访问。

## StateMapper: phase 前切片, phase 后封口

`StateMapper` 是 `@dataclass(frozen=True)`, 只有两个配置字段: `input_schema` 和 `output_schema`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:33`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:37`。它不执行业务逻辑, 只做 phase 边界上的 state 变换。

`input_schema` 决定 phase 能读什么。`build_phase_input(state)` 创建新的 phase-local `BlackboardState`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:40`。其中 `data` 由 `filter_runtime_inputs(dict(state.get("data", {})), self.input_schema)` 生成: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:42`。这一步是读隔离: phase 拿到的是当前声明允许的业务字段切片, 不是父 graph 的整块数据。

`flow` 在 phase-local state 中是 deep copy: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:43`。这里不能只做浅拷贝, 因为 flow 里面可能有 retry count 或 nested metrics。浅拷贝会让 phase 内部修改嵌套对象时回写到父状态, 破坏"先执行、再封口"的边界。

`messages` 是 list copy: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:44`。这能避免直接共享列表对象, 但列表里的 message 对象本身并未深拷贝。当前源码重点是保护列表结构, 而不是重写 LangChain message 对象。

`run_id` 原样复制: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:45`。它是定位信息, 不是业务数据。

`output_schema` 决定 phase 能写什么。`wrap_phase_output(output)` 先看 `output.get("data")`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:49`。如果 `data` 不是 dict, 当前直接放行: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:51`。如果没有可识别的 output properties, 也直接放行: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:53`。这两个放行分支说明当前实现是渐进式封口, 依赖编译产物提供完整 `io.outputs`。

当 output properties 存在时, mapper 会检查 phase 写回的 `data` key 是否都在允许集合里: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:60`。发现未声明 key 时, 抛 `[F-v3-runtime-state-mapping-failed] phase wrote undeclared keys`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:62`。这是写隔离的 Fail-fast 点。它把错误拦在 phase 返回边界, 而不是让污染字段进入后续节点。

还有一个当前源码里的兼容分支: 如果 `data` 只有一个 top-level key, 且这个 key 的 value 是 dict, 并且 nested dict 的 keys 都属于 allowed properties, mapper 会放行: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:56`。这是为了兼容 Agent `finish_task` 当前写 `data_updates[phase_id] = result.get("data", {})` 的形状: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:346`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:349`。换句话说, Agent 输出可以先挂在 phase_id 命名空间下, mapper 仍能验证里面的业务字段没有越界。

## PhaseWrapper 把规则套到节点上

`PhaseWrapper` 是非常薄的一层调用壳。它保存一个 `StateMapper`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:70`。`wrap(node)` 返回 `_wrapped(state)`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:75`。真正执行时只做三件事:

1. 调 `self.mapper.build_phase_input(state)`, 给 node 一个局部 state: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:78`。
2. 执行业务 node。
3. 调 `self.mapper.wrap_phase_output(result)`, 在返回全局 graph 之前封口: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:79`。

如果业务 node 已经抛 `GraphAgentFatalError`, wrapper 原样抛出: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:80`。这样更具体的错误码不会被抹掉。其它普通异常会被包装成 `[F-v3-runtime-state-mapping-failed]`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:82`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:83`。这不是说所有业务异常本质都是 state mapping 错, 而是 phase 边界发生了无法安全转换的异常, runtime 需要用统一错误码阻断脏状态进入 graph。

装配点在 `_wrap_phase_runtime_node()`: 它先取 `phase_ast.io`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:158`。没有 `io` 就返回原 node; 有 `io` 就返回 `PhaseWrapper(StateMapper(io.inputs, io.outputs)).wrap(node)`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:159`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:162`。

这意味着 IO contract 真正生效的前提是编译出的 AST 上有 `io`。如果某个 legacy node 没有 `io`, 当前 runtime 不会强行猜它的输入输出边界。

## 三类 runtime phase 如何经过 StateMapper

LOGIC phase 的 node 在 `_build_logic_node()` 中创建。它从 phase-local `state.data` 复制出 `before`, 再复制一份 `data` 给 `Context`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:176`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:177`。action 可以通过 `Context` 修改这份局部 data, 也可以直接返回 dict。runtime 先用 `_dict_delta(before, data)` 找隐式修改, 再合并显式返回: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:181`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:182`。最后返回 `{"data": updates}`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:185`。如果这份 updates 写了未声明字段, StateMapper 会在外层 wrapper 里拦住。

SUBGRAPH phase 当前仍把 `before_data = dict(state.get("data", {}))` 作为 child graph 的 data: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:209`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:213`。child messages 从空列表开始: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:215`。child 执行结束后, runtime 用 `_dict_delta(before_data, result_data)` 计算 data updates: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:219`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:220`。完成态应进一步收窄: child 初始 data 不应继承父 graph 全量 `data`, 而应只来自父 SUBGRAPH phase 的显式 input, 再通过 child root `GRAPH.md io.inputs` 漏斗。

Agent phase 的 node 在 `_build_skill_node()` 中创建。它先复制 `flow`, 组装 `messages`, 再进入 ReAct loop: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:297`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:299`。当 LLM 调 `finish_task` 且结果 `ok` 为真时, runtime 把业务结果放到 `data_updates[phase_id]`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:346`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:349`。这就是为什么 `wrap_phase_output()` 需要识别单 key nested dict: Agent 输出常用 phase id 做命名空间, 内部字段才是 `io.outputs` 要验证的业务字段。

这三类 phase 的共同点是: 业务 node 不直接决定自己能读全局多少数据、能写回哪些字段。只要 AST 有 `io`, 外层 `PhaseWrapper` 就先切片、后封口。

## subagent 与 child graph 的隔离

Agent 动态 subagent tool 走 `_invoke_subagent_once_t23()`。当前源码先取父 graph 的 `before_data`, 再构造 `child_data = {**before_data, **input_data}`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:582`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:583`。child graph 运行时 messages 为空, run_id 继承 parent state 的 run_id: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:586`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:588`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:589`。

这段代码说明当前实现已经隔离了 messages, 但 data 仍然带着父图全量字段。完成态的 state/io 契约要更严格: child graph 的输入应来自 tool call 的 explicit input, 然后按 child skill root 的 `GRAPH.md io.inputs` 过滤和校验。父图 data 只能作为调用上下文被显式传入, 不能默认暴露。

child 返回后, runtime 仍然通过 `_dict_delta(before_data, result_data)` 计算 child 相对父 data 的差量: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:593`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:594`。subagent tool 的最终返回是 `{"status": "ok", "data": data_delta, "flow": ...}`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:595`。这代表 subagent 结果先作为 tool result 回到父 Agent, 不等于直接 patch 父 graph 黑板。

child run metadata 由 `_subagent_runnable_config()` 构造。它保留父 `tags` 和 metadata, 写入 `parent_run_id` 与 `subagent_depth + 1`, 并为 child 分配新的 `run_id`: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:673`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:676`, `packages/graph-agent/src/graph_agent/core/graph_assembler.py:682`。这部分属于控制态隔离和 trace 定位, 不应混入业务 `data`。

## ReaderSandboxState 是装配期沙盒

`ReaderSandboxState` 是给 builtin reference reader 准备的隔离 envelope: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:90`。字段有 `skill_id`, `phase_id`, `root`, `timeout_s`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:94`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:95`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:96`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:97`。

`to_blackboard()` 生成一份新的 `BlackboardState`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:99`。它的 `data` 只含 `skill_id` 和 `phase_id`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:101`。它的 `flow` 只含 `timeout_s`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:102`。`messages` 固定为空, `run_id` 为 `None`: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:103`, `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:104`。

这个对象的业务含义是: reference reader 是装配期辅助模块, 不是父 Agent 的一轮对话, 也不是 runtime graph 的普通 phase。它不能继承父 graph 的 `data`, 不能继承父 Agent 的 messages。它只应该拿到当前 skill/phase 的 reference registry 和必要的定位信息。reader 超时、异常或输出非法时, 规范错误码是 `[F-v3-reference-reader-failed]`, 错误码表位于 `docs/engine/skill-spec/11-error-code-spec.md:138`。

## Fail-fast 的价值

state/io 的 Fail-fast 不是为了让系统更容易报错, 而是为了让错误停在最靠近原因的位置。

未知输入字段如果不在入口漏斗被拦, 可能会被下游 LLM 当成合法上下文使用。未声明输出字段如果不在 `wrap_phase_output()` 被拦, 会进入全局 `data`, 之后任何 phase 都可能隐式依赖它。并行写冲突如果不在 reducer 被拦, 后续执行会基于不确定值继续运行。

因此这三类错误都应该尽早失败:

- 输入切片失败或输出封口失败, 使用 `[F-v3-runtime-state-mapping-failed]`: `docs/engine/skill-spec/11-error-code-spec.md:159`。
- reducer 发现同 key 写入冲突, 当前源码使用 `[F-v3-state-conflict]`: `packages/graph-agent/src/graph_agent/runtime/state.py:28`。
- reference reader 输入/输出非法或执行失败, 使用 `[F-v3-reference-reader-input-invalid]`, `[F-v3-reference-reader-output-invalid]`, `[F-v3-reference-reader-failed]`: `docs/engine/skill-spec/11-error-code-spec.md:156`, `docs/engine/skill-spec/11-error-code-spec.md:157`, `docs/engine/skill-spec/11-error-code-spec.md:138`。

这些错误码的共同目标是让 Studio 和工程师定位到具体边界: 是入口输入不合法、phase 写越界、child graph 泄漏, 还是装配期 reader 降级。

## 读代码的顺序

先读 `runtime/state.py`: `shallow_dict_merge()` 解释了为什么 `data` 不能随便覆盖, `BlackboardState` 解释了全图共享状态有哪些区域。

再读 `runtime/state_mapper.py`: `schema_properties()` 和 `filter_runtime_inputs()` 是输入漏斗的最小实现, `StateMapper` 是 phase-local 切片和输出封口, `PhaseWrapper` 是统一拦截壳, `ReaderSandboxState` 是装配期沙盒。

最后读 `core/graph_assembler.py`: `assemble_graph()` 把状态类型交给 LangGraph, `_wrap_phase_runtime_node()` 决定哪些节点进入 StateMapper, LOGIC/SUBGRAPH/Agent/subagent 的 node 函数展示了 state 在真实执行中的读写形状。
