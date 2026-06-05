---
module: 02_capabilities/predict
doc: baseline
status: drafted（现状对齐 pinned 代码 3c1e2f5；后端 predict 链路 live、前端主入口是桩 ⚠️）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/Workspace.tsx:onPredict · apps/studio/frontend/src/api/client.ts:postPredictRun · apps/studio/backend/app/routers/runs.py:predict_run · apps/studio/backend/app/services/predictor.py:dispatch_predict_job · packages/graph-agent/src/graph_agent/core/runner.py:predict_skill
unit: predict-execution
lock: drafted
---

# predict — Baseline（当下代码实现逻辑）

> **Scope**: compile 后、run 前的"试飞"——按节点 i/o 跑图、验 schema/逻辑、确定性跑 logic、agent mock 不烧 token。
> **现状一句话**: 后端 predict 链路 live（路由 / service / 引擎 / golden guard），但**前端主入口 `Workspace.tsx:onPredict` 是 `console.info` 桩 ⚠️**，predict-pass 无法置位、Run 永锁。Source workflow：`01_workflows/04_run-and-verify.md`。

## UI/UX
center-action-bar 的 Predict 按钮（compile-pass 后点亮），点击应触发试飞并出 diagnostic。**现状点击只打日志。**

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Predict 入口 | 点击 handler **只 `console.info("predict clicked")` ⚠️** | `Workspace.tsx:onPredict`（L537） |
| API helper（就绪） | `postPredictRun` 已存在、POST `/skills/{id}/runs/predict` | `client.ts:postPredictRun`（L134） |
| predict-pass | **前端无代码置位 ⚠️**，Run 仍门控 | `center-action-bar.tsx`（无 predict-pass @L52） |

## 后端功能
| 面 | 现状 | 证据 |
|---|---|---|
| predict 路由 | 调 predictor service（mock flag / input / hashes） | `runs.py:predict_run`（L33） |
| predictor service | `dispatch_predict_job` 跑 job + 落 `result.json` | `predictor.py:dispatch_predict_job`（L41） |
| 引擎 predict | `predict_skill` 写 predict artifacts/trace | `runner.py:predict_skill`（L163/353） |
| golden guard | diagnostic export 拒 predict trace 入 golden（409） | `diagnostic_export.py:export_predict_diagnostics`（L25） |

## API
- 前端：`postPredictRun(skillId, inputData) -> PredictRunResponse | RunDetail`（`client.ts:postPredictRun`）。
- 后端：`POST /skills/{id}/runs/predict` → `predict_run`（`runs.py:predict_run`）。

## Data Model / State
predict 产物落 `result.json`（`RunResult`，`source="predict"`）；不入 golden（409 guard 挡 predict 轨迹）。

## 当前边界（predict 现在不是什么）
- 不是 Run（不烧真 token；agent 走 mock）。
- 不拥有 golden 内容（只读 golden 状态选 mock）——golden 归 `golden-eval`。
- 不拥有 compile gate 规则（只置 predict-pass）——gate 归 `compile-lint`。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 前端主入口 | `onPredict` = `console.info` 桩 ⚠️ | onPredict 调 `postPredictRun` 跑真 predict |
| predict-pass | 前端无置位、Run 永锁 ⚠️ | predict 成功置 predict-pass、解锁 Run |
| 输入来源 | helper 只收 ad hoc `input_data` | 从 i/o 面板选已导入输入 |
> **验"是否按目标改了"**：① 点 Predict 真发请求出 diagnostic；② 成功 predict 后 Run 可点；③ predict 用 i/o 面板选中的 input。

## 读代码主路径提示
`Workspace.tsx:onPredict` →（应接）`client.ts:postPredictRun` → `runs.py:predict_run` → `predictor.py:dispatch_predict_job` → `runner.py:predict_skill`。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `compile-lint`（`compile-stage-gate` 门控）· `golden-eval`（`golden-per-agent-node` mock/guard）· `input` region（输入）· `engine`（`predict_skill`）
