---
module: 03-api-contract
doc: baseline
status: drafted（迁移源 = _migration-src/api-engine-studio-contract.md 完整 5 节）
---

# 03-api-contract — Baseline(现状)

> 现状 = 完整 drafted 契约,迁移时逐行复核 `file:line`:
> - 迁移源:`_migration-src/api-engine-studio-contract.md`(§0–§7:三接口面 + trace + 执行 + golden + iterate/resume + compile + 端点总索引)
> - 引擎侧 SSOT:`packages/graph-agent/src/graph_agent/core/runner.py`(run_skill/predict_skill 签名)、`core/result.py`(RunResult)、`core/compiler.py`(compile_skill)
> - studio 暴露面:`apps/studio/backend/app/routers/*`(以此为准)

完整 238 行契约迁入本域 mvp1-alignment 时,字段级 RunResult/ErrorPayload 链 `data-contracts`、事件 schema 链 `02-observability`、resume 寻址链 `03-checkpoint`。
