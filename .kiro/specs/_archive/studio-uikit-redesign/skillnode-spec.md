# SkillNode 视觉规范 (6 态)

## 1. 节点容器
- **基础原语**: 基于 shadcn `<Card>` 衍生。
- **圆角**: `rounded-xl` (12px)，对齐标准卡片。
- **边框**: 
  - 常态: `border-border`
  - Hover: `hover:border-muted-foreground`
  - 选中态: `ring-2 ring-primary ring-offset-1 ring-offset-background border-border` (选中时仅加 ring，不动 border 基础色)
- **阴影**:
  - 常态: `shadow-sm`
  - Hover / 选中: `shadow-md`
- **尺寸 & 间距**:
  - `min-w-[200px]` (稍微加宽以容纳更长状态文本)
  - 内部 Padding: `p-3` (12px)，头部与内容使用 `gap-2` 分离。

## 2. 6 态视觉差

| 态 | 边框/Ring 颜色 | 状态点位置 | 状态点尺寸 | 状态点颜色 (Semantic Token) | 动画 |
|---|---|---|---|---|---|
| **idle** | 默认 (无特殊) | 左上角, 标题前 | `size-2.5` | `bg-muted-foreground/50` | 无 |
| **running** | 默认 (无特殊) | 左上角, 标题前 | `size-2.5` | `bg-primary` | `animate-pulse` (Tailwind 内置) |
| **success** | 默认 (无特殊) | 左上角, 标题前 | `size-2.5` | `bg-emerald-500` (如果未定义 token, 暂用此) | 无 |
| **error** | `ring-destructive` (出错时强制高亮) | 左上角, 标题前 | `size-2.5` | `bg-destructive` | 无 |
| **paused** | 默认 (无特殊) | 左上角, 标题前 | `size-2.5` | `bg-amber-500` (如果未定义 token, 暂用此) | 无 |
| **breakpoint** | `ring-amber-500` (强制高亮) | 左上角, 标题前 | `size-2.5` | `bg-amber-500` | `animate-pulse` (Tailwind 内置) |

*(注：不需要额外的 framer-motion，Tailwind 的 `animate-pulse` 和 `transition-all` 足够覆盖状态切换)*

## 3. 节点内部布局
- **层级**: 分为 Header (图标+标题) 和 Body (属性/类型)。
- **Header**:
  - 排列: `flex items-center gap-2 mb-2`
  - 状态点: `div` 占位左侧首位。
  - 标题: `text-sm font-medium text-foreground tracking-tight`
- **Body**:
  - 排列: `flex items-center justify-between`
  - ID / 副标题: `text-xs font-mono text-muted-foreground`
  - 节点类型角标: 右下角，`<Badge variant="secondary" className="text-[10px] uppercase">`

## 4. react-flow Handle (连接点)
- **视觉调整**: 取代默认的实心灰圆点，改为类似锚点的空心方块或稍大的圆。
- **常态 className**: `!w-2.5 !h-2.5 !bg-background !border-2 !border-border !transition-colors !rounded-sm` (移除原生 border-radius，变小圆角方块)。
- **Hover/选中态**: 当所在 Node 被选中时，连带高亮 Handle：`!border-primary`。

## 5. Selected ring 完整 className 示例
```tsx
className={cn(
  "relative bg-card rounded-xl border border-border min-w-[200px] shadow-sm transition-all duration-200",
  selected && "ring-2 ring-primary ring-offset-1 ring-offset-background shadow-md",
  data.status === "error" && "ring-2 ring-destructive ring-offset-1 ring-offset-background",
  data.status === "breakpoint" && "ring-2 ring-amber-500 ring-offset-1 ring-offset-background"
)}
```

## 6. Dark mode 适配
- **背景**: `bg-card` 自动跟随 shadcn 配置切换至深色 (在 `index.css` 中定义为 `oklch(0.205 0 0)`)。
- **文本**: `text-foreground` 和 `text-muted-foreground` 自动适配。
- **无需写 `dark:` 前缀**，因为所有的语义 Tokens (`border`, `card`, `primary`, `muted-foreground`) 已经在 `components.json` / `index.css` 的 `.dark` 块中配置好了反转值。
