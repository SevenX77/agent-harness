---
module: copilot-assist
doc: baseline
status: drafted（基于 mvp0 copilot-chat baseline 2026-05-20 + 本轮 copilot.py/SDK 复核；实现前 file:line 重核）
last_verified: 2026-06-03
ground_truth:
  - apps/studio/frontend/src/components/copilot/copilot-panel.tsx
  - apps/studio/frontend/src/hooks/useCopilot.ts · useCopilotContext.ts
  - apps/studio/frontend/src/types/copilot.ts · store/copilotStore.ts
  - apps/studio/backend/app/services/copilot.py · routers/copilot.py · models/copilot.py
  - claude_agent_sdk/types.py
---

# copilot-assist — Baseline（现状·对齐代码）

核心结论：**基础对话链路 live**（面板/流式/工具气泡/模型选择器/WS），但侧边栏要做的"全功能"几乎全是**空壳/桩/丢失**：@mention 纯占位、session 不持久化（退出即丢）、安全写未做（`acceptEdits` 直写）、`ThinkingBlock` 被丢、judge 不可达、徽章是假的。= **接线工程为主**。目标设计见 [mvp1-alignment](./mvp1-alignment.md)。

## 覆盖范围（现状 file:line）

| 目标 | 现状范围 | 说明 |
|---|---|---|
| 面板主入口 | `copilot-panel.tsx:74-230` | header / 连接态 / 消息列表 / 空态(按 view) / 输入框 / 模型选择器 / 发送 |
| 消息渲染 | `copilot-panel.tsx:17-37` | 用户/assistant 区分；`ToolCallBubble`；Edit/Write/Read/Bash 结果→diff/summary bubble |
| 会话逻辑 | `useCopilot.ts:25-157` | skillId 变即 reset；WS connect/重连；textQueue 75ms flush；发送只构造 `{user_message, model_override?}` |
| 上下文同步 | `useCopilotContext.ts:6-62` | debounce POST `view/context/timestamp`；>2048 压缩；**view 快照通道、非 mention** |
| 事件类型 | `types/copilot.ts:14-109` | `text_delta`/`tool_use_start`/`tool_use_result`/`error`/`done`/`unknown` |
| 后端 WS | `routers/copilot.py:34-55` | `WS /api/skills/{id}/copilot/ws`；`CopilotWsRequestPayload(user_message, model_override)` |
| SDK 服务 | `copilot.py:51-114` | `ClaudeSDKClient`；allowed `Read/Write/Edit/Bash`；**`permission_mode=acceptEdits`（直写）** |
| SDK 翻译 | `copilot.py:378-400` | `TextBlock`→text；`ToolUseBlock`→start；`ToolResultBlock`→result；**`ThinkingBlock` 未翻（丢）** |
| provider | `copilot.py:372-381` | `model_override` 否则 `copilot_chat` role |

## 编号执行流程（现状）

1. skill 打开 → `copilotOpen=Boolean(skillId)`（`Workspace.tsx:41,545`），welcome 屏无 copilot。
2. `useCopilot` 建 WS `/api/skills/{id}/copilot/ws`；skillId 变即 reset 消息（**纯内存**，`copilotStore.ts:10-12,27-28`）。
3. 发消息 → `{user_message, model_override?}`（`useCopilot.ts:143-157`，**无 mentions / dirty buffer / 选中态**）。
4. 后端 `stream_query` → SDK；`TextBlock/ToolUse/ToolResult` 翻成事件 `send_json`（`copilot.py:378-400`）；**`ThinkingBlock` 丢**。
5. 流式 `text_delta` 进 textQueue，75ms flush（`useCopilot.ts:50-70`）。
6. SDK `acceptEdits` → Write/Edit **直接落盘**（`copilot.py:129`），**无提案**。

## 现状 gap（→ alignment 接线目标）

- **@mention**：占位符 only（`copilot-panel.tsx:195`），无菜单/无 payload；"Add context" disabled（`:199-212`）。
- **session**：纯内存，退出/切 skill / 回 Home 全丢（无持久化，D8 未落）。
- **安全写**：`acceptEdits` 直写，无 `patch_proposed`（前后端 grep 空）。
- **ThinkingBlock**：`copilot.py:382-400` 未翻 → 推理不可见。
- **judge**：`view='eval'` 无人传 → `inEvalView` 恒 false → judge 不可达（`copilot-panel.tsx:81,146-152`）。
- **假测试/桩/`copilot_` 前缀 bug/假徽章**：见 settings §3 走查（copilot **配置**侧，归 [[studio-settings]]）。

## SDK block 类型（折叠/翻译依据）

`claude_agent_sdk/types.py`：`AssistantMessage.content` = `TextBlock`(答复) / `ThinkingBlock`(推理,:927) / `ToolUseBlock` / `ToolResultBlock` / `ServerToolUse*`。现码只消费前 3 类（+ ToolResult），**Thinking/ServerTool/SystemMessage(TaskStarted/Progress/Notification) 未捕获**。

## 待办 / 疑点

- 实现前重核 file:line（baseline 基于 2026-05-20 mvp0 + 本轮 SDK 复核）。
- `ThinkingBlock`/`ServerToolUse`/`SystemMessage` 翻译补全范围（alignment 要求全流式不省略）。
