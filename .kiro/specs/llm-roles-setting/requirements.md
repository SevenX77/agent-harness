# LLM Roles Configuration Requirements

## 1. 业务背景 (Context)
当前 Studio 的 LLM 配置过于平铺，所有 Provider 和 Model 被揉捏在一个全局下拉框或简单的 Role-to-Model 映射中。随着 `thinking` (推理模式)、`max_tokens` 约束以及多厂商 SDK (OpenAI/Anthropic 兼容) 的激增，现有的 UI 与数据结构已无法满足精细化、多级降级的编排需求。本需求旨在重塑 LLM Roles 设置，下沉控制粒度至 Model，并提供直观的双栏 UI 与 Test Chain 探活能力。

## 2. 核心需求矩阵 (Requirements)

| ID | 需求描述 (Description) | 验收标准 (Acceptance Criteria) |
|---|---|---|
| **REQ-01** | **SDK 兼容性探测**<br>系统必须能向 Provider 发送极简 Chat Probe (1-token)，验证底层 SDK 协议层的连通性。 | 1. `POST /api/llm/providers/test` 必须支持多协议请求。<br>2. 正确返回 `ok`, `invalid_key`, `timeout` 等状态码。 |
| **REQ-02** | **Max Tokens 边界探测**<br>探活时需动态拉取并归一化底层模型的 `max_context_tokens` 和 `max_output_tokens` 阈值。 | 1. 探测结果必须持久化到 `ProviderCredential.available_models[].capabilities` 中。 |
| **REQ-03** | **Capability 扩展探测 (含 Thinking)**<br>系统必须探测模型在特定 Provider 下是否支持 `thinking` 模式及 `function_calling` 等能力。 | 1. 探测数据必须写入 provider-model 维度的 capabilities 字典。<br>2. (UX决定) 对声明支持 reasoning 的模型，执行强校验探活。 |
| **REQ-04** | **多 UI 模式双栏布局**<br>废弃原有的顶部下拉框切换模式，采用左侧平铺 Role Card、右侧固定 Available Models 侧边栏的交互布局。 | 1. 提供清晰的左主右副视图。<br>2. 支持从侧边栏快速 Add/Append 模型到指定 Role。 |
| **REQ-05** | **概念视图翻转 (双级嵌套)**<br>Role Card 内部必须展示 `Model Fallback Chain`，而每个 Model 内部嵌套展示 `Provider Chain`。 | 1. 树状层级明确，状态下沉，模型作为第一级兜底，Provider 作为第二级兜底。 |
| **REQ-06** | **配置粒度下沉 (Model Settings)**<br>将原 Role 级别的生成参数下沉至 Model 级，允许针对不同模型设置不同的参数。 | 1. `temperature` 和 `max_tokens` 必须在 ModelItem 的 Settings Modal 中配置。<br>2. 默认值均为 `None`，调用时若为空，则回退到系统全局默认值 (如 0.7)。 |
| **REQ-07** | **双级拖拽排序 (DND)**<br>允许用户通过拖拽自由调整 Model 的降级顺序，以及 Model 内部 Provider 的降级顺序。 | 1. 集成 `@dnd-kit/core`。<br>2. 拖拽时不得触发不必要的全页面重绘。 |
| **REQ-08** | **Test Chain 聚合探活**<br>在 Role 卡片级别提供一键测试完整降级链路的能力，并以圆点可视化各节点的连通性。 | 1. Model 之间并发探活，单个 Model 内 Provider 之间串行探活。<br>2. 全局限制最大并发数为 3 以防 429 Rate Limit。<br>3. 探活状态 🟢⚪🔴 映射到 Provider Tag。 |
| **REQ-09** | **Fallback 总控制与加载体验**<br>必须提供 Role 级别的 `model_fallback` 统一开关，及页面初始渲染时的骨架屏。 | 1. Role 头部保留 `model_fallback` 总开关。<br>2. 加载阶段显示 `shadcn <Skeleton />`。 |