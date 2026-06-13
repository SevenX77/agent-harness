---
spec_id: mvp1-three-module-interface-2026-06-11
module: engine
step: 4
artifact: gemini-prompt
status: ready-for-codex-review
created: 2026-06-11
task_file: .kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-4/task.md
worktree: /Users/sevenx/Documents/coding/agent-harness/.worktrees/pm-engine-mvp1-interface-2026-06-11
branch: codex/pm-engine-mvp1-interface-2026-06-11
---

# Gemini Prompt - Engine Step 4 Functional Closeout GREEN

```text
你是 Gemini，负责在 Engine PM 的 worktree 中实施 MVP1 三模块接口设计与修改的 Engine Step 4。

工作区：
/Users/sevenx/Documents/coding/agent-harness/.worktrees/pm-engine-mvp1-interface-2026-06-11

分支：
codex/pm-engine-mvp1-interface-2026-06-11

当前 Step：
- Step 4 名称：Engine 功能收口 GREEN
- 当前任务：实现真实 Engine owner path，使已审核通过的 Step 3 RED 测试转 GREEN。
- 执行前提：Codex 已审核通过 `.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-4/task.md` 和本 prompt。

必须先读：
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/02-implementation-plan.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/pm-engine-work-order.md
- .kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-3/red-report.md
- .kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-4/task.md

如果上面的 `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/*` 在当前 worktree 中不存在，立即停止并报告：
"BLOCKED: MVP1 three-module design docs are missing from the Engine PM worktree."
不要猜测文档内容，不要继续实施。

硬约束：
1. 使用 `superpowers:test-driven-development`。先跑 approved Step 3 RED，确认失败形状仍然是 Step 4 Engine owner-path 缺口，再写最小 GREEN。
2. 只能改 Step 4 `task.md` 允许的 Engine 文件。
3. 不得改 Studio/Gateway 生产代码。
4. 不得改 FROZEN MVP1 文档：`docs/engine/**`、`docs/graph-agent-gateway/**`、`docs/studio/**`。
5. 不得改 `uv.lock`；如果 `uv run` 触碰它，恢复它并报告。
6. 不得削弱 Step 1 或 Step 3 productization tests。
7. 每个 Step 4 runtime 错误必须有专属 `error_code`。
8. 只允许硬失败或显式结构化失败，禁止静默降级。
9. GREEN-2 不能 fake；唯一例外仍然是 Step 2 已存在的 `FakeLLMProvider` SPI contract fake，因为真实 provider implementation 归 Gateway。
10. Provider invoke failure 必须通过真实注入的 `LLMProvider.invoke()` 路径触发；禁止新增 direct error injection shortcut。
11. Raw `skill_path` 必须由 Engine runtime 显式拒绝，并使用 `runtime.raw_skill_path`；普通 Python signature `TypeError` 不能作为最终实现。

允许修改：
- packages/graph-agent/src/graph_agent/core/artifacts.py
- packages/graph-agent/src/graph_agent/core/adapter_contracts.py
- packages/graph-agent/src/graph_agent/core/event_contracts.py
- packages/graph-agent/src/graph_agent/core/llm_provider.py
- packages/graph-agent/src/graph_agent/core/runner.py
- packages/graph-agent/src/graph_agent/core/storage_contracts.py
- packages/graph-agent/src/graph_agent/core/runtime_state.py
- packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py 仅限移除 Engine core concrete Gateway import boundary 时修改
- packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py 仅限移除 Engine core concrete Gateway import boundary 时修改
- packages/graph-agent/src/graph_agent/__init__.py 仅限暴露 artifact runtime entrypoints 或保护 import boundary 时修改

禁止修改：
- apps/studio/**
- packages/graph-agent-gateway/**
- docs/engine/**
- docs/graph-agent-gateway/**
- docs/studio/**
- uv.lock
- Step 1 and Step 3 productization tests, unless Codex explicitly approves a mechanical correction

已有 RED 测试和失败摘要：
- packages/graph-agent/tests/core/test_productization_compile_artifact_red.py
- packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py
- packages/graph-agent/tests/core/test_productization_engine_storage_red.py
- packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py
- packages/graph-agent/tests/core/test_productization_event_stream_red.py

当前 approved RED：
- `15 tests`
- `12 failed, 3 passed`
- 失败集中在：
  - missing `graph_agent.core.artifacts.compile_artifact`
  - missing `graph_agent.core.runner.run_artifact`
  - missing `graph_agent.core.runtime_state`
  - missing `EventStreamBuffer` and stream error classes
  - missing real SPI invocation path for provider failure
- 已通过并必须保持：
  - `artifact.sealed_write`
  - `state.lease_conflict`
  - `state.lease_fenced`

先运行 RED：
uv run pytest \
  packages/graph-agent/tests/core/test_productization_compile_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_engine_storage_red.py \
  packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py \
  packages/graph-agent/tests/core/test_productization_event_stream_red.py \
  -q

RED 期望：
- `12 failed, 3 passed`
- 失败形状仍然是 Step 4 Engine owner-path 缺口。
- 没有语法、夹具、环境、依赖安装或 unrelated runtime failure。

实现目标：

1. `packages/graph-agent/src/graph_agent/core/artifacts.py`
   - 增加 `compile_artifact(source_root=..., skill_resolver=..., store="ephemeral", version=None)`。
   - 调用 existing Engine `compile_skill(..., cache=False, skill_resolver=...)`。
   - 对 source tree 做 canonical hash：relative POSIX path 排序、文件 bytes 内容参与、mtime/temp root/absolute path 不参与。
   - `GRAPH.md` 的 `metadata.ui` 不进入 `execution_fingerprint`。
   - `ArtifactRef.content_hash`、`manifest_ref`、`source_map_ref`、`execution_fingerprint` 使用 deterministic `sha256:` 格式。

2. `packages/graph-agent/src/graph_agent/core/runner.py`
   - 增加 `run_artifact(...)` 和 `predict_artifact(...)`，作为 Engine artifact-first runtime entrypoints。
   - `run_artifact` 接收 `RunArtifactRequest`，不得要求 raw `skill_path`。
   - 如果调用者传 `skill_path`，抛 dedicated Engine error，`error_code == "runtime.raw_skill_path"`。
   - `idempotency_key` 相同必须只执行一次，重复调用返回同一 `RunSession`。
   - 有 `artifact_executor` 时调用它并把返回 dict 作为 runtime output。
   - 有 `run_artifact_store` 时必须调用 `begin_run`、`put_batch`、`seal_run`，并设置非空 `result_ref`。
   - 显式 `llm_provider=None` 且无 executor 时，返回 structured failure：`llm.provider_not_configured`。
   - 有 `LLMProvider` 且无 executor 时，构造 `LLMProviderRequest` 并调用 `llm_provider.invoke()`。
   - 捕获 `LLMProviderError` 后返回 structured failure，保留 provider error 的 `error_code`、`details`、`retryable`。
   - 不 import `graph_agent_gateway`。

3. `packages/graph-agent/src/graph_agent/core/runtime_state.py`
   - 增加 `StateLeaseRequiredError.error_code == "state.lease_required"`。
   - 增加 `snapshot_checkpoint(...)`：无 lease token 硬失败，有 token 时调用 `RuntimeStateStore.snapshot(...)`。
   - 增加 `restore_checkpoint(...)`：调用 `RuntimeStateStore.restore(...)`。
   - 保持 `state.lease_fenced` 从 store 原样传播。

4. `packages/graph-agent/src/graph_agent/core/event_contracts.py`
   - 增加 `EventStreamBuffer`、`EventStreamResumeResult`。
   - 增加 stream errors：
     - `stream.cursor_gap`
     - `stream.cursor_expired`
     - `stream.backpressure`
     - 可选 `stream.out_of_order`
   - 支持 cursor resume、seq dedupe、gap、cursor too old、backpressure、out-of-order replay。
   - `resume(cursor=None)` 返回 retained events sorted by `seq`。

5. Engine import boundary
   - `import graph_agent` 不得 import `graph_agent_gateway`。
   - Step 4 新 runtime entrypoints 不得 import `graph_agent_gateway`。
   - 如果必须保留 Gateway-specific predict helper，只能放在 optional/lazy import path，不得在 Engine package import 或 artifact runtime import 时触发。

实现建议：
- 先实现最小代码让 Step 3 tests GREEN，再跑 Step 1 + Step 3 productization tests 合集。
- 对 dotted productization error_code 使用本地异常或 local structured result，不要塞进现有 `[F-v3-*]` `ErrorPayload` registry。
- `RunArtifactErrorResult` 可以放在 `adapter_contracts.py`，字段至少要有 `error_code` 和 `error_payload`。
- `error_payload` 建议使用 dict：`error_code`、`message`、`details`、`retryable`。
- Event stream cursor 使用 `f"{stream_id}:{seq}"`，并校验 stream id。
- 不要为了 GREEN 绕开 `LLMProvider.invoke()`；测试会检查 failing provider 的 request 计数。

验证命令：

1. Step 1 + Step 3 productization tests：
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

2. Ruff：
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

3. Existing error payload regression：
uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py -q

4. Scope guard：
git diff -- \
  apps/studio \
  packages/graph-agent-gateway \
  docs/engine \
  docs/graph-agent-gateway \
  docs/studio \
  uv.lock

5. Diff whitespace：
git diff --check

6. Final status：
git status --short -uall

期望：
- Step 1 + Step 3 productization tests pass。
- ruff passes。
- `test_error_payload_contract.py` passes。
- scope guard no diff。
- `git diff --check` no output。
- 没有 Studio/Gateway/FROZEN-doc/uv.lock 修改。
- 回复中明确列出 `FakeLLMProvider` 仍是唯一 fake 例外；Step 4 runtime owner path 不使用 fake。

请实施最小改动使目标测试通过，并在回复中提供：
1. 修改文件列表。
2. 关键实现说明。
3. 测试命令和结果。
4. Scope guard、diff check、git status 摘要。
5. 风险和未处理项。
```
