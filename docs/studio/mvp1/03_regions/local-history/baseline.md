---
module: 03_regions/local-history
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；HistoryPanel 只显示 git snapshot；RunDetailDrawer/BatchSummary 存在但未挂，这与最新归属一致但旧 alignment 曾留未决口径 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/panels/HistoryPanel.tsx:HistoryPanel · apps/studio/frontend/src/components/history/HistoryPanel.tsx:HistoryPanel · apps/studio/backend/app/routers/skills.py:get_skill_history · apps/studio/backend/app/routers/skills.py:get_skill_history
units: [local-history-snapshot]
---

# local-history — Baseline（当下代码实现逻辑）

> **Scope**: Local History region 的 snapshot 列表、显示与 revert；run detail/batch summary 不归这里。
> **现状一句话**: HistoryPanel 只显示 git snapshot；RunDetailDrawer/BatchSummary 存在但未挂，这与最新归属一致但旧 alignment 曾留未决口径 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Panel route | Panels routes `activePanel === "local-history"` to `HistoryPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L40）` |
| Re-export | Studio panel re-exports shared history component. | `apps/studio/frontend/src/components/studio/panels/HistoryPanel.tsx:HistoryPanel（L1）` |
| Local history view | View renders snapshot count, refresh, list, selected snapshot, and revert button. | `apps/studio/frontend/src/components/history/HistoryPanel.tsx:LocalHistoryPanelView（L51）`, `apps/studio/frontend/src/components/history/HistoryPanel.tsx:selected（L130）` |
| Local history hook | Component uses `useLocalHistory` and calls revert with toast feedback. | `apps/studio/frontend/src/components/history/HistoryPanel.tsx:HistoryPanel（L156）`, `apps/studio/frontend/src/components/history/HistoryPanel.tsx:handleRevert（L161）` |
| Backend history | Backend exposes history and revert endpoints. | `apps/studio/backend/app/routers/skills.py:update_skill_file_endpoint（L397）`, `apps/studio/backend/app/services/skills.py:update_skill_files（L397）` |
| Run detail orphan | RunDetailDrawer exists separately with Replay/Compare/Export but is not mounted here. | `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer（L27）`, `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer（L54）` |
| Batch summary orphan | BatchSummary exists separately and is not mounted here. | `apps/studio/frontend/src/components/history/BatchSummary.tsx:BatchSummary（L32）`, `apps/studio/frontend/src/components/history/BatchSummary.tsx:percent（L64）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Panel route | Panels routes `activePanel === "local-history"` to `HistoryPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L40）` |
| Re-export | Studio panel re-exports shared history component. | `apps/studio/frontend/src/components/studio/panels/HistoryPanel.tsx:HistoryPanel（L1）` |
| Local history view | View renders snapshot count, refresh, list, selected snapshot, and revert button. | `apps/studio/frontend/src/components/history/HistoryPanel.tsx:LocalHistoryPanelView（L51）`, `apps/studio/frontend/src/components/history/HistoryPanel.tsx:selected（L130）` |
| Local history hook | Component uses `useLocalHistory` and calls revert with toast feedback. | `apps/studio/frontend/src/components/history/HistoryPanel.tsx:HistoryPanel（L156）`, `apps/studio/frontend/src/components/history/HistoryPanel.tsx:handleRevert（L161）` |
| Run detail orphan | RunDetailDrawer exists separately with Replay/Compare/Export but is not mounted here. | `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer（L27）`, `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer（L54）` |
| Batch summary orphan | BatchSummary exists separately and is not mounted here. | `apps/studio/frontend/src/components/history/BatchSummary.tsx:BatchSummary（L32）`, `apps/studio/frontend/src/components/history/BatchSummary.tsx:percent（L64）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Backend history | Backend exposes history and revert endpoints. | `apps/studio/backend/app/routers/skills.py:update_skill_file_endpoint（L397）`, `apps/studio/backend/app/services/skills.py:update_skill_files（L397）` |

## 当前边界（local-history 现在不是什么）
- 不拥有 run detail / batch summary。
- 不拥有快照写入机制，只显示/回滚。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| scope | 旧文留 RunDetail/BatchSummary PM confirmation ⚠️ | Local History 只做 git snapshot；RunDetail/BatchSummary 归 Timeline/I/O |
| snapshot | HistoryPanel 显示 snapshot/revert live | 快照列表/刷新/revert 可用且错误可见 |
| 写机制 | 快照写机制不在本 region | snapshot 写由 publish/native-fs 触发，本 region 只显示 |
> **验"是否按目标改了"**：1. scope；2. snapshot；3. 写机制。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/panels/HistoryPanel.tsx:HistoryPanel` → `apps/studio/frontend/src/components/history/HistoryPanel.tsx:HistoryPanel` → `apps/studio/backend/app/routers/skills.py:get_skill_history` → `apps/studio/backend/app/routers/skills.py:get_skill_history`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-local-history)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `publish` · `native-fs` · `timeline`
