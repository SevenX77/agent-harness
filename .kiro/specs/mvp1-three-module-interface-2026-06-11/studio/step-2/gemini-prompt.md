你是 Gemini，负责在 Studio PM 的 worktree 中实施 MVP1 三模块接口设计与修改的 Studio Step 2。

必须先读：
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/02-implementation-plan.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/pm-studio-work-order.md
- .kiro/specs/mvp1-three-module-interface-2026-06-11/studio/step-2/task.md

硬约束：
- 只能改 task.md 允许的 Studio 文件和测试。
- 不得改 Engine/Gateway 生产代码，即不得改 `packages/graph-agent/**` 或 `packages/graph-agent-gateway/**`。
- 不得改 Studio run/predict/publish/golden/router 现有业务流，除非 task.md 明确允许。
- HTTP 本地模拟 harness 必须能触发传输族错误。
- 每个错误必须有专属 `error_code`。
- 只允许硬失败或显式降级，禁止静默降级。
- dev/prod 分层只允许用于完整性 hash not-found；本 Step 不实现 dev/prod missing hash 业务分层。
- publish 失败不能留下半成品；本 Step 只落 DTO/protocol，不实现完整 publish 原子链路。
- 不得改 FROZEN MVP1 文档。
- 不要为了过测写固定返回值 fake；local provider 必须有真实磁盘持久化和真实不变量检查。

当前 Step：
- Step 2 名称：Studio 接口定义 GREEN。
- 目标：把 Step 1 RED 的 Studio adapter/provider/harness/publish/golden 接口定义测试转为 GREEN。

已有 RED 测试和失败摘要：
- `apps/studio/backend/tests/core/adapters/test_productization_adapters.py`
  - 缺 `app.core.adapters.engine.EngineAdapter`
  - 缺 `app.core.adapters.gateway.GatewayAdapter`
  - 缺 `app.core.adapters.http_transport.HttpTransport`
  - 要求 adapters 支持 `transport="in_process"` 和 `transport="http_loopback"`
  - 要求 HTTP transport 发送 `Idempotency-Key` 并校验 `schema_version`
- `apps/studio/backend/tests/core/adapters/test_productization_local_providers.py`
  - 缺 `LocalGatewayConfigStore`
  - 缺 `LocalProductArtifactStore`
  - 缺 `LocalRuntimeStateStore`
  - 缺 `LocalRunArtifactStore`
  - 要求 error_code：`config.etag_conflict`、`artifact.hash_mismatch`、`state.lease_required`、`state.lease_fenced`、`artifact.sealed_write`
- `apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py`
  - 缺 `apps/studio/backend/tests/support/http_loopback_harness.py`
  - harness 必须注入 timeout、connection refused、5xx、malformed JSON、missing DTO fields、schema mismatch
  - harness 必须能启动两个共享存储的 worker
- `apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py`
  - 缺 `app.services.publish_pipeline.PublishArtifactRequest`
  - 缺 `app.services.golden_headless.GoldenHeadlessRequest`
  - publish request 必须有 `artifact_ref`、`release_version`、`idempotency_key`、`atomic_stage`
  - golden headless request 只接受 `run_results_ref + baseline_ref`，拒绝 `final_state` 等 legacy 字段

目标测试命令：

```bash
uv run pytest \
  apps/studio/backend/tests/core/adapters/test_productization_adapters.py \
  apps/studio/backend/tests/core/adapters/test_productization_local_providers.py \
  apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py \
  apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py \
  -q
```

同时运行 lint：

```bash
uv run ruff check \
  apps/studio/backend/app/core/adapters/engine.py \
  apps/studio/backend/app/core/adapters/gateway.py \
  apps/studio/backend/app/core/adapters/http_transport.py \
  apps/studio/backend/app/core/adapters/gateway_config_store_local.py \
  apps/studio/backend/app/core/adapters/run_artifact_store_local.py \
  apps/studio/backend/app/core/adapters/runtime_state_store_local.py \
  apps/studio/backend/app/core/adapters/product_store_local.py \
  apps/studio/backend/tests/support/http_loopback_harness.py \
  apps/studio/backend/tests/support/multi_worker_storage.py \
  apps/studio/backend/app/services/publish_pipeline.py \
  apps/studio/backend/app/services/golden_headless.py \
  apps/studio/backend/tests/core/adapters/test_productization_adapters.py \
  apps/studio/backend/tests/core/adapters/test_productization_local_providers.py \
  apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py \
  apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py
```

请实施最小改动使目标测试通过，并在回复中提供：
1. 修改文件列表。
2. 关键实现说明，特别说明哪些是接口/协议，哪些是 owner-side 最小真实路径。
3. 测试命令和结果。
4. 风险和未处理项。
5. 确认没有修改 Engine/Gateway 生产代码。
