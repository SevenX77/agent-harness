# tracing-and-observability (engine) — MVP0 Alignment (V0.3.0 目标对齐逻辑)

> **Status**: Filled by a1 (Codex) based on a2 framework, 2026-05-20; Q9/Q13 + 死代码清退 + V0.3.0 版本号 升级 2026-05-21
> **Scope**: Predict 内部与 LangGraph 节点拦截、生命周期事件发出、结构化 Trace 日志 (audit P1-4)
> **改造目标 engine 版本**: V0.3.0 (MVP0 落地后, 详见 [INDEX.md#engine-版本号约定-2026-05-21-pm-拍定](../../INDEX.md#engine-版本号约定-2026-05-21-pm-拍定))
> **配套**: 见 [INDEX.md](../../INDEX.md) 三时态模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

Tracing 是“把运行过程拍成可回放记录”的 engine 能力。它不画瀑布流、不画 Edge Inspection，但它必须提供 Studio 能消费的数据。当前 V2.1 runner 返回一个 `trace_path` 字符串，见 `packages/graph-agent/src/graph_agent/core/runner.py:480` 到 `packages/graph-agent/src/graph_agent/core/runner.py:485`，但这条主线没有真正写出 phase 级 trace。

MVP0 的 UI 价值是让前端可以回答三个问题：哪个 phase 开始了、它看到了哪些输入、它输出了什么或在哪里失败。没有这些事件，Studio 只能展示最终结果，不能展示过程。

PM 可以把本模块理解为“黑盒飞行记录仪”。它不会决定飞机怎么飞，那是 execution-runtime 的职责；它只保证每个关键动作都留下时间、身份、输入、输出和错误。当前 Predict 路径已经能保存一部分业务切片，但 V2.1 主执行路径仍缺统一事件。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

前端将来只订阅事件流或读取 trace 文件。它不应该知道 `GraphAssembler` 怎么调用 `model.invoke()`，也不应该直接调用 `PredictTracingCallback`。当前 Predict 内部已有 callback/exporter，但 V2.1 graph runtime 的 LOGIC/SUBGRAPH/SKILL node 没有统一发事件：LOGIC 主体在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136`，SUBGRAPH 主体在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:172`，SKILL 主体在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:229` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:296`。

这也意味着前端的 TracePanel 不应该自己推断 phase 生命周期。它应该消费 engine 事件：`NODE_START` 出现就新增一行，`LLM_CALL_END` 出现就补 prompt/response，`EXCEPTION` 出现就把当前 phase 标红。事件协议稳定后，Studio 的 WebSocket 和本地 trace 文件可以复用同一种 payload。

## 后端功能

### 1. V2.1 Runtime Callback 与 Trace 事件分发体系恢复 (P1-4 修复)

MVP0 SHOULD 把 callbacks/trace 接回 V2.1 主线。当前 `_run_v21_skill_dict()` 直接 `del callbacks`，见 `packages/graph-agent/src/graph_agent/core/runner.py:451` 到 `packages/graph-agent/src/graph_agent/core/runner.py:462`，随后只执行 `compile_skill -> assemble_graph -> graph.invoke`，见 `packages/graph-agent/src/graph_agent/core/runner.py:463` 到 `packages/graph-agent/src/graph_agent/core/runner.py:471`。这就是 P1-4：旧 harness 的 callbacks / trace / heartbeat 等能力没有进入 V2.1 graph runtime。

现有可复用基础是 Predict tracing。`PredictTracingCallback` 定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76`，支持 chain start、phase start/end、LLM call 和 save；phase start 保存 inputs，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:111` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:116`；phase end 保存 outputs、metrics 和 mocked source，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:118` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:137`；LLM call 清零 usage 后写入，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:139` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:157`。

MVP0 WILL 设计 V2TracingCallback，不直接把 `_predict_internal` 私有模块变成 public API。文件头已经说明 Predict tracing 是 private internal，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:1` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:6`。V2TracingCallback 应接入 LangGraph node lifecycle：NODE_START 记录 phase_input，NODE_END 记录 phase output，LLM_CALL_START/END 记录 prompt 与 response，SUBAGENT_ENTER/EXIT 记录嵌套边界，EXCEPTION 记录错误。

接入点 SHOULD 尽量靠近节点 wrapper，而不是只包住 `graph.invoke()`。只包顶层只能知道“图开始/结束”，不知道哪个 phase 出错。LOGIC 的 action 调用点在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:131`，SUBGRAPH 的 child graph invoke 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:157` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:164`，SKILL 的模型调用点在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:245`。这些位置都应发细粒度事件。

P1-4 还要求恢复旧 harness 的“运行健康”语义。旧路径会创建 `LoggingCallback()` 和 `TracingCallback(trace_dir=...)`，见 `packages/graph-agent/src/graph_agent/core/runner.py:284` 到 `packages/graph-agent/src/graph_agent/core/runner.py:286`。MVP0 不必照搬旧 harness，但必须让 V2.1 主线具备等价的 phase trace、错误 trace 和可持续事件输出。

### 2. 异步日志记录器构建

MVP0 SHOULD 避免 trace 写盘阻塞模型推理。LLM 调用和工具调用可能产生大量事件，如果每个事件都同步写 `trace.jsonl`，运行性能会被 I/O 拖慢。异步记录器可以理解成“一个后台队列”：runtime 只把结构化事件丢进队列，后台线程或 async task 批量写盘。

现有 Predict exporter 已经有清洗字段的经验。`assemble_phase_record()` 会把 raw phase 转成 `PhaseRecord`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:24` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:38`；`_sanitize_mapping()` 会过滤 usage/cost 并截断长字段，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:74` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:108`。MVP0 的异步 logger SHOULD 复用这些“不要无限写大 payload”的原则。

异步 logger 还 SHOULD 支持 backpressure。比如后台队列超过阈值时，低价值 token 事件可以合并，高价值 EXCEPTION/NODE_END 事件不能丢。这样即使模型流式输出很快，也不会因为 trace 太慢把整个 run 卡住。

## API

以下为事件类型及回调处理入口的全新 Python 接口契约提议，它们属于 `graph_agent` 的核心观测模块，是对外吐出数据的唯一标准：

### 1. Trace Event 类别枚举规范
为了彻底梳理和统一发送向 Studio 总线或磁盘日志的种类，我们必须锁定并强约束有限种类的事件枚举。不能再让开发者随意派发乱七八糟的纯字符串事件。

```python
from enum import StrEnum

class TraceEventKind(StrEnum):
    """Enumeration of all system-emitted trace events.
    
    This strict enumeration ensures that both backend dispatchers
    and frontend consumers follow the exact same event taxonomy
    to avoid parsing failures down the line.
    """
    NODE_START = "node_start"
    NODE_END = "node_end"
    LLM_CALL_START = "llm_call_start"
    LLM_CALL_END = "llm_call_end"
    SUBAGENT_ENTER = "subagent_enter"
    SUBAGENT_EXIT = "subagent_exit"
    EXCEPTION = "exception"
```

MVP0 SHOULD 保持枚举小而稳定。Predict 侧目前把 mocked source 限定为 `"golden_case" | "copilot" | "heuristic_stub" | "manual"`，类型在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:18`，exporter 同样有集合约束，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:21`。Trace event kind 也应采用这种有限集合。

如果未来要支持更多事件，SHOULD 用 additive 扩展，不重命名已发布枚举。Studio 和 CLI 都会按字符串解析事件类型，一旦重命名，历史 trace 文件就会失效。

### 2. TracingCallback V2 接口定义
接棒老版本的失效回调体系，全新的 Callback Interface 应当契合当前对 LangGraph 环境下的拦截参数提取要求。具体代码可能落定于重构的 `runner.py` 装载点附近，或通过事件调度器注入。

```python
from typing import Any

class V2TracingCallback:
    """Core interface for observing V2.1 skill execution lifecycle.
    
    Plugs into LangGraph dispatch mechanisms to surface granular
    events out of the execution black box and feed them to the Event Bus.
    """
    
    def on_node_start(self, run_id: str, phase_id: str, inputs: dict[str, Any]) -> None:
        """Emitted when a phase graph node evaluation kicks off.
        
        Args:
            run_id: Global tracking identifier for the skill execution.
            phase_id: Target phase identifier.
            inputs: Sandboxed `phase_input` presented to this specific node.
        """
        pass
        
    def on_llm_call(self, run_id: str, phase_id: str, prompt: list[Any], response: Any) -> None:
        """Emitted covering the complete roundtrip of a model invoke.
        
        This will wrap the serialized array of LangChain messages alongside
        whatever JSON response was successfully decoded back from the vendor.
        """
        pass
        
    def on_node_end(self, run_id: str, phase_id: str, result: dict[str, Any]) -> None:
        """Emitted when node successfully or erroneously exits execution.
        
        Provides the output state difference generated by this exact stage.
        """
        pass
```

MVP0 SHOULD 把这个 callback 放到 runtime 可传入的 config 中。当前 subagent config 已经能透传 callbacks，如果 parent config 里有 callbacks，它会写进 child config，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:497` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:505`。问题是 public V2.1 runner 顶层没有传入 callbacks。

`on_llm_call` 的签名目前把 prompt 和 response 放在同一个方法里，适合非流式调用。MVP0 实现时可以内部拆成 start/end 两个事件，但保持此 high-level method 作为兼容 facade。这样调用者可以简单接一个 callback，同时事件总线仍能输出 `LLM_CALL_START` 和 `LLM_CALL_END`。

## Data Model / State

### 1. AgentTraceEvent JSON Schema 对接标准契约
不管是吐向磁盘存储日志文件，还是走内存 Event Bus 交给后端外壳，承载以上 Event 的根本外壳包体必须具有固定的 `TypedDict` 模型。这份 `AgentTraceEvent` 的严格 Schema 最终将交付给前端用于实现结构的序列化渲染解析：

```python
from typing import Any, TypedDict
from .events import TraceEventKind

class AgentTraceEvent(TypedDict):
    """The canonical shape of an emitted trace log."""
    run_id: str
    phase_id: str
    event_type: TraceEventKind
    timestamp_ms: int
    payload: dict[str, Any]
```

`payload` SHOULD 随 event type 保持可预测结构。`NODE_START` 放 `phase_input`，`NODE_END` 放 phase output delta，`LLM_CALL_START` 放 prompt messages，`LLM_CALL_END` 放 response 和 tool calls，`EXCEPTION` 放 error code、message、stack。Predict exporter 目前只输出 phase_name/type/inputs/outputs/mocked_source，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:31` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:38`；MVP0 的 AgentTraceEvent 会比 Predict business slice 更底层、更完整。

`timestamp_ms` SHOULD 使用单调时间或统一 UTC wall time 的明确策略。面向 UI 排序时，单调时间更稳；面向日志审计时，UTC 时间更直观。MVP0 可以同时保存 `timestamp_ms` 和 `iso_time`，但必须指定哪个字段用于排序。

payload 还需要 size guard。Predict exporter 当前会截断长字符串并写 `truncated` 标记，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:92` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:108`。V2 event payload SHOULD 采用同样策略，避免 prompt 或工具结果把单条事件撑到数 MB。

## Cross-feature Interaction

本观测特性的平稳运行，重度依赖于大量其他引擎底层特征的动作捕捉与配合支持：

- **提供源头用于 Studio Trace-Visualization 体系**:
  上述 `AgentTraceEvent` 及 `TraceEventKind` 是和 Studio 前端直接达成的 JSON 数据协议对接契约。这批发送往事件流通道的序列构成了完全透明可靠的日志数据本源。前端对 Trace 瀑布流的呈现，甚至连线之间的 Edge 节点探视面板所依托的数据，均需完全依赖本文件提出的格式源泉。其双向关联细节详见 [Studio trace-visualization 的接收渲染规划](../../studio/feature-folders/trace-visualization/mvp0-alignment.md)。
  
- **与 BlackBoardState 的状态切片提取联动**:
  在每次 `NODE_START` 等关键生命周期事件触发时，提取出并发放的 `inputs` / `outputs` 数据片段，正是基于在执行前被严格拦截并拆散的黑板数据——即基于 [state-and-io-contract 模块彻底沙盒隔离划分下的纯净状态](../state-and-io-contract/mvp0-alignment.md#Data-Model-/-State)。

- **与 execution-runtime 的调用点绑定**:
  Tracing 不应独立模拟运行过程。它必须由 runtime 在真实执行点发出事件。P0-1 的 ModelResolver、P1-3 的 ExitContractRegistry、A5 的 call_subgraph 都会新增关键调用点，观测模块需要为这些调用点提供统一事件命名。

### 3. `TraceEventKind` 与可观测性生命周期的完整映射
在上述提到的事件分类中，每一次投递都对应图流转的一个真实物理阶段。
- `NODE_START`：发生在 LangGraph 调用节点包装器前。MVP0 应在此记录 phase_input。
- `NODE_END`：发生在节点返回 state delta 后。LOGIC 当前返回 `{"data": updates}`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:132` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136`。
- `LLM_CALL_START`：紧贴 `model.invoke(prompt_messages)` 前，当前调用点在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:243` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:245`。
- `EXCEPTION`：发生在 runtime 捕获错误时，应绑定 [execution-runtime 的异常分发与状态码体系](../execution-runtime/mvp0-alignment.md#9-异常分发与状态码体系)。

这张映射表也是测试清单。每个事件类型都应该有至少一个 fixture 证明它会在正确位置发出，并且 payload 不包含未授权的全局黑板字段。

### 4. 高效日志文件的轮转与清理
虽然引擎不应过多干预外部日志系统的管理，但对于输出到默认目录 `trace.jsonl` 的行为，为了防止无休止的文件膨胀导致磁盘耗尽：
- 我们将在每次 `run_skill` 触发新流时，检查目标日志文件的大小。
- 若超过预设阈值（例如 50MB），自动执行文件的 rotate 行为（加上时间戳后缀），保障最新的追踪数据总是落在最易访问的文件头部。

轮转策略 SHOULD 不影响实时事件总线。写文件失败时，runtime 可以继续向 callbacks/WebSocket 发事件，并记录 logger warning；它不应该因为 trace 文件不可写而中断业务执行。这与 compilation cache 的 P2-2 降级原则一致。

### 5. 面向 Studio 的数据反补
Studio 需要按 `phase_id` 把 trace event 贴回 Canvas 节点和 Trace 列表。`AgentTraceEvent.phase_id` 因此是必须字段，不是可选装饰。当前 `CompiledStateGraph` 已经保存 `phase_ids` 和 edges，构造见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:91` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:96`，MVP0 trace 应沿用这些 phase id。

Edge Inspection 还需要 edge 级数据。MVP0 可以先从 NODE_END 的 output 和下游 NODE_START 的 input 推导“这条边传了哪些字段”；长期则可在 StateMapper 里直接发出 edge transfer event。这个设计依赖 [state-and-io-contract 的 Phase Wrapper](../state-and-io-contract/mvp0-alignment.md#6-phase-wrapper-的上下文准备过程)。

### 6. 模型流式响应的集成展望
目前的 `LLM_CALL_END` 主要是为了捕获同步请求（Sync Call）或非流式的完整回应。但是在前端界面，PM 和开发者往往希望能看到逐字输出（Streaming）的效果。
MVP0 观测体系的预留：
- `V2TracingCallback` 将引入一对新的辅助方法：`on_llm_new_token(token: str)`。
- 这要求在底层使用 `chat_model.stream()` 的情况也能被完整覆盖。虽然最终组装好的响应会通过 `LLM_CALL_END` 统一发射，但中间过程的 Token 也能利用这个观测窗口喂给 Web Socket。

流式 token 事件应该被视作高频低价值事件。MVP0 SHOULD 允许关闭 token 级 trace，只保留最终聚合文本，以便批量测试和 CI 不产生海量日志。

### 7. 对外部网络及工具的专项抓取
图中的节点不仅仅是调用模型，它们还会频繁使用 Tools。当前 SKILL node 对普通工具直接 `tool.invoke(call_args)`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:266` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:267`；subagent tool 则走 `_invoke_subagent_tool_t21()`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:256` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:265`。

MVP0 SHOULD 扩容 `TraceEventKind`，加入 `TOOL_CALL_START` 和 `TOOL_CALL_END`，payload 带 `tool_name`、validated args、result summary 和 error。这样 ReAct 调试不只看到”模型说了什么”，也能看到”工具实际做了什么”。

**Q13 决策协同 — `tool_name` 是 per-subagent/subgraph**: 按 Q13 PM 拍定 (详见 [execution-runtime/mvp0-alignment.md#5-call_subgraph-大流程动态工具暴露-a5-改造-q13-决策落地](../execution-runtime/mvp0-alignment.md#5-call_subgraph-大流程动态工具暴露-a5-改造-q13-决策落地)), engine 不暴露统一 `call_subagent(name=..., args=...)` 入口, 而是每个登记的 subagent / subgraph 编译为独立原生 tool `call_subagent_<name>` / `call_subgraph_<name>`。所以 `TOOL_CALL_START.payload.tool_name` SHOULD 直接是这些具体 tool 名 (例: `”call_subagent_beat_extractor”`), Studio Trace 面板可以按 tool name 聚合调用统计, 不需要再额外解析 args 里的 `name=...` 字段。

**Q9 决策协同 — `EXCEPTION` 事件的 fallback 语义**: 按 Q9 决策, LLM 调用失败时 fallback 责任完全在 `GatewayChatModel._generate` 内消化 (`packages/graph-agent/src/graph_agent/models/gateway_chat_model.py` 内部 with_fallbacks 思路)。engine 只看到一次 `chat_model.invoke()` 调用 — 要么成功 (即便底层换了 provider 也是透明的), 要么所有 provider 全 fail 抛出 `ModelResolutionError`。所以 `EXCEPTION` 事件**只在所有 fallback 都用尽之后**才发出, 单 provider fail 重试**不**触发 `EXCEPTION`。如果 Studio 后续要展示”哪个 provider 被试过 / 何时降级”, 那是 `GatewayChatModel` 内部 metric 暴露的事 (不在本 engine tracing spec scope 内)。

工具事件还要和安全过滤联动。工具参数应该记录“校验后的 args”，不要记录 LLM 原始未校验文本；如果校验失败，事件应标记 `success=false` 并带 `error_code=F-v21-tool-args-invalid`。这样 Studio 展示的不是一团模型幻觉文本，而是 runtime 真正尝试执行的结构化调用。

对外部网络工具，payload SHOULD 避免保存敏感 header、API key 或完整响应体。MVP0 可以保存 URL host、status code、耗时、截断后的 body 摘要；完整数据如果需要调试，应通过显式 debug 开关控制。这个规则与 LLM provider credential 隔离一致，避免 trace 文件变成秘密泄漏面。

最后，所有 tool call event 都应该带 `phase_id` 和可选 `tool_call_id`。SKILL node 当前从模型 tool call 中读取 `call.get("id", f"{name}-call")` 构造 ToolMessage，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:268` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:273`；MVP0 trace SHOULD 复用同一个 id，让 prompt、tool request、tool result 可以在 UI 中串起来。

这也为回放提供稳定锚点。一次 ReAct turn 里可能有多个 tool call；没有 `tool_call_id`，前端只能按时间猜测响应属于哪个请求。MVP0 SHOULD 把 `tool_call_id` 作为同一轮工具事件的 correlation id，并在异步 logger 中保持事件顺序。

回放器还应允许按 `run_id`、`phase_id`、`event_type` 做过滤。这样同一份 trace 既能服务完整时间线，也能服务单个节点的局部调试。
过滤结果必须保持原始时间顺序，避免调试时误判事件因果。

## MVP0 死代码清退 {#mvp0-死代码清退}

按 a1 (Codex) 2026-05-21 死代码调查 (详见 [baseline.md#legacy--死代码残留清单-a1-调查-2026-05-21](./baseline.md#legacy--死代码残留清单-a1-调查-2026-05-21)) 跟 PM 拍定原则 "把事情做对, 不向后兼容", MVP0 cutover **同 PR** 一并清退以下 tracing-and-observability 域内的 legacy / 死代码:

### 旧 harness 路径 callbacks 整体退役

跟 [execution-runtime/mvp0-alignment.md#MVP0-死代码清退](../execution-runtime/mvp0-alignment.md#mvp0-死代码清退) 协同, 旧 harness `_run_skill_dict` 路径 (`runner.py:284-286`) 默认创建的 `LoggingCallback()` 跟 `TracingCallback(trace_dir=...)` **跟 harness 栈一起退役**。V2.1 主线唯一 callback 接入点是新设计的 `V2TracingCallback` (本文件 API §2)。

### Callback legacy dict/event 兼容退役

以下 legacy dict/event 兼容代码 MVP0 同 PR 退役 (`V2TracingCallback` + 严格 `TraceEventKind` 枚举替代):

- `packages/graph-agent/src/graph_agent/callbacks/base.py:9` — legacy dict 兼容代码
- `packages/graph-agent/src/graph_agent/callbacks/events.py:10` — legacy event 兼容
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py:88` — legacy tracing callback 体

清退方式: 跟 V2TracingCallback (新设计, 接 LangGraph node lifecycle) 同 PR 直接替换, 不留 alias。

### 关键保留 — `_predict_internal/` 不退役

a1 已确认 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py` (`PredictTracingCallback`) + `exporter.py` + `interception.py` **不是死代码**, 是 V2.1 Predict 旁路活路径。

但 MVP0 设计的 `V2TracingCallback` 是 **public** API surface, 而 `_predict_internal/tracing.py:1-6` 文件头明示 "not public SDK surface"。两者关系需要在 design 阶段明确:

- 选项 A: V2TracingCallback 作为新 public surface, `PredictTracingCallback` 保留为 private 子类继承 V2TracingCallback (额外加 Predict-specific source tagging)
- 选项 B: 不复用 `_predict_internal` 类, 让 V2TracingCallback 跟 PredictTracingCallback 并存作为两个独立 callback (用户可以同时挂)

**这个选择 PM 拍**。在 baseline + mvp0-alignment 不预设, 留给 a2 在 design 阶段提推荐 + PM 拍。

### Cutover discipline (按 SOP-05)

tracing-and-observability 的 P1-4 修复 + V2TracingCallback 引入 + legacy callbacks 清退 **必须同 PR**, 跟 execution-runtime harness 栈退役同 cutover。改 callback shape 是 [BREAKING] (按 SOP-06), 必带完整迁移路径。

### V0.3.0 版本号 cutover (PM 2026-05-21)

MVP0 落地 = engine 版本号从 V2.1 升 V0.3.0 (详见 [INDEX.md#engine-版本号约定-2026-05-21-pm-拍定](../../INDEX.md#engine-版本号约定-2026-05-21-pm-拍定))。同 cutover PR 处理 tracing-and-observability 域内的版本号 step:

- **类名 `V2TracingCallback` → `V3TracingCallback`**: 上面 API §2 设计的新 public callback class 名字直接走 V0.3.0 命名 (PM 决策 "不向后兼容", V2.1 没真正接公开 callback, 不需要 V2 → V3 名字过渡)。文件命名 `tracing_v3.py` 或合并入新 `packages/graph-agent/src/graph_agent/callbacks/v3.py` (a2 design 阶段细化)。
- **`TraceEventKind` enum** 不带版本号 (枚举值就是 `NODE_START` / `NODE_END` / 等), 但 trace 文件顶部 metadata SHOULD 写 `engine_version: 0.3.0` 让 Studio 知道 schema 版本。
- **错误码前缀**: trace event payload `EXCEPTION.error_code` 跟 engine 错误码同步 (`F-v3-*`)。
- **trace dir 默认名**: `_run_v21_skill_dict` 返回 `trace_path` (`packages/graph-agent/src/graph_agent/core/runner.py:484`) 现状只拼 `Path(trace_dir) / "trace.json"`, V0.3.0 加版本目录避免新旧混淆 (可选, a2 拍)。

### MVP0 test 全清重写 (PM 2026-05-21)

PM 原则 (2026-05-21): **不只是 V1/V2.0 dead test, V2.1 现有 test 也全部清掉, MVP0 重新写 test 套**。

- **现状 V2.1 test**: `packages/graph-agent/tests/core/test_predict_*.py` / `test_tracing*.py` / `test_callbacks*.py` 等 tracing 相关 test 部分清退 (`_predict_internal/` 相关 test 保留 — Predict 不是死代码, 详见 baseline.md §Legacy 节)。
- **MVP0 重写覆盖** (tracing-and-observability 域):
  - P1-4: V3TracingCallback 在 LangGraph node lifecycle 发出 NODE_START/END / LLM_CALL_START/END / SUBAGENT_ENTER/EXIT / EXCEPTION 全 7 类事件 (覆盖每类至少一个 fixture)
  - 异步 logger 行为 (backpressure / 不阻塞模型推理)
  - TOOL_CALL_START/END 含 `tool_name = "call_subagent_<name>"` 跟 Q13 per-tool 命名一致
  - EXCEPTION 在 Q9 fallback 用尽后才触发 (单 provider fail 不触发)
  - trace file rotate (50MB 阈值) + size guard (payload 截断)
- **重写策略**: 同 P1-4 cutover PR。**禁止** "测试随后补"。
- **覆盖率**: unit (单 callback method) + integration (端到端 skill 跑, 抓 trace.jsonl 校验所有 event 都发) + e2e (Studio Trace 面板真消费 event, 不是 mock — 这部分跟 Studio 侧 spec 协同, 不在 engine 域 scope 内)。
