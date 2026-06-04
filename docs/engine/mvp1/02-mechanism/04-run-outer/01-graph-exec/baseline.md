---
module: 02-mechanism/04-run-outer/01-graph-exec
doc: baseline
status: drafted（AGENT侧有源;LOGIC 现状待钉清）
---

# 01-graph-exec — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 运行时流 + StateMapper 规则:mvp0 `12-compile-runtime-flow-spec.md`(运行时 Workflow)
> - `packages/graph-agent/src/graph_agent/core/run_context.py`、`runtime/state_mapper.py`(slice/merge)、io_manager
> - **LOGIC 现状**:`core/actions.py`(`ActionDef`/`ActionRegistry`)、`code_phase_node`(LOGIC 执行现状)——这是 ❌ 设计,baseline 先把现有 action 执行实情查清

待填:当前运行时调度/StateMapper/io 实情 + LOGIC code_phase_node 现状(action 注册/调度/args)。
