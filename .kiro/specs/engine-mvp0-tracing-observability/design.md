# Engine MVP0 — tracing-and-observability Design

## §0.5 继承字段表

### [NEW]
- `V2TracingCallback` 接口 `[NEW]` — 全新的针对 V2.1 生命周期的回调实现类。
- `TraceEventKind` enum `[NEW]` — 枚举锁定了 `NODE_START`, `NODE_END`, `LLM_CALL_START`, `LLM_CALL_END`, `SUBAGENT_ENTER`, `SUBAGENT_EXIT`, `TOOL_CALL_START`, `TOOL_CALL_END`, `EXCEPTION`。
- `AgentTraceEvent` TypedDict `[NEW]` — 统一对外吐出的规范化 JSON Schema 结构。
- 异步 logger `[NEW]` — 后台日志消费队列机制（含防阻塞的背压控制）。

### [BREAKING] 
- `run_skill` V2.1 主线初始化: 明确执行 `del callbacks` → 恢复并接入注册 `V2TracingCallback` `[BREAKING]` (P1-4 修复)。
- LOGIC / SUBGRAPH / SKILL node wrapper (在 `graph_assembler.py` 内): 执行前后不发事件 → 全部追加 `NODE_START` 和 `NODE_END` 调用 `[BREAKING]`。
- Subagent runtime: 无外围层级捕获事件 → 追加发送 `SUBAGENT_ENTER` 和 `SUBAGENT_EXIT` 报告递归嵌套边界 `[BREAKING]`。
- Tool 调用层: 针对 Langchain 工具调用不透传细节事件 → 强制发 `TOOL_CALL_START` 和 `TOOL_CALL_END` (附加 `tool_name` 和脱敏 payload) `[BREAKING]`。
- Exception 捕获机制: 抛出原生异常及堆栈阻断执行 → 被拦截并映射至 ErrorCode，发 `EXCEPTION` 标准事件后再中止 `[BREAKING]` (与 Block 3 ErrorCode 接轨)。

## §1. V2TracingCallback 接口设计

### §1.1 候选 A: 完全独立, 不继承 Predict
- **描述**：重头新写一个纯粹响应 `on_node_start` 等一系列显式函数调用的普通单例类对象。通过拦截器手动在代码核心缝隙进行插桩。
- **Trade-off**：摆脱了 Langchain 框架回调复杂的回传绑定。但所有图执行内部都必须硬编码导入和触发。

### §1.2 候选 B: 继承 BaseCallbackHandler (langchain) + 扩展
- **描述**：通过 LangChain/LangGraph 标准的 `BaseCallbackHandler` 实现。
- **Trade-off**：高度融入框架理念，但难以精准捕捉业务含义上的“沙箱变量”与“子代理隔离深度”，需要靠反向嗅探状态实现。

### §1.3 候选 C: 抽 BaseV2Callback 父类, V2TracingCallback / PredictTracingCallback 继承
- **描述**：将私有模块 `_predict_internal` 里的可贵特性（如 `_sanitize_mapping` 脱敏）和统一生命周期抽取为 `BaseV2Callback` 父类，作为 V2.1 的通用底座。
- **Trade-off**：不仅解决公开调用的缺失问题，同时使得预测/覆盖模式（Predict）与常规主路执行可以共享代码体系，架构最佳。

### §1.4 推荐 + 拍板项
- **推荐**：候选 C。统一内外日志体系底座是成熟工程的表现。
- **PM 拍板 Q-T-1**：新事件入口 `V2TracingCallback`，是应脱离框架纯手工插桩（候选 A）、强依赖 LangChain Handler（候选 B），还是采用提取抽象基类整合目前孤立的 Predict 特性（候选 C）？

## §2. TraceEventKind 枚举
建议锁定以下 9 枚不可变的业务事件：
- `NODE_START` / `NODE_END`
- `LLM_CALL_START` / `LLM_CALL_END`
- `TOOL_CALL_START` / `TOOL_CALL_END`
- `SUBAGENT_ENTER` / `SUBAGENT_EXIT`
- `EXCEPTION`

关于更细的 Edge-Transfer (边沿数据转化) 和 Token-Level (流式单字)。在 MVP0 阶段，流式单字被列为可选项（可被 UI 消费但不进入长期轮转以节约 IO）；而 Edge 的传递数据能够被 `NODE_END` 与紧接其后的 `NODE_START` 对冲得出，暂时无需强造 `EDGE_TRANSFER` 事件以维持最简集合。

## §3. AgentTraceEvent payload 规范
每次吐出给前端的总线对象格式应强约定，Payload 内需脱敏超长文本并符合下列场景：
- **`NODE_START`**: `payload = phase_input` (严格来自 Block 2 StateMapper 的沙箱切片)。
- **`NODE_END`**: `payload = phase_output` (本次节点实际产生的数据增量)。
- **`LLM_CALL_START`**: `payload = {"prompt": [{"role": "system", ...}, ...]}`。
- **`LLM_CALL_END`**: `payload = {"response": "...", "usage": {"tokens": ...}}`。
- **`EXCEPTION`**: `payload = {"error_code": "MODEL_NOT_FOUND", "message": "...", "traceback": "..."}`。

## §4. 异步 logger
- **队列推送**：当 Callback 拦截到事件后，通过内置的 `queue.Queue` 进行生产投递，不阻塞 `graph.invoke`。
- **后台异步刷盘**：开启 `threading.Thread` 或 `asyncio` task 定期批量从队列取出写入文件。
- **背压 (Backpressure) 策略**：如果队列满载警告，丢弃高频的低价值 `ON_NEW_TOKEN` 类更新事件，保证关键 `EXCEPTION` / `NODE_END` 进入存盘队列。

## §5. trace 文件轮转 + 持久化
建立基于 `trace.jsonl` 的滚动记录文件：
- 以 JSON Line 的形式逐行追加单个独立事件，利于前端流式边下边播。
- 追加硬阈值：一旦 `trace.jsonl` 单个文件超过 50MB（或者设定值），便触发 Rotate 操作（重命名并压缩为 `trace.2026xxxx.jsonl.gz`）。该控制可确保长期运行的 Daemon 不会爆掉机器的存储。

## §6. 流式 token + tool call (扩展)
- **Token**：暴露特定的 `on_llm_new_token`。但默认处于关闭存储文件或降级存活状态。前端 WebSocket 依然可以拿到它来产生逐字显示，但绝不直接记录入上述的轮转文件以免污染高权重的事件流。
- **Tool Call**：由于工具可能去外网发请求爬数据或执行 Python，其重要度高于普通推断，应享受等同于 LLM Call 相同的首屏录入待遇，并在错误时作为独立的 Trace 展示块。

## §7. 测试策略
- **生命周期打点测试**：在没有任何真实大模型的情况下（Mock-only），装配带有一系列节点逻辑的 `CompiledStateGraph`。将拦截队列对准 `list` 并断言其产生的数组长度和 `TraceEventKind` 类型序列一致（例如 Start-Call-End-End 一条龙）。
- **截断与防爆测试**：对 `AgentTraceEvent` 的 Payload 强制喂入超过 50MB 长度的模拟文本或超深 JSON 层级，断言 `_sanitize_mapping` 能不能按照期望输出为 `[truncated]`。
- **背压拦截测试**：强行向异步 logger 丢入超限堆栈，核验是否有序截留次要 Token。

## §8. 实施顺序
1. **依赖前置**：本方案极大程度受限于 Block 2 与 Block 3。因此必须先向 PM 确立那两项（特别是 Block 2 中的强沙箱环境）已获拍板且实施。
2. 开发基建并引入 `TraceEventKind` 与对应的 `AgentTraceEvent` Types。
3. 创建带队列缓冲的 `V2TracingCallback` 和 logger 机制。
4. **关键阶段**：对 Block 2 中完成的 StateMapper Phase Wrapper 进行再包转，在启动前后把截取的片段发射出相应的 `START`/`END` Payload 队列。

## §9. 跟 Block 1/2/3 + Studio 耦合
- **耦合 Block 1**：节点名及各类子任务（Subagent）名称、拓扑信息均是由 Block 1 的静态解析作为依据传递到追踪记录上。
- **耦合 Block 2 (最高权重)**：若 Block 2 `StateMapper` 不存在，这里的 `NODE_START` 及 `NODE_END` 所获得的 payload 会包含不属于该节点的极其冗余的全局 `state.data`。这将使记录的数据丧失切片价值，并导致产生巨量垃圾日志。
- **耦合 Block 3**：Block 3 定义好的所有 `ErrorCode` 枚举值及其附带文本应当被原样封存进入 `EXCEPTION` 的事件 Payload 中。
- **耦合 Studio (外部)**：Studio 的前端面板与 Canvas 将按本文预置的 `AgentTraceEvent` 模型对事件进行接管消费。任何对本章 Payload 的命名重构，都将直接导致 Studio 的可视化连线及瀑布流断裂。