---
module: 11-io-and-edge-ops
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-03
aligns_with:
  - ../../../studio/mvp1/02_capabilities/{trace-observability,phase-editing}.md
  - ../../../studio/_reorg/engine-prompt-trace-compile-debug.md（§三-1）
---

# 11-io-and-edge-ops — MVP1 Alignment(目标设计)

MVP1 目标:把"节点之间的黑板/IO 操作"收口成一组明确能力 + 让它们都可观测(dot 内容)。4 件:① 放宽子图 io 1:1;② 文件导入→黑板(跑到节点才注入);③ io.outputs artifact 路径标注扩展 + md 取 business_data_md;④ 边操作 trace 事件成系列。复用 StateMapper/StorageManager,**黑板切片(FROZEN-4)引擎侧已成,不改**。

## 1. 子图 io 去 1:1（G2/FROZEN-1）

- **现状**:`loader.py:546-556` 对 inputs+outputs 都强制 `parent==child`,否则 `[F-v3-subgraph-io-mismatch]`。
- **目标**:**删 inputs 侧的相等强制**——子图节点像任何 phase 一样,用自己声明的 `io.inputs` 经 `StateMapper.build_phase_input` 从黑板切片(机制已现成)。子图不必声明和子 GRAPH.md 完全一致的 inputs。
- **outputs 侧**:暂保留相等校验(子图输出契约仍需对齐,否则下游取不到)——除非 PM 要求一并放宽(studio FROZEN-1 只点名 inputs)。**决策:只放 inputs,outputs 保留**(见 §5)。
- 落点:`loader.py:546-556` 改为只校验 outputs;inputs 不再比对。

## 2. 文件导入→黑板（G2/FROZEN-3,新运行时能力）

- **语义**:任意节点可声明"导入某文件 → 把其字段注入黑板",**时机 = 跑到该节点时才注入**(不是图启动就注入)。
- **设计**:节点(io 配置)上声明 import（文件路径 + 注入字段映射）;运行到该节点前,引擎读文件 → 经 `StateManager.update_business(state, **fields)` 把字段写进黑板 → 再 `StateMapper.build_phase_input` 切片。
- **落点**:在 `_wrap_phase_runtime_node`(节点执行包装)进节点前加"文件注入"步;复用现有 `read_file` 工具的读路径 + `StateManager` 写黑板。
- **发事件**:`InputFileInjectedEvent`(见 §4),让 dot 能看到"这里注入了哪个文件的哪些字段"。
- **D12 边界**:文件读经引擎(Python sidecar),注入写黑板是内存态;若需落盘走 Rust。

## 3. io.outputs artifact 扩展（G3/FROZEN-2）

- **现状**:`io/manager.py` 已支持 `target: file|artifact` + `path`;`save_artifact` 写盘 + 发 `ArtifactSavedEvent`。
- **扩展**:
  1. **路径标注更丰富**:io.outputs schema 顶层可标文件路径(`xx/xx.json|md`);支持一 schema 落多文件 / 多 schema 各落;**只写文件名 → 默认 `.workspace/artifacts`**(现 path-less file 默认已近似,`runner.py:603`)。
  2. **md 源 = validated `business_data_md`,不做 json→md 回转**:当输出标 `.md` 时,直接取 finish_task 校验后保留的 `business_data_md`(`cognitive_flow.py` 保留点),**不**把已解析的 JSON 再序列化回 md。现 `save_artifact` 对 str 原样写(`io/storage.py:167`)——把 business_data_md 作为 str 喂进去即可,机制现成,关键是**接线取 business_data_md 而非 parsed json**。
- **落点**:`io/manager.py` 输出落盘处按 schema 路径标注选 file/artifact + 文件名;md 输出从 business_data_md 取值。

## 4. 边操作 trace 事件成系列（dot 内容,接 06-trace 待办#5）

dot = "上节点 end→下节点 start 之间全部操作"。现仅 `ArtifactSavedEvent`/`CompactionEvent`。**补**:
- `BlackboardReduceEvent`:节点输出并入黑板(`wrap_phase_output` 处)——哪些 key 被写/覆盖。
- `InputDispatchEvent`:黑板按 io.inputs 切片喂节点(`build_phase_input` 处),**并联节点各发一条**(对应"并联输入统一筛选/分发")。
- `InputFileInjectedEvent`:§2 文件注入。
- 已有 `ArtifactSavedEvent`(落盘)、`CompactionEvent`(截断/摘要)纳入同一"边操作"族。
- 前端点 dot → 按 `from_phase`/`to_phase`(或 edge id)聚合这一族事件 + 该刻黑板快照(PhaseEnd[A].context),组成"完整操作记录"。
- reducer 级前后态 diff(REQ-7)单列(06 待办#6),本块先把操作事件发全。

## 5. 决策

| # | 决策 | 结论 |
|---|---|---|
| E1 | 子图 io 放宽范围 | 只放 **inputs**(从黑板切片);outputs 保留相等校验 |
| E2 | 文件注入时机 | 跑到该节点才注入(lazy),非图启动注入 |
| E3 | md artifact 来源 | validated `business_data_md` 原样写,不 json→md 回转 |
| E4 | 黑板切片(FROZEN-4) | 引擎侧已成(StateMapper),本块不改;前端 canvas 可视化另算 |
| E5 | dot 事件粒度 | 黑板 reduce / 输入分发(并联各一条)/ 文件注入 各发事件,聚合按 edge |

## 6. FROZEN 解冻清单

1. `04-subgraph-md-spec`:删 inputs 1:1 强制(只留 outputs);`loader.py:546-556` 同步。
2. `02/03/05` io.outputs:加 artifact 路径标注(`xx/xx.json|md`,一/多文件,filename-only 默认 .workspace/artifacts);md 取 business_data_md。
3. 节点 io 配置加 file-import 声明(文件路径 + 字段映射)。
4. `callbacks/events.py` + trace 契约:新增 `BlackboardReduceEvent`/`InputDispatchEvent`/`InputFileInjectedEvent`。
5. workspace-spec:确认顶层 `artifacts/`(已在 §3.1 runs/<id>/artifacts/;G3 顶层 artifacts/ 待补)。

## 7. 已实现 / 与 baseline 差异

- 已实现(复用):黑板切片(StateMapper)、io.outputs target/path 落盘、StorageManager+ArtifactSaved、Compaction、read_file 读路径、StateManager 写黑板。
- 未实现:子图 inputs 放宽、文件导入→黑板、artifact 路径标注扩展+md 取 business_data_md、3 个边操作事件。

## 8. 待办/疑点

1. 待办(TDD 先行):放宽子图 inputs(改 loader)+ 文件导入→黑板(_wrap_phase_runtime_node 前置步)+ artifact 路径标注/md 取值 + 3 个边操作事件。
2. 疑点:文件导入的"字段映射"声明形态(整文件当一个字段 vs 文件内字段展开)——实现期定。
3. 关联:dot 事件供 06-trace 渲染;reducer diff(REQ-7)在 06 待办#6 单列。
