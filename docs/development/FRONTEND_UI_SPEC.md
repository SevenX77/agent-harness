---
status: Living
target_goal: "确立 Studio 研发端的全局 UI/UX 基准，包含样式库、面板交互与 Tauri 桥接标准"
linked_code_paths:
  - apps/studio/frontend/src/index.css
  - apps/studio/frontend/src/components/ui/
linked_specs:
  - .kiro/specs/studio-uikit-redesign/
last_updated: 2026-05-19
---

# 前端与 UI 规范 (Frontend UI Spec)

## 1. Tailwind 设计令牌与暗色模式适配
- **基础库**: 全局放弃早期手写的杂乱 CSS，统一由 `TailwindCSS` 与 `shadcn/ui` 托管。
- **暗黑沉浸**: Studio 定位为极客生产力工具，采用纯正的 Dark 模式。背景色使用 `bg-background` (`zinc-950` 级别)，面板边框使用 `border-border` (`zinc-800` 级别)。
- **一致性控制**: 无论是在 React Flow 节点还是右侧的 Copilot 侧边栏，边框圆角统一为 `rounded-md` (0.375rem)，杜绝圆滑边框与极客风格产生割裂。

## 2. React Flow 画布基础样式重写
`@xyflow/react` 默认的主题在我们的深色模式下过于突兀。
必须在 `index.css` 的 `@layer components` 中覆写：
- `react-flow__node`: 消除默认白底，应用我们的背景和阴影类。
- `react-flow__handle`: 连线的接驳点需调小并匹配我们的主色调。
- 画布底纹 (Background) 必须设置为极其暗淡的 `Dots`，以减少视觉噪音。

## 3. 面板拖拽系统
整个屏幕必须是响应式的分栏系统（基于 `react-resizable-panels`）。
- **左侧**: 极窄的工具条 (Toolbar) + 可收起的资源树 (AssetsPanel)。
- **中侧**: 分割区 (SplitEditor)，通常是上方画布，下方代码，两者可通过中部的 Handle 自由拉伸。
- **右侧**: 默认隐藏，当触发 Copilot 或打磨 Golden 时滑出。
确保拖动顺滑，不破坏 Monaco 编辑器和 React Flow 画布的自适应宽高度计算。

## 4. Tauri Native API 桥接层最佳实践
前端代码中绝不允许出现零散的 `window.__TAURI__` 调用。
一切系统级操作必须经过 `apps/studio/frontend/src/lib/tauri.ts` 封装的契约方法。
当应用在纯 Web 模式下开发时 (如 `npm run dev`)，桥接层自动 Mock 返回假数据以保证 UI 不崩溃。

## 相关 Spec
- [studio-uikit-redesign](../../.kiro/specs/studio-uikit-redesign/design.md)
