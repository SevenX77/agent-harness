# Gemini Prompt: WS-E4 Runtime Edge Events

这是一份 Gemini implementation handoff prompt，不是 Kiro spec。

不要运行 `/kiro:spec-tasks`。
不要生成或覆盖 Kiro requirements/design。
`.kiro/specs/engine-mvp1/task-ws-e4-runtime-edge-events.md` 是本仓库已写好的实施任务文件，请只把它当作任务说明读取。

你是 Gemini，实现 Engine MVP1 WS-E4 runtime edge events。请严格测试先行，不要扩大范围。

工作区：
`/Users/sevenx/Documents/coding/agent-harness/.worktrees/engine-mvp1-ws-e4-runtime-edge-events`

分支：
`codex/engine-mvp1-ws-e4-runtime-edge-events`

基线：
- `HEAD = 34ee40f1 feat(gateway): merge mvp1 updates into main`
- 当前不是 stacked branch。
- 本地 `codex/engine-mvp1-ws-e1-io-runtime` 当前也指向同一 commit，没有 file lazy injection 实现可依赖。
- `graph_assembler.py` 与 WS-E1-io 有潜在冲突；本次实现完成后必须在汇报中写明 base/stacked 状态和剩余 merge 风险。

必读文件：
- `.kiro/specs/engine-mvp1/requirements-ws-e4-runtime-edge-events.md`
- `.kiro/specs/engine-mvp1/task-ws-e4-runtime-edge-events.md`
- `docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md` §3/§5/§8
- `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md` 后端功能 §1/§4/§5
- `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md` §2/§3/§5/§8
- `docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md` §2/§3/§5/§7
- `docs/engine/mvp1/03-api-contract/mvp1-alignment.md` §2.2/§3.2
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`
- `packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py`
- `packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py`

已批准 RED：
```bash
uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py -q
```

当前 RED 结果：`4 failed, 1 xfailed`。

失败形状必须保持为 runtime edge events 尚未接入真实 emit：
- 普通串行图真实执行成功，但 subscriber 中没有 `InputDispatchEvent`。
- batch iterate 真实执行成功，但每个分支没有带稳定 `branch_index` 的 `InputDispatchEvent`。
- loop accumulate 真实执行成功，但 reducer/accumulate 后没有 `BlackboardReduceEvent`。
- `run_skill` e2e 真实执行成功，但 `event_subscriber` 与 `trace.jsonl` 都没有 `input_dispatch`。
- `InputFileInjectedEvent` 测试 xfail：当前 base 无 WS-E1-io file lazy injection path，必须继续保留依赖门。

允许修改文件：
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`
- `packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py`
- `packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py`

默认禁止触碰文件：
- `apps/studio/**`
- `packages/graph-agent-gateway/**`
- `packages/graph-agent/src/graph_agent/callbacks/events.py`
- `packages/graph-agent/src/graph_agent/callbacks/emit.py`
- `packages/graph-agent/src/graph_agent/callbacks/base.py`
- `packages/graph-agent/src/graph_agent/core/runner.py`
- `packages/graph-agent/src/graph_agent/io/**`
- `packages/graph-agent/src/graph_agent/tools/builtin/read_file.py`
- `packages/graph-agent/src/graph_agent/core/checkpointer.py`
- `packages/graph-agent/src/graph_agent/core/exceptions.py`
- `packages/graph-agent/src/graph_agent/core/error_registry.py`
- `packages/graph-agent/src/graph_agent/core/result.py`

如果你认为 callback schema/serialization drift 迫使你修改 callback modules，先停下并报告原因；不要自行扩大 owns。

目标契约：
1. 在 phase 输入从 blackboard 按 `io.inputs` 切片并交给节点前，发 `InputDispatchEvent`。
2. 普通串行图每个真实执行 phase 都要发一条。
3. batch/iterate 每个分支或轮次都要发一条，并提供稳定 1-based `branch_index`，与既有 `iter1` / `iter2` / `iter3` 习惯一致。
4. 声明式 loop accumulate/reducer 合并后，发 `BlackboardReduceEvent`，包含 reducer、changed_keys、操作后 blackboard_snapshot。
5. 所有事件必须走通用 callbacks/event sink，并自然写入 `trace.jsonl`，一行一个 typed event。
6. 不实现 `InputFileInjectedEvent` 的真实 runtime path，因为 WS-E1-io 当前未落地；继续保留 xfail。
7. 不新增 Studio-only 字段，不做 reducer authoritative before/after diff。

实现顺序：
1. 先运行已批准 RED，确认仍是 `4 failed, 1 xfailed` 且失败形状干净。
2. 读 `PhaseWrapper.wrap(...)`、`StateMapper.build_phase_input(...)`、`_wrap_phase_runtime_node(...)`、`_build_batch_iterate_phase(...)`、`_build_loop_iterate_phase(...)`，确认当前 input slice、callbacks、iterate accumulate 的真实路径。
3. 实现普通 phase input dispatch 的最小 emit，先让 serial dispatch 和 e2e trace 测试通过。
4. 扩展 batch/iterate 分支 dispatch，每个实际分支一条，`branch_index` 为 1-based。
5. 在声明式 loop accumulate merge 后发 `BlackboardReduceEvent`，snapshot 必须是 merge 后 business blackboard。
6. 保持 file injection xfail，不写 file lazy injection / read_file / artifact / storage / runner 语义。
7. 跑全部验证，确认 forbidden files 无 diff。

验证命令：
```bash
uv run pytest packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py -q
uv run pytest packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/runtime/test_state_mapper.py -q
uv run pytest packages/graph-agent/tests/callbacks/test_emit.py packages/graph-agent/tests/callbacks/test_on_event_characterization.py -q
uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py -q
uv run ruff check packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/runtime/state_mapper.py packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py
git diff --check
git diff -- packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/callbacks/base.py
git diff -- apps/studio packages/graph-agent-gateway packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/io packages/graph-agent/src/graph_agent/tools/builtin/read_file.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/exceptions.py packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/core/result.py
```

如果 `uv run` 摸脏 `uv.lock`，执行：
```bash
git restore -- uv.lock
```

硬退出条件：
- 已批准 WS-E4 runtime RED suite 变为 `4 passed, 1 xfailed`。
- 串行图每个 phase 执行前都有 `InputDispatchEvent`。
- `InputDispatchEvent` 同时到达 event subscriber 和 `trace.jsonl`。
- batch/iterate 每个分支都有 `InputDispatchEvent`，`branch_index` 稳定 1-based。
- loop accumulate 每次 declared merge 后都有 `BlackboardReduceEvent`。
- `BlackboardReduceEvent` 包含 reducer 名、changed keys、操作后 blackboard snapshot，不新增 before/after diff。
- `InputFileInjectedEvent` 继续停在 WS-E1-io 依赖门；不实现 file lazy injection/read_file/artifact/storage/runner。
- callback modules 无 diff，除非 Codex 明确批准扩大 owns。
- Studio、gateway、runner/io/read_file/artifact/checkpoint/error-contract files 无 diff。
- 回归验证命令通过。
- `uv.lock` 干净。

不要回写 baseline。GREEN 后只报告真实落地行为，等待 Codex review 后再由 Codex 回写：
- `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md`
- `docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md`
- graph-exec baseline 状态；如果目标 baseline 文件不存在，报告原因。

回报格式：
1. 修改文件清单。
2. 每条验证命令的 pass/fail 摘要。
3. `InputDispatchEvent` 的 emit 时机，以及 `from_phase`、`dispatched_keys`、`changed_keys`、`blackboard_snapshot`、`branch_index` 如何得出。
4. `BlackboardReduceEvent` 的 emit 时机，以及 reducer 名和 snapshot 时点。
5. 确认 `InputFileInjectedEvent` 仍因 WS-E1-io 未落地而保持 xfail。
6. 确认 forbidden files 无 diff。
7. 写明 `graph_assembler.py` 与 WS-E1-io 的协调状态：base commit、是否 stacked、剩余 merge 风险。
8. 如有 hard exit 未满足，逐条说明原因。
