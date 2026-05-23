# F3_T2_VIRTUAL_TRACE_SPEC (虚拟滚动)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

> ## ⚠️ 命名澄清 (2026-05-06 加)
>
> 这份 spec 里的 **"Virtual Trace"** 指的是**前端 DOM 渲染层的虚拟滚动 (Virtual Scrolling) 性能优化**——
> 当 trace 事件多达数千条时, 浏览器只渲染当前可见视口内的 ~20-30 个节点, 滚出去的节点 unmount。
>
> **它不是** PM 工作流里的 **`Predict` 功能**(用 LLM 模拟跑 skill 推算业务逻辑流, 不烧真 token)。
> Predict 设计在另一份 spec: `docs/architecture/PREDICT_SPEC.md` (Gemini 2026-05-06 起草)。
>
> 两件事完全无关, 只是中文翻译都用了"虚拟"二字, 容易混淆。
> 决策上下文: `docs/architecture/POST_PLAN_C_FINAL_DECISIONS.md` 第 4 节。

## 1. Executive Summary

本任务旨在解决大型技能在长时间运行后，Trace 面板产生的上千个 DOM 节点导致浏览器卡顿的问题。通过引入 **虚拟滚动 (Virtual Scrolling)** 技术，我们将 Trace 渲染限制在当前可见视口内（约 20-30 个节点），无论总事件数是 100 还是 10,000，内存占用和渲染性能都将保持恒定。核心挑战在于处理 Trace 事件可展开（Expandable）导致的动态高度计算。

## 2. PM 痛点

### 2.1 现状
*   **浏览器假死**: 运行一个含有循环的大型技能，产生 1000+ 条 Trace 事件后，滚动页面会出现明显的掉帧。
*   **交互延迟**: 此时进行搜索、过滤或点击查看详情，浏览器响应时间从毫秒级退化到秒级。
*   **内存激增**: 数千个复杂的 DOM 节点（包含 JSON Payload 详情）会迅速消耗数百 MB 内存。

### 2.2 理想 UX
*   **丝滑滚动**: 始终保持 60 fps 的滚动体验。
*   **透明感**: 用户在滚动时感觉不到“虚拟化”的存在，无闪烁或空白。
*   **状态保留**: 滚动出视口的事件在重新进入视口时，其展开状态（Expanded）和选中状态（Selected）需完美保留。

## 3. 技术决策

### 3.1 方案选择
*   **不引新依赖**: 遵守 F3 阶段“零新 npm dep”原则。
*   **自主实现**: 采用基于 `scrollTop` 的原生 Windowing 算法。由于 Trace 事件大部分高度统一（Collapsed 状态），自主实现的复杂度可控且更轻量。

### 3.2 实现原理
1.  **容器监听**: 监听 `TracePanel` 容器的 `onScroll` 事件。
2.  **索引计算**: 根据 `scrollTop` 和预估行高 `rowHeight` 计算当前视口的 `startIndex` 和 `endIndex`。
3.  **切片渲染**: 仅渲染 `traceLogs.slice(startIndex, endIndex + buffer)`。
4.  **高度撑起**: 使用一个空的 `div` (Spacer) 撑开总高度，或使用 `padding-top` 偏移列表。

---

## 4. 前端组件设计

### 4.1 目录结构
```
apps/studio/frontend/src/
├── components/trace/
│   ├── TracePanel.tsx (改造)    # 作为 Scroll 容器
│   ├── VirtualTraceList.tsx    # 核心虚拟化逻辑
│   └── TraceEventRow.tsx       # 适配高度测量
└── hooks/
    └── useVirtualScroll.ts      # 通用索引计算 Hook
```

### 4.2 关键 Hook 设计 (`useVirtualScroll.ts`)
```typescript
interface VirtualConfig {
  itemCount: number;
  itemHeight: number; // 默认高度 (e.g. 48px)
  overscan?: number;  // 预渲染缓冲区数量 (默认 5)
}

export function useVirtualScroll(containerRef: RefObject<HTMLElement>, config: VirtualConfig) {
  // 1. 获取容器 scrollTop
  // 2. 计算可见范围
  // 3. 返回 { startIndex, endIndex, translateY }
}
```

---

## 5. 实施 Sub-steps (a1 指南)

### T2.1: 基础算法与 Hook 实现 (3h)
1.  实现 `useVirtualScroll.ts`:
    *   使用 `useSyncExternalStore` 或简单的 `onScroll` 状态。
    *   计算总高度：`itemCount * itemHeight`。
    *   计算偏移量，防止滚动时元素跳变。
2.  编写简单的列表 Demo 验证算法。

### T2.2: Trace 列表虚拟化改造 (3h)
1.  **重构 `TracePanel.tsx`**: 移除直接的 `.map()` 渲染。
2.  **引入 `VirtualTraceList.tsx`**: 
    *   负责渲染 Spacer。
    *   将 `filteredEvents` 传给虚拟列表。
3.  **适配展开高度**: 
    *   V1: 采用“固定高度”策略，即使展开也按固定高度滚动（可能产生裁剪，仅作第一步）。
    *   V2: 引入 `itemHeightEstimate`，针对展开项通过 `expandedEventIds` Set 计算额外偏移量。

### T2.3: 性能测试与调优 (2h)
1.  使用 F3 T1 的 Batch Runner 跑出 1000+ 事件。
2.  在 Chrome Performance Tab 确认滚动无 `Long Task`。
3.  验证暗色模式与选中高亮逻辑。

---

## 6. 风险点与缓解
*   **动态高度偏移**: 展开 Trace 详情后高度翻倍。
    *   *缓解*: 维持一个 `heightMap` 记录已展开项的高度，或者在 V1 中优先保证 Collapsed 状态下的虚拟化性能。
*   **键盘导航失效**: 使用 `Tab` 键切换时，目标元素可能不在 DOM 中。
    *   *缓解*: 监听 `focus` 事件，当焦点移向视口边缘时主动滚动容器。

## 7. 验收 Checklist
- [ ] 1000+ 条事件下滚动不掉帧。
- [ ] 顶部 Search/Filter 后的列表依然能正常进行虚拟滚动。
- [ ] 快速拖动滚动条，列表内容能够即时呈现（无白屏）。
- [ ] 点击展开某个事件详情，虚拟列表不会崩溃或跳动。
- [ ] 滚动出视野再滚回来，之前的选中高亮依然存在。
