---
module: 10-iteration-and-resume
doc: baseline
status: drafted
last_verified: 2026-06-03
aligns_with:
  - ../../../studio/mvp1/02_capabilities/run-execution.md（batch/loop）
  - ../../../studio/mvp1/02_capabilities/debug-resume.md（三场景）
  - ../../../studio/_reorg/engine-prompt-trace-compile-debug.md（#5-8 + 统一 checkpoint 铁律）
---

# 10-iteration-and-resume — Baseline(现状)

核心结论:**节点级 batch(声明式并发)已实现**;**checkpoint 整套已接**(run 级 thread,memory/sqlite/postgres,且留了续跑开关);**loop(串行累积)、图级迭代、节点级 resume 是缺口**(`resume_run`=501)。engine-prompt 明确要求"batch/loop 的 loop 累积态 与 debug 的 checkpoint **本质同源,统一一套**"——故本关注点把迭代与续跑合并、共用 checkpoint 底座设计。

## 覆盖代码(含覆盖率)

覆盖率:100%。覆盖现有 batch、checkpoint、续跑地基、HitL 原语。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| `_build_batch_wrapped_node`(用途:把一个 phase 节点包成"对一组输入并发跑+聚合") | `graph_assembler.py:240-284` | 读 `batch_spec.iterator` 列表、`asyncio.Semaphore(concurrency)` 并发、按 `item_var` 注入每项、`asyncio.gather` 跑、聚合成 `aggregated_data[字段]=[各项值]`+`batch_outputs` |
| `_resolve_iterator`(用途:按点路径从 state 取迭代列表) | `graph_assembler.py:225-237` | `data.events` 之类点路径 → list |
| batch 接线 | `graph_assembler.py:299`(`_wrap_phase_runtime_node`) | `if phase_ast.batch is not None: node=_build_batch_wrapped_node(...)` |
| `checkpointer_context`/`resolve_checkpointer`(用途:按 backend 造 LangGraph checkpointer) | `core/checkpointer.py:38-160` | memory/sqlite/postgres;`resolve_checkpointer("auto")` 读 STUDIO_CHECKPOINTER/GRAPH_AGENT_CHECKPOINTER_DB |
| run 路径 checkpointer 接线 | `runner.py:663-691` | `active_checkpointer=resolve_checkpointer("auto")` → `assemble_graph(checkpointer=...)` → `graph.invoke(config={"thread_id":run_id})` |
| 续跑地基 | `runner.py:481-485` | `cleanup_checkpoints_on_finish=False` 文档明说"为从更早 checkpoint 续跑而留" |
| `resume_run`(501) | `apps/studio/backend/app/routers/runs.py`(raise_not_implemented) | 未实现;`ResumeReq.context_overrides` 字段已定义但**零消费** |
| HitL 原语 | `tools/builtin/clarification_tool.py` + `AmbiguityReportEvent` + `RunEndedEvent status="interrupted"` | 引擎已 emit 问题/中断,缺"答案注入 + 续跑"入口 |

## 编号执行流程(现状)

1. 节点上声明 `batch`(`batch_spec`)时,`_wrap_phase_runtime_node` 把该 phase 包成 `_build_batch_wrapped_node`,见 `graph_assembler.py:299`。
2. `_batch_wrapped` 用 `_resolve_iterator(state, batch_spec.iterator)` 取列表,`asyncio.Semaphore(concurrency)` 并发跑每项(每项经 `StateManager.update_business(state, **{item_var:item})` 注入),`asyncio.gather` 收集,见 `:241-258`。
3. 聚合:每个结果的 `data` 收进 `aggregated_data[k]=[各项值]` + `batch_outputs`,返回 `{"data": aggregated_data}`,见 `:260-282`。**只有并发独立,无串行累积(loop)。**
4. run 路径 `_run_v030_skill_dict` 用 `resolve_checkpointer("auto")` 编译图并 `graph.invoke(config={"configurable":{"thread_id":run_id}})`,见 `runner.py:663-691`。**thread 级(整 run 一个 thread);LangGraph 在 thread 内按 super-step 存 checkpoint。**
5. `resume_run` 端点 501;`ResumeReq.context_overrides` 定义了但全代码零消费。
6. HitL:`clarification_tool` / `AmbiguityReportEvent` / `interrupted` 已 emit,但无"注入答案从断点续"的闭环。

## Baseline / Alignment 差异

| 维度 | baseline 现状 | mvp1 目标 |
|---|---|---|
| 节点级 batch | ✅ 已声明式(`batch_spec`) | 复用 + 加 range 切片 |
| loop(串行累积) | ✗ 无 | 新增 mode=loop + 显式累积(F1) |
| 图级迭代 | ✗ 只节点级 | 整图跑 N 遍(batch/loop)+ 嵌套 |
| checkpoint | run/thread 级(+ LangGraph 节点 super-step) | 节点级精准续跑 + 失效追踪;**与 loop 累积统一一套** |
| resume | `resume_run`=501;overrides 零消费 | 实现 resume(节点级 + context_overrides + HitL 注入) |
| 配置 | `batch_spec`(iterator/concurrency/item_var) | 统一 `iterate`(向后兼容) |

## 代码索引(clues)

- `graph_assembler.py:225-284`:`_resolve_iterator` + `_build_batch_wrapped_node`(现节点级 batch)。
- `graph_assembler.py:299`:batch 接线点(loop 分支加这里)。
- `core/checkpointer.py:38-160`:checkpointer 工厂。
- `runner.py:663-691`:run 路径 checkpointer + invoke(图级迭代层包这外面)。
- `runner.py:481-485`:续跑开关(地基)。
- `apps/studio/backend/app/routers/runs.py`:`resume_run` 501。

## 待办/疑点

1. loop 串行累积、图级迭代、节点级 resume 全缺;但底座(batch 包装点、checkpointer、续跑开关、HitL 原语)都在。
2. engine-prompt 铁律:loop 累积态与 debug checkpoint 必须**统一一套**,不能两套——见 alignment §4。
3. `resume_run` 在 studio 后端 501;引擎能 resume LangGraph thread,但缺"节点级 + override/HitL 注入"的引擎能力。
