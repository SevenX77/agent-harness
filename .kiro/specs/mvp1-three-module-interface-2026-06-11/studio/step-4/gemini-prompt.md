# Gemini Prompt: Studio Step 4 Contract Repair GREEN

你是 Gemini，负责在 Studio PM 的 worktree 中实施 Studio Step 4 合同补钉后的 GREEN 修复。

你不是 PM，也不是 Codex reviewer。完成后必须把结果交回 Studio PM 自审；不要直接进入 Step 5，不要直接交 Codex。

## Worktree

```bash
cd /Users/sevenx/Documents/coding/agent-harness/.worktrees/mvp1-three-module-integration-2026-06-11
```

## 必须先读

- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md`
- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/02-implementation-plan.md`
- `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/pm-studio-work-order.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/studio/step-4/red-contract-fix-report.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/studio/step-4/task.md`

## 当前任务

先修这两个已通过 Codex 审核的 RED，直到它们转 GREEN：

1. Studio Gateway owner path 必须改为 Gateway Step 4 新契约：`ModelResolver(config_store=..., user_id=...)`。不得再使用 `ModelResolver(registry_snapshot=...)`。
2. Studio `EngineAdapter.run_artifact(...)` / `EngineAdapter.predict_artifact(...)` 必须调用 Engine 新 artifact API。不得再调用旧 `run_skill(...)` / `predict_skill(...)`。

这两个 RED 是三模块接口契约问题，不是普通 mock 适配问题。实现必须面向设计收口，不能为了过测把旧路径改名藏进 adapter。

## 硬约束

- 不得修改 `packages/graph-agent/**`。
- 不得修改 `packages/graph-agent-gateway/**`。
- 不得修改 `docs/studio/**`、`docs/engine/**`、`docs/graph-agent-gateway/**`。
- 不得修改 FROZEN docs。
- 不得修改 `uv.lock`。
- 不得修改 `apps/studio/frontend/**`。
- 不要写新的 Kiro task/prompt，不要改本 prompt。
- 不要弱化、跳过、删除已审核 RED 测试。
- 不要用固定返回值 fake 填生产代码。
- 不要用字符串绕过静态检查。
- 如果必须改 Engine/Gateway 包才能继续，停止并报告 blocker，不要自行扩大 scope。

## 允许优先修改的 Studio 文件

优先只改：

- `apps/studio/backend/app/core/adapters/gateway.py`
- `apps/studio/backend/app/core/adapters/engine.py`
- `apps/studio/backend/app/services/gateway_resolver.py`

只有当真实 owner path 需要同步适配时，才允许补充修改其他 `apps/studio/backend/app/**` 文件。不要碰 Engine/Gateway package。

## Preflight dependency gate

在确认 RED 或修改任何实现代码之前，必须先运行依赖探针，确认当前 Studio worktree 已经带入 Engine/Gateway Step 4 公共 API。

运行：

```bash
uv run python - <<'PY'
import graph_agent
from inspect import signature
from graph_agent_gateway.resolver import ModelResolver

missing = [
    name for name in ("compile_artifact", "run_artifact", "predict_artifact")
    if not hasattr(graph_agent, name)
]
print("missing_engine_artifact_api:", missing)
print("gateway_model_resolver_signature:", signature(ModelResolver))
PY
```

只有满足以下条件，才能继续进入实现：

- `missing_engine_artifact_api: []`
- `ModelResolver` 签名接受 `config_store` 和 `user_id`

如果任一条件不满足：

- 立即停止，不要修改 Studio 实现代码。
- 报告 `dependency blocker`。
- 不要修改 `packages/graph-agent/**` 或 `packages/graph-agent-gateway/**`。
- 不要用旧 `run_skill/predict_skill` 模拟 artifact runtime。
- 不要用旧 `ModelResolver(registry_snapshot=...)` 兼容 Gateway。
- 请求 Studio PM/Codex/协调方确认依赖策略：先把已放行的 Engine + Gateway Step 4 变更同步进 Studio worktree，还是停在 blocker 等三模块集成 worktree。

当前本地已知 blocker 形状如下；如果你看到同类输出，必须停止：

```text
missing_engine_artifact_api: ['compile_artifact', 'run_artifact', 'predict_artifact']
gateway_model_resolver_signature: (*, registry_snapshot: 'RegistrySnapshot | None' = None, credentials_path: 'str | Path | None' = None, roles_path: 'str | Path | None' = None, client_manager: 'Any' = None, credential_provider: 'CredentialProviderProtocol | None' = None) -> 'None'
```

## 先确认 RED

运行：

```bash
uv run pytest \
  apps/studio/backend/tests/services/test_gateway_resolver_bridge.py \
  apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py \
  apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py \
  -q --tb=short
```

预期当前失败集中在：

- Studio 仍调用 `ModelResolver(registry_snapshot=...)`
- `EngineAdapter.run_artifact(...)` / `predict_artifact(...)` 仍调用 `run_skill(...)` / `predict_skill(...)`

如果失败原因变成 import typo、fixture 错误或其他无关问题，先报告，不要盲改。

## 修复 1：Gateway 新契约

### 必须达成

这些 Studio owner path 不得再出现 `ModelResolver(registry_snapshot=...)`：

- `apps/studio/backend/app/core/adapters/gateway.py`
- `apps/studio/backend/app/core/adapters/engine.py`
- `apps/studio/backend/app/services/gateway_resolver.py`

必须使用 Gateway Step 4 新契约：

```python
ModelResolver(config_store=..., user_id=...)
```

### 设计要求

- Studio 负责维护 config truth store。
- Gateway 负责根据 `config_store + user_id` 解析模型路由。
- Studio 不再把 registry snapshot 当作 Gateway resolver 的契约。
- 不要依赖 `resolver.registry_snapshot` 作为生产逻辑或测试断言对象。

### 实施提示

- 优先使用 Studio 已有的 `LocalGatewayConfigStore` 或等价本地 config store。
- 使用现有 Studio 默认用户语义，例如 `config.DEFAULT_USER_ID`。
- 确保 credentials 和 roles 能从 store 中按 user/key 读回。
- `GatewayAdapter.resolve_routes(...)` 和 Engine adapter 内部 gateway resolver helper 都要走 `config_store + user_id`。
- 若 Gateway 当前公共 API 不支持该构造方式，停止并报告 blocker；不要回退到 `registry_snapshot`。

## 修复 2：Engine artifact runtime

### 必须达成

`EngineAdapter.run_artifact(payload)` 必须调用：

- `graph_agent.run_artifact(...)`，或
- adapter 内对同一公共 artifact API 的重导出/别名。

`EngineAdapter.predict_artifact(payload)` 必须调用：

- `graph_agent.predict_artifact(...)`，或
- adapter 内对同一公共 artifact API 的重导出/别名。

不得调用：

- `run_skill(...)`
- `predict_skill(...)`

### 设计要求

- Studio Step 4 owner path 是 product artifact runtime，不是 source skill runtime。
- `EngineAdapter` 不能把旧 source runtime 藏在内部继续执行。
- 服务层仍然不得直接 import `graph_agent`。

### 调用语义

传给 Engine artifact API 的参数必须包含 artifact 语义：

- `artifact_ref`
- `inputs`
- `execution_context` 或等价上下文
- `idempotency_key`

返回值在 Studio adapter 边界必须是 JSON-serializable dict。

### 实施提示

- SDK import 保持在 `apps/studio/backend/app/core/adapters/engine.py` 内部或 adapter-private helper 内。
- 保留现有 `StudioAdapterError` 包装和明确 `error_code`。
- 保持 HTTP loopback 路径行为不回退。
- 如果当前 `graph_agent` 没有暴露 `run_artifact` / `predict_artifact` 或等价 artifact API，停止并报告 blocker；不要用临时目录加 `run_skill(...)` 模拟 artifact runtime。

## 验证命令

### 1. Contract GREEN

```bash
uv run pytest \
  apps/studio/backend/tests/services/test_gateway_resolver_bridge.py \
  apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py \
  apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py \
  -q --tb=short
```

预期：通过。

### 2. Step 4 Target Regression

```bash
uv run pytest \
  apps/studio/backend/tests/core/adapters/test_productization_http_transport_errors_red.py \
  apps/studio/backend/tests/core/adapters/test_productization_import_boundary_red.py \
  apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py \
  apps/studio/backend/tests/routers/test_productization_publish_artifact_red.py \
  apps/studio/backend/tests/services/test_productization_publish_atomicity_red.py \
  apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py \
  apps/studio/backend/tests/services/test_productization_golden_headless_red.py \
  apps/studio/backend/tests/routers/test_productization_resume_adapter_red.py \
  apps/studio/backend/tests/services/test_productization_graph_roundtrip_red.py \
  -q --tb=short
```

预期：通过。

### 3. Step 1/2 Regression

```bash
uv run pytest \
  apps/studio/backend/tests/core/adapters/test_productization_adapters.py \
  apps/studio/backend/tests/core/adapters/test_productization_local_providers.py \
  apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py \
  apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py \
  -q --tb=short
```

预期：通过。

### 4. Ruff

```bash
uv run ruff check \
  apps/studio/backend/app/core/adapters/gateway.py \
  apps/studio/backend/app/core/adapters/engine.py \
  apps/studio/backend/app/services/gateway_resolver.py \
  apps/studio/backend/tests/services/test_gateway_resolver_bridge.py \
  apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py \
  apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py
```

预期：`All checks passed!`

### 5. Scope Guard

```bash
git diff --name-only -- \
  packages/graph-agent \
  packages/graph-agent-gateway \
  docs/studio \
  docs/engine \
  docs/graph-agent-gateway \
  uv.lock
```

预期：无输出。

### 6. Status

```bash
git status --short
```

报告最终文件状态。这个 worktree 可能已经存在 Step 4 的历史 dirty 文件；不要回滚无关改动。

## 输出给 Studio PM 的自审报告

完成后必须回复：

1. 修改文件列表。
2. 哪些是接口/协议修复。
3. 哪些是 Studio owner-side 真实路径修复。
4. Contract GREEN pytest 摘要。
5. Step 4 target pytest 摘要。
6. Step 1/2 regression pytest 摘要。
7. Ruff 摘要。
8. Scope guard 摘要。
9. `git status --short` 摘要。
10. 确认是否误改 `packages/graph-agent/**`、`packages/graph-agent-gateway/**`、FROZEN docs、`uv.lock`。
11. 风险和未处理项。
12. `Ready for Studio PM self-review: Yes/No`。
