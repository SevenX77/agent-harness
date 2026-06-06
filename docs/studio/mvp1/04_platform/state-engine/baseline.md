---
module: 04_platform/state-engine
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；状态分散在 Workspace/sessionStorage/SWR/copilotStore/settings hooks；run stream 与 global events 存在但未形成单一 state-engine/WS bridge ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/RuntimeGate.tsx:RuntimeGate · apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace · apps/studio/frontend/src/hooks/useDebouncedLint.ts:useDebouncedLint · apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream · apps/studio/frontend/src/store/copilotStore.ts:copilotStore · apps/studio/backend/app/routers/websockets.py:run_events
units: [shell-runtime-gate, compile-stage-gate, run-execution-node-status, trace-dot-blackboard, settings-six-state-provider-health]
---

# state-engine — Baseline（当下代码实现逻辑）

> **Scope**: Studio 前端状态协调：workspace UI state、compile/predict/run stage、event->node-state 派生、websocket bridges 与 scoped sidecar failure。
> **现状一句话**: 状态分散在 Workspace/sessionStorage/SWR/copilotStore/settings hooks；run stream 与 global events 存在但未形成单一 state-engine/WS bridge ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Runtime gate | RuntimeGate initializes runtime config and can block with splash/error. | `apps/studio/frontend/src/components/RuntimeGate.tsx:RuntimeGate（L8）`, `apps/studio/frontend/src/components/RuntimeGate.tsx:cancelled（L31）` |
| Workspace state | Workspace owns selected panel, nav stack, copilot open, selected node/edge, compile stages, and open files. | `apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace（L39）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentSkillId（L55）` |
| Copilot context | Workspace sends selected node/edge/lint status into copilot context. | `apps/studio/frontend/src/components/studio/Workspace.tsx:isLoading（L69）`, `apps/studio/frontend/src/hooks/useCopilotContext.ts:timeout（L53）` |
| Lint state | Lint status is published through sessionStorage and a custom event. | `apps/studio/frontend/src/hooks/useDebouncedLint.ts:lintStatusEvent（L6）`, `apps/studio/frontend/src/hooks/useDebouncedLint.ts:publishLintStatus（L12）` |
| Run history state | `useRunHistory` uses SWR for run list/detail and local history. | `apps/studio/frontend/src/hooks/useRunHistory.ts:useRunHistory（L7）`, `apps/studio/frontend/src/hooks/useRunHistory.ts:useLocalHistory（L55）` |
| Run stream state | `useRunStream` opens run websocket and buffers queue/connection state. | `apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream（L12）`, `apps/studio/frontend/src/hooks/useRunStream.ts:connect（L49）` |
| Copilot store | Copilot messages live in a small external store with subscribe/reset/update. | `apps/studio/frontend/src/store/copilotStore.ts:copilotStore（L21）`, `apps/studio/frontend/src/store/copilotStore.ts:copilotStore（L27）` |
| Settings events | Settings listens to `/ws/events` for registry/roles refresh. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:handleFocus（L444）` |
| Backend event channels | Backend exposes run websocket and global events websocket. | `apps/studio/backend/app/routers/websockets.py:_close_unauthorized（L27）`, `apps/studio/backend/app/routers/websockets.py:terminal_stream（L50）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Runtime gate | RuntimeGate initializes runtime config and can block with splash/error. | `apps/studio/frontend/src/components/RuntimeGate.tsx:RuntimeGate（L8）`, `apps/studio/frontend/src/components/RuntimeGate.tsx:cancelled（L31）` |
| Workspace state | Workspace owns selected panel, nav stack, copilot open, selected node/edge, compile stages, and open files. | `apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace（L39）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentSkillId（L55）` |
| Copilot context | Workspace sends selected node/edge/lint status into copilot context. | `apps/studio/frontend/src/components/studio/Workspace.tsx:isLoading（L69）`, `apps/studio/frontend/src/hooks/useCopilotContext.ts:timeout（L53）` |
| Lint state | Lint status is published through sessionStorage and a custom event. | `apps/studio/frontend/src/hooks/useDebouncedLint.ts:lintStatusEvent（L6）`, `apps/studio/frontend/src/hooks/useDebouncedLint.ts:publishLintStatus（L12）` |
| Run history state | `useRunHistory` uses SWR for run list/detail and local history. | `apps/studio/frontend/src/hooks/useRunHistory.ts:useRunHistory（L7）`, `apps/studio/frontend/src/hooks/useRunHistory.ts:useLocalHistory（L55）` |
| Run stream state | `useRunStream` opens run websocket and buffers queue/connection state. | `apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream（L12）`, `apps/studio/frontend/src/hooks/useRunStream.ts:connect（L49）` |
| Copilot store | Copilot messages live in a small external store with subscribe/reset/update. | `apps/studio/frontend/src/store/copilotStore.ts:copilotStore（L21）`, `apps/studio/frontend/src/store/copilotStore.ts:copilotStore（L27）` |
| Settings events | Settings listens to `/ws/events` for registry/roles refresh. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:handleFocus（L444）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Backend event channels | Backend exposes run websocket and global events websocket. | `apps/studio/backend/app/routers/websockets.py:_close_unauthorized（L27）`, `apps/studio/backend/app/routers/websockets.py:terminal_stream（L50）` |

## 当前边界（state-engine 现在不是什么）
- 不拥有各能力业务状态含义，只拥有事件到 UI 状态投影。
- gateway 6 态投影内核归 ③b；state-engine 只消费/展示。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 状态源 | Workspace/sessionStorage/SWR/store 分散持状态 ⚠️ | stage/node/provider/sidecar 状态有清晰单源和投影边界 |
| WS bridge | useRunStream/global events 未统一接 state projection ⚠️ | run/global events 驱动 node lights/timeline/settings refresh |
| sidecar failure | RuntimeGate 可全屏阻塞 ⚠️ | sidecar failure 为局部壳状态，不阻塞基础 UI |
> **验"是否按目标改了"**：1. 状态源；2. WS bridge；3. sidecar failure。

## 读代码主路径提示
`apps/studio/frontend/src/components/RuntimeGate.tsx:RuntimeGate` → `apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace` → `apps/studio/frontend/src/hooks/useDebouncedLint.ts:useDebouncedLint` → `apps/studio/frontend/src/hooks/useRunStream.ts:useRunStream` → `apps/studio/frontend/src/store/copilotStore.ts:copilotStore` → `apps/studio/backend/app/routers/websockets.py:run_events`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#04-platform-state-engine)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `shell-layout` · `compile-lint` · `predict` · `run-execution` · `trace-observability` · `settings` · `gateway`
