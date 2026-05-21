# Engine MVP0 — execution-runtime Design

## §0.5 继承字段表

### [NEW] 新增
- `ModelResolver` `[NEW]` — 动态注入工厂，负责将 role 映射为大语言模型。
- `ExitContractRegistry` `[NEW]` — 临时消息管理机制，拦截并净化单轮循环中注入的系统级契约。
- `TraceEventKind` enum `[NEW]` — 标准化事件输出类型（跟 Block 4 共享）。
- `ErrorCode` 体系 `[NEW]` — 将原有的纯文本 Exception 格式化输出为可机器解读的枚举或结构体。
- `call_subgraph` 工具 `[NEW]` — 允许大模型显式调起完整大图的动态工具。
- 轻量 subagent 检测器 `[NEW]` — 判断入参为目录或单文件并适配执行容器。

### [BREAKING] 修改现有
- `run_skill` V2.1 分支: 未传递 `mock_llm` 时，由直接无视改为自动调用 `ModelResolver` 解析 `[BREAKING]` (配合 P0-1 修复)。
- SKILL phase 执行拦截: 无 model 时的原始 `RuntimeError` 变更为标准化结构体 `ModelNotFoundError` 附带 ErrorCode `[BREAKING]`。
- Subagent 调用 `_invoke_subagent_once_t23` 中的 child flow: 由 `parent_flow` 直接透传共享改为使用 `copy.deepcopy` 深拷贝后追加 `subagent_depth+1` `[BREAKING]` (P1-2 修复，阻断双向污染)。
- SKILL phase 中 `messages` 的 `exit_contract` 注入: 循环直接记录并堆积历史改为 `ExitContractRegistry` 在单轮推断后进行清理（Strip）处理 `[BREAKING]` (P1-3 优化提示词配额)。
- Subagent 概念扩展: 由仅接受带有 `GRAPH.md` 的完整根目录改为同时接受单个 `SKILL.md` (转化为 "轻量" 节点) `[BREAKING]` (A4 层级改造)。
- SKILL node tools 组装: 工具栏中不包含大图调用改为追加注入一系列 `call_subgraph_<name>` 的工具族 `[BREAKING]` (A5 新增子图通信能力)。

## §1. P0-1 ModelResolver 设计

### §1.1 候选 A: Studio LLM routing 接入 (apps/studio/backend 现有 llm_*)
- **描述**：直接强依赖外层的 `apps/studio/backend/app/services/llm_roles.py`，要求在启动 `run_skill()` 前，由后端系统实例化 `ModelResolver` 并传参进入运行上下文。
- **Trade-off**：使得 Engine 完全不关心各云服务商的 SDK 封装与凭证配置，极其轻量；但会导致纯 CLI 和无 Studio 环境下的脱壳运行变得非常困难。
- **冲击范围**：`runner.py` 主入口增加依赖入参。

### §1.2 候选 B: graph-agent 自带 ModelResolver, Studio 用其 API
- **描述**：将原本存在于 Studio 后端的 LLM 解析体系下沉至 `graph_agent` 的内部 `models.py`，使之能够直接读取 `llm_roles.yaml`。
- **Trade-off**：提高了 Engine 独立作战和纯粹 CLI 测试的能力，但把厂商 SDK 依赖硬塞到了核心中，增加了包体积。
- **冲击范围**：核心库体积激增，需要重构 Studio 后端依赖关系。

### §1.3 候选 C: 仅 PoC, mock_llm only (短期妥协)
- **描述**：暂时搁置自动模型发现机制，依旧要求上游代码只能手动拼装 LangChain 模型对象传入 `mock_llm` 参数。
- **Trade-off**：无需改动结构，但业务对接极其痛苦。

### §1.4 推荐 + 拍板项
- **推荐**：候选 A。让执行引擎维持干净的图编排功能。
- **PM 拍板 Q-R-P0-1**：ModelResolver 的解析功能应保留在外层 Studio Backend 中由依赖注入传入引擎 (候选A)，还是下沉合并至 graph-agent 作为内置功能 (候选B)？

## §2. P1-2 child flow 修复

### §2.1 候选 A: deep-copy parent_flow + 写 subagent_depth
- **描述**：进入子代理前深拷贝父图的 `flow` 控制流字典，并把累加的层级打入拷贝后的字典内传入 `child_state`。
- **Trade-off**：全面隔离了子节点内部在重试计数等逻辑时修改父级同名键的危险。
- **冲击范围**：`graph_assembler.py:398-405`。

### §2.2 候选 B: 只透传 subagent_depth, 其他 flow 不继承
- **描述**：在开启子图时，清空原本的 `flow`，完全初始化空字典并仅放入 `subagent_depth`。
- **Trade-off**：最极致的隔离，但会丢失可能对子节点有意义的如 trace_id 之类的上下文元数据。

### §2.3 推荐 + 拍板项
- **推荐**：候选 A。它在保证不双向污染的前提下保留了正向的环境特征下放。
- **PM 拍板 Q-R-P1-2**：解决控制流污染与丢失的修复中，是否采用在传递前针对 parent flow 进行 `copy.deepcopy` 并写回深度的策略 (候选A)？

## §3. P1-3 ExitContractRegistry

### §3.1 候选 A: 临时 SystemMessage marker, strip 后写回 messages
- **描述**：在发送给大模型之前常规 Append `exit_contract`。在获得了执行回复准备将消息合入 `state` 前，遍历一轮找出被特殊打上 Marker 的 `SystemMessage` 并剥离。
- **Trade-off**：易于实现，但处理逻辑散布在主控循环外围。

### §3.2 候选 B: 每轮单独构造 prompt_messages = [...messages, exit_contract], 不入 messages
- **描述**：在 `graph_assembler.py` 每次拼装 payload 阶段只临时性组装，不在状态累积层面调用 `add_messages`。将契约文本视作执行期的提示前缀，完全游离于 `BlackboardState` 的状态历史外。
- **Trade-off**：彻底干掉了状态污染，是架构上最优雅的解法。

### §3.3 推荐 + 拍板项
- **推荐**：候选 B。不仅解决了无限堆叠的冗余 Token 消耗，更减轻了 LangGraph state 更新的压力。
- **PM 拍板 Q-R-P1-3**：针对冗余累积的临时契约规则，是否同意完全脱离 `messages` 历史，改为仅在触发大模型调用前临时组合 payload 的形式 (候选B)？

## §4. A4 轻量 subagent

### §4.1 候选 A: 支持 path 指向单 SKILL.md, runtime 包装成虚拟单节点 graph
- **描述**：不改写配置文件的语法，仅在加载阶段检测指向如果非目录而是一个单独文件，则内存虚拟拼装出 `CompiledSkill` 结构进行流转。
- **Trade-off**：不引入新概念，语法向后兼容性极高。

### §4.2 候选 B: 新引入 SubagentSpec.lightweight 字段, 编译期不递归
- **描述**：在 `manifest.py` 内部引入专门的子代理配置节点，走一条不同于子图解析的工作流分支。
- **Trade-off**：模型层级更清晰，但开发变动较大，要求现有配置修改。

### §4.3 推荐 + 拍板项
- **推荐**：候选 A。基于文件格式自动推演能够最大程度减少用户书写 yaml / frontmatter 的心智负担。
- **PM 拍板 Q-R-A4**：轻量级子代理的支持，倾向于基于单一文件识别进行虚拟图包装 (候选A)，还是通过新引入语法字段区分配置模式 (候选B)？

## §5. A5 call_subgraph

### §5.1 候选 A: SKILL node 注入 call_subgraph_<name> tool 族 (跟 call_subagent_<name> 一致)
- **描述**：与 subagent 的提前声明法则一致，只有在 `phase_config.subgraphs` 中预先挂载的图，才会被转换并注入作为大模型可用工具。
- **Trade-off**：大模型不会产生因路径幻觉导致的宕机，极大地增强了安全性和可溯源性。

### §5.2 候选 B: 通用 call_subgraph(path, inputs) 工具
- **描述**：大模型可以通过单一固定工具，提供相对路径及 Explicit Mapping 去调用任意子图。
- **Trade-off**：非常灵活，但存在被模型乱编造不存在的图路径或传错类型进而阻塞工作流的风险。

### §5.3 推荐 + 拍板项
- **推荐**：候选 A。在生产级的流程编排中，预注册约束带来的确定性远大于动态探查带来的灵活性。
- **PM 拍板 Q-R-A5**：新增的大图间相互调起的工具 `call_subgraph`，应当走静态配置安全注入族 (候选A) 还是动态路径通用工具 (候选B)？

## §6. ErrorCode 体系

目前系统大多直接抛出如 `GraphAgentFatalError` 或带有 `[F-v21-*]` 文本的 Exception，为了配合前端和外设消费系统，这些将被梳理并在 `exceptions.py` 内部使用附带标准化字段 `code` 与 `message` 的基类进行分离。

常见的 Code 列举：
- `MODEL_NOT_FOUND`：未能由 `ModelResolver` 解析出真实的可用 Provider 实例 (P0-1)。
- `DEPTH_LIMIT_REACHED`：子代理超过循环限定深度。
- `INVALID_TOOL_ARGS`：大模型生成的工具参数未通过 jsonschema 或类型校验。
- `INPUT_MISSING` / `INPUT_INVALID`：来自于执行入口处未能满足漏斗所需约束。

## §7. 测试策略
- **P0-1 真 LLM e2e 验证**：在配置并提供实际测试用云供应商 Key（例如 Anthropic 的环境变量）时，运行一个包含了 LLM 任务的小图，断言 `run_skill()` 是否成功实例化并获得有效反馈。必须提供真实 Key。
- **P1-2 与 P1-3 逻辑修复**：可以使用纯 Mock LLM 并设定期望响应进行单元测试，断言拦截写入后 `state["flow"]` 字典深度的独立性以及 `state["messages"]` 列表长度不随 ReAct 轮次增加而产生额外扩容。Mock-only。
- **A4 / A5 挂载拦截断言**：编译和注入验证不需要发起真实大模型请求。只需生成 `CompiledStateGraph` 断言其内部存在的 Tools Name 是否成功载入了 `call_subgraph_<X>`。Mock-only。

## §8. 实施顺序
1. **决策前置**：明确向 Studio LLM routing 团队对齐 `ModelResolver` 的职责划分（Q-R-P0-1）。由于 A5（子图调用）直接受制于 Block 2 黑板状态的阻断，必须等 Block 2 方案落地才可实施。
2. **热修复执行**：第一时间实装对于 `messages`（P1-3）以及 `flow.subagent_depth`（P1-2）等内部逻辑漏洞的修复。
3. **引入基建**：增设 `ErrorCode` 体系替代生硬文字。
4. **功能扩充**：最后进行轻量级 Subagent 解析包装和预配置的子图调用能力开发。

## §9. 跟 Block 1/2/4 耦合
- **耦合 Block 1**：轻量子代理 (A4) 对源文件结构的识别重塑依赖 `loader.py`（属 Block 1 范畴）提供的前置解析支撑。
- **耦合 Block 2**：`call_subgraph` 注入后如果缺少强力沙箱 (A3+A6 的 Explicit Input 制约) 则极易变成对全局状态的致命大污染。没有 Block 2 提供护盾，Block 3 不能释放通用调图权。
- **耦合 Block 4**：结构化的 ErrorCode 生成与抛出将会无缝对接到 Block 4 (Tracing) 中的 `EXCEPTION` 和 `NODE_ERROR` 事件 payload 中进行标准化归档。