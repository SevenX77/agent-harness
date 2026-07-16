---
module: 02_capabilities/golden-eval
doc: baseline
status: FROZEN（2026-07 对账:后端 golden 已按 per-agent-node cases 落地(set_golden_baseline_for_run(node_id)+cases/{id}.json,golden_diff.py:58-79/186-208),旧"整次 run final_state 复制"已废;useGoldenDiff 路由已与 compare.py 对齐,TracePanel 已挂;创建入口部分 live(editor diff + analysis bar),I/O output 手动模板/Assets 入口尚未接 UI ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/backend/app/services/golden_diff.py:set_golden_baseline_for_run · apps/studio/backend/app/services/golden_diff.py:compare_run_to_golden · apps/studio/frontend/src/hooks/useGoldenDiff.ts:compare · apps/studio/backend/app/services/diagnostic_export.py:export_predict_diagnostics
units: [golden-per-agent-node]
---

# golden-eval — Baseline（当下代码实现逻辑）

> **Scope**: 按 agent node 管理 golden、run 后 diff、predict/run 与 golden 的边界。
> **现状一句话**: 后端 golden 已按 per-agent-node cases 落地(旧整次 final_state 复制已废);useGoldenDiff 路由已对齐 compare.py、TracePanel 已挂;创建入口部分 live(editor diff + Copilot analysis bar),I/O output 手动模板/Assets 文件树入口尚未接 UI ⚠️。

## UI/UX
按 agent node 管理 golden、run 后 diff、predict/run 与 golden 的边界。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Frontend save helper | `saveGoldenBaseline` posts a run id to `/golden`; this models golden as a run-derived baseline. | `apps/studio/frontend/src/api/client.ts:saveGoldenBaseline（L141）` |
| Frontend hook 对齐 | `useGoldenDiff.compare` 调 GET `/skills/{skill}/runs/{run}/compare`(带 `against`),与 `compare.py` GET `/compare` 对齐(旧 route-shape mismatch 已消)。 | `apps/studio/frontend/src/hooks/useGoldenDiff.ts:compare（L31）`, `apps/studio/backend/app/routers/compare.py:compare_run_get（L28）` |
| Trace buttons | TracePanel 有 Compare/Golden 按钮且已挂主路径(active run→TracePanel);run-level + per-node promote 均接 `saveGoldenBaseline`。 | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:TracePanel（L237）`, `apps/studio/frontend/src/components/TracePanel.tsx:onPromoteToGolden（L241）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Golden routes | Backend lists and sets golden baselines under `/api/skills/{skill_id}/golden`. | `apps/studio/backend/app/routers/golden.py:golden（L15）`, `apps/studio/backend/app/routers/golden.py:list_golden_baselines（L24）` |
| Current persistence | `set_golden_baseline_for_run` copies a run's final_state into a golden baseline folder. | `apps/studio/backend/app/services/golden_diff.py:set_golden_baseline_for_run（L34）` |
| Current diff | `compare_run_to_golden` compares a run final_state to the latest or selected golden final_state. | `apps/studio/backend/app/services/golden_diff.py:compare_run_to_golden（L68）`, `apps/studio/backend/app/services/golden_diff.py:_diff_value（L130）` |
| Compare API | Backend exposes POST `/compare` and GET `/diff`. | `apps/studio/backend/app/routers/compare.py:compare（L14）`, `apps/studio/backend/app/routers/compare.py:compare_run（L23）` |
| Frontend hook 对齐 | `useGoldenDiff.compare` 调 GET `/skills/{skill}/runs/{run}/compare`(带 `against`),与 `compare.py` GET `/compare` 对齐(旧 route-shape mismatch 已消)。 | `apps/studio/frontend/src/hooks/useGoldenDiff.ts:compare（L31）`, `apps/studio/backend/app/routers/compare.py:compare_run_get（L28）` |
| Predict guard | Diagnostic export blocks predict trace promotion to golden. | `apps/studio/backend/app/services/diagnostic_export.py:assert_trace_can_be_promoted_to_golden（L25）` |

## 当前边界（golden-eval 现在不是什么）
- golden 文件落点与 engine eval 归 engine SSOT，只引用不复制。
- Copilot 只提供分析 bar / chat 载体，数据流仍归 golden-eval。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 粒度 | `set_golden_baseline_for_run(node_id)` 写 cases/{id}.json,按 agent node 管(golden_diff.py:58-79/186-208)✅ | 按 agent node 管 golden case / output |
| 入口 | sonner 批量入口已删;editor diff(DiffView Promote)+ Copilot analysis bar(auto-write)+ TracePanel run/per-node promote 已 live;手动模板链(fetchGoldenTemplate/saveManualGolden + `GET /golden/template` + `POST /golden/manual/plan`)与 Properties per-node promote(NodeGoldenSection)已按 PM 2026-07-15 裁决删除,removal lock 测试守住 ✅ | 入口为 editor diff + Copilot analysis bar + TracePanel promote;golden 手填/编辑入口归 I/O 数据流方向(已搁置,`GET /golden/{id}/content` read path 留作脚手架) |
| predict guard | predict trace promotion 被 409 挡 | predict 不可入 golden；run 输出可做默认种子 |
> **验"是否按目标改了"**：1. 粒度；2. 入口；3. predict guard。

## 读代码主路径提示
`apps/studio/backend/app/services/golden_diff.py:set_golden_baseline_for_run` → `apps/studio/backend/app/services/golden_diff.py:compare_run_to_golden` → `apps/studio/frontend/src/hooks/useGoldenDiff.ts:compare` → `apps/studio/backend/app/services/diagnostic_export.py:export_predict_diagnostics`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-golden-eval)（迁移期安全网，代码实现验证后删）。

## WS-6 Studio-only Closeout Update

- **Manual Per-Node Golden Drafts**: 已删除(PM 2026-07-15)。该链(空模板 + manual plan 写盘)从未有 UI caller,整链移除;golden 手填/编辑归 I/O 数据流设计方向(已搁置)。Predict-source golden saves 仍被 409 `PREDICT_TRACE_CANNOT_BE_GOLDEN` 严格拒绝。
- **Deferred Items**: Engine exact per-node golden layout and actual-vs-golden run artifact diff remain deferred.

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `predict` · `run-execution` · `input` · `assets` · `editor` · `copilot-assist` · `engine`
