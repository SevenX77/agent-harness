---
ws_id: WS-8-debug-resume
modules: [02_capabilities/debug-resume, 03_regions/local-history, 03_regions/timeline]
depends_on: [WS-0, WS-1, WS-3]
blocks: []
owns_files:
  - apps/studio/backend/app/routers/debug.py
  - apps/studio/backend/app/routers/runs.py
  - apps/studio/frontend/src/components/history/RunDetailDrawer.tsx
  - apps/studio/frontend/src/components/trace/TraceEventRow.tsx
  - apps/studio/frontend/src/components/studio/Workspace.tsx
spec_ssot:
  - docs/studio/mvp1/02_capabilities/debug-resume/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md
  - docs/studio/mvp1/01_workflows/05_debugging.md
  - docs/studio/mvp1/DESIGN_UNITS_INDEX.md
  - docs/engine/mvp1/_migration-src/10-iteration-and-resume/mvp1-alignment.md
status: drafted
---

# WS-8 Debug Resume — 需求书

本需求书是 WS-8 的契约输入。实现前必须先有 RED 测试、PM 契约门和用户在聊天窗口明确确认。

## 1. 目标(intent + why)

在 engine checkpoint/resume API pinned 后，把 Studio 的 debug resume 从 501/占位变成可诊断、可恢复的节点级续跑入口；在契约未 pinned 前，需求书只能表达 blocked 或条件放行。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标真理：frontmatter `spec_ssot` 中 debug-resume、local-history、timeline 的 `mvp1-alignment.md` 与 `01_workflows/05_debugging.md`。
- 现状起点：`docs/studio/mvp1/02_capabilities/debug-resume/baseline.md`、`docs/studio/mvp1/03_regions/local-history/baseline.md`、`docs/studio/mvp1/03_regions/timeline/baseline.md`。
- 全局索引：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 中 `debug-resume-checkpoint`。
- 外部契约状态：engine checkpoint/resume 当前为 floating-draft，未 pinned 时 WS-8 blocked；Studio 不复制 engine checkpoint 内核。
- UI 规则：`docs/development/FRONTEND_UI_SPEC.md` §2；实现前先查 `components/ui`，使用语义 token、Playwright/浏览器验证和窄宽度检查。
- 必读源码：frontmatter `owns_files` 中 debug router、runs router resume 段、history drawer、trace row 和 Workspace action。

## 3. 文件归属(并发锁,IR1)

本 WS owns frontmatter `owns_files`。`apps/studio/backend/app/routers/runs.py` 与 WS-3 共享，必须按 `docs/studio/mvp1/_impl/IMPL_PLAN.md` 串行：WS-8 只处理 resume 段，run/predict/trace 由 WS-3。`apps/studio/frontend/src/components/studio/Workspace.tsx` 与 WS-1、WS-3 共享，WS-8 只处理 resume action，shell 和 run action 先释放后再接入。

禁止触碰 authoring、Settings/LLM、Copilot、golden/publish、engine package。范围外问题登记 deferred。

## 4. 现状锚点(baseline)

baseline 显示 Studio resume 当前仍是占位或 501，history/trace 中尚未有可执行的 checkpoint resume 闭环。

## 5. 目标行为(可测的契约)

- engine checkpoint/resume API 未 pinned 时，UI 和后端必须显示 blocked/条件放行，不伪装已可执行。
- API pinned 后，RunDetail/Trace/Workspace 中 resume action 使用后端 debug/runs contract，错误可诊断。
- resume 必须绑定具体 run/checkpoint/node，不从 UI 显示名推断执行目标。
- UI 使用 `FRONTEND_UI_SPEC.md`、`components/ui` wrapper、语义 token、Playwright/浏览器验证和窄宽度检查。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，覆盖 blocked 状态、engine contract pinned 条件、resume API 参数、history/trace action 可见性、失败诊断和 no fake mock 边界。至少一条真实 e2e 或手动验证必须在 blocked 或 pinned 条件下点击 resume 入口并看到正确反馈；不许 fake mock 到绿。

## 7. 硬依赖约束

WS-8 依赖 WS-3 run artifacts 和 engine checkpoint/resume API pinned。若 API 未 pinned，只能提交 blocked 条件与测试，不得实现假 resume。修改后端 Python 后必须重启 Studio App。

## 8. 验收标准(硬退出,IR4)

- [ ] RED 测试先失败，PM 契约门通过后实现到 GREEN 或明确 blocked。
- [ ] 未 pinned 时不会出现假可用 resume。
- [ ] pinned 后 resume 参数、错误和 UI action 有测试覆盖。
- [ ] Playwright 或浏览器真实 e2e/手动验证覆盖 blocked 或 resume 成功/失败路径和窄宽度。
- [ ] 后端修改后完成 Studio App 重启验证。

## 9. 不做(范围锁定,IR7)

不实现 engine checkpoint 内核，不改 run execution 主链，不做 golden/publish、Settings、Copilot。范围外问题登记 deferred。

## 10. baseline 回写指令(IR6)

实现或 blocked 条件落地后，按真实状态回写 debug-resume、local-history、timeline 的 `baseline.md`，不能把未 pinned 目标写成 live。

## 11. 评审检查点

PM 契约门审 RED 是否覆盖 blocked 条件、resume 参数和 no-fake。Codex 审查退出以 §8 为准。PM 终审检查 baseline 是否诚实表达 pinned 或 blocked。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/studio-mvp1/task-ws8-debug-resume.md` 并输出 Gemini prompt。交接必须包含 owns_files、禁止触碰、验证命令、用户明确确认、baseline 回写和 PM 终审。
