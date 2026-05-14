# Requirements: Studio Canvas UI & Interaction Enhancements (v1)

## Source materials
- `docs/studio/ux_workflow/02_EDIT_AND_COMPILE.md:28-39` (§3.1 宏观: 全局起点 Input Node 与终点 Output Node)
- `.kiro/specs/studio-frontend-v2/requirements.md` (US-2.2: Input Node 推导 Schema)
- `.kiro/specs/studio-frontend-v2/requirements.md:40` (US-4.4: 点击连线 Edge 圆点唤起 Context 黑板透视)
- `.kiro/specs/studio-frontend-v2/requirements.md:82` (AC_FN_3: 触发执行后 Timeline 点击 Context JSON 查看器)
- `.kiro/specs/studio-frontend-v2/design.md:152` (Edge 圆点弹出 JSON Viewer)
- `docs/studio/ux_workflow/04_RUN_AND_TRACE.md:28-32` (§2.3 Edge Inspection 透视)
- `docs/studio/ux_workflow/05_DEBUG_AND_RESUME.md:28` (Edge Dot 展开 Context 并允许篡改)
- `docs/studio/ux_workflow/UI_SPEC.md:185` (§4.10 Edge inspector popover)
- `docs/studio/ux_workflow/02_EDIT_AND_COMPILE.md:44-48` (§3.2 中观: 处理 Subgraph 展开模式)

## 1. Background & motivation
现有的 Graph Canvas 初步实现了 Phase 节点的渲染与连线，但在具体交互体验和视觉隐喻上，尚未完全契合产品经理（PM）的工作心智。PM 需要一个不仅能表达“流程走向”的画布，更需要一个能清晰表达“全局数据从哪来、到哪去”，并且能在运行和调试时直观“透视”数据流状态的工作台。
本次 v1 改造的五条核心诉求（新增全局输入/输出节点、连线中点透视、子图内联展开按钮、移除冗余标题、连线去箭头）背后的统一动机是：**降低画布的视觉噪音，增强结构层级（宏观起点/终点与子图展开）的表现力，并为后续核心的运行时数据流透视（Context 查看器）埋下最直观的交互抓手。**让画布既符合 PM “看宏观蓝图”的心智，又赋予其“随时 Inspect 运行时上下文状态”的能力。

## 2. Goals / Non-goals

**Goals (本次目标)**:
- 补全 Skill 级别宏观拓扑语义，在画布中新增全局的 Input Node 和 Output Node。
- 升级连线 (Edge) 交互，移除视觉方向噪音（箭头），增加 Context 状态透视入口（中点圆点）。
- 升级 Subgraph 节点的交互隐喻，使用直观的“加号 (+)”图标按钮替代现有的文字按钮用于 Inline Expand（内联展开）。
- 精简视觉噪音，移除左上角冗余的 Title 框。

**Non-goals (非本次目标)**:
- Agent-Loop 微观拓扑展开（Micro-Topology）：本次只做 Subgraph 的 Inline Expand，Agent-Loop 内部的多步运转展示不在本次范围。
- Subgraph 双击下钻模式（Drill-down mode）：本次通过加号实现树状内联展开（Inline Expand），双击进入独立画布页面的下钻交互不在本次范围内。
- 连线中点的设计态高级编辑：在 Design-time (设计态)，连线上的 Context 没有真实运行数据，因此点击不应要求支持编辑，仅需提供占位交互或 Schema 预览。
- 工具栏锁功能改造：左下角工具栏的 Lock 按钮为 React Flow 的默认交互锁（禁用 pan/zoom/drag），本次不做业务改造，先原样保留，等待后续再规划。

## 3. User stories

**US-1: 全局输入输出节点 (Global Input/Output Nodes)**
As a 产品经理 (PM)
I want 画布上存在明确独立的“起点 Input Node”和“终点 Output Node”
So that 我可以直观地定义整个技能所需的初始原料（参数）和最终必须交付的产物（结果），并为全局 Context 提供明确的数据起点和终点。

**US-2: 连线数据透视入口 (Edge Context Dot)**
As a 产品经理 (PM)
I want 画布上节点间的连线去掉箭头，并且在连线中点显示一个圆点 (Edge Dot)
So that 我可以在视觉上减少方向箭头的干扰（流程方向由节点顺位自然表达），并通过点击圆点轻松查看两节点之间传递的 Context 数据卡片。

**US-3: 子图内联展开 (Subgraph Inline Expand)**
As a 产品经理 (PM)
I want 在包含子图 (Subgraph) 逻辑的节点底部看到一个显眼的“加号/减号 (+/-)”图标按钮
So that 我可以通过点击它，直接在当前主画布中原位展开/收起该子图的内部拓扑，而无需寻找不够直观的文字按钮。

**US-4: 简化画布视觉噪音 (Remove Redundant Title)**
As a 产品经理 (PM)
I want 移除当前画布左上角悬浮的 Title 标题框
So that 画布更加干净纯粹，因为标题已经在全局 Header 区域展示过，避免信息的重复与空间的浪费。

## 4. Acceptance criteria

### AC for US-1: 全局输入输出节点
- **When** 渲染 Graph Canvas 时
- **Then** 系统应在图中自动插入一个 `Input Node` (位于最上方/最左侧起点) 和一个 `Output Node` (位于最下方/最右侧终点)。
- **Shall** 确保所有业务的 Phase 节点都被正确地链接在这两个全局节点之间（或从 Input 开始，指向 Output）。

### AC for US-2: 连线数据透视入口
- **When** Graph Canvas 渲染节点之间的 Edge（连线）时
- **Then** 连线末端不应显示尖头 (Arrow head)，并且连线的中点位置应渲染一个可交互的圆点 (Edge Dot)。
- **When** PM 在 Design-time（设计时/未运行态）将鼠标悬停(Hover)在 Edge 圆点上时
- **Then** 界面应浮出一个轻量级提示或 Context Schema 的占位卡片。
- **When** PM 在 Run-time（运行后/拥有 Trace 数据态）点击该 Edge 圆点时
- **Then** 系统应在侧边或弹出层展示实际跑过的 Context JSON 详情查看器。

### AC for US-3: 子图内联展开
- **When** 画布中渲染类型为 `subgraph` 的节点时
- **Then** 该节点底部或边缘应渲染一个带有加号 (`+`) 图标的圆形按钮。
- **When** PM 点击处于收起状态的加号按钮时
- **Then** 图标变为减号 (`-`)，并原地将子图的拓扑展开显示在当前画布中 (调用 `SubgraphInline` 组件逻辑)。
- **When** PM 点击处于展开状态的减号按钮时
- **Then** 图标变回加号 (`+`)，并折叠隐藏内部拓扑。

### AC for US-4: 简化画布视觉噪音
- **When** 加载 Studio 的 Workspace 页面时
- **Then** Graph Canvas 区域左上角不应再渲染原本的 `Title` 组件/文本框。

## 5. Out of scope

- **Toolbar 锁定功能改造**: 针对用户疑问的“左下角工具栏的锁”，这是 `react-flow` 的 `Controls` 自带的 `interactive lock`，锁定后用于禁用画布的 Pan、Zoom 和节点 Drag 操作。当前阶段我们保留该原始行为，不为其增加额外的业务语义或移除。
- **运行态数据强制篡改功能 (Resume Edit)**: US-2 中只要求能在连线处唤起 Context 数据查看，至于在弹出面板里直接修改 JSON 并在断点处点击 `[ Resume ]` 续跑的能力，留在 Debug/Resume 专项实现，本次仅完成透视点入口与 UI 卡片调用的打通。
- **Agent-Loop 的微观拓扑图**: 复杂循环阶段（Agent-Loop）本身的微观展开本次不做。
- **Drill-down 下钻模式**: 本次只优化 Subgraph 的 Inline 展开体验，双击节点切换画布沙盒的 Drill-down 模式延后处理。

## 6. Open questions

1. **Input/Output 节点在画布上的布局排列**
   - *分歧点*: 新增的 Input 和 Output Node 是作为独立节点参与 dagre 自动布局，还是作为固定的悬浮锚点（固定在画布的极左/极右，或者极上/极下）？
   - *我的倾向*: 让它们作为普通节点参与 dagre 自动布局（树形顶端和底端）。
   - *理由*: 参与自动布局能够保证连线路由的自然与防重叠，如果作为绝对定位的悬浮块，在复杂图结构下连线追踪将变得极其困难，也违背了 React Flow 的排版心智。

2. **设计时 (Design-time) 点击 Edge Dot 的行为响应**
   - *分歧点*: 在没有真实运行 Context 数据的情况下（仅有设计态 Schema），点击 Edge Dot 是否需要弹出同样的 JSON Viewer，还是仅允许 Hover 提示？
   - *我的倾向*: Design-time 仅提供 Hover 的简单 Tooltip（提示“运行后可查看传递数据”），点击无响应或弹窗提示。
   - *理由*: 设计时两节点间的实际载荷并不存在，展示空的 JSON Viewer 容易给 PM 造成“有数据丢失”的误解，明确区分 Design-time 与 Run-time 交互可减少迷惑。
