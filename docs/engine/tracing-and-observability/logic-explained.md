# tracing-and-observability 人话功能逻辑解释

tracing-and-observability 负责把一次 run_skill 从黑盒变成可回放过程。它不决定图怎么跑，也不决定模型怎么选；它只负责忠实记录：哪个 phase 开始了，拿到了什么输入，LLM 看到了什么，调了哪个工具，子 agent 什么时候进入和退出，最后哪里成功或失败。

最贴切的比喻是飞行记录仪。飞机正常飞行时，乘客不需要看飞行记录仪；一旦延误、告警、事故或复盘，所有人都要靠它知道每个时刻发生了什么。trace 对 engine 也是一样。平时它服务 Studio 的运行面板；出错时，它是判断问题属于 compile、state、runtime、LLM routing 还是工具的依据。

trace 不是随手写日志。日志可以是“summarize done”这种句子；trace 必须是结构化事件。每条事件至少要有 run id、phase id、event type、时间、payload。这样 Studio 才能把事件贴回 Canvas 节点、Trace 瀑布流、Edge Inspection 和错误面板。

V0.3.0 的核心 trace event 有七类。

`NODE_START` 表示某个 phase 开始执行。它应该在 runtime 调用 phase wrapper 前触发，payload 里放这个 phase 真正拿到的 `phase_input`。比如 `summarize` 开始时，只拿到 `{clean_text, locale}`，trace 就记录这两个字段，而不是整张黑板。这样 PM 能确认：这个 phase 没有偷看到 `debug_token` 或其他无关字段。

`NODE_END` 表示某个 phase 成功结束。它应该在 phase 返回输出后触发，payload 里放该 phase 的输出摘要或完整可控输出。比如 `summarize` 结束后产出 `summary` 和 `bullet_points`，事件记录这些字段被写入 `phase_outputs["summarize"]`。下游如果读不到，就能查是 NODE_END 没产出，还是 StateMapper 没传过去。

`LLM_CALL_START` 表示即将调用模型。它发生在 SKILL phase 的 ReAct loop 里，模型真正 `invoke` 之前。payload 应该包含 role、phase id、prompt messages 摘要、绑定了哪些 tools、这轮是第几轮。比如 `extract_points` 第 2 轮调用模型前，trace 能看到它带着上轮 tool result 继续推理。

`LLM_CALL_END` 表示模型返回了结果。它发生在模型调用成功之后。payload 应该包含模型文本、tool calls、provider/model metadata、token usage 摘要和是否经过 fallback。比如 provider A 503 后 Gateway 切到 provider B 并成功，LLM_CALL_END 可以显示最终使用的是 provider B，但这不等于 phase 失败。

`SUBAGENT_ENTER` 表示进入 subagent 或子任务边界。比如父 SKILL phase 调用了 `call_subagent_claim_checker`，runtime 在调用子 agent 前发这个事件。payload 应该包含具体 tool name、validated args、parent phase、child run context、subagent_depth。它回答“是谁叫了哪个助手，带了哪些材料进去”。

`SUBAGENT_EXIT` 表示子任务结束返回。比如 `claim_checker` 返回 `{verdict: "supported", citations: [...]}`，事件记录这个结果摘要以及耗时。它回答“助手交回了什么”。如果子 agent 内部还有自己的 phase trace，Studio 可以把它折叠在这个 enter/exit 区间里。

`EXCEPTION` 表示运行发生真正阻断。它不应该被滥用。单个 LLM provider 失败但 fallback 成功，不是 EXCEPTION；工具参数第一次校验失败但 LLM 获得反馈后修正，也不一定是 EXCEPTION。只有 phase 无法继续、所有 fallback 用尽、contract 违规、subagent 深度超限、action 抛不可恢复错误时，才发 EXCEPTION。payload 应带 `F-v0.3-*` 错误码、phase id、message 和可安全展示的上下文。

除了七类核心事件，V0.3.0 还需要两类工具事件：`TOOL_CALL_START` 和 `TOOL_CALL_END`。SKILL phase 的 ReAct 调试离不开它们，因为 LLM 的工作不是只“说话”，还会“按按钮”。如果 trace 只记录模型文本，不记录工具调用，就像只录了电话的一边。

`TOOL_CALL_START` 在工具执行前触发。payload 里要有 `tool_name`、validated args、tool_call_id 和 phase id。Q13 决策后，subagent / subgraph 工具是 per-tool 命名，比如 `call_subagent_claim_checker`、`call_subgraph_quality_review`，所以 payload 里的 `tool_name` 应该就是这些具体名字，而不是统一的 `call_subagent` 再把名字藏在 args 里。

`TOOL_CALL_END` 在工具返回后触发。payload 里要有 success、result summary、耗时、可选 error code。比如 `call_subagent_claim_checker` 返回三条 citation，trace 不一定要保存完整长文本，但要记录它成功了、返回了 `verdict` 和 citations 数量。若工具失败，要记录失败类型，而不是只让 LLM 看到一段字符串。

Predict 模式和真实 LLM 模式的 trace 必须区分。真实模式里，LLM_CALL_END 代表真的调用了 provider，usage 和 provider metadata 有成本意义。Predict 模式里，输出可能来自 `golden_case`、`copilot`、`heuristic_stub` 或 `manual`。因此 Predict trace 必须标 `mocked_source`，让 PM 知道这段输出是回放、智能补全、规则 stub，还是人工填入。

举例：Studio 里用户点 Predict 预览一张图。`extract_points` 的输出来自 golden case，`write_summary` 的输出来自 heuristic stub。Trace 面板应该明确显示 mocked_source。否则 PM 可能误以为模型真的跑了一遍，并错误评估成本、质量和耗时。

Studio 消费 trace 主要有四种方式。

第一，Canvas 节点状态。收到 `NODE_START`，节点进入 running；收到 `NODE_END`，节点变成功；收到 `EXCEPTION`，节点标红。如果 EXCEPTION 带 phase id 和错误码，Canvas 可以精确标红出错节点，而不是只显示整张图失败。

第二，Trace 面板瀑布流。用户可以按时间看到：`clean` 开始、`clean` 结束、`extract` 开始、LLM 第 1 轮、工具调用、LLM 第 2 轮、finish_task、`extract` 结束。这比一段最终错误清楚得多，因为它显示过程和因果。

第三，Edge Inspection。用户点 `clean -> extract` 这条边，Studio 可以展示 `clean` 的 NODE_END 输出里有哪些字段，以及 `extract` 的 NODE_START 输入里实际拿到了哪些字段。比如 `clean_text` 传过去了，但 `language` 没传过去，就能判断是 StateMapper 映射问题还是 phase IO 声明问题。

第四，成本和质量复盘。真实 LLM trace 可以聚合 token、provider、耗时、fallback 次数；Predict trace 可以聚合 mocked_source，告诉 PM 哪些结果是人工或 stub，不应该当成真实质量评估。

异步 logger 是必须的，因为写盘不能阻塞 LLM 推理。一次 SKILL phase 可能在几秒内产生多轮 LLM、多个工具、多个子 agent 事件。如果每个事件都同步写文件，模型调用会被磁盘 I/O 拖慢。正确做法是 runtime 把事件放进队列，后台 logger 批量写盘，同时高优先级事件如 EXCEPTION 不能丢。

异步 logger 还要有 backpressure。事件太多时，可以合并低价值、高频的 token 事件，但不能丢 NODE_END 或 EXCEPTION。比如流式输出每个 token 都进队列，队列满了可以只保留聚合文本；但 phase 失败事件必须写出来，否则 trace 就失去审计价值。

payload size guard 是防止 trace 文件变成垃圾场。prompt、response、tool result、artifact 摘要都可能很大。默认 trace 应截断大字符串，保留原始长度、截断标记和摘要。需要完整 payload 时，应该有显式 debug 开关。否则一次长文档分析就可能把 trace 写成几百 MB。

file rotate 是防止长期运行把磁盘写爆。trace 文件超过阈值后应该轮转，旧文件带时间戳归档，新事件写入新文件。轮转失败不应该中断业务运行；最多记录 logger warning，并继续通过内存 callback 或 WebSocket 发送事件。

敏感信息也要过滤。Trace 不应该默认保存 API key、Authorization header、完整 provider request、用户 secret。对于外部工具调用，可以保存 host、status code、耗时和截断后的 body 摘要；不要保存敏感 header 和完整响应体。trace 是调试资料，不应该变成秘密泄漏面。

最终心智模型：tracing-and-observability 是 V0.3.0 engine 的运行回放系统。它用有限、稳定、结构化的事件，把图执行、LLM 调用、工具调用、subagent 边界和异常都记录下来。Studio 用它标节点、画瀑布流、看边上传了什么；开发者用它定位问题；PM 用它理解一次运行到底发生了什么。

