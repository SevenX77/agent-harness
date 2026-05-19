# Skill Studio uikit 视觉 audit (Gemini a2)

## §1 总结
- **现状一句话定性**: 当前实现（v0 遗留）在视觉上显得松散且破碎，缺乏企业级工具的紧凑感和层级深度；User 偏好高密度的紧凑布局，而当前手工拼凑的 UI 大大拉低了信息密度。
- **跟 shadcn create demo 的核心差距**:
  1. **布局骨架 (Shell)**: 当前用原生的 div 和 border 手工拼接全屏布局，缺乏 shadcn 标准 SidebarProvider、双侧 Sidebar 带来的清晰区域区隔。
  2. **组件嵌套与密度**: shadcn 的 SidebarGroup、Breadcrumb 形成了极高密度的紧凑排列 (通常是 gap-1, h-8 控件)，而当前代码的 Panel 列表使用了偏大的 py-1.5 与手工编排的 DOM。
  3. **主题色克制**: radix-mira (深紫蓝) 在 shadcn 标准中极度克制，仅用于 active 状态环、主按钮和指示，而当前代码有些生硬地使用了主色边框。
- **修复优先级**:
  - **P1**: 用 shadcn Sidebar 组件重构左侧 Toolbar/Panels 和右侧 Copilot（解决整体 Shell 骨架问题）。
  - **P2**: 用 shadcn Breadcrumb + 标准结构重写顶部导航 Header。
  - **P3**: 重新设计 Canvas 的 SkillNode，使其视觉符合 shadcn Card 标准。

---

## §2 组件级 audit

### §2.1 Header (header.tsx)
**当前**: apps/studio/uikit/src/components/studio/header.tsx:28 高度为 h-11 (44px)，左侧直接放置了一个扁平的下拉按钮。
**shadcn 标准**: 基于 https://ui.shadcn.com/docs/components/breadcrumb ，标准的顶栏应具有清晰的层级面包屑。高度通常为 h-14 或 h-16。
**差距**: 高度偏矮（44px vs 56px），没有结构化的导航面包屑，视觉上缺乏“顶梁”的支撑感。
**建议**:
- [x] 直接换 shadcn 现成模板 → 使用 SidebarTrigger 配合 Breadcrumb 组合来替代左侧的 Project Info 下拉框。
- [ ] 没现成模板, 单独设计 → N/A
**主题色应用**: 仅保留右侧 "Predict/Run" 按钮的 Primary 色填充，不作为大面积背景。

### §2.2 Toolbar (toolbar.tsx)
**当前**: apps/studio/uikit/src/components/studio/toolbar.tsx:24 使用 w-12，内部 button size-8。手工绘制。
**shadcn 标准**: 基于 https://ui.shadcn.com/docs/components/sidebar ，应使用 Sidebar collapsible="icon" 模式。
**差距**: 完全手写的 div 栏，缺乏标准 Sidebar 的自动背景、边框和折叠动画支持。
**建议**:
- [x] 直接换 shadcn 现成模板 → 用 shadcn Sidebar 组件 (collapsible="icon") 重写。保留 User 满意的 size-8 按钮基准。
- [ ] 没现成模板, 单独设计 → N/A
**主题色应用**: 选中状态的图标保留 Primary 色。

### §2.3 Panel headers + 4 个 panels (panels.tsx)
**当前**: apps/studio/uikit/src/components/studio/panels.tsx:14 PanelHeader 高度 h-10，树形结构 (AssetsPanel:49) 用手工 ml-4 border-l pl-3 缩进绘制。
**shadcn 标准**: 使用 SidebarContent, SidebarGroup, SidebarMenu 来处理可折叠的树形菜单。
**差距**: 手工缩进视觉松散，Hover 态无法完美包裹整个行，信息密度低于标准 Sidebar 菜单。
**建议**:
- [x] 直接换 shadcn 现成模板 → 彻底用 SidebarMenu 系列重写 AssetsPanel 的树形结构。PropertiesPanel 可用标准 Form 组件。
- [ ] 没现成模板, 单独设计 → TimelinePanel 的 trace 列表和 EditorPanel。
  - **设计要点 (Editor)**: 行号区域背景应使用 bg-muted/50，文本 text-xs font-mono text-muted-foreground。
**主题色应用**: Timeline 中仅用于状态小圆点点缀。

### §2.4 Canvas / SkillNode (canvas.tsx)
**当前**: apps/studio/uikit/src/components/studio/canvas.tsx:21 Node 使用 bg-card border rounded-md min-w-[180px]。
**shadcn 标准**: 标准卡片应具备明确的阴影层级和标准的圆角 (rounded-xl 即 12px)。
**差距**: 当前 Node 圆角 rounded-md 偏小，选中时使用生硬的 shadow-[0_0_0_1px_var(--primary)]。
**建议**:
- [ ] 直接换 shadcn 现成模板 → N/A
- [x] 没现成模板, 单独设计 →
  - **设计要点**: 节点基础采用 Card。常态边框 border-border，选中态改用 ring-2 ring-primary ring-offset-1。内部角标用 Badge variant="secondary"。

### §2.5 Copilot 右栏 + 浮球 (copilot.tsx)
**当前**: apps/studio/uikit/src/components/studio/copilot.tsx:18 手写 w-full bg-sidebar border-l 结构。输入框使用嵌套边框。
**shadcn 标准**: shadcn 提供 Sidebar side="right"。
**差距**: 与 Toolbar 问题相同，缺乏标准框架支撑。
**建议**:
- [x] 直接换 shadcn 现成模板 → 使用 Sidebar side="right"。
- [ ] 没现成模板, 单独设计 → Copilot 输入框。
  - **设计要点**: 组合输入框外层使用 bg-background border rounded-lg focus-within:ring-1 focus-within:ring-ring，内部实际 Input 去掉边框 border-0 shadow-none。

### §2.6 Resizable handles + ResizablePanelGroup
**当前**: apps/studio/uikit/src/components/studio/workspace.tsx:42 使用了标准 ResizableHandle。
**shadcn 标准**: 标准提供 withHandle 属性渲染拖拽把手图标。
**差距**: 把手是隐形的细线。
**建议**:
- [x] 直接换 shadcn 现成模板 → 修改为 ResizableHandle withHandle 增加可视拖拽把手。

---

## §3 没有 shadcn 模板可抄 → 必须单独设计的清单

| 组件 | 设计要点 | 跟 shadcn 系统的对齐方式 |
|---|---|---|
| **SkillNode (Canvas)** | 节点 6 态 (idle/running/success/error/paused/breakpoint)。 | 基础用 Card。选中态用 ring 而非改 border。状态指示用点状灯 (size-2 rounded-full) 配合 semantic tokens。 |
| **Trace Timeline Node** | 垂直时间线排列，带有执行时长和状态图标。 | 间距对齐 gap-2，文字 text-xs，状态图标用 Lucide icons 配合 text-emerald-500 或 text-destructive。 |
| **Editor 行号与高亮** | 行号固定在左侧，等宽字体。 | 行号栏 bg-muted/50 text-muted-foreground font-mono。 |
| **Copilot 输入组合框** | 多行 Textarea 配合底部工具栏。 | 外层 Wrapper 模拟 focus 状态 (focus-within:ring-1)，内部 textarea border-0。 |

---

## §4 全局 token 调整建议

> 注：不更改 oklch 主色。

| token | 当前 | 建议 | 理由 |
|---|---|---|---|
| Dark Mode border | oklch(1 0 0 / 10%) | oklch(1 0 0 / 15%) | Dark mode 下当前的边框对比度过低，稍微提亮边框线使其更清晰，增强结构分割感。 |

## §5 Audit self-check
- [x] 每个组件都有 file:line
- [x] 实际 fetch 了 shadcn URL (不是凭印象)
- [x] "没有模板可抄"清单完整
- [x] 主题色建议合理 (sparse 用紫色, 不到处铺)
- [x] 没改任何 .tsx 源文件 (只写 audit md)

## §6 Round 2 复核 (主控 push back 3 条)

### §6.1 Header 高度 h-11 vs h-14/h-16
**主控疑问**: Toolbar icon `size-8` (32px)，当前 Header `h-11` (44px) 比例 1.375，如果改 `h-14` (56px) 比例变 1.75，是否与 User "偏密度型紧凑" 诉求反向？
**我的实测数据**: Fetch `https://ui.shadcn.com/create...` (b38miVIYq preset) 后确认，其顶层 `<header>` 的高度直接使用了 `--header-height` 变量，该变量定义为 `calc(var(--spacing) * 14)`，对应的 Tailwind class 正是 `h-14` (56px)。内部主按钮为 `text-sm h-9` 或 `h-8`。
**我的最终结论**: **接受主控的 push back，保留当前 uikit 的 `h-11` (44px) 作为 Workspace 的 Header 高度**。
理由：shadcn create demo 是一个偏向 C 端展示的营销页/配置页，使用 `h-14` 留白充足。但我们的项目是专业型桌面端 IDE 工具 (Tauri)，在 IDE 类布局（如 Cursor/VSCode）中，顶栏通常极为紧凑。保留 `h-11` (44px) 能完美呼应 Toolbar 内部 `size-8` (32px) 的高密度诉求（留给上下各 6px padding）。因此，撤回对 Header 尺寸改为 `h-14` 的建议，但**保留**关于加入 Breadcrumb 和优化左侧结构的视觉建议。

### §6.2 shadcn create demo 实测字号
**主控疑问**: User 第 3 条铁律要求“字体清晰排版大小极其舒服美观”，需要实测 demo 实际字号并给出 uikit 各区域对应建议。
**我的实测数据**: 
- 顶部导航/菜单项 (Sidebar Menu Items): `text-sm` (14px) 配合 `font-medium` (500)。
- 主要按钮 (如 "New" btn): `text-[0.8rem]` (~13px) 或 `text-sm`，`font-medium`。
- 内容区正文: `text-sm` (14px) 和 `text-muted-foreground`。
- 内容区主标题: `text-2xl` (24px) 配合 `font-semibold` (600) `tracking-tight`。
**我的最终结论**: 当前 uikit 需按以下标准锁紧排版密度：
- **Header**: 项目名及状态用 `text-sm font-medium` (14px)。
- **Toolbar / Panels (左栏)**: 菜单列表、树形结构标题及面板 Header 必须统一使用 `text-sm font-medium` (14px)。次级说明或折叠项采用 `text-xs text-muted-foreground` (12px)。避免使用 `text-base`。
- **Canvas (SkillNode)**: 节点名称 `text-sm font-medium` (14px)，ID及副文本必须使用 `text-xs font-mono text-muted-foreground` (12px)。
- **Copilot (右栏)**: 对话气泡正文 `text-sm` (14px)，时间戳/系统提示 `text-xs text-muted-foreground` (12px)。输入框占位符同样为 `text-sm`。

### §6.3 Toolbar 换 `<Sidebar collapsible="icon">` 时 size-8 保护
**主控疑问**: shadcn Sidebar `collapsible="icon"` 默认内部的 `SidebarMenuButton` 折叠态偏小 (`size-7`/28px)，如何保护 User 满意的 `size-8` (32px)？
**我的实测数据**: shadcn 源码中 `collapsible="icon"` 是通过 `data-state="collapsed"` 和 CSS group data 属性来切换宽度的。其内部包裹的 `<SidebarMenuButton>` 默认支持 `size` prop（通常有 `default`, `sm`, `lg`）。
**我的最终结论**: 实施时无需硬写 className 或修改 primitive 源码。只需在包裹 Toolbar 图标时，显式使用 className 覆盖尺寸即可。
**实施代码指引**:
```tsx
<SidebarMenuButton isActive={isActive} className="size-8 rounded-md justify-center">
  <tool.icon className="size-4" strokeWidth={1.75} />
</SidebarMenuButton>
```
由于 `collapsible="icon"` 时外层 Sidebar 宽度由 `--sidebar-width-icon` 控制（需在 globals.css 中将其改为 `3rem` 即 48px），内部的 Button 强设 `size-8` 将完美居中，彻底对齐 User 给定的密度基准。

