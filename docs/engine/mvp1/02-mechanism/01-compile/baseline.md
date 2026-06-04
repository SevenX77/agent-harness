---
module: 02-mechanism/01-compile
doc: baseline
status: drafted（现状散在 mvp0 + 代码;含死簇待清）
---

# 01-compile — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 时序契约:mvp0 `12-compile-runtime-flow-spec.md`(FROZEN)
> - `packages/graph-agent/src/graph_agent/core/loader.py`(读/解析/DAG·IO·mention·purity 校验聚合)、`compiler.py`(compile_skill + cache:38)、`purity.py`(扫描器)、`module_sandbox.py`(导入隔离)
> - ⚠️ 死簇:`graph_builder.py`/`phase_executor.py`/`phase_nodes/`(~1900 行 legacy,live 不走,kiro 删)

待填:当前编译路径 assemble_graph、cache/序列化现状、死簇与 live 边界。
