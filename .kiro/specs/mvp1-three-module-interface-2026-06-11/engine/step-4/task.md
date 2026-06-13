---
spec_id: mvp1-three-module-interface-2026-06-11
module: engine
step: 4
step_name: Engine functional closeout GREEN
role: Engine PM
status: ready-for-codex-review
created: 2026-06-11
worktree: /Users/sevenx/Documents/coding/agent-harness/.worktrees/pm-engine-mvp1-interface-2026-06-11
branch: codex/pm-engine-mvp1-interface-2026-06-11
approved_red_summary: "15 tests; 12 failed, 3 passed; failures are missing Step 4 Engine runtime owner paths"
---

# Engine Step 4 Task: Functional Closeout GREEN

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. Step 3 RED tests are already written and reviewed. Do not weaken them. This task is for Gemini implementation only after Codex approves this `task.md` and `gemini-prompt.md`.

## 目标

Implement the real Engine-owned functional closeout path for MVP1 productization:

- Deterministic artifact compilation with frozen identity, source map references, and execution fingerprint.
- Artifact-first runtime entrypoints: `run_artifact` and `predict_artifact`.
- Engine-owned runtime storage writes through `RunArtifactStore`.
- Runtime checkpoint snapshot/restore helpers backed by `RuntimeStateStore` leases and fencing.
- LLM provider failures routed through the injected `LLMProvider.invoke()` SPI path.
- Event stream replay built on `EventEnvelope`.
- Engine core import boundaries that do not require `graph_agent_gateway` while importing `graph_agent`.

## 非目标

- Do not change Studio production code.
- Do not change Gateway production code.
- Do not publish product artifacts or implement product release versioning; Studio/Gateway closeout owns those pieces.
- Do not change FROZEN MVP1 docs under `docs/engine/**`, `docs/graph-agent-gateway/**`, or `docs/studio/**`.
- Do not introduce a fake runtime that bypasses Engine owner paths. The only allowed fake remains the Step 2 `FakeLLMProvider` contract fake.
- Do not make productization error codes silent fallbacks. Every runtime error below must either raise or return a structured result with its dedicated `error_code`.

## 允许修改的文件

Production files allowed for Step 4 GREEN implementation:

- Modify: `packages/graph-agent/src/graph_agent/core/artifacts.py`
- Modify: `packages/graph-agent/src/graph_agent/core/adapter_contracts.py`
- Modify: `packages/graph-agent/src/graph_agent/core/event_contracts.py`
- Modify: `packages/graph-agent/src/graph_agent/core/llm_provider.py`
- Modify: `packages/graph-agent/src/graph_agent/core/runner.py`
- Modify: `packages/graph-agent/src/graph_agent/core/storage_contracts.py`
- Create: `packages/graph-agent/src/graph_agent/core/runtime_state.py`
- Modify only if needed to remove concrete Gateway imports from Engine core import paths:
  - `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py`
  - `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py`
  - `packages/graph-agent/src/graph_agent/__init__.py`

Approved Step 3 RED tests are in scope only as verification inputs. Do not edit them unless Codex explicitly asks for a mechanical lint or fixture correction:

- `packages/graph-agent/tests/core/test_productization_compile_artifact_red.py`
- `packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py`
- `packages/graph-agent/tests/core/test_productization_engine_storage_red.py`
- `packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py`
- `packages/graph-agent/tests/core/test_productization_event_stream_red.py`

Step 4 planning artifacts:

- `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-4/task.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-4/gemini-prompt.md`

## 禁止修改的文件

- `apps/studio/**`
- `packages/graph-agent-gateway/**`
- `docs/engine/**`
- `docs/graph-agent-gateway/**`
- `docs/studio/**`
- `uv.lock`
- Step 1 and Step 3 productization tests, except for Codex-approved mechanical corrections.

If implementation cannot pass the approved Step 3 tests without touching a forbidden path, stop and report the blocker to Codex.

## RED 测试清单

Approved Step 3 RED command:

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_productization_compile_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_engine_storage_red.py \
  packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py \
  packages/graph-agent/tests/core/test_productization_event_stream_red.py \
  -q
```

Current RED summary:

- `15 tests`
- `12 failed, 3 passed`
- Expected failures:
  - `graph_agent.core.artifacts.compile_artifact` is missing.
  - `graph_agent.core.runner.run_artifact` is missing.
  - Raw `skill_path` rejection cannot be verified until `run_artifact` exists; once it exists, plain Python signature rejection is not enough. The runtime must raise a dedicated `runtime.raw_skill_path` error.
  - `graph_agent.core.runtime_state` is missing.
  - `graph_agent.core.event_contracts.EventStreamBuffer` and stream error classes are missing.
  - Provider invoke failure must flow through a real injected `LLMProvider.invoke()` call.
- Expected passes:
  - `artifact.sealed_write`
  - `state.lease_conflict`
  - `state.lease_fenced`

## GREEN-1 接口/协议任务

### 1E. Artifact Compiler Contract

Modify `packages/graph-agent/src/graph_agent/core/artifacts.py`.

Add public function:

```python
def compile_artifact(
    *,
    source_root: str | Path,
    skill_resolver: SkillResolverProtocol,
    store: Literal["ephemeral", "product"] = "ephemeral",
    version: str | None = None,
) -> CompiledArtifactManifest:
    ...
```

Required behavior:

- Call existing `graph_agent.core.compiler.compile_skill(source_root, cache=False, skill_resolver=...)` so compilation stays Engine-owned.
- Build canonical source bytes from files under `source_root` using relative POSIX paths sorted lexicographically.
- Ignore file mtimes, temp directory names, absolute paths, and OS-specific path separators.
- For `GRAPH.md`, remove `metadata.ui` from the execution fingerprint input. Other metadata stays in the fingerprint input.
- `ArtifactRef.content_hash`, `manifest_ref`, and `source_map_ref` must be deterministic and formatted with a `sha256:` prefix.
- `CompiledArtifactManifest.execution_fingerprint` must be deterministic and formatted with a `sha256:` prefix.
- The returned `ArtifactRef.store` must default to `"ephemeral"`.
- Do not import Studio or Gateway modules.

### 2E. Runtime Request and Error Result Contract

Modify `packages/graph-agent/src/graph_agent/core/adapter_contracts.py` only if the runtime needs explicit result/error DTOs.

Allowed additions:

```python
class RunArtifactErrorResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    error_code: str
    error_payload: dict[str, Any]
    run_id: str | None = None
    retryable: bool = False
```

Required error payload shape for runtime failures:

```python
{
    "error_code": "...",
    "message": "...",
    "details": {...},
    "retryable": False,
}
```

Dedicated error codes required by Step 4:

- `runtime.raw_skill_path`
- `llm.provider_not_configured`
- `llm.provider_invoke_failed`
- `state.lease_required`
- `stream.cursor_gap`
- `stream.cursor_expired`
- `stream.backpressure`

### 3E. Runtime State Helpers

Create `packages/graph-agent/src/graph_agent/core/runtime_state.py`.

Required public error:

```python
class StateLeaseRequiredError(Exception):
    error_code = "state.lease_required"
```

Required public helpers:

```python
def snapshot_checkpoint(
    *,
    run_id: str,
    state: dict[str, Any],
    runtime_state_store: RuntimeStateStore,
    lease_token: LeaseToken | None,
) -> StateVersionRef:
    ...

def restore_checkpoint(
    *,
    run_id: str,
    runtime_state_store: RuntimeStateStore,
    state_ref: StateRef | None = None,
) -> dict[str, Any]:
    ...
```

Required behavior:

- `snapshot_checkpoint` must raise `StateLeaseRequiredError` when `lease_token is None`.
- With a lease token, `snapshot_checkpoint` must call `runtime_state_store.snapshot(...)`.
- Fencing errors from the store must propagate with `state.lease_fenced`.
- `restore_checkpoint` must call `runtime_state_store.restore(...)`.

### 4E. Event Stream Buffer Contract

Modify `packages/graph-agent/src/graph_agent/core/event_contracts.py`.

Required public value object:

```python
class EventStreamResumeResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    events: list[EventEnvelope]
    next_cursor: str | None
```

Required public errors:

- `StreamCursorGapError.error_code == "stream.cursor_gap"`
- `StreamCursorExpiredError.error_code == "stream.cursor_expired"`
- `StreamBackpressureError.error_code == "stream.backpressure"`
- `StreamOutOfOrderError.error_code == "stream.out_of_order"` may exist for callers that choose hard failure outside the reviewed RED path.

Required public class:

```python
class EventStreamBuffer:
    def __init__(self, *, stream_id: str, capacity: int) -> None: ...
    def append(self, event: EventEnvelope) -> None: ...
    def resume(self, *, cursor: str | None) -> EventStreamResumeResult: ...
```

Required behavior:

- `append` must reject events for a different `stream_id`.
- Duplicate `seq` values are idempotent and must not create duplicate events.
- If the buffer has already accepted `seq=1`, appending `seq=3` before `seq=2` must raise `StreamCursorGapError`.
- If an empty buffer receives `seq=2` and later receives `seq=1`, `resume(cursor=None)` must return `[1, 2]` sorted by `seq`.
- Capacity `1` must raise `StreamBackpressureError` when appending a new contiguous event while the current event is still retained.
- Capacity greater than `1` may evict the oldest retained event after a contiguous append; cursors older than the retained window must raise `StreamCursorExpiredError`.
- `resume(cursor="stream-id:N")` returns events with `seq > N`.
- `resume(cursor=None)` returns all retained events sorted by `seq`.
- `next_cursor` must be the cursor of the last returned event, or the input cursor when no events are returned.

### 5E. Artifact Runtime Entrypoints

Modify `packages/graph-agent/src/graph_agent/core/runner.py`.

Add public functions:

```python
def run_artifact(
    request: RunArtifactRequest | None = None,
    *,
    artifact_executor: Callable[[RunArtifactRequest], dict[str, Any]] | None = None,
    run_artifact_store: RunArtifactStore | None = None,
    llm_provider: LLMProvider | None | object = _LLM_PROVIDER_UNSET,
    **legacy_kwargs: Any,
) -> RunSession | RunArtifactErrorResult:
    ...

def predict_artifact(
    request: PredictArtifactRequest | RunArtifactRequest,
    *,
    artifact_executor: Callable[[RunArtifactRequest], dict[str, Any]] | None = None,
    run_artifact_store: RunArtifactStore | None = None,
    llm_provider: LLMProvider | None | object = _LLM_PROVIDER_UNSET,
) -> RunSession | RunArtifactErrorResult:
    ...
```

Required behavior:

- If `legacy_kwargs` contains `skill_path`, raise an Engine-owned exception with `error_code == "runtime.raw_skill_path"`.
- Plain Python signature rejection must not be the only raw path guard.
- `run_artifact` must accept only a `RunArtifactRequest` for the artifact path.
- Build a deterministic `run_id` from `idempotency_key` and artifact identity.
- Cache completed `RunSession` objects by `idempotency_key` so repeated calls do not re-run `artifact_executor`.
- When `artifact_executor` is provided, call it exactly once per idempotency key and use its returned dict as runtime output.
- When `run_artifact_store` is provided, call `begin_run`, `put_batch`, and `seal_run`. Store a JSON bytes object for the runtime output and set `RunSession.result_ref` to a non-empty object reference string.
- When `llm_provider is None` is explicitly passed and no `artifact_executor` is provided, return `RunArtifactErrorResult(error_code="llm.provider_not_configured", ...)`.
- When an `LLMProvider` is provided and no `artifact_executor` is provided, build an `LLMProviderRequest`, call `llm_provider.invoke(request)`, and convert `LLMProviderResponse.content` to runtime output.
- If `llm_provider.invoke(...)` raises `LLMProviderError`, return `RunArtifactErrorResult` using the provider error's `error_code`, `message`, `retryable`, and `details`.
- `predict_artifact` must reuse the same artifact-first runtime path and may set metadata `mode="predict"`.
- Do not call `graph_agent_gateway` from `run_artifact` or `predict_artifact`.

### 6E. Engine Import Boundary

Review Engine concrete Gateway imports in the allowed files.

Required behavior:

- `import graph_agent` must not import `graph_agent_gateway`.
- New Step 4 runtime entrypoints must not import `graph_agent_gateway`.
- If `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py` still needs Gateway-specific behavior, keep it behind an optional/lazy import path that is not reached by `import graph_agent` or `run_artifact`.
- In `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py`, replace direct Gateway-only missing-resolver errors with Engine-owned errors or local exceptions carrying a structured error code. Do not require Gateway merely to report a missing provider.

## GREEN-2 owner-side production path 任务

Step 4 GREEN must not stop at DTOs. It must create an Engine-owned production path behind every reviewed RED test:

- `compile_artifact` must use Engine compiler output and deterministic source hashing.
- `run_artifact` must be a real owner-side runtime entrypoint that coordinates idempotency, executor/provider invocation, and `RunArtifactStore` writes.
- `predict_artifact` must reuse artifact runtime instead of raw `skill_path`.
- `snapshot_checkpoint` must write through `RuntimeStateStore` and enforce leases.
- `EventStreamBuffer` must retain and replay `EventEnvelope` instances.
- Provider failure must flow through a real `LLMProvider.invoke()` call; no direct injected provider-error shortcut is allowed.

## 验证命令

Before implementation, Gemini must re-run approved RED:

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_productization_compile_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_engine_storage_red.py \
  packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py \
  packages/graph-agent/tests/core/test_productization_event_stream_red.py \
  -q
```

Expected before GREEN:

- `12 failed, 3 passed`
- Failures are the reviewed Step 4 owner-path gaps, not syntax, fixture, environment, or unrelated runtime failures.

After implementation, run:

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_productization_artifact_contracts.py \
  packages/graph-agent/tests/core/test_productization_storage_contracts.py \
  packages/graph-agent/tests/core/test_productization_llm_event_contracts.py \
  packages/graph-agent/tests/core/test_productization_run_result_contracts.py \
  packages/graph-agent/tests/core/test_productization_compile_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_engine_storage_red.py \
  packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py \
  packages/graph-agent/tests/core/test_productization_event_stream_red.py \
  -q
```

Expected after GREEN:

- All Step 1 and Step 3 Engine productization tests pass.

Run lint over touched Engine files and productization tests:

```bash
uv run ruff check \
  packages/graph-agent/src/graph_agent/core/artifacts.py \
  packages/graph-agent/src/graph_agent/core/adapter_contracts.py \
  packages/graph-agent/src/graph_agent/core/event_contracts.py \
  packages/graph-agent/src/graph_agent/core/llm_provider.py \
  packages/graph-agent/src/graph_agent/core/runner.py \
  packages/graph-agent/src/graph_agent/core/runtime_state.py \
  packages/graph-agent/src/graph_agent/core/storage_contracts.py \
  packages/graph-agent/tests/core/test_productization_artifact_contracts.py \
  packages/graph-agent/tests/core/test_productization_storage_contracts.py \
  packages/graph-agent/tests/core/test_productization_llm_event_contracts.py \
  packages/graph-agent/tests/core/test_productization_run_result_contracts.py \
  packages/graph-agent/tests/core/test_productization_compile_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_engine_storage_red.py \
  packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py \
  packages/graph-agent/tests/core/test_productization_event_stream_red.py
```

Run existing error payload regression:

```bash
uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py -q
```

Run scope guard:

```bash
git diff -- \
  apps/studio \
  packages/graph-agent-gateway \
  docs/engine \
  docs/graph-agent-gateway \
  docs/studio \
  uv.lock
```

Expected scope guard output:

- No diff.

Run whitespace check:

```bash
git diff --check
```

Final status check:

```bash
git status --short -uall
```

Expected status:

- Step 1 tests remain present.
- Step 3 tests remain present and unchanged unless Codex explicitly requested a mechanical correction.
- Step 4 adds this task file, the Step 4 Gemini prompt, and Engine production files only within the allowed list.
- No Studio/Gateway/FROZEN-doc/`uv.lock` modification.

## 回滚范围

If Codex rejects Step 4 implementation, rollback only Step 4 implementation files and Step 4 planning artifacts:

- `packages/graph-agent/src/graph_agent/core/artifacts.py`
- `packages/graph-agent/src/graph_agent/core/adapter_contracts.py`
- `packages/graph-agent/src/graph_agent/core/event_contracts.py`
- `packages/graph-agent/src/graph_agent/core/llm_provider.py`
- `packages/graph-agent/src/graph_agent/core/runner.py`
- `packages/graph-agent/src/graph_agent/core/runtime_state.py`
- `packages/graph-agent/src/graph_agent/core/storage_contracts.py`
- `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py`
- `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py`
- `packages/graph-agent/src/graph_agent/__init__.py`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-4/task.md`
- `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-4/gemini-prompt.md`

Do not rollback the approved Step 1 or Step 3 RED tests unless Codex explicitly rejects them.

## PM 审核口径

Codex/PM should review:

- `compile_artifact` hash stability across temp roots and mtime changes.
- Execution fingerprint excludes `metadata.ui` but still reflects runtime-relevant source content.
- `run_artifact` and `predict_artifact` are Engine-owned runtime entrypoints and reject raw `skill_path` with `runtime.raw_skill_path`.
- Idempotency prevents duplicate executor calls.
- `RunArtifactStore` writes are real owner-side writes, not a fake success marker.
- Provider failure uses a real `LLMProvider.invoke()` call.
- `RuntimeStateStore` lease/fencing errors preserve `state.lease_conflict`, `state.lease_fenced`, and `state.lease_required`.
- Event stream behavior covers cursor resume, dedupe, gap, expired cursor, backpressure, and out-of-order replay.
- No production code outside the allowed Engine paths changed.
