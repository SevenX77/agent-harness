---
module: 02-mechanism/05-run-inner/02-middleware
doc: baseline
status: drafted（迁自 _migration-src/01-agent-loop）
---

# 02-middleware — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 迁移源:`_migration-src/01-agent-loop/{baseline,mvp1-alignment}.md`
> - `middleware/__init__.py:58-65`(6 槽顺序契约)、`middleware/factory.py:29-65`(build_middleware_chain)
> - 前三槽真实类:`protocol_validation.py`、`cognitive_flow.py`、`execution_control.py:67-90`(本域 own)
> - 后三槽 no-op:`tracing.py`、`tool_error.py`、`loop_detection.py`(逻辑归各域)

待填:6 槽现状 + 前三槽细节 + 后三槽 no-op + deerflow 参考边界。
