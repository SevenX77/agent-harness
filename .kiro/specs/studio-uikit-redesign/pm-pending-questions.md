# PM 待决问题清单 — 11 UI 组件 audit + 4 遗漏组件

**来源**: a2 (Gemini) audit, 2026-05-13, job_id `job_ac36f9b25dc3`
**对照规范**: `.kiro/specs/studio-uikit-redesign/{tokens.md, design.md, skillnode-spec.md}`
**audit 范围**: 11 个 UI 组件 (`apps/studio/frontend/src/components/studio/` 下)
**总待决数**: 22 个 (11 × 2) + 4 个遗漏组件未审计

> 这份清单是 a2 audit 原文 (轻量整理排版), 没改 a2 措辞。PM 拍板后由主控更新 design.md / tokens.md 收敛。

---

### 1. CompilationWidget

**规范覆盖度**: 无

**未覆盖维度**:
- 视觉 token / 布局: 组件位置（放在 Header 面包屑旁还是底部状态栏）、整体高度/边距，以及加载态/错误态的颜色映射。

**PM 需拍板的问题**:
- 该组件应放置在顶层 Header 内还是独立作为全局底部状态栏？
- 编译/解析的状态指示器，是用主题 primary 还是更具体的 semantic 状态色？

### 2. Minimap

**规范覆盖度**: 部分

**关键规范点**:
- `tokens.md §1.6`: 定义了 MiniMap 的底层映射容器背景色 (`bg-card`)、遮罩色 (`maskColor="var(--color-background)"`) 和节点色 (`nodeColor="var(--color-primary)"`)。

**未覆盖维度**:
- 视觉 token / 交互行为: Minimap 的默认具体尺寸 (如最大宽度或长宽比)、吸附边距位置，以及是否允许点击收缩与折叠。

**PM 需拍板的问题**:
- Minimap 应该默认固定在画板哪个角落，预留的 padding 是多少？
- 用户是否需要能自由拖拽调整 Minimap 的大小和隐藏它？

### 3. GlobalShortcutShell

**规范覆盖度**: 无

**未覆盖维度**:
- 视觉 token: 快捷键面板呼出时的容器尺寸（宽度/最大高度）、所用的阴影层级，以及内部列表和输入的字体大小。
- 交互行为: 列表项 focus 与 active 时的背景色态（应该沿用 bg-accent 还是突出的 bg-primary）。

**PM 需拍板的问题**:
- 命令面板展现的字号密度是继续沿用紧凑的 `text-sm` 还是使用更大的字号？
- 面板中上下切换选项时的高亮选中色该如何定义？

### 4. Predict

**规范覆盖度**: 无

**未覆盖维度**:
- 布局形态 / 状态机: 批测结果矩阵的具体展示形态（Bottom Panel 还是抽屉式），以及矩阵内成功/失败单元格的具体 token 对应（是否独立衍生浅色版的 semantic 颜色）。

**PM 需拍板的问题**:
- 结果矩阵的交互呈现形式是拆分视图 (Split Panel) 还是独立的浮层抽屉？
- 表格内部结果的高亮对比度，是否直接借用 SkillNode 现有的 success / error 绿红颜色？

### 5. publish-modal

**规范覆盖度**: 无

**未覆盖维度**:
- 视觉 token: 对话框尺寸（如 maxWidth）和主次按钮的布局。
- 状态机 / 交互行为: 执行不可逆危险操作（Release to Production）是否需要配合 `destructive` 系列的按钮颜色以及特定校验。

**PM 需拍板的问题**:
- 这个严重操作弹窗是否需要用户输入项目名称来进行二次防呆确认？
- 确定的发布按钮要采用 `destructive`、`primary` 还是普通的 `default`？

### 6. SubgraphInline

**规范覆盖度**: 无

**未覆盖维度**:
- 视觉 token: 嵌套展开层内的内外间距 (padding/gap) 以及为了跟外层区分开所使用的底色级别 (如 bg-muted)。
- 交互行为: 折叠/展开嵌套层级的过渡方式，连线出入内嵌节点的作用点展示。

**PM 需拍板的问题**:
- 子图是直接在当前父级画布上行内展开，还是作为“双击后进入内部视角”的单页面路由刷新？
- 允许用户在一个画板中嵌套多少层 Subgraph？

### 7. edge-context-viewer

**规范覆盖度**: 无

**未覆盖维度**:
- 视觉 token: 该信息弹出层的底层容器颜色属性（bg-popover 还是深色的类似 tooltip 的组件背景）和圆角/阴影规格。
- 交互行为: 触发弹出与消失的时间阈值机制（hover 还是 click）。

**PM 需拍板的问题**:
- 它是作为纯信息提示的黑底 Tooltip 出现，还是可以交互点选的 Popover 卡片出现？
- 触发交互是定义为悬停在连线上 500ms 还是需要明确去点击连线？

### 8. diff-bubble

**规范覆盖度**: 无

**未覆盖维度**:
- 视觉 token / 排版: 差异高亮色块（新增/删除）对应的 semantic token 色，是否强制规定代码比对为 monospace 字体及 `text-xs` 字号。
- 交互行为: 对比形式（行内 Inline Diff 与左右分栏 Split Diff 的选择）。

**PM 需拍板的问题**:
- 呈现给用户的 diff 视效，优先展示行内合并差异还是左右视窗对照差异？
- Diff 背景色是否需要设立独立的色板 token（如 `--diff-add`），还是借用原有的成功/失败色？

### 9. SettingsModal

**规范覆盖度**: 无

**未覆盖维度**:
- 视觉 token / 布局: 这个轻量态模态框的最大宽度，表单项和区块的垂直密度差距（gap），以及分类导航的位置结构。

**PM 需拍板的问题**:
- 与厚重的 SettingsPage 相比，这里的轻量模态框只收敛和暴露哪些基础设置？
- 左侧导航与顶部 Tabs，在此弹窗中应该选择哪种作为内容分组层级？

### 10. skill-node

**规范覆盖度**: 完全

**关键规范点**:
- `skillnode-spec.md §1`: 节点原语基础衍生于 shadcn Card，明确要求圆角 `rounded-xl` (12px) 及常态采用 `border-border`。
- `skillnode-spec.md §2`: 极其明确地罗列了节点从 idle、running 到 breakpoint 共 6 种状态，各自要求使用的边框或 ring 颜色及状态指示点尺寸（`size-2.5`）。
- `design.md §2.4` / `skillnode-spec.md §4`: react-flow Handle 被明确指示调整为空心方形连接锚点 `!bg-background !border-2 !border-border`，选中时 `border-primary`。

**PM 需拍板的问题**:
- 节点描述/标题字符超长时，究竟是采用折行显示还是限制单行截断（并增加 Hover Tooltip）？
- 当触发 error 状态，详细的异常堆栈说明是否直接渲染在节点底部的伸展区中？

### 11. center-action-bar

**规范覆盖度**: 无

**未覆盖维度**:
- 视觉 token: 悬浮工具条使用的背板材料（如加重阴影加上 bg-card/bg-popover），工具条内嵌按钮大小（是否遵守 Toolbar 的 size-8 标准）。
- 交互行为: 该动作栏是常驻画面中心，还是基于用户选中的多节点产生的自适应悬浮位置？

**PM 需拍板的问题**:
- 工具条内部按钮的具体图标尺寸是否严格沿用左侧侧边栏已定的密度紧凑版（28px-32px）？
- 面板呈现是固定在视窗水平居中底部，还是始终跟随用户聚焦/框选的技能节点动态浮动？

---

### 总结

| 组件 | 覆盖度 | 主要 gap | PM 待决数 |
|---|---|---|---|
| CompilationWidget | 无 | 位置布局 / 状态色 token | 2 |
| Minimap | 部分 | 尺寸约束 / UI挂载位置及折叠交互 | 2 |
| GlobalShortcutShell | 无 | 弹窗尺寸 / Focus列表项高亮色 | 2 |
| Predict | 无 | 呈现形态（浮层或内嵌） / Diff单元格状态色 | 2 |
| publish-modal | 无 | 确认按钮语义色 / 二次校验防呆 | 2 |
| SubgraphInline | 无 | 画布嵌套交互方式 / 内嵌背景颜色级别 | 2 |
| edge-context-viewer | 无 | Tooltip与Popover的定性 / Hover触发机制 | 2 |
| diff-bubble | 无 | Split与Inline的选择 / Diff语义背景色谱 | 2 |
| SettingsModal | 无 | Modal最大宽度限制 / 内部分类导航结构 | 2 |
| skill-node | 完全 | 无 | 2 |
| center-action-bar | 无 | 悬浮条背景及阴影层级 / 按钮组件尺寸 | 2 |

**遗漏组件**:
在前台组件目录 (`apps/studio/frontend/src/components/studio/`) 下，还发现了另外 4 个规范设计并未覆盖但具有显著架构重量的核心 UI 组件需要被纳管审计：
1. **`micro-topology-panel` (微拓扑缩略面板)**：未在任何设计文档涉及，缺失与主图双向联动的行为标准。
2. **`predict-split` (批测拆分视图)**：批测页面的拆分骨架缺乏对其侧边把手宽度、背景分离度的规范定性。
3. **`SplitEditor` (拆分比对编辑器)**：涉及双栏比对代码，目前只有基础代码行号规定，缺乏拖拽把手及比对中分界线的视觉规范。
4. **`LazyMonacoPanel` (懒加载 Monaco 容器)**：缺失编辑器加载时的 Loading 骨架屏以及未命中文件时的空状态占位符规定。 
- 视觉 token / 布局: 组件位置（放在 Header 面包屑旁还是底部状态栏）、整体 高度/边距，以及加载态/错误态的颜色映射。

**PM 需拍板的问题**:

