---
module: 10-iteration-and-resume
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-03
decisions_locked: 2026-06-03（fork F1-F5）
aligns_with:
  - ../../../studio/mvp1/02_capabilities/{run-execution,debug-resume}.md
  - ../../../studio/_reorg/{gemini-prompt-batch-loop,engine-prompt-trace-compile-debug}.md
design_draft: ../../../../temp/2026-06-03-batch-loop-resume-engine-design.md
---

# 10-iteration-and-resume — MVP1 Alignment(目标设计)

MVP1 目标:声明式 `iterate`(batch 并发 / loop 串行累积,图级 + 节点级 + 嵌套)+ **统一的节点级 checkpoint/状态机**(loop 累积 与 debug 续跑共用一套,engine-prompt 铁律)+ 实现 `resume_run`(节点级 + context 篡改 + HitL 注入)。复用现 `batch_spec`/checkpointer,不从零。

## 0. fork 决策(2026-06-03 锁)

- **F1** loop 累积态 = **显式声明**(作者声明累积变量/初值/来源/合并,引擎不猜、不糊整黑板)。
- **F2** 图级 loop 整体回灌 = 认可(上一轮所有节点 outputs 汇成 dict 当下一轮累积输入)。
- **F3** 迭代粒度 = 各 scope 各自声明 `over`(顶层 range 只切顶层,不往深层传)。
- **F4** = 默认显式 `over`,自动探测仅作规整序列建议。
- **F5** = 复用并发 semaphore + 图级全局并发闸。

## 1. 统一配置 `iterate`(扩现 batch_spec,向后兼容)

```yaml
iterate:
  mode: batch | loop
  over: <字段路径>                # = 现 iterator；F4 默认显式
  item_var: <注入名>
  range: [start, end]             # predict 默认 [1,1]，run 默认全量
  concurrency: N                  # 仅 batch
  accumulate:                     # 仅 loop（F1 显式）
    var: <累积变量名>; init: []; from: <本轮输出字段>; merge: append|extend|merge|replace
```
- **scope = 写在哪**:节点文件=节点级 / `GRAPH.md`=图级 / `SUBGRAPH.md`=子图继承级(不写进子图自身 GRAPH.md)。
- batch = 现 `_build_batch_wrapped_node` + range;`batch_spec` 即 `mode:batch`(兼容)。

## 2. loop 累积语义(F1 显式)

```
acc = accumulate.init
for item in over[range]:                              # 串行 + range 切片
    out = run_unit(黑板 ∪ {item_var:item} ∪ {accumulate.var:acc})
    acc = merge(acc, out[accumulate.from])            # append/extend/merge/replace
    checkpoint(iteration_index, acc)                   # 每轮存档(§4 统一底座)
写回 {accumulate.var: acc} + 末轮 out
```
- loop 节点的 `io.inputs` **必须含 `item_var` 和 `accumulate.var`**(显式契约,编译可校验)。
- 例(event-timeline):`over:data.events`、`item_var:current_event`、`accumulate:{var:timeline,init:[],from:merged_segment,merge:append}`。

## 3. 执行模型(4 种 + 嵌套 + 子图)

- 节点级 batch:现成 + range。
- 节点级 loop:`_wrap_phase_runtime_node` 加 loop 分支(§2)。
- 图级 batch:并行 N 遍(`Send` fan-out / 各遍隔离),受 F5 全局闸。
- 图级 loop:**引擎把整张 DAG 包成 loop-body(决策 B)**——一次执行 + 引擎注入回边,串行 N 遍、每遍 `ns="iter{k}"` 在**同一 thread**;整图输出按 accumulate 喂下一遍(**整体回灌 F2 mode② = 取上一轮全部节点 outputs dict,merge:replace**)。DAG-only(`[F-v3-graph-phase-cycle]`)下回边**由引擎注入,非用户画**。详见 `records/state-checkpoint-storage-model §2.3`。
- 嵌套(B4):图级进程走到设了节点级 iterate 的节点,先跑完节点级再继续(次数=图级×节点级)。
- 子图继承(B5):SUBGRAPH.md 上的 iterate 由父图用来迭代调子图,子图本身跑 1 遍;子图 GRAPH.md 也设则嵌套。
- **每轮 trace 归属(2026-06-03 PM 定,多轮不丢)**:loop/batch/图级 每轮、resume 每次,执行器都要给该轮所有事件盖 **`phase_execution_id`**(执行实例,前端按它分组)+ `iteration_index`/`source`——否则前端按节点看 trace 会丢轮次(只剩最近一次)。**⚠️ 现 `_build_batch_wrapped_node` 并发跑 + 聚合,事件没盖 item 维度 → 100 项 trace 全糊在同一 `phase_name` 下、丢归属,必须给每项补 `phase_execution_id` + `iteration_index`**。事件字段定义见 `06-trace-observability` 待办#9;层级 = `phase_name` → `phase_execution_id`(轮)→ 轮内 turns。

## 4. 统一 checkpoint / 状态机 + resume(engine-prompt 铁律:不要两套)

> **C2 机制已闭环(2026-06-03)** —— 不再留"实现期对齐"。**权威机制 = `records/state-checkpoint-storage-model`;本节是它在 iteration/resume 上的应用,不复制。** 核心:**唯一 base = LangGraph 的"每 super-step 一存"thread checkpoint**;节点级、loop 每轮、图级每遍、**以及 agent loop**,都映射成 super-step、靠 `checkpoint_ns` 嵌套区分,绝不另起自管 store(那才是两套)。
> 已核证据:① 每 phase = 一个 `builder.add_node`(`graph_assembler.py:106-151`),即一个 super-step;② langgraph 1.2.2 支持 `checkpoint_ns`(嵌套命名空间)+ `get_state_history`/`get_state`(历史寻址)+ `Send`(并行 fan-out)。

- **唯一底座**:LangGraph thread checkpoint(`compile(checkpointer=...)`,`graph_assembler.py:151`)。"存状态以便续/迭代"本质同源 → 同一套 saver、同一个 thread、靠 `checkpoint_ns` 分层。
- **节点级(= debug 续跑,LangGraph 原生)**:phase=节点=super-step,每步自动存档。"从节点 X 续、1..X-1 不重跑" = `get_state_history(thread_id)` 定位 X-1 后的 checkpoint → 带 `checkpoint_id` 重 invoke。**无需新机制**。
- **loop 每轮(关键:建模成 super-step,不自管 key)**:loop body 编译成**嵌套子图 + 回灌边**,每轮 = 该子图一个 super-step,LangGraph 在 `checkpoint_ns="<phase_id>"` 下原生为每轮存档;累积变量 `accumulate.var` 写在黑板 state 里,**本就被 checkpoint**。→ 与节点级**同一 base**,resume 到"第 N 轮" = 该 ns 下 super-step N 的 checkpoint。**(否决:node 内 asyncio 循环自管 per-iteration store —— 那是第二套。)**
- **batch(与 loop 不同形态)**:并行独立 → 用 `Send` fan-out(每 item 一个并行 task),非 loop 的串行子图。batch 每 item 是否单独 checkpoint 为次要(并行独立,失败可整组或仅失败项重跑);loop 才是必须逐轮可续。
- **图级迭代每遍**:整图跑 N 遍,每遍 = `checkpoint_ns="iter{N}"` 下一组 super-step,**仍同一 thread**(否决独立 sub-thread,见 §8.2 收口)。
- **`resume_run` 寻址契约**(闭 api 契约 §4):`resume_run(run_id, from=<node_id> | <node_id>:<iter_index>, context_overrides?)` → `get_state_history` 列档 → 选 `checkpoint_id`(+ `checkpoint_ns`)→ `update_state` 套 `context_overrides`(场景C 篡改黑板)/ 注入 `ToolMessage`(场景A HitL)→ 带该 checkpoint 重 `invoke`。
- **内层 agent loop 也经 `checkpoint_ns` 挂进同一 checkpointer(不另起 saver 实例)**:agent loop 每 model/tool 步在 `ns="<phase_id>/agent"` 下存档,使 **mid-conversation HITL/interrupt 续跑成立**(`interrupt()` 依赖 checkpoint,`cognitive_flow.py:292`);命名空间隔离即解 uncovered-areas #3 的"内层污染外层"。**(纠正前稿"内层不 checkpoint"——那样人类打断对话后无从续。)权威机制见 `records/state-checkpoint-storage-model §2.2`。**
- **失效追踪(脏状态)**:上游/拓扑/输出 schema 改 → 标下游 checkpoint 失效(前端 [Resume] 置灰)——归 **C3 统一"变更→失效"模型**,不在此自定义。
- **range 起点 + 续跑**:`range.start=50` + 复用已有 checkpoint(载到 iter 49)= 接着跑;不复用 = 从 start。
- **必须 D-test(承 uncovered-areas #3)**:嵌套子图在父 thread 下按 `checkpoint_ns` 逐 super-step 存档、且 `get_state_history` 能跨 ns 寻址续跑 —— 在 langgraph 1.2.2 + 我们的 GatewayChatModel 下实测成立(这是"统一一套"成立的唯一实证前提)。

## 5. 决策表

| # | 决策 | 结论 |
|---|---|---|
| F1 | loop 累积 | 显式声明 `accumulate{var,init,from,merge}` |
| F2 | 图级 loop 回灌 | 上一轮全部节点 outputs dict,merge:replace |
| F3 | 迭代粒度 | 各 scope 各自 `over`,顶层 range 不下传 |
| F4 | over 来源 | 默认显式;自动探测仅建议 |
| F5 | 并发 | 复用 semaphore + 图级全局闸 |
| C1 | checkpoint | loop 累积与 debug 续跑**统一一套**(engine-prompt 铁律) |
| C2 | 统一机制(2026-06-03 闭环) | 唯一 base = LangGraph super-step thread checkpoint;节点/loop轮/图级遍 都映射 super-step,靠 `checkpoint_ns` 嵌套;**不**另起 node 自管 store。resume = `get_state_history`+`checkpoint_id/ns`+`update_state`。内层 create_agent 不带自己 checkpointer。需 D-test(嵌套 ns 寻址) |

## 6. FROZEN 解冻清单

1. skill-spec `02-graph`(图级)+`03-logic`/`05-agent`(节点级)+`04-subgraph`(继承):加 `iterate` 字段(兼容 `batch`)。
2. 新校验:loop 节点 `io.inputs` 必须含 `item_var`+`accumulate.var`。
3. 新错误码:`[F-v3-iterate-accumulate-fields-missing]`、`[F-v3-iterate-over-not-list]`;resume/失效相关码与 `11-error-code-spec` 对齐。

## 7. 已实现 / 与 baseline 差异

- 已实现(复用):节点级 batch、checkpointer 工厂、run 级 thread + 续跑开关、HitL 原语。
- 未实现:loop 执行器、图级迭代层、统一节点级 checkpoint、`resume_run`、失效追踪、子图继承、iterate spec/校验。

## 8. 待办/疑点

1. 待办(TDD 先行):统一 iterate AST/spec + 编译校验、loop 执行器、图级迭代层、resume_run+overrides+失效、子图继承。
2. ~~疑点:图级迭代每遍独立 sub-thread vs 共享 thread~~ → **已闭环(C2)**:共享 thread + `checkpoint_ns="iter{N}"`,不开独立 sub-thread(统一 base)。
3. ~~疑点:节点内 loop 的 per-iteration checkpoint key 与 LangGraph thread checkpoint 的关系~~ → **已闭环(C2,见 §4)**:loop 建模成嵌套子图,每轮 = `checkpoint_ns="<phase_id>"` 下一个 super-step,即 LangGraph 原生 checkpoint,非自管 key。待 D-test 实测嵌套 ns 寻址。
4. 关联:resume 的"事件→节点态派生"归 trace-observability(debug-resume Q4);本块只产 checkpoint/事件,不做前端态派生。
