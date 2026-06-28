你是 Gemini，负责在 Gateway PM 的 worktree 中实施 MVP1 三模块接口设计与修改的 Gateway Step 4。

目标 worktree：

`/Users/sevenx/Documents/coding/agent-harness/.worktrees/pm-gateway-mvp1-interface-2026-06-11`

必须先读：

- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md`
- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/02-implementation-plan.md`
- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/pm-gateway-work-order.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-4/task.md`
- `packages/graph-agent-gateway/tests/test_productization_resolver_storage_red.py`
- `packages/graph-agent-gateway/tests/test_productization_fallback_decision_red.py`
- `packages/graph-agent-gateway/tests/test_productization_state_projection_red.py`
- `packages/graph-agent-gateway/tests/test_productization_credential_failure_red.py`
- `packages/graph-agent-gateway/tests/test_productization_resource_terminal_red.py`

硬约束：

- 只能改 `.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-4/task.md` 允许的 Gateway production 文件。
- 不得修改任何测试文件。
- 不得改 Engine/Studio 生产代码。
- 不得改 `gateway_chat_model.py` 或 `registry/**`。
- 不得改 `__init__.py`。
- 每个错误必须有专属 `error_code`。
- 只允许硬失败或显式降级，禁止静默降级。
- 凭证接口和错误 payload 不得泄漏 raw secret。
- 空 route / give_up / empty fallback_chain 必须显式错误化。
- 不得改 FROZEN MVP1 文档。

当前 Step：

- Step 4 名称：Gateway 功能收口 GREEN
- 已有 RED 测试和失败摘要：
  - 目标命令当前为 `9 failed, 1 passed`。
  - 已通过的是 stale `if_match` 双写者冲突。
  - 仍失败的是 resolver bypass、fallback 公共函数、state projection/materialize 函数、vault failure、expired handle、ConfigTruthStore owner path 下的资源终态。

目标测试命令：

```bash
uv run pytest \
  packages/graph-agent-gateway/tests/test_productization_resolver_storage_red.py \
  packages/graph-agent-gateway/tests/test_productization_fallback_decision_red.py \
  packages/graph-agent-gateway/tests/test_productization_state_projection_red.py \
  packages/graph-agent-gateway/tests/test_productization_credential_failure_red.py \
  packages/graph-agent-gateway/tests/test_productization_resource_terminal_red.py \
  -q

uv run ruff check \
  packages/graph-agent-gateway/tests/test_productization_resolver_storage_red.py \
  packages/graph-agent-gateway/tests/test_productization_fallback_decision_red.py \
  packages/graph-agent-gateway/tests/test_productization_state_projection_red.py \
  packages/graph-agent-gateway/tests/test_productization_credential_failure_red.py \
  packages/graph-agent-gateway/tests/test_productization_resource_terminal_red.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/route_handoff.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py
```

实现范围只允许：

- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_handoff.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py`

请实施最小改动使目标测试通过。

关键实现要求：

1. `resolver.py`
   - `ModelResolver.__init__` 不得再有 `registry_snapshot`、`credentials_path`、`roles_path` 参数。
   - 改为 `config_store: ConfigTruthStore` 和 `user_id: str` owner path。
   - 从 `config_store.get_config(user_id, "credentials").value` 和 `config_store.get_config(user_id, "roles").value` materialize `RegistrySnapshot`。
   - no route / empty fallback chain / route missing 要转成结构化错误：`error_code == "resource.no_available_route"`，payload 至少含 `role`。

2. `fallback_decision.py`
   - 新增 `FallbackDecisionRequest`。
   - 新增 `decide_fallback(request)`。
   - 当前 route 后还有 route -> `switch_route`。
   - 没有下一条 route 或 chain 为空 -> `give_up` + `fallback.give_up` + error payload。

3. `state_projection.py`
   - 新增 `project_route_state(...)`。
   - 新增 `materialize_role(...)`。
   - failed/off/cooling_down 不进入可执行 fallback chain。
   - fallback chain 为空 -> `resource.no_available_route`。

4. `credential_resolver.py` / `route_chat_model_factory.py`
   - 定义或使用结构化 credential error。
   - credential provider `get(...)` 抛异常 -> `credential.vault_unreachable`，payload 含 `credential_ref`，不含 raw secret。
   - `credential_ref.startswith("secret-handle://expired/")` -> provider build 前抛 `credential.secret_expired`，payload 含 `credential_ref`。

实施后请额外运行 scope guard：

```bash
git diff --name-only -- \
  packages/graph-agent \
  apps/studio \
  packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/registry \
  docs/graph-agent-gateway/mvp1 \
  docs/studio \
  docs/engine \
  uv.lock

git status --short
```

scope guard diff 必须无输出。

请在回复中提供：

1. 修改文件列表。
2. 关键实现说明。
3. pytest 命令和结果。
4. ruff 命令和结果。
5. scope guard 命令和结果。
6. `git status --short` 摘要。
7. 风险和未处理项。
