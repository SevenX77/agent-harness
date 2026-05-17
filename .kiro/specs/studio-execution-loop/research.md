# Research: Studio Execution Loop

## 1. Engine Callback Event Payload 契约
- **位置**: `packages/graph-agent/src/graph_agent/callbacks/events.py`
- **发现**: Engine 已经定义了非常完整且类型安全的 `CallbackEvent` Pydantic Union (v1.0 schema)。
- **核心 Payload**: 包含 `PhaseStartEvent`, `PhaseEndEvent` (携带 `context` 和 `metrics`), `LLMCallEvent`, `ToolCallEvent`, 以及 V2 新增的 `PromptCapturedEvent` 等 14 种事件。
- **现状**: 底层其实不缺数据，引擎在执行时已经能透出足够细粒度的状态与 I/O。

## 2. Backend run_manager 持久化与分发
- **位置**: `apps/studio/backend/app/services/run_manager.py`
- **发现**:
  - `run_manager` 维护了 `RunRecord`，通过 `StudioQueueCallback` 将引擎事件映射并推入 `ws_queue` (`asyncio.Queue`)。
  - **持久化缺口**: 当前 `RunRecord` 主要存在于内存 (`events` 列表)。如果 Studio 服务重启，或者需要查询过去的 History，并没有看到明显的持久化落盘机制 (如 SQLite 或 JSONL) 被深度整合以供 API 查询。目前是易失的。

## 3. Backend WebSocket Push 机制
- **位置**: `apps/studio/backend/app/routers/websockets.py`
- **发现**:
  - `/ws/runs/{run_id}` 端点确实存在，且正确接驳了 `run_manager.stream_run(run_id)`。
  - 核心问题在于：由于持久化和 Run Lifecycle 的缺陷，前端很难在正确的时机连上正确的 `run_id`，或者连上后读不到历史事件，只能读到连接之后的增量流。

## 4. Frontend Trace 与 Canvas 状态
- **位置**: `apps/studio/frontend/src/components/trace/`
- **发现**:
  - Trace UI 具备 `VirtualTraceList`, `TraceEventRow`, `EventTypeBadge` 等静态组件。
  - **缺口**: 缺乏一个全局的 Run 状态机 Store 来消费 `/ws/runs/{run_id}` 下发的数据，并据此驱动 Trace 面板的渲染，以及驱动 React Flow Canvas 的 Phase 节点实现"正在运行"或"报错"的高亮效果。

## 5. 关于 4 个 Polish Bugs 的解耦
分析发现，这四个 bug 具有不同的领域属性：
- **启动状态泄漏 / skill 切换 toast 不去重 / footer WS disconnect**: 都和全局的状态初始化、WebSocket (特别是 `/ws/events`) 连接生命周期、以及文件系统事件的去重合并有关，这属于**Phase 1 数据流重构**的强相关领域，应该在 P1 顺手解决。
- **CJK 字体 fallback**: 纯粹的 CSS / 客户端渲染样式问题，应单列至 Phase 3 或剥离。

## 结论与重构指导原则
不要为了"省事"去在当前的内存 `RunRecord` 上打补丁。必须重新设计 `run_manager` 的存储策略（建议采用 SQLite 或可靠的 JSONL 机制记录 run history），并且明确一套严格的前后端 WS 重连与追赶 (Catch-up) 机制。
