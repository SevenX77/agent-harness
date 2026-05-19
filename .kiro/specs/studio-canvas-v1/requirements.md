# Requirements: Studio Canvas UI & Interaction Enhancements (v1)

## 1. Background & motivation
旧版 Canvas v1 实施后暴露了推导逻辑的严重错位。本次重构基于以下核心 Reset 动机：
1. **Manifest `depends_on` 是唯一真相**：取消缺乏数据支撑的隐式连线推导。
2. **I/O 节点作为 `depends_on` 一等公民**：全局 Input 和 Output 节点不再是游离的视觉装饰，它们与 Phase 节点对称地参与 `depends_on` 有向图关系。
3. **Compile Validation 拒孤立**：通过编译期校验拒绝“无入边且无出边”的孤立 Phase 节点，强制推行数据连通性。

## 2. Goals / Non-goals

**Goals (本次目标)**:
- I/O 节点与 Phase 对称参与 `depends_on` 连线计算。
- 引入编译期规则 `F-isolated-phase-not-allowed` 拒绝孤立节点。
- 连线 (Edge) 视觉回归 uikit 标准（平滑曲线、无箭头、状态驱动透明度），保留 Context 状态透视入口。
- Subgraph 内联展开的 `+` 图标升级，去 Title。

**Non-goals (非本次目标)**:
- 不对现有 V1 skill（如 story-deconstruction）做 Schema 的自动 codemod 或向后兼容。
- 隐式依赖推导（基于 prompt 变量的反查）。

## 3. User stories

**US-1: I/O 节点作为 `depends_on` 一等公民**
As a 产品经理 (PM)
I want 全局 Input 和 Output 节点能像业务阶段一样被 `depends_on` 显式引用
So that 数据流的起点和终点可以通过明确的连线表达，而不是靠前端自己瞎猜。

**US-2: 连线数据透视入口 (Edge Context Dot)**
As a 产品经理 (PM)
I want 画布上的连线没有方向箭头干扰，并带有主次层级 (如 uikit 那样)，且中点有一个圆点 (Edge Dot)
So that 流程由自上而下的树状布局自然表达，同时我能通过点击圆点轻松透视两节点之间的 Context 数据。

**US-3: 子图内联展开 (Subgraph Inline Expand)**
As a 产品经理 (PM)
I want 在包含子图逻辑的节点底部看到一个显眼的“加号 (+)”图标按钮
So that 我能原位展开子图内部拓扑，无需点击文字按钮。

**US-4: 简化画布视觉噪音 (Remove Redundant Title)**
As a 产品经理 (PM)
I want 移除当前画布左上角的 Title 标题框
So that 画布更加纯净。

**US-5: Compile-time validation 拒绝孤立 Phase 节点**
As a 系统框架 (Framework)
I want 编译期严格检查阶段的图连通性
So that 任何由于漏写 `depends_on` 而变成既无前置又无后继的孤立 Phase 都能在运行前被立刻拦截，保障数据流拓扑健康。

## 4. Acceptance criteria

### AC for US-1: I/O 节点作为 `depends_on` 一等公民
- **[H/H/A]** **When** 解析 Manifest 画连线时
  **Then** Phase 允许声明 `depends_on: ['global_input']`（或预定的输入标识符），而 `manifest.io` 允许声明 `depends_on: ['phase_x']` 来挂载 Output 节点。

### AC for US-2: 连线数据透视入口与 uikit 对齐
- **[H/M/A]** **When** Graph Canvas 渲染节点之间的 Edge 时
  **Then** 使用 `smoothstep` 曲线且无箭头。若目标节点活跃/成功则主干线 `--primary` 实心；否则 `--muted-foreground` 降低 `opacity`。
- **[H/H/A]** **When** 渲染连线中点时
  **Then** 显示 Edge Dot，Design 态 Hover 提示“运行后可查看”，运行态 Click 弹出 Context JSON。

### AC for US-3: 子图内联展开
- **[H/L/A]** **When** 渲染 `subgraph` 类型的节点时
  **Then** 底部悬浮 `+` 按钮，点击展开变为 `-` 且渲染 `SubgraphInline`。

### AC for US-4: 简化画布视觉噪音
- **[H/L/A]** **When** 加载 Studio Canvas 时
  **Then** 不存在画布左上角的 Title 组件。

### AC for US-5: Compile-time validation 拒绝孤立 Phase 节点
- **[H/H/A]** **When** 编译（compile）一个 Manifest 时
  **Then** 若发现某个 Phase 既无出边（未出现在任何节点的 `depends_on` 中）又无入边（自身 `depends_on` 为空），则触发 compile fail。
- **[H/H/A]** **Then** 报错信息应明确包含出问题的 Phase ID 及“Phase {id} has no in-edge and no out-edge; 孤立节点不允许”的具体提示。