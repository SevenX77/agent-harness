# copilot-assistance (studio feature) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Studio Copilot 面板、上下文注入、AI 辅助编辑、diff / apply 体验
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

Copilot UI 的主入口是 `CopilotPanel`，它包含 header、连接状态、消息列表、空态、输入框、模型选择器和发送按钮，见 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:74` 到 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:230`。空态会根据当前 view 展示不同提示：评估视图、模板创建、普通 skill 创建，见 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:130` 到 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:179`。

消息呈现由 `ChatMessageItemBase` 负责，用户消息和 assistant 消息使用不同背景，并用 ReactMarkdown 渲染文本，见 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:17` 到 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:28`。工具事件显示为 `ToolCallBubble`，工具结果如果是 Edit/Write/Read/Bash 结果则进入 diff/summary bubble，见 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:29` 到 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:37`。

输入区 placeholder 明确提示 “Use '@' to mention nodes, files, or trace events”，见 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:195`。但当前 @ mention 没有解析 UI、没有 token picker，也没有把 mentions 放进 WebSocket payload；“Add context”按钮也是 UI 占位，只是 disabled，见 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:199` 到 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:212`。这是审计 High-002 的核心现状：规范期待 `mentions: [{type:'file', id:'...'}]` 一类 payload，但当前代码没有实现。

模型选择器连接 LLM Roles 和 provider 配置，`CopilotPanel` 加载角色与 credentials，用户可选模型覆盖，见 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:75` 到 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:108`。模型配置本身见 [llm-provider-config baseline](../llm-provider-config/baseline.md)。

## 前端逻辑

Copilot 的会话逻辑集中在 `useCopilot(skillId)`。Hook 会在 skillId 变化时重置消息，建立 `wsUrl(/api/skills/${skillId}/copilot/ws)` WebSocket，维护 `connecting/open/closed/error` 状态，并在异常关闭后重连，见 `apps/studio/frontend/src/hooks/useCopilot.ts:25` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:117`。

流式文本不是每个 token 都直接 setState，而是先进入 `textQueueRef`，再每 75ms flush 一次，降低渲染压力，见 `apps/studio/frontend/src/hooks/useCopilot.ts:50` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:70`。收到 `text_delta` 时追加文本，收到其他事件时更新 assistant message 的事件列表和状态，见 `apps/studio/frontend/src/hooks/useCopilot.ts:119` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:141`。

发送消息时，前端只构造 `{ user_message, model_override? }`，见 `apps/studio/frontend/src/hooks/useCopilot.ts:143` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:157`。这里没有 `mentions`、`attachments`、`selectedNodeId`、`selectedFilePath` 或 trace event id，因此 @ 提及和“Add context”按钮不会改变请求 payload。

上下文同步由 `useCopilotContext` 负责，它把 `view`、`context`、`timestamp` debounce 后 POST 到 `/skills/{skillId}/copilot/context`，见 `apps/studio/frontend/src/hooks/useCopilotContext.ts:39` 到 `apps/studio/frontend/src/hooks/useCopilotContext.ts:62`。大对象会被压缩成摘要，阈值是 2048 bytes，见 `apps/studio/frontend/src/hooks/useCopilotContext.ts:6` 到 `apps/studio/frontend/src/hooks/useCopilotContext.ts:37`。这是一条“当前 view 快照”通道，不是用户显式 mention 通道。

事件类型和前端 normalize 逻辑在 `apps/studio/frontend/src/types/copilot.ts:14` 到 `apps/studio/frontend/src/types/copilot.ts:109`。`CopilotContextPayload` 只有 `view/context/timestamp`，见 `apps/studio/frontend/src/types/copilot.ts:63` 到 `apps/studio/frontend/src/types/copilot.ts:67`，同样没有 mentions 字段。

## 后端功能

后端 WebSocket endpoint 是 `/api/skills/{skill_id}/copilot/ws`，见 `apps/studio/backend/app/routers/copilot.py:34` 到 `apps/studio/backend/app/routers/copilot.py:55`。它校验权限后循环接收 JSON，解析成 `CopilotWsRequestPayload`，然后调用 `copilot_service.stream_query`，把事件逐条 `send_json` 回前端。

Copilot 请求模型只有 `user_message` 和 `model_override`，见 `apps/studio/backend/app/models/copilot.py:21` 到 `apps/studio/backend/app/models/copilot.py:28`。这再次确认 High-002：后端 schema 当前不接受 `mentions`，因此即使前端将来发送该字段，也需要先扩展模型与服务层。

服务层使用 Claude Agent SDK。`CopilotService` 设置允许工具 Read/Write/Edit/Bash，见 `apps/studio/backend/app/services/copilot.py:51` 到 `apps/studio/backend/app/services/copilot.py:54`；系统提示和工作目录配置在 `apps/studio/backend/app/services/copilot.py:64` 到 `apps/studio/backend/app/services/copilot.py:114`。上下文通过 `set_view_context` 缓存在服务内，见 `apps/studio/backend/app/services/copilot.py:117` 到 `apps/studio/backend/app/services/copilot.py:140`。

每次 query 前，服务会解析 provider：如果有 `model_override` 则按模型解析，否则使用 `copilot_chat` role，见 `apps/studio/backend/app/services/copilot.py:372` 到 `apps/studio/backend/app/services/copilot.py:381`。缺少 API key 时会返回错误事件，见 `apps/studio/backend/app/services/copilot.py:191` 到 `apps/studio/backend/app/services/copilot.py:205`。

SDK 消息被翻译成前端事件。TextBlock 转成 `text_delta`，ToolUseBlock 转成 `tool_use_start`，ToolResultBlock 转成 `tool_use_result` 或 error，见 `apps/studio/backend/app/services/copilot.py:317` 到 `apps/studio/backend/app/services/copilot.py:361`。dispatch REST endpoint 目前直接 `NotImplementedError`，见 `apps/studio/backend/app/routers/copilot.py:23` 到 `apps/studio/backend/app/routers/copilot.py:31`。

## API

WebSocket API：`WS /api/skills/{skill_id}/copilot/ws`。请求体当前是 `CopilotWsRequestPayload(user_message, model_override)`，响应体是 `CopilotEvent` union，见 `apps/studio/backend/app/models/copilot.py:21` 到 `apps/studio/backend/app/models/copilot.py:70`。

上下文 API：`POST /api/skills/{skill_id}/copilot/context`，请求体是 `ContextUpdateRequest(view, context, timestamp)`，见 `apps/studio/backend/app/models/copilot.py:73` 到 `apps/studio/backend/app/models/copilot.py:80`；router 处理见 `apps/studio/backend/app/routers/copilot.py:58` 到 `apps/studio/backend/app/routers/copilot.py:86`。

前端 WebSocket URL 由 `wsUrl` 生成，见 `apps/studio/frontend/src/api/client.ts:101` 到 `apps/studio/frontend/src/api/client.ts:108`。LLM roles / credentials API 由 settings 模块提供，Copilot 通过 `getRoles`、`getCredentials` 获取模型选择数据，见 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:83` 到 `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:100`。

## Data Model / State

前端消息模型是 `CopilotMessage`，包含 `id/role/content/events/status`，见 `apps/studio/frontend/src/types/copilot.ts:54` 到 `apps/studio/frontend/src/types/copilot.ts:61`。Hook 内部维护 messages、status、currentAssistantId、文本队列和 WebSocket ref，见 `apps/studio/frontend/src/hooks/useCopilot.ts:25` 到 `apps/studio/frontend/src/hooks/useCopilot.ts:33`。

后端事件模型包括 text_delta、tool_use_start、tool_use_result、error、done，见 `apps/studio/backend/app/models/copilot.py:30` 到 `apps/studio/backend/app/models/copilot.py:70`。工具名限定为 Read/Write/Edit/Bash，见 `apps/studio/backend/app/models/copilot.py:9`。

上下文状态不是持久化数据库，而是服务内 `_contexts` dict，类型是 `ViewContext`，见 `apps/studio/backend/app/services/copilot.py:71` 到 `apps/studio/backend/app/services/copilot.py:82`。`build_system_prompt` 会把最近 view/context 作为 JSON 注入系统提示，见 `apps/studio/backend/app/services/copilot.py:165` 到 `apps/studio/backend/app/services/copilot.py:180`。

## Cross-feature interaction

与 Canvas：当前没有节点 mention payload，Canvas 选中态只能通过通用 context 间接进入 Copilot，见 `apps/studio/frontend/src/hooks/useCopilotContext.ts:48` 到 `apps/studio/frontend/src/hooks/useCopilotContext.ts:62`。Canvas 的节点和边现状见 [canvas-topology baseline](../canvas-topology/baseline.md)。

与多文件编辑器：Copilot 工具可 Read/Write/Edit 文件，但前端 message payload 不包含当前打开文件路径；文件上下文依赖 `useCopilotContext` 的 view 快照。编辑器保存与冲突处理见 [multi-file-editor baseline](../multi-file-editor/baseline.md)。

与 LLM provider config：Copilot 默认使用 `copilot_chat` role，也允许 model override，见 `apps/studio/backend/app/services/copilot.py:372` 到 `apps/studio/backend/app/services/copilot.py:381`。provider credential 和 roles 的编辑见 [llm-provider-config baseline](../llm-provider-config/baseline.md)。
