# Studio UIKit Token Specifications

> 来源: 100% 推导自 shadcn preview demo (preset b38miVIYq, style mira, theme indigo) 实测 computed CSS
> 实测原始数据: /tmp/shadcn-demo-preview-tokens.json (light + dark)
> Master + Gemini 视觉对比验证: 确认主题为 Indigo 紫色。

## §1 推导自 demo 的硬规范

### §1.1 Header
| studio 角色 | demo 对应元素 | demo 实测 | studio 应该用 | 备注 |
|---|---|---|---|---|
| 顶栏整体 (`header.tsx:28`) | application header | not found in demo | `h-11 bg-background border-b` | Demo 无此元素，移入 §2 例外收敛 |
| Toolbar 触发器 / 辅助按钮 | sidebar trigger | not found in demo | `variant="ghost" className="size-8"` | 同上，采用 32px 基准 |

### §1.2 Sidebar menu item
| studio 角色 | demo 对应元素 | demo 实测 height / fontSize / radius | studio 应该用 | 备注 |
|---|---|---|---|---|
| Sidebar 项 (`toolbar.tsx`) | `data-sidebar="menu-button"` | h=32, fontSize=12, radius=8, fontWeight=500 | `className="h-8 text-xs font-medium rounded-md"` | 实测对齐 |

### §1.3 Typography
| studio 角色 | demo 对应元素 | demo 实测字号/字重 | studio 应该用 | 备注 |
|---|---|---|---|---|
| 正文辅助段落 | `pMuted` (cn-item-description) | h=16, 12px, 500, uppercase tracking-wider | `text-xs font-medium tracking-wider uppercase text-muted-foreground` | 实测对齐 |
| 三级标题 | `h3` | 12px, 400 | `text-xs font-normal` | 实测对齐 |

### §1.4 Color tokens
| Token | Light oklch | Dark oklch |
|---|---|---|
| `--primary` | `oklch(0.457 0.24 277.023)` 紫色 | `oklch(0.398 0.195 277.366)` 暗紫 |
| `--primary-foreground` | `oklch(0.962 0.018 272.314)` 极浅紫 | `oklch(0.962 0.018 272.314)` 极浅紫 |
| `--background` | `oklch(1 0 0)` 纯白 | `oklch(0.145 0 0)` 近黑 |
| `--foreground` | `oklch(0.145 0 0)` 近黑 | `oklch(0.985 0 0)` 近白 |
| `--card` | `oklch(1 0 0)` 纯白 | `oklch(0.205 0 0)` 中暗 |
| `--card-foreground` | `oklch(0.145 0 0)` 近黑 | `oklch(0.985 0 0)` 近白 |
| `--popover` | `oklch(1 0 0)` 纯白 | `oklch(0.205 0 0)` 中暗 |
| `--popover-foreground` | `oklch(0.145 0 0)` 近黑 | `oklch(0.985 0 0)` 近白 |
| `--muted` | `oklch(0.97 0 0)` 极浅灰 | `oklch(0.269 0 0)` 中灰 |
| `--muted-foreground` | `oklch(0.556 0 0)` 中灰 | `oklch(0.708 0 0)` 浅灰 |
| `--accent` | `oklch(0.97 0 0)` 中灰/浅灰 | `oklch(0.269 0 0)` 中灰/深灰 |
| `--accent-foreground` | `oklch(0.205 0 0)` 中灰/浅灰 | `oklch(0.985 0 0)` 近白 |
| `--border` | `oklch(0.922 0 0)` 浅灰 | `oklch(1 0 0 / 10%)` 半透白 |
| `--input` | `oklch(0.922 0 0)` 浅灰 | `oklch(1 0 0 / 15%)` 半透白 |
| `--ring` | `oklch(0.708 0 0)` 中灰/浅灰 | `oklch(0.556 0 0)` 中灰/深灰 |
| `--sidebar` | `oklch(0.985 0 0)` 极浅灰 | `oklch(0.205 0 0)` 中暗 |
| `--sidebar-foreground` | `oklch(0.145 0 0)` 近黑 | `oklch(0.985 0 0)` 近白 |
| `--sidebar-primary` | `oklch(0.511 0.262 276.966)` 紫色 | `oklch(0.585 0.233 277.117)` 紫色 |
| `--sidebar-primary-foreground` | `oklch(0.962 0.018 272.314)` 极浅紫 | `oklch(0.962 0.018 272.314)` 中灰/深灰 |
| `--sidebar-accent` | `oklch(0.97 0 0)` 中灰/浅灰 | `oklch(0.269 0 0)` 中灰/深灰 |
| `--sidebar-accent-foreground` | `oklch(0.205 0 0)` 中灰/浅灰 | `oklch(0.985 0 0)` 近白 |
| `--sidebar-border` | `oklch(0.922 0 0)` 中灰/浅灰 | `oklch(1 0 0 / 10%)` 中灰/深灰 |
| `--sidebar-ring` | `oklch(0.708 0 0)` 中灰/浅灰 | `oklch(0.556 0 0)` 中灰/深灰 |
| `--destructive` | `oklch(0.577 0.245 27.325)` 红 | `oklch(0.704 0.191 22.216)` 暗红 |
| `--destructive-foreground` | `lab(96.4152% 3.22586 1.14673)` 近白 | `lab(49.0747% 69.3434 49.6251)` 暗红(注意自定义) |

> 已 verify: `apps/studio/uikit/src/index.css` 的 oklch 值完全对齐 demo preview tokens (主控 cat 比对). round 8 报告的 '严重不一致' 是基于 ui.shadcn.com **外层 chrome** 的错值,已废弃。

### §1.5 Button + icon size 配对
- **主行动按钮**: h=28 + svg `size-3.5` (14px) [按 28px 等比推算]
- **Sidebar item**: h=32 + svg `size-4` (16px) [按 32px 等比推算]
- **Radius 配对**: Card radius=10px (`--radius-lg`), button radius=8px (`--radius-md`), input radius=6px (`--radius-sm`).

### §1.6 react-flow 适配 (来源: reactflow.dev 官方示例推导)
| 部件 | studio CSS 覆写 (用 shadcn semantic token) |
|---|---|
| Controls 容器 | `.react-flow__controls { background: var(--color-card); border: 1px solid var(--color-border); border-radius: var(--radius-md); box-shadow: var(--shadow-sm); }` |
| Controls button | `.react-flow__controls-button { background: var(--color-card); color: var(--color-foreground); border-color: var(--color-border); }` |
| Controls button hover | `.react-flow__controls-button:hover { background: var(--color-accent); }` |
| MiniMap 容器 | `.react-flow__minimap { background-color: var(--color-card); }` |
| MiniMap mask | `<MiniMap maskColor="var(--color-background)" />` (JSX 中指定) |
| MiniMap node | `<MiniMap nodeColor="var(--color-primary)" />` (JSX 中指定) |
| Background dots | `<Background color="var(--color-border)" className="!bg-background" />` (JSX 中指定) |

## §2 已辩论收敛的例外 (Round 2 + Round 7)

- **Header h-11 (44px)**: `header.tsx:28`。理由：demo 没暴露 application header, 继承 round 2 user 拍定的 IDE 紧凑风格。
- **Panel 内联 X close**: `panels.tsx:38`。拍定为 **20px** (`Button variant="ghost" size="icon-xs"`) + 内 svg `size-2.5 strokeWidth=1.5`。理由：demo 无 icon-only close pattern; 跟 demo 主按钮 28px 形成层级 (panel 内紧凑)。
- **Copilot 浮球**: `copilot.tsx:106`。拍定为 **40px** (`Button size="icon" className="fixed ... size-10 rounded-full shadow-lg"`)。理由：demo 无 FAB pattern; 符合 iOS HIG 44pt 触控目标妥协 + Material FAB mini; user 4 铁律明示要浮球。
- **Copilot 输入框 toolbar button**: `copilot.tsx:37/90`。拍定为 **28px** (`Button variant="ghost" className="h-7 w-7"`) + 内 svg `size-3.5`。理由：demo 主按钮 28px，Copilot 输入框 toolbar button 跟主按钮**同 28px** 形成统一节奏（代表辅助交互）。
- **SkillNode (canvas 节点)**: 见 `.kiro/specs/studio-uikit-redesign/skillnode-spec.md`。理由：demo 无 react-flow custom node。

## §3 需要 User 讨论的"demo 无对应"清单

> (清空, 已全部收敛至 §1.6 或 §2)

## §4 Drift 清单 (基于 §1 新基准 + 实测 studio 现状)

> 已 grep `apps/studio/uikit/src/components/`,具体 file:line 已落实。"现值"是 Tailwind class → 像素换算后的实际渲染尺寸。

### §4.1 button.tsx 基线 (`src/components/ui/button.tsx`)

| size | class | 像素 | 跟 demo 对齐? |
|---|---|---|---|
| `default` | h-7 | **28px** | ✓ = demo 主按钮 28px |
| `xs` | h-5 | 20px | ✓ = §2 Panel close 拍 (icon-xs) |
| `sm` | h-6 | 24px | ✗ = 比 demo 28px 小一档 (这是 drift 源头) |
| `lg` | h-8 | 32px | ✓ = demo sidebar item 32px |
| `icon` | size-7 | 28px | ✓ |
| `icon-xs` | size-5 | 20px | ✓ |
| `icon-sm` | size-6 | 24px | ✗ |
| `icon-lg` | size-8 | 32px | ✓ |

**结论**: button.tsx 本身 ok,问题在调用方很多用 `size="sm"` (24px) 应该用 `size="default"` (28px) 或 `size="lg"` (32px)。

### §4.2 header.tsx Drift (`src/components/studio/header.tsx`)

| file:line | 当前 | 应改 | 理由 |
|---|---|---|---|
| `header.tsx:44` | `h-11 bg-background border-b` | 保留 | ✓ 已对齐 §2 例外 |
| `header.tsx:49` | `<Button size="sm">` (24px) projectName | `size="default"` (28px) | demo 主按钮基准 |
| `header.tsx:50` | `text-sm font-medium` (14px) projectName | `text-xs font-medium` (12px) | demo fontSize=12 |
| `header.tsx:78` | `<Button variant="ghost" size="sm">` Predict | `size="default"` (28px) | 同上 |
| `header.tsx:83` | `<Button size="sm">` Run | `size="default"` (28px) | demo 主按钮 28px |
| `header.tsx:95/110/122` | `size="icon-sm"` (24px) Copilot/Theme/User | `size="icon"` (28px) | 跟主按钮节奏一致 |

### §4.3 panels.tsx Drift (`src/components/studio/panels.tsx`)

| file:line | 当前 | 应改 | 理由 |
|---|---|---|---|
| `panels.tsx:21` | `h-10` (40px) panel header | 保留 (40px 介于 32-44 中间, 比 Header 略矮但比 sidebar item 高一档) | §2 没拍, 视为合理 |
| `panels.tsx:26` | `size="icon" className="size-6"` (24px) close X | `size="icon-xs"` (20px) + svg `size-2.5` | §2 拍定 20px |
| `panels.tsx:49,138,276` | `text-sm` panel body 文字 (14px) | `text-xs` (12px) | demo body 12px 基线 |
| `panels.tsx:176` | `Input h-8 text-sm` (32px + 14px) | `h-7 text-xs` (28px + 12px) | demo input h=28 fontSize=12 |
| `panels.tsx:192` | `SelectTrigger h-8 text-sm` | `h-7 text-xs` | 同上 |
| `panels.tsx:225` | `Textarea text-sm` | `text-xs` | 同上 |
| `panels.tsx:152` | `<Button size="sm">` | `size="default"` (28px) | demo 主按钮基准 |

### §4.4 copilot.tsx Drift (`src/components/studio/copilot.tsx`)

| file:line | 当前 | 应改 | 理由 |
|---|---|---|---|
| `copilot.tsx:26` | `h-11` copilot header | 保留 | ✓ 跟 Header 同高 (44px), 合理 |
| `copilot.tsx:28` | `text-sm font-medium` (14px) "New Chat" | `text-xs font-medium` (12px) | demo body 12px |
| `copilot.tsx:32,35` | `size="icon-xs"` (20px) header toolbar buttons | 保留或改 `size="icon-sm"` (24px) | header 内紧凑, 20-24px 都可 |
| `copilot.tsx:49` | `text-sm text-muted-foreground` (14px) empty state | `text-xs` (12px) | 12px 基线 |
| `copilot.tsx:79,82,86` | `size="icon-xs"` (20px) input toolbar (附件/send 等) | **`className="h-7 w-7"` + svg `size-3.5`** (28px) | §2 round 7 user 拍定 |
| `copilot.tsx:103-104` | `size="icon" className="fixed ... size-10"` (40px) floating ball | 保留 | ✓ §2 round 7 user 拍定 |

### §4.5 toolbar.tsx (sidebar) Drift (`src/components/studio/toolbar.tsx`)

| file:line | 当前 | 应改 | 理由 |
|---|---|---|---|
| `toolbar.tsx:35` | `size-7 rounded-md` (28px) logo | `size-8 rounded-md` (32px) | 跟 demo sidebar menu item 32px 对齐 |
| `toolbar.tsx:50` | `<Button size="icon">` (28px) 项目按钮 | `size="icon-lg"` (32px) | 同上, demo sidebar item 32px |
| `toolbar.tsx:81` | `<Button size="icon" className="size-8">` (32px) 底部按钮 | 保留 | ✓ 已对齐 |

### §4.6 ui/ primitives 基线检查

| 组件 file:line | 当前 | 应改 | 理由 |
|---|---|---|---|
| `card.tsx:15` | `rounded-lg text-xs/relaxed` | 保留 | ✓ `rounded-lg` 在 shadcn 4 = `var(--radius-lg)` = 10px,跟 demo 实测对齐; 文字基线 text-xs ✓ |
| `input.tsx:11` | `h-7 rounded-md text-sm` | `h-7 rounded-md text-xs` | h-7 ✓ 28px; rounded-md (8px) ✓; **text-sm (14px) → text-xs (12px)** (demo input fontSize=12) |
| `sidebar.tsx` 整体 bg/border | (token-driven, oklch 已对齐) | 不需要改 | 主控已 cat 验证 oklch token 全行对齐 |

