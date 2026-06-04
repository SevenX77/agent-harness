---
module: 01-contract/05-invalidation
doc: baseline
status: drafted（迁自 _migration-src/records/change-invalidation-model;注意 mvp1 反转）
---

# 05-invalidation — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 迁移源:`_migration-src/records/change-invalidation-model.md`(C3 模型已 drafted)
> - 旧实证:`packages/graph-agent/src/graph_agent/core/runner.py:127-160`(`_warn_on_stale_golden_hashes_sdk` 整哈希 warn,**退役**)、`compiler.py:38`(cache)
> - studio 侧 golden diff:`apps/studio/backend/app/services/golden_diff.py`

⚠️ mvp1 反转:原 change-invalidation-model 把 golden 失效写成**编译期硬错误**(`[F-v3-golden-stale-fields]`),mvp1 因 golden→workspace **改为 eval 期**(见 mvp1-alignment §5 IV2)。迁移时不照抄编译期落点。
