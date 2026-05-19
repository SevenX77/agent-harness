# Design Specification: Studio Canvas UI & Interaction Enhancements (v1)

## 1. Overview
这是一次基于数据一致性原则的设计 Reset。本次重构的基调是：“manifest 的 `depends_on` 数组是画线的唯一真相；I/O 节点是一等公民；不允许任何隐式推导和孤立节点”。所有的前端渲染都将严格镜像后端的编译期有向无环图，彻底解决假并联和隐式连线的乱象。

## 2. 界面与组件设计

### 2.1 I/O 节点作为 depends_on 一等公民 (`InputNode` / `OutputNode`)
- **镜像参与连线 (mirror semantics)**: Input 和 Output 节点不再是脱离 `depends_on` 体系的游离块。Output 用 `manifest.io.depends_on` 反向声明上游 phase；Input 通过被 Phase 在 `phase.depends_on: ['global_input']` 正向引用进入图。两者语义是 mirror 不是 strict symmetric — 但都在同一个 depends_on 数组系统里描述, 画线机制统一。
- **Output Hook 机制**: 采用方案 (a) 对称机制。在 `manifest.io` 对象级新增一个加性字段 `depends_on: list[str]`，代表最终 Output 节点所依赖的前置 Phase。这维持了有向无环图定义的高度一致性。
- **空 Manifest 的 Dagre 渲染**: 当 Manifest 内只有 0 个 Phase 时（仅存在 Input 和 Output 两个节点），Dagre 布局应当退化成垂直排列（Input 顶，Output 底），且由于无连线，它们分别作为两个卡片垂直居中呈现。

### 2.2 视觉完全对齐 uikit 的 Custom Edge (`ContextEdge`)
- **无箭头 & 平滑**: `defaultEdgeOptions={{ type: "smoothstep" }}` 并且禁止渲染 `markerEnd`。
- **状态驱动的主次视觉**: 关键主路径（Target 为 running/success/paused/breakpoint）使用 `animated: true`, `stroke: "var(--primary)"`；副路径/未激活（Target 为 idle）使用 `opacity: 0.5`, `stroke: "var(--muted-foreground)"`。
- **Edge Dot**: 在曲线中心点保留圆点设计。设计态空心虚灰，运行态实心紫。Hover 提示，Click 在无真实 Context 时无弹窗。

### 2.3 子图与噪音清理
- **Subgraph 内联**: 节点底部绝对定位 `size-5` 的 `+`/`-` 按钮。
- **去 Title**: 彻底移除画布左上角 Title DOM 节点。

## 3. Data Model
- **Schema 扩展 (Additive)**: 在 `SkillManifest.io` (`IoDeclaration` pydantic model) 下新增字段 `depends_on: list[str] = Field(default_factory=list)`。此为纯加性扩展，不产生 Breaking Change，确保 Output 节点作为 `depends_on` 一等公民的语义落地。

## 4. 实施细节与决策记录 (Decision Log)

| 争议点 | 最终决策方案 | 三轴评级 | 决策理由 |
| :--- | :--- | :--- | :--- |
| **P1-1: 连线推导规则** | manifest 的 `depends_on` 数组是画线的唯一真相；不论 Phase ID 还是 `global_input`/`global_output` 都一致处理；不做任何隐式推导 / fallback。 | [H/H/A] | 让 UI 绝对忠实于数据，杜绝瞎猜。 |
| **P2-2: I/O 节点的地位** | I/O 节点是 `depends_on` 的一等公民 (Output 反向声明 / Input 正向被引用, mirror 语义)。 | [H/M/A] | 使整个图的边定义逻辑一致。 |
| **P3-1: Edge 视觉规范** | 回归 uikit：无箭头，smoothstep，按目标节点状态定主次虚实。 | [H/L/A] | 优秀的视觉隐喻不应被丢弃。 |
| **P4-1: 孤立节点的 Compile Validation** | 属于 Cross-spec 依赖。复用现有的 semantic checks 机制，在 `packages/graph-agent/src/graph_agent/core/validators/` 目录下新增一个如 `check_isolated_phase.py` 的校验器，并在 `compiler.py` 的主执行流中挂载。 | [H/H/A] | 孤立节点直接在编译期拒绝，彻底切断了前端需要考虑“完全没连线的卡片散落一地”的极端场景。由于已通过代码 grep 实证了 `compiler.py` 的实际扩展机制，方案置信度为 A。 |

## 5. 迁移与向下兼容 (V1 Skill 影响)
- **V1 老 Skill 崩溃预期**: canvas-v1 上线后，现有的基于隐式顺序执行且未声明 `depends_on` 的老 Skill（如 `story-deconstruction`）将会因为触发孤立节点规则而 **全部 compile fail**。
- **无自动化 Codemod**: 系统不提供迁移脚本或默认的顺序 `depends_on` 推断。PM 需视情况手动给 V1 skill 补充 `depends_on`，或者暂不使用 Canvas v1 渲染该技能。强制 Schema 演进（将 `depends_on` 从 Optional 变为 Required 等结构性突变）推迟到未来的独立 Spec 进行。
