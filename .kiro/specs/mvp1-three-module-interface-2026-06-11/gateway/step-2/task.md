# Gateway Step 2 Task: Interface Definition GREEN

## 目标

在 `packages/graph-agent-gateway` 内补齐 MVP1 Gateway 接口定义 GREEN 所需的公共契约模块，让已审核通过的 Step 1 RED 测试转绿。

本步骤只落地接口定义和最小 owner-side 契约实现：

- 配置真相线接口包含 `user_id`、`etag`、`if_match`、`if_none_match` 和 stale etag 冲突错误。
- 凭证解析 DTO 包含 `source`、`secret_handle`、`expires_at`，并禁止 raw secret 字段。
- route handoff DTO 包含 `role`、`routes`、`skipped`。
- fallback decision DTO 包含 `retry_same`、`switch_route`、`give_up` 三种动作。
- 6-state projection/materialize DTO 在 gateway 包内定义。
- 空 route、空 fallback chain、`give_up` 都必须显式 error payload，不得作为普通空值继续。

## 非目标

- 不接入 `ModelResolver`、`GatewayChatModel`、registry resolver 或真实调用路径；这些属于 Step 4 功能收口。
- 不实现 fake vault、expired secret handle 执行拦截、fallback 公共函数抽取；这些属于 Step 4 功能收口。
- 不修改 Engine 或 Studio 生产代码。
- 不修改已审核的 Step 1 RED 测试，除非 Codex 单独要求机械同步。
- 不改 FROZEN MVP1 文档。
- 不扩大错误范围，不新增本任务未要求的恢复逻辑。

## 允许修改的文件

只允许创建或修改以下 Gateway 生产文件：

- `packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_handoff.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`

## 禁止修改的文件

- `packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py`
- `packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/**`
- `packages/graph-agent/**`
- `apps/studio/**`
- `docs/studio/**`
- `docs/graph-agent-gateway/mvp1/**`
- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/**`

## RED 测试清单

已安装并审核通过的 RED 测试：

- `packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py`
  - `ConfigTruthStore.get_config(self, user_id, key)` 必须要求 `user_id`。
  - `ConfigTruthStore.put_config(self, user_id, key, value, *, if_match=None, if_none_match=None)` 必须要求 `user_id`，并支持 `if_match` / `if_none_match`。
  - `InMemoryConfigTruthStore.get_config(...)` 返回 `ConfigRecord(value, etag)`。
  - `if_none_match="*"` 遇到已存在 key 必须抛 `ConfigConflictError`，`error_code == "config.etag_conflict"`。
  - stale `if_match` 必须抛 `ConfigConflictError`，payload 包含 `expected_etag` 和 `actual_if_match`。
  - `CredentialResolveRequest.source` 只支持 `local_input` / `remote_vault`。
  - `CredentialResolveResponse` 返回 `secret_handle` / `expires_at` / `redacted_label`，schema 不得有 `raw_secret` / `api_key` / `secret`，且 extra 字段被拒绝。

- `packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py`
  - `ResolvedRouteChain` dump 出 `role`、`routes`、`skipped`。
  - 空 route chain 没有显式错误时必须 validation error；显式错误使用 `resource.no_available_route`。
  - `FallbackDecision.action` 只允许 `retry_same` / `switch_route` / `give_up`。
  - `switch_route` 必须有 `next_route_id`。
  - `give_up` 必须有显式 `error_code == "fallback.give_up"` 和 `error_payload`。
  - `MaterializedRole` 空 fallback chain 没有显式错误时必须 validation error；显式错误使用 `resource.no_available_route`。
  - 非 failed 的 6-state projection 不允许 failed reason。
  - failed reason 只允许 `missing_config`、`endpoint_unreachable`、`model_failed`。
  - cooling_down 可以携带 `retry_at` / `ui_detail`，但不得携带 failed reason。

当前 RED 命令：

```bash
uv run pytest \
  packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py \
  packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py \
  -q
```

当前 RED 摘要：`20 failed`，全部为目标契约模块缺失：

- `graph_agent_gateway.storage_contracts`
- `graph_agent_gateway.credential_resolver`
- `graph_agent_gateway.route_handoff`
- `graph_agent_gateway.fallback_decision`
- `graph_agent_gateway.state_projection`

## GREEN-1 接口/协议任务

### 1. `storage_contracts.py`

定义配置真相线契约和最小内存实现。

必须包含：

- `ConfigRecord`
  - Pydantic `BaseModel`
  - `value: dict[str, Any]`
  - `etag: str`
  - `model_config = ConfigDict(extra="forbid")`

- `ConfigConflictError`
  - Exception 类型
  - 属性 `error_code: str`
  - 属性 `error_payload: dict[str, Any]`
  - etag 冲突时 `error_code == "config.etag_conflict"`

- `ConfigTruthStore`
  - `Protocol` 或抽象基类均可。
  - `get_config(self, user_id: str, key: str) -> ConfigRecord`
  - `put_config(self, user_id: str, key: str, value: dict[str, Any], *, if_match: str | None = None, if_none_match: str | None = None) -> str`
  - 签名必须匹配 RED 测试的 `inspect.signature` 断言。

- `InMemoryConfigTruthStore`
  - 实现 `ConfigTruthStore`。
  - key 空间必须按 `(user_id, key)` 隔离。
  - `put_config(..., if_none_match="*")` 遇到已有记录时抛 `ConfigConflictError`。
  - `put_config(..., if_match=<etag>)` 遇到不存在记录或 etag 不匹配时抛 `ConfigConflictError`。
  - 成功写入返回新 etag；同一 key 后续成功写入的新 etag 必须不同。
  - stale etag 冲突 payload 至少包含 `user_id`、`key`、`expected_etag`、`actual_if_match`。

### 2. `credential_resolver.py`

定义凭证解析 DTO。只定义安全 DTO，不返回 raw secret。

必须包含：

- `CredentialResolveRequest`
  - Pydantic `BaseModel`
  - `user_id: str`
  - `role: str`
  - `credential_ref: str`
  - `source: Literal["local_input", "remote_vault"]`
  - `model_config = ConfigDict(extra="forbid")`

- `CredentialResolveResponse`
  - Pydantic `BaseModel`
  - `secret_handle: str`
  - `expires_at: datetime | None = None`
  - `redacted_label: str | None = None`
  - `model_config = ConfigDict(extra="forbid")`
  - 不得定义 `raw_secret`、`api_key`、`secret` 字段。

### 3. `route_handoff.py`

定义 route handoff DTO。

必须包含：

- `RouteSkipDiagnostic`
  - Pydantic `BaseModel`
  - `route_id: str`
  - `reason_code: str`
  - `message: str`
  - `from_override: bool`
  - `model_config = ConfigDict(extra="forbid")`

- `ResolvedRouteChain`
  - Pydantic `BaseModel`
  - `role: str`
  - `routes: list[ResolvedRoute]`
  - `skipped: list[RouteSkipDiagnostic]`
  - `error_code: str | None = None`
  - `error_payload: dict[str, Any] | None = None`
  - `model_config = ConfigDict(extra="forbid")`
  - 如果 `routes` 为空，则必须同时提供 `error_code == "resource.no_available_route"` 和非空 `error_payload`。
  - 默认 `model_dump(mode="json")` 时应排除 None 字段，使正常成功 DTO 只 dump 出 `role`、`routes`、`skipped`。

### 4. `fallback_decision.py`

定义 fallback decision DTO。

必须包含：

- `FallbackDecision`
  - Pydantic `BaseModel`
  - `action: Literal["retry_same", "switch_route", "give_up"]`
  - `reason_code: str`
  - `next_route_id: str | None = None`
  - `retry_after: datetime | None = None`
  - `error_code: str | None = None`
  - `error_payload: dict[str, Any] | None = None`
  - `model_config = ConfigDict(extra="forbid")`
  - `action == "switch_route"` 时必须提供 `next_route_id`。
  - `action == "give_up"` 时必须提供 `error_code == "fallback.give_up"` 和非空 `error_payload`。

### 5. `state_projection.py`

定义 Gateway 包内 6-state projection/materialize DTO。

必须包含：

- `ProviderModelStateProjection`
  - Pydantic `BaseModel`
  - `route_id: str`
  - `ui_state: Literal["ready", "historical_ready", "untested", "failed", "cooling_down", "off"]`
  - `reason_code: Literal["missing_config", "endpoint_unreachable", "model_failed"] | None = None`
  - `retry_at: datetime | None = None`
  - `ui_detail: str | None = None`
  - `evidence_refs: list[str] = Field(default_factory=list)`
  - `model_config = ConfigDict(extra="forbid")`
  - 如果 `ui_state != "failed"`，不得提供 `reason_code`。
  - 如果 `ui_state == "failed"`，`reason_code` 必须是上述三枚举之一。

- `RouteWarning`
  - Pydantic `BaseModel`
  - `route_id: str`
  - `warning_code: str`
  - `message: str`
  - `model_config = ConfigDict(extra="forbid")`

- `MaterializedRole`
  - Pydantic `BaseModel`
  - `role: str`
  - `fallback_chain: list[ResolvedRoute]`
  - `warnings: list[RouteWarning]`
  - `projections: dict[str, ProviderModelStateProjection]`
  - `error_code: str | None = None`
  - `error_payload: dict[str, Any] | None = None`
  - `model_config = ConfigDict(extra="forbid")`
  - 如果 `fallback_chain` 为空，则必须同时提供 `error_code == "resource.no_available_route"` 和非空 `error_payload`。

可选但推荐：

- `MaterializeRoleRequest`
  - `user_id: str`
  - `role: str`
  - `include_diagnostics: bool = True`

## GREEN-2 owner-side production path 任务

本步骤的 owner-side production path 是 Gateway 包内的最小可执行契约层，不是跨模块接线。

- `InMemoryConfigTruthStore` 必须是真实可用的配置真相 store 实现，支持 user-scoped get/put、etag 更新、`if_match`、`if_none_match="*"` 和冲突 payload。
- route/fallback/materialize/projection DTO 必须用 Pydantic validator 在 Gateway 包内硬失败，不能让空 route、空 fallback chain、`give_up` 作为普通空值通过。
- credential DTO 必须在 schema 层禁止 raw secret 字段，避免调用方把明文 secret 穿过 UI/adapter DTO。
- 所有新模块都应使用 `from __future__ import annotations`，并保持 ASCII。
- 不需要在本步骤修改 `__init__.py` 公共导出；如实现者认为导出必要，必须先在回复里说明理由，不能擅自扩大范围。

## 验证命令

必须运行：

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

git status --short

git diff --name-only -- \
  packages/graph-agent \
  apps/studio \
  packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py \
  packages/graph-agent-gateway/src/graph_agent_gateway/registry \
  docs/graph-agent-gateway/mvp1 \
  docs/studio \
  docs/engine \
  uv.lock
```

预期：

- Step 1 两个测试文件全部通过。
- Ruff 通过。
- `git status --short` 允许出现以下路径：
  - `.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-2/task.md`
  - `.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-2/gemini-prompt.md`
  - `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/`
  - `packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py`
  - `packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py`
  - `packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py`
  - `packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py`
  - `packages/graph-agent-gateway/src/graph_agent_gateway/route_handoff.py`
  - `packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py`
  - `packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`
- scope guard `git diff --name-only -- ...` 必须无输出，证明没有 Engine/Studio、旧 Gateway owner 文件、FROZEN MVP1 文档或 `uv.lock` 改动。

## 回滚范围

如果 Codex 审核不通过，本 Step 只回滚以下文件：

- `packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_handoff.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`

不得回滚 Step 1 已审核 RED 测试，不得回滚工单文档。
