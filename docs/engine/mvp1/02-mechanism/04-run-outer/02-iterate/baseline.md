---
module: 02-mechanism/04-run-outer/02-iterate
doc: baseline
status: drafted（B✅ 现状写全:节点级 batch live(file:line 已核 `graph_assembler.py:225/240/249/253/268/300`),loop/图级/range 明确标缺口;U11 锁）
---

# 02-iterate — Baseline(当下代码实现逻辑)

> **Scope**: 声明式循环的现状:`_build_batch_wrapped_node`(节点级 batch 并发)、`_resolve_iterator`(取迭代列表)。loop 串行累积、图级迭代、range 切片是 mvp1 缺口。
> **现状一句话**:只有**节点级 batch**(声明式并发)live:`_build_batch_wrapped_node`(`graph_assembler.py:240`)读 `batch_spec.iterator` 列表、`Semaphore(concurrency)` 并发、按 `item_var` 注入每项、`gather` 收集、聚合成 `aggregated_data[k]=[各项值]`。**loop(串行累积)、图级迭代、range、统一 `iterate` 配置都还没有。**

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. 节点级 batch(已 live)
`_build_batch_wrapped_node(node, batch_spec)`(`:240`):
1. `items = _resolve_iterator(state, batch_spec.iterator)`(`:242`)——按点路径(如 `data.events`)从 state 取 list(`_resolve_iterator` `:225`)。
2. `semaphore = asyncio.Semaphore(batch_spec.concurrency)`(`:249`)控并发。
3. 每项经 `StateManager.update_business(state, **{batch_spec.item_var: item})`(`:253`)注入,`asyncio.gather`(`:256`)并发跑。
4. 聚合:每结果的 data key 收进 `aggregated_data[k].append(v)`(`:268-270`)。
> **batch 第一次出现需定义**:对一组输入并行 map 同一个 phase,再把各项输出聚合回黑板。

### 2. 接线
`_wrap_phase_runtime_node`(`:287`)在 phase 声明了 batch 时,把节点包成 `_build_batch_wrapped_node`。

## API
- `_build_batch_wrapped_node(node, batch_spec) -> wrapped_node`(`:240`)。
- `_resolve_iterator(state, path_str) -> list`(`:225`)。

## Data Model / State
读 `batch_spec`(iterator/concurrency/item_var);写 `aggregated_data`(各 item 输出聚合回黑板)。

## 当前边界(这个模块现在不是什么)
- **没有串行累积(loop)**:现状只并发独立,无 `accumulate`。
- **没有图级迭代**:只节点级。
- **没有 range 切片**:跑全量。
- **batch 事件未盖 item 维度**:100 项 trace 全糊在同一 `phase_name`(归 `02-observability`,要补 `phase_execution_id`+`iteration_index`)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 配置 | `batch_spec`(iterator/concurrency/item_var) | 统一 `iterate`(mode/over/range/accumulate,兼容 batch) |
| loop | 无 | mode=loop + 显式 `accumulate{var,init,from,merge}` |
| 图级 | 无 | 图级 batch(Send)/ 图级 loop=B(引擎包 loop-body,一 thread + ns=iter{k}) |
| range | 无 | range 切片(predict 默认 [1,1]) |

> **验"是否按 mvp1 改了"**:① 图级 iterate 是否引擎包 loop-body(一 thread + ns=iter{k}),非 N 次独立 invoke;② loop 累积 checkpoint 总体积 O(N);③ 每项 trace 盖 `phase_execution_id`。

## 读代码主路径提示
`_resolve_iterator`(`:225`)→ `_build_batch_wrapped_node`(`:240`)→ 接线 `_wrap_phase_runtime_node`(`:287`)。loop/图级/range 是 target,现无代码。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `01-contract/02-skill-syntax`(iterate 声明,双向)· `03-checkpoint`(loop 累积 checkpoint,双向)· `06-seam/02-observability`(每轮 trace 盖戳)· `05-run-inner/08-messages-state`
