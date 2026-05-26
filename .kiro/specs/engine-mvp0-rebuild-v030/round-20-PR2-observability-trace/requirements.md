# PR-2 Requirements: 可观测事件流恢复与 Trace 落盘

## 1. 目标
修复 V0.3 主路径下节点无观测、Trace 无落盘的重大工程缺陷。确保 Studio 和外部监控能够接收到每个阶段（Phase）真实的输入输出事件（与旧有 Harness 路径保持契约一致），且 Trace 文件能够被正确持久化和寻址。

## 2. 具体要求与验收标准 (Acceptance Criteria)

### 2.1 `_skill_node` 的生命周期事件全覆盖
- [ ] 必须将原 `harness.py` 内的 `_safe_emit_event` 抽取为独立的公共模块（例如 `graph_agent.callbacks.emit`）进行解耦调用。
- [ ] 必须在 `_skill_node` 进入时发出 `PhaseStartEvent`，其 `context` 须提取全量 `state.get("data", {})`（对齐旧 `LLMPhaseNode` 约定）。
- [ ] 必须在 `_skill_node` 所有返回路径（无论是 `finish_task` 提前退出，还是正常循环结束）发出 `PhaseEndEvent`，其 `context` 同样为最终的全量业务数据。
- [ ] 必须在大模型 `model.invoke` 后发出 `LLMCallEvent`。对于没有返回统计信息的情况，容错处理将 `input_tokens` 和 `output_tokens` 赋值为 `0`，不能跳过事件发射；并统一提取字段。
- [ ] 必须在工具（包含普通工具、Framework 工具如 `finish_task` 及 Subagent）成功执行之后，发出 `ToolCallEvent`。若执行结果是字典或列表，需 JSON 序列化成字符串后再放入 `result` 字段。

### 2.2 Trace 文件真实落盘与防假绿
- [ ] `core/runner.py` 中，在发起 `graph.invoke()` 之前，必须计算出有效的目标目录，并确保 `TracingCallback` 完成 `trace_dir` 绑定，防止过程中 typed events 不记录到流文件。
- [ ] 图执行结束后，必须主动调用 `TracingCallback.save()` 使 summary 落地。
- [ ] 返回值必须为真实的 `trace_path`（A类修复，不再返回假路径）。

### 2.3 测试验收 (Tests-First 策略)
- [ ] 必须新增显式使用 **V0.3.0 目录型 GRAPH.md** 夹具的自动化集成测试。
- [ ] **红灯与验证:** 在代码改造前，应当发现通过 V0.3 运行没有任何事件触发及落盘。
- [ ] **实施转绿:** 改造后验证测试可以拦截到完整的 `PhaseStart`, `LLMCall`, `ToolCall`, `PhaseEnd` 序列，并且返回的 `trace_path` 在磁盘上具有确切对应的 `.json` summary 及带内容的 `.jsonl` 追踪流文件。