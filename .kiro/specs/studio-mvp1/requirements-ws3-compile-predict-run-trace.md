---
ws_id: WS-3-compile-predict-run-trace
modules: [02_capabilities/compile-lint, 02_capabilities/predict, 02_capabilities/run-execution, 02_capabilities/trace-observability, 03_regions/center-action-bar, 03_regions/timeline]
depends_on: [WS-0, WS-1, WS-2]
blocks: [WS-6, WS-8]
owns_files:
  - apps/studio/frontend/src/components/studio/Workspace.tsx
  - apps/studio/frontend/src/components/studio/center-action-bar.tsx
  - apps/studio/frontend/src/components/TracePanel.tsx
  - apps/studio/frontend/src/components/trace/
  - apps/studio/frontend/src/hooks/useRunStream.ts
  - apps/studio/frontend/src/components/history/RunHistoryRow.tsx
  - apps/studio/backend/app/routers/runs.py
  - apps/studio/backend/app/services/run_manager.py
  - apps/studio/backend/app/services/predictor.py
spec_ssot:
  - docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/predict/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/center-action-bar/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md
  - docs/studio/mvp1/01_workflows/03_compile.md
  - docs/studio/mvp1/01_workflows/04_run-and-verify.md
  - docs/studio/mvp1/DESIGN_UNITS_INDEX.md
status: drafted
---

# WS-3 Compile/Predict/Run/Trace 接线 — 需求书

本需求书是 WS-3 的契约输入。实现前必须先有 RED 测试、PM 契约门和用户在聊天窗口明确确认。

## 1. 目标(intent + why)

把 Compile、Predict、Run 和 Trace 从孤立按钮或桩接成一条可观察的运行链：stage gate 明确，运行事件能驱动节点状态、Timeline 和 Trace 黑板反馈。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标真理：frontmatter `spec_ssot` 所列 `mvp1-alignment.md` 与 `01_workflows/03_compile.md`、`01_workflows/04_run-and-verify.md`。
- 现状起点：`docs/studio/mvp1/02_capabilities/compile-lint/baseline.md`、`predict/baseline.md`、`run-execution/baseline.md`、`trace-observability/baseline.md`、`docs/studio/mvp1/03_regions/center-action-bar/baseline.md`、`timeline/baseline.md`。
- 全局索引：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 中 `compile-stage-gate`、`predict-execution`、`run-execution-node-status`、`trace-dot-blackboard`。
- 外部契约状态：engine run/observability/API contract 当前按 floating-draft 消费，WS-3 只接 Studio 侧 HTTP、stream 和 UI 投影，不复制 engine 运行时。
- UI 规则：读 `docs/development/FRONTEND_UI_SPEC.md` §2，先查 `components/ui`，用 Playwright/浏览器验证窄宽度和语义 token。
- 必读源码：frontmatter `owns_files` 中 Workspace、center-action-bar、TracePanel、trace、run stream、history row、runs router、run manager、predictor。

## 3. 文件归属(并发锁,IR1)

本 WS owns frontmatter `owns_files`。`apps/studio/frontend/src/components/studio/Workspace.tsx` 与 WS-1、WS-8 共享，必须按 `docs/studio/mvp1/_impl/IMPL_PLAN.md` 串行：WS-3 只接 compile/predict/run/trace action，WS-8 resume action 排队。`apps/studio/backend/app/routers/runs.py` 与 WS-8 共享，WS-3 只接 compile/predict/run/trace，resume 段排队到 WS-8。

禁止触碰 Canvas authoring 文件、Settings/LLM、Copilot、golden/publish、engine/gateway packages。范围外问题登记 deferred。

## 4. 现状锚点(baseline)

baseline 显示 Compile、Predict、Run、Trace 的若干 UI 和后端服务已存在，但部分入口仍是桩、Trace/Timeline 未形成完整工作流，节点状态与运行事件没有端到端闭环。

## 5. 目标行为(可测的契约)

- Compile stage gate 是 Predict/Run 的唯一前置判定来源，Predict/Run 不重复发明 gate。
- Predict 调用真实后端 dry-run/predict 路径，错误以结构化方式显示，不静默 console。
- Run 触发后，run_manager 事件能投影到 Workspace、Timeline、TracePanel 和相关状态。
- Trace 黑板和运行事件可搜索、过滤、检查，不用固定 mock 数据冒充。
- UI 使用 `FRONTEND_UI_SPEC.md`、`components/ui` wrapper、Playwright/浏览器点击验证、窄宽度检查和语义 token。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，覆盖 compile gate、Predict 成功/失败、Run 事件流、TracePanel 挂载、Timeline 状态、run history row、后端 runs/predictor 契约。至少一条真实 e2e 或手动验证必须从 Compile 走到 Predict 或 Run，再看到 Trace/Timeline 反馈；不许 fake mock 到绿。

## 7. 硬依赖约束

WS-3 依赖 WS-2 authoring schema 和 WS-1 native writer。engine event schema 未 pinned 的字段必须写成 floating-draft 或 blocked 条件，不在 Studio 中复制 engine 内核。

## 8. 验收标准(硬退出,IR4)

- [ ] RED 测试先失败，PM 契约门通过后实现到 GREEN。
- [ ] Compile/Predict/Run/Trace 的单元、集成和回归测试通过。
- [ ] 后端 Python 修改后已重启 Studio App 或重新拉起 `cargo tauri dev` 验证。
- [ ] Playwright 或浏览器真实 e2e 覆盖成功、失败、空态和窄宽度。
- [ ] 无回归：authoring 工作台、Settings 和 Copilot 不被 WS-3 改动破坏。

## 9. 不做(范围锁定,IR7)

不做 WS-6 golden/eval/publish，不做 WS-8 debug resume，不重写 engine runtime，不改 Settings/LLM/Copilot。范围外问题登记 deferred。

## 10. baseline 回写指令(IR6)

实现后按真实代码回写 compile-lint、predict、run-execution、trace-observability、center-action-bar、timeline 的 `baseline.md`。

## 11. 评审检查点

PM 契约门审 RED 是否覆盖 stage gate、真实 run/predict 和 trace 可观察性。Codex 审查退出以 §8 为准。PM 终审检查 baseline 诚实、测试非假绿。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/studio-mvp1/task-ws3-compile-predict-run-trace.md` 并输出 Gemini prompt。交接必须包含 owns_files、禁止触碰、验证命令、用户明确确认、baseline 回写和 PM 终审。
