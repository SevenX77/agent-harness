---
module: 11-io-and-edge-ops
doc: baseline
status: drafted
last_verified: 2026-06-03
aligns_with:
  - ../../../studio/mvp1/02_capabilities/trace-observability.md（dot = 节点间状态机操作）
  - ../../../studio/mvp1/02_capabilities/phase-editing.md（G2/G3 io 改动）
  - ../../../studio/_reorg/engine-prompt-trace-compile-debug.md（§三-1 dot 操作事件）
---
<!-- 核对进度:已迁 0 块 / 未迁 6 块 / 2026-06-04 -->

<!-- ⚠️ 未迁入（正式 graph-exec/observability 仅摘要，缺黑板切片覆盖表、子图 io 校验、artifact 落盘、边操作事件现状细节） → 应归入:02-mechanism/04-run-outer/01-graph-exec + 02-mechanism/06-seam/02-observability -->
# 11-io-and-edge-ops — Baseline(现状)

核心结论:**黑板字段切片、io.outputs artifact 落盘、子图 io 校验都已实现**。缺口 = ① 子图 io 严格 1:1 要放宽(G2);② 节点级文件导入→黑板(新运行时能力,G2/FROZEN-3);③ io.outputs artifact **路径标注扩展 + md 取 business_data_md 不回转**(G3);④ "节点间操作"(dot)需成系列 emit trace 事件(现只零散 Compaction/ArtifactSaved)。

<!-- ⚠️ 未迁入（正式 graph-exec/observability 仅摘要，缺黑板切片覆盖表、子图 io 校验、artifact 落盘、边操作事件现状细节） → 应归入:02-mechanism/04-run-outer/01-graph-exec + 02-mechanism/06-seam/02-observability -->
## 覆盖代码(含覆盖率)

覆盖率:100%。覆盖黑板切片、子图 io 校验、artifact 落盘、现有边操作事件。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| `StateMapper.build_phase_input`(用途:按 io.inputs 把全局黑板切成 phase 本地输入) | `runtime/state_mapper.py:44-75` | flatten 黑板(inputs+phase_outputs)→ `filter_runtime_inputs(raw, input_schema)` **按 io.inputs 切片**——FROZEN-4 引擎侧已成 |
| `StateMapper.wrap_phase_output`(用途:按 io.outputs 校验并并入黑板) | `runtime/state_mapper.py:77-121` | 节点输出 reduce/并入黑板 |
| `StateManager.update_business/update_framework` | `core/state.py:217-245` | 黑板写入原语 |
| 子图 io 严格 1:1 | `loader.py:528-556`(`_validate_subgraph_io_contracts`) | inputs+outputs 都 `parent_schema != child_schema` → `[F-v3-subgraph-io-mismatch]` fatal |
| io.outputs target 落盘 | `io/manager.py:139-195` | `target: file\|artifact` + `path` + `{context.key}` 占位;path-less file 默认 `runner.py:603` |
| `StorageManager.save_artifact` | `io/storage.py:149-196` | 写 `<run_dir>/phases/<phase>/<name>`(str/bytes 原样,else JSON)+ 发 `ArtifactSavedEvent` |
| 现有边操作事件 | `callbacks/events.py`(`ArtifactSavedEvent:315` / `CompactionEvent`) | artifact 落盘、截断/摘要已有事件 |
| 文件导入→黑板 | 无 | **缺**:运行中"跑到节点才把外部文件字段注入黑板" |

<!-- ⚠️ 未迁入（正式 graph-exec/observability 仅摘要，缺黑板切片覆盖表、子图 io 校验、artifact 落盘、边操作事件现状细节） → 应归入:02-mechanism/04-run-outer/01-graph-exec + 02-mechanism/06-seam/02-observability -->
## 编号执行流程(现状)

1. 进节点前:`StateMapper.build_phase_input` 把全局黑板按该节点 `io.inputs` 切片(`filter_runtime_inputs`),只喂声明的字段,见 `state_mapper.py:44-75`。**并联节点各自切片**就是 dot 处"输入筛选/分发"。
2. 出节点后:`wrap_phase_output` 按 `io.outputs` 校验并把输出并入黑板(reduce),见 `state_mapper.py:77-121`。
3. 终端节点 io.outputs 落盘:`io/manager` 按 `target`——`artifact`→`StorageManager.save_artifact`(发 `ArtifactSavedEvent`);`file`→写 `path`(或 `output_dir/{name}.json`),见 `io/manager.py:163-195`。
4. 子图节点:compile 期 `_validate_subgraph_io_contracts` 强制父 SUBGRAPH.md io == 子 GRAPH.md io,见 `loader.py:546-556`。
5. 截断/摘要:`CompactionEvent`(removed_summary + sidecar)已 emit。
6. **缺**:① 节点间"黑板 reduce/分发"操作没有专门事件(只有前后快照 PhaseStart/End.context);② 文件导入→黑板无机制。

<!-- ⚠️ 未迁入（正式 graph-exec/observability 仅摘要，缺黑板切片覆盖表、子图 io 校验、artifact 落盘、边操作事件现状细节） → 应归入:02-mechanism/04-run-outer/01-graph-exec + 02-mechanism/06-seam/02-observability -->
## Baseline / Alignment 差异

| 维度 | baseline | mvp1 目标 |
|---|---|---|
| 黑板切片(FROZEN-4) | ✅ StateMapper 已按 io.inputs 切 | 引擎侧无需改(前端 canvas 可视化另算) |
| 子图 io | 严格 1:1(inputs+outputs) | **放宽 inputs**:子图像任何节点从黑板按 io.inputs 过滤(G2/FROZEN-1) |
| 文件导入→黑板 | 无 | **新增**:跑到节点才注入(G2/FROZEN-3) |
| io.outputs artifact | target/path 已有 | **扩展**路径标注 + **md 取 business_data_md 不回转**(G3/FROZEN-2) |
| dot 操作事件 | 仅 Compaction/ArtifactSaved | **成系列**:黑板 reduce、输入分发、文件注入 都 emit(供前端点 dot 看完整操作) |

<!-- ⚠️ 未迁入（正式 graph-exec/observability 仅摘要，缺黑板切片覆盖表、子图 io 校验、artifact 落盘、边操作事件现状细节） → 应归入:02-mechanism/04-run-outer/01-graph-exec + 02-mechanism/06-seam/02-observability -->
## 代码索引(clues)

- `runtime/state_mapper.py:44-121`:黑板切片(输入)+ reduce(输出)。
- `core/state.py:217-245`:`StateManager` 黑板写入。
- `loader.py:528-556`:子图 io 1:1 校验(待放宽)。
- `io/manager.py:139-195`:io.outputs target 落盘。
- `io/storage.py:149-196`:`save_artifact` + `ArtifactSavedEvent`。
- `callbacks/events.py:315`:`ArtifactSavedEvent`(+ `CompactionEvent`)。

<!-- ⚠️ 未迁入（正式 graph-exec/observability 仅摘要，缺黑板切片覆盖表、子图 io 校验、artifact 落盘、边操作事件现状细节） → 应归入:02-mechanism/04-run-outer/01-graph-exec + 02-mechanism/06-seam/02-observability -->
## 待办/疑点

1. 子图 io 1:1 放宽只放 inputs 还是 outputs 也放——待 alignment 定(studio FROZEN-1 只点名 inputs)。
2. 文件导入→黑板是全新运行时能力,无现成代码。
3. dot 操作事件成系列 = 本关注点与 06-trace 的接合点(06 待办 #5 已登记)。
