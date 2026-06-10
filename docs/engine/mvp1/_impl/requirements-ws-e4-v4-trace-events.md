---
ws_id: WS-E4-v4-trace-events
modules: [02-mechanism/06-seam/02-observability, 03-api-contract]
depends_on: []
blocks: [WS-E1-io, WS-E2]
owns_files:
  - docs/engine/mvp1/_impl/requirements-ws-e4-v4-trace-events.md
  - packages/graph-agent/src/graph_agent/callbacks/events.py
  - packages/graph-agent/src/graph_agent/callbacks/emit.py
  - packages/graph-agent/src/graph_agent/callbacks/base.py
  - packages/graph-agent/tests/callbacks/test_ws_e4_v4_trace_events_red.py
  - packages/graph-agent/tests/test_public_api_contract.py
spec_ssot:
  - ../02-mechanism/06-seam/02-observability/mvp1-alignment.md §2/§3/§5/§8
  - ../02-mechanism/06-seam/02-observability/baseline.md 后端功能 §1/§4
  - ./IMPL_PLAN.md §三 WS-E4 / §六 Wave 2
status: drafted
---

# WS-E4 V4 Trace Events — 需求书

## 1. 目标
补齐 V4 trace 的事件契约，让 Studio 能在 trace 流里识别 agent 内微观拓扑和节点间 dot 操作。此 WS 只建立 schema、union、JSONL、默认 callback 和 public contract；不接真实 emit 点。

## 2. SSOT 指针
- 目标机制：`docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md` §2/§3/§5/§8。
- 现状锚点：`docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md` 后端功能 §1/§4。
- 必读源码：`packages/graph-agent/src/graph_agent/callbacks/events.py`、`packages/graph-agent/src/graph_agent/callbacks/emit.py`、`packages/graph-agent/src/graph_agent/callbacks/base.py`、`packages/graph-agent/tests/test_public_api_contract.py`。

## 3. 文件归属
- 本 WS owns：frontmatter `owns_files`。
- 禁止触碰：`packages/graph-agent/src/graph_agent/core/graph_assembler.py`、`packages/graph-agent/src/graph_agent/core/runner.py`、`packages/graph-agent/src/graph_agent/middleware/tracing.py`、`packages/graph-agent/src/graph_agent/middleware/tool_error.py`、`packages/graph-agent/src/graph_agent/middleware/loop_detection.py`。
- 边界说明：`callbacks/base.py` 只允许补默认 `Callback.on_event` 对新增 typed-only 事件的识别；不新增 legacy hook，不改变旧事件派发语义。

## 4. 现状锚点
当前 `CallbackEvent` 是 33 类 typed event 的 discriminated union；`trace.jsonl` 已能写任意可 `model_dump` 的 event。缺口是 V4 的 3 个边操作事件，以及 agent 内 LLM/tool 微观事件的 `parent_node_id` / `node_type` 契约。

## 5. 目标行为
- `LLMCallEvent` 和 `ToolCallEvent` 能携带 `parent_node_id: str | None` 与 `node_type: str | None`，用于把 agent 内微观事件挂回外层 phase。
- 新增 3 个边操作 typed event：
  - `BlackboardReduceEvent`：节点输出并入黑板。
  - `InputDispatchEvent`：黑板按 `io.inputs` 切片喂给目标节点；并联/iterate 每个分支各一条。
  - `InputFileInjectedEvent`：文件内容注入黑板字段。
- 三个边操作事件共享 edge 聚合字段：`from_phase`、`to_phase`、`changed_keys`、`blackboard_snapshot`。
- 三个边操作事件各自保留 alignment 指定的专有字段：`reducer`、`dispatched_keys`/`branch_index`、`file_ref`/`target_field`。
- 新事件进入 `CallbackEvent` union 和公共导出，能被 `TypeAdapter(CallbackEvent)` round-trip。
- `_TraceJsonlSink` 对新事件保持一行一 JSON object。
- 默认 `Callback().on_event(...)` 接受新事件，不记录 “unrecognised event type” warning。
- `tests/test_public_api_contract.py` 的 callback event public contract 必须包含新增事件。

## 6. 测试要求
- RED 必须覆盖新事件类存在、字段 schema、extra forbid、union round-trip、JSONL 写入。
- RED 必须覆盖 `LLMCallEvent` / `ToolCallEvent` 的 `parent_node_id` / `node_type` 字段，以及旧构造方式下两个字段默认 `None`。
- RED 必须覆盖默认 callback 对新 typed-only event 无 warning。
- RED 必须覆盖 public contract 期望列表包含新增事件，并覆盖 `graph_agent.callbacks.events.__all__` 公共导出包含新增事件类。
- 不写真实发射测试；真实 emit 接线属于后续 WS-E2 / graph-exec / io 工作。

## 7. 硬依赖约束
无实现依赖；本 WS 是后续 emit 接线的契约前置。

## 8. 验收标准
- [ ] RED 测试已写，并在当前 baseline 下失败。
- [ ] 失败原因是 V4 trace event schema/union/public contract 缺失，而不是夹具或环境错误。
- [ ] 未触碰 forbidden files。
- [ ] `uv.lock` 等运行副作用已恢复。

## 9. 不做
- 不实现真实 emit 接线。
- 不改 `graph_assembler.py` / `runner.py` / middleware 三个后槽文件。
- 不做 reducer authoritative 前后态 diff；alignment 已定为前端近似。
- 不改变 Prompt 三视图；现有 `PromptCapturedEvent` 已满足。

## 10. baseline 回写指令
实现落地后，按真实代码回写 `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md` 的事件数量、V4 边操作事件现状和微观字段现状。

## 11. 评审检查点
- 契约门：测试是否忠实编码 alignment §8 的 3 个边操作事件和微观拓扑字段，且没有偷偷要求真实 emit 接线。
- Codex 审查退出：§8 全满足。
- Claude 终审：事件契约是否足够给 Studio trace dot / 微观拓扑消费，baseline 是否只在实现后回写。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md
契约门通过后，Codex 据已批准的 RED 测试写 kiro `task.md`，并同步输出给 Gemini 的可复制实施 prompt。交接约束：
- 来源只能是已批准测试、`spec_ssot` 和本需求书，不凭空新增范围。
- `task.md` 使用 Phase 分段和 `- [ ]` 勾选项，每项挂 `_Requirements: WS-E4-v4-trace-events` 并写明验证命令。
- frontmatter 指回本需求书、alignment SSOT、`owns_files` 和 forbidden files；不得重写设计文档内容。
- 行号只允许作为执行者落地时重新核实的 grounding，不写成编辑坐标。
- 不写函数体、不写逐行 before/after、不指定具体实现步骤到代码级。
- Gemini prompt 必须包含工作区路径、分支、RED 命令/失败摘要、允许修改文件、禁止触碰文件、目标契约、验证命令和回报格式。
