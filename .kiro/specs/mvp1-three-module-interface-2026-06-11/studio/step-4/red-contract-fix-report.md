# Studio Step 4 RED Contract Fix Report

## 修改的测试文件列表

- `apps/studio/backend/tests/services/test_gateway_resolver_bridge.py`
- `apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py`
- `apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py`

## 新 RED 测试钉住的契约

### Gateway 契约

- `app/core/adapters/gateway.py`
- `app/core/adapters/engine.py`
- `app/services/gateway_resolver.py`

上述 Studio owner path 不得再构造 `ModelResolver(registry_snapshot=...)`。

`test_gateway_resolver_bridge_uses_config_truth_store_instead_of_registry_snapshot` 使用 Step 4 形状的 fake Gateway resolver：只接受 `ModelResolver(config_store=..., user_id=...)`。如果 Studio 继续传 `registry_snapshot`，测试会失败并明确报：

`Studio must not build Gateway ModelResolver with registry_snapshot; pass config_store and user_id instead.`

旧的 `resolver.registry_snapshot` 断言已改为断言：

- Studio 向 resolver 传入 `config_store`
- Studio 向 resolver 传入 `config.DEFAULT_USER_ID`
- `config_store` 能按 user/key 读取 credentials 与 roles

### Engine artifact runtime 契约

`test_engine_adapter_artifact_runtime_uses_new_artifact_apis_not_source_skill_runtime` 将旧入口硬失败：

- `engine_module.run_skill = pytest.fail(...)`
- `engine_module.predict_skill = pytest.fail(...)`

同时 monkeypatch 新 artifact API：

- `engine_module.run_artifact(...)`
- `engine_module.predict_artifact(...)`

测试要求新 artifact API 收到：

- `artifact_ref`
- `inputs`
- `execution_context`
- `idempotency_key`

当前实现仍调用旧 `run_skill`，因此 RED 失败。

## pytest RED 输出摘要

命令：

```bash
uv run pytest \
  apps/studio/backend/tests/services/test_gateway_resolver_bridge.py \
  apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py \
  apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py \
  -q --tb=short
```

结果：

```text
4 failed, 10 passed in 0.32s
```

失败集中在：

- `test_gateway_resolver_bridge_uses_config_truth_store_instead_of_registry_snapshot`
- `test_gateway_resolver_bridge_allows_missing_credentials_first_run`
- `test_gateway_owner_paths_do_not_use_registry_snapshot_model_resolver_contract`
- `test_engine_adapter_artifact_runtime_uses_new_artifact_apis_not_source_skill_runtime`

失败原因：

- Studio 仍调用 `ModelResolver(registry_snapshot=...)`
- `EngineAdapter.run_artifact(...)` 仍调用旧 `run_skill` source runtime

## ruff 输出摘要

命令：

```bash
uv run ruff check \
  apps/studio/backend/tests/services/test_gateway_resolver_bridge.py \
  apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py \
  apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py
```

结果：

```text
All checks passed!
```

## scope guard 输出摘要

命令：

```bash
git diff --name-only -- \
  apps/studio/backend/app \
  packages/graph-agent \
  packages/graph-agent-gateway \
  docs/studio \
  docs/engine \
  docs/graph-agent-gateway \
  uv.lock
```

实际输出非空，列出的是进入本轮 RED 前已经存在的 Step 4 GREEN 生产代码 diff：

```text
apps/studio/backend/app/core/adapters/__init__.py
apps/studio/backend/app/routers/llm.py
apps/studio/backend/app/routers/runs.py
apps/studio/backend/app/routers/skills.py
apps/studio/backend/app/services/copilot.py
apps/studio/backend/app/services/diagnostic_export.py
apps/studio/backend/app/services/gateway_resolver.py
apps/studio/backend/app/services/golden_diff.py
apps/studio/backend/app/services/llm_credentials.py
apps/studio/backend/app/services/llm_import_drafts.py
apps/studio/backend/app/services/llm_role_materializer.py
apps/studio/backend/app/services/llm_route_capabilities.py
apps/studio/backend/app/services/llm_state_projection.py
apps/studio/backend/app/services/predictor.py
apps/studio/backend/app/services/run_manager.py
apps/studio/backend/app/services/skill_resolver.py
apps/studio/backend/app/services/skills.py
apps/studio/backend/app/services/validator.py
```

本轮没有修改任何 `apps/studio/backend/app/**` 文件，也没有修改 `packages/graph-agent/**`、`packages/graph-agent-gateway/**`、FROZEN docs 或 `uv.lock`。

## 生产代码修改确认

- 本轮生产代码修改：0
- 本轮只修改测试与本 RED 报告

## Kiro/Gemini 文件确认

- 未写 Step 4 Kiro `task.md`
- 未写 Gemini prompt
- 未交 Gemini

## Ready for Codex review

Yes.
