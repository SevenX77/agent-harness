# studio-layout (studio system-level) — MVP0 Alignment (下一步对齐逻辑)

> **Status**: Filled by a2 (Gemini), 2026-05-20
> **Scope**: Layout 承载、Context Provider 重构、Resizable 面板与 Context Inspector (High-003)
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

在 MVP0 中，为了让 PM 达到 "不开终端，可视化完成一切" 的目标，界面的利用率和合理切割至关重要。目前 5 个核心功能面板堆叠较为简单，详见 [baseline.md#UI/UX](./baseline.md#UI/UX)。

我们将规划如下的大格局：
- **左侧边栏 (Left Sidebar)**：固定且可收起的项目文件树资源（关联 `multi-file-editor`），方便进行整体管理。它会在左上角保留极小的留白。
- **中央主工作区 (Center Canvas/Editor)**：以大量宽度承载最核心的 `GraphCanvas` 或 `SplitEditor`。PM 将在这里进行逻辑搭桥或者修补 Prompt。这是 PM 视线停留最久的地方。
- **右侧面板集 (Right Panels)**：使用 Tab 或可折叠手风琴堆叠 `Properties`（包含属性配置）、`Copilot` (大模型聊天)，这是 PM 获得帮助的区域。
- **底部抽屉 (Bottom Drawer)**：常驻为 `TracePanel`。在点击运行后会弹起展示瀑布流。

### 1. Resizable 组件嵌套细节
在保持现在的 `react-resizable-panels` 基础上，我们将对底部的 TracePanel 赋予一个特殊的 `defaultSize={0}` 和 `collapsible={true}` 属性。
这使得平时编辑时，它是绝对隐形的（或者只有一行 Toolbar）；只有发生 Run 动作或手动触发时，它才会通过 ref `expand()` 自动弹起占据约 30% 屏幕空间。

### 2. SplitEditor 比例绑定
为了迎合多文件开发的重度需要，中央主视图的 Width 不再是固定的。左侧的文件树 `PanelFiles` 可以被缩放到仅仅留下图标，从而为 `SplitEditor` 让出将近 85% 的横向屏幕空间。这将给代码阅读带来极大的舒适感。

### 3. Right Panels 的互斥设计
`PropertiesPanel` (包含 Context Inspector) 与 `CopilotPanel` 同属右侧槽位。MVP0 将把它们设计为 Tabs 的形式（默认激活 Properties）。当 Copilot 收到新消息时，若当前处于 Inspector 状态，顶部的 Copilot Tab 将会出现一个 Red Dot 的 Badge 通知，引导用户切回查看。

### 4. TraceDrawer 拖拽行为定制
对于底部的 TraceDrawer 来说，因为包含了极其繁杂的历史和耗时瀑布图，其展开动作并非是单纯的显隐切换，它需要在拖拽（Resize）的时候发出专有的 `onLayoutResize` 事件。这个状态更新对于里面包裹着的虚拟列表 (VirtualList) 或者 Canvas 重绘是决定性的，不然会造成高度截断的丑陋渲染。

### 5. 极简模式与全屏能力
随着多显示器用户的增多，未来的框架内可能需要为某些 Panel 添加 `fullscreen` 按钮。
在 MVP0 阶段我们虽然不主推脱离主窗口，但 Layout 的划分必须预留 `isMaximized` 这种组件属性，例如让画布直接覆盖左侧文件树，提供纯粹的白板心流体验模式。

### 6. 多端适配与自适应
考虑到不同开发者的屏幕比例差异极大，`Workspace` 的 Provider 必须包含对窗口 Resize 事件的监听。如果总宽度低于某个阈值，左侧的目录树会被自动吸附隐藏，从而优先保障 Editor 和 Canvas 的核心展示面积。

### 7. Layout 状态持久化实现方案
为了使得侧边栏宽度的存储更加健壮，避免由于刷新导致面板抖动（FOUC），`apps/studio/frontend/src/components/studio/Workspace.tsx` 中的 Layout Provider 需要在初始渲染前阻塞：
- 采用 SSR-safe 的 `useLocalStorage` 钩子，并在默认值上进行打底。
- 当 `localStorage.getItem("layout-panels")` 返回空时，给定 `[20, 50, 30]` 这种黄金比例切分。

### 8. Mobile 端的降级适配
即使 Studio 主要是为桌面环境（Tauri + Web Desktop）设计的，但我们仍需通过 CSS Media Query 支持极限小屏幕（如 1024px 以下）。
- 当屏幕小于断点时，强制将 `Left Sidebar` 收起，只展示核心编辑区。
- `Right Panels` 如果空间不足以支持侧边停靠，考虑将其变为浮动的 Drawer 组件。

### 9. Header Toolbar 的重构
原有的 Toolbar 可能在 `PropertiesPanel.tsx` 或是其他区域散落。
- MVP0 必须抽离出一个统一的 `<CenterActionBar />`，置于界面的顶端正中。
- 这里放置 `Run`、`Compile` 等全局指令，保证无论下面的面板如何切换，全局动作永远触手可及。

### 10. CSS Theme Variables
这套全新的 Layout 必须通过 CSS Variables (如 `--panel-background`, `--border-color`) 来支撑 Dark/Light 模式的秒级切换，杜绝任何硬编码的绝对色值，保证框架的美观。

## 前端逻辑

为支持 High-003 (点击连线数据包打开 Context Inspector 却在目前 Layout 中无此定义的缺失，见 [baseline.md#前端逻辑](./baseline.md#前端逻辑))，我们将对右侧的 `Panels.tsx` 和 `PropertiesPanel.tsx` 进行重构。

- **Context Provider 升级**：当前 `apps/studio/frontend/src/components/studio/Workspace.tsx:372` 附近的 `<Panels />` 调用只是接收简单的 `selectedNode` 引用。我们将扩展外层的 Context，使其能分辨 `Edge` 选型。这个上下文将在整个 Layout 树中透传。
- **Inspector 的真正着落点**：Context Inspector 将不作为一级最高 Tab，而是挂载在 `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:83` 的条件渲染区域。当 PM 点击画布节点时，显示 Node 属性；当点击画布的连线时，这块区域将平滑切换为 Inspector 结构展示视图。
- **Resizable 替换策略**：考虑到 MVP0 PM 操作的顺滑度，继续维持现有 Resize 组件，但在底部引入更强壮的抽屉式 Layout 展开逻辑（类似 VS Code Bottom Panel）。
- **Keyboard Shortcut (快捷键)**：MVP0 阶段暂不强求复杂快捷键栈，保留最基本的 Cmd/Ctrl+S 触发 Draft 持久化保存即可。

## Context Inspector 触发器机制说明
关于 Inspector 在 PropertiesPanel 挂载时的行为：当没有获取到 `selection.type === 'edge'` 时，该区域将 fallback 展现为空提示或是友好的指引文案："点击任意两阶段间的连线，即刻洞察上下文数据"。

## 后端功能

N/A — 此模块专指纯前端 React Shell 的组件组合排布，无后端功能。后端提供的只是数据载荷，如何利用屏幕像素面积属于纯前端范畴。这里 "backend Python library" 并不介入任何 CSS Grid 或是 Flex 布局规划。它只负责吐出 JSON 以供前台使用。

## API

在 TypeScript 端，我们要扩充传递给 Layout 系统的 Context 或 Props，明确增加连线数据检查的支持，以承接 Context Inspector (High-003)：

```typescript
// apps/studio/frontend/src/components/studio/panels/Panels.tsx

export interface LayoutContextState {
    /** Currently active right-hand tab (e.g., 'properties', 'copilot') */
    activeRightPanelTab: string;
    
    /** Selection object derived from Canvas click events */
    selection: {
        type: 'node' | 'edge' | 'none';
        id: string | null;
        /** Captured data payload of an edge to feed Context Inspector */
        edgePayload?: Record<string, any>;
    };
    
    /** Dispatcher to toggle bottom trace drawer */
    setTraceDrawerOpen: (isOpen: boolean) => void;
}
```
通过这样的接口设计，`PropertiesPanel` 内部就可以通过 `selection.type === 'edge'` 来无缝渲染 Inspector 视图。这在类型层面也是极其安全的。

## Data Model / State

本模块主要维护在纯 UI 状态机的设计上。没有复杂的数据库 Schema 支撑。
状态包含但不限于：左侧边栏伸缩宽度、底部 Trace 面板弹起高度、右侧 Tab 激活索引。
这些 UI State 应当被储存在内存或轻量级的 LocalStorage 中，确保 PM 下次打开 Studio 时，Layout 的比例和习惯依旧被记忆。

Layout 的记忆将不仅仅是保存在纯内存：
- 引入 `useLocalStorage` hook 或者类似的浏览器端持久化机制，绑定 `activeRightPanelTab` 和 `panelSizes` 数组。
- 这意味着刷新游览器后，PM 配置的最顺手的侧边栏比例将会被立刻无感还原，大大提升高级用户的黏性体验。

## Cross-feature interaction

- **响应 Canvas 操作 (High-003)**:
  这正是 High-003 在界面的最终解。当 PM 在中央画布上点选连线，Canvas 会派发一个选中事件。这引起 Layout state 更新。随之 `PropertiesPanel` 接收到 `selection.type === 'edge'`，渲染出数据剖析组件（Inspector）。交互流转详尽说明见 [ux-workflow 的操作流蓝图](./ux-workflow/mvp0-alignment.md)。
- **与 Trace-Visualization 协同**:
  底部抽屉弹起是由 [Trace 特性](../../feature-folders/trace-visualization/mvp0-alignment.md) 收到了第一条 Engine 回传事件而发起的强制展开行为。
- **与 Editor 区域占比分配**:
  Layout 为 [multi-file-editor](../../feature-folders/multi-file-editor/mvp0-alignment.md) 锁定了左侧与中央区域的宽度比例，保障了 V2.1 目录型代码文件的展示空间充足。这两者的结合让多文件无缝协同成为可能。