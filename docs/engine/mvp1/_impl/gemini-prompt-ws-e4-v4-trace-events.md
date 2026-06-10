# Gemini Prompt: WS-E4 V4 Trace Events

这是一份 Gemini implementation handoff prompt，不是 Kiro spec。

不要运行 `/kiro:spec-tasks`。
不要生成或修改 Kiro spec。
`.kiro/specs/engine-mvp1/task-ws-e4-v4-trace-events.md` 只是本仓库已经写好的实施任务文件，请只把它当作任务说明读取。

你是 Gemini，实现 Engine MVP1 Wave2 / WS-E4 V4 trace events。请严格测试先行，不要扩大范围。

工作区：
`/Users/sevenx/.config/superpowers/worktrees/agent-harness/codex-engine-mvp1-e4-red`

分支：
`codex/engine-mvp1-e4-red`

基线：
- `HEAD = 1b79bce4`
- 从 wave2 clean baseline 创建
- baseline 已跑：
  `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_purity_le2.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q`
- baseline 结果：`51 passed`

必读文件：
- `docs/engine/mvp1/_impl/requirements-ws-e4-v4-trace-events.md`
- `.kiro/specs/engine-mvp1/task-ws-e4-v4-trace-events.md`
- `docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md` §2/§3/§5/§8
- `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md` 后端功能 §1/§4
- `packages/graph-agent/src/graph_agent/callbacks/events.py`
- `packages/graph-agent/src/graph_agent/callbacks/base.py`
- `packages/graph-agent/src/graph_agent/callbacks/emit.py`
- `packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py`
- `packages/graph-agent/tests/test_public_api_contract.py`

已批准 RED：
```bash
uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py packages/graph-agent/tests/test_public_api_contract.py::test_callback_event_union_contains_consumed_event_models -q
```

当前 RED 结果：`6 failed`。失败点应落在：
- `LLMCallEvent` / `ToolCallEvent` 缺 `parent_node_id`、`node_type`
- 旧构造下缺 `parent_node_id=None`、`node_type=None`
- `graph_agent.callbacks.events.__all__` 缺 `BlackboardReduceEvent`、`InputDispatchEvent`、`InputFileInjectedEvent`
- `BlackboardReduceEvent` / `InputDispatchEvent` / `InputFileInjectedEvent` 类不存在
- `CallbackEvent` union 缺这 3 个 V4 trace events

允许修改文件：
- `packages/graph-agent/src/graph_agent/callbacks/events.py`
- `packages/graph-agent/src/graph_agent/callbacks/emit.py`
- `packages/graph-agent/src/graph_agent/callbacks/base.py`
- `packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py`
- `packages/graph-agent/tests/test_public_api_contract.py`

禁止触碰文件：
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/src/graph_agent/core/runner.py`
- `packages/graph-agent/src/graph_agent/middleware/tracing.py`
- `packages/graph-agent/src/graph_agent/middleware/tool_error.py`
- `packages/graph-agent/src/graph_agent/middleware/loop_detection.py`
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py`
- `packages/graph-agent/src/graph_agent/core/tracing_proxy.py`
- `apps/studio/**`
- `packages/graph-agent-gateway/**`

目标契约：
1. `LLMCallEvent` 和 `ToolCallEvent` 增加 additive 字段：
   - `parent_node_id: str | None = None`
   - `node_type: str | None = None`
   旧构造方式必须保持兼容，两个字段默认 `None`。不要改变旧 legacy callback hook 的参数语义。

2. 新增 3 个 V4 edge operation typed events：
   - `BlackboardReduceEvent`
     - `event_type = "blackboard_reduce"`
     - 共有字段：`from_phase: str | None`、`to_phase: str`、`changed_keys: list[str]`、`blackboard_snapshot: dict[str, Any]`
     - 专有字段：`reducer: str`
   - `InputDispatchEvent`
     - `event_type = "input_dispatch"`
     - 共有字段同上
     - 专有字段：`dispatched_keys: list[str]`、`branch_index: int | None`
   - `InputFileInjectedEvent`
     - `event_type = "input_file_injected"`
     - 共有字段同上
     - 专有字段：`file_ref: str`、`target_field: str`
   这 3 个事件必须继承现有 `_EventBase` 行为，保持 `extra="forbid"`。

3. 将 3 个新增事件加入：
   - `CallbackEvent` discriminated union
   - `graph_agent.callbacks.events.__all__`
   - 默认 `Callback().on_event(...)` 的 typed-only event 识别集合

4. `_TraceJsonlSink` 对新事件保持一行一个 JSON object。如果现有 generic `model_dump(mode="json")` 逻辑已经满足测试，不要为了“看起来改了”而改 `callbacks/emit.py`。

5. 不做真实 emit 接线。不要改 graph exec、runner、middleware。不要把事件接到实际运行路径；这属于后续 WS-E2 / graph-exec / io 工作。

实现顺序建议：
1. 先运行已批准 RED，确认仍是 `6 failed` 且失败形状干净。
2. 修改 `events.py`：补 LLM/tool 微观拓扑字段。
3. 修改 `events.py`：补 3 个 edge operation event class。
4. 修改 `events.py`：补 union 和 `__all__`。
5. 修改 `base.py`：让默认 callback 把 3 个新事件视作 typed-only event，不加 legacy hook。
6. 只有在 RED 证明需要时才修改 `emit.py`。

验证命令：
```bash
uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py packages/graph-agent/tests/test_public_api_contract.py::test_callback_event_union_contains_consumed_event_models -q
uv run pytest packages/graph-agent/tests/callbacks/test_events.py packages/graph-agent/tests/callbacks/test_on_event_characterization.py packages/graph-agent/tests/callbacks/test_emit.py -q
uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_purity_le2.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q
git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/callbacks/tracing.py packages/graph-agent/src/graph_agent/core/tracing_proxy.py
git diff --check -- packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/callbacks/base.py packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py packages/graph-agent/tests/test_public_api_contract.py
```

如果 `uv run` 摸脏 `uv.lock`，执行：
```bash
git restore -- uv.lock
```

硬退出条件：
- 已批准 WS-E4 RED suite 全绿。
- `LLMCallEvent` / `ToolCallEvent` 新字段存在且旧构造默认 `None`。
- 3 个 V4 edge operation events 存在、字段正确、extra forbid。
- 新事件进入 `CallbackEvent` union 和 `events.__all__`。
- `_TraceJsonlSink` 写新事件为一行一 JSON object。
- 默认 `Callback().on_event(...)` 接受新 typed-only events，不出现 `unrecognised event type` warning。
- existing callback tests 仍绿。
- baseline regression suite 仍绿。
- 禁止文件无 diff。
- `uv.lock` 干净。

回报格式：
1. 修改文件清单。
2. 运行过的测试命令和 pass/fail 摘要。
3. 确认 forbidden files 无 diff，且没有修改 `apps/studio/**` / `packages/graph-agent-gateway/**`。
4. 说明 `callbacks/emit.py` 是否真的需要改；如果没改，说明是因为现有 generic JSONL 逻辑已满足。
5. 如有未满足 hard exit 的项目，逐条说明原因。
