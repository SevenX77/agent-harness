# Gateway PM 作业单：MVP1 三模块接口设计与修改（2026-06-11）

## 1. PM 角色

你是 Gateway PM，只负责 `packages/graph-agent-gateway` 内的接口定义、测试、实现审查和交付报告。你不能直接改 Engine/Studio 生产代码；跨模块需要通过报告交给 Codex 协调。

## 2. 建立 worktree 和分支

从主仓库根目录执行：

```bash
cd /Users/sevenx/Documents/coding/agent-harness
git worktree add .worktrees/pm-gateway-mvp1-interface-2026-06-11 -b codex/pm-gateway-mvp1-interface-2026-06-11 feat/studio-mvp1-integration
cd .worktrees/pm-gateway-mvp1-interface-2026-06-11
```

## 3. 每一步固定流程

每一步都按下面流程执行：

1. 只写/改测试，确认 RED。
2. 提交 RED 报告给 Codex。
3. Codex 审核通过后，写 Kiro spec：`.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-N/task.md`。
4. 写 Gemini prompt：`.kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-N/gemini-prompt.md`。
5. 把 prompt 交给 Gemini 实施。
6. 审核 Gemini diff 和测试输出。
7. 审核无误后提交实施报告给 Codex。
8. Codex 复审通过后进入下一步。

## 4. 四步任务

### Step 1: Gateway 接口定义 RED

只允许新增/修改测试：

- `packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py`
- `packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py`

RED 必须覆盖：

- `ConfigTruthStore` 必须要求 `user_id`。
- `get_config` 返回 `etag`。
- `put_config` 支持 `if_match` 和 `if_none_match="*"`。
- stale `etag` 必须报冲突。
- `CredentialResolveRequest.source` 支持 `local_input` / `remote_vault`。
- `CredentialResolveResponse` 返回 `secret_handle` / `expires_at`，不返回 raw secret。
- route handoff DTO 有 `role`、`routes`、`skipped`。
- fallback decision action 是 `retry_same` / `switch_route` / `give_up`。
- 空 route、空 fallback chain、give_up 必须显式错误。
- 6-state failed reason 只允许 `missing_config`、`endpoint_unreachable`、`model_failed`。

RED 命令：

```bash
uv run pytest \
  packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py \
  packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py \
  -q
```

### Step 2: Gateway 接口定义 GREEN

Codex 审核 Step 1 RED 后，写 Kiro `task.md` 和 Gemini prompt，再交 Gemini 实施。

实现范围：

- `packages/graph-agent-gateway/src/graph_agent_gateway/storage_contracts.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/credential_resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_handoff.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/fallback_decision.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`

实现目标：

- 配置真相线接口含 `etag` / `if_match` / `if_none_match`。
- 凭证解析接口含 source、secret handle、`expires_at`。
- route/fallback/materialize/projection DTO 完整。
- 资源终态有 error payload，不是普通空值。

### Step 3: Gateway 功能收口 RED

只允许新增/修改测试：

- `packages/graph-agent-gateway/tests/test_productization_resolver_storage_red.py`
- `packages/graph-agent-gateway/tests/test_productization_fallback_decision_red.py`
- `packages/graph-agent-gateway/tests/test_productization_state_projection_red.py`
- `packages/graph-agent-gateway/tests/test_productization_credential_failure_red.py`
- `packages/graph-agent-gateway/tests/test_productization_resource_terminal_red.py`

RED 必须覆盖：

- `ModelResolver` 仍能绕过 `ConfigTruthStore` 读 path/snapshot。
- 两个并发 `put_config` 同 key 可能 last-writer-wins。
- stale `etag` 未报 `config.etag_conflict`。
- fallback decision 仍藏在 `GatewayChatModel` 私有逻辑里。
- Gateway 包内没有 6-state projection/materialize 实现。
- fake vault 5xx 未报 `credential.vault_unreachable`。
- expired secret handle 被拿去执行。
- no route / give_up / empty fallback chain 被当普通空值继续跑。

RED 命令：

```bash
uv run pytest \
  packages/graph-agent-gateway/tests/test_productization_resolver_storage_red.py \
  packages/graph-agent-gateway/tests/test_productization_fallback_decision_red.py \
  packages/graph-agent-gateway/tests/test_productization_state_projection_red.py \
  packages/graph-agent-gateway/tests/test_productization_credential_failure_red.py \
  packages/graph-agent-gateway/tests/test_productization_resource_terminal_red.py \
  -q
```

### Step 4: Gateway 功能收口 GREEN

Codex 审核 Step 3 RED 后，写 Kiro `task.md` 和 Gemini prompt，再交 Gemini 实施。

实现目标：

- resolver 配置读取走 `ConfigTruthStore`。
- credential source 和 expiry 按契约处理。
- fallback decision 导出为公共函数。
- 6-state projection/materialize 下沉 gateway。
- 空路线、give_up、空 fallback chain 都输出显式 error code。

## 5. RED 报告模板

```markdown
## Gateway PM RED Report - Step N

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
## Gateway PM Implementation Report - Step N

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
你是 Gemini，负责在 Gateway PM 的 worktree 中实施 MVP1 三模块接口设计与修改的 Gateway Step N。

必须先读：
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/02-implementation-plan.md
- docs/mvp1-three-module-interface-design-and-changes-2026-06-11/pm-gateway-work-order.md
- .kiro/specs/mvp1-three-module-interface-2026-06-11/gateway/step-N/task.md

硬约束：
- 只能改 task.md 允许的 Gateway 文件和测试。
- 不得改 Engine/Studio 生产代码。
- 每个错误必须有专属 error_code。
- 只允许硬失败或显式降级，禁止静默降级。
- 凭证接口不得泄漏 raw secret。
- 空 route / give_up / empty fallback_chain 必须显式错误化。
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
