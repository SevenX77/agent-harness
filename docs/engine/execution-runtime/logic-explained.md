# Execution Runtime Logic Explained

本文把 V0.3.0 execution runtime 翻译成可检查的字段级规则。读法很简单: 入口负责把一次 run 变成 `BlackboardState`, assembler 负责把 AST 变成 LangGraph 节点, 每个节点只读自己声明的输入, 只回写自己声明的输出。运行时的关键不是"多跑几个节点", 而是让 graph、model、resolver、subgraph、tool 和 trace 都在同一份黑板契约下收口。

## 1. Runtime Boundary

execution runtime 的边界由三层组成。

| 层 | 代码位置 | 输入 | 输出 | 运行期职责 |
|---|---|---|---|---|
| public runner | `packages/graph-agent/src/graph_agent/core/runner.py:162` | `skill_path`, `inputs`, `mock_llm`, `trace_dir`, `thread_id`, `skill_resolver` | `WorkflowResult` | 包装成功/失败, 记录 run 元信息, 把 V0.3.0 skill root 转交给 dict runner |
| V0.3.0 dict runner | `packages/graph-agent/src/graph_agent/core/runner.py:456` | skill root 目录和运行输入 | `dict` | `compile_skill()` 后调用 `assemble_graph()`, 再用 `graph.invoke()` 执行 |
| graph runtime | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:68` | `CompiledSkill`, `chat_model`, `skill_resolver` | `CompiledStateGraph` | 把 manifest phase 顺序、依赖边和 AST mode 转成 LangGraph |

这里的"调度脊柱"是 `run_skill -> _run_skill_dict -> _run_v21_skill_dict -> assemble_graph -> graph.invoke`。任何 V0.3.0 运行行为都应能落回这条链路上的具体字段。

## 2. `run_skill` Lifecycle

`run_skill()` 是对外稳定入口。它不直接执行 LangGraph, 而是负责把运行结果标准化成 `WorkflowResult`。

| 字段 | 来源 | 代码位置 | 行为 |
|---|---|---|---|
| `skill_path` | 调用方 | `runner.py:162` | 接收文件或目录; 目录且包含 `GRAPH.md` 时进入 V0.3.0/V2.1 graph path |
| `mock_llm` | 调用方 | `runner.py:165` | 非默认值时作为 `chat_model` 传入 graph assembly |
| `trace_dir` | 调用方 | `runner.py:166` | public runner 透传; V0.3.0 dict runner目前只用于返回 `trace_path` 字符串 |
| `thread_id` | 调用方 | `runner.py:167` | 没有提供时生成 UUID; 写入 `BlackboardState.run_id` |
| `callbacks` | 调用方 | `runner.py:169` | public path 接收; V0.3.0 dict runner当前 `del callbacks` |
| `skill_resolver` | 调用方 DI | `runner.py:173` | 透传给 `compile_skill()` 与 `assemble_graph()` |
| `inputs` | kwargs | `runner.py:174` | 写入 `BlackboardState.data` |
| `started_at` | runtime | `runner.py:177` | 用于最终 `WorkflowResult.started_at` |
| `wall_time_sec` | runtime | `runner.py:200` / `runner.py:215` | 失败和成功路径都计算 |
| `context` | graph result | `runner.py:220` | 成功时来自 dict runner `context`; 失败时为空 |

失败路径只捕获 `GraphAgentError`, 并把错误字符串放进 `WorkflowResult.error` (`runner.py:198`)。其它异常仍会向上冒泡, 这是当前源码行为, 不是文档层兜底。

## 3. V0.3.0 Dict Runner

`_run_v21_skill_dict()` 是当前 graph skill 的实际执行函数, 名称仍带 v21, 但它已经承载 V0.3.0 execution runtime 的主路径。

| 步骤 | 代码位置 | 输入 | 输出 | 说明 |
|---|---|---|---|---|
| 选择 chat model | `runner.py:472` | `mock_llm` | `chat_model` | mock 存在时直接作为 `chat_model`; 没有 mock 时为 `None` |
| 编译 skill | `runner.py:474` | `skill_root`, `skill_resolver` | `CompiledSkill` | 编译期可用 resolver 做 target skill 可达性检查 |
| 装配 graph | `runner.py:475` | `compiled`, `chat_model`, `skill_resolver` | LangGraph compiled graph | runtime DI 继续传入 assembler |
| 构造 run id | `runner.py:476` | `thread_id` | `run_id` | 不提供则 UUID |
| invoke 初始状态 | `runner.py:477` | `inputs`, empty flow/messages, run_id | graph result | `data` 是黑板数据, `messages` 初始为空 |
| 返回 context | `runner.py:486` | graph result | `context`, `metrics`, `trace_path` | `metrics` 当前只填 `wall_time_sec` |

初始 `BlackboardState` 的字段就是 runtime 的四个共享槽: `data`, `flow`, `messages`, `run_id` (`runner.py:477`)。

## 4. Blackboard State

`BlackboardState` 是所有节点共同读写的状态结构。

| 字段 | 类型 | 代码位置 | 合并规则 | 业务含义 |
|---|---|---|---|---|
| `data` | `dict[str, Any]` | `runtime/state.py:38` | `shallow_dict_merge` | 业务输入和 phase 输出 |
| `flow` | `dict[str, Any]` | `runtime/state.py:39` | 普通覆盖 | 运行控制信息, 如 `finish_task_result` 和 subagent retry |
| `messages` | `list[AnyMessage]` | `runtime/state.py:40` | LangGraph `add_messages` | Agent 对话上下文 |
| `run_id` | `str | None` | `runtime/state.py:41` | 普通值 | 顶层 run 标识 |

`data` 的合并是浅层冲突检测: 两个并行分支写同一个 top-level key 会抛 `[F-v3-state-conflict]` (`runtime/state.py:27`)。因此字段名就是并发边界, 不是随意命名的临时变量。

## 5. Graph Assembly

`assemble_graph()` 只做确定性结构装配, 不执行业务。

| 装配动作 | 代码位置 | 结果 |
|---|---|---|
| 创建 `StateGraph(BlackboardState)` | `graph_assembler.py:77` | 确定全 graph 状态类型 |
| 按 manifest phases 找 phase document | `graph_assembler.py:82` | 缺失节点时 `_graph_fatal` |
| 为每个 phase 添加节点 | `graph_assembler.py:86` | 节点函数来自 `_build_phase_node()` |
| 无依赖 phase 接 `START` | `graph_assembler.py:99` | graph 入口边 |
| 有依赖 phase 接前置 phase | `graph_assembler.py:103` | manifest `depends_on` 变成边 |
| terminal phase 接 `END` | `graph_assembler.py:108` | graph 结束边 |
| 返回 `CompiledStateGraph` | `graph_assembler.py:112` | 包含 compiled graph、phase ids、edges |

`_build_phase_node()` 按 AST 类型分发: `LogicNodeAST` 进 `_build_logic_node()` (`graph_assembler.py:129`), `SubgraphNodeAST` 进 `_build_subgraph_node()` (`graph_assembler.py:131`), `AgentNodeAST | SkillNodeAST` 进 `_build_skill_node()` (`graph_assembler.py:142`)。

## 6. Phase Wrapper And StateMapper

`PhaseWrapper` 是所有 mode 的共同 IO 闸口。

| 函数 | 代码位置 | 输入 | 输出 | 作用 |
|---|---|---|---|---|
| `schema_properties()` | `runtime/state_mapper.py:15` | JSON schema | property names | 只认 `properties` 下的字符串 key |
| `filter_runtime_inputs()` | `runtime/state_mapper.py:24` | raw inputs, input schema | filtered dict | phase 只看到声明过的输入字段 |
| `StateMapper.build_phase_input()` | `runtime/state_mapper.py:40` | full state | phase state | 复制 `flow/messages/run_id`, 过滤 `data` |
| `StateMapper.wrap_phase_output()` | `runtime/state_mapper.py:49` | node output | validated output | phase 写未声明 key 时 fatal |
| `PhaseWrapper.wrap()` | `runtime/state_mapper.py:75` | node callable | wrapped node | 把普通异常归一为 `[F-v3-runtime-state-mapping-failed]` |

`_wrap_phase_runtime_node()` 只有在 AST 有 `io` 时才套 wrapper (`graph_assembler.py:158`)。因此 V0.3.0 的字段隔离依赖每个 phase AST 的 `io.inputs` 和 `io.outputs` 被正确编译出来。

## 7. LOGIC Runtime

LOGIC 节点是纯 Python action 运行路径。

| 字段/动作 | 代码位置 | 说明 |
|---|---|---|
| `python_callable` | `graph_assembler.py:170` | 通过 `compiled.actions.resolve(phase_id, phase_ast.python_callable)` 解析 |
| action path | `graph_assembler.py:171` | 用于错误定位 |
| action first line | `graph_assembler.py:173` | 用于 `[F-v3-actions-keys]` 报错行号 |
| `before` | `graph_assembler.py:177` | action 前的 `data` 快照 |
| `Context` | `graph_assembler.py:179` | 传给 action 的上下文对象, 含 phase_id/run_id |
| return dict | `graph_assembler.py:182` | 返回 dict 时合并为 data updates |
| implicit mutation delta | `graph_assembler.py:181` | action 改动 context data 时通过 `_dict_delta()` 捕获 |
| output key 校验 | `graph_assembler.py:705` | 未声明输出 key 抛 `[F-v3-actions-keys]` |

V0.3.0 要求 LOGIC action 采用一层地址: phase 只声明自己可写的 output key, action 返回或修改的 top-level key 必须落在该集合内。当前源码的根目录寻址由 `compiled.actions.resolve()` 提供; completion 目标仍是顶层 `Context.data` 的声明字段。

## 8. Agent Runtime Loop

Agent/SKILL 节点共享 `_build_skill_node()`, 但 V0.3.0 Agent 使用新的 cognitive template。

| 运行项 | 代码位置 | 行为 |
|---|---|---|
| business tools | `graph_assembler.py:240` | 从 compiled tool registry 取本 phase 工具 |
| resource tools | `graph_assembler.py:241` | `AgentNodeAST` 追加 `read_reference/read_example` |
| subagent tools | `graph_assembler.py:244` | 由 compiled subagents 生成 `call_subagent_*` 映射 |
| critic tools | `graph_assembler.py:254` | 按名称模式临时构造 |
| finish_task | `graph_assembler.py:281` | 每个 Agent/SKILL 节点固定追加 |
| missing chat model | `graph_assembler.py:294` | 没有 `chat_model` 时抛 `[F-v3-graph] SKILL phase requires chat_model` |
| system prompt | `graph_assembler.py:299` | 来自 `_agent_system_prompt()` |
| model binding | `graph_assembler.py:303` | 支持 `bind_tools()` 时绑定所有工具 |
| max turns | `graph_assembler.py:307` | Agent 用 AST `max_iterations`, legacy skill 用默认 |
| model invoke | `graph_assembler.py:316` | 每轮调用 LLM |
| unknown tool | `graph_assembler.py:324` | LLM 调未知工具时 `_graph_fatal` |
| finish data | `graph_assembler.py:346` | `finish_task.ok` 时写 `data_updates[phase_id]` |

Agent 节点的输出当前以 phase_id 嵌套写回 (`graph_assembler.py:349`)。如果 phase `io.outputs` 声明了扁平字段, `StateMapper.wrap_phase_output()` 会允许一种特殊情况: 单个 nested dict 的 keys 是 allowed 的子集时通过 (`runtime/state_mapper.py:56`)。

## 9. Cognitive Template: 8 Slots

本文按本任务的 V0.3.0 口径说明 8 个业务插槽。源码函数名是 `apply_v030_cognitive_template()` (`cognitive/prompt.py:125`), docstring 仍写 "seven-slot" (`cognitive/prompt.py:139`), 这是旧描述; 实际渲染已经覆盖 role、goal、steps、protocols、examples、knowledge base 和 tail exit contract。

| 插槽 | 来源 | 当前源码落点 | 默认/空值 | 运行期作用 |
|---|---|---|---|---|
| `skill_role` | `AgentNodeAST.role` | `graph_assembler.py:398`, `cognitive/prompt.py:163` | 编译期应保证非空 | 写入 `<role>` |
| `skill_goal` | `AgentNodeAST.goal` | `graph_assembler.py:399`, `cognitive/prompt.py:169` | 编译期应保证非空 | 写入 `<goal>` |
| `skill_steps_splat` | `AgentNodeAST.steps` | `graph_assembler.py:400`, `cognitive/prompt.py:146` | `"无显式步骤"` | 写入 `<steps>` |
| `skill_protocols_splat` | `AgentNodeAST.protocols` | `graph_assembler.py:401`, `cognitive/prompt.py:150` | `"无显式协议"` | 写入 `<protocol_citation>` |
| `reference_reader_subagent_output_markdown` | 预读 reference 的 markdown | `cognitive/prompt.py:134`, `cognitive/prompt.py:179` | `"无预读取参考资料"` | 写入 `<knowledge_base>`; 当前 assembler 未传该参数 |
| `inline_examples_splat` | inline examples | `graph_assembler.py:404`, `cognitive/prompt.py:154` | `"无内联示例"` | 写入 `<examples>` |
| `document_examples_registry` | document examples id/summary | `graph_assembler.py:409`, `cognitive/prompt.py:155` | `"无扩展案例"` | 写入 `<document_examples>` |
| `skill_exit_contract_inline` | `AgentNodeAST.exit_contract` + schema | `graph_assembler.py:402`, `cognitive/prompt.py:210` | 编译期应保证非空 | prompt 尾部 `<exit_contract>` |

这个"八槽板"的重点是每个插槽都有可追踪来源, 而不是让 prompt 拼接成为自由文本。`output_schema` 会追加到 `<exit_contract>` 内 (`cognitive/prompt.py:158`), 所以输出结构和完成条件在 prompt 末尾一起出现。

## 10. Inline Exit Contract

V0.3.0 Agent 的 exit contract 采用 inline tail 方案。

| 路径 | 代码位置 | 行为 |
|---|---|---|
| AgentNodeAST | `graph_assembler.py:396` | `_agent_system_prompt()` 调 `apply_v030_cognitive_template()` |
| exit contract slot | `cognitive/prompt.py:210` | 渲染为尾部 `<exit_contract>` |
| output schema | `cognitive/prompt.py:158` | 非空时追加 `<output_schema>` |
| legacy SkillNodeAST | `graph_assembler.py:311` | 每轮前调用 `inject_exit_contract()` |
| legacy injection | `runtime/exit_contract.py:8` | 把 contract 作为 tail `HumanMessage` 追加 |

因此当前源码里两种策略并存: V0.3.0 `AgentNodeAST` 靠 system prompt 尾部 inline; legacy `SkillNodeAST` 仍使用每轮动态追加。写新 V0.3.0 规则时不要把 legacy 动态追加误认为 Agent 的主路径。

## 11. ModelResolver DI

模型解析的职责是把角色配置解析成 LangChain chat model。它不是 health check, 也不提前制造 fallback 事件。

| 字段/方法 | 代码位置 | 说明 |
|---|---|---|
| `ModelResolver.resolve()` | `models/resolver.py:57` | 接收 `role_name`, `thinking_enabled`, `model_override`, `callbacks`, `phase_name` |
| `total_resolves` | `models/resolver.py:68` | 每次 resolve 增加统计 |
| role config | `models/resolver.py:70` | 从 `llm_roles.yaml` 解析 role/model |
| fallback to factory | `models/resolver.py:76` | 未配置 role 时走 minimal factory |
| peer fallback candidates | `models/resolver.py:84` | 把同组 model 追加到 call chain |
| Gateway model | `models/resolver.py:117` | 返回 `GatewayChatModel` |
| callbacks | `models/resolver.py:122` | 传给 gateway, 由运行时事件使用 |
| phase name | `models/resolver.py:123` | 进入 LLM event 的 phase 维度 |

V0.3.0 的目标接口称为 `ModelResolverProtocol DI`, 当前源码落点是具体 `ModelResolver`。文档上的边界应写成: Engine 节点只依赖"可 resolve 出 LangChain-compatible chat model"的能力; provider fallback 的真实事件在 gateway runtime call loop 里产生, 不是在 resolver construction 时产生。

## 12. LLM Event Timing

LLM 追踪分两类事件。

| 事件 | 代码位置 | 触发时机 | 记录内容 |
|---|---|---|---|
| `LLMCallEvent` | `callbacks/tracing.py:219` | callback 收到一次 LLM call 后 | phase, tokens, messages, response |
| trace json llm call | `callbacks/tracing.py:207` | 同一次 callback 内 | `messages`, `response`, `usage` |
| `LLMFallbackEvent` | `models/gateway_chat_model.py:273` | 某个 provider/model 真实失败并准备切到下一候选时 | phase, from_provider, to_provider, reason |
| fallback callback dispatch | `models/gateway_chat_model.py:279` | 事件对象创建后 | 对每个 callback 调 `on_event()` |

因此 `LLMFallbackEvent` 是真实失败后的运行时事实; 它不能在 `ModelResolver.resolve()` 拼出 call chain 时提前发。`LLMCallEvent` 则是一轮模型调用完成后的统计和快照。

## 13. SkillResolverProtocol DI

跨 skill 的路径解析通过 `SkillResolverProtocol` 隔离 Engine 和 Studio registry。

| 字段/方法 | 代码位置 | 当前源码行为 |
|---|---|---|
| `SKILL_ID_PATTERN` | `skill_resolver_protocol.py:11` | 当前允许大小写、数字、下划线、点和短横线, 长度 1..128 |
| `SkillResolutionError.code` | `skill_resolver_protocol.py:23` | 默认 `[F-v3-skill-not-registered]` |
| `resolve_skill()` | `skill_resolver_protocol.py:35` | 单方法协议, 返回 `str | Path` |
| `validate_skill_id()` | `skill_resolver_protocol.py:39` | 不匹配时报 `[F-v3-invalid-skill-id]` |
| `resolve_skill_root()` | `skill_resolver_protocol.py:50` | 调 resolver 后检查目录和 `GRAPH.md` |
| missing dir | `skill_resolver_protocol.py:64` | 抛 `SkillResolutionError` |
| missing `GRAPH.md` | `skill_resolver_protocol.py:66` | 抛 `SkillResolutionError` |

规范文档 `10-skill-resolver-protocol-spec.md` 写的是小写正则和 `[F-v3-resolver-skill-id-invalid]`; 当前源码尚未完全对齐。execution runtime 文档应以源码为准, 同时把目标设计标为 V0.3.0 alignment 项。

## 14. SUBGRAPH Runtime

SUBGRAPH phase 当前有两条相关路径: manifest phase 的 `SubgraphNodeAST`, 以及 Agent 内部 tool 调用的 subagent。

| 路径 | 代码位置 | 输入隔离 | 输出回写 |
|---|---|---|---|
| `SubgraphNodeAST` root | `graph_assembler.py:190` | 当前用 `_resolve_sub_skill_path(phase_doc.path, phase_ast.sub_skill_ref)` | child result 与 before 做 `_dict_delta()` |
| child compile | `graph_assembler.py:198` | `SkillLoader(validate_context_writes=False)` | 透传 `skill_resolver` |
| child invoke | `graph_assembler.py:211` | 当前传完整 `before_data` | `messages` 重置为空 |
| child flow | `graph_assembler.py:214` | 继承 parent `flow` | 返回 child `flow` |
| path resolver | `graph_assembler.py:721` | 相对 phase path 或绝对路径 | 尚未使用 `target_skill` registry |

V0.3.0 目标语义是 `target_skill` + `SkillResolverProtocol` + 黑板沙盒。当前源码对 `SubgraphNodeAST` 仍保留 legacy `sub_skill_ref` 文件路径解析, 但 assembler 参数已经把 `skill_resolver` 透传到 child compile/assemble。这个差距应在 alignment 中继续收敛。

## 15. Subagent Runtime

Agent subagent tool 路径已经更接近 V0.3.0 的"隔离舱"模型。

| 字段/动作 | 代码位置 | 行为 |
|---|---|---|
| tool name | `graph_assembler.py:376` | `call_subagent_{subagent.name}` |
| runtime map | `graph_assembler.py:553` | 为每个 subagent 编译 child graph |
| resolver passthrough | `graph_assembler.py:562` / `graph_assembler.py:566` | child compile 和 assemble 都接收 `skill_resolver` |
| depth check | `graph_assembler.py:501` | 超深度时 fatal |
| validation retry | `graph_assembler.py:504` | 每个 tool 记录 retry count |
| validation failure | `graph_assembler.py:530` | 返回 tool result, 让 LLM 修参 |
| batch execution | `graph_assembler.py:537` | `_invoke_subagent_many_t24()` |
| child data | `graph_assembler.py:583` | 当前 `{**before_data, **input_data}` |
| child messages | `graph_assembler.py:588` | 子图对话从空开始 |
| data delta | `graph_assembler.py:594` | 只把 child 相对 parent 的差量返回 |
| child run id | `graph_assembler.py:684` | 每个 child item 生成新 UUID |
| metadata | `graph_assembler.py:676` | 带 `parent_run_id` 和 `subagent_depth` |

隔离语义不是说 child 完全看不到 parent data; 当前实现是 child 初始 data 包含 parent data 与 tool input, 但 messages 清空、run id 独立、回写只取 delta。若要达到更严格 V0.3.0 沙盒, 下一步应把 child input 收窄到 subagent input schema。

## 16. Builtin Reference Reader And Resource Tools

reference/example 有两个层面: prompt 装配期的预读报告, 以及 Agent 运行期可调用的读取工具。

| 能力 | 代码位置 | 当前状态 |
|---|---|---|
| reader sandbox state | `runtime/state_mapper.py:90` | 定义 `ReaderSandboxState` |
| sandbox data | `runtime/state_mapper.py:99` | 只放 `skill_id` 和 `phase_id` |
| sandbox flow | `runtime/state_mapper.py:102` | 只放 `timeout_s` |
| sandbox messages | `runtime/state_mapper.py:103` | 空消息 |
| `read_reference` | `graph_assembler.py:426` | 按 reference id 读取 skill root 内文件 |
| invalid reference id | `graph_assembler.py:429` | `[F-v3-resource-reference-id-invalid]` |
| `read_example` | `graph_assembler.py:432` | inline 返回 content, document 读文件 |
| invalid example id | `graph_assembler.py:435` | `[F-v3-resource-example-invalid]` |
| missing example path | `graph_assembler.py:439` | `[F-v3-resource-example-path-invalid]` |
| root escape | `graph_assembler.py:478` | `[F-v3-resource-reference-path-invalid]` |

当前 `_agent_system_prompt()` 没有把预读 reference reader 输出传给 `knowledge_base` (`graph_assembler.py:396`), 所以 prompt 内默认显示"无预读取参考资料" (`cognitive/prompt.py:180`)。运行期工具已可读 declared resources, 但装配期 reader 还需要接入。

## 17. Error Normalization

runtime 错误要优先落到可搜索的错误码。

| 错误码 | 代码位置 | 触发条件 |
|---|---|---|
| `[F-v3-state-conflict]` | `runtime/state.py:27` | 并行分支写同一个 top-level data key |
| `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:62` | phase 写未声明输出 key |
| `[F-v3-runtime-state-mapping-failed]` | `runtime/state_mapper.py:83` | wrapper 捕获普通异常 |
| `[F-v3-actions-keys]` | `graph_assembler.py:715` | LOGIC action 返回未声明 key |
| `[F-v3-graph]` | `graph_assembler.py:294` | Agent/SKILL 节点缺少 chat model |
| `[F-v3-resource-reference-id-invalid]` | `graph_assembler.py:429` | reference id 未注册 |
| `[F-v3-resource-example-invalid]` | `graph_assembler.py:435` | example id 未注册 |
| `[F-v3-resource-example-path-invalid]` | `graph_assembler.py:439` | document example 没有 path |
| `[F-v3-resource-reference-path-invalid]` | `graph_assembler.py:480` | resource path 越过 skill root |
| `[F-v3-invalid-skill-id]` | `skill_resolver_protocol.py:46` | skill id 不符合当前源码正则 |
| `[F-v3-skill-not-registered]` | `skill_resolver_protocol.py:23` | resolver 默认未注册错误 |
| `[F-v3-cognitive-slot-render-failed]` | `docs/engine/skill-spec/11-error-code-spec.md:154` | 规范定义的 template slot render 失败 |
| `[F-v3-cognitive-output-schema-render-failed]` | `docs/engine/skill-spec/11-error-code-spec.md:155` | 规范定义的 output schema 渲染失败 |
| `[F-v3-runtime-phase-failed]` | `docs/engine/skill-spec/11-error-code-spec.md:160` | 规范定义的 phase 泛化失败 |

代码里已经存在的错误码要优先引用源码行; 只在源码尚未落地时引用 spec 行, 并明确它是规范定义。

## 18. V0.3.0 Alignment Checklist

| 改造点 | 当前源码状态 | 目标状态 |
|---|---|---|
| run_skill lifecycle | 已有入口和 V0.3.0 graph path | 补齐 callbacks/trace 在 V0.3.0 path 的贯通 |
| AST to LangGraph | 已有 deterministic assembly | 保持 node dispatch 和 state wrapper 一致 |
| ModelResolverProtocol DI | 当前是具体 `ModelResolver` | 抽象出协议边界, 节点不依赖具体实现 |
| SkillResolverProtocol DI | 协议和 runner/assembler 参数已存在 | SUBGRAPH `target_skill` 全量使用 resolver |
| cognitive 8 slots | 函数已覆盖主要 slot | 接入 reference reader output, 修正文档旧 "seven-slot" 描述 |
| inline exit_contract | Agent 已 inline tail | legacy `SkillNodeAST` 保持兼容或迁移 |
| LOGIC one-level output | 已通过 output key 校验实现 | action registry 路径和错误码继续对齐 spec |
| SUBGRAPH isolation | child messages 清空, delta 回写 | child data 收窄到 input schema, target skill registry 化 |
| subagent isolation | 有 child run id、metadata、delta | 进一步限制 child 可见 data |
| builtin resource tools | runtime tools 已有 | 装配期 reader sandbox 真正接入 `knowledge_base` |
| LLM events | call/fallback 事件已有 | V0.3.0 graph path callbacks 需要贯通到 gateway |

这份文档的判断原则: 如果源码已经落地, 写源码事实; 如果规范要求但源码还没落地, 写成 alignment 目标, 不把目标当成现状。
