---
status: Living
target_goal: "前端模块化组织原则 + UI 组件基准规范 + 画布/拖拽/Tauri 桥接最佳实践"
linked_code_paths:
  - apps/studio/frontend/src/components/studio/Panels.tsx
  - apps/studio/frontend/src/components/studio/SettingsPage.tsx
  - apps/studio/frontend/src/index.css
  - apps/studio/frontend/src/components/ui/
  - apps/studio/frontend/src/lib/tauri.ts
linked_specs:
  - .kiro/specs/_archive/studio-uikit-redesign/
last_updated: 2026-05-19
---

# 前端模块化与 UI 规范 (Frontend Modularity & UI Spec)

## 1. 前端模块化组织原则 (Module Hygiene)

在过往的快速迭代中，前端堆积了严重的“多组件挤一文件”反模式（如 `Panels.tsx` 超过 500 行，容纳了 5 个完全不相关的面板组件）。为了保障可维护性，从现在起确立以下重构与开发红线：

### 1.1 一文件一组件 (Single Component per File)
- **核心原则**: 每个 `.tsx` 文件应当只默认导出一个（或命名导出一个）核心的 React 组件。
- **例外豁免**: 仅供该核心组件局部使用的子渲染函数（如 `function FileRow()` 仅在 `AssetsPanel` 中被使用）或微型组件（总行数 < 50 行），允许生存在同一个文件中。但严禁在同一文件中导出（Export）多个平级的业务组件。

### 1.2 物理阈值拦截 (warning, 非阻塞)
- **200 行软提示**: 开发者应考虑是否混入了过多状态管理或子级渲染逻辑。
- **400 行 ESLint warning**: 文件突破 400 行时, ESLint 触发 warning (编辑器红线提示), 但**不 阻塞 PR / 不 build fail**。已存在的超阈值文件作为技术债清单 (见 §1.4) 排期重构, 不需立即修复 。
- **理由**: 强制 error 业界少数派 (一旦触发开发者倾向加 `/* eslint-disable max-lines */` 注释 escape, 反成反模式), warning + code review 把关是业界主流 (参考 Material UI / Airbnb / Google style guide)。
- **后续**: 实际 ESLint 配置 (`eslint.config.js` 加 `max-lines: ['warn', 400]`) 跟拆代码任务 一起实施。

### 1.3 拆分与目录策略 (Feature-Based Directory)
我们采用按 **Feature (功能域)** 划分的目录结构，拒绝扁平的 `components/` 堆砌：
- 当一个文件需要拆分时，应原地升级为以功能命名的目录，例如将 `Panels.tsx` 拆分为：
  ```
  components/studio/panels/
  ├── index.ts
  ├── AssetsPanel.tsx
  ├── InputPanel.tsx
  └── PropertiesPanel.tsx
  ```
- **文件命名**:
  - React 视图组件（包含 JSX）：必须使用大驼峰 `PascalCase.tsx`。
  - 纯逻辑 / 工具 / Hooks 文件：使用烤肉串格式 `kebab-case.ts`。

### 1.4 反模式示例 (需优先重构清单)
以下是全量扫描后列出的高优技术债（按优先级降序）：
1. **`components/studio/Panels.tsx`** (530行) 包含 `AssetsPanel`, `InputPanel`, `TimelinePanel`, `PropertiesPanel`, `Panels` 5个不相关的顶级业务面板。需拆分为 `panels/` 目录。
2. **`components/studio/SettingsPage.tsx`** (1017行) 混杂了设置大壳、`SettingsPageContent` 以及极其复杂的 `LlmRolesTab` 和 8 个处理数据流的纯逻辑 util 函数。不仅违反了组件单一原则，还混入了纯逻辑。需拆分为 `settings/` 目录，并将数据操作函数抽出为 hooks 或 API utils。
3. **`components/GraphCanvas.tsx`** (632行) 混杂了主画板 `GraphCanvas`、具体节点渲染器 `SkillNode` 以及边构建逻辑 `buildEdges`。应将具体节点抽出至 `components/nodes/` 目录下。

## 2. UI 组件与样式基准规范

Studio 定位为沉浸式的极客生产力工具。在构建桌面级复杂工具时，统一的设计系统是效率的保障。UI 视觉规范继承于我们早期的重构成果，并由本基准文件实施长期仲裁。

### 2.1 依赖体系与组件复用
- **基础库选型**: 抛弃内联 CSS 和手写类名，全面基于 `TailwindCSS v4` 配合无头组件库 [`shadcn/ui`](https://ui.shadcn.com/) (官方主页) / [组件文档](https://ui.shadcn.com/docs/components)。
- *(新)* 诸如 `AlertDialog`, `RadioGroup` 等新增组件，必须优先从 `shadcn` 统一引入，并统一落户在 `src/components/ui/` 目录下。
- **严禁重新发明轮子**：业务代码中如需模态框，必须复用 `ui/dialog.tsx`，除非有极为特殊的交互理由，才允许手写封装。

### 2.2 样式 Token 化 (Design Tokens)
**本项目样式真实来源**: shadcn `radix-mira` preset (preset id `b38miVIYq`, style `mira`, theme `indigo`), 可直接预览 demo: <https://ui.shadcn.com/create?preset=b38miVIYq&template=vite&pointer=true&rtl=true>。
- **核心风格**: deep indigo-violet primary on neutral grays, light + dark mode, 0.625rem radius, Inter Variable + JetBrains Mono Variable fonts, lucide icons。
- 设计 tokens 已 100% 推导自 demo computed CSS, 详细 token 矩阵见 [`.kiro/specs/_archive/studio-uikit-redesign/tokens.md`](../../.kiro/specs/_archive/studio-uikit-redesign/tokens.md), 当前已沉淀至本地主题 CSS (`apps/studio/frontend/src/index.css`)。
- **颜色原则**: 开发人员写新组件时, **严禁 Hardcode 任何十六进制颜色码或 Tailwind 具体色值** (如 `bg-gray-800`)。必须使用语义化的 CSS 变量类 (如 `bg-background`, `text-muted-foreground`, `border-border`)。

### 2.3 暗黑极客主题 (Dark Theme Only)
默认强制并专注于高对比度的暗色环境，营造专业生产力环境，不要求完美兼顾白昼模式的降级体验。
- 背景底色: `bg-background` 使用 `zinc-950`，制造沉浸深度感。
- 边框与分割线: `border-border` 使用 `zinc-800`。

### 2.4 圆角原则
为保持极客硬朗感，应用圆角不得超过 `rounded-md` (0.375rem)，杜绝大圆角的“消费端”圆滑感。视觉一致性约束包含全局组件（包括浮动弹窗和侧边栏），严禁引入过度活泼的大圆角元素。

## 3. GraphCanvas 画布样式覆写
原生的 `@xyflow/react` 深色主题仍带有较重的网页感，在 `GraphCanvas` 组件和全局 `index.css` 中进行了覆写：
- **节点主体 (`SkillNode`)**: 应用统一的背景令牌 (`bg-card`) (见 `GraphCanvas.tsx:143`)；处于执行态时，采用呼吸式的高亮效果，但仅应用在节点内部的 Status 徽章上 (通过 Tailwind `animate-pulse-primary` 实现，见 `GraphCanvas.tsx:186`)。
- **连接线 (Edges)**: `[TODO: 设计意图未实现]` 当前仅实现了基础连线和数据包中心点 (见 `ContextEdge.tsx:37`)，原设计的浅灰色常态及数据流动画渐变色均未实现。
- **连接点 (Handles)**: `[TODO: 设计意图未实现]` 目前已覆写基础样式 (如 `!size-2.5 !bg-primary`，见 `GraphCanvas.tsx:155`)，但未实现“仅 hover 时激活显示”的隐藏防噪逻辑。

## 4. 面板拖拽系统与自适应重绘
Studio 必须表现得像一个原生桌面应用，核心支撑是灵活的分屏拖拽框架。
- **基建组件**: 采用 `react-resizable-panels`。
- **区域分割**:
  - `Sidebar (AssetsPanel)` 宽 15%-25%。
  - `Main Workspace (SplitEditor)` 包含上下或左右分割的 Canvas 画布和 Monaco 代码编辑器。
  - `Right Drawer (Copilot / Golden)` 按需滑出。
- **重要 caveat**: 拖拽调节窗体大小时，必须确保 `ReactFlow` 和 `Monaco Editor` 及时监听 Resize Observer，触发自我边界更新 (`fit-to-screen` 和 `layout()`)，否则可能产生渲染撕裂。

## 5. Tauri Native API 桥接层最佳实践
将网页代码安全接入 Tauri 本地能力的护城河机制：
- 严禁业务组件中直接解构 `window.__TAURI__` 对象。
- 所有本地 I/O 和 Shell 调用，必须收敛并封装在统一的文件下：`apps/studio/frontend/src/lib/tauri.ts`。
- **兼容策略**: 为了便于直接使用 Vite `npm run dev` 在浏览器中纯粹调试 UI，桥接层必须提供运行时检测：如果不在 Tauri 沙盒中，所有针对本地文件读写的接口必须返回模拟成功数据（Mock fallback ），而不是直接引发白屏崩溃。

## 相关 Spec
- [studio-uikit-redesign](../../.kiro/specs/_archive/studio-uikit-redesign/design.md)
