# canvas-topology (studio feature) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: React Flow 画布微观 / 宏观拓扑展现、节点连接、布局流
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

画布主体由 `GraphCanvas` 承载，视觉层使用 React Flow 的背景、控制器和 MiniMap，入口在 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:177` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:222`。组件把画布初始化为 `fitView`，限制缩放在 0.2 到 1.5，并在初始化时再次 `fitView({ padding: 0.2 })`，所以用户打开 skill 后默认看到完整拓扑而不是局部节点。

节点类型分为全局输入、全局输出、普通 skill phase 三类。`nodeTypes` 映射在 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:37` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:41`，输入/输出节点由 `GlobalInputOutputNode` 展示，普通节点由 `SkillNode` 展示。普通节点视觉区分 `logic`、`agent`、`subgraph`，并显示 phase 名称、类型标签、状态和子图入口，来源见 `apps/studio/frontend/src/components/nodes/SkillNode.tsx:42` 到 `apps/studio/frontend/src/components/nodes/SkillNode.tsx:52`、`apps/studio/frontend/src/components/nodes/SkillNode.tsx:62` 到 `apps/studio/frontend/src/components/nodes/SkillNode.tsx:123`。

选中态当前体现在节点容器 ring 上，`selected` 为真时使用 `ring-2 ring-primary`，见 `apps/studio/frontend/src/components/nodes/SkillNode.tsx:62` 到 `apps/studio/frontend/src/components/nodes/SkillNode.tsx:67`。画布自身维护 `selectedCanvasNodeId` 并同步外部 `selectedNodeId`，对应 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:59` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:61`、`apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:130` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:132`。

边使用自定义 `ContextEdge`，但当前只是 1.5px 基础曲线加中点按钮，不存在审计 High-001 提到的 animated gradient，也没有“handle hidden until hover”。`BaseEdge` 样式只有 strokeWidth，见 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:35` 到 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:37`；按钮只是一个小圆点，见 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:39` 到 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:60`。Handle 在节点上始终渲染，并固定 `size-2.5`，见 `apps/studio/frontend/src/components/nodes/SkillNode.tsx:74`、`apps/studio/frontend/src/components/nodes/SkillNode.tsx:124`、`apps/studio/frontend/src/components/nodes/GlobalInputOutputNode.tsx:28` 到 `apps/studio/frontend/src/components/nodes/GlobalInputOutputNode.tsx:31`。

边中点按钮的文案是“查看连线传递数据”，但点击处理当前只 `stopPropagation`，不会打开 inspector 或请求 trace 数据，见 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:48` 到 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:59`。这与 system-level 的 Trace/Edge Inspection 缺口一致，详见 [ux-workflow baseline](../../system-level/ux-workflow/baseline.md)。

## 前端逻辑

`GraphCanvas` 从 `SkillDetail` 推导节点和边：节点由 `buildNodes` 生成，边由 `buildEdges` 生成，再交给 dagre 自动布局，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:93` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:111`。布局结果再同步给 `useNodesState` / `useEdgesState`，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:112` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:121`。

布局算法在 `apps/studio/frontend/src/lib/layout.ts:23` 到 `apps/studio/frontend/src/lib/layout.ts:65`。它创建 dagre graph，固定方向 `LR`，设置 `nodesep`、`ranksep`、边距和节点尺寸，然后把 dagre 输出的中心点换算成 React Flow 左上角坐标。`compact` 模式只改变水平偏移，见 `apps/studio/frontend/src/lib/layout.ts:50` 到 `apps/studio/frontend/src/lib/layout.ts:65`。

环检测发生在布局前。`graphlib.alg.isAcyclic` 为 false 时抛出 `CycleDetectedError`，见 `apps/studio/frontend/src/lib/layout.ts:45` 到 `apps/studio/frontend/src/lib/layout.ts:47`；`GraphCanvas` 捕获后 toast “Canvas layout skipped”，并保持原始节点/边，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:102` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:128`。

V2.1 manifest 的 `graph.phases` 会被转成逻辑 phase 节点，旧 graph/agent 结构也有 fallback。转换入口见 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:20` 到 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:29`，旧 graph 和 agent fallback 见 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:32` 到 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:102`。普通 phase 节点数据包含 `filePath`、`dependsOn`、`llmRole`、`tools`、`subagents` 和 `subgraphPath`，见 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:162` 到 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:184`。

边构建逻辑以 `dependsOn` 为主，没有依赖的 phase 连到全局输入，没有被依赖的 phase 连到全局输出。实现见 `apps/studio/frontend/src/components/nodes/buildEdges.ts:23` 到 `apps/studio/frontend/src/components/nodes/buildEdges.ts:49`。所有 phase 间边都标记 `type: "contextEdge"`，但 `hasTraceData` 固定为 false，见 `apps/studio/frontend/src/components/nodes/buildEdges.ts:8` 到 `apps/studio/frontend/src/components/nodes/buildEdges.ts:20`。

交互逻辑包括点击/拖拽选中节点、双击输入输出节点打开 `io/inputs.json` 或 `io/outputs.json`、双击普通 skill 节点打开 `phases/<id>/<id>.md`。这些行为在 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:185` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:210`。连线时只更新前端 `phaseNodes` 的 `dependsOn` 本地状态，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:135` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:151`。

## 后端功能

Canvas 本身没有专属后端服务。它消费 Studio skill 详情、文件内容、manifest 结构和运行状态，这些由 workspace 与 skill detail API 提供。画布需要的 `SkillDetail` 类型包含 `manifest`、`files`、`topology` 等字段，见 `apps/studio/frontend/src/api/types.ts:383` 到 `apps/studio/frontend/src/api/types.ts:403`。

后端当前不持久化画布上的新增连线。`onConnect` 的 `dependsOn` 更新停留在 React state，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:135` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:151`；没有对应的 `writeSkillFile` 或 manifest patch 调用。因此 Canvas 可以临时展示新边，但刷新或重新加载后会回到文件中的 manifest。

运行状态依赖 run stream 或 workspace 状态传入 `statusByNodeId`，`GraphCanvas` 只把它透传给节点。该 prop 定义在 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:25` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:35`，节点数据写入在 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:162` 到 `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:184`。

## API

Canvas 直接使用的 API 是 skill detail 和文件打开链路，不直接调用后端。`getSkillDetail` 定义在 `apps/studio/frontend/src/api/client.ts:157` 到 `apps/studio/frontend/src/api/client.ts:160`，写文件 API 定义在 `apps/studio/frontend/src/api/client.ts:162` 到 `apps/studio/frontend/src/api/client.ts:173`，但当前连线操作没有调用写文件。

后端 skill detail endpoint 是 `GET /api/skills/{skill_id}`，见 `apps/studio/backend/app/routers/skills.py:98` 到 `apps/studio/backend/app/routers/skills.py:105`。编译 endpoint 是 `POST /api/skills/{skill_id}/compile`，见 `apps/studio/backend/app/routers/skills.py:108` 到 `apps/studio/backend/app/routers/skills.py:118`，它会影响画布周边的 compile error 面板，但不是拓扑本身的 API。

## Data Model / State

React Flow 的状态由 `useNodesState` 与 `useEdgesState` 管理，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:112` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:113`。额外 UI 状态包括 `expandedSubgraphs`、`selectedCanvasNodeId` 和 `canvasHeight`，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:59` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:61`。

节点源模型来自 `SkillDetail.manifest`。V2.1 `GraphManifestV21`、旧 `GraphSkillDef`、`AgentSkillDef` 等类型定义在 `apps/studio/frontend/src/api/types.ts:277` 到 `apps/studio/frontend/src/api/types.ts:381`。`GraphCanvas` 当前把 V2.1 `graph.phases` 视作 phase 列表，但不会在 Canvas 内直接编辑 manifest 文件。

边状态当前只在前端内存中计算和变更。`buildEdges` 从 `dependsOn` 建依赖边，并补齐 input/output 边，见 `apps/studio/frontend/src/components/nodes/buildEdges.ts:28` 到 `apps/studio/frontend/src/components/nodes/buildEdges.ts:49`。边数据结构携带 `sourcePhaseId`、`targetPhaseId`、`hasTraceData`、`contextJson` 字段，见 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:5` 到 `apps/studio/frontend/src/components/edges/ContextEdge.tsx:10`，但后两个字段当前没有被 run trace 填充。

## Cross-feature interaction

与多文件编辑器的交互：双击节点会触发 `onFileOpen`，并切换右侧 panel 到 inputs 或 properties，见 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:198` 到 `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:210`。多文件编辑器如何打开和保存文件见 [multi-file-editor baseline](../multi-file-editor/baseline.md)。

与 trace visualization 的交互：边按钮和 `ContextEdgeData` 已经预留 trace/context 字段，但当前没有 edge inspector，`hasTraceData` 也固定 false，见 `apps/studio/frontend/src/components/nodes/buildEdges.ts:8` 到 `apps/studio/frontend/src/components/nodes/buildEdges.ts:20`。Trace 面板和 run stream 见 [trace-visualization baseline](../trace-visualization/baseline.md)。

与 Copilot 的交互：Canvas 选中节点可以成为 Copilot 上下文的一部分，但当前 Copilot context hook 发送的是通用 view/context JSON，不是边或节点级 payload，见 `apps/studio/frontend/src/hooks/useCopilotContext.ts:48` 到 `apps/studio/frontend/src/hooks/useCopilotContext.ts:62`。@ mention 的缺口见 [copilot-assistance baseline](../copilot-assistance/baseline.md)。
