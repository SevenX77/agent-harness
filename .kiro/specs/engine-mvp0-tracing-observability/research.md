# Engine MVP0 — tracing-and-observability Research

## §1. 现状综述
当前引擎的 `tracing-and-observability` 能力呈现出双轨分离的状态：
- 一方面，V2.1 的主线执行路径 `_run_v21_skill_dict()` 明确执行了 `del callbacks` (`runner.py:462`)，导致原 harness 里的 `TracingCallback` 等能力无法接入 LangGraph 节点生命周期中，主线运行目前处于无日志、无心跳、无阶段记录的“盲飞”状态。
- 另一方面，引擎私有模块内部存在 `PredictTracingCallback` 和 `exporter.py`，能够完成从 phase inputs/outputs 截取到生成 `PhaseRecord` 的业务切片，但它们由于被标明为 `_predict_internal` 而无法被直接用作公开 SDK API 且缺乏对于普通运行主干节点的高细粒度（Token / Tool 层级）捕捉。
整个模块亟待完成对主线的重新接线，并构建异步、不阻塞推理的标准化事件流，以支撑 Studio 进行可视化（瀑布流）。

## §2. MVP0 目标拆分

### P1-4 V2.1 callback 接回
- **现状**：旧有的 harness 可以注册回调并在执行前后触发，但被 V2.1 图调度废弃了。
- **MVP0 目标**：为主线 graph runtime 恢复事件发送能力，建立不依赖旧框架的可持续事件输出。

### V2TracingCallback 新接口
- **现状**：只有内部专用的 `PredictTracingCallback` (`tracing.py:76`)。
- **MVP0 目标**：全新设计 `V2TracingCallback`，全面接入 LangGraph 的 node 生命周期，并作为向事件总线（Event Bus）投递颗粒化事件的转换锚点。

### TraceEventKind 枚举
- **现状**：缺乏标准类型限制。
- **MVP0 目标**：限制发送给系统总线或落盘日志的事件类型（如：`NODE_START`, `NODE_END`, `LLM_CALL_START`, `LLM_CALL_END`, `SUBAGENT_ENTER`, `SUBAGENT_EXIT`, `TOOL_CALL_START`, `TOOL_CALL_END`, `EXCEPTION`）。

### AgentTraceEvent schema
- **现状**：Predict export 只吐出包含了 inputs/outputs/mocked_source 的 `PhaseRecord`。
- **MVP0 目标**：定义更为底层和通用的结构体，包含 `run_id`, `phase_id`, `event_type`, `timestamp_ms`, 及标准化的被脱敏 `payload`。

### 异步 logger
- **现状**：暂无独立的统一落地通道。
- **MVP0 目标**：实现带背压（backpressure）策略的后台日志队列，确保高频事件不会拖慢阻塞模型的 I/O。

### 流式 token + tool call event
- **现状**：仅捕捉聚合的结果。
- **MVP0 目标**：通过 `on_llm_new_token` 暴露出逐字事件（Streaming）接口，并增加 Tool 层级的详细记录方便排障。

### trace 文件轮转
- **现状**：全无轮转管控，会把单个 payload 越撑越大。
- **MVP0 目标**：增加按照体积（如 50MB 阈值）进行历史留档的日志文件轮转策略，防盘爆。

## §3. 各目标设计候选

### P1-4 接回 & V2TracingCallback 接口
- **候选 A：在节点 Wrapper 中显式发事件 (基于 StateMapper)**
  - **Trade-off**：直接在 `graph_assembler.py` 各种 Node 构建包装器（如 LOGIC / SKILL node wrapper）里，读取 `phase_input` 并直接调用 Callback。颗粒度极高且绑定数据准确，但不具备 LangGraph 原生的钩子特性。
  - **冲击范围**：执行装配的核心逻辑。
- **候选 B：注册至 LangGraph 的 Runnable 体系**
  - **Trade-off**：依赖 LangChain 原生回调向下传递，更为框架原教旨主义；但部分私有字典状态需要从流中逆向提取，开发和验证成本高。

### 异步 logger
- **候选 A：Python `Queue` 与后台线程消费写入**
  - **Trade-off**：最标准的方式，利用 `threading.Thread` 进行消费者出队刷盘。可精确控制缓冲阈值，实现平滑写入。
- **候选 B：asyncio 的后台 `create_task` 派发**
  - **Trade-off**：仅限全链路异步场景使用，若系统某处发生了同步阻塞可能会殃及 Task。

### 流式 token 控制
- **候选 A：默认全部投递至事件总线并落盘**
  - **Trade-off**：支持 Studio 完美的打字机效果回放，但在长轮次中占用海量 IO 和空间。
- **候选 B：Token仅推送总线，不记入 trace.json 日志落盘**
  - **Trade-off**：WebSocket 前端消费得到流式效果，但文件体积大幅削减。回放时只能看到区块结果。

### payload 截断与防爆
- **候选 A：复用 Predict Exporter 的 `_sanitize_mapping`**
  - **Trade-off**：代码现成，一旦超界定长度即截断。简单粗暴。
- **候选 B：建立多级引用落盘**
  - **Trade-off**：事件仅保留短描述，长报文写入附属 blob 文件。复杂，MVP0 过于超前。

## §4. 不依赖 PM 拍板可独立推进的工作清单
1. **基础基建定义**：定义 `TraceEventKind` 的 StrEnum 和 `AgentTraceEvent` 的 TypedDict（无破坏性，纯结构）。
2. **异步轮转日志雏形**：在非核心区建立起基于队列与背压轮转的 Logger 机制，可独立开展纯 Python 测试。

## §5. 必须 PM 拍板才能进 task 阶段的清单
- **Q-T-P1-4**: 事件分发入口，是通过改写 Graph node wrappers 显式投递（候选A），还是走 LangGraph 内置 Runnable 回调树（候选B）？ [BREAKING]
- **Q-T-STREAM**: 流式 Token 的处理态度：完全并入全链路存盘（候选A），还是仅提供在线传输拒不写入磁盘以免体积爆炸（候选B）？
- **Q-T-PAYLOAD**: 长 Payload 是强制粗暴截断 `_sanitize_mapping` 模式（候选A）还是保留全景？ [BREAKING]

## §6. 跟 Block 1/2/3 耦合
- **耦合 Block 2 (state-and-io-contract)**：本模块记录 `NODE_START` 与 `NODE_END` 事件，其 Payload 所携带的内容**强烈依赖**于 Block 2 中 `StateMapper` 建立起的 `phase_input` 和 `phase_output` 隔离结果。若是发送原始混写的 `state.data`，Trace JSON 将被海量重复的全局黑板数据撑爆。本 Block 的节点级追踪必须跟在 Block 2 方案落地后才能开工。
- **耦合 Block 3 (execution-runtime)**：本模块中 `EXCEPTION` 类型事件中的承载体应当是 Block 3 定义并在异常边界抛出的结构化 ErrorCode 及其元数据。
- **耦合 Block 1 (skill-compilation)**：所追踪的结构体名称均来自 Block 1 解析出的标准 AST (如子代理和节点 id 名称)。

## §7. 跟 Studio 的接口
- 输出的事件 JSON 流将成为 Studio 前端的唯一数据锚点。
- **Trace 瀑布流**：将按 `timestamp_ms` 时序逐条排列 `TraceEventKind` 事件，组合成单条会话的回放。
- **Canvas Edge Inspection（边探视器）**：将提取 `NODE_END` 的输出 Payload 及下游 `NODE_START` 的输入 Payload，将其做 Diff 对比，以此展现数据在这条连线上的状态变迁，进而完成从后台到前端画布的可视化绑定。