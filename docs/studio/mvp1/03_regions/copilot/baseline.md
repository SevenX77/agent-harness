---
module: 03_regions/copilot
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；面板与 WS live；session 仍易丢，ThinkingBlock/@mention/analysis bar 未落，且 Workspace 传 outer `skillId` 有下钻风险 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace · apps/studio/frontend/src/components/copilot/copilot-panel.tsx:CopilotPanel · apps/studio/frontend/src/hooks/useCopilot.ts:useCopilot · apps/studio/frontend/src/hooks/useCopilotContext.ts:useCopilotContext · apps/studio/frontend/src/components/copilot/tool-call-bubble.tsx:ToolCallBubble · apps/studio/frontend/src/components/copilot/diff-bubble.tsx:DiffBubble
units: [copilot-session-persistence, copilot-sdk-test-parity]
---

# copilot — Baseline（当下代码实现逻辑）

> **Scope**: 右侧 Copilot region：chat panel、connection state、view context sync、model route picker、tool/diff rendering 与 analysis bar UI。
> **现状一句话**: 面板与 WS live；session 仍易丢，ThinkingBlock/@mention/analysis bar 未落，且 Workspace 传 outer `skillId` 有下钻风险 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Shell mount | Workspace mounts CopilotPanel in a right resizable panel when open. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L545）` |
| Skill prop risk | CopilotPanel receives the outer `skillId` prop instead of `currentSkillId`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L554）` |
| Panel | CopilotPanel shows connection status, messages, empty prompts, input box, attach/context buttons, and model picker. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:CopilotPanel（L74）`, `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:submit（L118）` |
| Registry role | Panel loads registry and picks `copilot_chat` fallback route. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:inEvalView（L83）`, `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:role（L90）` |
| Send | Submit sends draft through `useCopilot` with selected route id. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:submit（L111）` |
| Websocket | `useCopilot` opens `/copilot/ws`, reconnects, queues text deltas, and appends events. | `apps/studio/frontend/src/hooks/useCopilot.ts:connect（L96）`, `apps/studio/frontend/src/hooks/useCopilot.ts:delay（L123）` |
| View context | `useCopilotContext` debounces current view context to `/copilot/context`. | `apps/studio/frontend/src/hooks/useCopilotContext.ts:useCopilotContext（L39）`, `apps/studio/frontend/src/hooks/useCopilotContext.ts:timeout（L53）` |
| Tool/diff bubbles | Tool calls and diff summaries render inside messages. | `apps/studio/frontend/src/components/copilot/tool-call-bubble.tsx:ToolCallBubbleBase（L18）`, `apps/studio/frontend/src/components/copilot/diff-bubble.tsx:DiffBubbleBase（L19）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Shell mount | Workspace mounts CopilotPanel in a right resizable panel when open. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L545）` |
| Skill prop risk | CopilotPanel receives the outer `skillId` prop instead of `currentSkillId`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L554）` |
| Panel | CopilotPanel shows connection status, messages, empty prompts, input box, attach/context buttons, and model picker. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:CopilotPanel（L74）`, `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:submit（L118）` |
| Registry role | Panel loads registry and picks `copilot_chat` fallback route. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:inEvalView（L83）`, `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:role（L90）` |
| Send | Submit sends draft through `useCopilot` with selected route id. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:submit（L111）` |
| Websocket | `useCopilot` opens `/copilot/ws`, reconnects, queues text deltas, and appends events. | `apps/studio/frontend/src/hooks/useCopilot.ts:connect（L96）`, `apps/studio/frontend/src/hooks/useCopilot.ts:delay（L123）` |
| View context | `useCopilotContext` debounces current view context to `/copilot/context`. | `apps/studio/frontend/src/hooks/useCopilotContext.ts:useCopilotContext（L39）`, `apps/studio/frontend/src/hooks/useCopilotContext.ts:timeout（L53）` |
| Tool/diff bubbles | Tool calls and diff summaries render inside messages. | `apps/studio/frontend/src/components/copilot/tool-call-bubble.tsx:ToolCallBubbleBase（L18）`, `apps/studio/frontend/src/components/copilot/diff-bubble.tsx:DiffBubbleBase（L19）` |

## 后端功能
N/A。

## 当前边界（copilot 现在不是什么）
- chat 行为 owner 是 `copilot-assist`；region 只管渲染与交互。
- 真实 SDK smoke 路径归 capability/platform，region 只展示结果。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| session UI | 内存态 / skill 切换 reset 风险 ⚠️ | 顶部多 session tab 持久化并恢复 |
| analysis bar | 旧 golden 入口/sonner 口径残留 ⚠️ | predict/run 后输入框上方弹 analysis bar，确认后消失 |
| 下钻 skillId | Panel 收 outer `skillId`，非 `currentSkillId` ⚠️ | 子图下钻时 copilot 上下文与 currentSkillId 一致 |
> **验"是否按目标改了"**：1. session UI；2. analysis bar；3. 下钻 skillId。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace` → `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:CopilotPanel` → `apps/studio/frontend/src/hooks/useCopilot.ts:useCopilot` → `apps/studio/frontend/src/hooks/useCopilotContext.ts:useCopilotContext` → `apps/studio/frontend/src/components/copilot/tool-call-bubble.tsx:ToolCallBubble` → `apps/studio/frontend/src/components/copilot/diff-bubble.tsx:DiffBubble`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-copilot)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `copilot-assist` · `studio-settings` · `settings` · `native-fs` · `golden-eval`
