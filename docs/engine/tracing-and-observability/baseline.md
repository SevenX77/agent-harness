# tracing-and-observability (engine) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Predict 内部与 LangGraph 节点拦截、生命周期事件发出、结构化 Trace 日志 (audit P1-4)
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

trace 文件和 callback 事件本身不是 UI。Studio 可以选择读取它们做瀑布流或历史面板，但本文件只描述 Python engine 目前能产生什么观测数据。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

前端不直接执行 `PredictTracingCallback`，也不直接参与 LangGraph node interception。本 feature 的前端相关性只存在于数据消费者层面，不在当前 Python 实现里。

## 后端功能

### V2.1 主线 observability 现状

当前 V2.1 `run_skill()` 主线是 `_run_v21_skill_dict()`，代码在 `packages/graph-agent/src/graph_agent/core/runner.py:451` 到 `packages/graph-agent/src/graph_agent/core/runner.py:486`。它明确 `del callbacks`，见 `packages/graph-agent/src/graph_agent/core/runner.py:462`，随后直接 `compile_skill -> assemble_graph -> graph.invoke`，见 `packages/graph-agent/src/graph_agent/core/runner.py:463` 到 `packages/graph-agent/src/graph_agent/core/runner.py:471`。

因此 audit P1-4 的当前结论成立：V2.1 主线没有接 callbacks / trace / heartbeat 等旧 harness 能力，位置是 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:360`。`_run_v21_skill_dict()` 返回的 `trace_path` 只是当 `trace_dir` 存在时拼出 `trace.json` 路径，见 `packages/graph-agent/src/graph_agent/core/runner.py:484`；这不等于 runtime 已经写出 phase 级 trace。

旧 harness 侧仍然会默认创建 `LoggingCallback()` 和 `TracingCallback(trace_dir=...)`，代码在 `packages/graph-agent/src/graph_agent/core/runner.py:284` 到 `packages/graph-agent/src/graph_agent/core/runner.py:286`。但这是 legacy `_run_skill_dict()` 旧路径，不是 V2.1 `_run_v21_skill_dict()` 的实际主线。

### PredictTracingCallback

`PredictTracingCallback` 是当前可见的 Predict 专用 tracing callback，定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76`。Predict 第一次出现时需要定义：它是 Studio / engine 用来做 "不花真实 LLM 成本的预测/回放/手工覆盖" 的内部模式，trace 需要标明输出来自 golden case、Copilot、heuristic stub 或 manual，而不是普通真实 LLM 调用。

`PredictTracingCallback` 继承 `TracingCallback`，并在初始化时持有一个 `PredictMockSourceCache`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:79` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:87`。`PredictMockSourceCache` 是进程内缓存，把 phase name 映射到 mocked source，定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:31` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:52`。

`on_chain_start()` 会把 root metadata 标记为 `is_predict=True`，写 `predict_chain_start` 事件，并写 typed `PredictChainStartEvent`，代码在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:101` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:109`。

`on_phase_start()` 会调用父类开始 phase，并把 business inputs 保留到 phase stack 顶部，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:111` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:116`。这里的 business inputs 指本 phase 看到的上下文字段快照，不包含 UI 状态。

`on_phase_end()` 会把 usage/cost 指标清零，读取 cached mocked source，调用父类结束 phase，然后把 outputs、metrics、mocked_source 写回最后一个 phase record，代码在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:118` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:137`。

`on_llm_call()` 会强制 token/cost 为 0，再调用父类记录 LLM 活动，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:139` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:157`。`save()` 会调用父类保存 trace，然后把 root metadata 写入 JSON，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:159` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:167`。

### Predict interception 和 source 标记

Predict mock source 的记录函数是 `record_mock_source(phase_name, source)`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:58` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:61`。读取函数是 `get_mock_source()`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:64` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:67`。

实际 interception 层会在 mock LLM 返回前调用 `record_mock_source()`，`rg` 核验到调用点在 `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py:189`。这个机制的含义是：拦截层决定某个 phase 的输出来自 golden case、Copilot、heuristic stub 还是 manual；tracing callback 在 phase end 时把这个 source 合进 phase record。

### 结构化导出

`exporter.py` 负责把 raw trace phase/event 转成紧凑的 Predict business slice。入口 `assemble_phase_record(raw_phase, max_field_chars=4096)` 在 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:24` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:38`。

导出的 `PhaseRecord` 包含：

- `phase_name`，从 `raw_phase["phase_name"]` 或 `raw_phase["name"]` 来，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:33`。
- `type`，由 `_phase_type()` 推断，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:34` 和 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:54` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:63`。
- `inputs` 和 `outputs`，都会走 `_sanitize_mapping()`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:35` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:36`。
- `mocked_source`，来自 `_mocked_source()`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:31` 和 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:66` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:71`。

`_sanitize_mapping()` 会丢弃 usage/token/cost 字段，见 `_USAGE_KEYS` 在 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:9` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:19`，实际过滤在 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:74` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:89`。长字符串会被截断，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:92` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:108`。

批量导出入口 `assemble_phase_records()` 在 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:41` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:51`。

### 和 LangGraph 节点的关系

当前 `assemble_graph()` 创建的 LOGIC/SKILL/SUBGRAPH node 本身没有调用 `PredictTracingCallback.on_phase_start()` 或 `on_phase_end()`。LOGIC node 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136` 只执行 action 并返回 data delta；SUBGRAPH node 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:172` 只调用子图并返回 delta；SKILL node 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:229` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:296` 只处理模型/tool/finish_task 循环。

subagent runnable config 会透传 parent callbacks 到 child config，如果 parent config 带 callbacks，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:497` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:505`。但是 V2.1 `run_skill()` 顶层已经 `del callbacks`，见 `packages/graph-agent/src/graph_agent/core/runner.py:462`，所以 public runner 默认不会给这条通道提供 callbacks。

这就是当前 observability 的核心边界：Predict 内部有 callback/exporter 工具；V2.1 LangGraph 主执行路径没有统一 phase start/end、tool call、LLM call、heartbeat、checkpoint/resume trace 接线。

## API

### Predict tracing API

`PredictTracingCallback` 构造函数接受 `*args`、可选 `source_cache` 和 `**kwargs`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:79` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:84`。它暴露 `root_metadata`、`phases`、`phases_in_progress` 三个 property，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:89` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:99`。

模块 `__all__` 暴露 `PredictMockSourceCache`、`PredictTracingCallback`、`clear_mock_source_cache`、`get_mock_source`、`record_mock_source`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:182` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:188`。

### Predict exporter API

导出 API 是 `assemble_phase_record()` 和 `assemble_phase_records()`，并在 `__all__` 暴露，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:111`。它们输出的是 `PhaseRecord` 模型，模型 import 在 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:7`。

### V2.1 runner trace API

V2.1 runner 目前没有稳定 trace callback API。`run_skill()` 签名里有 `callbacks` 和 `trace_dir`，见 `packages/graph-agent/src/graph_agent/core/runner.py:165` 到 `packages/graph-agent/src/graph_agent/core/runner.py:168`，但 V2.1 分支删除 callbacks，见 `packages/graph-agent/src/graph_agent/core/runner.py:462`。`trace_dir` 只影响返回 dict 里的 `trace_path` 字符串，见 `packages/graph-agent/src/graph_agent/core/runner.py:484`。

## Data Model / State

### trace phase record

Predict trace 的核心业务切片是 `PhaseRecord`。从 exporter 看，当下关心的字段是 `phase_name`、`type`、`inputs`、`outputs`、`mocked_source`，构造位置是 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:31` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:38`。

`mocked_source` 的合法值是 `"golden_case"`、`"copilot"`、`"heuristic_stub"`、`"manual"`，集合定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:21`，tracing 侧类型定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:18`。

usage/cost 类字段在 Predict trace 里被清零或过滤：tracing 侧 `_ZERO_USAGE_KEYS` 定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:20` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:28`，清零函数在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:170` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:179`；exporter 侧 `_USAGE_KEYS` 定义在 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:9` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:19`。

### P1-4 缺口的当下具体内容

audit P1-4 说旧 `GraphAgentHarness` 支持 callbacks、heartbeat、checkpoint/resume、tracing、IOManager、working memory、nudge loop、validation retry、artifact saver，但 V2.1 `run_skill()` 直接走 `compile_skill -> assemble_graph -> graph.invoke`，见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:360` 到 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:374`。

当前代码对应的缺口是：

- V2.1 public runner 丢弃 callbacks，见 `packages/graph-agent/src/graph_agent/core/runner.py:462`。
- V2.1 graph node 没有统一发 phase start/end event，LOGIC/SUBGRAPH/SKILL node 主体分别见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:155`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:229`。
- V2.1 runner 返回 `trace_path` 但没有在这条分支保存 trace JSON，见 `packages/graph-agent/src/graph_agent/core/runner.py:480` 到 `packages/graph-agent/src/graph_agent/core/runner.py:485`。
- Predict callback/exporter 存在，但它是 `_predict_internal` 私有模块，文件头说明 "not public SDK surface" 的定位在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:1` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:6`。

### 与 state/runtime 的互动

Trace 要想表达 phase 输入输出，必须理解 runtime 的 `BlackboardState`。当前 `data`、`flow`、`messages` 的定义在 [state-and-io-contract/baseline.md#data-model--state](../state-and-io-contract/baseline.md#data-model--state)。当前节点生命周期在 [execution-runtime/baseline.md#后端功能](../execution-runtime/baseline.md#后端功能)。

当下 Predict exporter 只保留 inputs/outputs 这类 business slice，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:35` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:36`。它不会完整表达 reducer 冲突、subagent child flow、LangGraph super-step 等 runtime 细节。

### 当前可观测性的分层

当下代码里至少有三层容易混淆的 observability。

第一层是旧 harness callbacks。`run_skill()` 旧路径会默认创建 `LoggingCallback()` 和 `TracingCallback(trace_dir=...)`，代码在 `packages/graph-agent/src/graph_agent/core/runner.py:284` 到 `packages/graph-agent/src/graph_agent/core/runner.py:286`。这层历史上承担 heartbeat、trace、artifact 等职责，但 V2.1 graph runner 没有完整接入。

第二层是 V2.1 LangGraph runtime 自身。它有 node、edge、state reducer，但当前 node 函数没有在入口/出口发统一事件。LOGIC node 返回 data delta，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136`；SUBGRAPH node 返回 data/flow，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:172`；SKILL node 返回 flow/messages/data，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:289` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:296`。

第三层是 Predict 内部 tracing。它能标记 Predict chain、phase inputs/outputs、mock source、zeroed usage，入口是 `PredictTracingCallback`，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76`。但是 `_predict_internal` 的文件头明确说它是 private internal，不是 public SDK surface，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:1` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:6`。

### 与 execution-runtime 的双向关系

tracing 本身不执行任务。真实任务执行发生在 runtime node 生命周期里，详见 [execution-runtime/baseline.md#后端功能](../execution-runtime/baseline.md#后端功能)。如果没有 runtime 在 phase start/end、LLM call、tool call 时调用 callback，`PredictTracingCallback` 这样的 callback 类就只能服务已经接入它的 Predict 路径。

反过来，execution runtime 返回 `trace_path` 但不写 trace 的现状属于 observability 缺口，不属于 graph 装配算法本身。证据是 `_run_v21_skill_dict()` 在返回 dict 时只拼接 `Path(trace_dir) / "trace.json"`，见 `packages/graph-agent/src/graph_agent/core/runner.py:480` 到 `packages/graph-agent/src/graph_agent/core/runner.py:485`。

### 与 state-and-io-contract 的双向关系

trace 里要表达的 `inputs` 和 `outputs` 不是凭空来的，它们必须从 state 或 Predict mock records 中提取。当前 `PhaseRecord` 记录 inputs/outputs，见 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:35` 到 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:36`。但 runtime 当前没有 phase-level IO contract，因此 "phase input" 在 V2.1 主线里不是一个正式 state 字段。state 现状见 [state-and-io-contract/baseline.md#data-model--state](../state-and-io-contract/baseline.md#data-model--state)。

这也解释了为什么 P1-4 不只是 "少一个 callback 类"。callback 类存在，Predict exporter 也存在；缺口在于 V2.1 graph runtime 没有把 phase lifecycle 和 state slice 统一投递出去。

### 读代码时的主路径提示

读 observability 建议先看 `_run_v21_skill_dict()`，位置是 `packages/graph-agent/src/graph_agent/core/runner.py:451`，确认 V2.1 主线没有接 callbacks。然后看旧路径 callbacks 默认创建，位置是 `packages/graph-agent/src/graph_agent/core/runner.py:284`，理解 legacy 能力来自哪里。

再看 `PredictTracingCallback`，位置是 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:76`。phase start/end 分别在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:111` 和 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:118`。LLM call 记录在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:139`。保存 trace metadata 在 `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py:159`。

最后看 exporter，入口是 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:24`。如果关心 trace 字段被怎么清洗，看 `_sanitize_mapping()`，位置是 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:74`。如果关心 usage/cost 为什么不进入 Predict business slice，看 `_USAGE_KEYS`，位置是 `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py:9`。
