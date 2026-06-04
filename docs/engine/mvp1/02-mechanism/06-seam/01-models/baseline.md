---
module: 02-mechanism/06-seam/01-models
doc: baseline
status: drafted（迁自 _migration-src/13-models）
---

# 01-models — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 迁移源:`_migration-src/13-models/{baseline,mvp1-alignment}.md`(D1 双模)
> - `core/graph_assembler.py:581-603`(`_resolve_phase_chat_model` → `model_resolver.resolve`,透传 predict_context)
> - `core/_predict_internal/interception.py:29-140`(PredictGatewayChatModel `_generate`/`bind_tools`)
> - gateway 子系统(独立,只读不改);第1趴 engine↔gateway = `temp/2026-06-02-engine-gateway-interface-needs.md`

待填:当前 model 解析路径 + GatewayChatModel 现状 + predict mock 现状。
