# Studio Copilot V1 Requirements

## 1. 项目背景
项目旨在为 Studio 引入一个强大的 Copilot 助手。经过多次架构与合规调研，PM 拍板决定：“决定了就用Claude code, 在配置项做几套backup, 1.Claude api; 2.deepseek api; 3.gemini api; 4.open ai api; 前端界面可以随时切换模型就和cursor ide一样”。考虑到时间约束 (<16h) 以及工具调用（tool_use）跨协议转换的复杂性，V1 Scope 锁定为 **Claude + DeepSeek 2 路** 方案。Gemini 和 OpenAI 仅作为卡位在 UI 展示，并在底层架构中移除 LiteLLM 代理，一切转换与路由依赖端点配置，具体多平台网关实现延至 V1.5。

## 2. User Stories
- **US1.a (常驻 panel)**: 作为 PM，我希望 Copilot 是 Studio 主界面的常驻 side panel，永远在右侧（以免与左侧导航冲突），我无需手动召唤。
- **US1.b (Agent 全能)**: 作为 PM，我希望 Copilot 能直接读 workspace 文件 / 编辑文件 / 跑 Bash 命令，不只是 chat。每次工具调用要在 chat UI 显示（例如 “正在读 X 文件”），让我能看清 Copilot 在做什么。
- **US1.c (自动 context 注入)**: 作为 PM，我希望 Copilot 自动知道我当前在 Studio 哪个 view (WelcomeScreen / 编辑 / Compile / Validate / Predict / Run / Publish)，并把当前 view 的 context (SKILL.md / phase config / trace JSON 等) 自动塞进 prompt — 我不需要手动 @ 文件。
- **US1.d (业务聚焦但不拒通用问题)**: 作为 PM，我希望 Copilot 默认理解我当前在调试 Studio 的某个 SKILL/phase/trace，但同时也能回答跟 Studio 无关的通用问题 (例如 Java 关键字)，不要硬拒绝。
- **US2**: 作为 PM，我想像使用 Cursor IDE 一样，在界面上的下拉菜单中随时切换 LLM backend（Claude 和 DeepSeek）。
- **US3**: 作为 PM，我想在一个专门的 Settings 模态框中配置各个 backend 的 API key。对于 V1，我期望能填入 Claude 和 DeepSeek 的 key，而看到 Gemini 和 OpenAI 置灰标示“V1.5 上线”。

## 3. Acceptance Criteria (V1 = 2 路 closed)
- **AC1**: 用户在 ModelPicker 选 Claude 时，Copilot 的请求直接路由到 Anthropic 官方 API。
- **AC2**: 用户在 ModelPicker 选 DeepSeek 时，Copilot 的请求路由到 DeepSeek 原生的 Anthropic 兼容端点（不走 LiteLLM 转换）。
- **AC3**: 切 model 时当前会话**重起新 session**，清空之前的历史，并在 UI 上提示“切换 backend 会重新开始对话”。
- **AC4**: 未配 key 的 backend 在 ModelPicker 灰显且不可选，Hover 时有 tooltip 提示“请先在 Settings 配置 API Key”。
- **AC5**: V1.5 的卡位 (Gemini / OpenAI) 必须处于 disabled grey out 状态，并且带有标签标示“V1.5 上线”，且不可点击。
- **AC6**: 设置的 API Keys 保存在本地文件 `~/.studio/copilot.json` 中，并且权限设置为 `600`。
- **AC7 (always-on)**: Copilot panel 在任何 Studio view 都可见，panel 不能被关闭（V1 不实现 collapse，V1.5 加）。
- **AC8 (Agent 全能)**: `claude-agent-sdk` 启用 Read/Write/Edit/Bash 工具集，`permission_mode='acceptEdits'` 自动接受编辑。
- **AC9 (tool_use UI 展示)**: 每次 Copilot 调用工具，ChatBubble 显示 "正在 [Read|Edit|Write|Bash] [文件名 / 命令]"，文件 Edit 显示 unified diff。
- **AC10 (自动 context 注入)**: view 切换时，前端 hook 检测变化 → 调用 backend `POST /api/skills/{skill_id}/copilot/context` 更新 context → 后端在下次 ClaudeSDKClient query 前 prepend 到 system prompt 或 user message。
- **AC11 (聚焦但不拒通用问题)**: System prompt template 必须明确写 "聚焦 Studio 上下文，但允许任何通用问题不要拒答"。
- **AC12 (view 切换 chat 历史保留)**: view 切换不重起 session（不要清 chat history）；只有切 backend (Claude ↔ DeepSeek) 才重起。

## 4. Out of Scope (V1 不做, 留 V1.5)
- LiteLLM 完整的 Gemini / OpenAI 协议转换及子进程拉起。
- 历史会话落盘持久化 (V1 仅限 in-memory，刷新即丢)。
- Tauri keyring 加密凭据 (V1 妥协使用文件 `chmod 600`)。
- per-skill 多会话管理 (V1 仅支持一个 skill 一个 session)。
- Copilot panel collapse / minimize 按钮 (V1 always-on 不可关，V1.5 加 collapse)。
- Tool use 一键回滚 (V1 显示 diff 不回滚，V1.5 加)。
- 跨项目 Copilot 上下文共享 (V1 一个 workspace 一个 Copilot session)。
- Copilot 主动 push (V1 只 user-initiated 后续被动 reply，V1.5 探索主动提示)。