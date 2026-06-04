---
module: 02-mechanism/05-run-inner/06-golden-eval
doc: baseline
status: drafted（迁自 _migration-src/09-golden-eval;⚠️ 含决策反转）
---

# 06-golden-eval — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 迁移源:`_migration-src/09-golden-eval/mvp1-alignment.md`(**顶部有 2026-06-03 决策 A 反转 admonition:golden→workspace**;下文 G1-G5 仍按旧决策 A 行文,迁移时按反转改写)
> - `runner.py:84-124`(回放 resolve_generation P0)、`golden_diff.py:130-216`(diff 算法,复用)
> - golden 落点:`.workspace/golden/`(mvp0 workspace-spec §3.2,**不废**)

⚠️ 关键:旧 09-golden-eval 的决策 A(golden 随技能进 git `phases/<id>/golden.json`)**作废**;baseline 以反转后(golden 在 .workspace、失效移 eval)为准。
