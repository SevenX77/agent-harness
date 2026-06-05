---
module: 03_regions/timeline
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；TimelinePanel 只列历史 run；TracePanel/PromptInspector/RunDetailDrawer/useRunStream 都存在但未挂主流程 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel · apps/studio/frontend/src/components/TracePanel.tsx:TracePanel · apps/studio/frontend/src/components/PromptInspector.tsx:PromptInspector · apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer · apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream
units: [compile-lint-structured-error, trace-dot-blackboard, run-execution-node-status]
---

# timeline — Baseline（当下代码实现逻辑）

> **Scope**: Timeline region：run/predict history、live trace auto-open、full trace、prompt inspector、compare/golden actions 与 model compare tabs。
> **现状一句话**: TimelinePanel 只列历史 run；TracePanel/PromptInspector/RunDetailDrawer/useRunStream 都存在但未挂主流程 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Panel route | Panels routes `activePanel === "timeline"` to `TimelinePanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L37）` |
| Run history | TimelinePanel reads current skill id and `useRunHistory`. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L32）` |
| Header/refresh | Panel shows run count and refresh button. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L39）`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L44）` |
| States | Panel has loading, error, and empty states. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L56）` |
| Run rows | Panel maps run rows with status, id, relative time, duration, and tokens. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L71）` |
| TracePanel orphan | TracePanel can render event streams and actions but is not mounted. | `apps/studio/frontend/src/components/TracePanel.tsx:TracePanel（L22）`, `apps/studio/frontend/src/components/TracePanel.tsx:filter（L50）` |
| Prompt inspector orphan | PromptInspector exists for template/variables/rendered tabs. | `apps/studio/frontend/src/components/PromptInspector.tsx:PromptInspector（L20）` |
| Run detail orphan | RunDetailDrawer exists but is not opened by Timeline rows. | `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer（L27）` |
| Stream hook orphan | `useRunStream` exists but no mounted timeline flow consumes it. | `apps/studio/frontend/src/hooks/useRunStream.ts:connect（L49）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Panel route | Panels routes `activePanel === "timeline"` to `TimelinePanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L37）` |
| Run history | TimelinePanel reads current skill id and `useRunHistory`. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L32）` |
| Header/refresh | Panel shows run count and refresh button. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L39）`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L44）` |
| States | Panel has loading, error, and empty states. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L56）` |
| Run rows | Panel maps run rows with status, id, relative time, duration, and tokens. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L71）` |
| TracePanel orphan | TracePanel can render event streams and actions but is not mounted. | `apps/studio/frontend/src/components/TracePanel.tsx:TracePanel（L22）`, `apps/studio/frontend/src/components/TracePanel.tsx:filter（L50）` |
| Prompt inspector orphan | PromptInspector exists for template/variables/rendered tabs. | `apps/studio/frontend/src/components/PromptInspector.tsx:PromptInspector（L20）` |
| Run detail orphan | RunDetailDrawer exists but is not opened by Timeline rows. | `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer（L27）` |
| Stream hook orphan | `useRunStream` exists but no mounted timeline flow consumes it. | `apps/studio/frontend/src/hooks/useRunStream.ts:connect（L49）` |

## 后端功能
N/A。

## 当前边界（timeline 现在不是什么）
- 不拥有 trace 语义；owner 是 `trace-observability`。
- 不拥有 golden creation 数据流；只提供历史/动作入口。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| live trace | TracePanel/useRunStream 未挂主流程 ⚠️ | run/predict 时 Timeline 自动打开 live trace |
| run detail | RunDetailDrawer 不由 row 打开 ⚠️ | row 可开 detail/replay/compare/export |
| golden actions | 旧 sonner/batch copilot 入口残留 ⚠️ | golden analysis 入口为 Copilot analysis bar，Timeline 只提供 compare/detail |
> **验"是否按目标改了"**：1. live trace；2. run detail；3. golden actions。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel` → `apps/studio/frontend/src/components/TracePanel.tsx:TracePanel` → `apps/studio/frontend/src/components/PromptInspector.tsx:PromptInspector` → `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer` → `apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-timeline)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `trace-observability` · `run-execution` · `compile-lint` · `golden-eval` · `copilot-assist`
