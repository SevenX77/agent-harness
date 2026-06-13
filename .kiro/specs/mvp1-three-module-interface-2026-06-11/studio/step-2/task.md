# Studio Step 2: Interface Definition GREEN

## 目标

把 Studio Step 1 的接口定义 RED 测试转为 GREEN，建立 Studio 拥有的 adapter transport boundary、本地 provider、HTTP loopback harness、publish protocol DTO、golden headless DTO。

本步骤只完成接口定义和最小 owner-side 可执行路径，不迁移现有 run/predict/publish/golden/router 业务流。业务收口属于 Step 3/Step 4。

## 非目标

- 不修改 `packages/graph-agent/**` 生产代码。
- 不修改 `packages/graph-agent-gateway/**` 生产代码。
- 不迁移 Studio `run_manager.py` / `predictor.py` / `routers/*.py` 到新 adapter。
- 不实现 Step 3 的 HTTP retry/idempotency replay、event stream cursor、GRAPH roundtrip、publish atomicity 全链路。
- 不改 FROZEN MVP1 文档。
- 不把 provider 写成只为测试返回固定值的 fake。

## 允许修改的文件

- `apps/studio/backend/app/core/adapters/engine.py`
- `apps/studio/backend/app/core/adapters/gateway.py`
- `apps/studio/backend/app/core/adapters/http_transport.py`
- `apps/studio/backend/app/core/adapters/gateway_config_store_local.py`
- `apps/studio/backend/app/core/adapters/run_artifact_store_local.py`
- `apps/studio/backend/app/core/adapters/runtime_state_store_local.py`
- `apps/studio/backend/app/core/adapters/product_store_local.py`
- `apps/studio/backend/app/core/adapters/__init__.py`
- `apps/studio/backend/tests/support/http_loopback_harness.py`
- `apps/studio/backend/tests/support/multi_worker_storage.py`
- `apps/studio/backend/app/services/publish_pipeline.py`
- `apps/studio/backend/app/services/golden_headless.py`
- `apps/studio/backend/tests/core/adapters/test_productization_adapters.py`
- `apps/studio/backend/tests/core/adapters/test_productization_local_providers.py`
- `apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py`
- `apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py`

Test files above may only be changed for mechanical compatibility with the finalized interface. Do not weaken assertions.

## 禁止修改的文件

- `packages/graph-agent/**`
- `packages/graph-agent-gateway/**`
- `apps/studio/backend/app/services/run_manager.py`
- `apps/studio/backend/app/services/predictor.py`
- `apps/studio/backend/app/services/gateway_resolver.py`
- `apps/studio/backend/app/services/golden_diff.py`
- `apps/studio/backend/app/routers/**`
- `docs/**/*FROZEN*`
- `docs/development/FRONTEND_UI_SPEC.md`
- Any frontend file under `apps/studio/frontend/**`

If an implementation appears to require one of these files, stop and report the blocker to Codex instead of widening scope.

## RED 测试清单

Run:

```bash
uv run pytest \
  apps/studio/backend/tests/core/adapters/test_productization_adapters.py \
  apps/studio/backend/tests/core/adapters/test_productization_local_providers.py \
  apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py \
  apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py \
  -q --tb=short
```

Current RED summary:

- `app.core.adapters.engine.EngineAdapter` is missing.
- `app.core.adapters.gateway.GatewayAdapter` is missing.
- `app.core.adapters.http_transport.HttpTransport` is missing.
- `app.core.adapters.gateway_config_store_local.LocalGatewayConfigStore` is missing.
- `app.core.adapters.product_store_local.LocalProductArtifactStore` is missing.
- `app.core.adapters.runtime_state_store_local.LocalRuntimeStateStore` is missing.
- `app.core.adapters.run_artifact_store_local.LocalRunArtifactStore` is missing.
- `apps/studio/backend/tests/support/http_loopback_harness.py` is missing.
- `app.services.publish_pipeline.PublishArtifactRequest` is missing.
- `app.services.golden_headless.GoldenHeadlessRequest` is missing.

The expected GREEN result is that all four Step 1 test files pass without changing their semantics.

## GREEN-1 接口/协议任务

### 1. Common response and error shape

Create `apps/studio/backend/app/core/adapters/http_transport.py`.

Required constants and classes:

- `SCHEMA_VERSION = "studio.mvp1.v1"`
- `StudioAdapterError(Exception)` with:
  - `error_code: str`
  - `error_payload: dict[str, object]`
- `HttpTransport`
  - constructor: `base_url: str`, optional `http_client: httpx.Client`, optional `schema_version: str`
  - method: `post(path: str, payload: dict[str, object], *, idempotency_key: str | None = None) -> object`

Protocol rules:

- Send JSON payload to `base_url + path`.
- If `idempotency_key` is present, send header `Idempotency-Key`.
- Response body must be a `ResponseEnvelope` dict with `schema_version`, `ok`, and either `data` or `error_code` / `error_payload`.
- If response JSON cannot be decoded, raise `StudioAdapterError("transport.serialization_failed", ...)`.
- If envelope is not a dict or is missing required DTO fields, raise `StudioAdapterError("transport.serialization_failed", ...)`.
- If `schema_version` differs from the configured schema version, raise `StudioAdapterError("transport.schema_mismatch", ...)`.
- If HTTP request times out, raise `StudioAdapterError("transport.timeout", ...)`.
- If connection is refused/connect fails, raise `StudioAdapterError("transport.connection_refused", ...)`.
- If status code is `>= 500`, raise `StudioAdapterError("transport.http_5xx", ...)`.
- If envelope has `ok: false`, raise `StudioAdapterError(error_code, error_payload)`.
- If envelope has `ok: true`, return the `data` value.

### 2. EngineAdapter

Create `apps/studio/backend/app/core/adapters/engine.py`.

Required class:

- `EngineAdapter`
  - constructor accepts `transport: Literal["in_process", "http_loopback"]`
  - exposes public attribute `transport`
  - accepts optional `http_transport: HttpTransport`
  - methods: `compile`, `run_artifact`, `predict_artifact`, `resume`

Protocol rules:

- Reject unknown transport with `ValueError`.
- For `http_loopback`, each method delegates through `HttpTransport.post`.
- Use stable endpoint paths:
  - `/engine/compile`
  - `/engine/run_artifact`
  - `/engine/predict_artifact`
  - `/engine/resume`
- For `run_artifact`, `predict_artifact`, and `resume`, extract `idempotency_key` from the request payload when present and pass it as the HTTP header.
- For `in_process`, keep the adapter as a thin owner-side boundary. It may call injected callables or public SDK entrypoints lazily, but it must not import Engine internals at module import time and must not return hard-coded success data. If an owner-side primitive is not yet available, raise a `StudioAdapterError` with a specific error code such as `engine.operation_unavailable`.

### 3. GatewayAdapter

Create `apps/studio/backend/app/core/adapters/gateway.py`.

Required class:

- `GatewayAdapter`
  - constructor accepts `transport: Literal["in_process", "http_loopback"]`
  - exposes public attribute `transport`
  - accepts optional `http_transport: HttpTransport`
  - methods: `resolve_routes`, `materialize_role`, `project_route_state`, `decide_fallback`, `resolve_credential`

Protocol rules:

- Reject unknown transport with `ValueError`.
- For `http_loopback`, delegate through `HttpTransport.post`.
- Use stable endpoint paths:
  - `/gateway/resolve_routes`
  - `/gateway/materialize_role`
  - `/gateway/project_route_state`
  - `/gateway/decide_fallback`
  - `/gateway/resolve_credential`
- For `in_process`, keep the adapter thin and lazy. It may call injected gateway facade functions or public gateway APIs, but it must not import gateway concrete internals at module import time and must not silently return empty routes/fallbacks. If an owner-side primitive is unavailable, raise `StudioAdapterError("gateway.operation_unavailable", ...)`.

### 4. LocalGatewayConfigStore

Create `apps/studio/backend/app/core/adapters/gateway_config_store_local.py`.

Required shape:

- `ConfigRecord` dataclass or Pydantic model with `user_id`, `key`, `value`, `etag`.
- `LocalGatewayConfigStore(root: Path)`
- `get_config(user_id: str, key: str) -> ConfigRecord`
- `put_config(user_id: str, key: str, value: dict[str, object], if_match: str | None = None, if_none_match: str | None = None) -> ConfigRecord`

Protocol rules:

- Empty `user_id` or empty `key` raises `ValueError`.
- Persist records under `root` so multiple store instances with the same root share data.
- Compute a new etag whenever value changes.
- If `if_match` is supplied and does not match the existing etag, raise `StudioAdapterError("config.etag_conflict", ...)`.
- If `if_none_match == "*"` and a record already exists, raise `StudioAdapterError("config.etag_conflict", ...)`.
- Writes must be atomic at file level.

### 5. LocalProductArtifactStore

Create `apps/studio/backend/app/core/adapters/product_store_local.py`.

Required shape:

- `ArtifactRef` dataclass or Pydantic model with at least `artifact_id`, `content_hash`, `store`, `manifest_ref`.
- `LocalProductArtifactStore(root: Path)`
- `put(content: bytes, artifact_id: str, store: str = "product") -> ArtifactRef`
- `get(content_hash: str) -> bytes`
- `blob_path(content_hash: str) -> Path | str`

Protocol rules:

- `content_hash` format is `sha256:<hex digest>`.
- Store bytes by content hash.
- `get(hash)` recomputes the digest of stored bytes and raises `StudioAdapterError("artifact.hash_mismatch", ...)` if bytes are corrupted.
- Missing hash should raise a specific adapter error, for example `artifact.not_found`. Dev/prod missing hash behavior is Step 3/4 scope; do not silently recompile here.

### 6. LocalRuntimeStateStore

Create `apps/studio/backend/app/core/adapters/runtime_state_store_local.py`.

Required shape:

- `LeaseToken` dataclass or Pydantic model with `lease_id`, `owner_id`, `fencing_token`, `ttl_ms`, `safety_margin_ms`.
- `StateSnapshot` dataclass or Pydantic model with `run_id`, `state`, and the fencing token used.
- `LocalRuntimeStateStore(root: Path)`
- `acquire_lease(run_id: str, owner_id: str, ttl_ms: int) -> LeaseToken`
- `heartbeat(run_id: str, lease: LeaseToken) -> LeaseToken`
- `snapshot(run_id: str, state: dict[str, object], lease: LeaseToken | None) -> StateSnapshot`
- `restore(run_id: str) -> StateSnapshot`
- `release(run_id: str, lease: LeaseToken) -> None`

Protocol rules:

- `snapshot(..., lease=None)` raises `StudioAdapterError("state.lease_required", ...)`.
- Each acquired lease gets a monotonically increasing fencing token per run.
- A snapshot using an older fencing token than the current lease raises `StudioAdapterError("state.lease_fenced", ...)`.
- Persist state under `root`.

### 7. LocalRunArtifactStore

Create `apps/studio/backend/app/core/adapters/run_artifact_store_local.py`.

Required shape:

- `LocalRunArtifactStore(root: Path)`
- `begin_run(run_id: str) -> object`
- `put_batch(run_id: str, objects: list[dict[str, object]]) -> None`
- `seal_run(run_id: str) -> object`
- `get_object(content_hash: str) -> bytes`

Protocol rules:

- `put_batch` accepts objects with `path` and `content`.
- Once sealed, any later `put_batch` for the same run raises `StudioAdapterError("artifact.sealed_write", ...)`.
- Store object bytes content-addressed and make `get_object(hash)` verify hashes before returning.

### 8. HTTP loopback harness

Create:

- `apps/studio/backend/tests/support/http_loopback_harness.py`
- `apps/studio/backend/tests/support/multi_worker_storage.py`

Required `HttpLoopbackHarness` shape:

- Context manager with `__enter__` and `__exit__`.
- Constructor accepts `schema_version: str` and optional `storage_root: Path`.
- `route(path: str, data: dict[str, object], required_fields: tuple[str, ...] = ()) -> None`
- Injection methods:
  - `inject_timeout(path: str) -> None`
  - `inject_connection_refused(path: str) -> None`
  - `inject_5xx(path: str) -> None`
  - `inject_malformed_json(path: str) -> None`
  - `inject_missing_dto_fields(path: str) -> None`
  - `inject_schema_mismatch(path: str) -> None`
- `http_transport(schema_version: str) -> HttpTransport`
- `start_workers(count: int) -> tuple[...]`

Protocol rules:

- Use `httpx.MockTransport` or an equivalent local-only transport; no real network is required.
- The harness must trigger the same errors as production `HttpTransport`.
- Workers started by `start_workers(count=2)` must share the same storage root and expose `gateway_config_store`.
- Do not implement Step 3 event stream reconnect or idempotent replay here.

### 9. Publish and golden DTO contracts

Create `apps/studio/backend/app/services/publish_pipeline.py`.

Required shape:

- `PublishArtifactRequest` Pydantic model or dataclass requiring:
  - `artifact_ref`
  - `release_version`
  - `idempotency_key`
  - `atomic_stage`
- Reject missing required fields.
- Prefer Pydantic `extra="forbid"` if using Pydantic.

Create `apps/studio/backend/app/services/golden_headless.py`.

Required shape:

- `GoldenHeadlessRequest` Pydantic model or dataclass requiring:
  - `run_results_ref`
  - `baseline_ref`
- Reject `final_state`, `skill_id`, and any other extra field.
- Do not call or rewrite existing `golden_diff.py` in Step 2.

## GREEN-2 owner-side production path 任务

- Local providers must persist to disk under their configured `root`. In-memory dictionaries are acceptable only as per-instance locks/cache and cannot be the source of truth.
- Hash, etag, fencing, and seal checks must be real invariants, not test-specific branches.
- `HttpTransport` must use the same response envelope and error-code behavior when called by tests and by adapters.
- `EngineAdapter` and `GatewayAdapter` must be thin boundaries. They may use injected callables/facades for unavailable upstream primitives, but they must not fabricate successful owner results.
- If an upstream Engine/Gateway primitive is unavailable in the current repo, fail explicitly with `StudioAdapterError("<owner>.operation_unavailable", ...)` rather than silently degrading.
- `publish_pipeline.py` and `golden_headless.py` should only introduce DTO/protocol surface in Step 2. Full publish atomicity and full golden evaluator integration remain Step 4 scope.

## 验证命令

Run the exact Step 2 target tests:

```bash
uv run pytest \
  apps/studio/backend/tests/core/adapters/test_productization_adapters.py \
  apps/studio/backend/tests/core/adapters/test_productization_local_providers.py \
  apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py \
  apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py \
  -q
```

Run focused lint on changed files:

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

Optional broader Studio backend smoke:

```bash
uv run pytest apps/studio/backend/tests/core/adapters apps/studio/backend/tests/services/test_artifact_registry.py -q
```

Expected Step 2 result:

- Step 1 target tests pass.
- Ruff passes for changed Python files.
- No `packages/graph-agent/**` or `packages/graph-agent-gateway/**` production changes.

## 回滚范围

If Codex rejects Step 2 implementation, revert only:

- Files listed in "允许修改的文件" that were changed for Step 2.
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/studio/step-2/task.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/studio/step-2/gemini-prompt.md`

Do not revert Step 1 RED tests unless Codex explicitly asks for a RED redesign.
