# Studio Copilot V1 Research

## 1. SDK 选型决策路径 (Round 1-5)

### 1.1 Round 1-2: agent SDK 各家对比
早期对比了 Anthropic SDK、Google Generative AI SDK 等，最初以模型调用与 Agent 运行时的差异为焦点，探讨了自带文件操作与工具调用的便利性，以及纯 Model SDK 在复杂工作流中的不足。主控介入后强调需要关注实际集成成本与政策风险。

### 1.2 Round 3: 中国大陆 policy 风险查证
详细查证后确认 Anthropic 具有严格的 50% 股权穿透封禁政策；Gemini 存在 Geo-block；而 Cursor 虽然提供了 TypeScript SDK，但缺乏原生 Python Binding 且与账号订阅强绑定。

### 1.3 Round 4: PM 5 条纠偏后修正
梳理了 PM 的纠偏反馈：a) 明确区分了 Model SDK（如 `openai`）与 Agentic SDK（如 `claude-agent-sdk`）；b) 评估了 Cursor 官方 SDK；c) 分析了 PM 个人承担 API key 风险 + 挂 VPN 的合规及运营可行性。当时的中间结论一度偏向使用 Cursor 为主推，因为误以为 Claude Code 无法切模型。

### 1.4 Round 5: ANTHROPIC_BASE_URL verify (关键转折)
主控指出漏点，经过验证确认 `claude-agent-sdk` 底层继承了 `anthropic` client 的特性，能够通过设置 `ANTHROPIC_BASE_URL` 路由至任意兼容 Anthropic Messages API 的第三方 backend（如 LiteLLM，DeepSeek，或 Z.ai 网关）。此发现彻底消除了 Claude SDK 强绑 Anthropic 后端导致的 Policy 封锁问题，V1 推荐重回 #1 顺位的 Claude Code。

## 2. 最终 V1 SDK + Backend 决策

| 项 | 选择 | 理由 |
|---|---|---|
| 主 SDK | `claude-agent-sdk` | PM agent 能力排序 #1，可通过 `ANTHROPIC_BASE_URL` 解锁 backend 灵活性，满足复杂 Agent 需求。 |
| Backend #1 | Claude API (Anthropic 直连) | 默认链路，直连无额外代理负担。 |
| Backend #2 | DeepSeek (Anthropic 兼容直切) | DeepSeek 原生提供 `https://api.deepseek.com/anthropic`，直接切换 Endpoint 即可，不需 LiteLLM 深度工具转换。 |
| Backend #3-4 V1.5 | Gemini + OpenAI | 需要 LiteLLM 深度介入完成协议转换（尤其是 tool_use schema），工时不可控，故延至 V1.5。 |

## 3. PM 拍板 V1 scope
> “决定了就用Claude code, 在配置项做几套backup, 1.Claude api; 2.deepseek api; 3.gemini api; 4.open ai api; 前端界面可以随时切换模型就和cursor ide一样”
V1 锁定 2 路 (Claude + DeepSeek)，并在 ModelPicker 中给 Gemini 和 OpenAI 留 2 个灰显的卡位 (标示 "V1.5 上线")。

## 4. Anthropic policy 风险接受
根据 Round 4 调研结果，针对 Anthropic 严格的封杀机制，公司层面不提供统一代理或企业实名 API，允许 PM 自带个人 Key + 自挂 VPN 承担个人责任。V1 架构通过灵活的 Base URL 设置，提供直切 DeepSeek 作为国内合规备选方案，从技术架构上避免强依赖高风险通道。

## 5. 工作量估算 (V1 = 2 路 后)
砍掉高风险转换（Gemini / OpenAI）后，重新估算总工时约在 13-15 小时以内，满足预算要求。

| Stage | 说明 | 工作量 |
|---|---|---|
| S1 LiteLLM proxy / 代理配置 | 配置文件仅含 Claude+DeepSeek，验证子进程拉起及端口管理 | 2.5 h |
| S2 Claude Agent SDK 接入 | 验证 base_url 注入机制，接入 SDK，实现长连接调度 | 3.5 h |
| S3 WebSocket endpoint | 编写 WebSocket 路由及 CopilotEvent Union 结构 | 2.0 h |
| S4 Frontend ModelPicker | 实现下拉菜单、置灰与状态逻辑，以及拆分子组件 | 3.5 h |
| S5 Settings Modal & 文件存储 | 开发配置填写界面与本地 `~/.studio/copilot.json` 读取 (chmod 600) | 2.0 h |
| S6 E2E smoke 测试 | 跑通 Claude 和 DeepSeek 的各一次真 Key 调用 | 1.5 h |
| **合计** | V1 (Claude + DeepSeek 2路 MVP) | **15.0 h** |