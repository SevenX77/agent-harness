# Engine PM 作业单：MVP1 三模块接口设计与修改（2026-06-11）

## 1. PM 角色

你是 Engine PM，只负责 `packages/graph-agent` 内的接口定义、测试、实现审查和交付报告。你不能直接改 Studio/Gateway 生产代码；跨模块需要通过报告交给 Codex 协调。

## 2. 建立 worktree 和分支

从主仓库根目录执行：

```bash
cd /Users/sevenx/Documents/coding/agent-harness
git worktree add .worktrees/pm-engine-mvp1-interface-2026-06-11 -b codex/pm-engine-mvp1-interface-2026-06-11 feat/studio-mvp1-integration
cd .worktrees/pm-engine-mvp1-interface-2026-06-11
```

## 3. 每一步固定流程

每一步都按下面流程执行：

1. 只写/改测试，确认 RED。
2. 提交 RED 报告给 Codex。
3. Codex 审核通过后，写 Kiro spec：`.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-N/task.md`。
4. 写 Gemini prompt：`.kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-N/gemini-prompt.md`。
5. 把 prompt 交给 Gemini 实施。
6. 审核 Gemini diff 和测试输出。
7. 审核无误后提交实施报告给 Codex。
8. Codex 复审通过后进入下一步。

## 4. 四步任务

### Step 1: Engine 接口定义 RED

只允许新增/修改测试：

- `packages/graph-agent/tests/core/test_productization_artifact_contracts.py`
- `packages/graph-agent/tests/core/test_productization_storage_contracts.py`
- `packages/graph-agent/tests/core/test_productization_llm_event_contracts.py`
- `packages/graph-agent/tests/core/test_productization_run_result_contracts.py`

RED 必须覆盖：

- `ArtifactRef`、`CompiledArtifactManifest`、`RunArtifactRequest`、`PredictArtifactRequest`、`ResumeRequest`、`RunSession`。
- runtime request 必须有 `idempotency_key`，不得有 `skill_path`。
- `RunArtifactStore` 必须有 `seal_run`，seal 后再写必须被拒。
- `get_object(hash=...)` 必须重算 hash，损坏字节硬失败。
- `LeaseToken` 必须有单调 `fencing_token`。
- `ResponseEnvelope` 必须有 `schema_version` 和结构化错误 payload。
- run result contract 只供 golden headless 读取，不启动 run。

RED 命令：

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_productization_artifact_contracts.py \
  packages/graph-agent/tests/core/test_productization_storage_contracts.py \
  packages/graph-agent/tests/core/test_productization_llm_event_contracts.py \
  packages/graph-agent/tests/core/test_productization_run_result_contracts.py \
  -q
```

### Step 2: Engine 接口定义 GREEN

Codex 审核 Step 1 RED 后，写 Kiro `task.md` 和 Gemini prompt，再交 Gemini 实施。

实现目标：

- 新增/修改：
  - `packages/graph-agent/src/graph_agent/core/artifacts.py`
  - `packages/graph-agent/src/graph_agent/core/adapter_contracts.py`
  - `packages/graph-agent/src/graph_agent/core/storage_contracts.py`
  - `packages/graph-agent/src/graph_agent/core/llm_provider.py`
  - `packages/graph-agent/src/graph_agent/core/event_contracts.py`
  - `packages/graph-agent/src/graph_agent/core/result_contracts.py`
- `GREEN-2` 必须有 owner-side 最小 production path。
- `LLMProvider` contract fake 是唯一允许例外，必须在报告中说明。

### Step 3: Engine 功能收口 RED

只允许新增/修改测试：

- `packages/graph-agent/tests/core/test_productization_compile_artifact_red.py`
- `packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py`
- `packages/graph-agent/tests/core/test_productization_engine_storage_red.py`
- `packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py`
- `packages/graph-agent/tests/core/test_productization_event_stream_red.py`

RED 必须覆盖：

- 同源不同 temp root 编译 hash 必须一致；mtime 变化不影响 hash。
- UI metadata 不进入 execution fingerprint。
- `run_artifact` 同 `Idempotency-Key` 只能执行一次。
- core runtime 拒绝 raw `skill_path`。
- run artifact 写入 `RunArtifactStore`。
- seal 后再写报 `artifact.sealed_write`。
- lease 冲突报 `state.lease_conflict`。
- stale fencing token 报 `state.lease_fenced`。
- Engine import `graph_agent` 时不能依赖 `graph_agent_gateway`。
- 未注入 SPI 报 `llm.provider_not_configured`。
- provider invoke 失败经 SPI error shape 上报。
- event stream 支持 cursor 续接、seq 去重、gap、cursor too old、backpressure、乱序处理。

RED 命令：

```bash
uv run pytest \
  packages/graph-agent/tests/core/test_productization_compile_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_run_by_artifact_red.py \
  packages/graph-agent/tests/core/test_productization_engine_storage_red.py \
  packages/graph-agent/tests/core/test_productization_gateway_dependency_red.py \
  packages/graph-agent/tests/core/test_productization_event_stream_red.py \
  -q
```

### Step 4: Engine 功能收口 GREEN

Codex 审核 Step 3 RED 后，写 Kiro `task.md` 和 Gemini prompt，再交 Gemini 实施。

实现目标：

- `compile` 输出 frozen artifact identity、source map、execution fingerprint。
- `run_artifact` / `predict_artifact` 成为核心 runtime 入口。
- `run_skill` / source entry 只能是 host/adapter 兼容包装。
- run artifact 写 `RunArtifactStore`。
- checkpoint/resume 写 `RuntimeStateStore` 并校验 lease/fencing。
- Engine 去除 gateway concrete import。
- event stream 统一 `EventEnvelope`。

## 5. RED 报告模板

```markdown
## Engine PM RED Report - Step N

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
## Engine PM Implementation Report - Step N

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
你是 Gemini，负责在 Engine PM 的 worktree 中实施 MVP1 三模块接口设计与修改的 Engine Step N。

必须先读：
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/02-implementation-plan.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/pm-engine-work-order.md
- .kiro/specs/mvp1-three-module-interface-2026-06-11/engine/step-N/task.md

硬约束：
- 只能改 task.md 允许的 Engine 文件和测试。
- 不得改 Studio/Gateway 生产代码。
- 每个错误必须有专属 error_code。
- 只允许硬失败或显式降级，禁止静默降级。
- GREEN-2 不能 fake；唯一例外是 LLMProvider SPI contract fake。
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
