---
spec: copilot-context-design
status: Draft
target_goal: "Copilot 上下文渐进式披露 + @ 引用节点机制"
linked_code_paths:
  - apps/studio/frontend/src/components/copilot/copilot-panel.tsx:195
  - apps/studio/frontend/src/hooks/useCopilotContext.ts
  - apps/studio/frontend/src/components/studio/Workspace.tsx:65
linked_specs:
  - docs/studio/STUDIO_LAYOUT_SPEC.md
last_updated: 2026-05-19
---

# Requirement: Copilot Context Design

## 1. 问题陈述 (Problem Statement)
当前 Studio 中的 Copilot 面板 (`copilot-panel.tsx`) 仅仅是一个拥有占位符 ("Use '@' to mention nodes...") 的空壳。
PM 在真实使用中发现：
1. 大模型（如 Claude）如果缺乏当前项目（Skill）的整体框架和局部细节，它提供的回答完全不具备可执行性。
2. 每次向模型全量丢整个工程是不现实的，且容易超 context window 或导致模型关注力涣散。
3. PM 需要在对话时极高效率地指代某个特定的节点、某个具体的配置文件或代码片段。
因此，亟需一套**渐进式的系统提示词注入策略（Progressive Context Disclosure）**，以及前端完备的 `@` 引用拦截和菜单响应交互，以便“点击 canvas 上的任何可选择的部分对话框都出现 @ 该节点的 name/ID”。

## 2. 用户故事 (User Stories)
1. **As a PM**, I want 在 Canvas 上选中 (单击 / 拖拽) 任何可选元素 (node / context 的点 / + 扩展出来的节点) 时，Copilot 聊天框能自动填入 `@该元素` 的 mention，so that 我不需要手工复制粘贴长长的节点 ID 就能对它提问。
2. **As a PM**, I want 在 Copilot 对话框主动输入 `@` 字符时，弹出一个智能下拉菜单（MentionMenu）列出当前 Skill 所有的可引用元素，so that 我能快速选用它们作为上下文。
3. **As a 后端 Dev**, I want Copilot 拥有清晰的层级组装策略，so that 我能根据用户的当前状态（是否遇到了 Lint Error，是否 @ 了某个文件）按需截取和拼装系统 Prompt 给到大模型。

## 3. Acceptance Criteria
### User Story 1 (自动 Mention)
- **Given** 用户当前打开了 Copilot 面板，**When** 用户在 Graph Canvas 单击选中了节点 `agent_planner`，**Then** THE SYSTEM SHALL 自动在 Copilot 对话框输入区出现 `@agent_planner` 的 mention。
- **Given** 用户点击了连线数据包（Edge Context），**When** Context Inspector 抽屉滑出，**Then** THE SYSTEM SHALL 自动在聊天框带入对该数据流的引用标签 `@edge_context_123`。

### User Story 2 (主动输入 Mention)
- **Given** 用户正在 Copilot 聊天框输入内容，**When** 敲击 `@` 键，**Then** THE SYSTEM SHALL 立即在光标上方弹出 MentionMenu 下拉，列出当前 Skill 的所有可引用元素 (nodes / files / phases)。
- **Given** 悬浮菜单出现后，**When** 用户继续输入字母（如 `@plan`），**Then** 列表实时过滤并高亮包含该字符串的元素。按下 Enter 键将确认选择。

### User Story 3 (渐进式提示词组装)
- **Given** 用户跟 Copilot 对话，**When** 后端收到请求时，**Then** THE SYSTEM SHALL 按渐进式披露原则组装 System Prompt:
  - 第 1 层 (Always): Skill 基本信息 (id, name, current status)
  - 第 2 层 (按需): 当前选中节点的 detail (label, status, summary, file path)
  - 第 3 层 (按需): 用户 @ mention 引用的 nodes/files 内容
  - 第 4 层 (按需): Lint 状态 / Compile errors

## 4. 范围 (In Scope vs Out of Scope)
### In Scope
- Copilot 输入框对 `@` 的键盘拦截、菜单渲染 (`MentionMenu`) 及自动填充逻辑。
- 后端基于不同“层级”的 System Prompt 动态拼装管线设计。
- 点击 Canvas 节点、文件树与 Copilot 输入框的内容联动机制。

### Out of Scope
- 本地代码的纯离线智能补全（Ghost Text），这属于 Monaco Editor 本身的高级 LSP 集成。
- 对超大文件进行的 RAG 检索（本阶段的提及机制假设所有注入内容加起来仍在 LLM 的 200K 上下文窗口内，超大文件的向量库检索不在 MVP0 之内）。

## 5. 依赖与前置条件
- 依赖 `docs/studio/STUDIO_LAYOUT_SPEC.md` 中定义的 Right Panel 结构。
- 依赖前端引入类似 `tiptap` 或成熟的 TextArea Mention 插件，而不是重复造轮子。
- 依赖后端 Claude Agent SDK 对 `system_prompt` 的组装注入能力。

## 6. 关键约束
- **性能**: 当项目存在超过 500 个文件或节点时，键入 `@` 弹出的过滤菜单延迟必须低于 50ms。
- **Token 防爆**: 如果组合出来的 System Prompt 超过了 150K Token（考虑预留回复空间），必须有明确的截断机制或抛出过载提示。

## 相关文档
- [STUDIO_LAYOUT_SPEC.md](../../../docs/studio/STUDIO_LAYOUT_SPEC.md)
