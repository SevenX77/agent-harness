---
module: 02_capabilities/copilot-assist
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；SDK 对话 live，但仍直写、session 内存态、ThinkingBlock 未翻译，Settings 里的 SDK 测试路径与真实 chat 不等价 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/backend/app/services/copilot.py:stream_query · apps/studio/backend/app/services/copilot.py:_translate_sdk_message · apps/studio/backend/app/routers/copilot.py:copilot_ws · apps/studio/frontend/src/store/copilotStore.ts:reset · apps/studio/backend/app/routers/llm.py:_probe_copilot_sdk_tool_call
units: [copilot-sdk-test-parity, copilot-session-persistence]
---

# copilot-assist — Baseline（当下代码实现逻辑）

> **Scope**: 右侧 copilot chat 的端到端能力：对话、多 session、@mention、安全写、建技能向导、judge/打磨载体与分析 bar。
> **现状一句话**: SDK 对话 live，但仍直写、session 内存态、ThinkingBlock 未翻译，Settings 里的 SDK 测试路径与真实 chat 不等价 ⚠️。

## UI/UX
右侧 copilot chat 的端到端能力：对话、多 session、@mention、安全写、建技能向导、judge/打磨载体与分析 bar。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| 面板主入口 | `copilot-panel.tsx:74-230` | header / 连接态 / 消息列表 / 空态(按 view) / 输入框 / 模型选择器 / 发送 |
| 消息渲染 | `copilot-panel.tsx:17-37` | 用户/assistant 区分；`ToolCallBubble`；Edit/Write/Read/Bash 结果→diff/summary bubble |
| 会话逻辑 | `useCopilot.ts:25-157` | skillId 变即 reset；WS connect/重连；textQueue 75ms flush；发送只构造 `{user_message, model_override?}` |
| 上下文同步 | `useCopilotContext.ts:6-62` | debounce POST `view/context/timestamp`；>2048 压缩；**view 快照通道、非 mention** |
| 事件类型 | `types/copilot.ts:14-109` | `text_delta`/`tool_use_start`/`tool_use_result`/`error`/`done`/`unknown` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| 后端 WS | `routers/copilot.py:34-55` | `WS /api/skills/{id}/copilot/ws`；`CopilotWsRequestPayload(user_message, model_override)` |
| SDK 服务 | `copilot.py:51-114` | `ClaudeSDKClient`；allowed `Read/Write/Edit/Bash`；**`permission_mode=acceptEdits`（直写）** |
| SDK 翻译 | `copilot.py:378-400` | `TextBlock`→text；`ToolUseBlock`→start；`ToolResultBlock`→result；**`ThinkingBlock` 未翻（丢）** |
| provider | `copilot.py:372-381` | `model_override` 否则 `copilot_chat` role |

## 当前边界（copilot-assist 现在不是什么）
- 数据流归属保持切开：judge/打磨归 `golden-eval`，commit-msg 归 `publish`。
- 写盘唯一权威不在 copilot；Apply 委托 `native-fs` / editor 保存契约。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| ThinkingBlock | `_translate_sdk_message` 丢 ThinkingBlock ⚠️ | thinking/tool call 全量流式，折叠但不省略 |
| 安全写 | SDK `acceptEdits` 直写 ⚠️ | Write/Edit 变 diff proposal，Apply 走 Rust/编辑器保存与冲突处理 |
| session | 前端 store reset 后内存态丢失 ⚠️ | 一 skill 多 session 持久化，退出恢复全部与活跃 tab |
| SDK 测试 | Settings probe 走 `AsyncAnthropic` ⚠️ | 短 smoke 走真实 `ClaudeSDKClient` chat 路径 |
> **验"是否按目标改了"**：1. ThinkingBlock；2. 安全写；3. session；4. SDK 测试。

## 读代码主路径提示
`apps/studio/backend/app/services/copilot.py:stream_query` → `apps/studio/backend/app/services/copilot.py:_translate_sdk_message` → `apps/studio/backend/app/routers/copilot.py:copilot_ws` → `apps/studio/frontend/src/store/copilotStore.ts:reset` → `apps/studio/backend/app/routers/llm.py:_probe_copilot_sdk_tool_call`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-copilot-assist)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `copilot` region · `studio-settings` · `golden-eval` · `publish` · `native-fs` · `llm-copilot-http-api`
