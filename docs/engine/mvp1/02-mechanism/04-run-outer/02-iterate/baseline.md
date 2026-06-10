---
module: 02-mechanism/04-run-outer/02-iterate
doc: baseline
status: drafted（WS-E4 runtime 回写 2026-06-10:统一 `iterate` schema + 节点级 batch/range + 节点级 loop accumulate + 图级 batch/loop live;旧 `batch:` 兼容保留;WS-E5 已补 graph iterate 内 agent checkpoint namespace 组合;WS-E4 已接 branch dispatch 与 loop reduce trace;data-delta/compaction 仍归后续 WS）
---

# 02-iterate — Baseline(当下代码实现逻辑)

> **Scope**: 声明式循环的当前实现:phase-level `iterate` / legacy `batch`、graph-level `iterate`、range 切片、loop accumulate merge、iterate 专属错误码、graph iterate 与 AGENT checkpoint namespace 组合。
> **现状一句话**:WS-E1 Step4 已把 `iterate:{mode,over,item_var,range,concurrency,accumulate}` 落到 schema 与 runtime。节点级 batch/range、节点级 loop accumulate、图级 batch、图级 loop 都已能执行;旧 `batch:{iterator,item_var,concurrency}` 仍兼容并走新 batch 适配层。WS-E5 后,graph iterate 每轮执行期间会把当前 `iter{k}` 暴露给 AGENT 内层 checkpoint wrapper,使 agent checkpoint 写成 `iter{k}.agent:<phase>`。WS-E4 runtime 后,iterate 分支/轮次会在 phase input dispatch 事件上带稳定 1-based `branch_index`,声明式 loop accumulate merge 后会发 `BlackboardReduceEvent`;checkpoint data delta/compaction 仍不在当前现状。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. schema / compile
- 统一声明模型:`packages/graph-agent/src/graph_agent/core/manifest.py:IterateSpec`，字段为 `mode`、`over`、`item_var`、`range`、`concurrency`、`accumulate`。
- loop accumulator 模型:`packages/graph-agent/src/graph_agent/core/manifest.py:IterateAccumulateSpec`，字段为 `var`、`init`、`from`、`merge`，其中 `merge` 只接受 `append` / `extend` / `merge` / `replace`。
- `GraphManifest.iterate` 支持 `GRAPH.md` frontmatter 图级 iterate；phase AST 共享字段支持 `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 节点级 iterate。
- 旧 `BatchSpec` 保留，phase-level `batch:` 仍可解析。
- 编译期 loop 字段校验在 `loader.py:_validate_iterate_compile_contracts`:当 `iterate.mode=loop` 时，phase `io.inputs` 必须声明 `item_var` 与 `accumulate.var`，否则 fatal `[F-v3-iterate-accumulate-fields-missing]`。
- iterate 错误码已进 `ERROR_REGISTRY`:`[F-v3-iterate-accumulate-fields-missing]` 与 `[F-v3-iterate-over-not-list]`。

### 2. 节点级 batch + range
`graph_assembler.py:_build_iterate_wrapped_phase` 在 phase 有 `iterate` 时把已由 `PhaseWrapper(StateMapper)` 包好的 phase body 再套一层 iterate runtime。
- `mode=batch` 走 `_build_batch_iterate_phase`。
- `over` 通过 `_resolve_iterate_items` 从 `WorkflowState` 读取，非 list 报 `[F-v3-iterate-over-not-list]`。
- `range` 由 `_apply_iterate_range` 处理，语义是 1-based 闭区间；如 `[2,3]` 命中第 2、3 项。
- `concurrency` 用 `asyncio.Semaphore` 控制并发，`asyncio.gather` 保持结果顺序。
- 每项通过 `StateManager.update_business(... item_var=item)` 注入，再调用 phase body。
- 每项执行 phase body 前会设置 runtime branch contextvar,使 phase input dispatch 发出的 `InputDispatchEvent.branch_index` 为稳定 1-based 序号。
- 聚合按 phase `io.outputs` 的字段收集成 `field -> [per_item_value]`，并写回 business data 与 `phase_outputs[phase_id]`。
- 空 list 不调用 phase body，返回声明输出字段的空聚合。

### 3. 节点级 loop accumulate
`mode=loop` 走 `graph_assembler.py:_build_loop_iterate_phase`。
- 初始值来自 `accumulate.init`，每轮输入包含 `item_var` 与当前 `accumulate.var`。
- 每轮先调用 phase body，再从本轮输出取 `accumulate.from`。
- merge 语义由 `_merge_accumulator` 实现:
  - `append`: list accumulator 追加单个 piece。
  - `extend`: list accumulator 扩展 list piece。
  - `merge`: dict accumulator 合并 dict piece。
  - `replace`: 用 piece 替换 accumulator。
- 后一轮能读到前一轮累积结果；最终只把 `accumulate.var` 写回 blackboard 与 `phase_outputs[phase_id]`。
- 每轮 phase body 执行前的 input dispatch 带 1-based `branch_index`;每次 `_merge_accumulator` 后、累积值写回 `loop_state` 后发 `BlackboardReduceEvent`,事件携带 `reducer=accumulate.merge`、`changed_keys=[accumulate.var]` 和 merge 后 blackboard snapshot。
- 空 list 不调用 phase body，直接返回 `accumulate.init`。

### 4. legacy `batch:` 兼容
旧 `batch:{iterator,item_var,concurrency}` 不再走旧 `_build_batch_wrapped_node` 路径，而是经 `_build_legacy_batch_wrapped_phase` 转接到 `_build_batch_iterate_phase`。
- legacy `iterator` 等价于新 `iterate.over`。
- 为兼容旧测试与旧图输出，legacy batch 仍会写 `batch_outputs`。
- 旧 `data.<field>` iterator 在 graph 输入信封场景下有窄 fallback，可解析到 `data.inputs.<field>`。

### 5. 图级 batch / loop
当 `GRAPH.md` 声明 `iterate` 时，`assemble_graph` 会把编译好的 LangGraph 包成 `_GraphIterateRuntime`。
- `mode=batch` 走 `_run_graph_batch_iterate`:每个 item 执行一次整张 DAG，实例状态隔离，最终按 graph `io.outputs` 聚合。
- `mode=loop` 走 `_run_graph_loop_iterate`:同一外层 `graph.invoke` 内串行执行整张 DAG，多轮共享 accumulator，最终写回 `accumulate.var`。
- 每轮内部调用都会带 `checkpoint_ns=iter{k}` 风格 config；同时在 `flow.working_memory["iterate_executions"]` 暴露结构性信号，便于测试证明这是一次 graph.invoke 内部完成的图级迭代，而不是测试/runner 外层 N 次独立 invoke。
- graph-level batch/loop 在每轮执行内层 graph 时也设置 runtime branch contextvar,让内层 phase input dispatch 事件带稳定 1-based `branch_index`。graph-level loop 每次 graph 输出并入 accumulator 后会发 `BlackboardReduceEvent`,目标 phase 取 terminal phase(无 terminal 时为 `"output"`)。
- Step4 未接真实 checkpoint saver delta/compaction;WS-E4 runtime 只接入边操作 trace emit,不改 checkpoint storage。

### 6. WS-E5:graph iterate 与 AGENT checkpoint namespace
graph-level batch/loop 在调用内层 compiled graph 的每轮期间设置 `active_outer_ns="iter{k}"`,并在本轮结束后 reset。AGENT phase 的 `NamespaceCheckpointer` 写入 checkpoint 时读取这个 marker,把 agent namespace 组合成 `iter{k}.agent:<phase>`。这样同一 `thread_id` 下既能查询 graph iterate 轮次归属,也能区分 AGENT phase 内层 checkpoint;后续非 iterate AGENT checkpoint 不会泄漏上一轮 `iter{k}`。

## API
- `manifest.py:IterateSpec` / `IterateAccumulateSpec`。
- `loader.py:_validate_iterate_compile_contracts`。
- `graph_assembler.py:_build_iterate_wrapped_phase`。
- `graph_assembler.py:_build_batch_iterate_phase` / `_build_loop_iterate_phase`。
- `graph_assembler.py:_GraphIterateRuntime` / `_run_graph_batch_iterate` / `_run_graph_loop_iterate`。
- `graph_assembler.py:active_outer_ns` / `NamespaceCheckpointer` 的组合逻辑(与 `03-checkpoint`/`08-messages-state` 双向)。

## Data Model / State
iterate runtime 读写 `WorkflowState.data`。节点级 iterate 先让 `StateMapper` 对 phase body 做正常 io slice/merge，再由 iterate wrapper 聚合或累积结果写回 business data 与 `phase_outputs`。图级 iterate 包在 compiled graph 外层，按 graph `io.outputs` 取最终输出并聚合/累积。

## 当前边界(这个模块现在不是什么)
- **trace event emit 边界**:WS-E4 runtime 已接 `InputDispatchEvent` branch_index 与 `BlackboardReduceEvent`;仍没有 checkpoint data delta/compaction 事件,也没有 `InputFileInjectedEvent` 文件注入 emit。
- **没有 checkpoint data delta/compaction**:图级 loop 会传 `checkpoint_ns=iter{k}`,AGENT 内层会组合 `iter{k}.agent:<phase>`,但不改 `WorkflowState.data` reducer 或有界 accumulator。
- **没有 LangGraph `Send` 专门接线**:当前图级 batch 由外层 runtime fan-out 调用整图，契约上状态隔离并聚合输出。
- **没有子图 inputs 放宽**:SUBGRAPH io 仍是 Step5 范围。
- **没有 IO/read_file/Studio/gateway 改动**。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 配置 | `iterate` 已 live；旧 `batch` 兼容 | 统一 `iterate` 主契约，旧 `batch` 迁移期兼容 |
| 节点 batch | live，含 1-based 闭区间 range 与空 list 空聚合 | 对齐 |
| 节点 loop | live，显式 `accumulate{var,init,from,merge}` 串行累积 | 对齐基础 runtime |
| merge | append/extend/merge/replace live | 对齐 |
| 图级 batch | live，外层 runtime fan-out 整张 DAG 并聚合 | 目标提到 LangGraph `Send`，当前未用专门 Send API |
| 图级 loop=B | live 为一次 graph.invoke 内部串行 loop-body，带 `iter{k}` config 与结构性信号;AGENT 内层 checkpoint 保留 `iter{k}.agent:<phase>`;loop reducer 后发 `BlackboardReduceEvent` | data delta/compaction 仍后续 |
| 每轮 trace | phase input dispatch 带 1-based `branch_index`;loop accumulate 后发 `BlackboardReduceEvent` | 仍未引入 `phase_execution_id` 专用事件 |

> **验"是否按 mvp1 改了"**:① `iterate` schema 是否同时接受 phase 与 GRAPH frontmatter；② node batch `[2,3]` 是否按 1-based 闭区间命中第 2、3 项；③ loop 后轮是否读到前轮 accumulator；④ `over` 非 list 是否 `[F-v3-iterate-over-not-list]`；⑤ graph-level loop 是否能证明是单次 graph.invoke 内部 loop-body；⑥ AGENT 跑在 graph iterate 内时 checkpoint namespace 是否同时含 `iter{k}` 与 `agent:<phase>`。

## 读代码主路径提示
phase-level: `manifest.py:IterateSpec` → `loader.py:_validate_iterate_compile_contracts` → `graph_assembler.py:_wrap_phase_runtime_node` → `_build_iterate_wrapped_phase` → `_build_batch_iterate_phase` / `_build_loop_iterate_phase`。

graph-level: `GraphManifest.iterate` → `assemble_graph` → `_GraphIterateRuntime.invoke` → `_run_graph_batch_iterate` / `_run_graph_loop_iterate`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `01-contract/02-skill-syntax`(iterate 声明,双向)· `01-contract/03-compile-rules`(iterate 错误码)· `03-checkpoint`(loop 累积 checkpoint,双向)· `06-seam/02-observability`(每轮 trace 盖戳)· `05-run-inner/08-messages-state`
