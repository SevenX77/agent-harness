---
ws_id: WS-3-compile-predict-run-trace
doc: task
status: pending
depends_on_requirements: requirements-ws3-compile-predict-run-trace.md
depends_on_contract_gate: contract-gate-ws3-compile-predict-run-trace.md
date: 2026-06-08
green_authorization: pending
---

# WS-3 Compile/Predict/Run/Trace 接线 — 实现（GREEN）任务交接

本文件是契约门通过后给执行者的 GREEN 实现交接单。
唯一目标：在不碰范围外、不写 e2e、不引入 fake mock 的前提下，把已批准的 **WS-3 RED 测试转 GREEN**。
所有判断只以 Studio MVP1 设计文档与 FROZEN 契约为准。

## 1. 文件归属 (owns_files)
本 WS 隔离并拥有以下文件（只允许修改这些文件）：
- `apps/studio/frontend/src/components/studio/Workspace.tsx`
- `apps/studio/frontend/src/components/studio/center-action-bar.tsx`
- `apps/studio/frontend/src/components/studio/SplitEditor.tsx` (单文件锁：只为 statusByNodeId 进行 props 透传，不触碰/修改任何编辑器具体交互行为)
- `apps/studio/frontend/src/components/TracePanel.tsx`
- `apps/studio/frontend/src/components/trace/`
- `apps/studio/frontend/src/hooks/useRunStream.ts`
- `apps/studio/frontend/src/components/history/RunHistoryRow.tsx`
- `apps/studio/backend/app/routers/runs.py`
- `apps/studio/backend/app/services/run_manager.py`
- `apps/studio/backend/app/services/predictor.py`

**禁止触碰**：Canvas 拖拽与属性编辑、Settings 页面、Copilot 侧栏、Golden/Publish（WS-6/WS-8 范围）。

## 2. RED → 生产文件映射与实现指南 (GREEN 落点)

| RED 用例 | 目标行为 (mvp1) | 生产落点 |
|---|---|---|
| Workspace Predict Click | 点击 Predict 调用 `postPredictRun`，传入当前 skillId 以及选中 input_data，成功后 stage 置为 `predict-pass` | `apps/studio/frontend/src/components/studio/Workspace.tsx` |
| Workspace Predict Fail | Predict 失败返回结构化错误时，拦截并用 toast.error 展示具体的校验失败信息，不静默 console | 同上 |
| Workspace Run Gating | 门控：Run 动作仅在 `predict-pass` 阶段允许点击/触发 | 同上 |
| Workspace Run Trigger | 点击 Run 调用 `startRun`，保存返回的 `run_id`，打开 trace/timeline 面板；将 websocket 实时事件流通过事件类型投影（projection）到 Canvas 各节点的 `status` 属性（`phase_start` -> `running`, `phase_end` -> `success`, 错误事件 -> `error`） | 同上 |
| Backend Predict 400 | Predict 接口捕获编译/运行校验失败异常（例如 `ValueError`），返回 HTTP 400 `compile_failed` DTO，包含 code 与 errors (包含 field, message) 列表 | `apps/studio/backend/app/routers/runs.py` 或 `app/services/predictor.py` |

---

## 3. 验证命令
实现过程中及完成后，执行以下测试命令：

### 3.1 前端 Vitest 测试
```bash
cd apps/studio/frontend && npx vitest run \
  src/components/studio/center-action-bar.red.test.tsx \
  src/hooks/useRunStream.red.test.ts \
  src/components/TracePanel.red.test.tsx \
  src/components/history/RunHistoryRow.red.test.tsx \
  src/components/studio/Workspace.ws3.red.test.tsx
```
- 基线状态：**3 failed | 14 passed (17)** (Workspace 测试中的 3 项 RED 失败)
- 目标状态：**17 passed**

### 3.2 后端 Pytest 测试
```bash
uv run pytest apps/studio/backend/tests/test_studio_mvp1_requirements_ws3_red.py
```
- 基线状态：**1 failed | 1 passed (2)** (Predict 400 契约 RED 失败)
- 目标状态：**2 passed**

---

## 4. Deferred Backend/Engine Drift (保持挂起，不在此 WS 中修)
- engine 拒绝 subgraph 相对 `path`；
- serializer 拒绝保留字 `input` 连线；
- `graph_topology` 发 `mode: "agent"` 与 DTO 冲突；
- LOGIC action 声明签名与当前引擎执行不匹配。

---

## 5. baseline 回写要求
GREEN 落地后，按事实回写对应 baseline 状态：
- `docs/studio/mvp1/02_capabilities/predict/baseline.md`
- `docs/studio/mvp1/02_capabilities/run-execution/baseline.md`
- `docs/studio/mvp1/02_capabilities/trace-observability/baseline.md`
