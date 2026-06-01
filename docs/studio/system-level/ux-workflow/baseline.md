# ux-workflow (studio system-level) — Baseline (Round 31 API 协作链)

> **Status**: Updated by a1 (Codex), 2026-05-30
> **Scope**: Studio 系统级端到端操作流，重点是 Predict ↔ Golden ↔ Run ↔ Copilot 闭环。
> **配套**: Round 31 design §2.5；workspace 写入规范见 [engine workspace spec](../../../engine/workspace-spec/baseline.md)。

## 1. 简介与范围

本文件描述 Studio 用户如何从编辑 skill 走到可验证的执行结果。它是 UX 蓝图：只写用户点什么、系统给什么反馈、业务价值是什么；不展开 Gateway / SDK 内部的 resolver 协议、模型注入或 trace writer 实现。

Round 31 后，Studio 的关键体验不再是孤立的 Predict 或 Run 按钮，而是一条闭环协作链：

Predict 沙盘推演 → Copilot 像军师一样指出 prompt / few-shot / protocol 问题 → 用户把满意的推演固化成 Golden Baseline → 真 Run 实弹演练 → 对照 Golden 复盘，继续迭代到真实输出达标。

## 2. 现有主流程：Welcome → 画布 → 编辑器

当前主流程保留为系统入口，但不是本轮重点。

用户打开 Studio 后，如果没有选中 skill，`Workspace` 渲染 `WelcomePage`。用户可以创建或导入 skill，然后进入 loaded workspace：

- `apps/studio/frontend/src/components/studio/Workspace.tsx:402-405`
- `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:174-197`

用户打开 skill 后，中心区域在画布与编辑器之间切换：

- 无打开文件时显示 `GraphCanvas`：`apps/studio/frontend/src/components/studio/Workspace.tsx:405-413`
- 有打开文件时显示 `SplitEditor`：`apps/studio/frontend/src/components/studio/Workspace.tsx:392-401`

中心操作栏提供 `Compile`、`Predict`、`Run` 三个用户动作：

- `apps/studio/frontend/src/components/studio/center-action-bar.tsx:62-95`

当前实现中，Compile 已接后端；Predict / Run 按钮仍是占位 console 输出：

- Compile 调 `compileSkill()` 并写入 compile 状态：`apps/studio/frontend/src/components/studio/Workspace.tsx:292-322`
- Predict / Run 当前仅 `console.info(...)`：`apps/studio/frontend/src/components/studio/Workspace.tsx:420-424`

Round 31 的文档目标是定义它们应接入的产品闭环，而不是把当前占位实现误写成已完成体验。

## 3. 闭环协作链：Predict ↔ Golden ↔ Run ↔ Copilot

### 3.1 阶段一：Predict 预演推演

用户在编辑器或画布完成 skill 修改后，先点击 Compile。Compile 通过后，用户点击 Predict。

目标体验：

- Studio 调用后台 Predict 编排。
- 后台调用 SDK `predict_skill(..., workspace_dir=...)`。
- Predict 不是盲跑逻辑图：逻辑节点真实执行，LLM 节点由 Gateway 的 Copilot 接口作为大模型替身做真实语义推演。
- 结果以同形 `RunResult(source="predict")` 返回。
- 推演日志和结果只进入 `<workspace_dir>/runs/<run_id>/`。

字段级输出：

- `RunResult.source = "predict"`
- `RunResult.run_id`
- `RunResult.phases`
- `RunResult.path_diff`
- `<workspace_dir>/runs/<run_id>/trace.jsonl`
- `<workspace_dir>/runs/<run_id>/result.json`
- `<workspace_dir>/runs/<run_id>/final_state.json`
- `<workspace_dir>/runs/<run_id>/metrics.json`
- `<workspace_dir>/runs/<run_id>/artifacts/`

现状实证：

- 当前 Predict 后端入口存在：`apps/studio/backend/app/routers/runs.py:32-40`
- 当前 Predict 编排仍使用内部 `PredictTracingCallback` 和旧 `PredictResult`：`apps/studio/backend/app/services/predictor.py:65-90`
- 当前 `PhaseRecord` / `PathDiff` / `PredictResult` 仍在 private predict model 中：`packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:24-52`

### 3.2 阶段二：Copilot 辅助与 Prompt 迭代

用户读取 Predict 的 phase 结果、路径差异和最终状态后，在 Copilot 面板里继续提问或要求修改建议。

目标体验：

- Copilot 针对 prompt、phase 结构、few-shot、协议字段给出具体修改建议。
- 用户接受或手工改动后，再次 Compile + Predict。
- Studio 只把 Copilot 作为用户协作界面；即席 chat 和模型 provider 能力属于 Gateway，不属于 SDK。

现状实证：

- Copilot view 已包含 `Compile`、`Predict`、`Run` 等上下文枚举：`apps/studio/backend/app/models/copilot.py:9-16`
- Studio workspace 已挂载 Copilot panel：`apps/studio/frontend/src/components/studio/Workspace.tsx:440`

### 3.3 阶段三：Golden 转化

用户对一次 Predict 推演满意后，点击“设为基线”。

目标体验：

- Studio HTTP golden CRUD endpoint 把本次同形 `RunResult(source="predict")` 编排固化为 Golden Baseline。
- 这是 Studio 产品层编排，不新增 SDK verb。
- SDK 不提供 `set_golden_from_predict` 之类专用动作。

字段级输入：

- `skill_id`
- `run_id`
- `lock`

字段级输出：

- `GoldenBaseline.id`
- `GoldenBaseline.linked_input_id`
- `GoldenBaseline.content_path`
- `GoldenBaseline.locked`

现状实证：

- 前端 promote 当前 POST `/skills/{skillId}/golden`，body 带 `run_id` 和 `lock`：`apps/studio/frontend/src/hooks/useGoldenDiff.ts:39-49`
- 后端 golden endpoint 当前接 `SetGoldenReq`：`apps/studio/backend/app/routers/golden.py:24-30`
- 后端当前从 run 的 `final_state.json` 拷贝成 baseline：`apps/studio/backend/app/services/golden_diff.py:34-64`

### 3.4 阶段四：真 Run 执行与对照

用户点击 Run 后，Studio 触发真实执行。

目标体验：

- Studio 调用 SDK `run_skill(..., workspace_dir=...)`。
- 真实 LLM 由 Gateway 管理的模型环境提供。
- SDK 返回 `RunResult(source="run")`。
- 真实 run 与 predict 使用同一结果形状，统一写入 `<workspace_dir>/runs/<run_id>/`。

字段级输出：

- `RunResult.source = "run"`
- `RunResult.success`
- `RunResult.context`
- `RunResult.metrics`
- `RunResult.trace_path`
- `<workspace_dir>/runs/<run_id>/trace.jsonl`
- `<workspace_dir>/runs/<run_id>/result.json`
- `<workspace_dir>/runs/<run_id>/final_state.json`
- `<workspace_dir>/runs/<run_id>/metrics.json`
- `<workspace_dir>/runs/<run_id>/artifacts/`

现状实证：

- 当前 `RunResult` 已有 `success/run_id/skill_id/context/metrics/trace_path/error/started_at/finished_at/wall_time_sec`：`packages/graph-agent/src/graph_agent/core/result.py:46-60`
- 当前 Studio run worker 已按 run_dir 创建 artifacts 并调用 `run_skill`：`apps/studio/backend/app/services/run_manager.py:226-241`

### 3.5 阶段五：深度优化循环

真 Run 完成后，用户查看 Golden 对比结果，并让 Copilot 给出下一轮优化建议。

目标体验：

- Studio HTTP 层调用 SDK `evaluate_golden_baseline(compiled_skill, dataset, model_resolver, workspace_dir)` 取 diff。
- Copilot 根据 diff 给出具体 prompt、few-shot、protocol 修改建议。
- 用户按建议编辑，再走 Compile → Predict → Golden → Run → Compare 循环。

字段级对照：

- `golden_run_id`
- `differences`
- `total_score`
- field-level current value / golden value / score

现状实证：

- 当前前端 compare GET `/skills/{skillId}/runs/{runId}/compare`：`apps/studio/frontend/src/hooks/useGoldenDiff.ts:25-31`
- 当前后端 compare 从 run final state 对比 golden final state：`apps/studio/backend/app/services/golden_diff.py:68-110`

## 4. 协同边界

| 层 | Owner | 负责 |
|---|---|---|
| Studio UI / HTTP | Studio | 用户按钮、golden CRUD、闭环编排、Copilot 面板展示 |
| SDK | graph-agent | `predict_skill`、`run_skill`、`evaluate_golden_baseline`、同形 `RunResult`、runs 目录写入 |
| Gateway | graph-agent-gateway | Copilot predictor、chat facade、provider/model/role 环境 |

强制名词：

- SDK 动作只写 `run_skill` / `predict_skill` / `evaluate_golden_baseline`。
- 推演结果与日志只写 `<workspace_dir>/runs/<run_id>/`。
- Golden CRUD 是 Studio HTTP 产品功能，不是 SDK verb。
