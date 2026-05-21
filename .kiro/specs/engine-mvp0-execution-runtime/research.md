# Engine MVP0 — execution-runtime Research

## §1. 现状综述

当前 `execution-runtime` 模块负责将编译后的 `CompiledSkill` 转换为 LangGraph 实例并调度执行。核心入口是 `run_skill()`（`packages/graph-agent/src/graph_agent/core/runner.py:161`），实际执行链为 `compile_skill` -> `assemble_graph` -> `graph.invoke`。虽然基础的 LOGIC、SUBGRAPH 和 SKILL 节点装配已实现（`graph_assembler.py:116-298`），但存在诸多运行时脱节：无 mock 模型时直接宕机（P0-1）；递归调用的上下文与控制流未实现真正隔离（P1-2、A4、A5）；ReAct 对话机制导致系统提示（`exit_contract`）在历史记录中错误堆积（P1-3）；并且整体的错误抛出（如无模型等）依然是裸露的 Python 原生异常，未形成结构化 ErrorCode 体系。

## §2. MVP0 目标拆分

### P0-1 ModelResolver
- **现状**：`_run_v21_skill_dict()` 仅接收 `mock_llm`，若未传入且尝试执行 SKILL 阶段，将直接抛出 `RuntimeError("[F-v21-graph] SKILL phase requires chat_model")`（`graph_assembler.py:233-234`）。目前生产执行路径缺乏真实大模型（如 Anthropic/OpenAI）的自动实例化注入过程。
- **MVP0 目标**：引入 `ModelResolver` 工厂机制，将从 phase frontmatter 中声明的 `llm_role` 解析为真实 `BaseChatModel` 实例。同时，若解析失败应返回标准化错误代码（如 `F-v21-model-not-found`）。

### P1-2 child flow subagent_depth
- **现状**：子代理的调度深度仅被更新到了 `RunnableConfig` 的 `metadata` 中（`graph_assembler.py:482-505`），但在传递给子图的运行时 `flow` 字典里，依旧提取的还是 `parent_state.get("flow", {})`（`graph_assembler.py:400`），这使得真正的子图内部并不知道自己身处第几层。
- **MVP0 目标**：在调用前，显式地对父 `flow` 进行 `copy.deepcopy` 并把累加后的 `subagent_depth` 写入其中，再发送给子图作为状态初始值。

### P1-3 ExitContractRegistry
- **现状**：在 SKILL 阶段的 ReAct 循环里，每轮都会调用 `inject_exit_contract`，并将拼装后的消息同模型响应一起保存回 `BlackboardState.messages`（`graph_assembler.py:243-246`），导致同一契约文字每轮复印堆积。
- **MVP0 目标**：将 `exit_contract` 转变为仅在此次调用发给模型时的“临时贴纸”，使用类似 `ExitContractRegistry` 过滤机制或在存回黑板前将其 strip 掉，避免历史污染。

### A4 轻量 subagent
- **现状**：当前注册 subagent 时，必须是一个具有完整 `GRAPH.md` 和独立 `phases/` 目录的重量级 skill root（由 `_resolve_subagent_root` 在 `loader.py:447-483` 强约束）。
- **MVP0 目标**：允许挂载轻量级的（单文件/纯 Prompt）子代理以降低子任务委派的配置门槛。

### A5 call_subgraph
- **现状**：当前只支持作为静态拓扑的 `SUBGRAPH` node，或由 `compiled.subagents_by_phase` 提前解析注册的 `call_subagent_<name>` 工具。不存在让大模型（LLM）动态决定是否按需调用其它独立大图技能（graph skill）的通用动态工具 `call_subgraph`。
- **MVP0 目标**：提供 `call_subgraph` 工具，让大模型能提供 `child_graph_path` 和 `explicit_inputs` 实现安全的隔离黑板调用。

### ErrorCode 体系
- **现状**：各种校验与执行边界仍使用 `GraphAgentFatalError` 或原生的 `RuntimeError`，错误信息为自由格式文本。
- **MVP0 目标**：标准化代码化，如 `MODEL_NOT_FOUND`、`DEPTH_LIMIT_REACHED`、`INVALID_TOOL_ARGS`，并由 Studio 前端直接解析。

## §3. 各 audit 设计候选

### P0-1 ModelResolver
- **候选 A：Engine 内置 Resolver 解析 `llm_roles.yaml`**
  - **Trade-off**：Engine 库直接读取项目的配置并实例化。解耦了 Studio，但在依赖层需要强绑定不同厂商的模型 SDK，使得 Engine 本身变重。
  - **冲击范围**：`runner.py` 启动入口，新增 `models.py`。
  - **兼容性**：完全兼容。
- **候选 B：依托 Studio 注入 Resolver 回调**
  - **Trade-off**：复用现有的 `apps/studio/backend/app/services/llm_roles.py`，调用 `run_skill()` 时要求外层（Studio 后端）传入解析后的 `ModelResolver` 实例。保持 Engine 轻量。
  - **冲击范围**：`run_skill()` 的入参签名 `[BREAKING]`。
  - **兼容性**：需要在外层调用代码中全面跟进。

### P1-2 child flow subagent_depth
- **候选 A：在 Wrapper 中 `deepcopy` flow 并显式修改**
  - **Trade-off**：非常简单且有效，防止子图对 `flow` 中如重试计数器等控制字段的双向污染。
  - **冲击范围**：`graph_assembler.py` 内部子代理执行处（398-405行）。
- **候选 B：重构 `BlackboardState` 的嵌套模型**
  - **Trade-off**：复杂且无必要，仅仅为了 depth 引入更复杂的树状 state 将适得其反。

### P1-3 ExitContractRegistry
- **候选 A：在模型响应后剥离 (Strip SystemMessage)**
  - **Trade-off**：发送前常规注入，在拿到模型结果准备 `add_messages` 写回 `state` 前，把附带 `exit_contract` 的那条特制 Message 从列表中剔除。
  - **冲击范围**：`graph_assembler.py:243-247` 的 ReAct 主循环内部。
- **候选 B：封装动态代理 LLM Wrapper**
  - **Trade-off**：拦截在 LangChain 执行侧（仅在 payload 构建时混入），彻底使其游离在图的 state 之外。架构更优雅但涉及模型底层的劫持。

### A4 轻量 subagent
- **候选 A：支持以单个 `.md` 文件作为 subagent root**
  - **Trade-off**：判断如果 target path 指向 `.md` 文件，则将其在内存中虚拟编译为一个只包含单 SKILL 节点的 `CompiledSkill`。平滑过度且兼容。
  - **冲击范围**：`loader.py` 的解析分发层，以及 `graph_assembler.py:381`。
- **候选 B：在 frontmatter 新增轻量节点定义字段**
  - **Trade-off**：污染现有的 `manifest.py`，容易让语法变杂。

### A5 call_subgraph
- **候选 A：增加通用工具 `call_subgraph(path, inputs)`**
  - **Trade-off**：直接在 `all_tools` 注入该函数，让 LLM 动态给定图路径和输入。灵活性最高，但若 LLM 幻觉出不存在的路径极易导致执行中断。
  - **冲击范围**：`graph_assembler.py:184-227` 的工具集组装。
- **候选 B：基于静态配置映射的 `call_subgraph_<id>`**
  - **Trade-off**：与 `subagent` 类似，需在 `SKILL.md` 的 `phase_config.subgraphs` 中预先注册，限制大但模型不易犯错。

### ErrorCode 体系
- **候选 A：在现有 Exceptions 中增加 `code` 属性**
  - **Trade-off**：修改 `GraphAgentError` 基类，不改变报错流程但实现了机器可读。
- **候选 B：全部替换为返回 `WorkflowResult(error_code=...)`**
  - **Trade-off**：抛弃 Exception 作为控制流，改为严格的 Result 结构。安全但重构巨大。

## §4. 不依赖 PM 拍板可独立推进的工作清单
1. **P1-2 的 Bug 修复**：纯逻辑遗漏。可直接在 `graph_assembler.py:400` 处引入 `copy.deepcopy` 并写入 `subagent_depth`。
2. **P1-3 的历史净化**：纯逻辑修复。可在 ReAct 写回状态前增加针对临时契约的数组 filter。
3. **ErrorCode 基类改造**：为 `exceptions.py` 中的错误扩展 `code` 及 `metadata` 字典准备承载规范化结构。

## §5. 必须 PM 拍板才能进 task 阶段的清单
- **Q-R-P0-1**: ModelResolver 是由 Engine 内置实现 (候选A) 还是强制要求由调用的外层环境注入 (候选B)？
- **Q-R-A4**: 轻量 subagent 倾向于支持识别单 `.md` 文件 (候选A) 还是改写 Schema 语法？
- **Q-R-A5**: `call_subgraph` 应该做成放任输入任意路径的通用工具 (候选A) 还是需要提前预注册的具体工具 (候选B)？
- **Q-R-ERROR**: ErrorCode 体系更倾向于扩充 Exception 属性 (候选A) 还是全面转为无异常的 Result 结构 (候选B)？

## §6. 跟 Studio LLM routing 的耦合
由于 P0-1 存在没有模型直接挂掉的问题。当前 `apps/studio/backend/app/services/llm_roles.py` 已实现了角色的存取，并且 `llm_provider_test.py` 等文件中存在具体的连接实例化逻辑。
如果选定由 Studio 注入（候选 B），则 `run_skill()` 入口需完全依赖该路由文件构建的闭包函数，Engine 只负责发指令；若选内置（候选 A），Engine 需要自行反向依赖读取项目的 `llm_roles.yaml`。这构成了横跨前后端仓库的强架构耦合。

## §7. 跟 Block 1/2/4 的耦合点
- **跟 Block 1 (skill-compilation)**：A4 的轻量 subagent 如果允许解析单 `.md` 文件，则完全依赖于 `loader.py` 解析模式的更新支持。
- **跟 Block 2 (state-and-io-contract)**：本模块 A5 的 `call_subgraph` 及子代理的深度递归输入环境，将极其强烈的受制于 Block 2 最终决定的是“强沙箱”切分还是隐式透传。如果缺乏沙箱阻断（Block 2 未落实），新注入的工具就无法实现真正的隔离运行。
- **跟 Block 4 (tracing-and-observability)**：新的结构化 ErrorCode （比如 `MODEL_NOT_FOUND`）应当能够直接变成 Trace 系统发出的标准 `EXCEPTION` 事件 payload，以便 Studio 页面展示而无需截取字符串。