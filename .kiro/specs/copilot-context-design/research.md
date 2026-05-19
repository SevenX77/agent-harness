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

# Research: Copilot Context Design & Mention Mechanism

## 1. 业内方案调研

### 1.1 Cursor: @ File / @ Code 机制
- **怎么做的**: Cursor 在其 Chat 面板中，只要用户键入 `@`，即可弹出包含 `Files`, `Folders`, `Code`, `Docs` (Web) 的下拉菜单。用户选中后，该实体变成一个类似于 pill (胶囊) 的 UI 组件嵌在输入框中。在向大模型请求时，被 `@` 的文件内容会作为 `<context>` 标签嵌入。
- **能借鉴什么**: 将选中元素转化为 UI Pill 胶囊是非常直观的做法，防止用户不小心破坏掉引用路径字符串。我们的 MentionMenu 也应当采用分门别类 (Files/Phases) 的设计。

### 1.2 GitHub Copilot Chat (VS Code): Context Variables
- **怎么做的**: 在 VS Code 中使用 `#`（例如 `#file`, `#selection`, `#terminalLastCommand`）来附加隐式上下文，而使用 `@` 来指定 Agent（例如 `@workspace`, `@vscode`）。
- **能借鉴什么**: 我们当前 PM 要求使用 `@` 来引用节点和文件。这更符合常规的 Mention 习惯。我们应当借鉴 `#terminalLastCommand` 的思路，允许用户 `@last_compile_error` 从而把上一次的错误信息一键囊括进 Prompt。

### 1.3 渐进式披露 (Progressive Context Disclosure) 方法论
- **怎么做的**: 大型复杂系统（如 LangChain 复杂的 Agent 调度）在打 Prompt 时，通常将其分为 Base System Prompt（系统人设、格式规定）、Persistent Knowledge（核心依赖库规范）、Episodic Memory（过去几轮的对话）和 Situational Context（用户当前光标在哪、选了什么）。
- **能借鉴什么**: 必须在后端做分层组装。前端不需要把文件的字符串拼在请求里，前端只需要在 payload 里传 `mentions: ["phase:agent_planner", "file:script/my_tools.py"]`，真正读盘和组装在后端进行，减轻 WebSocket 载荷。

## 2. 现仓库 Codebase 状态

通过 `file:line` 对当前 codebase 进行扫描：

- **前端输入框**: `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:195` 处使用了普通的 HTML `<textarea>`（或者包裹过的简单 Textarea 组件），并设置了 `placeholder="Use '@' to mention nodes..."`。目前**没有任何拦截键盘输入、渲染 Mention 菜单的逻辑**，是 100% 的空壳。
- **上下文状态同步**: `apps/studio/frontend/src/hooks/useCopilotContext.ts` 和 `Workspace.tsx:65` 处，已经有一个通过 Context 传递的机制。目前 `selected_node_id`, `selected_node`, 和 `lint_status` 被打包传递给了 Copilot，这意味着前端其实已经有了全局被点击节点的数据流转，只差绑定到输入框的 `@` 自动填充动作。

## 3. 前后端 Payload schema (本 spec 推荐)

在传递聊天消息时，建议的前后端接口结构如下：

```typescript
interface ChatMessagePayload {
  message: string;
  mentions: Array<{
    type: "file" | "phase" | "edge_context" | "system_error";
    id: string; // 例如 "script/tool.py" 或 "node_planner"
  }>;
  implicitContext: {
    activeSkillId: string;
    selectedNodeId?: string;
    hasCompileErrors: boolean;
  }
}
```

后端系统级 Prompt 组装流的可能形态：
1. **Layer 1**: 永远加载 `WORKSPACE_AND_FILE_SPEC` 与当前 Skill 的基础 `<metadata>`。
2. **Layer 2**: 如果 `implicitContext.selectedNodeId` 有值，附上该 Node 的 YAML/Markdown 源码片段。
3. **Layer 3**: 遍历 `mentions`，对于 type="file"，将其全文放入 `<referenced_file name="...">` 标签；对于 type="system_error"，把近期的 Trace log 附上。

## 4. 关键技术决策点

在后续 Design 阶段需拍板：
1. **Mention 文本框实现技术**: 是使用轻量级的 `react-mentions` 库包裹原生的 Textarea，还是引入较重的但更强大的 `tiptap` 富文本编辑器框架来实现胶囊效果？
2. **Context 获取权**: 后端组装 Context 时，如果涉及的文件用户在前端正在编辑 (未保存的脏数据)，前端是否需要将所有 Dirty Files 一并作为 payload 发送给后端，还是后端主动调一次“获取当前在途数据”的同步逻辑？
3. **Token 防爆限制**: 如果用户丧心病狂地 `@` 了一堆大文件，后端如何决定截断策略（按优先级截断，还是抛出硬性错误提示框）？

## 5. 推荐方向

我个人的设计倾向：
- 采用 `react-mentions` 或类似的轻量级包裹方案，不要上重型富文本编辑器，保持极客感和轻快。
- Mentions 纯走后端解析：前端提交 `[{"type": "phase", "id": "router"}]`，由 Python 引擎层（因为具备完全的文件访问权和 AST 解析能力）去拼装具体的 Prompt 片段。这使得将来即使切换为纯 CLI 形态，这套 Mention 组装逻辑也依然可用。

## 相关文档
- [STUDIO_LAYOUT_SPEC.md](../../../docs/studio/STUDIO_LAYOUT_SPEC.md)
