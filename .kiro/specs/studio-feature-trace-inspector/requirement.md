---
spec: studio-feature-trace-inspector
status: Draft
last_updated: 2026-06-01
supersedes: trace-and-predict-visibility
linked_level3_docs:
  - docs/studio/02_features/trace-inspector/baseline.md
  - docs/studio/02_features/trace-inspector/mvp0-alignment.md
---

# Requirement — Trace Inspector(运行追踪 / 完全去黑盒)

> **本 spec 地位**: Studio 运行追踪的**唯一权威 spec**。由 `trace-and-predict-visibility`(2026-05-19 旧名)**改名而来并合并其内容**,旧目录已标记 Superseded(见 [INDEX.md](../INDEX.md))。

## 0. 功能本质(用户原话,原文留底)

> "就是看 tracing,整个 graph 运行的每一步操作的所有记录,输入输出结果,目的是**完全去黑盒**,让用户可以了解 run skill 确切发生了什么!"
>
> "最关键的是:**1. 能看到所有的操作日志;2. 能找到想要看的操作日志**。"
>
> "1. tracing panel,运行时实时看 tracing,突出信息;2. 非运行时,选择哪个节点,看哪个节点的 trace,连线上的 dot 代表 graph。**state snapshot 也是 tracing 的一部分,重要的部分**,tracing 里的节点抛出 context 变化、state snapshot,点进去跳转到编辑器看具体状态。点击 dot 弹出 state 黑板卡片,点击卡片进入编辑器看详情。"

## 1. 第一性原理

追踪器的不可约目的是**去黑盒**:让用户确切看到 run skill 时 graph 每一步发生了什么。由此只有两件事是核心:

1. **看到所有操作日志** —— 每一步的输入 / 输出 / 结果,无遗漏。
2. **找到想看的那一条** —— 在海量日志里快速定位到某个节点 / 某次操作 / 某段状态。

其余一切(结构化 diff 卡片、花哨可视化)都是次级优化,**不得喧宾夺主**。State snapshot 不是花哨功能 —— 它是 tracing 的一等组成,但其本质是「**看到**某点的黑板状态」,不是「计算前后差异」。

## 2. 现状(2026-06-01 实测)

**数据基本都在,缺的是「接线 + 组织 + 查找」,不是缺数据。**

- 引擎已把每步完整落盘到 `trace.jsonl`(真实样本:`.workspace/runs/dca08b4d-7f18-47f9-84be-89efe7939fa3/trace.jsonl`)。32 类事件见 [`events.py`](../../../packages/graph-agent/src/graph_agent/callbacks/events.py),其中:
  - `phase_start` / `phase_end` 携带**完整黑板快照** `context = {inputs, phase_outputs, scratch}`;
  - `prompt_captured` 携带 `resolved_prompt`(渲染后)+ `variables` + `resolved_model`;
  - `llm_call`(token)、`tool_call`(args/result/耗时)、`working_memory_update`(全文)、`compaction`、`run_started.initial_context`、`run_ended.final_context` 等。
- **前端几乎没接上这些数据**:
  - [`TracePanel.tsx`](../../../apps/studio/frontend/src/components/TracePanel.tsx)(114 行)+ [`useRunStream.ts`](../../../apps/studio/frontend/src/hooks/useRunStream.ts)(89 行)已实现但**零引用**(僵尸);
  - `TimelinePanel.tsx` 只是只读历史列表,卡片无点击进 trace;
  - 边 dot 的 context 是 **mock**(`ContextEdge.tsx` 的 `getMockEdgeContext()`),并把假 JSON 倒进静态 `PropertiesPanel.tsx:195-280`。

## 3. 功能需求

> **优先级与归属**: REQ-1~6 = **P1 核心**(均"现在可做",本 spec 拥有);REQ-7 = **P2**(本 spec 拥有,依赖引擎)。
> 原 `deferred-items.md` 的 **DEF-002 → REQ-3**(真实数据接线,P1)、**DEF-001 → REQ-7**(结构化 diff,P2)已**拉回本 spec scope** —— 它们本就是本 feature 自己的部分,不再以 deferred 形式悬挂。

### REQ-1 — Trace Panel:唯一控制台(运行时实时 + 非运行时回看)
接线 `TracePanel` + `useRunStream`,作为所有运行输出 / 事件 / 错误的唯一控制台。运行时实时流入并**突出关键信息**(phase 边界、错误红灯、token / 延迟);运行结束后可从历史运行回看同一控制台。不再新增第二个调试面板。

### REQ-2 — Findability:看得到,更要找得到
1. **节点定位**:在画布选中某节点 → 控制台只显示该节点的 trace(按事件 `phase_name` 过滤,已验证可行)。
2. **检索 / 筛选**:支持按事件类型(llm_call / tool_call / error / state…)与关键字检索,在海量日志中快速定位。

### REQ-3 — 边 dot = graph 框架操作 + state 黑板(真实数据)
连线中心 dot 代表两节点之间的 graph 框架操作(数据汇入、reducer 聚合、state 流转)。
- 点击 dot → 弹出 **state 黑板卡片**,展示这条边 A→B 上的**真实** blackboard 状态(由 `phase_end[A]` 与 `phase_start[B]` 的 context 重建,**替换当前 mock**)。
- 点击卡片 → 进入编辑器(**只读**)查看该状态的完整详情(深层嵌套可折叠展开)。

### REQ-4 — State snapshot 是 trace 的一等内容
节点在 trace 流中显式抛出其 context 变化 / working_memory / state 快照,作为可见的 trace 条目。点击该条目 → 跳转编辑器查看具体状态。这与 REQ-3 是同一能力的两个入口(从时间线进 / 从画布连线进),最终都落到「在编辑器里看那一刻的黑板」。

### REQ-5 — Prompt 透视(从旧 spec 合并)
点击一条 LLM 事件 → 三视图:`Template`(原始模板)/ `Variables`(喂入变量 JSON)/ `Rendered`(渲染后纯文本)。数据来自 `prompt_captured` 事件,无需引擎改动。

### REQ-6 — 净化 PropertiesPanel
移除 `PropertiesPanel.tsx:195-280` 的 `if (selectedEdge)` JSON 倾倒分支,属性栏回归单一职责(静态节点配置)。`ContextEdge.tsx:223` 的 dot click 从 `onPanelChange('properties')` 改道到 trace 控制台 / 黑板卡片。

### REQ-7 — 结构化前后态 DIFF(P2,本 spec 拥有,依赖引擎)
> 由 DEF-001 拉回。**本 spec 拥有,非 deferred 孤儿**;但优先级 P2,且需引擎支持后才能可靠落地。
在 REQ-3 的 state 黑板查看之上,额外高亮节点转移**前后变化的 key**(added / modified / deleted)。
- **数据依赖**:精确的 reducer 级差异(哪些 key 被聚合 / 保留 / 丢弃)在事件流里是隐式的,需引擎在 phase 边界显式 emit reducer 级 diff;在此之前前端可用 `phase_end[A]` vs `phase_start[B]` 做**近似 diff(非权威预览)**。
- **快照机制(已确认)**:当前每个 phase 边界落一份**全量**黑板快照(非 keyframe+delta),diff 是这两份全量快照之上的**纯展示层**计算,与存储无关。
- **不阻塞 P1**:REQ-3 的 state **查看**现在就能做,与本项无依赖关系。

## 4. 可行性锚定(诚实分层 —— 哪些现在就能做)

| 能力 | 状态 | 说明 |
|------|------|------|
| 看全部操作日志(REQ-1) | **现在可做** | trace.jsonl 已完整;接线 TracePanel/useRunStream |
| 节点过滤 + 检索(REQ-2) | **现在可做** | 每事件带 `phase_name` |
| 边 state 黑板**查看**(REQ-3/4) | **现在可做** | 从 phase_end/phase_start context 按需重建,**无需引擎改动** |
| Prompt 透视(REQ-5) | **现在可做** | `prompt_captured` 已含 template/variables/rendered |
| 结构化**前后态 DIFF**(added/modified/deleted) | 需引擎 · **P2**(本 spec 拥有) | 引擎需 emit reducer 级差异;见 REQ-7(非 deferred,P2 路线项) |
| 编辑状态 → 续跑 | 需后端 · 单独能力 | resume 端点当前 501,见 DEF-005 |

## 5. 边界与非目标

- **结构化 before/after Diff 卡片**:**在 spec 内**,但为 **REQ-7(P2,依赖引擎)**,非本轮 P1 交付。注意:state **查看**(REQ-3 核心)现在就能做,与此无依赖。
- **编辑-续跑(篡改 state → Resume)**:干预型能力,与本 spec 的只读去黑盒是不同 mode;后端 resume 为 `501`([`runs.py`](../../../apps/studio/backend/app/routers/runs.py)),DEF-005。
- **Compile 结构化报错**:已确认**拆出本 spec**(属编写期校验,与运行追踪正交)。用户对其 UX 有明确意图(底部 drawer · 只覆盖画布不挡边栏 · 一键复制到 Copilot),原话与去向登记 [`deferred-items.md`](../../../docs/deferred-items.md) DEF-010,候选 owner:`canvas-authoring-v1`。
- **画布亮暗联动 / 输出路径配置**:不属本 spec,DEF-003 / DEF-004。

## 相关文档
- [research.md](./research.md)
- [baseline.md](../../../docs/studio/02_features/trace-inspector/baseline.md) · [mvp0-alignment.md](../../../docs/studio/02_features/trace-inspector/mvp0-alignment.md)
- [05_debugging.md](../../../docs/studio/01_workflows/05_debugging.md)(场景C 编辑-续跑,DEF-005)
- [event-bus-alignment.md](../../../docs/studio/03_platform/state-engine/event-bus-alignment.md)(引擎产出 → 传输 → 渲染 三层归属)
