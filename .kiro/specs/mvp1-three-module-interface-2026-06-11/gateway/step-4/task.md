# Gateway Step 4 Task: Functional Closure GREEN

## 目标

把 Step 3 已审核通过的 RED 测试转绿，完成 Gateway MVP1 功能收口：

- `ModelResolver` 配置读取必须走 `ConfigTruthStore` / Gateway owner path，不能再通过 `registry_snapshot`、`credentials_path`、`roles_path` 绕过配置真相线。
- `ConfigTruthStore` stale `if_match` 冲突保持 `config.etag_conflict`，两个 writer 使用同一旧 etag 时第二个 writer 必须失败。
- fallback decision 从私有推进逻辑收口为 Gateway 公共函数 `decide_fallback(...)`。
- Gateway 包内提供可调用的 6-state projection/materialize 函数。
- fake vault 5xx 必须结构化为 `credential.vault_unreachable`。
- expired secret handle 必须在 provider build 前被拒绝，错误码为 `credential.secret_expired`。
- no route / empty fallback chain 必须由真实 Gateway owner path 输出 `resource.no_available_route`，不是普通空值或旧错误。

## 非目标

- 不修改 Step 1/Step 3 测试。
- 不改 Engine 或 Studio 生产代码。
- 不改 FROZEN MVP1 文档、`docs/studio/**`、`docs/engine/**`、`docs/graph-agent-gateway/mvp1/**`。
- 不实现真实远端 vault 客户端、真实数据库 provider、跨进程锁或多节点恢复逻辑。
- 不改变 provider registry schema 文件或 resolver 纯函数内部算法，除非当前任务明确要求。
- 不处理 Step 3 测试没有覆盖的已有 gateway 旧测试兼容性；如更广测试失败，报告为风险，不能为兼容旧 bypass 重新开放 `registry_snapshot` / path 入口。

## 允许修改的文件

只允许修改以下 Gateway production 文件：

- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_handoff.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py`

## 禁止修改的文件

- `packages/graph-agent-gateway/tests/**`
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/**`
- `packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py`
- `packages/graph-agent/**`
- `apps/studio/**`
- `docs/graph-agent-gateway/mvp1/**`
- `docs/studio/**`
- `docs/engine/**`
- `uv.lock`

## RED 测试清单

目标命令：

```bash
uv run pytest \
  packages/graph-agent-gateway/tests/test_productization_resolver_storage_red.py \
  packages/graph-agent-gateway/tests/test_productization_fallback_decision_red.py \
  packages/graph-agent-gateway/tests/test_productization_state_projection_red.py \
  packages/graph-agent-gateway/tests/test_productization_credential_failure_red.py \
  packages/graph-agent-gateway/tests/test_productization_resource_terminal_red.py \
  -q
```

当前 RED 形状：`9 failed, 1 passed`。

当前唯一已通过测试：

- `test_config_truth_store_rejects_second_writer_with_stale_if_match`

必须转绿的失败：

- `test_model_resolver_no_longer_exposes_file_or_snapshot_bypass`
  - `ModelResolver.__init__` 不得再暴露 `registry_snapshot`、`credentials_path`、`roles_path`。
  - 必须暴露 `config_store` 或 `config_truth_store`。

- `test_public_decide_fallback_switches_to_next_route`
  - `FallbackDecisionRequest` / `decide_fallback` 必须存在。
  - 当前 route 后还有 route 时，返回 `action == "switch_route"` 和正确 `next_route_id`。

- `test_public_decide_fallback_give_up_is_terminal_error`
  - 当前 route 是最后一个可用 route 时，返回 `action == "give_up"`。
  - `give_up` 必须包含 `error_code == "fallback.give_up"` 和非空 `error_payload`。

- `test_project_route_state_maps_missing_config_to_failed_reason`
  - `project_route_state(...)` 必须存在。
  - `credential_available=False` 时返回 `ui_state == "failed"`、`reason_code == "missing_config"`。

- `test_materialize_role_skips_failed_routes_and_returns_terminal_error`
  - `materialize_role(...)` 必须存在。
  - failed routes 必须被跳过。
  - 跳过后 fallback chain 为空时，返回 `error_code == "resource.no_available_route"`。

- `test_fake_vault_5xx_is_reported_as_vault_unreachable`
  - credential provider `get(...)` 抛 vault 5xx 时，RouteChatModelFactory build 必须抛结构化错误。
  - 错误码必须为 `credential.vault_unreachable`。
  - payload 必须包含 `credential_ref`。

- `test_expired_secret_handle_is_rejected_before_provider_build`
  - `credential_ref == "secret-handle://expired/openai"` 必须在 provider model build 前被拒绝。
  - 错误码必须为 `credential.secret_expired`。
  - payload 必须包含 `credential_ref`。

- `test_resolver_empty_fallback_chain_from_config_store_is_resource_terminal`
  - 通过 `InMemoryConfigTruthStore` 写入 empty fallback chain。
  - `ModelResolver(config_store|config_truth_store=store, user_id="user-a").resolve_routes(...)` 必须输出 `resource.no_available_route`。

- `test_resolver_missing_route_from_config_store_is_resource_terminal`
  - 通过 `InMemoryConfigTruthStore` 写入 missing route。
  - `resolve_routes(...)` 必须输出 `resource.no_available_route`。

## GREEN-1 接口/协议任务

### 1. `ModelResolver` 配置真相入口

修改 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`：

- `ModelResolver.__init__` 只保留 Gateway owner path：

```python
def __init__(
    self,
    *,
    config_store: ConfigTruthStore,
    user_id: str,
    client_manager: Any = None,
    credential_provider: CredentialProviderProtocol | None = None,
) -> None:
    ...
```

- 不得保留 `registry_snapshot`、`credentials_path`、`roles_path` 参数。
- 从 `config_store.get_config(user_id, "credentials").value` 读取 credentials payload。
- 从 `config_store.get_config(user_id, "roles").value` 读取 roles payload。
- 复用现有 `_assert_v4_credentials(...)`、`_assert_supported_roles(...)`、`_gateway_roles_payload(...)` 和 `RegistrySnapshot` 构造逻辑。
- 文件路径 loader helper 可以暂时保留为内部旧工具，但不能再由 `ModelResolver.__init__` 暴露为 bypass。
- `self.registry_snapshot` 仍可作为 resolver 内部 materialized snapshot cache。

### 2. 资源终态错误

在 `resolver.py` 内或允许文件中定义/使用结构化资源终态异常：

- `error_code == "resource.no_available_route"`
- `error_payload` 至少包含：

```python
{
    "role": role_name,
}
```

要求：

- `ModelResolver.resolve_routes(...)` 捕获 registry resolution 产生的 empty chain / all routes skipped / route missing 等 no-route 结果，转换为上述结构化资源终态错误。
- `ModelResolver.resolve(...)` 也应复用同一 resolver path，不能把 no-route 静默转成普通 `GatewayRoleNotConfiguredError`。

### 3. fallback 公共函数

修改 `packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py`：

- 新增 `FallbackDecisionRequest`：

```python
class FallbackDecisionRequest(BaseModel):
    chain: ResolvedRouteChain
    current_route_id: str
    attempt: int
    error_context: dict[str, Any] = Field(default_factory=dict)
```

- 新增 `decide_fallback(request: FallbackDecisionRequest) -> FallbackDecision`。
- 最小行为：
  - 找到 `current_route_id` 在 `request.chain.routes` 中的位置。
  - 如果存在下一条 route，返回 `FallbackDecision(action="switch_route", next_route_id=<next>, reason_code=<stable string>)`。
  - 如果没有下一条 route，返回 `FallbackDecision(action="give_up", reason_code=<stable string>, error_code="fallback.give_up", error_payload={"role": request.chain.role, ...})`。
  - 如果 route chain 为空，也返回 `give_up` + `fallback.give_up`。

### 4. 6-state projection / materialize 函数

修改 `packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`：

- 新增 `project_route_state(...) -> ProviderModelStateProjection`，签名必须接受 Step 3 测试参数：

```python
def project_route_state(
    *,
    route_id: str,
    endpoint_status: str,
    route_status: str,
    credential_available: bool,
    circuit_retry_at: datetime | None = None,
    draft_history: bool = False,
) -> ProviderModelStateProjection:
    ...
```

- 最小优先级：
  - `endpoint_status == "disabled"` 或 `route_status == "disabled"` -> `off`
  - `not credential_available` -> `failed` + `missing_config`
  - `endpoint_status == "failed"` -> `failed` + `endpoint_unreachable`
  - `route_status == "failed"` -> `failed` + `model_failed`
  - `circuit_retry_at is not None` -> `cooling_down`
  - endpoint 和 route 都 `verified` -> `ready`
  - endpoint `verified` 且 `draft_history` -> `historical_ready`
  - 其他 -> `untested`

- 新增 `materialize_role(...) -> MaterializedRole`，签名必须支持 Step 3 测试：

```python
def materialize_role(
    *,
    role: str,
    routes: list[ResolvedRoute],
    projections: dict[str, ProviderModelStateProjection],
) -> MaterializedRole:
    ...
```

- 最小行为：
  - `failed` / `off` routes 不进入 `fallback_chain`。
  - `cooling_down` routes 不进入 `fallback_chain`，可以进入 `warnings`。
  - 其他 route 保留。
  - 如果最终 `fallback_chain` 为空，返回 `MaterializedRole(..., error_code="resource.no_available_route", error_payload={"role": role})`。

### 5. credential vault failure / expired handle

修改 `packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py` 和 `route_chat_model_factory.py`：

- 定义结构化 credential error，至少有：
  - `error_code: str`
  - `error_payload: dict[str, Any]`

- `RouteChatModelFactory.build(...)` 在解析 credential 前必须拒绝过期 handle：

```python
if route.credential_ref.startswith("secret-handle://expired/"):
    raise <structured error>(
        error_code="credential.secret_expired",
        error_payload={"credential_ref": route.credential_ref, ...},
    )
```

- `_resolve_api_key(...)` 调 credential provider `get(...)` 时，如果 provider 抛异常，必须转成：

```python
error_code="credential.vault_unreachable"
error_payload={"credential_ref": route.credential_ref, ...}
```

- 不得把 raw secret 放入 error payload。

## GREEN-2 owner-side production path 任务

本 Step 的 owner-side path 不是 DTO 表面补齐，而是把 Step 2 合同接到真实 Gateway owner 入口：

- `ModelResolver` 必须只能通过 `ConfigTruthStore` materialize registry snapshot，不能从 caller 直接塞 snapshot 或文件路径。
- `resolve_routes(...)` 和 `resolve(...)` 必须把 no-route 类终态转成 `resource.no_available_route`。
- `RouteChatModelFactory` 必须在构建 provider model 之前处理 credential terminal errors。
- `fallback_decision.decide_fallback(...)` 是调用方可直接使用的公共 fallback 决策入口。
- `state_projection.project_route_state(...)` 和 `state_projection.materialize_role(...)` 是 Gateway 包内公共状态投影/物化入口。

## 验证命令

必须运行：

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

预期：

- Step 3 五个 RED 测试文件全部通过。
- Ruff 通过。
- scope guard `git diff --name-only -- ...` 无输出。
- `git status --short` 只允许出现：
  - `.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-4/task.md`
  - `.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-4/gemini-prompt.md`
  - 既有 `.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-2/**`
  - `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/`
  - Step 1 / Step 3 测试文件
  - Step 2 / Step 4 允许修改的 Gateway production 文件

## 回滚范围

如果 Codex 复审不通过，只回滚本 Step 修改的 Gateway production 文件：

- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_handoff.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py`

不得回滚 Step 1 / Step 3 RED 测试、Step 2 contract 文件、`.kiro` 任务材料或 docs 工作包，除非 Codex 明确要求。
