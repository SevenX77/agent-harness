---
ws_id: WS-6-golden-eval-publish-history
doc: contract-gate
status: red-verified-task-authoring-approved
depends_on: [WS-0, WS-1, WS-3]
date: 2026-06-09
gate_decision: RED 已先行失败；用户已在聊天窗口明确确认写 Kiro task 与 Gemini prompt（2026-06-09）；GREEN 编码仍需再次明确确认
---

# WS-6 Golden/Eval/Publish/History — 契约门报告 (RED)

本文件记录 WS-6 在进入 GREEN 交接前的契约门状态。已完成只读核实、SSOT 对齐和 RED 测试落地；本文只授权写 task / prompt，不授权生产实现。

**当前状态**：`RED verified; task/prompt authoring approved; GREEN coding pending explicit confirmation`。

## 1. owns_files

本 WS 只允许在后续 GREEN 阶段触碰以下生产文件范围：

- `apps/studio/backend/app/services/golden_diff.py`
- `apps/studio/backend/app/services/artifact_registry.py`
- `apps/studio/backend/app/routers/golden.py`
- `apps/studio/backend/app/routers/compare.py`
- `apps/studio/backend/app/routers/skills.py`（仅 publish/history 段）
- `apps/studio/backend/app/models/golden.py`
- `apps/studio/backend/app/models/compare.py`
- `apps/studio/backend/app/models/git_history.py`（仅 publish history kind/DTO，若采用显式 kind）
- `apps/studio/backend/app/services/git_local.py`（仅 publish history kind/commit 可见记录，若采用 git history）
- `apps/studio/frontend/src/api/client.ts`
- `apps/studio/frontend/src/api/types.ts`
- `apps/studio/frontend/src/hooks/useGoldenDiff.ts`
- `apps/studio/frontend/src/components/diff/`
- `apps/studio/frontend/src/components/history/HistoryPanel.tsx`
- `apps/studio/frontend/src/components/studio/Header.tsx`（仅 Release/publish/history 入口）

## 2. 禁止触碰

- `packages/graph-agent/**`
- `packages/graph-agent-gateway/**`
- `docs/engine/**`
- `docs/graph-agent-gateway/**`
- `.kiro/specs/graph-agent-gateway-mvp1/**`
- `apps/studio/tests-e2e/**`
- WS-8 debug resume / checkpoint 相关代码
- WS-1 shell/native writer 基座、WS-4 Settings/LLM、WS-5 Copilot

本批继续遵守：不跑 e2e；不手工修 engine/gateway 冲突；engine/gateway 对接统一登记 deferred。

## 3. SSOT 与核实结果

已读并对齐：

- `AGENTS.md`
- `docs/development/FRONTEND_UI_SPEC.md` §2
- `docs/studio/mvp1/_impl/IMPL_PLAN.md`
- `.kiro/specs/studio-mvp1/requirements-ws6-golden-eval-publish-history.md`
- `docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md`
- `docs/studio/mvp1/02_capabilities/publish/mvp1-alignment.md`
- `docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md`
- `docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md`
- `docs/studio/mvp1/01_workflows/04_run-and-verify.md`
- `docs/studio/mvp1/01_workflows/06_eval.md`
- `docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md`

核实到一个 SSOT 漂移：当前主 worktree 没有 `docs/studio/mvp1/DESIGN_UNITS_INDEX.md`，但 WS-6 requirements 把它列为 SSOT 指针。GREEN 阶段不得假装该文件存在；只可把这个缺口登记为 requirement/source drift。

## 4. RED 测试与失败证据

### 4.1 后端 golden contract RED

文件：`apps/studio/backend/tests/routers/test_ws6_golden_contract_red.py`

运行：

```bash
uv run pytest apps/studio/backend/tests/routers/test_ws6_golden_contract_red.py -q
```

结果：`2 failed`

- `test_ws6_manual_per_agent_golden_can_be_saved_without_run_promotion`
  - 目标：manual per-agent-node golden 可以保存到 `.workspace/golden`，不依赖 run promotion。
  - 当前失败：HTTP `422`，因为当前 `SetGoldenReq` 只接受 `run_id` / `lock`。
- `test_ws6_whole_run_final_state_promotion_is_rejected`
  - 目标：旧的 whole-run `final_state.json` promote 被拒绝，不能继续作为 MVP1 golden。
  - 当前失败：HTTP `200`，因为当前实现仍允许复制 run `final_state.json` 成 golden。

### 4.2 Publish → Local History RED

文件：`apps/studio/backend/tests/routers/test_publish.py::test_publish_success_records_artifact_in_local_history`

运行：

```bash
uv run pytest apps/studio/backend/tests/routers/test_publish.py::test_publish_success_records_artifact_in_local_history -q
```

结果：`1 failed`

- 目标：Release 成功后 local history 可见 artifact 发布记录。
- 当前失败：history 为空。当前 publish 只返回 `PublishResult`，未写入本地历史可见记录。

### 4.3 前端 compare route RED

文件：`apps/studio/frontend/src/api/client.ws6.red.test.ts`

运行：

```bash
cd apps/studio/frontend && npm run test -- client.ws6.red.test.ts
```

结果：`1 failed`

- 目标：前端通过 `/skills/{skill_id}/runs/{run_id}/diff` 读取 run-vs-golden diff。
- 当前失败：`compareRunToGolden is not a function`。当前 `useGoldenDiff` 还内联调用 `/compare`，并且没有 API helper 锁定 `/diff` 契约。

### 4.4 Diff UI token RED

文件：`apps/studio/frontend/src/components/diff/DiffView.ws6.red.test.tsx`

运行：

```bash
cd apps/studio/frontend && npm run test -- DiffView.ws6.red.test.tsx
```

结果：`1 failed`

- 目标：DiffView 空态使用语义 design token 与本地 UI wrapper，不用一次性 palette class。
- 当前失败：输出包含 `bg-slate-*`、`text-slate-*`、`bg-sky-*`、`border-amber-*` 等硬编码 Tailwind palette class，且按钮不是本地 `Button` wrapper 输出。

## 5. 旧测试处置台账

以下旧测试不能作为 MVP1 目标真相：

- `apps/studio/backend/tests/test_api.py::test_set_golden_and_compare_run_diff`
  - 当前断言 whole-run promote + whole-run final_state diff。
  - GREEN 阶段必须改写或拆分为 per-agent-node golden/diff 契约。
- `apps/studio/backend/tests/test_skill_git_p0.py`
  - 当前在成功 run 后继续调用 `/golden` promote run id。
  - GREEN 阶段不得保留该旧 promote 语义；需要改成 local history / run artifact / per-node golden 目标。
- `apps/studio/backend/tests/services/test_git_local.py::test_auto_commit_respects_gitignore_latest_but_commits_golden`
  - 当前仍允许 `.workspace/golden/run-1` 进入 auto-run commit。
  - 如果 WS-6 采用 per-node workspace golden，需按真实新布局调整，不得重新提交 whole-run final_state。

以下测试可作为回归锁保留：

- `apps/studio/backend/tests/test_diagnostic_export.py` 的 predict promotion guard。
- `apps/studio/backend/tests/services/test_artifact_registry.py` 的 package excludes `.workspace` / registry error。
- `apps/studio/backend/tests/routers/test_publish.py` 既有 Artifact Registry precondition/error/success 测试。
- `apps/studio/backend/tests/test_skill_git_history.py` 的 history list/revert 基础行为。
- `apps/studio/frontend/src/components/history/HistoryPanel.test.tsx` 的 local history 空态、失败态、revert 行为。

## 6. Deferred / Floating Draft

- engine golden 的 exact physical layout 仍未 pinned：`docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md` 只确认 golden 在 `.workspace/golden/`，但 per-node 绑定键仍是 gap。GREEN 可用 Studio-side floating draft 布局，但必须在 baseline/收尾里诚实标注。
- `DESIGN_UNITS_INDEX.md` 缺失：登记 source drift，不在本批补写。
- WS-8 Debug Resume 继续 blocked。
- backend pytest / sidecar vendor 仍可能被 `origin/main` 缺少 `graph_agent_gateway.registry.endpoints` 挡住；不要在 WS-6 复制 gateway helper。
- 真实 e2e 暂停；完成 UI 改动后只做浏览器/Tauri 手动点击验证和窄宽度检查，除非用户重新批准 e2e。

## 7. 契约门结论

- [x] RED 测试已先写并真实失败。
- [x] 失败点对应 WS-6 MVP1 drift，而不是语法或路径夹具错误。
- [x] 用户已在聊天窗口明确确认写 Kiro task 与 Gemini prompt。
- [ ] GREEN 编码授权：pending。后续实现生产代码前仍需用户在聊天窗口再次明确确认。

## 8. 交接要求

据本文写 `.kiro/specs/studio-mvp1/task-ws6-golden-eval-publish-history.md`，并在 task 中内嵌 Gemini prompt。Prompt 不单独落成 `gemini-prompt-ws*.md`，避免触发 WS-0 文档门禁。
