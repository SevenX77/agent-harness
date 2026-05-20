# state-management (studio system-level) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Studio frontend 跨 feature 共享 client state；不覆盖 server 数据获取本身。
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

当前 Studio 的用户状态体验是多来源拼起来的。
PM 打开一个 skill 后，顶部 Header、左侧 Panels、中间 Canvas/Editor、右侧 Copilot 都能看到同一个当前 skill。
这不是因为有一个统一全局 store，而是因为 `Workspace` 在顶层持有大量 `useState`，再通过 props 和 `WorkspaceContext` 向下传。

`App` 只持有 `currentSkillId`，见 `apps/studio/frontend/src/App.tsx:7` 到 `apps/studio/frontend/src/App.tsx:20`。
`Workspace` 再持有导航栈、active panel、Copilot 开关、打开文件、split mode、selected node、compile state、conflict 等状态，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:35` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:64`。

用户看到的编辑器状态主要来自 `WorkspaceContext`。
它定义 `activeFiles`、`activeFileDetails`、`splitMode`、文件打开/关闭/保存回调、导航栈回调，见 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:22` 到 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:38`。
Provider 本身只是 `createContext` 的 Provider alias，见 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:40` 到 `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:42`。

编辑器的视觉保存状态在单个 `LazyMonacoPanel` 里。
它维护 draft、saved value、hash、timer、in-flight 等本地 state/ref，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:65` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:76`。
这让单个文件编辑体验可用，但也说明当前 Draft 不在统一全局 draft store。

Split Editor 的用户体验由 `splitMode` 和 `activeFileDetails` 决定。
`SplitEditor` 从 `useWorkspaceContext()` 读取这些状态，见 `apps/studio/frontend/src/components/studio/SplitEditor.tsx:26` 到 `apps/studio/frontend/src/components/studio/SplitEditor.tsx:35`。
当前没有 `activeFocusSide`，所以用户点击文件时目标 pane 由 `Workspace` 规则决定。

Canvas 选中态也是 `Workspace` 本地 state。
`selectedNodeId` 和 `selectedNode` 在 `apps/studio/frontend/src/components/studio/Workspace.tsx:55` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:56`。
`handleNodeSelect` 写这两个状态，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:86` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:89`。

Copilot 消息状态不是 `WorkspaceContext`。
它使用一个自定义 external store `copilotStore`，包含 `skillId` 和 `messages`，见 `apps/studio/frontend/src/store/copilotStore.ts:5` 到 `apps/studio/frontend/src/store/copilotStore.ts:13`。
订阅模型是 Set listeners + `useSyncExternalStore`，见 `apps/studio/frontend/src/store/copilotStore.ts:15` 到 `apps/studio/frontend/src/store/copilotStore.ts:45`。

## 前端逻辑

当前 Provider 嵌套顺序很浅。
`main.tsx` 只创建 React root 并渲染 `App`，见 `apps/studio/frontend/src/main.tsx:14` 到 `apps/studio/frontend/src/main.tsx:18`。
`App` 包裹 `TooltipProvider`、`RuntimeGate`、`Workspace` 和 `Toaster`，见 `apps/studio/frontend/src/App.tsx:10` 到 `apps/studio/frontend/src/App.tsx:20`。
`WorkspaceProvider` 在 `Workspace` return 内包住整个 workspace，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:337` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:448`。

当前 `WorkspaceContext` 是粗粒度 context。
`contextValue` 聚合了当前 skill、导航栈、打开文件、split mode 和多个回调，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:258` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:290`。
因为它是一个对象，所以其中任何字段变化都可能让所有 consumer 重新渲染。

没有 Redux。
没有 Zustand。
当前自定义 store 只有 Copilot store 这种轻量 external store。
`copilotStore.subscribe` 添加 listener 并返回取消函数，见 `apps/studio/frontend/src/store/copilotStore.ts:21` 到 `apps/studio/frontend/src/store/copilotStore.ts:26`。
`useCopilot` 通过 `useSyncExternalStore` 读取它，见 `apps/studio/frontend/src/hooks/useCopilot.ts:25` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:27`。

有多个局部 `useReducer`。
Skill 创建向导使用 `useReducer`，见 `apps/studio/frontend/src/hooks/useSkillCreator.ts:1` 和 `apps/studio/frontend/src/hooks/useSkillCreator.ts:146`。
Input Playground 也使用 reducer，见 `apps/studio/frontend/src/hooks/useInputPlayground.ts:1` 和 `apps/studio/frontend/src/hooks/useInputPlayground.ts:147`。
这些 reducer 是 feature-local，不是跨 feature 全局 store。

持久化分三类。
Recent skills 存 `localStorage`，见 `apps/studio/frontend/src/hooks/useRecentSkills.ts:8` 到 `apps/studio/frontend/src/hooks/useRecentSkills.ts:10`、`apps/studio/frontend/src/hooks/useRecentSkills.ts:26` 到 `apps/studio/frontend/src/hooks/useRecentSkills.ts:31`。
Lint status 存 `sessionStorage` 并派发 `CustomEvent`，见 `apps/studio/frontend/src/hooks/useDebouncedLint.ts:6` 到 `apps/studio/frontend/src/hooks/useDebouncedLint.ts:18`。
Draft persist hook 存 `localStorage`，见 `apps/studio/frontend/src/hooks/useDraftPersist.ts:21` 到 `apps/studio/frontend/src/hooks/useDraftPersist.ts:31`、`apps/studio/frontend/src/hooks/useDraftPersist.ts:145` 到 `apps/studio/frontend/src/hooks/useDraftPersist.ts:164`。

主编辑器当前没有接入 `useDraftPersist`。
主链路是 `LazyMonacoPanel` 内存 draft + 1500ms debounce 写后端，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:163` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:179`。
保存失败或冲突时通过 `SaveConflict` 回到 Workspace，见 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:115` 到 `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:129`。

外部文件变化通过 WebSocket 更新 state。
`Workspace` 连接 `/ws/events`，解析 `skill_changed`，再刷新打开文件或设置 conflict，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:218` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:256`。
这说明 file watcher 事件不是独立 store，而是直接进入 Workspace state。

## 后端功能

本 folder 只描述 client state，但当前有些 client state 直接依赖后端事件。
后端 file watcher 通过 event bus 广播 `skill_changed`，事件结构在 `apps/studio/backend/app/services/file_watcher.py:120` 到 `apps/studio/backend/app/services/file_watcher.py:132`。
Frontend Workspace 订阅 `/ws/events` 后把这些事件转成 editor conflict 或 remote reload。

后端不保存 frontend panel layout state。
`Workspace` 的 active panel、split mode、selected node 都是浏览器内存 state，见 `apps/studio/frontend/src/components/studio/Workspace.tsx:35` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:64`。
浏览器刷新会丢掉这些 state，除非它们另有 local/session storage。

后端保存真实 skill file 内容。
前端保存文件调用 `writeSkillFile`，见 `apps/studio/frontend/src/api/client.ts:162` 到 `apps/studio/frontend/src/api/client.ts:173`。
这意味着 source of truth 是后端文件系统，而不是 frontend draft。

运行流状态来自 run manager。
Run stream 的 frontend hook 是 `useRunStream`，它维护 events/status/error，见 `apps/studio/frontend/src/hooks/useRunStream.ts:12` 到 `apps/studio/frontend/src/hooks/useRunStream.ts:20`。
后端 `StudioQueueCallback` 转换 graph-agent callback event，见 `apps/studio/backend/app/services/run_manager.py:87` 到 `apps/studio/backend/app/services/run_manager.py:150`。

Copilot 消息 state 在 frontend store，Copilot view context 在 backend service。
Frontend 通过 `useCopilotContext` 上报 selected node 等上下文，调用点在 `apps/studio/frontend/src/components/studio/Workspace.tsx:65` 到 `apps/studio/frontend/src/components/studio/Workspace.tsx:80`。
Copilot store 只保留消息，不保留后端 session 内部状态。

## API

当前没有一个统一 state API。
State 被拆在 React props/context、custom store、browser storage、HTTP/WS 返回中。

现有 WorkspaceContext TypeScript contract:

```typescript
export interface WorkspaceContextValue {
  currentSkillId: string | null
  navStack: string[]
  activeFiles: { left?: string, right?: string }
  activeFileDetails: Partial<Record<EditorSide, OpenFile>>
  splitMode: boolean
  onFileOpen: (fileOrPath: FileMeta | string, side?: EditorSide) => void
  openSplitEditor: () => void
  closeFile: (side: EditorSide) => void
  updateFileContent: (side: EditorSide, content: string) => void
  markFileSaved: (side: EditorSide, hash: string) => void
  setFileInFlight: (side: EditorSide, inFlight: boolean) => void
  onSaveConflict: (conflict: SaveConflict) => void
  reloadOpenFile: (side: EditorSide) => Promise<void>
  pushNavSkill: (skillId: string) => void
  popNavTo: (index: number) => void
}
```

The real definition is in `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:22` to `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:38`.

Copilot external store contract:

```typescript
interface CopilotState {
  skillId: string | null
  messages: CopilotMessage[]
}

interface CopilotStore {
  getSnapshot(): CopilotState
  subscribe(listener: () => void): () => void
  reset(skillId: string | null): void
  appendMessage(message: CopilotMessage): void
  updateMessage(messageId: string, updater: (message: CopilotMessage) => CopilotMessage): void
  clearMessages(): void
}
```

Current implementation is in `apps/studio/frontend/src/store/copilotStore.ts:21` to `apps/studio/frontend/src/store/copilotStore.ts:45`.

Browser storage contracts:

```typescript
type RecentSkillsStorage = string[] // localStorage["recentSkills"]

interface StoredDraft {
  content: string
  timestamp: number
  baseHash: string
}

type LintStatusStorage = "idle" | "checking" | "passed" | "failed"
```

`StoredDraft` is defined in `apps/studio/frontend/src/hooks/useDraftPersist.ts:7` to `apps/studio/frontend/src/hooks/useDraftPersist.ts:11`.
Lint status storage key is defined in `apps/studio/frontend/src/hooks/useDebouncedLint.ts:6` to `apps/studio/frontend/src/hooks/useDebouncedLint.ts:10`.

## Data Model & State

Current global-ish state inventory:

| State | Owner | Persistence | Notes |
|---|---|---|---|
| `currentSkillId` | `App` | memory | Top-level selected skill |
| `navStack` | `Workspace` | memory | Nested skill navigation |
| `activePanel` | `Workspace` | memory | Left panel selection |
| `copilotOpen` | `Workspace` | memory | Right panel presence |
| `activeFileDetails` | `WorkspaceContext` | memory | Editor open files |
| `splitMode` | `WorkspaceContext` | memory | Editor layout |
| `selectedNodeId` | `Workspace` | memory | Canvas selection |
| `compileStages` | `Workspace` | memory | Per skill compile UI |
| `compileErrors` | `Workspace` | memory | Per skill compile issue list |
| `messages` | `copilotStore` | memory | Per skill chat messages |
| `recentSkills` | hook | localStorage | Welcome-page recents |
| lint status | hook | sessionStorage | Build stage hint |
| draft persist | hook | localStorage | Existing hook, not main editor path |

Current `SaveConflict` contains skillId/path/side/localContent/remoteContent/remoteHash, see `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:13` to `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:20`.
This state is transient and shown by `ConflictDialog` in `Workspace`, see `apps/studio/frontend/src/components/studio/Workspace.tsx:441` to `apps/studio/frontend/src/components/studio/Workspace.tsx:446`.

Current compile state is not part of `WorkspaceContext`.
`compileStages` and `compileErrors` live only in `Workspace`, see `apps/studio/frontend/src/components/studio/Workspace.tsx:62` to `apps/studio/frontend/src/components/studio/Workspace.tsx:64`.
CenterActionBar consumes derived stage inside Workspace, see `apps/studio/frontend/src/components/studio/Workspace.tsx:324` to `apps/studio/frontend/src/components/studio/Workspace.tsx:331`.

Current panel layout state is not persisted.
Resizable panels use default sizes in JSX, see `apps/studio/frontend/src/components/studio/Workspace.tsx:359` to `apps/studio/frontend/src/components/studio/Workspace.tsx:439`.
There is no localStorage read/write for panel sizes in the main Workspace.

## Cross-feature interaction

### State workspace context owner {#cross-state-workspace-context}

State management owns the inventory of frontend client state and context boundaries.
Layout owns panel placement and Context Inspector UI; see [studio-layout baseline](../studio-layout/baseline.md).
Workspace file system owns file persistence and watcher semantics; see [workspace-file-system baseline](../workspace-file-system/baseline.md).

### State editor draft boundary {#cross-state-editor-draft}

Current editor draft is mainly memory inside `LazyMonacoPanel`.
The existing localStorage draft hook is not the main editor path.
Detailed file save behavior belongs to [workspace-file-system baseline](../workspace-file-system/baseline.md).

### State event bridge boundary {#cross-state-event-bridge}

File watcher and run events enter frontend state through WebSocket.
The realtime transport inventory belongs to [event-bus-and-websocket baseline](../event-bus-and-websocket/baseline.md).

