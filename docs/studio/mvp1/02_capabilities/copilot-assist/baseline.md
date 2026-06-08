---
status: verified（基于本轮 copilot.py/SDK 升级与 store/persistence/thinking 实现）
last_verified: 2026-06-08
ground_truth:
  - apps/studio/frontend/src/components/copilot/copilot-panel.tsx
  - apps/studio/frontend/src/hooks/useCopilot.ts · useCopilotContext.ts
  - apps/studio/frontend/src/types/copilot.ts · store/copilotStore.ts
  - apps/studio/backend/app/services/copilot.py · routers/copilot.py · models/copilot.py
  - claude_agent_sdk/types.py
---

# copilot-assist — Baseline（现状·对齐代码）

核心结论：**基础对话链路 live**（面板/流式/工具气泡/模型选择器/WS）。经过 WS-5 改造后，Session 支持按 `(workspace, skill)` 进行多会话隔离及磁盘持久化（写盘失败显示告警，冷启动恢复处于 deferred 状态），`ThinkingBlock` 已实现翻译为 `thinking_delta` 事件并在前端渲染为折叠的 Thought 气泡，@mention 与安全写依然作为 deferred 状态保留。

## 覆盖范围（现状 file:line）

| 目标 | 现状范围 | 说明 |
|---|---|---|
| 面板主入口 | `copilot-panel.tsx` | header / 连接态 / 消息列表 / 空态(按 view) / 输入框 / 模型选择器 / 发送 / Session 隔离与切换 |
| 消息渲染 | `copilot-panel.tsx` | 用户/assistant 区分；`ToolCallBubble`；`thinking_delta` (Thought折叠框)；Edit/Write/Read/Bash 结果→diff/summary bubble |
| 会话逻辑 | `useCopilot.ts` | WS connect/重连；textQueue 75ms flush；结合 `copilotStore` 获取当前 Session 消息并隔离 |
| 上下文同步 | `useCopilotContext.ts` | debounce POST `view/context/timestamp`；>2048 压缩；view 快照通道 |
| 事件类型 | `types/copilot.ts` | `text_delta`/`thinking_delta`/`tool_use_start`/`tool_use_result`/`error`/`done`/`unknown` |
| 后端 WS | `routers/copilot.py` | `WS /api/skills/{id}/copilot/ws`；`CopilotWsRequestPayload(user_message, model_override)` |
| SDK 服务 | `copilot.py` | `ClaudeSDKClient`；allowed `Read/Write/Edit/Bash`；`permission_mode=acceptEdits`（直写） |
| SDK 翻译 | `copilot.py` | `TextBlock`→text；`ToolUseBlock`→start；`ToolResultBlock`→result；`ThinkingBlock`→`thinking_delta` |
| provider | `copilot.py` | `model_override` 否则 `copilot_chat` role |

## 编号执行流程（现状）

1. skill 打开 → `copilotOpen=Boolean(skillId)`，welcome 屏无 copilot。
2. `useCopilot` 建 WS `/api/skills/{id}/copilot/ws`；会话与消息状态由 `copilotStore` 接管。
3. `copilotStore` 执行磁盘持久化，使用 Tauri native `writeWorkspaceFile` 并支持隔离切换。
4. 发消息 → `{user_message, model_override?}`（无 mentions / dirty buffer / 选中态）。
5. 后端 `stream_query` → SDK；`TextBlock/ToolUse/ToolResult/ThinkingBlock` 翻成事件 `send_json`。
6. 流式 `text_delta` 进 textQueue，75ms flush；`thinking_delta` 实时在前端折叠渲染。
7. SDK `acceptEdits` → Write/Edit 直接落盘，无提案。

## 现状 gap（→ alignment 接线目标）

- **@mention**：占位符 only，无菜单/无 payload；"Add context" disabled。
- **session 冷启动恢复**：由于缺少 native 读目录命令，冷启动恢复处于 deferred 状态（测试保持 `it.skip`），但会话切换与写入隔离持久化已完成。
- **安全写**：`acceptEdits` 直写，无 `patch_proposed`（前后端 grep 空）。
- **judge**：`view='eval'` 无人传 → `inEvalView` 恒 false → judge 不可达。
- **E2E 按钮选择**：因欢迎页面 Skill 卡片可访问名称包含路径等附加信息导致 E2E 锚点精确匹配超时，E2E 修复已登记为 deferred。

## SDK block 类型（折叠/翻译依据）

`claude_agent_sdk/types.py`：`AssistantMessage.content` = `TextBlock`(答复) / `ThinkingBlock`(推理,:927) / `ToolUseBlock` / `ToolResultBlock` / `ServerToolUse*`。现码只消费前 3 类（+ ToolResult），**Thinking/ServerTool/SystemMessage(TaskStarted/Progress/Notification) 未捕获**。

## 待办 / 疑点

- 实现前重核 file:line（baseline 基于 2026-05-20 mvp0 + 本轮 SDK 复核）。
- `ThinkingBlock`/`ServerToolUse`/`SystemMessage` 翻译补全范围（alignment 要求全流式不省略）。
