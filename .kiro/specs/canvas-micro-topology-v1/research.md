---
spec: canvas-micro-topology-v1
status: Draft
last_updated: 2026-05-19
linked_level3_docs:
  - docs/studio/UX_WORKFLOW_BLUEPRINT.md
---

# Research: Canvas Micro-Topology Expansion

## 1. 业内方案调研

### 1.1 n8n: 节点 Sub-workflow 展开
- **怎么做的**: n8n 允许一个节点作为一个 `Sub-workflow`（类似于我们的 Subgraph）。在其较新的 UI 中，双击或点击该节点，不会在当前画布强行嵌套渲染（防止爆炸），而是采用**下钻 (Drill-down)** 模式，整个画布切换为子图的视图，顶部通过面包屑 (Breadcrumbs) 显示层级。参见其官方文档中对 Execute Workflow Node 的描述。
- **关键设计决策**: 使用 Drill-down 而非 Inline Expand，极大简化了缩放逻辑和 DOM 节点数，牺牲了部分全局上下文的可见性。
- **能借鉴什么**: 对于深度嵌套的 Subgraph，下钻加面包屑是最佳兜底方案。我们可以对 Agent-Loop 内的有限步骤采用内联展开 (Inline Expand)，而对另一份 `SKILL.md` 的完全嵌套采用下钻。

### 1.2 LangSmith: Runs/Spans 嵌套渲染
- **怎么做的**: LangSmith 在其 Trace UI (`https://smith.langchain.com/`) 中，将一次完整的链式调用渲染为一个极深的树状目录。展开一个 Span（如 `AgentExecutor`），会列出内部的 `Tool`, `LLM`, `Parser` 等子 Span，并带有明确的时长条和 Token 消耗角标。
- **关键设计决策**: 这是一个纯竖向的 Tree 结构，不使用图布局（DAG），因此极易处理多层嵌套，性能极佳。
- **能借鉴什么**: 我们在画布节点中“展开” Agent-Loop 内部步骤时，可能不应该强行将其渲染为一组横向或纵向的复杂连线图，而是在放大的原节点框内部，嵌一个类似 LangSmith 的、纯竖向紧凑的“执行步骤时间轴 (Mini-Trace)”，这在 UX 上清晰得多。

### 1.3 React Flow: Group 与 Subflow 官方实现
- **怎么做的**: `@xyflow/react` 原生支持 `parentId` 属性。将一个节点的 `parentId` 设为另一个框节点，它就会在这个框内渲染，跟随父框拖动。官方提供了 Subflow 案例 (`https://reactflow.dev/examples/layout/subflows`)。
- **关键设计决策**: 必须开启 `extent: 'parent'` 来限制子节点拖拽出父框。父节点的尺寸计算需要动态依赖子节点的内容。
- **能借鉴什么**: 技术基建完全对齐。如果我们在前端实施内联展开，只需动态地向 nodes 数组注入一批带有目标 `parentId` 的新节点，并利用 `react-flow` 的重新布局算法排版即可。

### 1.4 VS Code: Outline / Breadcrumb
- **怎么做的**: VS Code 1.95 的 Outline view 用 `vscode.window.createTreeView` API 渲染代码折叠层级，通过 `workspaceState` 持久化记录用户折叠了哪些层级，使得重启或切文件后状态依然保持。
- **能借鉴什么**: 我们微观节点展开的状态（展开了哪些，合拢了哪些）必须记录在 React Context 或本地 localStorage 中，不能因为切了一下 Tab 或重跑一次 Predict，所有节点又缩回去了，这会让 PM 抓狂。

## 2. 现仓库 Codebase 状态

通过 `file:line` 对当前 codebase 进行扫描：

- **前端 React Flow 基建**: 在 `apps/studio/frontend/src/components/GraphCanvas.tsx:12` 中，目前已经引入了 `@xyflow/react` 的 `useNodesState`。但在 `apps/studio/frontend/src/CustomNodes.tsx:1` 开始的代码中，只定义了粗粒度的节点，**没有**定义 `AgentStepNode` 或 `SubflowWrapperNode`。当前画布渲染仅支持 flat（平铺）的一维节点数组，没有任何利用 `parentId` 的微观拓扑空壳或 stub。*(推断前端微观渲染实现度为 0%)*。
- **后端 Event Push**: 在 `apps/studio/backend/app/routers/runs.py:27` 中存在 `run()` 和 `predict()` 的路由。在 `apps/studio/backend/app/services/run_manager.py` (推测路径) 中，底层会向外抛出事件，但由于当前日志颗粒度较粗，暂未发现将诸如 `update_working_memory`, `tool_call`, `nudge` 等内部极其细微的子步骤构造成树形 JSON push 到前端的具体聚合逻辑代码。*(推断后端微观数据装配实现度较低，主要以打平的 Log 为主)*。

## 3. 前后端 Payload schema 探索 (本 spec 推荐)

在传递微观层级的事件时，后端向前端推流的 Payload Schema 有两种典型的设计流派：

### 候选方案 A: 打平的增量 Event 流 (Flat Event Stream)
后端只管按发生的时间顺序吐出一个个小事件，前端负责在本地内存中还原出一棵树。
```typescript
interface TraceEvent {
  eventId: string;
  type: "PHASE_START" | "TOOL_CALL" | "NUDGE";
  parentId?: string; // 如果为空，则是顶层节点；如果有，则属于微观子节点
  data: any;
}
```
- **Pros**: 实时性最好，后端无状态压力，流式推送极其丝滑。
- **Cons**: 前端负担极重。需要维护复杂的 Redux/Zustand reducer，根据 `parentId` 动态插入和寻找微观节点。如果中途 WebSocket 断开丢包，整棵树结构可能错乱。

### 候选方案 B: 嵌套树状聚合下发 (Nested Snapshot)
后端每次阶段性完毕（或节点挂起时），向前端下发当前整个 Phase 的完整树状快照。
```typescript
interface PhaseSnapshot {
  phaseId: string;
  status: "running" | "paused_on_nudge" | "success";
  microSteps: Array<{
    stepId: string;
    type: "plan" | "tool_call" | "llm_reply" | "validator";
    status: string;
    nudgeCount?: number;
    details: any;
  }>;
}
```
- **Pros**: 前端极度简单，收到什么画什么（直接塞给 React 渲染）。状态永远一致。
- **Cons**: 如果内部包含大量的 Token 文本或大量工具调用日志，Payload 会非常庞大，每次全量下发浪费带宽。

## 4. 关键技术决策点

在后续进入 Design 阶段时，必须由架构师/PM 拍板以下决策：
1. **渲染形式决断**: 对于 Agent-Loop 节点，展开时是使用 `React Flow` 的真实节点在画布里画图，还是在该框内部直接渲染一个纯 React DOM 的**竖排列表时间轴**（类似 LangSmith）？
2. **状态维护**: 使用增量更新流（候选方案 A），还是树状快照覆盖（候选方案 B）？
3. **嵌套限制**: 如果一个 Subgraph 里面又嵌套了 Subgraph，画布最多允许原地 Inline 展开多少层？超过该层数是否强制退化为双击下钻 (Drill-down) 打开新 Tab？

## 5. 推荐方向

基于上述 Research，我个人的初步推荐如下（供后续 design 参考）：
- **关于渲染形式**: **强烈倾向于在 Agent-Loop 节点内使用纯 DOM 竖向列表 (LangSmith 风格) 进行微观展开**，而不是强行用 React Flow 节点去连线。因为一次 Agent 循环就是线性的 “思考 -> 调工具 -> 答复 -> 校验”，用树/列表表达最清晰，能避免极度复杂的画布节点避让重排。
- **关于状态维护**: **推荐方案 B (快照覆盖)**。考虑到 MVP0 阶段的开发速度，让前端背负过于复杂的树重组逻辑风险太高。牺牲少许局部带宽，换取绝对不会出现结构错乱的前端渲染，在性价比上是最优的。

## 相关文档
- [UX_WORKFLOW_BLUEPRINT.md](../../../docs/studio/UX_WORKFLOW_BLUEPRINT.md)
- [GRAPH_EXECUTION_MODEL.md](../../../docs/engine/GRAPH_EXECUTION_MODEL.md)
