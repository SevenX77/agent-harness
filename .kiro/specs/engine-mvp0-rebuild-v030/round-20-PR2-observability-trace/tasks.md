# WS3 PR-2 Tasks: 观测事件恢复与 Trace 真实落盘

## Scope And Cutover Discipline

本 PR 修复 V0.3.0 目录型 `GRAPH.md` 主运行路径的观测断层与 trace 假路径。实施目标只覆盖 `runner._run_v030_skill_dict` 调用的 `graph_assembler` 路径；旧 `Harness -> PhaseExecutor -> LLMPhaseNode` 是平行引擎，不是本 PR 的改造目标，但事件 context 形态必须与其保持一致。

`WorkflowResult.trace_path` 从未写入的伪路径改为 `TracingCallback.save()` 返回的真实 summary 路径，属于 SOP-06 A 类 [BREAKING] 修复。若本 PR 提交，commit 标题必须使用 `feat(...)!`。SOP-06 继承字段表以 `design.md` 为准，本文件不重复维护字段表，避免 drift。

Cutover 要求：
- tests-first 红灯必须先提交到工作树并真实跑出失败，再实施转绿。
- 不得通过新增 skip/xfail、放宽断言、删除语料 deferral 或只测旧 Harness 路径制造假绿。
- `trace_path` 行为变更必须同步覆盖 unit、integration、e2e/入口级回归。
- 语料 deferral 保持 PR-1 后的预期状态：`19 xfailed + 2 skipped` 不变。

## Tasks

### 1. Red: 建立 V0.3.0 主路径事件与落盘红灯 [BREAKING]

Files:
- `packages/graph-agent/tests/**`

Steps:
- 新增显式 V0.3.0 目录型 `GRAPH.md` root fixture，测试必须从目录 root 进入 `run_skill` / `_run_v030_skill_dict` 路径，不能误走旧版 Harness。
- fixture 至少包含一个会触发大模型调用、普通工具调用，并通过 `finish_task` 结束的 agent phase。
- 挂载 Spy Callback，断言执行期间收到：
  - `PhaseStartEvent`
  - `LLMCallEvent`
  - `ToolCallEvent`，至少包含普通工具和 `finish_task`
  - `PhaseEndEvent`
- 断言 `trace_path` 非空且对应文件真实存在。
- 断言同目录 `tracing.jsonl` 真实存在、非空，并包含上述 typed events。
- 明确红灯原因：当前 `_skill_node` 零事件发射；V0.3.0 runner 分支在默认 callbacks 初始化前提前返回；当前返回的是未写入的 `trace.json` 伪路径。

Acceptance:
- 在不改生产代码时，上述测试必须失败，失败点应体现“没有事件”或“trace 文件不存在/typed stream 缺失”。
- 红灯测试不能依赖网络模型；用可控 mock chat model 触发固定 tool_calls 与 finish_task。
- 红灯测试不得新增 skip/xfail。

### 2. Green: 抽公共 callback emit helper，解除新旧运行栈耦合

Files:
- `packages/graph-agent/src/graph_agent/callbacks/emit.py`
- `packages/graph-agent/src/graph_agent/core/harness.py`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/tests/**`

Steps:
- 新增 `graph_agent.callbacks.emit._safe_emit_event(callbacks, event)`，语义保持：逐个调用 `callback.on_event(event)`，单个 callback 异常只记录日志，不中断运行。
- 将 `core.harness` 改为从公共 helper 复用 `_safe_emit_event`，不改变旧 Harness 行为。
- `graph_assembler` 后续只从公共 helper 导入，不从 `core.harness` 导入，避免 V0.3.0 装配器依赖旧 harness 模块。
- 增加/调整单测覆盖：一个 callback 抛错时，后续 callback 仍能收到事件。

Acceptance:
- `graph_assembler.py` 不 import `graph_agent.core.harness`。
- 旧 Harness 相关测试保持通过。
- 公共 helper 的错误隔离行为有单测保护。

### 3. Green: 在 `_skill_node` 发射 Phase/LLM/Tool 全链路事件

Files:
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/tests/**`

Steps:
- 进入 `_skill_node` 后立即发 `PhaseStartEvent`，`context=dict(state.get("data", {}))`，对齐旧 `LLMPhaseNode` 的完整业务数据快照契约。
- 每次 `model.invoke(...)` 后发 `LLMCallEvent`。
- token usage 提取需容错并归一字段名：
  - 支持 `input_tokens` / `output_tokens`
  - 支持 `prompt_tokens` / `completion_tokens`
  - 缺失或形态异常时降级为 `0`
- 每个工具成功执行后发 `ToolCallEvent`，覆盖普通业务工具、critic/framework 工具、subagent 工具和 `finish_task`。
- `ToolCallEvent.result` 必须是字符串；dict/list 用 `json.dumps(..., ensure_ascii=False, default=str)` 序列化，其他非字符串结果安全转字符串。
- `ToolCallEvent.args` 必须是 dict；非 dict 入参归一为空 dict 或安全包装，不得让 typed event 构造失败。
- 所有退出路径都必须发 `PhaseEndEvent`：
  - `finish_task` 提前返回路径
  - 正常循环结束路径
  - 若实现选择处理异常路径，必须保持异常继续抛出，不吞错
- `PhaseEndEvent.context` 为最终完整业务数据快照。`finish_task` 早返回时，应基于即将返回的状态计算最终 data，不得只发送空 `data_updates`。

Acceptance:
- 任务 1 的 Spy Callback 红灯转绿，并能证明普通工具与 `finish_task` 都产生 ToolCall。
- dict/list 工具结果不会导致 Pydantic event 校验失败。
- mock LLM 没有 token metadata 时仍产生 `LLMCallEvent(input_tokens=0, output_tokens=0)`。
- `PhaseStartEvent.context` / `PhaseEndEvent.context` 使用完整 data，而不是 `inputs` 子集或局部 delta。

### 4. Green: V0.3.0 runner 提前绑定 TracingCallback 并返回真实路径

Files:
- `packages/graph-agent/src/graph_agent/core/runner.py`
- `packages/graph-agent/tests/**`

Steps:
- 在 `_run_v030_skill_dict` 调用 `graph.invoke()` 前计算有效 trace 目录：
  - 显式 `trace_dir` 优先
  - 否则若输入包含 `output_dir`，使用与设计一致的 trace 输出目录
  - 两者都没有时允许 `trace_path=None`，但 callbacks 语义必须清晰
- 如果 `callbacks is None`，为 V0.3.0 分支初始化默认 callbacks，至少包含 `LoggingCallback()` 和 `TracingCallback(trace_dir=effective_trace_dir)`。
- 如果调用方传入 callbacks，检查其中的 `TracingCallback`：
  - 有有效 trace 目录且 tracer 尚未绑定时，在 `graph.invoke()` 前调用 `.set_trace_dir(...)`
  - 若没有 tracer 且有 trace 目录，追加一个 `TracingCallback(trace_dir=effective_trace_dir)`
- `graph.invoke()` 完成后调用每个 `TracingCallback.save(effective_trace_dir)`；返回值作为真实 `trace_path`。
- 若保存失败，应抛出明确 trace 写入错误，不返回伪成功路径。
- 删除 V0.3.0 分支中硬编码 `Path(trace_dir) / "trace.json"` 的返回行为。

Acceptance:
- 任务 1 的 `trace_path` 存在性断言转绿。
- `tracing.jsonl` 中包含执行期间产生的 typed events，而不是只在结束后生成空文件。
- summary 文件名来自 `TracingCallback.save()` 的真实返回，例如 `{run_id}_summary.json`。
- 无 `trace_dir` / `output_dir` 的调用行为由测试明确覆盖，不误报虚假路径。

### 5. Cutover Tests: 覆盖 unit + integration + e2e/入口行为 [BREAKING]

Files:
- `packages/graph-agent/tests/callbacks/**`
- `packages/graph-agent/tests/core/**`
- `packages/graph-agent/tests/e2e/**`
- 其他现有入口测试文件，按实际落点最小修改

Steps:
- Unit 层覆盖公共 emit helper、token usage 归一化、tool result 字符串化、trace callback 预绑定逻辑。
- Integration 层覆盖 V0.3.0 目录型 `GRAPH.md` fixture 的完整事件序列和真实落盘。
- E2E/入口层覆盖 `run_skill` 返回的 `trace_path` 是真实 summary 文件，不再是伪 `trace.json`。
- 增加一条回归，确保测试明确命中 V0.3.0 dir+`GRAPH.md` 路由，而不是旧 Harness。

Acceptance:
- 如果 `_skill_node` 事件发射被移除，新增测试失败。
- 如果 runner 不在 invoke 前绑定 `TracingCallback`，`tracing.jsonl` 断言失败。
- 如果 `trace_path` 回退为硬编码 `trace.json`，入口/e2e 测试失败。

### 6. Docs And API Notes: 同步 breaking 行为说明

Files:
- `packages/graph-agent/README.md`
- `docs/engine/**` 中与 trace path / observability 直接相关的文档，若已存在对应页面
- `.kiro/specs/engine-mvp0-rebuild-v030/round-20-PR2-observability-trace/design.md` 仅在实现发现事实漂移时更新

Steps:
- 更新用户可见说明：`trace_path` 现在指向真实 summary JSON 文件。
- 说明 `tracing.jsonl` 是同目录 typed event stream。
- 不扩大到 persona/cache/sandbox 等无关主题。
- 若实现过程中发现 design 的事实前提变化，先同步 design，再继续实现，避免文档和代码漂移。

Acceptance:
- 文档不再声称 V0.3.0 返回 `trace.json` 伪路径。
- 文档说明 summary 与 `tracing.jsonl` 的关系。
- 未引入与 PR-2 无关的重构说明。

### 7. Final Verification: 诚实绿与物理落盘验收

Files:
- No additional files expected.

Commands:
- `uv run pytest packages/graph-agent/tests`
- `rg "Path\\(trace_dir\\) / \"trace\\.json\"|trace\\.json" packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/tests`
- `rg "from graph_agent\\.core\\.harness import .*_safe_emit_event|import graph_agent\\.core\\.harness" packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `rg "strict=False|allow_module_level=True" packages/graph-agent/tests`
- 真跑一个 V0.3.0 fixture skill，指定输出目录，人工确认同目录存在：
  - `{run_id}_summary.json`
  - `tracing.jsonl`
  - `tracing.jsonl` 内包含 `phase_start`、`llm_call`、`tool_call`、`phase_end`

Acceptance:
- 全量 pytest 诚实绿：新增红灯全部转绿，非本 PR 语料 deferral 仍为 `19 xfailed + 2 skipped`。
- grep gate 不再发现 V0.3.0 runner 返回伪 `trace.json`。
- grep gate 证明 `graph_assembler` 没有耦合旧 harness 的 `_safe_emit_event`。
- 真实 fixture smoke 证明 summary 与 typed event stream 均物理落盘。
- 不以固定 passed 数作为唯一验收；以“0 failed + 预期 deferral 不变 + 新增验收覆盖”为准。
