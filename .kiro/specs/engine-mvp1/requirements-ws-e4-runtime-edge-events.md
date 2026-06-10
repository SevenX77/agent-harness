---
ws_id: WS-E4-runtime-edge-events
modules:
  - 02-mechanism/06-seam/02-observability
  - 02-mechanism/04-run-outer/01-graph-exec
  - 02-mechanism/04-run-outer/02-iterate
  - 03-api-contract
depends_on:
  - WS-E4-v4-trace-events
  - WS-E1-io for InputFileInjectedEvent runtime path
blocks: []
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e4-runtime-edge-events.md
  - packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py
  - packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/src/graph_agent/runtime/state_mapper.py
spec_ssot:
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md §3/§5/§8
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md 后端功能 §1/§4/§5
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md §2/§3/§5/§8
  - docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md §2/§3/§5/§7
  - docs/engine/mvp1/03-api-contract/mvp1-alignment.md §2.2/§3.2
status: drafted
---

# WS-E4 Runtime Edge Events — 需求书

## 1. 目标
把已经落地的 V4 edge event schema 接到真实 engine runtime emit 点，让节点输入分发、声明式 reducer/accumulate、以及文件 lazy 注入这些运行时事实进入通用 callbacks 和 `trace.jsonl`。本 WS 只做 engine runtime observability，不把 Studio canvas 展示 DTO 写进事件。

## 2. SSOT 指针
- 目标机制：`docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md` §3/§5/§8。
- 运行起点：`docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md` 后端功能 §1/§4/§5。
- graph-exec 目标：`docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md` §2/§3/§5/§8。
- iterate 现状：`docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md` §2/§3/§5/§7。
- API 事件协议：`docs/engine/mvp1/03-api-contract/mvp1-alignment.md` §2.2/§3.2。
- 已落地 schema 契约：`docs/engine/mvp1/_impl/requirements-ws-e4-v4-trace-events.md` 与 `.kiro/specs/engine-mvp1/task-ws-e4-v4-trace-events.md`。
- 必读源码：`packages/graph-agent/src/graph_agent/core/graph_assembler.py`、`packages/graph-agent/src/graph_agent/runtime/state_mapper.py`、`packages/graph-agent/src/graph_agent/callbacks/events.py`、`packages/graph-agent/src/graph_agent/callbacks/emit.py`、`packages/graph-agent/src/graph_agent/callbacks/base.py`。

## 3. 文件归属
- 本 WS owns：frontmatter `owns_files`。
- 禁止触碰：`apps/studio/**`、`packages/graph-agent-gateway/**`、错误 V2 registry/API、resume/golden、checkpoint storage 语义、WS-E1-io 的 file import/artifact 业务语义。
- `callbacks/events.py` 当前已包含三类 V4 edge event；本 WS 默认不 owns 它。若契约门发现 schema drift，必须先回到 PM 审查再扩大 owns。
- `callbacks/emit.py` 当前通用 JSONL sink 已可写任意 Pydantic event；本 WS 默认不 owns 它。只有 trace sink/serialization 的 RED 证明需要时，才能在契约门后扩大 owns。
- `graph_assembler.py` 与 WS-E1-io 潜在冲突。requirements + RED 可先并发；生产实现必须等待 WS-E1-io 合并，或明确建立 stacked branch 并在汇报里写清 base。

## 4. 现状锚点
V4 edge event schema、union、默认 callback typed-only 识别和 JSONL 泛化能力已落地；baseline 明确记录真实 `BlackboardReduceEvent` / `InputDispatchEvent` / `InputFileInjectedEvent` runtime emit 尚未接入。

## 5. 目标行为
- 当 phase 输入从 blackboard 依照 `io.inputs` 切片并交给节点前，runtime 必须发出 `InputDispatchEvent`。事件描述本次分发的 engine 事实：来源 phase、目标 phase、分发 key、触及 key、分发时的 blackboard snapshot；入口分发的 `from_phase` 可为空。
- 串行图中，每个真实执行的 phase 都要有对应 `InputDispatchEvent`；事件不得只覆盖最后一个节点。
- 声明式 iterate / batch / loop 中，每个实际执行的分支或轮次都要有自己的 `InputDispatchEvent`。分支序号必须稳定，可让 consumer 区分同一 phase 的多次分发；非分支执行可为空。
- 当声明式 accumulate/reducer 操作把分支或轮次结果合并回 blackboard 时，runtime 必须发出 `BlackboardReduceEvent`。事件包含 reducer 名、触及 key、操作后的 blackboard snapshot；不要求 engine 计算 authoritative before/after diff。
- 当 WS-E1-io 的文件 lazy 注入路径落地后，文件内容注入 blackboard 字段时必须发出 `InputFileInjectedEvent`，并包含文件 ref、目标字段、触及 key 和注入后的 blackboard snapshot。
- 所有新增 runtime emit 必须走通用 callback/event sink，并自然落入 `trace.jsonl` 一行一个 typed event。
- 不新增 Studio-only 字段；若 Studio 想要的字段不是通用 engine runtime 事实，本 WS 不接。

## 6. 测试要求
- RED 必须用真实 compiled graph/runtime 执行，不只手工实例化 event class。
- RED 必须覆盖普通串行图：每个 phase 执行前都有 `InputDispatchEvent`，字段包含 `from_phase`、`to_phase`、`dispatched_keys`、`changed_keys`、`blackboard_snapshot`，且 callback subscriber 收到 typed event。
- RED 必须覆盖 `trace.jsonl`：同一真实 run 的 edge event 能以一行一个 JSON object 读回，并保留 `event_type`。
- RED 必须覆盖并联或 iterate 分支：同一 phase 的每个分支/轮次都有 `InputDispatchEvent`，并带稳定 `branch_index` 或等价语义，不能只发最近一次。
- RED 必须覆盖声明式 accumulate/reducer：发生 reducer 操作时发 `BlackboardReduceEvent`，包含 reducer 名和 changed keys，snapshot 是操作后 blackboard。
- 文件注入 RED 受 WS-E1-io 依赖门约束：当前代码尚无 file lazy injection path 时，只记录依赖未满足和未来必须覆盖的失败点；不得在本 WS 抢做 IO 声明、read_file、artifact 或 state 业务语义。
- 不要求 Studio UI 渲染，不测 canvas。

## 7. 硬依赖约束
- `InputDispatchEvent` 与 `BlackboardReduceEvent` 的 RED 可在当前 base 上先写并失败。
- `InputFileInjectedEvent` 的真实 run RED 必须等 WS-E1-io 提供 file lazy injection path 后再启用；当前阶段只允许契约记录和依赖门。
- 未过契约门前，不写实施任务书、不写 Gemini prompt、不实现生产代码。

## 8. 验收标准
- [ ] requirements 文件存在且 owns_files 与禁止触碰范围清楚。
- [ ] RED 测试已写，并在当前 baseline 下失败。
- [ ] 失败原因是 runtime edge events 未接入真实 emit 或 WS-E1-io 文件注入依赖未落地，而不是夹具、导入或环境错误。
- [ ] 未触碰生产代码。
- [ ] 未触碰 forbidden files。
- [ ] `uv.lock` 等运行副作用保持干净。

## 9. 不做
- 不做 Studio UI、canvas、gateway 或 WebSocket DTO。
- 不新增或扩展 event schema 字段，除非契约门先确认 schema drift。
- 不做 reducer authoritative before/after diff。
- 不实现 WS-E1-io 的 file lazy injection、read_file、artifact、runner/io/storage 业务语义。
- 不改错误 V2 registry/API、resume/golden、checkpoint storage 语义。

## 10. baseline 回写指令
实现落地且 GREEN 后，按真实代码回写：
- `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md` 的 V4 runtime edge emit 现状。
- `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md` 中 StateMapper/phase input dispatch 与文件注入相关现状；若目标 baseline 文件仍不存在，先在汇报里标明无法回写的原因。
- `docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md` 的 accumulate/reducer trace emit 现状。

## 11. 评审检查点
- 契约门：RED 是否忠实编码 engine runtime 事实，是否误把 Studio 展示需求写进事件，是否越界抢 WS-E1-io。
- Codex 审查退出：§8 全满足，且实现阶段遵循文件锁/stacked base。
- Claude 终审：runtime emit 是否真实、baseline 是否诚实、测试是否非假绿。

## 12. 给 Codex 的交接：按写作规范写 kiro task.md
契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/engine-mvp1/task-ws-e4-runtime-edge-events.md`，并同步输出给 Gemini 的可复制 prompt。交接约束：
- 来源只能是已批准测试、`spec_ssot` 和本需求书。
- `task.md` 使用 Phase 分段与 `- [ ]` 勾选项，每项挂 `_Requirements: WS-E4-runtime-edge-events` 并写明验证命令。
- frontmatter 指回本需求书、alignment SSOT、owns_files、forbidden files 和 stacked/base 状态。
- 不跑 `/kiro:spec-tasks`，不重写设计。
- 如果 WS-E1-io 仍未落地，task/Gemini prompt 不得包含 `InputFileInjectedEvent` 生产实现步骤，只能保留依赖门说明。
