你是 Gemini，负责在 Gateway PM 的 worktree 中实施 MVP1 三模块接口设计与修改的 Gateway Step 2。

目标 worktree：

`/Users/sevenx/Documents/coding/agent-harness/.worktrees/pm-gateway-mvp1-interface-2026-06-11`

必须先读：

- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md`
- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/02-implementation-plan.md`
- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/pm-gateway-work-order.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-2/task.md`
- `packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py`
- `packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py`

硬约束：

- 只能改 `.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-2/task.md` 允许的 Gateway production 文件。
- 不得修改 Step 1 RED 测试。
- 不得改 Engine/Studio 生产代码。
- 不得改 `resolver.py`、`gateway_chat_model.py` 或 `registry/**`。
- 每个错误必须有专属 `error_code`。
- 只允许硬失败或显式降级，禁止静默降级。
- 凭证接口不得泄漏 raw secret。
- 空 route / give_up / empty fallback_chain 必须显式错误化。
- 不得改 FROZEN MVP1 文档。
- 不得进入 Step 3/Step 4 功能收口。

当前 Step：

- Step 2 名称：Gateway 接口定义 GREEN
- 已有 RED 测试和失败摘要：`uv run pytest packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py -q` 当前为 `20 failed`，失败均为目标 Gateway 契约模块缺失：
  - `graph_agent_gateway.storage_contracts`
  - `graph_agent_gateway.credential_resolver`
  - `graph_agent_gateway.route_handoff`
  - `graph_agent_gateway.fallback_decision`
  - `graph_agent_gateway.state_projection`

目标测试命令：

```bash
uv run pytest \
  packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py \
  packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py \
  -q

uv run ruff check \
  packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py \
  packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/route_handoff.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py
```

请实施最小改动使目标测试通过。

实现范围只允许：

- `packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_handoff.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`

实现要点：

1. `storage_contracts.py`
   - 定义 `ConfigRecord`、`ConfigConflictError`、`ConfigTruthStore`、`InMemoryConfigTruthStore`。
   - `get_config(self, user_id, key)` 和 `put_config(self, user_id, key, value, *, if_match=None, if_none_match=None)` 签名必须匹配 RED 测试。
   - `if_none_match="*"` 和 stale `if_match` 必须抛 `ConfigConflictError(error_code="config.etag_conflict", error_payload=...)`。

2. `credential_resolver.py`
   - 定义 `CredentialResolveRequest`，`source` 只允许 `local_input` / `remote_vault`。
   - 定义 `CredentialResolveResponse`，只返回 `secret_handle`、`expires_at`、`redacted_label`。
   - 禁止 `raw_secret`、`api_key`、`secret` 字段或 extra 字段。

3. `route_handoff.py`
   - 定义 `RouteSkipDiagnostic` 和 `ResolvedRouteChain`。
   - 成功 DTO dump 默认只输出 `role`、`routes`、`skipped`。
   - 空 route chain 必须要求 `error_code == "resource.no_available_route"` 和非空 `error_payload`。

4. `fallback_decision.py`
   - 定义 `FallbackDecision`。
   - `action` 只允许 `retry_same`、`switch_route`、`give_up`。
   - `switch_route` 必须有 `next_route_id`。
   - `give_up` 必须有 `error_code == "fallback.give_up"` 和非空 `error_payload`。

5. `state_projection.py`
   - 定义 `ProviderModelStateProjection`、`RouteWarning`、`MaterializedRole`。
   - `ui_state` 只允许 `ready`、`historical_ready`、`untested`、`failed`、`cooling_down`、`off`。
   - `reason_code` 只允许 failed 态使用，且只允许 `missing_config`、`endpoint_unreachable`、`model_failed`。
   - 空 `fallback_chain` 必须要求 `error_code == "resource.no_available_route"` 和非空 `error_payload`。

请在回复中提供：

1. 修改文件列表。
2. 关键实现说明。
3. 测试命令和结果。
4. `git status --short` 摘要。
5. 风险和未处理项。
