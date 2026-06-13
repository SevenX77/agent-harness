---
spec_id: mvp1-three-module-interface-2026-06-11
module: engine
phase: integration-gateway-contract-fix
artifact: gemini-prompt
status: ready-for-codex-review
created: 2026-06-11
task_file: .kiro/specs/mvp1-three-module-interface-2026-06-11/engine/integration-gateway-contract-fix/task.md
worktree: /Users/sevenx/Documents/coding/agent-harness/.worktrees/mvp1-three-module-integration-2026-06-11
branch: codex/mvp1-three-module-integration-2026-06-11
---

# Gemini Prompt - Engine Integration Gateway Step 4 Contract Fix

```text
你是 Gemini，负责在 Engine integration worktree 中实施一个很窄的 Gateway Step 4 契约适配修复。

工作区：
/Users/sevenx/Documents/coding/agent-harness/.worktrees/mvp1-three-module-integration-2026-06-11

分支：
codex/mvp1-three-module-integration-2026-06-11

当前任务：
- 修复已由 Codex 审核通过的 Engine integration RED。
- RED 指向：Engine 默认 predict resolver 仍在生产代码里构造 `ModelResolver(registry_snapshot=...)`。
- 目标：Engine 不得再构造 `ModelResolver(registry_snapshot=...)`；必须适配 Gateway Step 4 的 `config_store + user_id` 契约，或改为显式注入 resolver。

必须先读：
- .kiro/specs/mvp1-three-module-interface-2026-06-11/engine/integration-gateway-contract-red-report.md
- .kiro/specs/mvp1-three-module-interface-2026-06-11/engine/integration-gateway-contract-fix/task.md
- packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py
- packages/graph-agent/tests/core/test_predict_internal_imports.py
- packages/graph-agent/src/graph_agent/core/runner.py
- packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py
- packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py

如果上述文件缺失，立即停止并报告 BLOCKED，不要猜测。

硬约束：
1. 使用 `superpowers:test-driven-development`。
2. 先重跑 approved RED，确认当前仍是 `1 failed, 3 passed`，且唯一失败指向 `runner.py` 中的 `ModelResolver(registry_snapshot=snapshot)`。
3. 本次优先只改 `packages/graph-agent/src/graph_agent/core/runner.py`。
4. 不改 `packages/graph-agent-gateway/**`。
5. 不改 `apps/studio/**`。
6. 不改 FROZEN docs：`docs/engine/**`、`docs/graph-agent-gateway/**`、`docs/studio/**`。
7. 不改 `uv.lock`；如果工具改动了它，恢复并报告。
8. 不改 approved RED 测试，除非 Codex 明确要求机械修正。
9. 不把 Gateway 旧 `registry_snapshot=...` 兼容加回去。
10. 不把旧 Gateway snapshot 构造藏进 Engine helper、factory、lambda、字符串拼接或动态调用里。
11. 不用字符串绕过静态检查；`runner.py` 中不得再出现 `ModelResolver(registry_snapshot`。
12. 保持外部显式传入 `model_resolver` 的行为：调用者注入的 resolver 必须继续传给 `assemble_graph(...)`。
13. Gateway import 若仍需要存在，只能在运行时 lazy path 中出现，不能污染 `import graph_agent` 边界。

先运行 RED：
uv run pytest \
  packages/graph-agent/tests/core/test_predict_internal_imports.py \
  packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py \
  -q --tb=short

预期：
- `1 failed, 3 passed`
- 唯一失败：
  `test_engine_default_predict_resolver_uses_gateway_step4_contract`
- 失败原因：
  `runner.py` 仍含 `ModelResolver(registry_snapshot=snapshot)`

实施路线：

优先方案 A：显式注入 resolver
- 在 `packages/graph-agent/src/graph_agent/core/runner.py` 的 `predict_skill(...)` 中，删除 `if model_resolver is None:` 下构造 Gateway `RegistrySnapshot` 和 `ModelResolver(registry_snapshot=snapshot)` 的整段旧逻辑。
- 保留 `model_resolver` 参数。
- 保留后续 `assemble_graph(..., model_resolver=model_resolver, predict_context=predict_context, ...)` 调用。
- 如果 `model_resolver is None`，不要由 Engine 私自构造 Gateway resolver；让 Predict mock/interception path 和现有 graph assembly 行为处理。

备选方案 B：Gateway Step 4 config store 契约
- 只有当方案 A 导致已有核心测试出现真实行为回归时，才使用此方案。
- 如果必须保留默认 Gateway resolver，只能调用：
  `ModelResolver(config_store=config_store, user_id=user_id)`
- `config_store` 必须满足 Gateway `ConfigTruthStore`，并返回两个 key：
  - `credentials`
  - `roles`
- 可以使用 Gateway 的 `InMemoryConfigTruthStore`，但必须保持 lazy import。
- 严禁使用 `RegistrySnapshot` 作为 `ModelResolver` 构造参数。

无论选哪种方案，都必须通过静态探针：
rg -n "ModelResolver\\(registry_snapshot|registry_snapshot=snapshot" packages/graph-agent/src/graph_agent/core/runner.py

期望：无输出。

验证命令：

1. Integration RED now GREEN：
uv run pytest \
  packages/graph-agent/tests/core/test_predict_internal_imports.py \
  packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py \
  -q --tb=short

期望：`4 passed`

2. Existing predict resolver binding regression：
uv run pytest packages/graph-agent/tests/core/test_predict_runner_binding.py -q

期望：pass

3. Integration preflight：
uv run python -c 'import graph_agent; from inspect import signature; from graph_agent_gateway.resolver import ModelResolver; missing = [name for name in ("compile_artifact", "run_artifact", "predict_artifact") if not hasattr(graph_agent, name)]; print("missing_engine_artifact_api:", missing); print("gateway_model_resolver_signature:", signature(ModelResolver))'

期望：
- `missing_engine_artifact_api: []`
- `gateway_model_resolver_signature:` 显示 `config_store` 和 `user_id`

4. Engine core gate：
uv run pytest packages/graph-agent/tests/core -q

期望：pass；若已有 expected xpassed，请在报告中保留实际数量。

5. Ruff：
uv run ruff check \
  packages/graph-agent/src/graph_agent/core/runner.py \
  packages/graph-agent/tests/core/test_predict_internal_imports.py \
  packages/graph-agent/tests/core/test_productization_gateway_contract_integration_red.py

期望：`All checks passed!`

6. Scope guard：
git diff --name-only -- \
  packages/graph-agent-gateway \
  apps/studio \
  docs/engine \
  docs/graph-agent-gateway \
  docs/studio \
  uv.lock

期望：
- 本次修复没有新增这些禁止范围内的改动。
- 如果命令显示 integration worktree 已有聚合 diff，请明确标注为本次修复前已存在，不要回滚。

7. Diff whitespace：
git diff --check

期望：无输出。

8. Final status：
git status --short -uall

交付报告必须包含：
1. 采用方案 A 还是方案 B。
2. 修改文件列表。
3. 说明 `runner.py` 已不再出现 `ModelResolver(registry_snapshot`。
4. 说明没有把旧 Gateway snapshot 构造藏到 helper 里。
5. 说明显式注入 `model_resolver` 的路径仍保留。
6. pytest、ruff、preflight、scope guard、diff check、git status 摘要。
7. 确认未修改 Studio/Gateway/FROZEN docs/uv.lock。
8. 风险或未处理项。

不要提交 commit。
不要交 Codex 复审；完成后只把自审报告交给 Engine PM。
```
