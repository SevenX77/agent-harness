---
module: 02_capabilities/golden-eval
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；后端 golden 以整次 run final_state 复制为 baseline；per-agent-node golden 目标未落 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/backend/app/services/golden_diff.py:set_golden_baseline_for_run · apps/studio/backend/app/services/golden_diff.py:compare_run_to_golden · apps/studio/frontend/src/hooks/useGoldenDiff.ts:compare · apps/studio/backend/app/services/diagnostic_export.py:export_predict_diagnostics
units: [golden-per-agent-node]
---

# golden-eval — Baseline（当下代码实现逻辑）

> **Scope**: 按 agent node 管理 golden、run 后 diff、predict/run 与 golden 的边界。
> **现状一句话**: 后端 golden 以整次 run final_state 复制为 baseline；per-agent-node golden 目标未落 ⚠️。

## UI/UX
按 agent node 管理 golden、run 后 diff、predict/run 与 golden 的边界。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Frontend save helper | `saveGoldenBaseline` posts a run id to `/golden`; this models golden as a run-derived baseline. | `apps/studio/frontend/src/api/client.ts:saveGoldenBaseline（L141）` |
| Frontend hook mismatch | `useGoldenDiff` calls GET `/compare`, which does not match the backend route shape. | `apps/studio/frontend/src/hooks/useGoldenDiff.ts:compare（L19）`, `apps/studio/frontend/src/hooks/useGoldenDiff.ts:response（L27）` |
| Trace buttons | TracePanel has Compare and Golden buttons, but the panel is not mounted. | `apps/studio/frontend/src/components/TracePanel.tsx:filter（L50）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Golden routes | Backend lists and sets golden baselines under `/api/skills/{skill_id}/golden`. | `apps/studio/backend/app/routers/golden.py:golden（L15）`, `apps/studio/backend/app/routers/golden.py:list_golden_baselines（L24）` |
| Current persistence | `set_golden_baseline_for_run` copies a run's final_state into a golden baseline folder. | `apps/studio/backend/app/services/golden_diff.py:set_golden_baseline_for_run（L34）` |
| Current diff | `compare_run_to_golden` compares a run final_state to the latest or selected golden final_state. | `apps/studio/backend/app/services/golden_diff.py:compare_run_to_golden（L68）`, `apps/studio/backend/app/services/golden_diff.py:_diff_value（L130）` |
| Compare API | Backend exposes POST `/compare` and GET `/diff`. | `apps/studio/backend/app/routers/compare.py:compare（L14）`, `apps/studio/backend/app/routers/compare.py:compare_run（L23）` |
| Frontend hook mismatch | `useGoldenDiff` calls GET `/compare`, which does not match the backend route shape. | `apps/studio/frontend/src/hooks/useGoldenDiff.ts:compare（L19）`, `apps/studio/frontend/src/hooks/useGoldenDiff.ts:response（L27）` |
| Predict guard | Diagnostic export blocks predict trace promotion to golden. | `apps/studio/backend/app/services/diagnostic_export.py:assert_trace_can_be_promoted_to_golden（L25）` |

## 当前边界（golden-eval 现在不是什么）
- golden 文件落点与 engine eval 归 engine SSOT，只引用不复制。
- Copilot 只提供分析 bar / chat 载体，数据流仍归 golden-eval。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 粒度 | `set_golden_baseline_for_run` 复制整次 final_state ⚠️ | 按 agent node 管 golden case / output |
| 入口 | 旧文档曾留 sonner/Properties 入口 ⚠️ | 入口为 I/O output + Assets + editor diff + Copilot analysis bar |
| predict guard | predict trace promotion 被 409 挡 | predict 不可入 golden；run 输出可做默认种子 |
> **验"是否按目标改了"**：1. 粒度；2. 入口；3. predict guard。

## 读代码主路径提示
`apps/studio/backend/app/services/golden_diff.py:set_golden_baseline_for_run` → `apps/studio/backend/app/services/golden_diff.py:compare_run_to_golden` → `apps/studio/frontend/src/hooks/useGoldenDiff.ts:compare` → `apps/studio/backend/app/services/diagnostic_export.py:export_predict_diagnostics`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-golden-eval)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `predict` · `run-execution` · `input` · `assets` · `editor` · `copilot-assist` · `engine`
