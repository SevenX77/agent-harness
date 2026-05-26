# Tasks: LLM Provider Intelligence V2 Hard Cutover

本文档把 Claude audit 中的问题拆成两类：需要写进设计契约的内容，以及实现阶段要执行的任务。实现必须对齐 `requirements.md`、`design.md` 和 `docs/engine/graph-agent-gateway/mvp0-alignment.md`，不做旧 `models/providers/roles` schema、旧 Studio DTO、旧 Engine-owned client manager 的向后兼容。

## Audit Disposition

| Audit item | Classification | Decision |
|---|---|---|
| M1 gateway 反向依赖 `graph_agent` internals | Design + Task | 设计已规定 Gateway 自拥有 events/exceptions/predict/client manager；任务中先拆包边界。 |
| M2 Engine `graph_agent/config/llm_config.py` 漏列 | Design + Task | 设计已列入 Engine 影响面；任务中删除其生产 import。 |
| M3 gateway 旧 `llm_config.py` 与新 registry 冲突 | Design + Task | 设计已规定 registry 接管 schema；任务中重写或退役旧 `llm_config.py`。 |
| M4 `gateway/factory.py` env fallback | Design + Task | 设计已规定从 runtime surface 移除；任务中取消 re-export 或删除。 |
| M5 v3 credentials 切换策略 | Design + Task | 设计规定旧 schema fatal，不做 runtime migration；任务中实现 schema guard 和恢复说明。 |
| M6 uppercase/short-code endpoint IDs | Task | 通过新 schema seed/import 时生成 lowercase endpoint IDs；旧 role 文件不进 runtime。 |
| M7 `ProviderImportDraft` schema 缺失 | Design + Task | 设计已补独立 draft store schema；任务中实现 DTO/store/API。 |
| M8 frontend canonicalization 仍在 `role-utils.ts` | Design + Task | 设计和 UI spec 已规定由 backend DTO 提供；任务中删除前端推断逻辑。 |
| M9 frontend autosave/test hooks 漏列 | Task | 纳入 frontend cutover task affected files。 |
| M10 old `/api/llm/providers/*` 路由去向 | Design + Task | 设计已规定替换/删除；任务中移除旧 contract。 |
| M11 `model_override` route_id 边界 | Design + Task | 设计规定 route_id override；任务中更新 core types、schema validation、resolver error。 |
| M12 `gateway_resolver.py` / `llm_env.py` / `migrations.py` | Task | 纳入 backend cutover，删除旧 env patch 和 runtime migration reader。 |
| M13 `ResolvedRoute.api_key` 类型与 runtime fields | Design + Task | 设计已补 `SecretStr`、timeout/trust_env/proxy_env/fingerprint；任务中实现。 |
| G1 capability vendor tree squash | Design + Task | 设计已规定 normalizer 和 raw metadata 仅诊断；任务中实现 known-field mapper。 |
| G2 lint missing 语义 | Design + Task | 设计已规定 `error + missing` 为 blocking `requires_probe`。 |
| G3 error classifier | Design + Task | 设计已规定 `registry.error_classification`；任务中实现分类测试。 |
| G4 ModelProfile reapply conflict | Design + Task | 设计已规定 409 conflict + explicit replace，无 merge mode。 |
| G5 credential fingerprint | Design + Task | 设计已规定 fingerprint inputs；任务中复用 gateway helper。 |
| G6 tests/CI gaps | Task | 纳入 verification phase。 |
| G7 peer/single/circuit fate | Design + Task | 设计规定 peer/single 删除，runtime_policy 接管 health knobs；任务中删除 parser。 |
| G8 UI spec canonicalization rule | Design + Task | `FRONTEND_UI_SPEC.md` 已更新；任务中实施前端删除。 |
| G9 API Keys → Endpoints wording | Superseded by API Keys regression amendment | 不再强制把用户界面改名为 Endpoints；endpoint/route 保留为内部 registry 概念。 |
| G10 old specs superseded | Design | `design.md` 顶部已声明 supersedes。 |

## Round 2 Audit Disposition

| Audit item | Classification | Decision |
|---|---|---|
| N1 `runtime_policy` schema/传递路径 | Design + Task | 补 `RuntimePolicy` schema、`RegistrySnapshot.runtime_policy`、`ResolvedRole.runtime_policy` 和 client manager plumbing。 |
| N2 `system_prompt_prefix` 出口缺失 | Design + Task | 不放进 `ResolvedRoute`；新增 `ResolvedRole.system_prompt_prefix`，由 `GatewayChatModel` 使用。 |
| N3 v3→v4 恢复路径 | Task | 增加 bootstrap 文档和 example；missing v4 文件返回 empty registry + setup 状态，legacy v3 fatal 带文档链接。 |
| N4 endpoint_id 命名规则 | Design + Task | 设计补命名表；任务补 seed/cutover mapping 文档。 |
| N5 DELETE APIs | Design + Task | 补 endpoint/route/profile delete API 和引用冲突规则；任务纳入 router/backend/frontend。 |
| N6 fingerprint helper source of truth | Design + Task | Gateway helper 接管 backend fingerprint。 |
| N7 lint key 映射 | Design + Task | 补 lint key → capability key 映射表；任务纳入 linter tests。 |
| N8 invalid heredoc acceptance | Task | 改为 `python -c`。 |
| N9 grep acceptance 命中 spec 自身 | Task | 改成代码路径扫描，排除 docs/spec/test false positives。 |
| N10 exception hierarchy tests | Task | Gateway exception cutover 后追加 graph-agent exception/fallback tests。 |
| N11 fuzzy graph-agent test gate | Task | 改成 pytest 必须退出 0；删除旧行为测试要在 PR 描述列理由。 |
| N12 no-env smoke isolation | Task | 明确 monkeypatch 删除所有 provider env keys。 |
| N13 ImportDraft enum/probe/field_sources | Design + Task | 补完整 draft DTO shape 和测试。 |
| N14 multi-endpoint draft | Design + Task | `endpoint_candidates` 支持多 endpoint，route candidate 绑定 endpoint_id。 |
| N15 `data/llm_providers/*.md` fate | Task | cleanup phase 必须归档或迁入 registry seed。 |
| N16 old flow doc | Task | cleanup phase 必须 archive/rewrite `LLM_MODEL_CONFIGURATION_FLOW.md`。 |
| N17 tasks 5.6 directory ambiguity | Superseded by API Keys regression amendment | 不强制 renamed `endpoints/` 目录；API Keys/provider UI 可继续使用 `api-keys/` feature directory。 |
| N18 `system_prompt_prefix` type | Design + Task | schema 明确 string default `""`，`null` invalid。 |
| N19 YAML `off` parse risk | Design | examples quote lint values。 |
| N20 Role API paths | Design + Task | 补 GET/PUT role paths。 |

## Round 3 Audit Disposition

| Audit item | Classification | Decision |
|---|---|---|
| R1 mvp0 registry list missing `error_classification.py` | Task | 同步到 mvp0 alignment。 |
| R2 empty exception test acceptance | Task | 要求先 grep 至少一个相关测试，再跑 targeted pytest。 |
| R3 role PUT semantics | Design + Task | 明确 map upsert、single role full replace、frontend per-role serialized saves。 |
| R4 runtime_policy scope | Design + Task | 明确只接管 TTL/timeout/retry-rounds；retry status/finish reasons 留 client manager/classifier 常量。 |
| R5 deleted profile marker schema | Design + Task | 补 `deleted_at` / `deleted_marker`。 |
| R6 runtime_policy file ownership wording | Design | 明确顶层 block 位于 `<studio_config_dir>/llm/llm_credentials.json`，snapshot 只是内存镜像。 |
| R7 cache key vs fingerprint asymmetry | Design + Task | 明确 runtime_policy 影响 runtime cache，不影响 credential fingerprint/provider-test cache。 |
| R8 mvp0 deleted-profile wording | Task | 同步 mvp0 alignment。 |
| R9 import draft same endpoint update behavior | Design + Task | 同 endpoint draft 不 auto-promote，必须显式 diff/merge/delete-first。 |
| R10 canonical rules seed file | Task | Phase 6.7 创建 gateway package default rules；repo `config/llm_canonical_rules.yaml` 仅可作为 seed/example fixture，active override 放 `<studio_config_dir>/llm/` 或显式 env path。 |
| R11 endpoint PUT semantics | Design + Task | 明确 endpoint PUT 是 upsert，删除只能走 DELETE。 |
| R12 REQ-13 verification alignment | Requirements + Task | 补 delete conflict、RuntimePolicy、lint mapping 测试项。 |

## Round 4 Audit Disposition

| Audit item | Classification | Decision |
|---|---|---|
| S1 missing route metadata edit API | Design + Task | 补 `PUT /api/llm/routes/{route_id}`，只允许改 metadata/display/capability/status，route identity 不可变。 |
| S2 request/response JSON examples | Task | Phase 4 router 实现前必须在 design §8.x 补 endpoint/route/delete/profile conflict examples，并用 router tests 固化。 |
| S3 disposition/task double pointers | Task | 保持为文档维护提醒；后续改 spec 时同步 disposition 与具体 task。 |

## Runtime Settings / Provider Matrix Disposition

| Item | Classification | Decision |
|---|---|---|
| C1 repo-root `config/` as active runtime state | Design + Task | Active credentials/roles/canonical overrides move to `<studio_config_dir>/llm/*` or explicit env override. Repo `config/` may remain only as seed/example/package fixture, never hard-coded runtime state. |
| C2 capability vs user runtime setting conflation | Design + Task | Add fixed normalized `RuntimeSettings` schema and resolver-produced `effective_runtime_settings`; capabilities gate display/validation/defaults but are not user settings. |
| C3 missing runtime setting fallback defaults | Design + Task | Default chain is route entry → profile default → route capability default → protocol default → Studio safe default, with per-field source metadata in diagnostics/tracing. |
| C4 dynamic vs fixed runtime setting UI/schema | Design + Task | Backend/gateway use fixed schema; frontend may dynamically show/disable controls from capabilities but cannot invent arbitrary runtime keys. |
| C5 provider/model parameter pattern testing | Design + Task | Add protocol matrix tests covering same official family, same canonical model across providers, positive probes, negative boundary probes, and route-local capability storage. |
| C6 Volcengine Ark official SDK | Design + Task | Add `ark_runtime` protocol adapter and live/local tests comparing official Ark SDK behavior with the existing Ark OpenAI-compatible path when credentials are present. |

## Frontend Guardrails

- 修改 `apps/studio/frontend` 前必须阅读 `docs/development/FRONTEND_UI_SPEC.md` §2。
- 优先复用 `apps/studio/frontend/src/components/ui/` 下的 shadcn/Radix wrapper。
- 所有可见 UI 变更完成前必须启动 Studio 前端或 Tauri shell 手动检查 Settings → API Keys / LLM Roles / Model Profiles / Available Routes。
- Frontend 不再做 raw model string canonicalization、provider ownership inference、stale provider pruning；这些只能来自 backend DTO。

## Phase 0: Cutover Preparation

**目标**: 在改代码前清楚锁定硬切边界，避免实现时走回兼容路线。

- [x] 0.1 确认当前分支没有未提交实现代码混入本 spec 变更。
  - Run: `git status --short`
  - Acceptance: 仅包含本 spec/docs 相关变更，或先分批 commit 文档。
- [x] 0.2 建立 cutover 失败策略。
  - Modify: `.kiro/specs/llm-provider-intelligence-v2/design.md` 若后续发现新冲突，只能补硬切规则，不新增 legacy schema reader。
  - Acceptance: spec/docs may mention old paths only as removed/forbidden behavior; no runtime task may introduce old schema readers, compatibility DTOs, or compatibility wrappers.
- [x] 0.3 建立 commit 分层。
  - Commit 1: Gateway shared primitives and registry schema.
  - Commit 2: Gateway resolver/runtime/client manager hard cutover.
  - Commit 3: Studio backend storage/API hard cutover.
  - Commit 4: Studio frontend Endpoints/Routes/Profile UI cutover.
  - Commit 5: Verification/docs cleanup.
- [x] 0.4 准备 v4 bootstrap recovery docs。
  - Create: `docs/development/CREDENTIALS_V4_BOOTSTRAP.md`
  - Create: checked-in example credentials/roles files under an appropriate docs or config examples directory.
  - Define startup behavior: missing v4 credentials returns empty registry plus setup-required status; detected legacy v3 config fails with actionable schema error and doc link.
  - Acceptance: backend tests cover missing file, empty first-run registry, and legacy v3 fatal error.

## Phase 1: Gateway Package Boundary

**目标**: 先让 `graph-agent-gateway` 不再依赖 `graph_agent` execution internals，为 registry/runtime 迁移提供干净边界。

- [x] 1.1 新增 Gateway-owned event DTO。
  - Create: `packages/graph-agent-gateway/src/graph_agent_gateway/events.py`
  - Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py`
  - Move/define: `LLMFallbackEvent` payload fields `phase_name`, `from_provider`, `to_provider`, `reason`, `code`, `context`.
  - Acceptance: `rg -n "from graph_agent.callbacks.events" packages/graph-agent-gateway/src` 无结果。
- [x] 1.2 让 Gateway exceptions 不继承 Engine `ExecutionError`。
  - Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py`
  - Remove import: `graph_agent.core.exceptions`.
  - Keep fields: `code`, `context`, stable message string.
  - Acceptance: `pytest packages/graph-agent-gateway/tests/test_all_providers_failed_error.py packages/graph-agent-gateway/tests/test_gateway_integration.py -q` 通过.
  - Acceptance: `rg -n "def test_.*(exception|error|fallback)" packages/graph-agent/tests` 至少 1 条命中。
  - Acceptance: `pytest packages/graph-agent/tests -q -k "exception or error or fallback"` 通过。
- [x] 1.3 清理 Predict mock 反向 import。
  - Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`
  - Ensure Predict path uses `graph_agent_gateway.predict_interception.PredictGatewayChatModel` or injected strategy only.
  - Acceptance: `rg -n "graph_agent.core._predict_internal" packages/graph-agent-gateway/src` 无结果。
- [x] 1.4 处理 `factory.py` env fallback。
  - Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py`
  - Delete or de-export: `graph_agent_gateway.factory`.
  - If kept for tests, keep it outside public runtime imports and document as test helper.
  - Acceptance: `uv run python -c "import graph_agent_gateway; print(hasattr(graph_agent_gateway, 'factory'))"` 输出 `False`。

## Phase 2: Gateway Registry Core

**目标**: 建立 endpoint/route/profile/role/draft/lint 的纯数据层，不接入 SDK client。

- [x] 2.1 新建 registry package。
  - Create:
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/__init__.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/error_classification.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/probe_contracts.py`
  - Acceptance: `python -c "import graph_agent_gateway.registry"` succeeds.
- [x] 2.2 实现 schema models。
  - Define in `schema.py`: `ProviderEndpoint`, `ProviderRoute`, `CapabilityValue`, `RuntimePolicy`, `RoleRouteEntry`, `ModelProfile`, `RoleEntry`, `ProviderImportDraft`, `RegistrySnapshot`, `ResolvedRole`, `ResolvedRoute`, `LintRequirement`, `LintResult`.
  - Use `SecretStr` for runtime `ResolvedRoute.api_key`.
  - `ResolvedRole` carries `system_prompt_prefix: str`, `runtime_policy: RuntimePolicy`, route chain, lints, and optional profile trace metadata.
  - `source_profile_snapshot` supports `deleted_at` and `deleted_marker` for deleted-profile UI traceability.
  - `ProviderImportDraft` includes status enum, `endpoint_candidates`, `route_candidates`, `probe_results`, and field-source records.
  - Validate `endpoint_id`, `route_slug`, `route_id`, `model_profile_id`.
  - Acceptance: new tests in `packages/graph-agent-gateway/tests/test_registry_schema.py` cover valid/invalid IDs, secret serialization, runtime policy defaults/ranges, draft enums, multi-endpoint drafts, and `system_prompt_prefix` null rejection.
- [x] 2.3 Implement canonical mapper.
  - Define confidence classes: `transport_normalized`, `explicit_alias`, `orphan`.
  - Forbid fuzzy merges of `latest`, dated snapshots, `fast`, `thinking`, and provider variants unless explicit alias exists.
  - Acceptance: `pytest packages/graph-agent-gateway/tests/test_registry_canonical.py -q` covers positive and negative cases.
- [x] 2.4 Implement capability normalizer and linter.
  - Known keys: `max_input_tokens`, `max_output_tokens`, `thinking_protocol`, `tool_protocol`, `structured_output_protocol`, `vision`.
  - Implement explicit lint key mapping: `thinking` → `thinking_protocol`, `tool_calling` → `tool_protocol`, `structured_output` → `structured_output_protocol`, `vision` → `vision`, token keys to themselves.
  - `error + missing/unverified` returns blocking `requires_probe`.
  - `warn + missing` returns non-blocking warning.
  - Acceptance: `pytest packages/graph-agent-gateway/tests/test_registry_lint.py -q`.
- [x] 2.5 Implement registry resolver.
  - Input: `RegistrySnapshot`, role name or route override.
  - Output: `ResolvedRole` with role metadata, runtime policy, and ordered `ResolvedRoute` records.
  - Validate endpoint, route status, credential presence, lints.
  - Plumb `RegistrySnapshot.runtime_policy` into `ResolvedRole.runtime_policy`.
  - Never search by capability, availability, provider, price, or latency.
  - Acceptance: `pytest packages/graph-agent-gateway/tests/test_registry_resolver.py -q`.
- [x] 2.6 Implement error classifier.
  - Map `httpx.ConnectError`, `httpx.TimeoutException`, retryable 5xx, rate limits, marked-down route to fallback.
  - Map missing credential, auth failure, bad request, unknown model, unsupported capability, schema/config error to fail-fast.
  - Acceptance: `pytest packages/graph-agent-gateway/tests/test_registry_error_classification.py -q`.

## Phase 3: Gateway Runtime Hard Cutover

**目标**: 让 runtime 通过 explicit registry snapshot 执行 route chain，不再依赖 `.env`、旧 roles schema、旧 Engine client manager。

- [x] 3.1 Move `LLMClientManager` into Gateway.
  - Move: `packages/graph-agent/src/graph_agent/models/llm_client_manager.py` → `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py`
  - Update imports to use gateway schema/runtime DTOs.
  - Replace old class constants for probe down TTL, probe timeout, and token escalation with `ResolvedRole.runtime_policy`.
  - Cache key includes endpoint ID, credential fingerprint, timeout, trust/proxy settings, and relevant runtime policy values.
  - Runtime policy changes invalidate runtime client cache but not credential-fingerprint provider-test cache.
  - Delete Engine production import path; do not leave compatibility wrapper.
  - Acceptance: `rg -n "graph_agent.models.llm_client_manager" packages apps config` only appears in deleted-code references or no results.
- [x] 3.2 Remove Engine LLM config loader from production imports.
  - Remove production usage of `packages/graph-agent/src/graph_agent/config/llm_config.py`.
  - Update `packages/graph-agent/src/graph_agent/cognitive/prompt.py` so it does not read role config directly.
  - Acceptance: `rg -n "graph_agent.config.llm_config" packages/graph-agent/src apps/studio/backend/app` no production results.
- [x] 3.3 Rewrite `graph_agent_gateway.resolver.ModelResolver`.
  - Constructor accepts explicit `RegistrySnapshot` or explicit credentials/roles paths.
  - No `_load_default_roles_data`.
  - No built-in model defaults.
  - No env key fallback.
  - `model_override` means explicit `route_id`.
  - Acceptance: gateway resolver tests cover missing snapshot/path, old schema fatal, route override success/failure.
- [x] 3.4 Update `GatewayChatModel`.
  - Consume `ResolvedRole` with route-backed resolved candidates.
  - Apply role-specific `ResolvedRole.system_prompt_prefix` without Engine reading role files.
  - Emit diagnostics with `route_id`, `endpoint_id`, `provider_model_id`, `canonical_id`, protocol, fallback decision.
  - Use error classifier for fallback vs fail-fast.
  - Emit `unclassified_default: true` when the classifier uses the default fail-fast path.
  - Acceptance: `pytest packages/graph-agent-gateway/tests/test_llm_fallback_event.py packages/graph-agent-gateway/tests/test_gateway_integration.py -q`.
- [x] 3.5 Runtime no-env smoke.
  - Remove LLM API keys from test environment for smoke path using `monkeypatch.delenv(..., raising=False)` for every provider key the repo recognizes.
  - Build resolver from temp credentials/roles files with in-file secret.
  - Use fake client manager to avoid real provider call.
  - Acceptance: new integration test proves no `.env` lookup is required.
- [x] 3.6 Resolve Engine chat models per phase role.
  - Modify: `packages/graph-agent/src/graph_agent/core/runner.py`
  - Modify: `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - V0.3/V2.1 graph assembly must pass each executable phase's `llm_role` to `ModelResolver.resolve`.
  - It must not pre-resolve a workflow-level model with `role_name=None`.
  - Acceptance: `test_agent_phase_react_loop_uses_injected_model_resolver` asserts resolver receives the phase `llm_role` and phase ID.

## Phase 4: Studio Backend Storage and API

**目标**: Studio Backend becomes the product orchestration layer over `graph_agent_gateway.registry`.

- [x] 4.1 Replace backend LLM models.
  - Modify: `apps/studio/backend/app/models/llm_config.py`
  - Replace v3 `LLMCredentialsFile.providers` with v4 endpoint/route DTOs.
  - Add model profile, runtime policy, role route chain, lint result, import draft DTOs from gateway registry or thin API wrappers.
  - Acceptance: backend model tests cover secret redaction and schema-version fatal for old v3.
- [x] 4.2 Rewrite credential storage.
  - Modify: `apps/studio/backend/app/services/llm_credentials.py`
  - Active credentials file contains endpoints/routes/runtime policy only.
  - Drafts are not stored in active credentials.
  - Atomic write and single write lock remain.
  - Replace `provider_test_params_fingerprint` with `graph_agent_gateway.registry.storage.compute_credential_fingerprint(endpoint, secret)`.
  - Acceptance: tests verify omitted `api_key` keeps current secret, redacted placeholders are never stored, and explicit empty string clears the secret for Settings autosave.
  - Acceptance: backend provider-test result fingerprints match gateway runtime client fingerprints for the same endpoint/secret.
- [x] 4.3 Add import draft store.
  - Create: `apps/studio/backend/app/services/llm_import_drafts.py`
  - Store shape matches `ProviderImportDraft`.
  - Support create/read/probe/apply, status transitions, multiple endpoint candidates, route candidates keyed by route ID, probe result shape, expiration, conflict diff, concurrent write protection.
  - Drafts with an `endpoint_id` matching an active endpoint require explicit per-field merge, discard, or delete-active-first choice; no auto-promote.
  - Acceptance: tests cover draft enum validation, multi-endpoint draft, expired draft apply rejection, and concurrent apply conflict.
- [x] 4.4 Rewrite role storage.
  - Modify: `apps/studio/backend/app/services/llm_roles.py`
  - Schema v2 only: `model_profiles` and `roles[*].fallback_chain`.
  - `system_prompt_prefix` is a string defaulting to `""`; `null` is invalid.
  - Quote or serialize lint values as string enum values `"off"`, `"warn"`, `"error"`.
  - Old `models/providers/active_model/model_fallback/peer_model_groups/single_model_roles/circuit_breaker` fail validation.
  - Acceptance: tests prove old short-code YAML returns actionable schema error.
- [x] 4.5 Rewrite gateway resolver bridge.
  - Modify: `apps/studio/backend/app/services/gateway_resolver.py`
  - Build `RegistrySnapshot` from active credentials + roles.
  - Return `graph_agent_gateway.ModelResolver`.
  - Acceptance: `run_manager.py` uses this resolver without env patching.
- [x] 4.6 Delete old env patch and old migration runtime paths.
  - Modify/delete: `apps/studio/backend/app/services/llm_env.py`
  - Modify: `apps/studio/backend/app/services/migrations.py`
  - Runtime must not mutate `os.environ`.
  - Acceptance: `rg -n "patch_environment_from_credentials|os.environ\\[" apps/studio/backend/app/services packages/graph-agent-gateway/src` has no runtime env injection.
- [x] 4.7 Replace LLM router endpoints.
  - Modify: `apps/studio/backend/app/routers/llm.py`
  - Add: `GET /api/llm/registry`
  - Add: `PUT /api/llm/registry/endpoints` as endpoint upsert; absent endpoint IDs are retained.
  - Add: `DELETE /api/llm/registry/endpoints/{endpoint_id}`
  - Add: `POST /api/llm/endpoints/{endpoint_id}/test`
  - Add: `POST /api/llm/routes/{route_id}/probe`
  - Add: `PUT /api/llm/routes/{route_id}` as full replace for route editable metadata; `route_id`, `endpoint_id`, and `provider_model_id` are immutable.
  - Add: `DELETE /api/llm/routes/{route_id}`
  - Add: import draft create/read/probe/apply endpoints
  - Add: `GET/PUT /api/llm/roles` as roles-map upsert; absent roles are retained.
  - Add: `GET/PUT /api/llm/roles/{role_name}` as full replace for one role.
  - Add: `GET/PUT /api/llm/model-profiles`
  - Add: `DELETE /api/llm/model-profiles/{model_profile_id}`
  - Add: `POST /api/llm/roles/{role_name}/apply-profile`
  - Delete endpoints return `409 *_in_use` with reference lists when role/profile chains still reference the target.
  - Profile delete clears dangling `source_profile_id`, sets snapshot `deleted_at`, and sets `deleted_marker: true`.
  - Before implementation, add request/response JSON examples to `design.md` §8.x for endpoint upsert, route update, route probe, delete conflicts, and profile-apply conflicts.
  - Remove production contract for `providers/test`, `providers/test-models`, `providers/notable-models`.
  - Acceptance: router tests cover new endpoints, documented request/response shapes, conflict payloads, and old endpoints hard-cutover behavior.
- [x] 4.8 Update Copilot provider resolution.
  - Modify: `apps/studio/backend/app/services/copilot.py`
  - Resolve through route IDs and Gateway registry.
  - Remove imports from `graph_agent.config.llm_config`.
  - Acceptance: Copilot tests use route-backed registry fixtures.

## Phase 5: Studio Frontend Cutover

**目标**: UI moves to v4 endpoint/route data contracts while preserving the restored API Keys/provider UX. Roles continues to use route-backed Model Profiles / Available Routes.

- [x] 5.1 Update API types and clients.
  - Modify: `apps/studio/frontend/src/api/llm.ts`
  - Replace credentials v3 / roles v3 DTOs with registry, endpoint, route, model profile, role chain, lint, draft DTOs.
  - Acceptance: `cd apps/studio/frontend && npm run typecheck` reaches only component errors before components are updated.
- [x] 5.2 Rewrite autosave hooks.
  - Modify:
    - `apps/studio/frontend/src/hooks/useDebouncedCredentialsSave.ts`
    - `apps/studio/frontend/src/hooks/useDebouncedRolesSave.ts`
    - `apps/studio/frontend/src/hooks/useRoleTestChainRunner.ts`
  - Endpoints save via registry endpoint API.
  - Roles save route-chain schema.
  - Manual model test uses endpoint-scoped model test and refreshes from returned registry.
  - Acceptance: hook tests cover stale result suppression and serialized saves.
- [x] 5.3 Preserve API Keys UX over endpoint-backed storage.
  - Modify:
    - `apps/studio/frontend/src/components/studio/settings/api-keys/*`
    - `apps/studio/frontend/src/components/studio/api-keys/*`
    - `apps/studio/frontend/src/components/studio/settings/provider-utils.ts`
  - UI copy may continue to use API Keys/provider language for the Settings page.
  - Endpoint and route names stay in API DTOs, tests, and engineering docs.
  - Acceptance: component tests assert restored API Keys/provider copy, while data projection comes from v4 registry endpoints/routes.
- [x] 5.4 Rewrite LLM Roles data utilities.
  - Modify: `apps/studio/frontend/src/components/studio/settings/role-utils.ts`
  - Remove frontend raw model canonicalization.
  - Remove provider ownership inference.
  - Remove stale provider pruning based on frontend model strings.
  - Keep only pure role-chain operations over backend-provided route/profile DTOs.
  - Acceptance: `role-utils` tests prove route IDs are preserved and no raw model IDs are converted.
- [x] 5.5 Update LLM Roles UI.
  - Modify:
    - `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx`
    - `apps/studio/frontend/src/components/studio/settings/llm-roles/*`
  - Add Model Profiles area.
  - Available Routes grouped by backend `canonical_id`.
  - Drag/drop payload carries exact `route_id`.
  - Preserve pointer fallback, drag preview, drop shield, pointerup click suppression.
  - Acceptance: tests cover add route, reorder route, apply profile, apply conflict UI, lint badges.
- [x] 5.6 Add Import Draft UI.
  - Modify or create components under the relevant API Keys/provider feature directory; do not rename the user-facing page to Endpoints as part of this task.
  - Show draft diff, verified/unverified candidates, conflicts, apply confirmation.
  - Acceptance: tests cover draft diff rendering and apply disabled states.
- [x] 5.7 Manual frontend verification.
  - Run: `cd apps/studio/tauri && cargo tauri dev`
  - Verify Settings → API Keys: create/edit provider, omit API key, endpoint test, manual model test.
  - Verify Settings → LLM Roles: model profile card, apply profile, route drag/drop, lint warning/error, narrow width.
  - Acceptance: record manual verification results in final delivery notes.

## Phase 6: Verification and Cleanup

**目标**: Merge 前证明 hard cutover 完整、无旧 runtime 路径、无前端本地 canonicalization。

- [x] 6.1 Run gateway tests.
  - Run: `pytest packages/graph-agent-gateway/tests -q`
  - Expected: all pass.
- [x] 6.2 Run graph-agent tests affected by resolver protocol.
  - Run: `pytest packages/graph-agent/tests -q`
  - Expected: pytest exits 0. If any test still references the old short-code schema, update it to route IDs in the same PR; tests deleted because they covered removed behavior are listed in the PR description with rationale.
- [x] 6.3 Run backend tests.
  - Run: `cd apps/studio/backend && pytest`
  - Expected: all pass.
- [x] 6.4 Run frontend checks.
  - Run:
    - `cd apps/studio/frontend && npm run typecheck`
    - `cd apps/studio/frontend && npm run lint`
    - `cd apps/studio/frontend && npm run test`
    - `cd apps/studio/frontend && npm run build`
  - Expected: all pass.
- [x] 6.5 Static hard-cutover scans.
  - Run: `rg -n --glob '!**/*test*' --glob '!**/*.bak' "graph_agent.config.llm_config|graph_agent.models.llm_client_manager|patch_environment_from_credentials|api_key_env|providers/test-models|providers/notable-models" packages/graph-agent*/src apps/studio/backend/app apps/studio/frontend/src docs/development/examples/llm_roles.v2.example.yaml`
  - Expected: no production runtime references. Test names or archived docs are acceptable only when explicitly asserting deletion.
- [x] 6.6 No-env runtime smoke.
  - Run a short Graph Agent flow with temp credentials/roles files and no `.env` provider keys.
  - Expected: resolver creates route-backed `GatewayChatModel`; fake client receives endpoint credential from `ResolvedRoute`.
- [x] 6.7 Documentation cleanup.
  - Update `docs/engine/graph-agent-gateway/mvp0-alignment.md` if implementation changes any package boundary.
  - Update `docs/development/FRONTEND_UI_SPEC.md` if UI verification reveals a reusable rule.
  - Archive or rewrite `docs/development/LLM_MODEL_CONFIGURATION_FLOW.md` to match the V2 endpoint/route registry flow.
  - Decide fate of `apps/studio/backend/app/data/llm_providers/*.md`: archived under `docs/development/llm_provider_notes/` as import-draft reference material, not runtime source.
  - Create package-default canonical rules inside `graph_agent_gateway.registry` and keep any checked-in `config/llm_canonical_rules.yaml` as a seed/example fixture only; active overrides use `<studio_config_dir>/llm/llm_canonical_rules.yaml` or `STUDIO_LLM_CANONICAL_RULES_PATH`.
  - Add endpoint_id seed/cutover naming table to bootstrap docs.
  - Acceptance: `git diff --check` passes and spec/docs do not claim runtime support for the old short-code schema.

## Phase 7: Config Location and Runtime Settings Backend

**目标**: 先完成后端/网关的数据契约，不动前端视觉实现。Active LLM config 离开 repo-root `config/`，runtime settings 变成固定 normalized schema，并能解析默认值、校验能力、输出 tracing。

- [x] 7.1 Move active LLM config path resolution into Studio config dir.
  - Modify:
    - `apps/studio/backend/app/services/llm_credentials.py`
    - `apps/studio/backend/app/services/llm_import_drafts.py`
    - `apps/studio/backend/app/services/llm_roles.py`
    - `apps/studio/backend/app/services/gateway_resolver.py`
    - `apps/studio/backend/app/services/copilot.py`
    - `apps/studio/backend/app/routers/llm.py`
    - `apps/studio/backend/app/models/llm_config.py`
  - Add helpers that resolve:
    - `STUDIO_LLM_CREDENTIALS_PATH` or `<config.APP_SETTINGS_DIR>/llm/llm_credentials.json`
    - `STUDIO_LLM_ROLES_PATH` or `<config.APP_SETTINGS_DIR>/llm/llm_roles.yaml`
    - `STUDIO_LLM_IMPORT_DRAFTS_PATH` or `<config.APP_SETTINGS_DIR>/llm/llm_import_drafts.json`
    - `STUDIO_LLM_CANONICAL_RULES_PATH` or `<config.APP_SETTINGS_DIR>/llm/llm_canonical_rules.yaml`
  - Remove hard-coded `config.REPO_ROOT / "config" / "llm_roles.yaml"` from production code.
  - Acceptance: backend tests prove `STUDIO_CONFIG_DIR` redirects all default LLM files into a temp app settings dir, and explicit `STUDIO_LLM_*_PATH` overrides win.
  - Acceptance: `rg -n "REPO_ROOT / \"config\" / \"llm_roles.yaml\"|Path.home\\(\\) / \"\\.studio\"" apps/studio/backend/app packages/graph-agent-gateway/src` has no production hits.

- [x] 7.2 Introduce fixed `RuntimeSettings` and `EffectiveRuntimeSettings` schema.
  - Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`
  - Replace route-entry scalar fields `temperature`, `max_output_tokens`, `thinking_enabled`, and `thinking_budget_tokens` with:
    - `runtime_settings: RuntimeSettings = Field(default_factory=RuntimeSettings)`
    - compatibility shims are not allowed in production parsing.
  - Add typed submodels:
    - `ReasoningSettings(enabled: bool | None, effort: str | None, budget_tokens: int | None)`
    - `StructuredOutputSettings(mode: Literal["none", "json_object", "json_schema"], json_schema: dict[str, Any] | None, strict: bool | None)`
    - `RuntimeSettings(temperature, top_p, max_output_tokens, stop_sequences, seed, tool_choice, parallel_tool_calls, structured_output, reasoning)`
    - `EffectiveRuntimeSetting(value, source, message)`
  - Acceptance: `pytest packages/graph-agent-gateway/tests/test_registry_schema.py packages/graph-agent-gateway/tests/test_registry_runtime_settings.py -q` covers default object creation, unknown key rejection, scalar legacy field rejection, and valid nested reasoning/structured output settings.

- [x] 7.3 Resolve runtime setting defaults in the registry resolver.
  - Modify:
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py`
  - Implement default order: route entry → copied profile default → route capability default → protocol default → Studio safe default.
  - Store resolved values on `ResolvedRoute.effective_runtime_settings`.
  - Preserve original user-authored settings on `ResolvedRoute.runtime_settings`.
  - Acceptance: tests prove missing `max_output_tokens` and reasoning budget get deterministic defaults with source metadata, and profile-applied defaults do not create runtime dependency on the profile.

- [x] 7.4 Validate runtime settings against normalized capabilities.
  - Modify:
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/error_classification.py`
  - Add capability keys for `temperature`, `top_p`, `stop_sequences`, `seed`, `tool_choice`, `parallel_tool_calls`, `reasoning_budget_tokens`, and `reasoning_effort`.
  - Out-of-range known values return blocking lint on save/probe and fail fast at runtime if they slip through.
  - Acceptance: tests cover Anthropic-style `reasoning_budget_tokens.min`, unsupported `seed`, invalid `tool_choice`, and unknown runtime setting key failure.

- [x] 7.5 Map effective runtime settings in provider adapters.
  - Modify:
    - `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`
  - OpenAI-compatible adapter maps normalized settings to OpenAI-shaped request args.
  - Anthropic-compatible adapter maps `reasoning.enabled/budget_tokens` to Anthropic thinking args and validates max token interactions before request.
  - Google GenAI adapter maps generation config fields without leaking Google-specific names into role YAML.
  - Unsupported fields are omitted only after validation records why they are unsupported or defaulted.
  - Acceptance: gateway tests use fake clients to assert request payloads for OpenAI-compatible, Anthropic-compatible, and Google GenAI protocols.

- [x] 7.6 Add runtime settings diagnostics/tracing.
  - Modify:
    - `packages/graph-agent-gateway/src/graph_agent_gateway/events.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py`
    - `apps/studio/backend/app/services/run_manager.py`
  - Include redacted `effective_runtime_settings` source metadata in LLM call diagnostics and fallback events.
  - Do not log API keys, raw secrets, or full JSON schemas unless explicitly marked safe.
  - Acceptance: tracing tests assert route ID, provider model ID, fallback decision, and effective runtime setting sources are present.

- [x] 7.7 Update examples and bootstrap docs.
  - Modify:
    - `docs/development/examples/llm_roles.v2.example.yaml`
    - `docs/development/CREDENTIALS_V4_BOOTSTRAP.md`
    - `docs/engine/graph-agent-gateway/mvp0-alignment.md`
  - Examples use `runtime_settings` nested objects, not legacy scalar route-entry params.
  - Docs state repo `config/` files are seed/example only.
  - Acceptance: docs grep has no claim that repo-root `config/llm_roles.yaml` is the active runtime file.

## Phase 8: Provider Protocol Matrix and Ark SDK Verification

**目标**: 证明 normalized capability/runtime setting schema 能覆盖真实 provider 差异，并把 Ark official SDK 作为一等协议路径测试。

- [ ] 8.1 Add provider probe contracts for runtime settings.
  - Modify:
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/probe_contracts.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py`
  - Probe request supports selected runtime settings and negative-boundary checks, including `max_output_tokens`, `reasoning_budget_tokens`, tools, and structured output.
  - Probe result records normalized capabilities, raw diagnostic metadata, error class, observed request shape, and source URL/message when derived from docs.
  - Acceptance: unit tests cover successful probe normalization and failed boundary probe preservation without deleting previous verified capability values.

- [x] 8.2 Add `ark_runtime` protocol adapter.
  - Modify:
    - `packages/graph-agent-gateway/pyproject.toml`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`
    - `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py`
  - Add optional dependency for Volcengine Ark runtime SDK, using official import path `volcenginesdkarkruntime`.
  - `Protocol` includes `ark_runtime`.
  - Adapter constructs the official Ark client from endpoint `api_key`, `base_url`, timeout, and proxy/trust settings when supported.
  - Acceptance: tests skip cleanly when the optional SDK is not installed, and fake-client tests prove request construction does not use the OpenAI-compatible client path.

- [ ] 8.3 Run live/local provider matrix smoke when credentials are available.
  - Add tests under `packages/graph-agent-gateway/tests/live/` or guarded integration tests that run only with local credentials enabled.
  - Required local checks:
    - Anthropic official: valid thinking request and too-low thinking budget boundary.
    - Ark OpenAI-compatible: minimal chat call through existing `openai_compatible` protocol.
    - Ark official SDK: same model minimal chat call through `ark_runtime`.
    - Same Ark model comparison: record capability deltas between `openai_compatible` and `ark_runtime`.
  - Optional checks when credentials exist:
    - OpenAI official reasoning/non-reasoning route.
    - Gemini native thinking/generation config route.
    - DeepSeek OpenAI-compatible reasoning route.
  - Acceptance: live tests are opt-in, never required in normal CI, and produce a JSON observation artifact under `temp/` for review.

- [x] 8.4 Record provider pattern defaults and lower bounds.
  - Create: `docs/engine/graph-agent-gateway/provider-runtime-settings-matrix.md`
  - Document observed/default patterns for Anthropic, OpenAI-compatible, Google GenAI, DeepSeek, and Ark SDK routes.
  - Record at least one observed lower-bound or unsupported-setting result per tested provider family when safe.
  - Distinguish `provider_doc`, `manual`, and `probed_verified` sources.
  - Acceptance: docs link back to the official provider docs used for source claims and to the generated live observation artifact when available.

- [x] 8.5 Add backend API surface for runtime settings metadata.
  - Modify:
    - `apps/studio/backend/app/routers/llm.py`
    - `apps/studio/backend/app/models/llm_config.py`
  - Registry read DTO includes route capabilities, supported runtime setting descriptors, and current effective defaults for selected route/profile context.
  - Route probe API accepts runtime-setting probe requests and returns normalized capability/default/bounds updates.
  - Acceptance: backend router tests prove UI can discover which controls should be shown/disabled without doing frontend-side provider inference.
