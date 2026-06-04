---
module: 02-mechanism/07-runtime
doc: baseline
status: drafted（有 live 入口但无顶层设计;❌）
---

# 07-runtime — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - `packages/graph-agent/src/graph_agent/core/runner.py`(SDK V0.3.0 入口 run_skill/predict_skill → assemble_graph)
> - `packages/graph-agent/src/graph_agent/__init__.py`(当前 `__all__` public surface,约 18 符号)
> - ⚠️ 死簇:`GraphAgentHarness`(入口类根本不存在,~1900 行 legacy 死簇之一,kiro 删)

待填:当前真实入口路径 runner→assemble_graph、现有 `__all__` 清单、死簇与 live 入口边界(这是 ❌:有 live 入口无顶层契约文档)。
