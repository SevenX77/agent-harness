## Engine PM RED Report - Step 3

Worktree:
`/Users/sevenx/Documents/coding/agent-harness/.worktrees/pm-engine-mvp1-interface-2026-06-11`

Branch:
`codex/pm-engine-mvp1-interface-2026-06-11`

Changed tests:
- `packages/graph-agent/tests/core/test_productization_compile_artifact_red.py`
- `packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py`
- `packages/graph-agent/tests/core/test_productization_engine_storage_red.py`
- `packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py`
- `packages/graph-agent/tests/core/test_productization_event_stream_red.py`

Command:
```bash
uv run pytest \
  packages/graph-agent/tests/core/test_productization_compile_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_engine_storage_red.py \
  packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py \
  packages/graph-agent/tests/core/test_productization_event_stream_red.py \
  -q
```

Expected RED:
The Step 3 suite must fail because Engine does not yet expose the functional closeout runtime contracts: compiled artifact runtime, artifact-based execution, runtime checkpoint helpers, injected SPI runtime error shape, and event stream buffering.

Actual output summary:
- `12 failed, 3 passed`
- `compile_artifact` is missing from `graph_agent.core.artifacts`.
- `run_artifact` is missing from `graph_agent.core.runner`.
- Raw `skill_path` rejection is specified as a dedicated `runtime.raw_skill_path` error_code; a plain signature `TypeError` must not satisfy this test once `run_artifact` exists.
- `graph_agent.core.runtime_state` is missing.
- `EventStreamBuffer` and stream error classes are missing from `graph_agent.core.event_contracts`.
- Existing Step 2 storage contracts already pass direct sealed write, lease conflict, and stale fencing assertions.

Why this proves the old path/interface gap:
- Artifact compilation still lacks a public deterministic artifact compiler that ignores temp roots, mtimes, and UI-only metadata for execution identity.
- Engine runtime still lacks artifact-first execution, raw `skill_path` rejection, idempotency handling, and `RunArtifactStore` output writes.
- Runtime checkpointing still has no owner-side helper that requires a `RuntimeStateStore` lease.
- Core runtime still lacks a tested injected-SPI path for `llm.provider_not_configured`.
- Provider invoke failure is now tested through a real `LLMProvider.invoke()` path using a failing provider object; no direct error injection bypass is allowed or required.
- Event streaming still lacks cursor resume, seq dedupe, gap/expired cursor errors, backpressure, and out-of-order handling.

Production code changed: No new production code changes for Step 3 RED. This step only added Step 3 tests and this report.

Risks / cross-module blockers:
- `test_importing_graph_agent_does_not_require_gateway_concrete_module` already passes, so the remaining SPI boundary RED is focused on runtime behavior rather than package import.
- Three storage/fencing checks already pass from Step 2; they are kept in this suite to preserve Step 3 coverage and prevent regression.
- The raw `skill_path` RED intentionally requires `runtime.raw_skill_path`, not pure Python signature rejection.
- No Step 4 Kiro `task.md` or Gemini prompt was prepared.
