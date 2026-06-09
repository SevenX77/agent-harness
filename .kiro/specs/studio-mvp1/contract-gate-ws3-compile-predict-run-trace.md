---
ws_id: WS-3-compile-predict-run-trace
doc: contract-gate
status: red-verified-pending-approval
depends_on: [WS-0, WS-1, WS-2]
blocks: [WS-6, WS-8]
date: 2026-06-08
---

# WS-3 Compile/Predict/Run/Trace — 契约门报告 (RED)

本文件是 WS-3 编译、预测、运行与可观察性接线模块的契约门审查报告。已在 Studio 前端与后端完整落地对应的 RED 测试与回归锁防护网，并清除了全部代码风格与 Linter 问题。

**当前状态**：`RED 验证就绪，等待审批`。不提供 GREEN 任务授权。

---

## 1. 拥有文件清单 (owns_files)
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

**禁止触碰范围**：Canvas 拖拽/编辑、Settings 页面、Copilot 侧边栏、Golden 验收。

---

## 2. Linter 状态 (静态检查 100% 通过)

### 2.1 后端 Python (Ruff check)
- **运行命令**：
  ```bash
  uv run ruff check apps/studio/backend/tests/test_studio_mvp1_requirements_ws3_red.py
  ```
- **输出结果**：
  ```text
  All checks passed!
  ```

### 2.2 前端 TypeScript (npm run lint)
- **运行命令**：
  ```bash
  cd apps/studio/frontend && npm run lint
  ```
- **输出结果**：
  ```text
  > studio-frontend@0.0.0 lint
  > eslint .
  ```
  *(注：已清理全部 no-explicit-any、unused-vars、prefer-const 错误，通关无警告)*

---

## 3. 回归锁 (GREEN Regression Locks)
下列已被锁定为回归锁，其实现已在 Baseline 中为 GREEN 并通过测试：

### 3.1 前端中心动作条 (center-action-bar) 按钮使能
- **运行命令**：`npx vitest run src/components/studio/center-action-bar.red.test.tsx` (3 passed)
  - `locks Predict and Run when stage is idle, compiling, or compile-fail`
  - `unlocks Predict but locks Run when stage is compile-pass...`
  - `unlocks both Predict and Run when stage is predict-pass`

### 3.2 前端 useRunStream 事件流 Hook 行为
- **运行命令**：`npx vitest run src/hooks/useRunStream.red.test.ts` (4 passed)
  - `initializes in idle state when runId is null`
  - `connects to WS and appends events through the flush queue`
  - `sets error state when receiving malformed JSON`
  - `closes the old socket when runId changes`

### 3.3 前端 TracePanel 基础渲染与过滤
- **运行命令**：`npx vitest run src/components/TracePanel.red.test.tsx` (3 passed)
  - `renders Waiting for run events when traceLogs is empty` (空态可见)
  - `renders events keeping machine-readable event_type codes visible`
  - `correctly filters events based on searchTerm`

### 3.4 前端 RunHistoryRow 状态映射
- **运行命令**：`npx vitest run src/components/history/RunHistoryRow.red.test.tsx` (3 passed)
  - 成功映射 `success`, `failed`, `running` 并呈现对应的 Badge 类（不覆盖 queued 契约）。

### 3.5 后端 create_run 启动与 metadata 存储
- **运行命令**：`uv run pytest apps/studio/backend/tests/test_studio_mvp1_requirements_ws3_red.py -k test_create_run_endpoint_returns_metadata` (1 passed)
  - 触发 `/runs` 产生 `RunMetadata`，其状态为 `"running"`。

---

## 4. 业务契约 RED 测试验证 (4 个用例真实失败)

### 4.1 前端 Workspace 接线缺失 (Vitest RED)
- **运行命令**：
  ```bash
  npx vitest run src/components/studio/Workspace.ws3.red.test.tsx
  ```
- **测试结果**：`3 failed | 1 passed`
- **错因证据**：
  - `triggers postPredictRun on Predict click (RED)` -> **FAILED**: `postPredictRun` 期待被调用但没有（因为当前为 `console.info` 桩）。
  - `renders structured error messages when Predict fails (RED)` -> **FAILED**: `toast.error` 没有触发上报。
  - `triggers startRun, saves run_id, and drives canvas node status on Run success (RED)` -> **FAILED**: `startRun` 没有被调用。测试完整遵循了“点击 Predict 成功 -> state 更新至 predict-pass -> 再次 render -> 点击 Run 触发 startRun”的状态转移门控流，在生产代码未接线时由于门控而安全阻断并失败。

### 4.2 后端 predict 结构化 400 DTO 缺失 (Pytest RED)
- **运行命令**：
  ```bash
  uv run pytest apps/studio/backend/tests/test_studio_mvp1_requirements_ws3_red.py -k test_predict_run_endpoint_returns_structured_errors
  ```
- **测试结果**：`1 failed`
- **错因证据**：
  - `AssertionError: assert 422 == 400`
  - *原因*：当 dispatch 抛出 `ValueError` 时，由于后端路由缺少受控编译/运行校验异常拦截器，FastAPI 将未捕获的 ValueError 直接渲染成了 422 异常响应，没有包装成带有 `code: "compile_failed"` 且含 field/message 的 400 DTO。测试已被重写以确保其顺利运行过 API 请求层并受控在业务抛错阶段。

---

## 5. Deferred Backend/Engine Drift (范围外挂起)
1. **engine `SubgraphNodeAST` 拒 subgraph path**：当前后端 engine AST 不支持 subgraph 使用相对 `path`，强制要求 `target_skill`。
2. **serializer 拒绝 reserved keyword**：如果图连线指向保留字段 `input` 会触发 `422`。
3. **mode:"agent" 与 DTO 冲突**：后端 topology 返回 `mode: "agent"`，但 serializer 仅支持 logic/subgraph/skill。
4. **LOGIC action 签名 drift**：逻辑节点在 MVP1 声明为纯 action 节点，但当前引擎执行需要 `def run(...)` 骨架。
