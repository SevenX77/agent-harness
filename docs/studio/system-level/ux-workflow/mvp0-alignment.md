# ux-workflow (studio system-level) — MVP0 Alignment (下一步对齐逻辑)

> **Status**: Filled by a2 (Gemini), 2026-05-20
> **Scope**: 贯穿多个 feature (canvas → editor → trace) 的用户核心操作流蓝图
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

在 MVP0 中，我们将达成 "PM 不开终端、不写 YAML，全可视化闭环" 的端到端体验。用户旅程将被彻底打通：

- **编排即见 (Edit to Save)**：PM 在画布上拖拽节点或通过 Copilot 侧边栏对话生成新节点后，Studio 不再要求去左侧树找 YAML 手写。界面直接触发对连线的校验。如果发现类型不匹配，编辑器上方会立刻飘出红色的 Toast 警告。
- **一键启停 (Run Flow)**：工具栏将暴露全局唯一的 "Run Skill" 按钮。点击后，触发系统对大图的 Compile 与后续大模型请求。运行中状态如 `NODE_START` 的加载 spinner 会实时在对应的画布节点上亮起。这是让静态的图“活起来”的核心。
- **所见即所得的观测 (Trace Flow)**：当推演走到终点时，底部的 Trace 瀑布流会被瞬间点亮；此时由于图上抛出了详细的上下文，点击两节点间的连线（Edge）后，将会唤起 Context Inspector 悬浮窗或右侧固定面板，使得输入输出（I/O）无所遁形。
- **历史记录查阅 (History)**：所有的运行过程都会在历史面板被留存。当 PM 回头查看过去的某次失败时，点击历史条目，整个 UI (Canvas/Editor) 会恢复到当时的那一帧数据状态。

## 前端逻辑

为支持上述的体验闭环，我们将在前端引入全局状态编排机的概念。当前的 `Workspace.tsx` 只有简单的切换判断，例如 `currentSkillId` 在 `apps/studio/frontend/src/App.tsx:8` 传递，空态时渲染 `WelcomePage` 在 `apps/studio/frontend/src/components/studio/Workspace.tsx:398`，详见 [baseline.md#前端逻辑](./baseline.md#前端逻辑)。

MVP0 核心前端改造：
我们将扩充 `apps/studio/frontend/src/components/studio/Workspace.tsx` 的全局 Context Provider，新增一套针对 "Run Mode" 和 "Edit Mode" 的大流转状态：
- 当进入 "Run Mode" 时，自动切出底部面板，并清空旧的 Trace History。这可以复用现有的 Trace 组件。
- 监听 WebSocket 从后端推送的 `AgentTraceEvent`，实时将接收到的 `run_id` 及其 `payload` 注入到 Store 中，供其他视图订阅消费。
- **引入对 Edge 点击事件的全局支持**。当捕捉到用户点击画布上的连线时，触发 dispatch 行动向整个 Layout 广播展示 Context Inspector，这解决的是 High-003 的端到端流转。

### 1. 节点加载状态指示
当收到 `NODE_START` 时，在画布上对应的 Node 组件上会渲染一个转圈的 Spinner。此时该节点的颜色状态可能会变为 `running`。直到收到 `NODE_END` 或者 `EXCEPTION`，节点才会解除锁定状态并变成 `success` 绿或者 `error` 红。这增强了过程感知。

### 2. 边数据透视 (Edge Inspection)
解决 High-003 的难点在于，之前并没有组件能够承载两个阶段流转之间的数据片段。在 MVP0，一旦点击两个节点之间的 Edge（React Flow `Edge` entity），`inspectedEdge` 状态便会把该 Edge 源头的 `outputs` 和目标的 `inputs` 字典传入 Context Inspector 显示，完成数据包的“断点透视”。

### 3. Trace 历史溯源
每当一个 `run_id` 结束后，这份全图数据将被持久化。后续即使 PM 关闭了工作区再打开，也能通过顶部的 Run History 下拉框重新激活，再次重现出当时的 100% 数据流视图。这构成了调试的心智闭环。

### 4. 异常状态恢复流程 (Crash Recovery)
当系统遭遇到未捕获的严重异常（例如整个 V2.1 引擎的 core 崩溃），UI 层不能死锁。在 `run_skill` 的报错抛出后，Zustand Store 会将 `isRunning` 强制置为 `false`。同时，在编辑区上方会横幅展示一个带有 `Retry` 按钮的 banner，允许 PM 清理状态后再次触发，这是一个顺畅 UX 不可缺少的容错设计。

### 5. Copilot 无缝唤起与上下文加载
如果节点出现失败或者推演超时，用户不必去手动搜索代码。由于我们在 `inspectedEdge` 中截获了输入输出快照，当用户在侧边栏唤出 `Copilot` 聊天框时，系统会将其视为隐式的意图，自动将这些错误日志或数据片段以附带 Context 的形式放入聊天历史，提升协助效率。这也是 MVP0 智能化的重头戏。

### 6. 数据沙盘与测试容器的构建
为了让 "所见即所得的观测" 真正具有价值，PM 在执行 Run Flow 时不需要去拼凑混乱的数据集。前端界面的 `Playground` 会结合 `Input Funnel` 提供沙盘数据。当 PM 填好数据后，将产生一个新的 `run_id` 并将其封存在独立的环境里。整个 UX 流程能让使用者感觉他们是在测试容器内部做沙箱操作。

### 7. 对遗留 UI 的清理
在旧的流程里，由于状态未能收口，部分 React Context 中仍残留有 `AgentHarness` 相关的旧版回调订阅钩子。在这次的全面重塑中，这批钩子将被彻底摘除，以保证前端逻辑干净地对接 WebSocket 流。

## 后端功能

此 UX Workflow 在后端的表现为串联了 `compile_skill` 到 `run_skill` (`packages/graph-agent/src/graph_agent/core/runner.py:161`) 再到 `trace emitter` 的完整长链路。

- **触发态收口**:
  PM 在界面点击运行后，后端应当提供一个无阻碍的 HTTP POST 或者 WebSocket 通道来触发 `packages/graph-agent/src/graph_agent/core/runner.py:161`。引擎本身在这个链路中需要做的工作是：绝不允许中途因为某些配置错误而静默死亡。所有的 `CompileIssue` (例如静态依赖冲突) 以及 `GraphAgentFatalError` 都需要被包装成标准事件反馈给前端。
- **Context Inspector 数据源 (High-003 落地方案)**:
  旧文档提及点击连线数据包打开 Inspector 这一能力当前处于缺失状态。在 MVP0 中，引擎发出的每个阶段的 `phase_input` 和 `phase_outputs[phase_id]` 将由后端在本地构建好字典索引发送，它正是支撑 Frontend 提供数据包剖析（Inspector）的基石。

## API

为了承接 PM 从 "Run" 到 "Trace" 这个连贯交互，我们需要在 TypeScript 端定义严格的 API 发射契约，配合引擎传出的数据：

```typescript
// Proposed Event payload arriving from backend WebSocket
export interface AgentRunStateEvent {
  /** The unique identifier of the run triggered by PM */
  run_id: string;
  /** Matches the backend's TraceEventKind */
  event_type: "node_start" | "node_end" | "llm_call_start" | "llm_call_end" | "exception";
  /** Phase identifier associated with this event */
  phase_id: string;
  /** Free-form data representing input/output payloads or errors */
  payload: Record<string, any>;
  timestamp_ms: number;
}
```

触发大图运行的 HTTP 端点提案（预计在 `apps/studio/backend/app/routers/runs.py` 中）：

```python
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

router = APIRouter()

class RunSkillRequest(BaseModel):
    skill_root: str
    initial_inputs: dict

@router.post("/api/runs")
async def trigger_skill_run(req: RunSkillRequest, background_tasks: BackgroundTasks):
    """
    Triggers the V2.1 engine execution flow safely.
    The response contains the run_id immediately, while the 
    actual execution streams logs via WebSocket.
    """
    # ... logic invoking runner.py ...
    pass
```

## Data Model / State

在 UI 客户端层面，我们需要在 Zustand Store 中固化这套大流程状态树。前端当前 Store 较少 (如 `apps/studio/frontend/src/store/copilotStore.ts`)，因此亟需扩充。

```typescript
// Zustand Store signature proposition
interface UXWorkflowState {
  currentRunId: string | null;
  isRunning: boolean;
  
  // Storage for High-003 Edge Inspector context
  inspectedEdge: {
    sourcePhase: string;
    targetPhase: string;
    snapshotData: Record<string, any> | null;
  } | null;
  
  setInspectedEdge: (source: string, target: string, data: Record<string, any>) => void;
  startRun: (id: string) => void;
  endRun: () => void;
}
```
通过这个集中的 `inspectedEdge` 状态，当用户在 Canvas 触发点选时，Context Inspector 就能立刻感知并调取快照。

考虑到全局状态的繁多，对于 Zustand 的 Store 结构必须拆分得当：
- `useRunStreamStore` 专门处理接收到的 `AgentRunStateEvent` 及不断变长的 logs。
- `useWorkspaceStore` 仅仅处理诸如 `currentSkillId` 这样的大型顶层标识。
- `useEdgeInspectorStore` 专门应对复杂的数据包展开结构。
这种 Store 的正交切分极大地避免了无谓的 React 重新渲染风暴。

## Cross-feature interaction

- **与 Layout 架构的融合**:
  点击连线后打开的 Context Inspector 面板究竟放在哪里？它将被明确挂载为 `studio-layout` 中的右侧附属面板（作为 `PropertiesPanel` 的一个变种态，由 `selectedNode` 是否为连线类型进行切换）。详情见：[studio-layout/mvp0-alignment.md#前端逻辑](../studio-layout/mvp0-alignment.md#前端逻辑)。
- **与 Canvas 连线的触发绑定**:
  PM "点击连线" 这一物理动作的来源点是在 React Flow 内部。该画布捕获到动作后，将 dispatch `inspectedEdge` 更新。这涉及到画布上节点与连线的核心处理机制，详见 [canvas-topology mvp0](../../feature-folders/canvas-topology/mvp0-alignment.md)。
- **底层引擎 Trace 支撑**:
  整个界面从 Run 到 Trace 的一键点亮，数据全依赖 [Engine tracing-and-observability](../../../engine/tracing-and-observability/mvp0-alignment.md#Data-Model-/-State) 抛出的规范结构。没有后者的精准输送，就不会有流畅的 UX Workflow。两者必须严丝合缝地对接，这在 MVP0 是不可妥协的底线。