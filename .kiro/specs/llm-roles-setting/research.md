# LLM Roles Configuration Research

## 1. 现状代码分析

### 1.1 Backend Schema (`app/models/llm_config.py`)
- **现状 RoleEntry**: 目前包含 `temperature: float = 0.7` 和 `model_fallback: bool`。`temperature` 的作用域过大，当 Role 内 fallback 从 Claude (温和) 切换到 DeepSeek (激进) 时，共享同一温度不符合业务直觉。
- **现状 ProviderCredential**: 已经支持通过 `_persist_test_outcome` 写回探活状态。`available_models` 列表包含 `ModelInfo`。
- **现状 ModelInfo.capabilities**: (根据 API Keys Round 3 决议) 已变更为 `dict[str, Any]`，这为无缝写入 `thinking`, `max_context_tokens` 提供了灵活的温床。

### 1.2 Endpoint 现状 (`app/routers/llm.py`)
- `POST /api/llm/providers/test`: 目前仅发送基础 1-token 探活，并捕获状态码。尚未携带 `thinking` 相关特征进行强能力探测。

## 2. 探测可行性分析

### 2.1 Max Tokens 提取方案
- **Anthropic API**: 在其响应头或特定的 Vendor Metadata 中，通常没有直接的 max tokens 上限暴露。需要从预置的静态能力表 fallback。
- **OpenRouter**: 可通过 `/api/v1/models` 端点拉取全量模型的 `context_length` 和 `max_completion_tokens`，然后缓存。
- **结论**: Token 提取将采用 **混合策略**，优先读取 API HTTP 响应 (若支持)，次选调用特定的 Provider Metadata Endpoint (如 OpenRouter)，最后兜底使用静态文件 (`llm_roles.yaml` 的 `max_input_tokens` 字段)。

### 2.2 Thinking 能力探测机制 (UX 动线推导)
**UX 动线分析**:
1. 用户在侧边栏看到 `Claude 4.6 Thinking` 模型，将其拖入 Role 中。
2. 用户展开 `ModelSettingsModal`。由于模型天生标榜 Thinking，用户期望它直接生效，而不是需要繁琐地再点一次 "Enable Thinking" 开关。
3. 当用户点击 Role 卡片头部的 **"Test Chain"** 按钮时，系统依次探活。
4. **异常情况**: 虽然用户选择了 Thinking 模型，但配置的某个下游代理 Provider (如某个劣质的中转 API) 并未实装 Anthropic 的 `thinking` block 参数，导致带 `thinking` 的请求被直接 400 拒绝。
5. **用户感知**: 用户必须在 UI 上明确看到这个 Provider 到底是否真实支持 Thinking (例如通过一个带脑子图标 🧠 的 Badge 标示)，而不是在最终运行时才发现退化或崩溃。

**探测策略推导：混合强校验 (推荐)**
- **触发条件**: 从 `llm_roles.yaml` 读取模型本身的静态元数据 (如 `reasoning: true` 或代号后缀为 `T`)。
- **探测执行**: 
  - 如果模型被标记为支持 reasoning，`POST /providers/test` 必须构造携带 `thinking` 协议特征 (如对于 Anthropic: `thinking: {type: "enabled", budget_tokens: 1024}`) 的 1-token Chat 请求。
  - 如果 Provider 返回 **200 OK**，则将 `thinking: true` 写入 capability 字典。
  - 如果 Provider 返回 **400 Bad Request** 但常规 ping (不带 thinking) 成功，则记录 `thinking: false`，UI 会将对应 Provider Tag 上的 🧠 图标划掉。
- **总结**: 探测依赖强请求校验，避免伪造能力，结果存储在 `provider-model` 级。

## 3. UI 交互层调研
- **@dnd-kit/core**: 非常适合这种两级深度的拖拽场景。推荐在 RoleCard 层和 ModelItem 层分别使用独立的 `SortableContext`。为防止滑动冲突，建议使用 drag handle (拖拽手柄) 触发拖动。
- **Promise 节流**: 为了实现 "Model 并发，Provider 串行" 且总并发 ≤ 3，前端可以引入 `p-limit` 库或自己实现一个轻量级的限流 Semaphore 控制探活并发池。