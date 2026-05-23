# LLM Roles Configuration Implementation Tasks

本文档将 LLM Roles 设置改造拆解为 5 个独立且循序渐进的执行阶段 (Phases)。

## Frontend UI Guardrails (适用于所有 UI Phase)

- 修改 `apps/studio/frontend` 前先阅读 `docs/development/FRONTEND_UI_SPEC.md` §2，并搜索 `apps/studio/frontend/src/components/ui/` 是否已有对应 shadcn/Radix wrapper。
- 所有交互 primitive 使用本地 `@/components/ui/*`：Dialog 用 `ui/dialog.tsx`，Settings 表单用 `ui/field.tsx` + `ui/input.tsx`，加载态用 `ui/skeleton.tsx`，说明用 `ui/tooltip.tsx`，长列表用 `ui/scroll-area.tsx`，二态开关用 `ui/switch.tsx` 或现有 Settings 约定控件。
- 新增样式必须使用语义 token 和现有组件 variant；不得 hardcode hex 或 Tailwind 具体色值。圆角不得超过 `rounded-md`。
- LLM Roles 作为 Settings 页，默认采用和 API Keys 一致的 auto-save：变更后 debounce 保存，并显示 `Pending` / `Saving` / `Saved` / `Save failed`。不要新增独立 `Save` 按钮。
- 所有用户可见 UI 完成前必须运行 Studio 前端并手动检查：打开 Settings → LLM Roles、切换 Role、打开/取消/提交 Model Settings Dialog、append/remove/reorder、Test Chain、桌面宽度和窄面板宽度。

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
**目标**: 实现符合 Studio UI 规范的 LLM Roles 双栏基础布局、auto-save 状态、Skeleton、Role/Model/Provider 层级与 Model Settings Dialog，先不介入复杂拖拽逻辑。

- [ ] 2.1 拆分 `LlmRolesTab`，保持一文件一主组件。
  - Modify: `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx`，保留为 tab orchestrator。
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCardList.tsx`
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCard.tsx`
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/ModelItem.tsx`
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/ProviderTag.tsx`
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/AvailableModelsSidebar.tsx`
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/LlmRolesSkeleton.tsx`
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/ModelSettingsDialog.tsx`
  - Create: `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleSaveStatusBadge.tsx`
- [ ] 2.2 建立 Roles auto-save 管线，移除手动 Save 依赖。
  - Create: `apps/studio/frontend/src/hooks/useDebouncedRolesSave.ts`，复用 `useDebouncedCredentialsSave` 的状态语义或抽取共享 debounce save helper。
  - Modify: `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx`，`onRolesDataChange` 后 queue save `/api/llm/roles`。
  - Modify: `apps/studio/frontend/src/components/studio/settings/types.ts` 和 `SettingsPageContent.tsx`，向 `LlmRolesTab` 传入 `rolesSaveStatus`，移除 `onSaveRoles` / `rolesDirty` 的 UI 语义。
  - Modify: `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx`，在 `SectionTitle.trailing` 渲染 `RoleSaveStatusBadge`，不渲染独立 `Save` 按钮。
- [ ] 2.3 实现响应式双栏布局。
  - 主容器限制在 Settings 内容区内，可放宽到 `max-w-5xl` / `max-w-6xl`。
  - 主列使用 `min-w-0` 并通过 `ScrollArea` 支持上下浏览 Role cards；`SectionTitle` 必须放在这个 Roles 主列 `ScrollArea` 内，和 Role cards 作为一个整体滚动。
  - 右侧模型库与 Roles 主列同级，不嵌套在主列内容里，也不和 `SectionTitle` 组成外层 header/main 兄弟结构。
  - 右侧模型库不使用外层 `Card`，使用 title + 本地 `Input` 搜索框 + `ScrollArea`；`ScrollArea` 隐藏 scrollbar 且不保留内侧 gutter。数据源来自 `credentials.providers[*].available_models`，不使用 `RolesData.models` 缩写；OpenRouter 等聚合 provider 的 `~vendor/model` / `vendor/model` 在写入和展示侧归一化为 canonical model id，同一 canonical id 合并多个 provider label，并保留原始 provider model id 供调用。跨 provider 模型等价关系只通过 exact canonical id 或显式 alias metadata / curated alias map 合并，不靠模糊搜索自动合并 `latest`、dated snapshot、minor version、fast variant。搜索按 vendor、exact model id、provider label 过滤，并支持大小写/标点不敏感匹配。桌面端 sticky 固定在页面右侧，列宽使用 `minmax(14rem, 20vw)` 并在超宽时封顶，不固定占用 `18rem`；窄宽度下右侧模型库折到下方；不得横向挤压 Role/Model 文本。
  - 长列表包装 `ScrollArea`，不要让页面整体产生不可控横向滚动。
- [ ] 2.4 使用 `Skeleton` 替换纯文本加载态。
  - `LlmRolesSkeleton` 必须使用 `@/components/ui/skeleton`。
  - Skeleton 结构要对应双栏布局：Role card placeholder + Model item rows + sidebar model rows。
- [ ] 2.5 渲染 Role/Model/Provider 层级。
  - RoleCard 平铺展示所有可见 Role，不使用顶部标签切换。
  - RoleCard 头部展示 Role 名称、active model 摘要、`model_fallback` Switch、Test Chain Button placeholder。
  - ModelItem 展示模型代号、active badge、provider chain、settings icon button。
  - RoleCard 底部提供 Add model 控件；ModelItem 下方提供 Add provider 控件。
  - ProviderTag 展示 provider code、availability status、capability badge placeholder；状态说明通过 Tooltip/aria-label 提供，不只靠颜色。
- [ ] 2.6 实现 `ModelSettingsDialog`。
  - 必须使用 `@/components/ui/dialog`、`FieldSet` / `FieldGroup` / `Field` / `FieldLabel` / `FieldDescription`、`Input`、`Button`。
  - Temperature / Max Tokens 的 input `value` 同步真实 draft 值；空字符串表示继承默认。
  - 默认说明写在 `FieldDescription`（例如 `Blank uses system default 0.7`），placeholder 只写空状态提示，不承载真实默认值。
  - Dialog cancel 不写回；提交后更新 draft 并触发 auto-save。
- [ ] 2.7 更新组件测试。
  - Test: `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.test.tsx`
  - 覆盖：loading skeleton、无 Save 按钮、save status badge、dialog open/cancel/submit、空值默认说明、provider status tooltip/aria-label。
- **Acceptance**:
  - `cd apps/studio/frontend && npm run test -- LlmRolesTab.test.tsx` 通过。
  - `cd apps/studio/frontend && npm run typecheck` 通过。
  - 手动打开 Settings → LLM Roles，桌面和窄宽度下无穿模、截断、横向错位；Model Settings Dialog 可打开、取消、提交，变更触发 auto-save 状态。

---

## Phase 3: DND & Interactions (Draggable Flow)
**目标**: 整合 `@dnd-kit/core` 实现 Role 内模型级别和 Provider 级别的二维拖拽重排序。

- [ ] 3.1 引入 DND 依赖。
  - Modify: `apps/studio/frontend/package.json`
  - Add dependencies: `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`
  - Run: `cd apps/studio/frontend && npm install`
- [ ] 3.2 为 `<ModelFallbackChain>` 包装 `DndContext` + `SortableContext`，实现 Model Item 在 Role 内部垂直排序。
  - Drag handle 使用 lucide `GripVertical` 图标按钮，提供 Tooltip 和 `aria-label`。
  - 拖拽中保持 ModelItem 高度稳定，不因 hover/active 状态改变布局尺寸。
- [ ] 3.3 为 `<ProviderChain>` 包装独立 `SortableContext`，实现 ProviderTag 在特定 Model 内部排序。
  - ProviderTag 的拖拽只影响当前 Model 的 provider list，不跨 Model 移动。
  - 键盘 sensor 和 pointer sensor 都要可用；键盘排序后同样触发 draft update。
- [ ] 3.4 处理 `onDragEnd`。
  - 复用 `role-utils.ts` 中的 `moveModelInRole` / `moveProviderInRole` 或补齐纯函数。
  - 更新本地 draft 后通过 Phase 2 的 roles auto-save queue 写回 `/api/llm/roles`；不要绕过 save status 直接 PUT。
- [ ] 3.5 实现 RoleCard 内 Add model 与 ModelItem 内 Add provider。
  - AvailableModelsSidebar 从 provider test/manual probing 写回的 available models 聚合 tested models，按 vendor 分组；model card 使用 full-width card surface，hover 只改变背景色，selected 保留 primary ring 高亮；thinking 能力使用 `Badge` + lucide `Brain` 图标 + tiny `Thinking` 文本，窄宽度下可隐藏文字；model card 点击后仅展开原先被截断的 provider label 文本，不额外展示 provider id/detail 区块。
  - RoleCard 内 Add model 控件从缺失模型中选择并追加到该 Role，触发 auto-save。
  - ModelItem 内 Add provider 控件从该模型声明的缺失 provider 中选择并追加到该 Model，触发 auto-save。
- [ ] 3.6 更新测试。
  - Test: `apps/studio/frontend/src/components/studio/settings/role-utils.test.ts`（如不存在则创建）
  - Test: `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.test.tsx`
  - 覆盖：model reorder、provider reorder、append model、不可追加状态、auto-save queue 被调用。
- **Acceptance**:
  - `cd apps/studio/frontend && npm run test -- LlmRolesTab.test.tsx role-utils.test.ts` 通过。
  - `cd apps/studio/frontend && npm run typecheck` 通过。
  - 手动拖拽 Model 和 Provider，松手后层级不乱、状态显示 Saving/Saved、刷新后顺序保持。

---

## Phase 4: Testing Flow Orchestration (Capability Probing)
**目标**: 打通 Test Chain 并发控制，补全 Thinking 和 Token 边界的强校验，将探活状态回写至 UI 并驱动徽章显示。

- [ ] 4.1 在后端探活工具中，加入对声明 `reasoning: true` 的模型发送包含 `thinking` 协议块强校验请求的逻辑。
- [ ] 4.2 捕获 200/400 状态，正确地将 `thinking` 布尔值及获取到的 max_tokens 写入 `capabilities`，交由 `_persist_test_outcome` 持久化。
- [ ] 4.3 在前端建立总控 Test Chain Runner。
  - Create: `apps/studio/frontend/src/hooks/useRoleTestChainRunner.ts`
  - Model 间并发，单 Model 内 Provider 串行探活，全局最大并发不超过 3。
  - 如继续采用 `p-limit`，需在 `apps/studio/frontend/package.json` 显式新增依赖；否则在 hook 内实现一个有单测覆盖的小型 limiter。
- [ ] 4.4 渲染状态与能力标识。
  - Modify: `ProviderTag.tsx`
  - `last_test_status` 使用可访问 `StatusDot` + Tooltip + aria-label 表达 `Connected` / `Untested` / `Failed`，不得使用裸 emoji。
  - `capabilities.thinking` 使用 `Badge` + lucide `Brain` 表达可用/不可用；disabled 状态必须有 tooltip 文案。
  - 所有状态颜色使用语义 token 或新增的设计系统 variant，不使用 `bg-green-*` / `text-red-*` 等具体色值。
- [ ] 4.5 Test Chain Button 状态。
  - Button 使用 lucide `Play` / `Loader2`。
  - 运行中禁用重复点击，显示进度摘要；失败后保留错误摘要 Tooltip。
  - 完成后通过 credentials/capabilities refresh 驱动 UI 更新，不需要用户手动刷新。
- [ ] 4.6 更新测试与 e2e。
  - Test: `apps/studio/frontend/src/hooks/useRoleTestChainRunner.test.ts`
  - Test: `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.test.tsx`
  - E2E: `apps/studio/frontend/tests/e2e/llm-config-v2.spec.ts`
  - 覆盖：并发上限、provider 串行顺序、status/capability badge、失败 tooltip、重复点击 disabled。
- **Acceptance**:
  - `cd apps/studio/frontend && npm run test -- useRoleTestChainRunner.test.ts LlmRolesTab.test.tsx` 通过。
  - `cd apps/studio/frontend && npm run playwright -- tests/e2e/llm-config-v2.spec.ts` 通过或记录明确不可运行原因。
  - 手动点击 Test Chain，运行中/成功/失败状态都可见且不依赖颜色单独表达。

---

## Phase 5: Final Frontend Verification
**目标**: 在合并前完成 Studio UI 规范要求的自动化与人工验收。

- [ ] 5.1 运行自动化检查。
  - Run: `cd apps/studio/frontend && npm run typecheck`
  - Run: `cd apps/studio/frontend && npm run lint`
  - Run: `cd apps/studio/frontend && npm run test`
  - Run: `cd apps/studio/frontend && npm run build`
- [ ] 5.2 运行 Studio 并人工检查。
  - Standard startup: `cd apps/studio/tauri && cargo tauri dev`
  - 打开 Settings → LLM Roles。
  - 检查桌面宽度和窄面板宽度。
  - 点击每个 touched workflow：Role 切换、Model Settings Dialog 打开/取消/提交、model_fallback toggle、append model、remove model/provider、Model reorder、Provider reorder、Test Chain success/failure。
- [ ] 5.3 在 PR 或交付说明中报告人工验证结果。
  - 必须说明实际运行方式、检查过的交互路径、未覆盖路径及原因。
- **Acceptance**: 自动化检查通过；人工验证覆盖主要成功路径和明显取消/错误状态；没有横向溢出、文本穿模、不可访问的 icon-only 控件。
