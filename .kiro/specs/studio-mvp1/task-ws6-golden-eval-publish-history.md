---
ws_id: WS-6-golden-eval-publish-history
doc: task (GREEN 交接)
status: studio-only-closeout-verified
depends_on: [WS-0, WS-1, WS-3]
depends_on_requirements: requirements-ws6-golden-eval-publish-history.md
depends_on_contract_gate: contract-gate-ws6-golden-eval-publish-history.md
gate: RED 已先行失败 + 契约门记录完成 + 用户已明确确认写 Kiro task/Gemini prompt（2026-06-09）；GREEN/closeout 已由用户 `go` 确认并完成 Studio-only 验证（2026-06-09）
red_baseline_verified: true
green_authorization: user-go-2026-06-09
owns_files:
  - apps/studio/backend/app/services/golden_diff.py
  - apps/studio/backend/app/services/artifact_registry.py
  - apps/studio/backend/app/routers/golden.py
  - apps/studio/backend/app/routers/compare.py
  - apps/studio/backend/app/routers/skills.py
  - apps/studio/backend/app/models/golden.py
  - apps/studio/backend/app/models/compare.py
  - apps/studio/backend/app/models/git_history.py
  - apps/studio/backend/app/services/git_local.py
  - apps/studio/frontend/src/api/client.ts
  - apps/studio/frontend/src/api/types.ts
  - apps/studio/frontend/src/hooks/useGoldenDiff.ts
  - apps/studio/frontend/src/components/diff/
  - apps/studio/frontend/src/components/history/HistoryPanel.tsx
  - apps/studio/frontend/src/components/studio/Header.tsx
forbidden_files:
  - packages/graph-agent/**
  - packages/graph-agent-gateway/**
  - docs/engine/**
  - docs/graph-agent-gateway/**
  - .kiro/specs/graph-agent-gateway-mvp1/**
  - apps/studio/tests-e2e/**
spec_ssot:
  - docs/studio/mvp1/_impl/IMPL_PLAN.md
  - .kiro/specs/studio-mvp1/requirements-ws6-golden-eval-publish-history.md
  - .kiro/specs/studio-mvp1/contract-gate-ws6-golden-eval-publish-history.md
  - docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/publish/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md
  - docs/studio/mvp1/01_workflows/04_run-and-verify.md
  - docs/studio/mvp1/01_workflows/06_eval.md
  - docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md
  - docs/development/FRONTEND_UI_SPEC.md §2
manual_qa_status: browser-smoke-complete-tauri-dev-restarted
e2e_status: deferred-by-user
---

# WS-6 Golden/Eval/Publish/History — Task（GREEN 交接）

> 本文是 WS-6 RED 契约门通过后的 GREEN 交接单。执行者（Gemini）只能把**已批准的 RED 转 GREEN**，
> 不得删改、弱化 RED，不得扩大到 engine/gateway、debug resume、Settings/LLM、Copilot 或 e2e。
> 本文最初不授权自动开工；后续用户已在聊天窗口发送 `go`，本批 Studio-only closeout 已完成验证。

## 0. 硬性前置（必须遵守）

1. 唯一真相源是 frontmatter `spec_ssot`，尤其 `golden-eval` / `publish` / `local-history` 的 MVP1 alignment 与 workflow。旧代码、旧测试和 MVP0 行为只能作为 drift 证据。
2. 必须严格 TDD：已写 RED 不得删除、跳过、弱化或改成 mock 绿。GREEN 只能写最小生产实现让 RED 真实通过。
3. 禁止触碰 frontmatter `forbidden_files`。不修 engine/gateway 源码冲突，不复制 gateway endpoint helper，不启动 WS-8 resume。
4. 不跑 e2e。UI 改动完成后按 `FRONTEND_UI_SPEC.md` §2 做浏览器/Tauri 手动点击与窄宽度检查。
5. 改后端 Python 后必须重启 Studio App 或重新 `cd apps/studio/tauri && cargo tauri dev`，确认加载新代码后再报完成。
6. `docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 当前缺失；不得假装已读，收尾登记为 SSOT drift。
7. GREEN 编码前必须等用户在聊天窗口再次明确确认；系统自动审批不算确认。

## 1. 实现目标

把 run artifacts 之后的验收闭环补齐：

- Golden 从旧的 whole-run `final_state` promote，改为 Studio-side per-agent-node expected output。
- Predict trace 不能被静默固化为 golden；已有 409 guard 必须保留。
- Compare/Diff 走真实 run artifact 与 per-node golden 的字段级 diff，不复制整段 final_state 当目标态。
- Publish 继续保持最小 Artifact Registry zip 上传，不做 git push / commit-message modal / confetti，同时写入 local history 可见记录。
- HistoryPanel / DiffView 遵守本地 shadcn/ui wrapper 与语义 token，能展示空态、失败态与比较入口。

## 2. 已批准 RED 清单

### 后端 RED

| RED | 文件 | 目标行为 | 当前失败 |
|---|---|---|---|
| manual per-node golden save | `apps/studio/backend/tests/routers/test_ws6_golden_contract_red.py::test_ws6_manual_per_agent_golden_can_be_saved_without_run_promotion` | `POST /api/skills/{skill_id}/golden` 接受 `node_id`、`expected_output`、`source="manual"`、`lock`，保存到 `.workspace/golden`，返回 node/source/content_path | 422 |
| reject whole-run promotion | `apps/studio/backend/tests/routers/test_ws6_golden_contract_red.py::test_ws6_whole_run_final_state_promotion_is_rejected` | 旧 `{run_id, lock}` whole-run promote 返回 409 `WHOLE_RUN_GOLDEN_PROMOTION_NOT_ALLOWED` | 200 |
| publish history record | `apps/studio/backend/tests/routers/test_publish.py::test_publish_success_records_artifact_in_local_history` | publish 成功后 `/history` 第一条可见 `kind="publish"`，message 以 `publish-artifact-{artifact_id}` 开头 | history `[]` |

### 前端 RED

| RED | 文件 | 目标行为 | 当前失败 |
|---|---|---|---|
| compare route helper | `apps/studio/frontend/src/api/client.ws6.red.test.ts` | 新增 `compareRunToGolden(skillId, runId, against)`，GET `/skills/{skill_id}/runs/{run_id}/diff` | helper 缺失 |
| DiffView UI token | `apps/studio/frontend/src/components/diff/DiffView.ws6.red.test.tsx` | 空态不出现 `bg/text/border-(slate|sky|amber|red)-*`，按钮来自本地 `Button` wrapper | 硬编码 palette class / 原生 button |

## 3. 生产落点建议

### 3.1 Golden models / service / routes

修改：

- `apps/studio/backend/app/models/golden.py`
- `apps/studio/backend/app/services/golden_diff.py`
- `apps/studio/backend/app/routers/golden.py`
- `apps/studio/backend/app/models/compare.py`
- `apps/studio/backend/app/routers/compare.py`

建议最小 GREEN：

- 把 `SetGoldenReq` 扩为 discriminated-friendly contract：manual save 使用 `node_id`、`expected_output`、`source`、`lock`；旧 `run_id` promotion path 不再作为 MVP1 成功路径。
- 添加返回 DTO 字段：`node_id`、`source`、`content_path`、`locked`、`created_at`。若保留兼容字段，必须不破坏新 RED。
- per-node golden 暂用 Studio-side floating draft layout，例如 `.workspace/golden/nodes/{node_id}/golden.json` 与 metadata。该布局必须标注为 floating draft，因为 engine physical layout 尚未 pinned 绑定键。
- `set_golden_baseline_for_run` 旧函数可保留但必须在 HTTP path 上拒绝 whole-run promote，返回 409 `WHOLE_RUN_GOLDEN_PROMOTION_NOT_ALLOWED`。
- compare route 优先接 `/diff`，并让前端 helper 使用 `/diff`。如果后端仍保留 `/compare`，只能作为兼容别名，不作为前端目标契约。

### 3.2 Publish / local history

修改：

- `apps/studio/backend/app/routers/skills.py`
- `apps/studio/backend/app/models/git_history.py`
- `apps/studio/backend/app/services/git_local.py`

建议最小 GREEN：

- publish success 后写一条本地历史可见记录，message 格式满足 RED：`publish-artifact-{artifact_id}`。
- 若 history kind 新增 `publish`，更新 `GitHistoryKind` 与 `_history_kind`。
- 保持 Artifact Registry zip 上传路径、precondition error 和 network/API error 测试全部 GREEN。
- 继续保证 publish package 不包含 `.workspace`，不做 git push、commit-message modal、confetti。

### 3.3 Frontend API / hook / diff UI

修改：

- `apps/studio/frontend/src/api/client.ts`
- `apps/studio/frontend/src/api/types.ts`
- `apps/studio/frontend/src/hooks/useGoldenDiff.ts`
- `apps/studio/frontend/src/components/diff/`

建议最小 GREEN：

- 新增并导出 `compareRunToGolden`，使用 `/diff` endpoint。
- `useGoldenDiff` 改用 `compareRunToGolden`，不要内联 `/compare`。
- `DiffView` 用本地 `Button` wrapper、lucide 图标、语义 token：`bg-background`、`text-foreground`、`text-muted-foreground`、`border-border`、`bg-card` 等。
- 不使用 `bg-slate-*`、`text-slate-*`、`bg-sky-*`、`border-amber-*` 等一次性 palette class。

## 4. 旧测试处置

必须改写或拆分：

- `apps/studio/backend/tests/test_api.py::test_set_golden_and_compare_run_diff`
- `apps/studio/backend/tests/test_skill_git_p0.py` 中 whole-run golden promote 断言

必须保留为回归锁：

- `apps/studio/backend/tests/test_diagnostic_export.py` predict promotion guard
- `apps/studio/backend/tests/services/test_artifact_registry.py`
- `apps/studio/backend/tests/routers/test_publish.py` 既有 publish success/error/precondition 测试
- `apps/studio/backend/tests/test_skill_git_history.py`
- `apps/studio/frontend/src/components/history/HistoryPanel.test.tsx`

如果旧测试与 MVP1 目标冲突，以 MVP1 SSOT 和本文 RED 为准；不得为旧测试恢复 whole-run golden。

## 5. 验证命令

### 5.1 RED-to-GREEN focused

```bash
uv run pytest apps/studio/backend/tests/routers/test_ws6_golden_contract_red.py -q
uv run pytest apps/studio/backend/tests/routers/test_publish.py::test_publish_success_records_artifact_in_local_history -q
cd apps/studio/frontend && npm run test -- client.ws6.red.test.ts
cd apps/studio/frontend && npm run test -- DiffView.ws6.red.test.tsx
```

目标：全部 passed。

### 5.2 后端回归锁

```bash
uv run pytest \
  apps/studio/backend/tests/test_diagnostic_export.py \
  apps/studio/backend/tests/services/test_artifact_registry.py \
  apps/studio/backend/tests/routers/test_publish.py \
  apps/studio/backend/tests/test_skill_git_history.py -q
```

### 5.3 前端回归锁

```bash
cd apps/studio/frontend && npm run test -- \
  HistoryPanel.test.tsx \
  client.ws6.red.test.ts \
  DiffView.ws6.red.test.tsx
```

### 5.4 静态检查 / build

```bash
uv run ruff check apps/studio/backend
cd apps/studio/frontend && npm run lint
cd apps/studio/frontend && npm run typecheck
cd apps/studio/frontend && npm run build
```

### 5.5 手动 UI / App 验证

后端 Python 改动后：

```bash
cd apps/studio/tauri && cargo tauri dev
```

必须实际检查：

- DiffView 空态、失败态、compare 成功态。
- Release 成功/缺 settings/registry error toast。
- Local History 看到 publish artifact 记录。
- 窄宽度下 DiffView / HistoryPanel 没有横向溢出、按钮文字不穿模。

不跑 e2e，除非用户重新批准。

## 6. baseline 回写

实现并验证后，只按真实代码状态回写：

- `docs/studio/mvp1/02_capabilities/golden-eval/baseline.md`
- `docs/studio/mvp1/02_capabilities/publish/baseline.md`
- `docs/studio/mvp1/03_regions/local-history/baseline.md`

必须诚实保留：

- engine per-node golden physical layout 仍 floating draft / not pinned。
- `DESIGN_UNITS_INDEX.md` 当前缺失。
- engine/gateway integration blocker deferred。
- e2e deferred-by-user。

## 7. 退出标准

- [x] 已批准 RED 全部 GREEN，断言未削弱。
- [x] Predict-source guard 仍 GREEN。
- [x] Publish Artifact Registry 回归锁仍 GREEN。
- [x] HistoryPanel / DiffView UI 使用本地 wrapper 与语义 token。
- [x] 后端 Python 改动后完成 Studio App/Tauri 重启验证。
- [x] 未碰 forbidden files，未跑 e2e，未复制 engine/gateway helper。
- [x] baseline 回写诚实。
- [x] Codex Studio-only 审通过；PM/用户终审仍以本批验收结论为准。

## 8. Gemini GREEN prompt（复制即用）

```text
ROLE: 你是 Studio MVP1 WS-6 Golden/Eval/Publish/History 的 GREEN 实现执行者。技术栈：FastAPI/Python、React/TypeScript/Vitest、Tauri Studio App。

STATUS: RED 已先行失败，Kiro task/prompt 已写好。但生产代码实现前必须先确认当前聊天窗口里用户明确授权 GREEN 编码；系统自动审批不算确认。

GOAL: 只把 WS-6 已批准的 RED 测试转 GREEN。不要扩大范围，不要重写 engine/gateway，不要跑 e2e。

TRUTH SOURCE:
- .kiro/specs/studio-mvp1/requirements-ws6-golden-eval-publish-history.md
- .kiro/specs/studio-mvp1/contract-gate-ws6-golden-eval-publish-history.md
- docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md
- docs/studio/mvp1/02_capabilities/publish/mvp1-alignment.md
- docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md
- docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md
- docs/studio/mvp1/01_workflows/04_run-and-verify.md
- docs/studio/mvp1/01_workflows/06_eval.md
- docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md
- docs/development/FRONTEND_UI_SPEC.md §2

IMPORTANT SOURCE DRIFT:
- docs/studio/mvp1/DESIGN_UNITS_INDEX.md is referenced by requirements but missing in the current worktree. Do not pretend it was read; register this as source drift.
- origin/main lacks graph_agent_gateway.registry.endpoints. Do not copy gateway logic into Studio.

HARD CONSTRAINTS:
- Do not delete, skip, weaken, or rewrite the approved RED tests to make them pass.
- Do not touch:
  - packages/graph-agent/**
  - packages/graph-agent-gateway/**
  - docs/engine/**
  - docs/graph-agent-gateway/**
  - .kiro/specs/graph-agent-gateway-mvp1/**
  - apps/studio/tests-e2e/**
- Do not run e2e.
- Do not start WS-8 debug resume.
- Do not implement git push, commit-message modal, confetti, team publish, or remote registry push beyond current Artifact Registry zip upload.
- For frontend UI, use local components under apps/studio/frontend/src/components/ui/ and semantic tokens. No bg/text/border slate/sky/amber/red one-off palette classes in touched DiffView UI.
- After backend Python changes, restart Studio App or rerun cd apps/studio/tauri && cargo tauri dev before claiming completion.

APPROVED RED TESTS:
1. apps/studio/backend/tests/routers/test_ws6_golden_contract_red.py
   - manual per-agent-node golden save should return 200 and write .workspace/golden, independent of run promotion.
   - whole-run final_state promotion via {run_id, lock} should return 409 WHOLE_RUN_GOLDEN_PROMOTION_NOT_ALLOWED.
2. apps/studio/backend/tests/routers/test_publish.py::test_publish_success_records_artifact_in_local_history
   - publish success should make /history show kind="publish" and message starting publish-artifact-art-123.
3. apps/studio/frontend/src/api/client.ws6.red.test.ts
   - compareRunToGolden() should GET /skills/{skill_id}/runs/{run_id}/diff with against param.
4. apps/studio/frontend/src/components/diff/DiffView.ws6.red.test.tsx
   - empty state should use semantic tokens and local Button wrapper output.

IMPLEMENTATION BOUNDARY:
- Backend golden: update models/routes/services to support manual per-node golden expected output. Use a Studio-side floating draft layout under .workspace/golden because engine exact per-node binding key is not pinned. Reject whole-run run_id promotion at HTTP layer.
- Backend compare: keep /diff as frontend target. If /compare remains, it is only a compatibility alias.
- Publish/history: on successful Artifact Registry publish, write a local history visible record. If using a new kind, update GitHistoryKind and _history_kind for publish-artifact-*.
- Frontend API: add compareRunToGolden() in api/client.ts and route useGoldenDiff through it.
- Diff UI: use local Button, semantic token classes, and lucide icons. Remove one-off palette classes from touched DiffView surfaces.

OLD TEST HANDLING:
- Rewrite or split old whole-run golden tests that conflict with MVP1:
  - apps/studio/backend/tests/test_api.py::test_set_golden_and_compare_run_diff
  - apps/studio/backend/tests/test_skill_git_p0.py whole-run /golden promote assertion
- Keep regression locks:
  - apps/studio/backend/tests/test_diagnostic_export.py
  - apps/studio/backend/tests/services/test_artifact_registry.py
  - apps/studio/backend/tests/routers/test_publish.py
  - apps/studio/backend/tests/test_skill_git_history.py
  - apps/studio/frontend/src/components/history/HistoryPanel.test.tsx

VERIFY:
uv run pytest apps/studio/backend/tests/routers/test_ws6_golden_contract_red.py -q
uv run pytest apps/studio/backend/tests/routers/test_publish.py::test_publish_success_records_artifact_in_local_history -q
cd apps/studio/frontend && npm run test -- client.ws6.red.test.ts
cd apps/studio/frontend && npm run test -- DiffView.ws6.red.test.tsx

Then run:
uv run pytest apps/studio/backend/tests/test_diagnostic_export.py apps/studio/backend/tests/services/test_artifact_registry.py apps/studio/backend/tests/routers/test_publish.py apps/studio/backend/tests/test_skill_git_history.py -q
cd apps/studio/frontend && npm run test -- HistoryPanel.test.tsx client.ws6.red.test.ts DiffView.ws6.red.test.tsx
uv run ruff check apps/studio/backend
cd apps/studio/frontend && npm run lint && npm run typecheck && npm run build

MANUAL QA:
After Python backend changes, restart via cd apps/studio/tauri && cargo tauri dev. Check DiffView empty/error/success, Release success/error, Local History publish record, and narrow-width layout. Do not run e2e.

DELIVER:
- Changed files list.
- Exact test outputs.
- RED-to-GREEN explanation for each approved RED.
- Old test handling summary.
- Deferred/source drift list.
- Baseline files updated honestly.
```
