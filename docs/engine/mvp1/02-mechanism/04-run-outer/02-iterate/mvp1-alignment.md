---
module: 02-mechanism/04-run-outer/02-iterate
doc: mvp1-alignment
status: drafted（**U11 单元锁定 2026-06-06**;iterate 执行模型(batch/loop/图级/嵌套/子图继承)+ 现状/目标 demarcate 已成段;声明语法收编 `skill-syntax §2.9`;loop/图级/range/统一 iterate 未实现归 kiro;文件未 FROZEN——02-iterate 还参与 U5/U7）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行外层）
---

# 02-iterate — 机制 B · 循环(运行外层)

> **Tier**: 机制层 B · 运行·外层 | **Owns**: 声明式 `iterate`(batch/loop,图级+节点级+嵌套)· 图级 loop = 引擎包 loop-body | **现状**: ⏳(只有节点级 batch live;loop/图级/range/统一 iterate = 目标,归 kiro) | **Related**: `skill-syntax`(iterate 声明)· `03-checkpoint`(loop 累积/续跑)· `05-run-inner/08-messages-state`

## 1. 定义
iterate = skill **声明的循环原语**:batch(并行 map)/ loop(回环),图级、节点级、嵌套。**图级 loop = B**:引擎是 DAG-only(用户画不出回边),整图自循环时**引擎把 DAG 包成 loop-body**、一个 thread 跑 N 遍(每遍 `ns=iter{k}`),非 runner 外层 N 次 invoke。

> **现状(2026-07-02 reconcile,以 `01-graph-exec/baseline.md` 为准)**:WS-E1 Step4/5 + WS-E4 后,声明式 iterate 已接入运行外层——**节点级 batch/range/loop**(`_build_iterate_wrapped_phase`/`_build_batch_iterate_phase`/`_build_loop_iterate_phase`)与**图级 batch/loop**(`assemble_graph` 把 compiled graph 包成 `_GraphIterateRuntime`)均 live;统一 `iterate:` 声明生效(legacy `batch:` 经 `_build_legacy_batch_wrapped_phase` 接新 runtime);loop accumulate merge 后发 `BlackboardReduceEvent`、分支以 1-based `branch_index` 区分(WS-E4)。**仍未落**:checkpoint 深集成(loop 每轮 super-step 存档与 blackboard delta 协同)、`Send` 专门接线、每轮 trace 盖 `phase_execution_id` 的完整覆盖——见 §8 存留项。本条 2026-07-02 按代码 reconcile:旧文"只有节点级 batch live"的警告已过时,删除;细节以 graph-exec baseline 双向引用为准。

## 2. 数据流 / 机制
声明语法(`iterate:{mode, over, item_var, range, concurrency(batch), accumulate(loop)}`)归 `skill-syntax`(契约);本域是**执行机制**——四形态 + 嵌套 + 子图继承:
- **节点级 batch**(并行 map):`_build_batch_wrapped_node`(把一个 phase 对一组输入并发跑再聚合的包装器)+ range 切片;`asyncio.Semaphore(concurrency)` 控并发、按 `item_var` 注入每项、`asyncio.gather` 收集,聚合成 `aggregated_data[字段]=[各项值]`(现状 `graph_assembler.py:240-284`)。
- **节点级 loop**(已落 `_build_loop_iterate_phase`;串行累积,累积变量由作者**显式声明**、引擎不猜):`acc=accumulate.init`;`for item in over[range]`:跑 `run_unit(黑板 ∪ {item_var:item} ∪ {accumulate.var:acc})` → `acc=merge(acc, out[accumulate.from])`(merge ∈ append/extend/merge/replace)→ **每轮 checkpoint**;末轮写回 `{accumulate.var:acc}`。loop 节点 `io.inputs` 必含 `item_var`+`accumulate.var`(编译可校验,见 §3)。
- **图级 batch**(已落 `_GraphIterateRuntime` 整图 batch;`Send` fan-out 专门接线仍为目标):并行 N 遍、各遍隔离,受图级全局并发闸。
- **图级 loop = B**(已落 `_GraphIterateRuntime` 整图 loop;引擎包 loop-body):引擎把整张 DAG 包成 loop-body、**注入回边**(DAG-only,`[F-v3-graph-phase-cycle]` 禁环 → 用户画不出回边),**同一 thread** 串行 N 遍、每遍 `ns="iter{k}"`;整体回灌 = 取上一轮**全部节点 outputs** 汇成 dict 当下一轮累积输入(merge:replace)。
- **嵌套**:图级走到一个设了节点级 iterate 的节点,先跑完节点级再继续(总次数 = 图级 × 节点级)。**子图继承**:`SUBGRAPH.md` 上的 iterate 由父图用来迭代调子图,子图本身跑 1 遍。
- **每轮 trace 归属**(多轮不丢):loop/batch/图级每轮、resume 每次,执行器给该轮所有事件盖 `phase_execution_id`(本次节点整体执行的实例 id,前端按它分组成"轮")+ `iteration_index`/`source`——否则前端按节点看 trace 只剩最近一次。⚠️ 现 batch 并发跑+聚合未盖 item 维度 → 100 项 trace 全糊在同一 `phase_name` 下,须给每项补盖(归 `02-observability`,双向)。
- loop 累积与 debug 续跑**共用一套节点级 checkpoint**:每轮 = 嵌套子图的一个 super-step(LangGraph 每个 super-step 自动存档),`accumulate.var` 写在黑板 state 里本就被 checkpoint(归 `03-checkpoint`,双向)。

## 3. 接口契约
`iterate` 声明(语法在 skill-syntax)→ 引擎包 loop-body 的编译/执行契约;loop 累积状态 ↔ `03-checkpoint`;loop 节点 `io.inputs` 必含 `item_var`+`accumulate.var`(编译校验 `[F-v3-iterate-*]`,归 compile-rules)。

## 4. 设计决策基础(用户原话)
> 图级 loop 选 B(state-checkpoint):"我也选B"。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| IT1 | 图级 loop = **B**(引擎包 loop-body,一 thread + ns/iter) | DAG-only 唯一"一套 base"形态;与 subgraph-loop 同构 |
| IT2 | loop 累积与 debug 续跑共用一套节点级 checkpoint | 一套状态机,避免两套混写 |

## 6. 测试关键点
1. 图级 iterate → 引擎包 loop-body(一 thread + ns=iter{k}),非 N 次独立 invoke。
2. loop 累积 checkpoint 总体积 O(N)(与 `03-checkpoint` blackboard delta 协同)。

## 7. 涉及 region / platform
engine 全权。

## 8. gaps / 待设计(2026-07-02 按代码 reconcile:原 1-5 已由 WS-E1 Step4/5 落地并删除)
**已落地(见 `01-graph-exec/baseline.md` §3,双向)**:节点级 batch/range/loop、图级 batch/loop(`_GraphIterateRuntime`)、统一 `iterate:` 声明(legacy `batch:` 走兼容包装)、`[F-v3-iterate-accumulate-fields-missing]`/`[F-v3-iterate-over-not-list]` 已进 `ERROR_REGISTRY`。

**存留项**:
1. checkpoint 深集成:loop 每轮 super-step 存档与 blackboard delta 协同(归 `03-checkpoint`,双向)。
2. `Send` fan-out 专门接线(图级 batch 现为 `_GraphIterateRuntime` 内部执行,非 `Send` 原语)。
3. 每轮 trace 盖 `phase_execution_id`+`iteration_index` 的完整覆盖(WS-E4 已给分支 `branch_index`;batch 并发 item 维度补盖归 `02-observability`,双向)。

**待设计(非纯实现)**:
7. `parallel_map`(batch)× 6 槽中间件链(断层#3,与 `04-tools`/`02-middleware` 协同)。
8. delta snapshot 频率 N(实测定,messages 现 50)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `01-contract/02-skill-syntax`(iterate 声明,双向)· `03-checkpoint`(双向)· `05-run-inner/08-messages-state` · `06-seam/02-observability`(每轮 trace 盖戳,双向)· 代码现状 `core/graph_assembler.py:240-299`(节点级 batch + 接线点)
