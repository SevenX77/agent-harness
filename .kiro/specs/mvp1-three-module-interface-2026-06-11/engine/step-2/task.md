---
spec_id: mvp1-three-module-interface-2026-06-11
module: engine
step: 2
step_name: Engine interface definition GREEN
role: Engine PM
status: ready-for-codex-review
created: 2026-06-11
worktree: /Users/sevenx/Documents/coding/agent-harness/.worktrees/pm-engine-mvp1-interface-2026-06-11
branch: codex/pm-engine-mvp1-interface-2026-06-11
approved_red_summary: "16 failed; all failures are target Engine contract modules missing"
---

# Engine Step 2 Task: Interface Definition GREEN

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. Step 1 RED tests are already written and reviewed. Do not weaken them. This task is for Gemini implementation only after Codex approves this `task.md` and `gemini-prompt.md`.

## 目标

Implement the Engine-owned interface contracts required by MVP1 three-module productization so the approved Step 1 contract tests pass:

- Frozen artifact identity and runtime request/session DTOs.
- Run artifact store and runtime state store contracts with seal, hash verification, and monotonic fencing tokens.
- LLM provider SPI plus event/response envelope DTOs.
- Golden-headless-readable run result snapshot contracts.

## 非目标

- Do not migrate `run_skill`, `predict_skill`, or `resume_skill` to artifact-only runtime entrypoints. That belongs to Step 4.
- Do not remove existing `graph_agent_gateway` concrete imports. That belongs to Step 4 / E-F5.
- Do not implement event stream replay, gap recovery, cursor expiration, backpressure, or ordering recovery. Step 2 only defines contract DTOs and minimal builders.
- Do not change Studio or Gateway production code.
- Do not edit FROZEN MVP1 docs under `docs/engine/**`, `docs/graph-agent-gateway/**`, or `docs/studio/**`.
- Do not copy or rewrite the MVP1 design documents in this worktree during implementation. If the relative design docs are missing, stop and report the document availability blocker.

## 允许修改的文件

Production files allowed for Step 2 GREEN implementation:

- Create: `packages/graph-agent/src/graph_agent/core/artifacts.py`
- Create: `packages/graph-agent/src/graph_agent/core/adapter_contracts.py`
- Create: `packages/graph-agent/src/graph_agent/core/storage_contracts.py`
- Create: `packages/graph-agent/src/graph_agent/core/llm_provider.py`
- Create: `packages/graph-agent/src/graph_agent/core/event_contracts.py`
- Create: `packages/graph-agent/src/graph_agent/core/result_contracts.py`

Approved Step 1 contract tests are in scope only as verification inputs. Do not edit them unless Codex explicitly asks for a mechanical lint or fixture correction:

- `packages/graph-agent/tests/core/test_productization_artifact_contracts.py`
- `packages/graph-agent/tests/core/test_productization_storage_contracts.py`
- `packages/graph-agent/tests/core/test_productization_llm_event_contracts.py`
- `packages/graph-agent/tests/core/test_productization_run_result_contracts.py`

Step 2 planning artifacts:

- `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-2/task.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-2/gemini-prompt.md`

## 禁止修改的文件

- `apps/studio/**`
- `packages/graph-agent-gateway/**`
- `packages/graph-agent/src/graph_agent/core/runner.py`
- `packages/graph-agent/src/graph_agent/core/compiler.py`
- `packages/graph-agent/src/graph_agent/core/checkpointer.py`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/src/graph_agent/core/loader.py`
- `packages/graph-agent/src/graph_agent/core/result.py`
- `packages/graph-agent/src/graph_agent/__init__.py`
- `packages/graph-agent/src/graph_agent/callbacks/**`
- `packages/graph-agent/src/graph_agent/io/**`
- `packages/graph-agent/src/graph_agent/middleware/**`
- `docs/engine/**`
- `docs/graph-agent-gateway/**`
- `docs/studio/**`
- `uv.lock`

If implementation cannot pass the approved Step 1 tests without touching a forbidden path, stop and report the blocker to Codex.

## RED 测试清单

Approved Step 1 RED command:

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_productization_artifact_contracts.py \
  packages/graph-agent/tests/core/test_productization_storage_contracts.py \
  packages/graph-agent/tests/core/test_productization_llm_event_contracts.py \
  packages/graph-agent/tests/core/test_productization_run_result_contracts.py \
  -q
```

Current RED summary:

- `16 failed`
- Failure shape is clean target contract absence:
  - `ModuleNotFoundError: No module named 'graph_agent.core.artifacts'`
  - `ModuleNotFoundError: No module named 'graph_agent.core.adapter_contracts'`
  - `ModuleNotFoundError: No module named 'graph_agent.core.storage_contracts'`
  - `ModuleNotFoundError: No module named 'graph_agent.core.llm_provider'`
  - `ModuleNotFoundError: No module named 'graph_agent.core.event_contracts'`
  - `ModuleNotFoundError: No module named 'graph_agent.core.result_contracts'`
- `uv run ruff check` over the four Step 1 tests passes.

## GREEN-1 接口/协议任务

### 1E. Artifact and Adapter Contracts

Create `packages/graph-agent/src/graph_agent/core/artifacts.py`.

Use Pydantic models or frozen dataclasses with explicit validation. Existing Engine code already uses Pydantic heavily; Pydantic `BaseModel` with `ConfigDict(frozen=True)` is the recommended local pattern.

Required public value objects:

- `ArtifactRef`
  - Fields: `artifact_id: str`, `content_hash: str`, `store: Literal["ephemeral", "product"]`, `version: str | None = None`, `manifest_ref: str`, `source_map_ref: str`
  - Reject any `store` value outside `"ephemeral"` and `"product"`.
- `CompiledArtifactManifest`
  - Fields: `artifact_ref: ArtifactRef`, `execution_fingerprint: str`, `source_map_ref: str`, `diagnostics: list[dict[str, Any]]`
- `ArtifactBytes`
  - Fields: `bytes_ref: str`, `expected_content_hash: str`

Create `packages/graph-agent/src/graph_agent/core/adapter_contracts.py`.

Required public value objects:

- `RunArtifactRequest`
  - Fields: `artifact_ref: ArtifactRef`, `inputs: dict[str, Any]`, `execution_context: dict[str, Any]`, `idempotency_key: str`
  - Must not define or accept `skill_path`.
- `PredictArtifactRequest`
  - Same fields and constraints as `RunArtifactRequest`.
- `ResumeRequest`
  - Fields: `run_id: str`, `payload: dict[str, Any]`, `idempotency_key: str`
  - Must not define or accept `skill_path`.
- `RunSession`
  - Fields: `run_id: str`, `event_stream_ref: str`, `result_ref: str | None = None`, `status_ref: str | None = None`
  - Must not define or accept `skill_path`.

### 2E. Storage Contracts

Create `packages/graph-agent/src/graph_agent/core/storage_contracts.py`.

Required public Protocols:

- `RunArtifactStore`
  - Methods: `begin_run(run_id: str, metadata: dict[str, Any]) -> None`
  - `put_batch(run_id: str, objects: dict[str, bytes]) -> list[ObjectRef] | dict[str, ObjectRef]`
  - `seal_run(run_id: str) -> RunArtifactIndex`
  - `get_object(*, hash: str) -> bytes | StoredObject`
- `RuntimeStateStore`
  - Methods: `acquire_lease(run_id: str, *, owner_id: str, ttl_ms: int) -> LeaseToken`
  - `heartbeat(run_id: str, *, lease_token: LeaseToken) -> LeaseToken`
  - `snapshot(run_id: str, state: dict[str, Any], *, lease_token: LeaseToken) -> StateVersionRef`
  - `restore(run_id: str, *, state_ref: StateRef | None = None) -> dict[str, Any]`
  - `release(run_id: str, *, lease_token: LeaseToken) -> None`

Required public value objects and errors:

- `ObjectRef(bytes_ref: str, content_hash: str, size_bytes: int, path: str | None = None)`
- `StoredObject(content: bytes, content_hash: str)`
- `RunArtifactIndex(run_id: str, objects: list[ObjectRef], sealed: bool)`
- `LeaseToken(lease_id: str, owner_id: str, fencing_token: int, ttl_ms: int, safety_margin_ms: int)`
- `StateRef(run_id: str, version: int)`
- `StateVersionRef(run_id: str, version: int, fencing_token: int)`
- `HashMismatchError` with `error_code == "artifact.hash_mismatch"`
- `SealedRunWriteError` with `error_code == "artifact.sealed_write"`
- `LeaseConflictError` with `error_code == "state.lease_conflict"`
- `LeaseFencingError` with `error_code == "state.lease_fenced"`

### 3E. LLM Provider SPI and Event Contracts

Create `packages/graph-agent/src/graph_agent/core/llm_provider.py`.

Required public Protocol/value objects:

- `LLMProvider`
  - Method: `invoke(request: LLMProviderRequest) -> LLMProviderResponse`
  - Must import without importing `graph_agent_gateway`.
- `LLMProviderRequest`
  - Fields: `role: str`, `messages: list[Any]`, `metadata: dict[str, Any]`
- `LLMProviderResponse`
  - Fields: `content: Any`, `metadata: dict[str, Any]`
- `LLMProviderError`
  - Fields: `error_code: str`, `message: str`, `retryable: bool`, `details: dict[str, Any]`
- `FakeLLMProvider`
  - Contract fake allowed only for SPI testing. It must be reported as the single allowed GREEN-2 fake exception because Gateway owns the real provider implementation.

Create `packages/graph-agent/src/graph_agent/core/event_contracts.py`.

Required public value objects:

- `StreamCursor(stream_id: str, cursor: str, next_seq: int, window_start_seq: int)`
- `EventEnvelope(stream_id: str, seq: int, run_id: str, event_type: str, payload: dict[str, Any], cursor: str, timestamp: datetime)`
- `TransportErrorPayload(error_code: str, message: str, details: dict[str, Any], retryable: bool)`
- `ResponseEnvelope(schema_version: str, ok: bool, data: Any | None = None, error_code: str | None = None, error_payload: TransportErrorPayload | None = None)`

`ResponseEnvelope` must reject unstructured `error_payload` values such as plain strings.

### 4E. Run Result Contracts

Create `packages/graph-agent/src/graph_agent/core/result_contracts.py`.

Required public value objects and errors:

- `RunResultsRef(run_id: str, uri: str, content_hash: str)`
- `NodeRunResult(agent_node_id: str, status: str, outputs_ref: str, trace_refs: list[str])`
- `RunResultSnapshot(run_results_ref: RunResultsRef, node_results: list[NodeRunResult], status: str, outputs_ref: str, trace_refs: list[str])`
- `GoldenInputRef(run_results_ref: RunResultsRef, baseline_ref: str)`
- `RunResultsNotFoundError` with `error_code == "golden.run_results_not_found"`
- `GoldenBaselineNotFoundError` with `error_code == "golden.baseline_not_found"`
- `GoldenJudgeUnavailableError` with `error_code == "golden.judge_unavailable"`
- `GoldenBaselineStaleError` with `error_code == "golden.baseline_stale"`

The run result contracts must remain read-only data contracts. Do not add methods named `run`, `run_skill`, `run_artifact`, `predict`, `predict_artifact`, `resume`, `start_run`, `execute`, `invoke`, or `evaluate_golden_baseline` to these classes.

## GREEN-2 owner-side production path 任务

Step 2 must not stop at empty Protocols. Add the smallest Engine-owned path behind each interface, without migrating full runtime behavior:

### Artifact owner-side path

In `artifacts.py`, add a production helper:

- `build_compiled_artifact_manifest(*, compiled: Any, artifact_ref: ArtifactRef, execution_fingerprint: str, diagnostics: list[dict[str, Any]] | None = None) -> CompiledArtifactManifest`

Behavior:

- Return a `CompiledArtifactManifest`.
- Use `artifact_ref.source_map_ref` as the manifest `source_map_ref`.
- Default `diagnostics` to an empty list.
- Do not call `compile_skill` from this helper.
- Do not switch `run_skill` or `predict_skill` to this path in Step 2.

### Storage owner-side path

In `storage_contracts.py`, add in-process provider implementations:

- `InMemoryRunArtifactStore`
- `InMemoryRuntimeStateStore`

Required behavior:

- `InMemoryRunArtifactStore.put_batch` computes SHA-256 content hashes from bytes.
- `seal_run` marks the run immutable.
- `put_batch` after `seal_run` raises `SealedRunWriteError`.
- `get_object(hash=...)` recomputes SHA-256 over stored bytes and raises `HashMismatchError` if stored bytes no longer match the requested hash.
- For contract tests, expose `corrupt_object_for_test(hash: str, content: bytes) -> None`.
- `InMemoryRuntimeStateStore.acquire_lease` returns monotonically increasing integer `fencing_token` values per run.
- A held active lease blocks a second owner with `LeaseConflictError`.
- `snapshot` with a stale fencing token raises `LeaseFencingError`.

### Event/response owner-side path

In `event_contracts.py`, add small production builders:

- `make_event_envelope(*, stream_id: str, seq: int, run_id: str, event_type: str, payload: dict[str, Any], cursor: str | None = None, timestamp: datetime | None = None) -> EventEnvelope`
- `success_response(data: Any, *, schema_version: str = "engine.response.v1") -> ResponseEnvelope`
- `error_response(error: TransportErrorPayload, *, schema_version: str = "engine.response.v1") -> ResponseEnvelope`

Behavior:

- `make_event_envelope` defaults `cursor` to `f"{stream_id}:{seq}"`.
- `make_event_envelope` defaults `timestamp` to current UTC time.
- `success_response` returns `ok=True`, `data=data`, `error_code=None`, `error_payload=None`.
- `error_response` returns `ok=False`, `data=None`, `error_code=error.error_code`, `error_payload=error`.

### LLM Provider SPI exception

In `llm_provider.py`, `FakeLLMProvider` is the only allowed GREEN-2 fake because Gateway owns the real provider implementation.

Required behavior:

- It stores deterministic response content.
- `invoke` returns `LLMProviderResponse`.
- If configured with `LLMProviderError`, `invoke` raises or returns that error in a documented SPI shape.

The implementation report must explicitly say this is the only fake exception.

### Run result owner-side path

In `result_contracts.py`, add a production projection helper:

- `snapshot_from_run_result(*, run_result: Any, run_results_ref: RunResultsRef, node_results: list[NodeRunResult] | None = None, outputs_ref: str | None = None, trace_refs: list[str] | None = None) -> RunResultSnapshot`

Behavior:

- Derive `status` from `run_result.status` when present, otherwise from `run_result.success`.
- Default `node_results` to an empty list.
- Default `outputs_ref` to `run_results_ref.uri`.
- Default `trace_refs` from `run_result.trace_path` when present.
- Do not start a run, evaluate golden baselines, or call `run_skill`.

## 验证命令

Before implementation, Gemini must re-run approved RED:

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_productization_artifact_contracts.py \
  packages/graph-agent/tests/core/test_productization_storage_contracts.py \
  packages/graph-agent/tests/core/test_productization_llm_event_contracts.py \
  packages/graph-agent/tests/core/test_productization_run_result_contracts.py \
  -q
```

Expected before GREEN:

- `16 failed`
- Failures are target contract module absence, not syntax, fixture, environment, or unrelated runtime failures.

After implementation, run:

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_productization_artifact_contracts.py \
  packages/graph-agent/tests/core/test_productization_storage_contracts.py \
  packages/graph-agent/tests/core/test_productization_llm_event_contracts.py \
  packages/graph-agent/tests/core/test_productization_run_result_contracts.py \
  -q
```

Expected after GREEN:

- All Step 1 productization contract tests pass.

Run lint over Step 2 files:

```bash
uv run ruff check \
  packages/graph-agent/src/graph_agent/core/artifacts.py \
  packages/graph-agent/src/graph_agent/core/adapter_contracts.py \
  packages/graph-agent/src/graph_agent/core/storage_contracts.py \
  packages/graph-agent/src/graph_agent/core/llm_provider.py \
  packages/graph-agent/src/graph_agent/core/event_contracts.py \
  packages/graph-agent/src/graph_agent/core/result_contracts.py \
  packages/graph-agent/tests/core/test_productization_artifact_contracts.py \
  packages/graph-agent/tests/core/test_productization_storage_contracts.py \
  packages/graph-agent/tests/core/test_productization_llm_event_contracts.py \
  packages/graph-agent/tests/core/test_productization_run_result_contracts.py
```

Run a focused existing regression that protects Engine error payload behavior:

```bash
uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py -q
```

Run scope guard:

```bash
git diff -- \
  apps/studio \
  packages/graph-agent-gateway \
  packages/graph-agent/src/graph_agent/core/runner.py \
  packages/graph-agent/src/graph_agent/core/compiler.py \
  packages/graph-agent/src/graph_agent/core/checkpointer.py \
  packages/graph-agent/src/graph_agent/core/graph_assembler.py \
  packages/graph-agent/src/graph_agent/core/loader.py \
  packages/graph-agent/src/graph_agent/core/result.py \
  packages/graph-agent/src/graph_agent/__init__.py \
  packages/graph-agent/src/graph_agent/callbacks \
  packages/graph-agent/src/graph_agent/io \
  packages/graph-agent/src/graph_agent/middleware \
  docs/engine \
  docs/graph-agent-gateway \
  docs/studio \
  uv.lock
```

Expected scope guard output:

- No diff.

Final status check:

```bash
git status --short
```

Expected status:

- Step 1 tests remain present.
- Step 2 adds only the six allowed Engine contract source files and the two Step 2 Kiro prompt/task files.
- No Studio/Gateway/FROZEN-doc/`uv.lock` modification.

## 回滚范围

If Codex rejects this Step 2 implementation, rollback only Step 2 implementation files:

- `packages/graph-agent/src/graph_agent/core/artifacts.py`
- `packages/graph-agent/src/graph_agent/core/adapter_contracts.py`
- `packages/graph-agent/src/graph_agent/core/storage_contracts.py`
- `packages/graph-agent/src/graph_agent/core/llm_provider.py`
- `packages/graph-agent/src/graph_agent/core/event_contracts.py`
- `packages/graph-agent/src/graph_agent/core/result_contracts.py`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-2/task.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-2/gemini-prompt.md`

Do not rollback the approved Step 1 RED tests unless Codex explicitly rejects Step 1.

## PM 审核口径

Codex/PM should review:

- `GREEN-1`: all DTOs/Protocols import and validate fields as Step 1 tests require.
- `GREEN-2`: artifact manifest builder, in-memory stores, envelope builders, LLM SPI fake exception, and run result projection helper exist in Engine-owned modules.
- The `LLMProvider` fake is the only fake exception and is called out in Gemini's implementation report.
- No production code outside the six allowed Engine contract modules changed.
- No Studio/Gateway/FROZEN-doc/`uv.lock` diff exists.
