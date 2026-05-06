# F1_T4_TRACE_ENHANCE_SPEC (Trace Enhancement)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在显著提升 Skill Studio 的可观测性与调试效率。当前 Trace 视图仅为简单的事件堆叠，难以在大量数据中定位关键点。我们将引入 **搜索、多维过滤、事件详情折叠** 以及 **跨组件联动（Graph ↔ Trace ↔ Monaco）**。通过点击 ReactFlow 节点高亮 Trace，或点击 Trace 错误跳转至源码行，实现“三位一体”的协同研发体验。

## 2. PM 痛点

### 2.1 现状
*   **信息过载**: 一个中型技能运行会产生数百条 Trace，顺序滚动查找特定 Phase 或 Tool 调用非常痛苦。
*   **调试孤岛**: ReactFlow 节点是静态的，点击节点无法看到该节点的运行细节。
*   **跳转断层**: Trace 报错后，PM 需要手动回到编辑器搜索对应代码行，缺乏“一键抵达”的闭环。

### 2.2 理想 UX
*   **Trace 视图**: 顶部常驻搜索框与过滤标签（LLM, Tool, Validation, Error），支持按 Phase 分类。
*   **点击联动**:
    *   点击 **ReactFlow 节点** → Trace 自动过滤并定位到该 Phase 的起始事件。
    *   点击 **Trace 事件** → ReactFlow 节点高亮，若是错误事件则 **Monaco 自动跳转至对应代码行**。
*   **内容深度**: 默认显示摘要，点击可展开查看完整的 Payload（如 Prompt 变量、Tool 返回值）。

## 3. 现有契约分析

### 3.1 `CallbackEvent` (SDK 侧)
实测 `packages/graph-agent/src/graph_agent/callbacks/events.py` 定义了丰富的事件类型：
*   大部分事件包含 `phase_name`。
*   `internal_error` 包含 `traceback`。
*   `validation_fail` 包含 `errors` 列表。
*   **Gap**: 运行时事件目前不直接包含 `SKILL.md` 的行号。

### 3.2 联动方案 (Heuristic Jump)
由于运行时事件缺少行号，我们将采用 **启发式搜索跳转**：
*   当点击某 Phase 的事件时，前端在 `skillCode` 中搜索 `name: <phase_name>` 模式，获取行号并触发 `MonacoPanel.onJumpToLine`。

---

## 4. 前端设计

### 4.1 目录结构
```
apps/studio/frontend/src/
├── components/trace/
│   ├── TracePanel.tsx (重构)
│   ├── TraceSearchBar.tsx      # 搜索输入
│   ├── TraceFilter.tsx         # 过滤标签组
│   └── TraceEventRow.tsx       # 单行事件，支持折叠详情
├── hooks/
│   ├── useTraceFilter.ts       # 搜索与过滤逻辑
│   └── useTraceSelection.ts    # 跨组件联动状态 (selectedPhase, selectedEvent)
└── utils/
    └── search.ts               # 模糊匹配工具
```

### 4.2 联动状态机 (`useTraceSelection.ts`)
```typescript
interface SelectionState {
  activePhase: string | null;  // 当前关注的节点
  activeEvent: string | null;  // 当前选中的 Trace ID
}

// App.tsx 顶层管理，分发给 GraphCanvas 和 TracePanel
```

### 4.3 搜索与过滤逻辑
支持组合过滤：
```typescript
const filtered = events.filter(e => {
  const matchSearch = searchTerm === '' || JSON.stringify(e).includes(searchTerm);
  const matchType = selectedTypes.length === 0 || selectedTypes.includes(e.event_type);
  const matchPhase = !activePhase || e.phase_name === activePhase;
  return matchSearch && matchType && matchPhase;
});
```

---

## 5. 实施 Sub-steps (a1 指南)

### T4.1: Trace 基础功能增强 (4h)
1.  **重构 `TracePanel.tsx`**: 引入 `TraceSearchBar` 和 `TraceFilter`。
2.  **实现 `useTraceFilter`**: 状态管理（searchTerm, eventTypes）。
3.  **UI 打磨**: 为每种 `event_type` 制作彩色 Badge（如 LLM: 蓝色, Tool: 绿色, Error: 红色）。
4.  **详情折叠**: 默认只显示事件名和摘要，点击展开 `JSON.stringify(payload)`。

### T4.2: 跨组件联动实现 (4h)
1.  **Graph → Trace**: 
    *   修改 `GraphCanvas.tsx`，添加 `onNodeClick` 属性。
    *   点击节点时，设置 `activePhase`，使 Trace 视图仅显示该 Phase 的事件。
2.  **Trace → Graph**:
    *   点击 Trace 事件时，若是错误或关键节点，通知 `GraphCanvas` 对应的 Node 渲染高亮边框。
3.  **Trace → Monaco**:
    *   点击事件（或详情中的链接）时，根据 `phase_name` 在代码中正则匹配 `name: \s*phase_name` 找到行号，调用 `onJumpToLine`。

### T4.3: 错误诊断增强 (2h)
1.  专门针对 `internal_error` 和 `validation_fail` 渲染醒目的错误卡片。
2.  解析 `InternalErrorEvent` 的 `error_message`，尝试提取有意义的调试线索。

### T4.4: 验证与集成 (1h)
1.  验证多层 Subgraph 展开后的 Phase 匹配逻辑。
2.  测试在极长 Trace（500+ 事件）下的过滤性能。

---

## 6. 风险点与缓解
*   **正则匹配误差**: 两个 Phase 重名（虽然编译器已禁止）。
    *   *缓解*: 严格匹配 YAML 结构的 `name: ` 模式。
*   **性能下降**: 每次过滤都遍历所有事件。
    *   *缓解*: 使用 `useMemo` 缓存过滤结果。
*   **ReactFlow 兼容性**: 旧版 ReactFlow 不支持某些样式注入。
    *   *缓解*: 统一使用 `setNodes` 的方式更新节点的 `className`。

## 7. 验收 Checklist
- [ ] Trace 顶部搜索框实时生效。
- [ ] 点击“Error”过滤标签可快速定位失败点。
- [ ] 每一个 Trace 事件均有彩色标识，且可点击展开 Raw Payload。
- [ ] 点击左侧画布节点，右侧 Trace 自动同步过滤该 Phase。
- [ ] 错误事件点击后，代码编辑器自动滚动并定位到对应 Phase 定义行。
- [ ] 暗色模式完美适配。
