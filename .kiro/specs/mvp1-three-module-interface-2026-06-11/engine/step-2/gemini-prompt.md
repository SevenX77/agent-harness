---
spec_id: mvp1-three-module-interface-2026-06-11
module: engine
step: 2
artifact: gemini-prompt
status: ready-for-codex-review
created: 2026-06-11
task_file: .kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-2/task.md
worktree: /Users/sevenx/Documents/coding/agent-harness/.worktrees/pm-engine-mvp1-interface-2026-06-11
branch: codex/pm-engine-mvp1-interface-2026-06-11
---

# Gemini Prompt - Engine Step 2 Interface Definition GREEN

```text
你是 Gemini，负责在 Engine PM 的 worktree 中实施 MVP1 三模块接口设计与修改的 Engine Step 2。

工作区：
/Users/sevenx/Documents/coding/agent-harness/.worktrees/pm-engine-mvp1-interface-2026-06-11

分支：
codex/pm-engine-mvp1-interface-2026-06-11

当前 Step：
- Step 2 名称：Engine 接口定义 GREEN
- 当前任务：只实现 Engine 接口契约和 owner-side 最小 production path，使 Step 1 RED 测试转 GREEN。
- 执行前提：Codex 已审核通过 `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-2/task.md` 和本 prompt。

必须先读：
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/02-implementation-plan.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/pm-engine-work-order.md
- .kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-2/task.md

如果上面的 `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/*` 在当前 worktree 中不存在，立即停止并报告：
"BLOCKED: MVP1 three-module design docs are missing from the Engine PM worktree."
不要猜测文档内容，不要继续实施。

硬约束：
1. 使用 `superpowers:test-driven-development`。先跑 approved RED，确认失败形状仍然是目标契约模块缺失，再写最小 GREEN。
2. 只能改 task.md 允许的 Engine 文件。
3. 不得改 Studio/Gateway 生产代码。
4. 不得改 `runner.py`、`compiler.py`、`checkpointer.py`、`graph_assembler.py`、`loader.py`、`result.py`、`graph_agent/__init__.py`。
5. 不得改 FROZEN MVP1 文档：`docs/engine/**`、`docs/graph-agent-gateway/**`、`docs/studio/**`。
6. 不得改 `uv.lock`；如果 `uv run` 触碰它，恢复它并报告。
7. 每个错误必须有专属 `error_code` 字符串。
8. 只允许硬失败或显式降级，禁止静默降级。
9. GREEN-2 不能 fake；唯一例外是 `LLMProvider` SPI contract fake，因为真实 provider implementation 归 Gateway。报告里必须单独说明这个例外。
10. 不得削弱 Step 1 测试；测试文件只作为验证输入，除非 Codex 另行要求，不要改测试。

允许修改：
- packages/graph-agent/src/graph_agent/core/artifacts.py
- packages/graph-agent/src/graph_agent/core/adapter_contracts.py
- packages/graph-agent/src/graph_agent/core/storage_contracts.py
- packages/graph-agent/src/graph_agent/core/llm_provider.py
- packages/graph-agent/src/graph_agent/core/event_contracts.py
- packages/graph-agent/src/graph_agent/core/result_contracts.py

禁止修改：
- apps/studio/**
- packages/graph-agent-gateway/**
- packages/graph-agent/src/graph_agent/core/runner.py
- packages/graph-agent/src/graph_agent/core/compiler.py
- packages/graph-agent/src/graph_agent/core/checkpointer.py
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- packages/graph-agent/src/graph_agent/core/loader.py
- packages/graph-agent/src/graph_agent/core/result.py
- packages/graph-agent/src/graph_agent/__init__.py
- packages/graph-agent/src/graph_agent/callbacks/**
- packages/graph-agent/src/graph_agent/io/**
- packages/graph-agent/src/graph_agent/middleware/**
- docs/engine/**
- docs/graph-agent-gateway/**
- docs/studio/**
- uv.lock

已有 RED 测试和失败摘要：
- packages/graph-agent/tests/core/test_productization_artifact_contracts.py
- packages/graph-agent/tests/core/test_productization_storage_contracts.py
- packages/graph-agent/tests/core/test_productization_llm_event_contracts.py
- packages/graph-agent/tests/core/test_productization_run_result_contracts.py

当前 approved RED：
- `16 failed`
- 失败均为目标 Engine 契约模块缺失：
  - `graph_agent.core.artifacts`
  - `graph_agent.core.adapter_contracts`
  - `graph_agent.core.storage_contracts`
  - `graph_agent.core.llm_provider`
  - `graph_agent.core.event_contracts`
  - `graph_agent.core.result_contracts`
- ruff 已通过。

先运行 RED：
uv run pytest \
  packages/graph-agent/tests/core/test_productization_artifact_contracts.py \
  packages/graph-agent/tests/core/test_productization_storage_contracts.py \
  packages/graph-agent/tests/core/test_productization_llm_event_contracts.py \
  packages/graph-agent/tests/core/test_productization_run_result_contracts.py \
  -q

RED 期望：
- 16 failed
- 失败形状仍然是目标 contract module missing。
- 没有语法、夹具、环境、依赖安装或 unrelated runtime failure。

实现目标：

1. `packages/graph-agent/src/graph_agent/core/artifacts.py`
   - 定义 `ArtifactRef`、`CompiledArtifactManifest`、`ArtifactBytes`。
   - `ArtifactRef.store` 只接受 `"ephemeral"` 或 `"product"`。
   - 定义 `build_compiled_artifact_manifest(...)` owner-side helper：
     - 参数：`compiled`, `artifact_ref`, `execution_fingerprint`, `diagnostics=None`
     - 返回 `CompiledArtifactManifest`
     - `source_map_ref` 使用 `artifact_ref.source_map_ref`
     - 不调用 `compile_skill`
     - 不迁移 runtime。

2. `packages/graph-agent/src/graph_agent/core/adapter_contracts.py`
   - 定义 `RunArtifactRequest`、`PredictArtifactRequest`、`ResumeRequest`、`RunSession`。
   - `RunArtifactRequest` / `PredictArtifactRequest` / `ResumeRequest` 必须有 `idempotency_key`。
   - 这些 runtime request 和 `RunSession` 都不得定义或接受 `skill_path`。

3. `packages/graph-agent/src/graph_agent/core/storage_contracts.py`
   - 定义 Protocols：`RunArtifactStore`、`RuntimeStateStore`。
   - 定义 value objects：`ObjectRef`、`StoredObject`、`RunArtifactIndex`、`LeaseToken`、`StateRef`、`StateVersionRef`。
   - 定义错误：
     - `HashMismatchError.error_code == "artifact.hash_mismatch"`
     - `SealedRunWriteError.error_code == "artifact.sealed_write"`
     - `LeaseConflictError.error_code == "state.lease_conflict"`
     - `LeaseFencingError.error_code == "state.lease_fenced"`
   - 定义 `InMemoryRunArtifactStore`：
     - `put_batch` 根据 bytes 计算 SHA-256 hash。
     - `seal_run` 后再 `put_batch` 硬失败，抛 `SealedRunWriteError`。
     - `get_object(hash=...)` 每次重算 hash，损坏字节抛 `HashMismatchError`。
     - 提供 `corrupt_object_for_test(hash: str, content: bytes) -> None`。
   - 定义 `InMemoryRuntimeStateStore`：
     - `acquire_lease` 产生单调递增 integer `fencing_token`。
     - active lease 被其他 owner 抢占时抛 `LeaseConflictError`。
     - stale fencing token snapshot 抛 `LeaseFencingError`。

4. `packages/graph-agent/src/graph_agent/core/llm_provider.py`
   - 定义 `LLMProvider` SPI，不 import `graph_agent_gateway`。
   - 定义 `LLMProviderRequest`、`LLMProviderResponse`、`LLMProviderError`。
   - 定义 `FakeLLMProvider` contract fake，作为唯一允许的 GREEN-2 fake 例外。

5. `packages/graph-agent/src/graph_agent/core/event_contracts.py`
   - 定义 `StreamCursor`、`EventEnvelope`、`TransportErrorPayload`、`ResponseEnvelope`。
   - `ResponseEnvelope` 必须包含 `schema_version`、`ok`、`data`、`error_code`、`error_payload`。
   - `error_payload` 必须是结构化 `TransportErrorPayload`，不能接受 plain string。
   - 定义 helper：
     - `make_event_envelope(...)`
     - `success_response(data, schema_version="engine.response.v1")`
     - `error_response(error, schema_version="engine.response.v1")`

6. `packages/graph-agent/src/graph_agent/core/result_contracts.py`
   - 定义 `RunResultsRef`、`NodeRunResult`、`RunResultSnapshot`、`GoldenInputRef`。
   - 定义错误：
     - `RunResultsNotFoundError.error_code == "golden.run_results_not_found"`
     - `GoldenBaselineNotFoundError.error_code == "golden.baseline_not_found"`
     - `GoldenJudgeUnavailableError.error_code == "golden.judge_unavailable"`
     - `GoldenBaselineStaleError.error_code == "golden.baseline_stale"`
   - 定义 `snapshot_from_run_result(...)` projection helper：
     - 从 existing `RunResult` shape 投影为 `RunResultSnapshot`
     - 不启动 run
     - 不调用 `run_skill`
     - 不调用 `evaluate_golden_baseline`
   - 这些 run result contract class 不得包含以下 callable：
     - `run`
     - `run_skill`
     - `run_artifact`
     - `predict`
     - `predict_artifact`
     - `resume`
     - `start_run`
     - `execute`
     - `invoke`
     - `evaluate_golden_baseline`

实现建议：
- 优先使用 Pydantic `BaseModel` + `ConfigDict(frozen=True)`，贴合现有 Engine 代码风格，也方便字段验证。
- 对 dotted productization error_code 使用本地异常类属性，不要塞进现有 `[F-v3-*]` `ErrorPayload` registry；现有 registry 会拒绝未知 code。
- `get_object(hash=...)` 的 content hash 建议格式统一为 `sha256:<hex>`。
- 保持所有新模块独立，不从 Studio/Gateway import。

验证命令：

1. Step 1 contract GREEN：
uv run pytest \
  packages/graph-agent/tests/core/test_productization_artifact_contracts.py \
  packages/graph-agent/tests/core/test_productization_storage_contracts.py \
  packages/graph-agent/tests/core/test_productization_llm_event_contracts.py \
  packages/graph-agent/tests/core/test_productization_run_result_contracts.py \
  -q

2. Ruff：
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

3. Existing error payload regression：
uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py -q

4. Scope guard：
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

5. Final status：
git status --short

期望：
- Step 1 contract tests pass。
- ruff passes。
- `test_error_payload_contract.py` passes。
- scope guard no diff。
- `git status --short` 只出现 Step 1 四个测试文件、Step 2 六个 Engine contract source files、Step 2 task/prompt files。
- 没有 Studio/Gateway/FROZEN-doc/uv.lock 修改。

请实施最小改动使目标测试通过，并在回复中提供：
1. 修改文件列表。
2. 关键实现说明，逐项覆盖 GREEN-1 和 GREEN-2。
3. 测试命令和结果。
4. 明确说明 `LLMProvider` fake 是唯一 fake 例外。
5. 风险和未处理项。
6. scope guard 结果：Studio/Gateway/FROZEN-doc/uv.lock 是否无 diff。
```
