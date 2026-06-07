---
ws_id: WS-6-golden-eval-publish-history
modules: [02_capabilities/golden-eval, 02_capabilities/publish, 03_regions/local-history]
depends_on: [WS-0, WS-1, WS-3]
blocks: []
owns_files:
  - apps/studio/backend/app/services/golden_diff.py
  - apps/studio/backend/app/services/artifact_registry.py
  - apps/studio/backend/app/routers/golden.py
  - apps/studio/backend/app/routers/compare.py
  - apps/studio/backend/app/routers/skills.py
  - apps/studio/frontend/src/components/diff/
  - apps/studio/frontend/src/components/history/HistoryPanel.tsx
  - apps/studio/frontend/src/components/studio/Header.tsx
spec_ssot:
  - docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/publish/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md
  - docs/studio/mvp1/01_workflows/06_eval.md
  - docs/studio/mvp1/DESIGN_UNITS_INDEX.md
  - docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md
status: drafted
---

# WS-6 Golden/Eval/Publish/History — 需求书

本需求书是 WS-6 的契约输入。实现前必须先有 RED 测试、PM 契约门和用户在聊天窗口明确确认。

## 1. 目标(intent + why)

把 run artifacts 之后的验收闭环补齐：golden diff、eval、publish artifact autocommit 和 local history 只在真实 run 产物基础上运行，不再把 predict 或整段 final_state 误当 per-agent golden。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标真理：frontmatter `spec_ssot` 中 golden-eval、publish、local-history 的 `mvp1-alignment.md` 与 `01_workflows/06_eval.md`。
- 现状起点：`docs/studio/mvp1/02_capabilities/golden-eval/baseline.md`、`publish/baseline.md`、`docs/studio/mvp1/03_regions/local-history/baseline.md`。
- 全局索引：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 中 `golden-per-agent-node`、`publish-artifact-autocommit`、`local-history-snapshot`。
- 外部契约状态：engine physical layout/golden 落点按 floating-draft 消费；Studio 不复制 engine golden 内核。
- UI 规则：`docs/development/FRONTEND_UI_SPEC.md` §2；实现前查 `components/ui`，diff/history UI 使用语义 token、Playwright 或浏览器验证和窄宽度检查。
- 必读源码：frontmatter `owns_files` 中 golden diff、artifact registry、golden/compare/skills router、diff UI、HistoryPanel、Header。

## 3. 文件归属(并发锁,IR1)

本 WS owns frontmatter `owns_files`。`apps/studio/backend/app/routers/skills.py` 与 WS-1 共享，必须按 `docs/studio/mvp1/_impl/IMPL_PLAN.md` 串行：WS-6 只处理 publish 段，workspace/open-folder 由 WS-1。`apps/studio/frontend/src/components/studio/Header.tsx` 与 WS-1 共享，WS-6 只处理 release/publish/history 入口，shell 基座由 WS-1。

禁止触碰 run execution 内核、Settings/LLM、Copilot、debug resume、engine/gateway packages。范围外问题登记 deferred。

## 4. 现状锚点(baseline)

baseline 显示 golden_diff、artifact_registry、history/diff UI 已有基础，但 golden per-agent 落点、predict-source guard、publish artifact 和 local history 还未形成 MVP1 闭环。

## 5. 目标行为(可测的契约)

- Golden 只接受真实 run-source 产物，predict trace 不能被静默固化。
- Golden diff 以 per-agent/node 语义展示，不复制整段 final_state 当作目标态。
- Publish 生成本地 artifact/autocommit 最小闭环，并写入 local history 可见记录。
- HistoryPanel 能展示 run/publish 快照并进入 diff/compare 视图。
- UI 使用 `FRONTEND_UI_SPEC.md`、`components/ui` wrapper、语义 token、Playwright/浏览器验证和窄宽度检查。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，覆盖 predict trace 不能 promote、真实 run golden diff、artifact registry 写入、publish route、compare route、HistoryPanel 展示、diff UI 空态/失败态。至少一条真实 e2e 或手动验证必须从真实 run artifact 进入 golden/diff/publish/history；不许 fake mock 到绿。

## 7. 硬依赖约束

WS-6 依赖 WS-3 run artifacts 和 WS-1 native writer。engine golden 物理布局未 pinned 的字段必须写成 floating-draft 或 blocked 条件。修改后端 Python 后必须重启 Studio App。

## 8. 验收标准(硬退出,IR4)

- [ ] RED 测试先失败，PM 契约门通过后实现到 GREEN。
- [ ] Golden、publish、compare、history 的相关测试通过。
- [ ] Predict-source guard 保持有效，无回归。
- [ ] Playwright 或浏览器真实 e2e 覆盖 diff、publish/history 和窄宽度。
- [ ] 后端修改后完成 Studio App 重启验证。

## 9. 不做(范围锁定,IR7)

不做团队协作发布、远程 registry push、run engine 内核、debug resume、Copilot。范围外问题登记 deferred。

## 10. baseline 回写指令(IR6)

实现后按真实代码回写 golden-eval、publish、local-history 的 `baseline.md`。

## 11. 评审检查点

PM 契约门审 RED 是否覆盖真实 run-source、predict guard、artifact/history 和 no-fake。Codex 审查退出以 §8 为准。PM 终审检查 baseline 诚实。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/studio-mvp1/task-ws6-golden-eval-publish-history.md` 并输出 Gemini prompt。交接必须包含 owns_files、禁止触碰、验证命令、用户明确确认、baseline 回写和 PM 终审。
