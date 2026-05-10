# Studio uikit 视觉重设计 — 实施任务

## 目标

以 User 4 条铁律为约束，把当前 v0 遗留 uikit 收敛为高密度工具型界面：保留 toolbar `size-8` 密度基准，优先使用 shadcn 官方 primitive / preset，不魔改 primitive 配色，并与 radix-mira shadcn create demo 的清晰边框与字体层级对齐。Copilot 浮球已恢复，本轮任务只规划后续视觉重设计 slice。

## Slice 序列

### Slice 3 — P1 Sidebar 骨架 (Toolbar / Panels / Copilot 三栏整合)

**why**: design.md §1 总结的 P1 核心差距 — 当前 Shell 主要用手工 div 拼接，缺 shadcn SidebarProvider、左侧 Sidebar、右侧 Sidebar 的标准区域骨架。

**改 file**:
- `apps/studio/uikit/src/components/studio/toolbar.tsx` — 用 `<Sidebar collapsible="icon" side="left">` 重写 toolbar 外壳与菜单项。
- `apps/studio/uikit/src/components/studio/copilot.tsx` — 用 `<Sidebar side="right">` 包右侧 Copilot 外层，保留已恢复的 `CopilotButton`。
- `apps/studio/uikit/src/components/studio/panels.tsx` — 4 个 panel 的列表 / 树形菜单换成 `<SidebarContent>` / `<SidebarGroup>` / `<SidebarMenu>` 系列。
- `apps/studio/uikit/src/components/studio/workspace.tsx` — wrap `<SidebarProvider>`，调整 `ResizablePanelGroup` 与 Sidebar 的关系。
- `apps/studio/uikit/src/index.css` — 加 `--sidebar-width-icon: 3rem`，对齐 design.md §6.3。

**关键约束**:
- Toolbar button 必须保 `size-8` (32px)，用 `<SidebarMenuButton className="size-8 rounded-md justify-center">`。
- 字号统一：header / toolbar / panels 主级 `text-sm font-medium`，次级 `text-xs text-muted-foreground`。
- `ResizableHandle` 加 `withHandle`。
- 不魔改 shadcn primitive 默认配色，不把 primary 大面积铺开。

**验证**: `npm run typecheck` 0 error + `npm run diag` 无控制台报错 + screenshot 看整体三栏 layout 不崩。

---

### Slice 4 — P2 Header 用 SidebarTrigger + Breadcrumb

**why**: design.md §2.1 + §6.1 要求 Header 保持高密度 `h-11`，但左侧结构从扁平项目下拉升级为 SidebarTrigger + Breadcrumb，形成清晰层级。

**改 file**:
- `apps/studio/uikit/src/components/studio/header.tsx` — 左侧从 Project Info 下拉换成 `<SidebarTrigger />` + `<Breadcrumb>` 组合。

**关键约束**:
- Header 高度保 `h-11` (44px)，不改成 shadcn demo 的 `h-14`。
- 项目名 / 状态用 `text-sm font-medium`。
- 主题色仅保留 Predict / Run 主按钮，其他导航结构保持克制。
- Header 右上 Sparkles toggle 保留，不影响 Copilot 浮球双入口。

**验证**: typecheck + diag + light/dark screenshot，看顶部层级与密度是否稳定。

---

### Slice 5 — P3 SkillNode 视觉重构 (按 skillnode-spec.md)

**why**: SkillNode 是 canvas 核心 custom node，design.md §2.4 与 skillnode-spec.md 已定义 6 态视觉，需要从简单 border 卡片升级为 shadcn Card 风格节点。

**改 file**:
- `apps/studio/uikit/src/components/studio/canvas.tsx` — 重构 SkillNode 部分；如果体积变大，可拆出 `apps/studio/uikit/src/components/studio/skill-node.tsx`。
- `apps/studio/uikit/src/index.css` — 如需 success / warning 语义色，新增 `--success` / `--warning` oklch token。

**关键约束**:
- 严格按 skillnode-spec.md §1-§6 实施：`rounded-xl`、`shadow-sm`、`min-w-[200px]`、`p-3`。
- 不硬编码 `bg-emerald-500` / `bg-amber-500`；改用 `bg-success` / `bg-warning` 等语义 token。
- 选中态用 `ring-2 ring-primary ring-offset-1 ring-offset-background`，不改基础 border 色。
- error / breakpoint 态允许强制 ring，但仍遵守语义 token。
- Handle 改空心方块：`!w-2.5 !h-2.5 !bg-background !border-2 !border-border !rounded-sm`。
- 节点标题 `text-sm font-medium`，ID / 副标题 `text-xs font-mono text-muted-foreground`。

**验证**: typecheck + diag + screenshot；mock 6 个不同 status 节点逐态检查。

---

### Slice 6 — Trace Timeline + Editor 行号 + Copilot 输入框

**why**: design.md §3 列出没有 shadcn 模板可直接套的自定义组件；SkillNode 已在 Slice 5，本 slice 收敛剩余 3 个单独设计点。

**改 file**:
- `apps/studio/uikit/src/components/studio/panels.tsx` — TimelinePanel 改垂直时间线 + 状态图标；EditorPanel 增强行号区。
- `apps/studio/uikit/src/components/studio/copilot.tsx` — Copilot 输入组合框改为 shadcn 对齐的 focus wrapper。

**关键约束**:
- Timeline 使用 lucide 状态图标 + semantic tokens，文字 `text-xs`，间距 `gap-2`。
- Editor 行号区使用 `bg-muted/50 text-muted-foreground font-mono`。
- Copilot 输入外层 `bg-background border rounded-lg focus-within:ring-1 focus-within:ring-ring`，内部 Input / Textarea `border-0 shadow-none`。
- 不引入大面积装饰色，不提高整体留白密度。

**验证**: typecheck + diag + screenshot，检查 Timeline 信息密度、Editor 行号可读性、Copilot 输入 focus 态。

---

### Slice 7 — Dark mode border 微调 + 全局 token 收尾

**why**: design.md §4 指出 dark mode border 对比度不足，需要轻微提升结构分割感，同时不更改 radix-mira 主色。

**改 file**:
- `apps/studio/uikit/src/index.css` — dark mode `--border` 从 `oklch(1 0 0 / 10%)` 调整到 `oklch(1 0 0 / 15%)`；如 Slice 5 已引入 success / warning token，在此统一复核 light/dark 值。

**关键约束**:
- 不更改 oklch 主色、primary、background、card 等 radix-mira preset 核心 token。
- 只做 border 清晰度与新增语义 token 收尾。

**验证**: dark mode screenshot 看边框是否更清晰，且不出现高对比割裂。

## 验证总入口

每 slice 完成后:
1. `cd apps/studio/uikit && npm run typecheck` (0 error)
2. `npm run diag` (headless Playwright 看控制台没报错)
3. `npm run screenshot` (light + dark 各一张，存 `/tmp/uikit-{light,dark}.png`)
4. master 看 screenshot，与 design.md / skillnode-spec.md 对比，通过后 commit

## 边界

- 只按 slice 实施 uikit 视觉重设计，不改 backend。
- 优先 shadcn 官方 primitive / preset；没有模板的组件才单独设计。
- 不魔改 shadcn primitive 默认配色，不做大面积主题色铺底。
- 保留 toolbar `size-8` 密度基准。
- 保留 Header Sparkles toggle + 已恢复的 Copilot 浮球双入口。
