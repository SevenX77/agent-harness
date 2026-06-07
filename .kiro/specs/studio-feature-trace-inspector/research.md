---
spec: studio-feature-trace-inspector
status: Draft
last_updated: 2026-06-01
linked_level3_docs:
  - docs/studio/02_features/trace-inspector/baseline.md
  - docs/studio/02_features/trace-inspector/mvp0-alignment.md
---

# Research: Trace Inspector Redesign

This document conducts deep industry research, audits the current codebase status, and analyzes the structural schema options to formulate an outstanding MVP0 trace and state inspection architecture.

> **决策更新 (2026-06-01, v2 — 修正前一版误判)**: 经更深一层实测,**state 查看本身现在就能做** —— `phase_start`/`phase_end` 事件携带完整黑板快照 `context={inputs, phase_outputs, scratch}`([`events.py`](../../../packages/graph-agent/src/graph_agent/callbacks/events.py),真实样本 `.workspace/runs/dca08b4d…/trace.jsonl`)。因此 §3 讨论的「边原点状态查看」属本 spec **核心且现在可做**。
> 真正缺数据的**只有结构化「前后态 DIFF」**(added/modified/deleted,需引擎 emit reducer 级差异)—— 这是低优先的次级优化,登记 [`deferred-items.md`](../../../docs/deferred-items.md) DEF-001。§3 的行 Diff vs 键 Diff 抉择**待 DIFF 立项后再议**;当前先把**真实 state 接进来替换 mock**(`ContextEdge.getMockEdgeContext()`)。
> 注:本 spec 由 `trace-and-predict-visibility` 改名合并而来,是运行追踪的唯一权威 spec(非"移交")。§1/§2 作为实现背景保留。

## 1. 业内方案调研 (Industry Research)

### 1.1 LangSmith: LLM Spans & Prompt Playground Integration
- **怎么做的**: LangSmith (`smith.langchain.com`) 是大语言模型 (LLM) 事件追踪领域的标杆。它的调试控制台支持两个核心交互：
  1. **级联 Span 列表**：通过折叠树型渲染出每一次运行 (Run) 所经过 of Phase 和 LLM 阶段，附带运行耗时及 Token 数量。
  2. **Playground 快捷晋升**：在 Trace 详情中，用户可以直接查看 Prompt 捕获的完整模版和变量，并提供一个 "Promote to Playground" 按钮，一键把这组 Prompt 与测试参数发送到 Playground 进行微调，调试完毕后可以一键提升为 "Golden Dataset" (黄金基准数据集)。
- **能借鉴什么**: 我们目前的 `TracePanel.tsx` 存在 Golden Compare 与 Golden Promote 两个按钮的脚手脚，这与 LangSmith 的 Playground 晋升理念一致。重构后的 Trace Panel 必须作为这些高阶工程化操作的核心母港。

### 1.2 LangGraph Studio: Canvas Debugger & Event Highlight
- **怎么做的**: LangGraph Studio 是原生的 LangGraph 画布可视化调试工具。
  1. **连线高亮流动**：当工作流执行到某两个节点之间时，其间的连接边 (Edge) 会渲染流光特效，并在连线中心渲染代表数据流的圆点 (Data Flow Dot)。
  2. **原点状态机快照**：点击连线中心原点时，右侧抽屉不会展示空洞的属性，而是渲染出一个专门的 **State Change Panel**。该面板清晰地对比这一步前后的 State Channels (状态通道变量) 差异，直观地告诉开发者：哪个 key 发生了变化，哪些被 reducer 聚合，哪些变量在向后传递时被过滤了。
- **能借鉴什么**: 这是我们 REQ-4 和 REQ-5 需求的灵魂来源。点击 Edge Center Dot 不应污染 Properties Panel，而是必须在专属控制台开启 **State-Machine Snapshot Card**，以极高的视觉精度渲染 State Channels 的差异对比。

### 1.3 Phoenix / Arize: Structured Logs & Span Filters
- **怎么做的**: Phoenix 是主流的开源 AI 观测平台。其 Trace 页面提供了一个强大的 **交互式局部过滤器 (Interactive Focal Filters)**。
  1. 用户在可视化依赖图上点击任何一个环节，Phoenix 的日志 timeline 就会瞬间过滤出该节点产生的所有 Span、LLM call 和 standard outputs。
  2. 即使是在庞大的分布式系统里调试，开发者也只需要“画布点击”即可立刻在下方的终端中只保留与特定上下文相关的运行日志，极大地降低了日志轰炸引发的认知过载。
- **能借鉴什么**: 对齐 REQ-3。我们在画布中点击任何一个 Phase 节点时，Trace Panel 必须能智能拦截全局日志，瞬间过滤并只展示匹配该 Phase 节点执行 ID 的日志流，从而实现极佳的沉浸式局部调试。

---

## 2. 现仓库 Codebase 状态

我们对 `/apps/studio` 路径下的现存组件和逻辑进行了物理分析：

- **僵尸组件**: `TracePanel.tsx` (115 行) 和 `useRunStream.ts` (90 行) 已被完全实现但目前处于闲置状态，在 `Workspace.tsx` 与 `Panels.tsx` 中没有任何引入与渲染调用。
- **Properties 职责污染**: 在 `PropertiesPanel.tsx:195-280` 中，检测到明显的 `if (selectedEdge)` 代码。该部分代码在用户点击画布边时，强行把“连接追踪数据 (Connection Trace)”灌入静态属性侧边栏，显示了极长且凌乱的 raw JSON。这违反了单一职责，阻碍了干净的前端资产管理。
- **画布交互限制**: `ContextEdge.tsx:213-225` 中，点击边中心原点的事件监听器将行为死死地绑定在了 `workspace.onPanelChange('properties')` 上。这导致无法正常打开 Trace Timeline 进行对比。
- **历史记录无动作**: `TimelinePanel.tsx` (102 行) 仅使用 `useRunHistory` hook 拉取了一个只读的运行历史卡片列表，并未提供任何“点击运行卡片打开其事件 Trace”的交互入口。

---

## 3. 数据对比设计与 UI 流派探索 (State Machine Diff Strategy)

对于 edge 边界的 **State-Machine Snapshot Card** 差异渲染，我们对前端展示的 Payload 流派进行了对比抉择：

### 候选方案 A: 统一文本差异流 (Unified Line Diff)
将前后的 State 对象序列化为 JSON 字符串，并调用类似 git diff 的行差异渲染器，输出绿色加号与红色减号行。
- **Pros**: 支持展示极其复杂的深层嵌套对象，前端组件直接复用 Diff 库即可。
- **Cons**: 噪音极大。在状态机流转中，往往只有几个键（如 `working_memory.tokens` 或 `context`）发生了微调，用行 Diff 会输出大量重复的括号、缩进改动和非实质变动行，视觉极其刺眼。

### 候选方案 B: 结构化变量变更卡片 (Structured Key Diff)
直接在前端对前后的 State 键值对进行一层 shallow/deep comparison，提炼出三大核心指标分类并以微型卡片编排：
* **新增项 (Added)**：显示绿色 `+ key: value`；
* **修改项 (Modified)**：显示黄色 `Δ key: old_value ➔ new_value`；
* **移除项 (Deleted)**：显示红色 `- key`。
- **Pros**: 视觉效果极其 premium，完全屏蔽了语法噪音，精准契合极客对系统状态观测的第一性原理。
- **Cons**: 需要编写专用的对象 diff 函数进行状态提取。

### 本 Spec 推荐
**强烈推荐采用候选方案 B (结构化变量变更卡片)**。大语言模型工作流中的状态机流转就是变量的演化。提供一个剔除了全部标点缩进噪音、只保留“核心变量值演化”的精美 Diff 卡片，最符合 Kiro UI 设计美学，也能带给用户极致的视觉享受。

---

## 4. 关键技术决策点

在进入后续实现前，我们明确以下两个技术决策点，供开发者及 PM 审查：

1. **选中态流转拦截 (Navigation Redirect)**
   - 当点击边原点触发 timeline 面板打开时，如果当前并没有选中的 active run，UI 应如何表现？
   - **决策推荐**：应自动选中该 Skill 的 **Latest Run (最新一次运行)** 作为调试上下文，并在此上下文下显示连线的 State Diff。若一次运行都没有，则在 Trace Panel 内优雅展示 empty state。
2. **过滤条件解构与复合 (Compound Filter UI)**
   - 如果用户同时在画布上点击了“节点 A (进行局部过滤)”和“边 B (进行状态对比)”，Trace 控制台应以何种优先级展示？
   - **决策推荐**：两者属于不同维度的调试意图。状态对比（Edge Dot）优先级高于普通的日志过滤。点击边原点时，应展示状态对比卡片，并自动清空局部的节点筛选，防止两者冲突导致空日志。

---

## 5. 推荐方向

基于上述 Research 结果，我们建议以最快速度进入实现阶段，方案核心如下：
1. **重构控制台大本营**：将 `TimelinePanel.tsx` 改造为可以灵活在“历史运行列表”与“特定运行 Trace 控制台”之间切换的双模态组件。
2. **彻底净化属性栏**：将 Edge click 交互事件的回调函数全面引流到 `timeline` tab。
3. **高保真 Diff 变量卡片**：在前端开发专用的 `EdgeDiffViewer.tsx`，以 `rounded-md` (0.375rem / 6px) 圆角规范及 indigo/zinc 语义化色值实现美轮美奂的 State Diff。

## 相关文档
- [requirement.md](./requirement.md)
- [FRONTEND_UI_SPEC.md](../../../docs/development/FRONTEND_UI_SPEC.md)
