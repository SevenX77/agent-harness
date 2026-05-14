# Design Specification: Studio Canvas UI & Interaction Enhancements (v1)

## 1. Overview
本设计文档基于 `studio-canvas-v1/requirements.md`，将产品层面的 4 个 User Stories 转化为针对前端（React Flow 11 + @xyflow/react + shadcn UI）的可落地组件与交互设计方案。重点解决了全局 Input/Output 节点引入、Edge 数据透视交互、Subgraph 内联展开等核心诉求，并对主控 PM 提出的实施细节歧义进行了最终方案拍板。

## 1.4 Scope of this v1
**重要 scope 决策**：由于底层的 trace WebSocket pipeline 目前暂未接通，本次实施严格区分为 v1 与 v2 两个阶段：
- **v1 (本 spec 实施范围)**:
  - 视觉改造：连线强制去箭头、移除左上角 Title 框、新增全局 Input/Output 节点、新增 Subgraph 的 `+/-` 按钮。
  - 连线中点 (Edge Dot)：实现 `ContextEdge` 组件并在曲线上挂载 Edge Dot（design-time 状态呈现为空心虚灰）。支持 Hover 时显示 `运行后可查看传递数据` 的 Tooltip，Click 行为在设计态无响应。
  - 数据模型：定义完整的 `ContextEdgeData` 接口并留出 `hasTraceData` 与 `contextJson` 字段作为占位。
- **v2 (推迟，本 spec 不实施)**:
  - Trace Store 及 WebSocket 订阅，并将实际的 `contextJson` 注入到边数据中。
  - 运行态 (Run-time) 的 Edge Dot 实体紫高亮，以及点击后弹出的 Monaco JSON Viewer (`Popover`) 组件集成。

## 1.5 Architecture
系统数据流与组件架构如下：
```mermaid
flowchart TD
    M[manifest (后端 skills.py)] --> P[phasesFromManifest + buildNodes/buildEdges (GraphCanvas.tsx)]
    P --> RF[React Flow (nodes/edges state)]
    RF --> CN[CustomNodes: SkillNode / InputNode / OutputNode / SubgraphNode]
    RF --> CE[CustomEdges: ContextEdge with EdgeLabelRenderer dot]
    CE -. v2 .-> EC[EdgeContextCard: Popover + readonly Monaco]
    TS[Trace Store] -. v2 subscribe trace events .-> CE
```

## 2. 界面与组件设计

### 2.1 新增全局 Custom Nodes (`InputNode` / `OutputNode`)
为了满足 US-1，在 `react-flow` 中注册两种全新的 `nodeTypes`:
- **UI 呈现 (P1-5 视觉方案拍板)**: 采用 **选项 A** (复用 skillnode-spec 标准 Card + 顶部 1px 实色条：`border-t-2` 配合 `--primary` 用于 Input，`--muted-foreground` 用于 Output)。
  - *理由*：这种方案最大程度复用了现有的 Node Card 骨架与阴影规范，仅通过极小成本的顶边颜色线（Top Accent Border）就能与普通的业务阶段节点拉开视觉差异，克制且优雅。
- **内容展示 (P1-2 决策)**: 节点内部直接渲染 `manifest.io.inputs` (或 `outputs`) 的第一层 Schema 字段列表。每个字段显示名称和类型 Badge（如 `string`, `number`）。
- **交互行为**: 纯只读展示。PM **不可**在节点上直接修改 Schema 表单。提供一个 `[ 放大查看 JSON ]` 的图标按钮，点击通过只读 Monaco Viewer 查看完整的嵌套 Schema。

### 2.2 增强连线 Custom Edge (`ContextEdge`)
针对 US-2，在 `react-flow` 注册自定义边 `ContextEdge`：
- **去箭头 (P1-4 决策)**: 彻底移除箭头。无论是 `buildEdges` 初始化渲染，还是拖拽生成的 `onConnect`，统统不设置 `markerEnd` 属性。
- **Edge Dot 渲染**: 使用 `EdgeLabelRenderer` 在曲线中点（通过 `getBezierPath` 的坐标返回值）挂载一个可交互的 `<button>` 圆点。
- **视觉全态规范 (P1-3 决策)**:
  - **Design-time (未运行态)**: 边与圆点均使用 `--muted-foreground` 颜色。圆点为空心环或半透明背景，表示“占位但无数据”。
  - **(v2) Run-time (成功跑过，有 trace)**: 边与圆点高亮为 `--primary`（深紫），圆点实色填充。

### 2.3 边数据透视卡片 (`EdgeContextCard`)
当 PM 点击 Run-time 态的 Edge Dot 时，弹出透视卡片：
- **(v2) 组件复用**: 桌面端使用 shadcn `Popover` (锚点在 Dot 上)，右侧展示受限时降级为 `Sheet`。
- **(v2) 内部视图**: 直接挂载 `readonly` 的 Monaco Editor 实例，渲染这段边传输的上下文 JSON。
- **Design-time 点击行为 (OQ-2 决策)**: 设计态（无真实 Context 数据时）点击圆点**无响应**。PM `Hover` 圆点时，展示轻量级 Tooltip：`运行后可查看传递数据`。

### 2.4 子图内联展开 (`SubgraphNode` 改造)
满足 US-3，改造现有的 Subgraph 自定义节点：
- **UI 变化与视觉规范**: 移除旧的“展开/收起”文字按钮。在节点底部的垂直居中边界处悬浮一个小圆按钮。
  - **Size**: `size-5` (20px宽长，比常规 Handle 稍大以便点击)。
  - **Color**: 复用令牌 `bg-card`，边框 `border-border`，hover 时为 `border-primary`。
  - **Position**: `absolute` 锚定在底部 (`Position.Bottom`)，垂直位置稍偏下以避开自带的连线 Handle。
  - **Icon**: 使用 lucide-react 的 `Plus` / `Minus`。
  - **A11y**: `aria-label="展开子图"` / `"收起子图"`。
- **双击行为防冲突 (P1-5 决策)**: 对于 Subgraph 节点本身，**双击事件静默拦截（无响应）**。此举严格隔离单次点击“+”号的 Inline Expand 行为与未来可能的 Drill-down 双击下钻行为，防止由于系统级双击判定引起的 UI 闪烁。

## 3. Data Model
扩展 React Flow 元素的 `data` payload：

1. **Input/Output Node Data**:
   ```typescript
   type GlobalNodeData = {
     type: 'global-input' | 'global-output';
     schema: JSONSchema; // 从 manifest.io 映射
   };
   ```
2. **ContextEdge Data**:
   ```typescript
   type ContextEdgeData = {
     hasTraceData: boolean;      // 区分 design-time vs run-time (v1 始终为 false)
     contextJson?: any;          // 如果 hasTraceData 为 true，存放具体黑板内容或其引用
     sourcePhaseId: string;
     targetPhaseId: string;
   };
   ```

## 4. 关键交互流程与生命周期

- **Flow A (初始化与布局)**: PM 打开 skill → Canvas 挂载 → 拉取 manifest → `buildNodes` 组装并插入 Input + N phase + Output 节点 → `buildEdges` 按 P1-1 自动推导链接 → dagre 自动布局引擎计算坐标 → 渲染。
- **Flow B (设计态 Edge 交互)**: PM hover 连线中点的 Edge Dot (design-time 状态) → 触发显示 Tooltip "运行后可查看传递数据" (点击无响应)。
- **(v2) Flow C (运行态 Edge 透视)**: PM click edge dot (run-time, 有 trace 数据) → ContextEdge 检查 `data.hasTraceData=true` → 触发 Popover 弹出 → 加载 Monaco editor 组件 → 渲染 `contextJson` 数据。
- **Flow D (子图内联展开)**: PM click Subgraph 节点底部的 "+" button → 节点内部状态切换为 expanded → 节点底部内嵌渲染 `SubgraphInline` 子组件 → 节点视觉高度增加 → 触发 dagre 重新排版图节点 → 平滑过渡至新布局。

## 5. 实施细节与决策记录 (Decision Log)

| 争议点 / 实施细节 | 最终决策方案 | 决策理由 |
| :--- | :--- | :--- |
| **P1-1: Input/Output 如何链接 Phase** | **纯自动推导**。无 `depends_on` 前置的 phase 自动连 Input；未被其他 phase `depends_on` 的自动连 Output；空画布则 Input 直连 Output。 | 减免 PM 在 manifest 中繁琐手动连线的负担，DAG 拓扑天然能推导绝对的起点与终点边界。 |
| **P1-2: I/O 节点展示内容与交互** | 展示首层 Schema 字段名 + 类型 Badge；纯只读，仅提供查看完整 JSON 的入口。 | PM 应在左侧或全局设置配 Schema，而不是把画布节点当成庞大的编辑表单，保持节点小巧纯粹。 |
| **P1-3: Edge Dot 视觉** | Design-time 灰边空心(`--muted-foreground`)；(v2) Run-time 高亮实体紫(`--primary`)。 | 严格遵循 `tokens.md` 语义，让 PM 通过眼角余光就能判断“这条链路数据有没有真跑通”。 |
| **P1-4: 去箭头范围** | 初始渲染 (`buildEdges`) 与拖拽连线 (`onConnect`) 均**强制去箭头**。 | 维持全局 UI 的极致简约。在自上而下布局的有向无环图中，连线顺位就是自然的方向。 |
| **P1-5: Subgraph 双击行为** | **静默拦截无响应**。 | 单击“+”负责本页内联展开；双击事件留白给未来的 Drill-down 全屏下钻，避免交互偶合灾难。 |
| **OQ-1: Input/Output 节点定位** | **作为普通节点参与 dagre 自动布局**。 | *(反驳悬浮锚点倾向)* 强行绝对定位悬浮锚点极易在复杂图中让长连线野蛮穿透中间业务节点。参与 dagre 布局天然享有防重叠路由计算，更符合流式查阅心智。 |
| **OQ-2: Design-time Edge Dot 行为** | **Hover Tooltip 提示，Click 无弹窗响应**。 | 没有数据硬弹空 JSON Viewer 只会制造焦虑（“我是不是配丢数据了”），明确能力边界。 |

## 6. Migration / 改造步骤

1. **`GraphCanvas.tsx` (现有改造)**:
   - 移除左上角 `Title` UI 渲染区 (US-4)。
   - `buildNodes`: 新增逻辑，基于 `manifest.io` 组装并压入一个 Input node 和一个 Output node 对象。
   - `buildEdges`: 
     - 新增推导逻辑连接全局节点 (按 P1-1)。
     - 边类型统一替换为 `'contextEdge'`。
     - 删除所有的 `MarkerType.ArrowClosed` 配置 (按 P1-4)。
   - `nodeTypes` / `edgeTypes` 字典：注册三个新组件。
2. **`components/nodes/GlobalInputOutputNode.tsx` (新增)**:
   - 实现 Input / Output 节点的 UI ( 选项A Card + Schema list )。
3. **`components/edges/ContextEdge.tsx` (新增)**:
   - 实现包含 Edge Dot 和 Tooltip 的组件骨架。**(注：v1 仅需接入 Tooltip 与 Popover 的关闭占位，无需接入 trace store 逻辑)**。
4. **`components/nodes/SubgraphNode.tsx` (现有改造)**:
   - 删除文本按钮，替换为绝对定位的底部 `+`/`-` Icon Button，并去除双击事件透传 (US-3, P1-5)。

## 7. Testing Strategy
- **Unit (Vitest)**: 针对 `buildEdges` 中的自动推导逻辑 (P1-1) 编写单元测试，覆盖正常串行、并行分叉、单节点及空节点这 4 种边界场景的边生成正确性。
- **Component (Storybook/Vitest)**: 验证 `ContextEdge` 在 `hasTraceData=false` Props 输入下的渲染状态（Dot 颜色与 Hover 响应变化）。
- **(v2) E2E (Playwright)**: 待 v2 实施后，在真实 Skill 中加载包含 trace 的运行历史，断言 Edge Dot 点击后弹出的 DOM 中包含正确的 Monaco 内容。
