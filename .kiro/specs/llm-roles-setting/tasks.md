# LLM Roles Configuration Implementation Tasks

本文档将 LLM Roles 设置改造拆解为 4 个独立且循序渐进的执行阶段 (Phases)。

---

## Phase 1: Data Layer & Persistence 
**目标**: 完成后端 Schema 的调整、属性下沉及 `llm_roles.yaml` 的自动迁移，确保整个底层数据契约生效。

- [ ] 1.1 修改 `app/models/llm_config.py`，移除 `RoleEntry.temperature`，向 `RoleModelEntry` 新增 `temperature` (float|None) 和 `max_tokens` (int|None)。
- [ ] 1.2 编写并在后端初始化时挂载 `llm_roles.yaml` 的平滑迁移逻辑 (提取外层 `temperature` 注入内层各 Model，并删除外层记录)。
- [ ] 1.3 根据 API Keys Round 3 规范，确保 `ModelInfo.capabilities` 的类型为 `dict[str, Any]`。
- [ ] 1.4 在底层调用时，实现 `RoleModelEntry` 字段为 `None` 时，向上请求回退到系统全局默认值 `0.7` 的机制。
- **Acceptance**: `curl GET /api/llm/roles` 正常返回树状数据，原有的外层 temperature 成功消失，内层 model 带有参数。

---

## Phase 2: Layout & Skeleton (UI Foundation)
**目标**: 实现全新的右侧边栏和主内容区布局，建立 Skeleton 骨架屏以及角色卡片的初版渲染，先不介入复杂的拖拽逻辑。

- [ ] 2.1 引入并重构 `<LlmRolesTab>` 视图，建立 `flex-1` 主区域与 `w-64` 右侧模型列表栏。
- [ ] 2.2 开发并替换页面加载时的 `<Skeleton />` 骨架占位结构。
- [ ] 2.3 渲染 `<RoleCardList>`，每张卡片含 Role 名称及全局 `model_fallback` 开关 (UI只读或只发请求，不拖拽)。
- [ ] 2.4 在 Role 卡片内部循环渲染 `<ModelItem>`，在 Model 内渲染最基础的 Provider Tag 列表。
- [ ] 2.5 编写 `<ModelSettingsModal>` UI 组件，容纳 Temperature 和 Max Tokens 的表单，并在卡片上提供齿轮按钮触发。
- **Acceptance**: 用户可见双栏布局，点击 Role 能展开查阅 Model 层级，Model 齿轮能弹窗看到新的两个字段。

---

## Phase 3: DND & Interactions (Draggable Flow)
**目标**: 整合 `@dnd-kit/core` 实现 Role 内模型级别和 Provider 级别的二维拖拽重排序。

- [ ] 3.1 为 `<ModelFallbackChain>` 包装 `@dnd-kit` SortableContext，实现 Model Item 在 Role 内部的垂直拖拽。
- [ ] 3.2 为 `<ProviderChain>` 包装 `@dnd-kit` SortableContext，实现 Provider Tag 在特定 Model 内部的水平/垂直排序。
- [ ] 3.3 处理拖拽结束事件 (onDragEnd)，将排序结果更新到本地状态，并 debounce 后 PUT 到后端 `/api/llm/roles`。
- [ ] 3.4 实现右侧边栏向某个高亮 Role 快速 Append Model 的交互事件。
- **Acceptance**: 拖拽顺滑，不破坏嵌套层级结构，且松手后配置持久化成功。

---

## Phase 4: Testing Flow Orchestration (Capability Probing)
**目标**: 打通 Test Chain 并发控制，补全 Thinking 和 Token 边界的强校验，将探活状态回写至 UI 并驱动徽章显示。

- [ ] 4.1 在后端探活工具中，加入对声明 `reasoning: true` 的模型发送包含 `thinking` 协议块强校验请求的逻辑。
- [ ] 4.2 捕获 200/400 状态，正确地将 `thinking` 布尔值及获取到的 max_tokens 写入 `capabilities`，交由 `_persist_test_outcome` 持久化。
- [ ] 4.3 在前端建立一个总控 Test Chain Runner，实现：Model 间并发、单 Model 内 Provider 串行探活、全局最大并发不超过 3。
- [ ] 4.4 根据 `last_test_status` 渲染 🟢⚪🔴 状态圆点，并基于 `capabilities.thinking` 展示 🧠 状态标记 (点亮/划线)。
- **Acceptance**: 一键测试后，UI 实时跳动展示进度，最终清晰呈现 SDK 通信状况与 Thinking 特性是否被底层 Provider 阉割。