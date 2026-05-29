# PR-2 Research: 可观测机制现状与对标分析

## 1. 背景问题与代码现状
在三方审计中，发现最严重的缺失是 V0.3 主路径的运行时监控形同虚设（finding #1）：
- **事件断层 (`core/graph_assembler.py:347-421`)**：新的 `_skill_node` 作为一个 LangGraph 节点，其内部完全依靠 LangChain 的 `model.invoke` 和原生的 Python 工具调用进行大循环。在这一整个循环中，没有调用任何 `graph_agent.callbacks` 定义的事件发射逻辑。导致外部 UI (如 Studio) 和监控模块无从知晓该阶段（Phase）在什么时间开始、输入是什么、调用了什么工具、最后产生了哪些局部修改（输出）。
- **Trace 落盘造假与假绿陷阱 (`core/runner.py:511-517`)**：执行的最后，硬编码返回了 `trace.json` 的伪路径，而事实上 `TracingCallback` 所需的 `save()` 方法从未被触发。由于没有在执行前初始化 `trace_dir`，即使触发了 `save()`，过程中产生的 typed events 也因未绑定流文件路径而全部丢失（没有写入 `tracing.jsonl`）。

## 2. 平行引擎的存在与契约对齐
目前，系统中存在并行的旧引擎执行路径（如 `parallel_map` 可能路由到的 `load_workflow_from_md -> GraphAgentHarness -> LLMPhaseNode` 路径）。
调查 `llm_phase_node.py` 可知，在这条路径下，`on_phase_start` 传入的 `context` 参数是整个数据快照 (`state["data"].model_dump()`)。
**核心对标与结论:** 新引入的 V0.3.0 `_skill_node` 的事件发射机制必须尊重这一历史事实，将 `PhaseStartEvent` 和 `PhaseEndEvent` 的 `context` 对齐为全量 `data`，否则当单一运行（Trace）中混杂着新旧两种 Phase 节点时，将导致 UI 端（Studio）拿到分裂的数据格式并最终崩溃。

## 3. 现有事件体系复用性
调查 `callbacks/base.py` 和 `callbacks/events.py`，发现我们在 PR-E 阶段建立了一套完善的 Pydantic Typed 回调事件模型，它足以支撑此次修复而不需要过度设计：
- 具备基础事件：`PhaseStartEvent`, `PhaseEndEvent`, `ToolCallEvent`, `LLMCallEvent` 等。
- `ToolCallEvent.result` 约定为 `str` 类型，这意味着所有 JSON 形式的返回结果需要转译序列化。
- `LLMCallEvent` 的 Token 定义需要防错处理，以兼容模型方不返回 Token 统计信息的情况。
- 历史遗留的 `_safe_emit_event` 在 `harness.py` 中，需要被抽取至公共模块以避免循环导入风险。

## 4. 结论与方案
在现有的 `_skill_node` 闭包里打下主动断点，利用独立出来的 `emit` helper 发射标准 Pydantic 事件；并在顶层 `runner.py` 严格保证 `TracingCallback` 在执行（`invoke`）**前**被挂载和绑定好目标目录，从而保证流式追踪（JSONL）及最终摘要能诚实地物理落盘。