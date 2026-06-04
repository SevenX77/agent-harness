---
spec: canvas-micro-topology-v1
status: Superseded
superseded_by: studio-feature-canvas-topology
last_updated: 2026-06-01
linked_level3_docs:
  - docs/studio/UX_WORKFLOW_BLUEPRINT.md
  - docs/engine/GRAPH_EXECUTION_MODEL.md
---

> ⚠️ **Superseded → `studio-feature-canvas-topology`**（2026-06-01）。运行态微观展开 / Nudge / Payload schema 已吸收为主文档 REQ-11..14。本文件仅留作历史调研，待物理归档到 `_archive/`。

# Requirement: Canvas Micro-Topology Expansion

## 1. 问题陈述 (Problem Statement)
### 1.1 现状痛点
当前的 Studio 画布 (React Flow) 仅支持宏观层面的死节点渲染。PM 无法穿透节点，查看复杂 Agent-Loop 内部的多次工具调用、报错纠偏（Nudge）或 Subgraph 嵌套执行的细节。这导致了严重的“业务逻辑黑盒”。

### 1.2 为什么需要这个 spec
- **PM 原话引用**: "消除业务逻辑黑盒，graph agent 运行中的每一步都可视化。节点下方+按钮，点击展开各个节点的详细拓扑结构：subgraph展开嵌套的另一个skill全套节点图；logic展开按照编排的python代码模块节点，双击打开action代码文件；agent节点展开所有step；系统模版化的工作步骤，比如validator也要附加在最后的节点，双击可以打开validate的文件。"
- **Phase 3 Gap Matrix 描述**: 缺乏前后端交互时的 WebSocket/API Payload 数据结构定义来支撑这种嵌套渲染（例如，前端点击 `+` 后向后端拿什么样的嵌套树状 JSON）。本 spec 旨在收敛微观拓扑展开的需求边界，为后续架构设计提供清晰依据。

## 2. 用户故事 (User Stories)
1. **As a PM**, I want 在画布上点击复杂节点下方的 `[ + ]` 按钮，so that 我能在一个悬浮或内联的微观画布中，看清该节点内部的 Plan、Tool Calls 和 Validator 执行细节，打破黑盒。
2. **As a PM**, I want 在微观展开视图中清晰看到 Nudge (纠偏) 的重试计数 (如 `Nudge: 2/3`) 和标红报错，so that 我能立刻知道大模型在哪一环“翻车”了。
3. **As a 前端 Dev**, I want 后端能够通过清晰的 WebSocket/API Schema 下发层级嵌套的执行事件，so that 我能基于 React Flow 的 Group 节点特性，平滑地渲染子图，而不用在前端堆砌复杂的业务数据重组逻辑。
4. **As a 后端 Dev**, I want 明确知道前端在展开节点时需要全量还是增量数据，so that 我能设计合理的 Event Bus 推流策略，防止大图展开时内存爆炸。

## 3. Acceptance Criteria
### User Story 1 (微观展开交互)
- **Given** 一个处于运行完毕或挂起状态的 `agent` 类型节点，**When** 用户点击节点底部的 `[ + ]`，**Then** 画布原地平滑推开周围节点，内联展示该节点的内部执行子树 (Sub-flow)。
- **Given** 内联展开的子图，**When** 用户点击其中的子节点，**Then** 右侧的 Trace 或 Inspector 抽屉能够正确切换并展示该子步骤的 Payload。

### User Story 2 (Nudge 计数标示)
- **Given** 一个内部发生了 2 次 Validator 报错并触发重试的节点，**When** 该节点被展开，**Then** 微观图内的 Validator 步骤旁必须用红/黄色警示徽章标出 `Nudge: 2/3`。
- **Given** 最后一次 Validator 依然失败导致整个 Phase 崩溃，**When** 用户查看微观图，**Then** 最后一个步骤必须附带显眼的 Error Stack 气泡。

### User Story 3 & 4 (数据与渲染性能)
- **Given** 一个包含嵌套深度大于 3 层的超大 Subgraph，**When** 用户展开顶层，**Then** 前端组件不应出现超过 500ms 的明显卡顿渲染（需具备 Virtualization 或合理的 DOM 重用）。
- **Given** 后端向前端推流微观事件，**Then** API Payload 中必须严格包含 `parent_node_id` 和 `node_type` 字段，通过 Schema 校验。

## 4. 范围 (In Scope vs Out of Scope)
### In Scope
- React Flow 画布中节点的“内联展开” (Inline Expand) 交互规范。
- Agent-Loop, Subgraph, Logic-only 三类节点的微观视觉结构（分别对应：执行链、嵌套 DAG、单脚本文件）。
- 前后端传递微观层级数据的 Payload Schema 结构定义（Research阶段探讨，Design阶段锁定）。

### Out of Scope
- 画布中连线 Context 数据包抽屉的详细设计（属于 Trace 瀑布流范畴，移交 `trace-and-predict-visibility` spec）。
- 编辑态下的“双向子图编辑”（本 spec 仅覆盖运行态/只读态下的微观执行细节展开，子技能的双向热编排属于未来的进阶特性）。
- 跨分布式机器的分布式 Trace 跟踪（本仓库聚焦本地研发端与单机模拟执行）。

## 5. 依赖与前置条件
- 必须依赖 `docs/engine/GRAPH_EXECUTION_MODEL.md` 中定义的 13 大暴露 API 与运行状态差异。
- 必须依赖 `docs/studio/UX_WORKFLOW_BLUEPRINT.md` §2.3 中确立的宏观/中观/微观三段式编辑哲学。
- 依赖前端 `@xyflow/react` 库（版本 >= 12.10.2），需充分利用其 Sub Flow 和 Group 节点特性。

## 6. 关键约束
- **性能约束**: 当一个 Skill 包含 50+ 个微观步骤时，React Flow 画布缩放和展开操作的 FPS 必须保持在 30 以上。
- **Tauri 兼容性**: 展开时可能需要直接触发本地文件系统的读取（如打开 Logic 节点的 Python 源文件），必须严格走 `apps/studio/frontend/src/lib/tauri.ts` 桥接，防止在纯 Web 调试态下白屏崩溃。

## 相关文档
- [UX_WORKFLOW_BLUEPRINT.md](../../../docs/studio/UX_WORKFLOW_BLUEPRINT.md)
- [GRAPH_EXECUTION_MODEL.md](../../../docs/engine/GRAPH_EXECUTION_MODEL.md)
- 历史参考: `docs/archive/studio_history/02_EDIT_AND_COMPILE.md`
