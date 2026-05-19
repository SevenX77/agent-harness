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

## 1. Tailwind 设计令牌与暗色模式
在构建桌面级复杂工具时，统一的设计系统是效率的保障。
- **基础库选型**: 抛弃内联 CSS 和手写类名，全面基于 `TailwindCSS v4` 配合无头组件库 `shadcn/ui`。
- **暗黑极客主题**: 默认只支持暗色模式（Dark Theme），营造专业生产力环境。
  - 背景底色: `bg-background` 使用 `zinc-950`，制造沉浸深度感。
  - 边框与分割线: `border-border` 使用 `zinc-800`。
- **视觉一致性约束**: 全局组件（包括浮动弹窗和侧边栏）圆角上限设定为 `rounded-md` (0.375rem)。严禁引入过度活泼的大圆角元素。

## 2. ReactFlow 画布样式覆写
原生的 `@xyflow/react` 深色主题仍带有较重的网页感，需在全局 `index.css` (通过 `@layer components`) 中彻底覆写：
- **节点主体**: 去除硬高亮，应用统一的背景令牌，增添轻微半透明磨砂效果（backdrop-blur）。
- **连接线 (Edges)**: 常态显示为浅灰色（如 `zinc-500`），在动画状态下（模拟数据流）渲染动态渐变色。
- **连接点 (Handles)**: 调小尺寸并使其处于隐藏半透状态，只有节点被 Hover 时激活显示，降低整体画布的视觉噪音。

## 3. 面板拖拽系统与自适应重绘
Studio 必须表现得像一个原生桌面应用，核心支撑是灵活的分屏拖拽框架。
- **基建组件**: 采用 `react-resizable-panels`。
- **区域分割**:
  - `Sidebar (AssetsPanel)` 宽 15%-25%。
  - `Main Workspace (SplitEditor)` 包含上下或左右分割的 Canvas 画布和 Monaco 代码编辑器。
  - `Right Drawer (Copilot / Golden)` 按需滑出。
- **重要 caveat**: 拖拽调节窗体大小时，必须确保 `ReactFlow` 和 `Monaco Editor` 及时监听 Resize Observer，触发自我边界更新 (`fit-to-screen` 和 `layout()`)，否则可能产生渲染撕裂。

## 4. Tauri Native API 桥接层最佳实践
将网页代码安全接入 Tauri 本地能力的护城河机制：
- 严禁业务组件中直接解构 `window.__TAURI__` 对象。
- 所有本地 I/O 和 Shell 调用，必须收敛并封装在统一的文件下：`apps/studio/frontend/src/lib/tauri.ts`。
- **兼容策略**: 为了便于直接使用 Vite `npm run dev` 在浏览器中纯粹调试 UI，桥接层必须提供运行时检测：如果不在 Tauri 沙盒中，所有针对本地文件读写的接口必须返回模拟成功数据（Mock fallback），而不是直接引发白屏崩溃。

## 相关 Spec
- [studio-uikit-redesign](../../.kiro/specs/studio-uikit-redesign/design.md)
