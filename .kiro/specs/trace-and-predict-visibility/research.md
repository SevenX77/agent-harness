---
spec: trace-and-predict-visibility
status: Draft
last_updated: 2026-05-19
linked_level3_docs:
  - docs/studio/TRACE_AND_VISUALIZATION.md
---

# Research: Trace & Predict Visibility

## 1. 业内方案调研

### 1.1 LangSmith Trace UI
- **怎么做的**: LangSmith 专为 LLM Agent 调优而生。它的 Trace 列表不仅仅是瀑布流，还巧妙地利用缩进表示 `Chain -> Agent -> LLM/Tool` 的嵌套调用栈。选中任意条目，右侧会固定切出一块分屏，详细展示该节点的 Input 和 Output（高亮 JSON）。在其官方面板中，甚至对 Messages 数组做到了结构化还原。
- **关键设计决策**: 对于 Prompt 的审查，LangSmith 非常注重对最终发送给 API 的“Messages Array”（包含 Role、Content、Function Signatures）进行原生结构还原。
- **能借鉴什么**: 我们设计的 Prompt Inspector 必须像它一样，不能只显示一个打平的纯字符串，而是要清晰地分栏展示 Template 和具体的 Variables 映射，这对 PM 排查模型幻觉至关重要。

### 1.2 Pydantic Logfire Trace
- **怎么做的**: Logfire 在处理嵌套日志时，除了瀑布流树状图，它会把所有的上下文环境变量 (Context) 在面板最右边以一个小字典的形式随动悬浮展示。可以通过访问 `https://logfire.pydantic.dev/` 了解其侧边栏交互。
- **关键设计决策**: 强行区分“全局 Context”和“局部 Event”，全局 Context 永远常驻侧边栏。
- **能借鉴什么**: 我们的 Edge Inspection (点击连线查看大黑板 Context) 需求，正好需要一种独立的抽屉交互，与主 Trace 流相辅相成。Logfire 将局部输入和全局 Context 清晰分开展示的思路值得效仿。

### 1.3 Datadog APM & Grafana Tempo
- **怎么做的**: 传统的 APM 工具在展示 Trace 时，核心使用**火焰图 (Flame Graph)** 或甘特图 (Gantt Chart)，以时间轴的绝对长度来刻画耗时。
- **关键设计决策**: 强调并发执行时的性能瓶颈（哪些节点在等，哪些节点并行）。
- **能借鉴什么**: 如果我们的 Graph Agent 支持并发流转（并行 Phase），那么前端的 Timeline 组件不能只是一个简单的列表，它可能需要借助类似 Gantt 的横向条条来告诉 PM 哪些阶段在并行，哪一步拖慢了整体节奏。这可以作为未来的 P2 级进阶参考。

### 1.4 OpenTelemetry SDK (OTel Schema)
- **怎么做的**: OTel 将每一次观测定义为 Span。Span 具有 `TraceId`, `SpanId`, `ParentSpanId`, `Attributes` 和 `Events`。
- **关键设计决策**: Schema 高度抽象，不绑定任何单一厂商。
- **能借鉴什么**: 我们 Engine 后端吐给前端的 WebSocket Event Payload，在结构设计上应该高度借鉴 OTel 的标准化命名，这有助于未来我们向生产环境（Cloud）无缝迁移。

## 2. 现仓库 Codebase 状态

通过 `file:line` 扫描当前仓库的开发状态：

- **前端 Timeline UI**: `apps/studio/frontend/src/components/history/HistoryPanel.tsx:16`（从文件名看）似乎承担了类似职能，但在主 `Workspace.tsx` 代码中我们看到仅有 `CompileErrorPanel` 的简陋实现，缺乏针对 LLM Event 精细化的树状或卡片状渲染逻辑。*(推断：前端瀑布流与透视仪可视化是大片空白)*。
- **WebSocket 协议**: `apps/studio/backend/app/routers/runs.py:27` 已包含关于 Run 生命周期管理的完整路由。在相关的实现 `apps/studio/backend/app/services/run_manager.py:24` 中，我们看到 `run_manager.start_run` 会触发执行。推测引擎内已经具备通过 AsyncGenerator 吐出基础事件的能力，但缺少严谨的前后端对接 Schema 契约。
- **React Flow 状态机联动**: 在 `apps/studio/frontend/src/index.css:180` 的代码审计中，我们看到了对 React Flow 的基础样式挂载，但在 `apps/studio/frontend/src/components/GraphCanvas.tsx` 中，暂未看到将 WebSocket 事件（如正在运行的 Phase ID）绑定回画布节点，从而触发发光边框（呼吸灯）的代码映射。*(推断：UI 联动仍未实装)*。

## 3. 前后端 Payload schema 探索 (本 spec 推荐)

为了支持上述的瀑布流和透视仪，后端的推流数据应当向以下 OTel-like 风格靠拢：

```typescript
// 推荐的 Trace Event 契约
interface RunTraceEvent {
  eventId: string;           // 全局唯一跟踪 ID
  traceId: string;           // 属于哪次 Run
  parentEventId?: string;    // 如果由嵌套触发，指向父 ID
  timestampMs: number;       // 时间戳
  
  eventType: 
    | "PHASE_START" | "PHASE_SUCCESS" | "PHASE_FAIL" 
    | "LLM_REQUEST" | "LLM_RESPONSE" 
    | "TOOL_INVOKE" | "TOOL_RETURN" 
    | "VALIDATOR_NUDGE";
    
  targetId: string;          // 关联到 SKILL.md 里的具体 phaseId
  
  // 不同的 eventType 携带不同的 details 结构
  details: {
    // 例如 LLM_REQUEST 的 details
    promptTemplate?: string;
    variables?: Record<string, any>;
    renderedText?: string;
    
    // 例如 LLM_RESPONSE 的 metrics
    latencyMs?: number;
    tokensPrompt?: number;
    tokensCompletion?: number;
    
    // 或者 Edge Inspection 触发的快照数据
    blackboardSnapshot?: Record<string, any>;
  };
}
```

## 4. 关键技术决策点

在进入 Design 阶段，架构师需要定下以下核心决策：
1. **Trace 的存储与加载**: 前端是只把 WebSocket 收到的流存在内存里展示（一刷新就没），还是后端存进 SQLite `.workspace/runs.db` 里，前端不仅接收实时的流，还能随时分页回放历史 Trace？
2. **状态同步机制**: 画布上节点的呼吸灯状态（如正在跑高亮绿框），是由后端专门发一条 `UI_UPDATE` 事件指挥，还是前端自行消费纯粹的 Trace 业务流（收到 `PHASE_START` 自己推导出 UI 要高亮哪个节点）？
3. **Payload 体积防爆**: 连线上的大黑板快照如果包含了上百兆的长文本，推流时要如何裁剪？（例如：全量下发，但在长文本中插入 `__TRUNCATED__` 标记，由前端按需点击请求全量 API 获取）。

## 5. 推荐方向

根据调研，我给出的初步推荐如下（供 Design 参考）：
- **关于状态同步机制**: 强烈建议**前端通过订阅原始业务 Trace 流自行推导 UI 状态**，例如维护一个活跃 Phase 的 Set。切忌让后端发送诸如 `CHANGE_BORDER_COLOR_TO_RED` 的 UI 控制指令，这会严重破坏前后端的数据协议纯洁性。
- **关于 Trace 存储**: 既然这是一个供 PM 本地长期打磨的 Studio，每次调试的运行轨迹应该落盘到本地的 `.workspace/` 缓存库中，前端除了 WebSocket 实时接入外，必须支持从该库加载历史回放，否则断点调试毫无意义。

## 相关文档
- [TRACE_AND_VISUALIZATION.md](../../../docs/studio/TRACE_AND_VISUALIZATION.md)
- LangSmith 文档: https://docs.smith.langchain.com/
- OpenTelemetry 规范: https://opentelemetry.io/docs/specs/
