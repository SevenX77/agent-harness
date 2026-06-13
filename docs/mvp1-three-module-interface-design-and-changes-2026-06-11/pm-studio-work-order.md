# Studio PM 作业单：MVP1 三模块接口设计与修改（2026-06-11）

## 1. PM 角色

你是 Studio PM，只负责 `apps/studio` 内的 adapter、provider、HTTP 本地模拟 harness、publish、golden、resume、GRAPH 收口。你不能直接改 Engine/Gateway 生产代码；跨模块需要通过报告交给 Codex 协调。

## 2. 建立 worktree 和分支

从主仓库根目录执行：

```bash
cd /Users/sevenx/Documents/coding/agent-harness
git worktree add .worktrees/pm-studio-mvp1-interface-2026-06-11 -b codex/pm-studio-mvp1-interface-2026-06-11 feat/studio-mvp1-integration
cd .worktrees/pm-studio-mvp1-interface-2026-06-11
```

## 3. 每一步固定流程

每一步都按下面流程执行：

1. 只写/改测试，确认 RED。
2. 提交 RED 报告给 Codex。
3. Codex 审核通过后，写 Kiro spec：`.kiro/specs/mvp1-three-module-interface-2026-06-11/studio/step-N/task.md`。
4. 写 Gemini prompt：`.kiro/specs/mvp1-three-module-interface-2026-06-11/studio/step-N/gemini-prompt.md`。
5. 把 prompt 交给 Gemini 实施。
6. 审核 Gemini diff 和测试输出。
7. 审核无误后提交实施报告给 Codex。
8. Codex 复审通过后进入下一步。

## 4. 四步任务

### Step 1: Studio 接口定义 RED

只允许新增/修改测试：

- `apps/studio/backend/tests/core/adapters/test_productization_adapters.py`
- `apps/studio/backend/tests/core/adapters/test_productization_local_providers.py`
- `apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py`
- `apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py`

RED 必须覆盖：

- `EngineAdapter` exposes `compile`、`run_artifact`、`predict_artifact`、`resume`。
- `GatewayAdapter` exposes `resolve_routes`、`materialize_role`、`project_route_state`、`decide_fallback`、`resolve_credential`。
- adapters 支持 `transport="in_process"` 和 `transport="http_loopback"`。
- HTTP adapter 发送 `Idempotency-Key` 并校验 `schema_version`。
- local config store 有 `user_id`、`etag`、`if_match`。
- local product store `get(hash)` hash 校验，拒绝 corrupted bytes。
- runtime state store 拒绝无 lease 和 stale fencing token。
- run artifact store seal 后拒写。
- HTTP 本地模拟 harness 能注入 timeout、connection refused、5xx、malformed JSON、missing DTO fields、schema mismatch。
- harness 能启动两个 worker 共享存储。
- publish contract 有 artifact ref、release version、idempotency key、atomic stage 字段。
- golden headless request 只接受 `run_results_ref + baseline_ref`。

RED 命令：

```bash
uv run pytest \
  apps/studio/backend/tests/core/adapters/test_productization_adapters.py \
  apps/studio/backend/tests/core/adapters/test_productization_local_providers.py \
  apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py \
  apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py \
  -q
```

### Step 2: Studio 接口定义 GREEN

Codex 审核 Step 1 RED 后，写 Kiro `task.md` 和 Gemini prompt，再交 Gemini 实施。

实现范围：

- `apps/studio/backend/app/core/adapters/engine.py`
- `apps/studio/backend/app/core/adapters/gateway.py`
- `apps/studio/backend/app/core/adapters/http_transport.py`
- `apps/studio/backend/app/core/adapters/gateway_config_store_local.py`
- `apps/studio/backend/app/core/adapters/run_artifact_store_local.py`
- `apps/studio/backend/app/core/adapters/runtime_state_store_local.py`
- `apps/studio/backend/app/core/adapters/product_store_local.py`
- `apps/studio/backend/tests/support/http_loopback_harness.py`
- `apps/studio/backend/tests/support/multi_worker_storage.py`
- `apps/studio/backend/app/services/publish_pipeline.py`
- `apps/studio/backend/app/services/golden_headless.py`

实现目标：

- adapter transport switch 可切 in-process / HTTP loopback。
- local providers 实现 etag、fencing、seal、hash 校验。
- HTTP harness 可触发传输族错误和多 worker 并发。
- publish/golden 先落协议，不迁移全部业务。

### Step 3: Studio 功能收口 RED

只允许新增/修改测试：

- `apps/studio/backend/tests/core/adapters/test_productization_http_transport_errors_red.py`
- `apps/studio/backend/tests/core/adapters/test_productization_import_boundary_red.py`
- `apps/studio/backend/tests/services/test_productization_run_artifact_flow_red.py`
- `apps/studio/backend/tests/routers/test_productization_publish_artifact_red.py`
- `apps/studio/backend/tests/services/test_productization_publish_atomicity_red.py`
- `apps/studio/backend/tests/services/test_productization_gateway_adapter_flow_red.py`
- `apps/studio/backend/tests/services/test_productization_golden_headless_red.py`
- `apps/studio/backend/tests/routers/test_productization_resume_adapter_red.py`
- `apps/studio/backend/tests/services/test_productization_graph_roundtrip_red.py`

RED 必须覆盖：

- HTTP timeout -> `transport.timeout`。
- connection refused -> `transport.connection_refused`。
- HTTP 5xx -> `ResponseEnvelope` error payload。
- malformed JSON / missing DTO field -> `transport.serialization_failed`。
- schema mismatch -> `transport.schema_mismatch`。
- 同 `Idempotency-Key` retry 不重复执行。
- event stream disconnect cursor 续接，重复 seq 去重。
- Studio services 仍 direct import SDK internals。
- run/predict 仍把 raw `skill_path` 传给 SDK runtime。
- corrupted artifact bytes 未报 `artifact.hash_mismatch`。
- dev missing hash 未显式重编到 ephemeral 并记录。
- prod missing hash 未硬失败。
- `/publish` 仍 zip source 或不写 ProductArtifactStore release。
- publish partial failure 留半成品。
- duplicate `release_version` 覆盖。
- copilot/settings 未走 GatewayAdapter。
- golden 仍整次 final_state diff。
- resume endpoint 仍 501 或解 checkpoint internals。
- GRAPH parse/serialize roundtrip 不一致。
- UI metadata 进入 execution fingerprint。

RED 命令：

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
  -q
```

### Step 4: Studio 功能收口 GREEN

Codex 审核 Step 3 RED 后，写 Kiro `task.md` 和 Gemini prompt，再交 Gemini 实施。

实现目标：

- services 只依赖 `EngineAdapter` / `GatewayAdapter`。
- source run/predict 变成 `source -> ephemeral artifact -> run_artifact/predict_artifact`。
- artifact retrieval 强制 hash 校验。
- dev/prod missing hash 分层只用于完整性 not-found。
- publish 写 ProductArtifactStore release，并实现 two-stage atomicity + compensation GC。
- copilot route/fallback 走 GatewayAdapter。
- settings 只渲染 gateway 6-state。
- golden UI/backend 调 headless evaluator。
- resume endpoint 薄接 EngineAdapter。
- GRAPH authoring 走 shared parser/serializer。

## 5. RED 报告模板

```markdown
## Studio PM RED Report - Step N

Worktree:
Branch:
Changed tests:
Command:
Expected RED:
Actual output summary:
Why this proves the old path/interface gap:
Production code changed: No
Risks / cross-module blockers:
```

## 6. 实施报告模板

```markdown
## Studio PM Implementation Report - Step N

Worktree:
Branch:
Kiro task.md:
Gemini prompt:
Gemini implementation summary:
PM review summary:
Commands run:
Passing evidence:
Diff risk:
Cross-module contracts affected:
Ready for Codex review: Yes/No
```

## 7. Kiro task.md 要求

每个 Step 的 Kiro `task.md` 必须写：

- 目标。
- 非目标。
- 允许修改的文件。
- 禁止修改的文件。
- RED 测试清单。
- GREEN-1 接口/协议任务。
- GREEN-2 owner-side production path 任务。
- 验证命令。
- 回滚范围。

## 8. Gemini 实施提示词模板

```markdown
你是 Gemini，负责在 Studio PM 的 worktree 中实施 MVP1 三模块接口设计与修改的 Studio Step N。

必须先读：
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/02-implementation-plan.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/pm-studio-work-order.md
- .kiro/specs/mvp1-three-module-interface-2026-06-11/studio/step-N/task.md

硬约束：
- 只能改 task.md 允许的 Studio 文件和测试。
- 不得改 Engine/Gateway 生产代码。
- HTTP 本地模拟 harness 必须能触发传输族错误。
- 每个错误必须有专属 error_code。
- 只允许硬失败或显式降级，禁止静默降级。
- dev/prod 分层只允许用于完整性 hash not-found。
- publish 失败不能留下半成品。
- 不得改 FROZEN MVP1 文档。

当前 Step：
- Step N 名称：
- 已有 RED 测试和失败摘要：
- 目标测试命令：

请实施最小改动使目标测试通过，并在回复中提供：
1. 修改文件列表。
2. 关键实现说明。
3. 测试命令和结果。
4. 风险和未处理项。
```
