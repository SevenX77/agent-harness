---
module: 02_capabilities/run-execution
doc: baseline
status: FROZEN（2026-07 对账:后端 run manager live;前端 Run handler 已 live(handleRun→startRun,Workspace.tsx:2153-2181/2165)、predict-pass 已置位(:2137)、节点灯接真跑态(deriveNodeStatuses,:665-666→2608);仍缺前端 batch UI(useBatchRun.ts 已删,后端 batch-run live)⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/Workspace.tsx:onRun · apps/studio/frontend/src/api/client.ts:startRun · apps/studio/backend/app/routers/runs.py:start_run · apps/studio/backend/app/services/run_manager.py:start_run · apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream
units: [run-execution-node-status, golden-per-agent-node]
---

# run-execution — Baseline（当下代码实现逻辑）

> **Scope**: 单次 run、batch/loop 触发、live run state、节点灯、历史详情与成功 run autocommit。
> **现状一句话**: 后端 run manager live;前端 Run handler 已 live(handleRun→startRun)、predict-pass 已置位、节点灯接真跑态;仍缺前端 batch UI(useBatchRun.ts 已删,后端 batch-run 保留)⚠️。

## UI/UX
单次 run、batch/loop 触发、live run state、节点灯、历史详情与成功 run autocommit。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Run button | Center action bar 在 predict-pass 后显示 Run;`handlePredict` 置 predict-pass、`handleRun` 门控 predict-pass 后调 `startRun`(非桩)。 | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:deriveButtons（L52）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:handleRun（L2153）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:handlePredict（L2105）` |
| API helper | `startRun` posts input data to `/runs`. | `apps/studio/frontend/src/api/client.ts:startRun（L154）` |
| History | Frontend has run history hooks; TimelinePanel lists runs. | `apps/studio/frontend/src/hooks/useRunHistory.ts:useRunHistory（L7）`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L32）` |
| Batch | 后端 batch-run + list/status live;前端无 batch UI —— `useBatchRun.ts` 已删,batch 入口/结果展示未接主路径 ⚠️。 | `apps/studio/backend/app/routers/runs.py:create_batch_run（L92）`, `apps/studio/backend/app/routers/runs.py:list_runs（L88）`, `apps/studio/backend/app/routers/runs.py:get_batch_status（L316）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Run route | Backend starts a run via `run_manager.start_run`. | `apps/studio/backend/app/routers/runs.py:runs（L27）` |
| Worker | Run manager spawns a process, calls `run_skill`, writes final state, metrics, and status. | `apps/studio/backend/app/services/run_manager.py:_run_worker_main（L81）`, `apps/studio/backend/app/services/run_manager.py:start_run（L182）` |
| Run artifacts | Run directory includes trace, artifacts, checkpoints, and metadata files. | `apps/studio/backend/app/services/run_manager.py:_ensure_run_files（L164）` |
| Run stream | Backend exposes run websocket and drains run event queue. | `apps/studio/backend/app/routers/websockets.py:_close_unauthorized（L27）`, `apps/studio/backend/app/services/run_manager.py:stream_run（L334）` |
| Batch | 后端 batch-run + list/status live;前端无 batch UI —— `useBatchRun.ts` 已删,batch 入口/结果展示未接主路径 ⚠️。 | `apps/studio/backend/app/routers/runs.py:create_batch_run（L92）`, `apps/studio/backend/app/routers/runs.py:list_runs（L88）`, `apps/studio/backend/app/routers/runs.py:get_batch_status（L316）` |
| Autocommit | Successful run auto-commits and records git status. | `apps/studio/backend/app/services/run_manager.py:_auto_commit_successful_run（L445）` |

## 当前边界（run-execution 现在不是什么）
- predict 机制归 `predict`；run 只消费 predict-pass。
- engine 循环原语/observability 只引用 engine SSOT。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| Run 入口 | `handleRun` 门控 predict-pass 后调 `startRun`(Workspace.tsx:2156/2165)✅ | Run 真调用 `startRun`，携带选中 input/settings |
| 节点态 | `statusByNodeId`=`deriveNodeStatuses(runStream.events,runId)` 投画布(:665-666→:2608)✅ | run events 经 state-engine 投到节点灯/边 |
| batch | 后端 batch-run live,前端无 batch UI(useBatchRun.ts 已删)⚠️ | 批量/循环入口与结果展示可用 |
| golden seed | run final output 可做 golden 默认种子 | predict fake trace 不可做 golden |
> **验"是否按目标改了"**：1. Run 入口；2. 节点态；3. batch；4. golden seed。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/Workspace.tsx:onRun` → `apps/studio/frontend/src/api/client.ts:startRun` → `apps/studio/backend/app/routers/runs.py:start_run` → `apps/studio/backend/app/services/run_manager.py:start_run` → `apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-run-execution)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `predict` · `canvas` · `timeline` · `state-engine` · `golden-eval` · `engine` iterate/observability
