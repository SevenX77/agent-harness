---
module: 02-mechanism/06-seam/02-observability
doc: baseline
status: drafted（迁自 _migration-src/06-trace-observability + api §1）
---

# 02-observability — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 迁移源:`_migration-src/06-trace-observability/`、`_migration-src/api-engine-studio-contract.md §1`(trace API)
> - `callbacks/events.py:42`(`_EventBase`)+ 34 类 event;`callbacks/{emit,tracing,serialize,metrics,logging_cb,base}.py`
> - `core/graph_assembler.py:515-555`(当前内联 emit LLMCallEvent/ToolCallEvent;迁到 Tracing 中间件后不回退)
> - `trace.jsonl` 落点 `<workspace>/runs/<run_id>/`(归 `physical-layout`)

待填:当前事件发/序列化/metrics 现状 + 内联 emit 迁 Tracing 中间件。
