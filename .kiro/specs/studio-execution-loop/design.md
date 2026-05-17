# Design: Studio Execution Loop

## 1. 架构决策与数据流 (Architecture & Data Flow)

本 Spec 的核心目标是彻底打通 "Engine -> Backend -> Frontend" 的运行态事件流，并实现持久化与回放。

### 1.1 数据流重构 (The Data Flow)
1. **Engine 发送**: `graph-agent` 内部通过 `StudioQueueCallback` 将产生的强类型 `CallbackEvent` (v1.0) 放入进程队列。
2. **Backend 接收与持久化**: 后端 `run_manager` 从队列取出事件后，执行**双写 (Dual-write)**：
   - 实时推送：推入该 Run 对应的 `ws_queue`。
   - 持久化落盘：将事件追加写入该 Run 专属的 `.tracing.jsonl` 日志文件中。
3. **Frontend 消费与追赶 (Catch-up)**:
   - 前端通过 `/ws/runs/{run_id}` 连接后端。
   - 后端在建立连接时，首先从 `.tracing.jsonl` 中读取已有历史事件全量下发，然后再切换到实时 `ws_queue` 流，确保前端不错过瞬间爆发的启动事件。
4. **前端状态树 (Store)**: 前端构建 `useRunStore` (Zustand) 消费事件，派生出当前 Active Phase、整体 Run 状态以及 Trace Timeline 数据。

### 1.2 Phase 划分大纲 (Task Breakdown)
- **Phase 1: Trace & History Data Flow**
  - **P1.1 (Engine/Backend)**: 确认/小调 `StudioQueueCallback` 直接透传 Pydantic Events。
  - **P1.2 (Backend)**: 重构 `run_manager`，引入 `.tracing.jsonl` 落盘机制。提供查历史 Run 列表的 API。
  - **P1.3 (Backend)**: 改造 `/ws/runs/{run_id}`，实现 "History Catch-up + Realtime Stream" 的无缝衔接。顺手修复 WS 启动序列问题 (Modal 泄漏/断线/重连)。
  - **P1.4 (Frontend)**: 实现 `useRunStore`，对接 WS，渲染 Trace Panel 时间线与 History 列表。
- **Phase 2: Canvas State Sync**
  - **P2.1 (Frontend)**: 基于 `useRunStore` 提供的 `activePhase` / `errorPhase`，驱动 React Flow Canvas。
  - **P2.2 (Frontend)**: 绘制 Phase Node 的执行中呼吸灯/报错高亮状态。
- **Phase 3: Polish Bugs**
  - **P3.1 (Backend/Frontend)**: 在 Event Bus / Frontend Store 层实现 "Skill Changed" Toast 去重逻辑。

## 2. 风险点 (Risks)
- **高频事件洪峰**: Phase 内可能短时间产生大量工具调用/Nudge事件。如果前端不加防抖 (Debounce) 或 Windowing，会导致 React 渲染卡顿。
- **僵尸进程/孤儿 Run**: 后端 FastAPI 重启或异常崩溃时，正在跑的子进程可能遗留，导致历史记录永远卡在 "running"。需要健壮的生命周期清理 (Reaper) 或超时判定。

## 3. 跨 Master 边界 (Cross-master boundary)

| 我 (Backend Owner) 要做的 | Apps Master (Frontend Owner) 要做的 |
|---|---|
| 1. **定契约**: 明确 14 种 `CallbackEvent` 下发时的 JSON Schema，不阻断前端开发。 | 1. **接模型**: 根据 Schema 构建前端 Typescript types。 |
| 2. **持久化层**: 实现 `run_manager` 写 `.tracing.jsonl` 及读取逻辑。 | 2. **状态管理**: 建立 `useRunStore` 处理 Catch-up 事件流与断线重连。 |
| 3. **WS 追赶流**: 改造 WebSocket `/ws/runs/{run_id}`，连上先发历史，再发增量实时。 | 3. **UI 渲染**: 将 Store 状态分别映射给 Trace Panel 和 Canvas Node。 |
| 4. **API 补齐**: 确保 History 列表 API (`GET /runs`) 能正确读取文件并返回概览。 | 4. **组件去重**: 实现统一的 Toast 并合逻辑，消除 UI 霸屏。 |
