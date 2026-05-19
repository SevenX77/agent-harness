# Studio Canvas v1 — Tasks

> **Status**: Draft, v0.1, 2026-05-14
> **Implementer**: a1 (Codex)
> **Spec link**: requirements.md / design.md (本 spec dir)
> **Branch**: 复用当前 `feat/copilot-v1-backend` (跟 parent master 共用, 不开新 branch — 待 主控 确认)
> **预估**: 总 ≈ 9 小时 a1 工作时间
> **Scope**: 仅 v1 (visual + design-time), v2 (run-time trace 接入) 推迟

本批次任务清单仅覆盖 design v1 scope。涉及 v2 的组件骨架仅写 Tooltip + 占位接口, 不接 trace pipeline；`Trace Store` / WebSocket 订阅、Run-time Edge Dot 实色高亮、`EdgeContextCard`、`Popover`、readonly Monaco JSON Viewer 均不在本批次实施。

## 任务总览

```
T1  移除 Canvas 左上角 Title 框                         ── 0.5h
T2  ContextEdge 骨架: 去箭头 + Edge Dot + Tooltip       ── 1.5h
T3  Global Input/Output Node 组件                       ── 1.5h
T4  GraphCanvas 注入 I/O 节点并自动推导全局边             ── 2h
T5  Subgraph +/- Icon Button 与双击拦截                  ── 1.5h
T6  Vitest 覆盖边推导与 ContextEdge 设计态                ── 1.5h
T7  端到端视觉验收与截图记录                              ── 1h
```

各 task 落地后, a1 自测 + 自审；若主控需要, 再请 a2/a3 做视觉与 e2e audit。

---

## T1: 移除 Canvas 左上角 Title 框

### 依赖

无。

### 文件 + 改动

**`apps/studio/frontend/src/components/GraphCanvas.tsx`**:

1. 移除 `<section>` 内左上角 absolute Title UI 区块。
2. 保留 error/loading/cycle overlay 的现有位置与表现, 不改 React Flow 主体行为。
3. 不新增替代标题, skill 名称仍由全局 Header 承载。

### 测试

**`apps/studio/frontend/src/components/GraphCanvas.test.tsx`** (如已有则追加, 否则新建):

- 渲染 `GraphCanvas` 后, 断言不再出现 `Edit graph` 文本。
- 保留 loading/error 文案快照或 DOM 断言, 防止误删 overlay。

### 验收

- `pnpm test GraphCanvas` pass。
- Manual: 打开 Workspace, Canvas 左上角无悬浮 title 框；loading/error overlay 仍按原位置展示。

---

## T2: ContextEdge 骨架: 去箭头 + Edge Dot + Tooltip

### 依赖

T1 可并行, 无强依赖。

### 文件 + 改动

**`apps/studio/frontend/src/components/edges/ContextEdge.tsx`** (新增):

1. 按 design §2.2 实现 React Flow custom edge: `getBezierPath` + `EdgeLabelRenderer`。
2. 在曲线中点渲染 design-time 空心灰色 Edge Dot button。
3. Hover Dot 显示 Tooltip 文案 `运行后可查看传递数据`；Click 在 `hasTraceData=false` 时无响应。

**`apps/studio/frontend/src/components/GraphCanvas.tsx`**:

1. 注册 `edgeTypes.contextEdge`。
2. `onConnect` 新边统一设为 `type: 'contextEdge'`。
3. 删除 `MarkerType.ArrowClosed` import 与 `markerEnd` 设置, 确保拖拽连线也无箭头。

### 测试

**`apps/studio/frontend/src/components/edges/ContextEdge.test.tsx`** (新):

- `hasTraceData=false` 时渲染 Edge Dot button。
- Hover Dot 显示 Tooltip 文案。
- Click Dot 不打开任何 card/popover, 不抛错。

### 验收

- `pnpm test ContextEdge GraphCanvas` pass。
- Manual: Canvas 中所有边无箭头；每条边中点有灰色空心 Dot；Hover 出现 Tooltip, Click 无弹窗。

---

## T3: Global Input/Output Node 组件

### 依赖

无；T4 会接入。

### 文件 + 改动

**`apps/studio/frontend/src/components/nodes/GlobalInputOutputNode.tsx`** (新增):

1. 按 design §2.1 选项 A 实现 `InputNode` / `OutputNode` 共用组件。
2. 复用 `skillnode-spec.md` 的 Card 骨架、圆角、阴影与语义 token；Input 顶部 accent 用 `--primary`, Output 用 `--muted-foreground`。
3. 渲染 `manifest.io.inputs` / `manifest.io.outputs` 的第一层字段名与类型 Badge；完整 JSON 查看入口仅保留只读图标按钮占位, 不接 Monaco。

**`apps/studio/frontend/src/components/GraphCanvas.tsx`**:

1. 引入新组件并注册 `nodeTypes.globalInput` / `nodeTypes.globalOutput`。
2. 不在本 task 改 `buildNodes`; 仅保证组件可注册。

### 测试

**`apps/studio/frontend/src/components/nodes/GlobalInputOutputNode.test.tsx`** (新):

- Input 模式显示 `Input` 标识、字段名、类型 Badge。
- Output 模式显示 `Output` 标识、字段名、类型 Badge。
- 空 schema 时显示克制的 empty state, 不撑破节点布局。

### 验收

- `pnpm test GlobalInputOutputNode` pass。
- Manual/Story render: 节点宽度稳定, 字段文本不溢出, dark mode token 可读。

---

## T4: GraphCanvas 注入 I/O 节点并自动推导全局边

### 依赖

依赖 T2、T3。

### 文件 + 改动

**`apps/studio/frontend/src/components/GraphCanvas.tsx`**:

1. 扩展 node/edge data 类型, 定义 `GlobalNodeData` 与 `ContextEdgeData`；`hasTraceData` 在 v1 始终为 `false`。
2. `buildNodes` 基于 `manifest.io` 注入 `global-input` 与 `global-output` 节点, 作为普通节点参与 dagre 布局。
3. `buildEdges` 按 design §5 P1-1 推导边: 无前置依赖的 phase 由 Input 指向；未被其他 phase 依赖的 phase 指向 Output；空 phase 时 Input 直连 Output；所有边类型为 `contextEdge`。

**`apps/studio/frontend/src/lib/layout.ts`**:

1. 如 I/O 节点高度与 phase 节点不同, 以最小改动支持节点自带宽高或安全 fallback。
2. 保持 cycle detection 现有行为。

### 测试

**`apps/studio/frontend/src/components/GraphCanvas.test.tsx`**:

- 覆盖串行、并行分叉、单节点、空节点 4 种 `buildEdges` 推导场景。
- 断言所有自动边 `type === 'contextEdge'` 且无 `markerEnd`。
- 断言每条边 data 含 `hasTraceData=false`、`sourcePhaseId`、`targetPhaseId`。

### 验收

- `pnpm test GraphCanvas` pass。
- Manual: 常见 graph skill 中 Input/Output 节点出现在 dagre 排布两端, phase 节点均位于两者之间；复杂图没有明显重叠。

---

## T5: Subgraph +/- Icon Button 与双击拦截

### 依赖

T1 可并行；建议在 T4 后做一次整体视觉检查。

### 文件 + 改动

**`apps/studio/frontend/src/components/GraphCanvas.tsx`**:

1. 将 Subgraph 旧文字按钮替换为节点底部绝对定位 `+` / `-` icon button。
2. 使用 lucide-react `Plus` / `Minus`, `aria-label="展开子图"` / `"收起子图"`。
3. 对 Subgraph 节点双击事件 `stopPropagation` 并静默无响应, 避免与未来 Drill-down 冲突。

**`apps/studio/frontend/src/components/studio/SubgraphInline.tsx`**:

1. 必要时微调上边距/边框, 避免底部 icon button 与 inline 内容重叠。
2. 不改变 inline 内容的数据来源与展示逻辑。

### 测试

**`apps/studio/frontend/src/components/GraphCanvas.test.tsx`**:

- 有 `subgraphPath` 的节点显示 `展开子图` icon button。
- 点击后按钮 aria-label 变为 `收起子图`, `SubgraphInline` 出现。
- 双击 Subgraph 节点不触发额外展开/收起或导航。

### 验收

- `pnpm test GraphCanvas` pass。
- Manual: Subgraph 节点底部按钮位置稳定, 单击展开/收起顺滑；双击节点主体无响应；按钮不会遮挡 React Flow Handle。

---

## T6: Vitest 覆盖边推导与 ContextEdge 设计态

### 依赖

依赖 T2、T4、T5。

### 文件 + 改动

**`apps/studio/frontend/src/components/GraphCanvas.tsx`**:

1. 如测试需要, 导出纯函数 `phasesFromManifest` / `buildNodes` / `buildEdges` 或迁移到轻量 helper, 不改变运行时行为。

**`apps/studio/frontend/src/components/GraphCanvas.test.tsx`**:

1. 整理 T1/T4/T5 追加的 case, 去除脆弱快照, 以 DOM 与纯函数断言为主。

**`apps/studio/frontend/src/components/edges/ContextEdge.test.tsx`**:

1. 固化 design-time `hasTraceData=false` 的 Dot、Tooltip、Click no-op 行为。

### 测试

- 串行、并行分叉、单节点、空节点的边推导均为 deterministic。
- ContextEdge 不依赖 Trace Store/WebSocket 即可独立渲染。
- Subgraph `+/-` aria 行为可由 Testing Library 查询。

### 验收

- `pnpm test GraphCanvas ContextEdge` pass。
- `pnpm lint` 无新增 lint error。
- 测试中不得 mock 或引入 trace pipeline、Popover、Monaco。

---

## T7: 端到端视觉验收与截图记录

### 依赖

依赖 T1-T6。

### 文件 + 改动

**`apps/studio/frontend/tests/e2e/edit-workflow.spec.ts`** (或现有 Canvas 覆盖文件):

1. 增加轻量 e2e 断言: Workspace 打开后不存在 `Edit graph` title 框。
2. 断言 Input/Output 节点文本存在。
3. 断言 Subgraph `+/-` 按钮可聚焦且 aria-label 正确。

**`apps/studio/frontend/tests/e2e/canvas-v1.spec.ts`** (如新增更清晰, 则用此文件替代上面的追加):

1. 只覆盖 v1 design-time 视觉行为。
2. 不启动 run trace, 不断言 runtime JSON viewer。

### Test plan

按 `requirements.md §4` 与 `design.md §7` 验收:

- [ ] **US-1**: Input/Output 节点参与布局, phase 被连在两者之间。
- [ ] **US-2**: 边无箭头, 中点 Dot hover 有 Tooltip, click no-op。
- [ ] **US-3**: Subgraph `+/-` icon button 展开/收起 inline 内容。
- [ ] **US-4**: Canvas 左上角无冗余 title 框。

### 验收

- `pnpm test:e2e --grep "canvas"` pass, 或按仓库现有 Playwright 命令运行对应 spec pass。
- Desktop 与窄屏各截一张图, 对照 `skillnode-spec.md` 检查节点圆角、阴影、Handle、文字无重叠。

---

## Out of scope (本批次不做)

- Trace Store / WebSocket 订阅接入。
- Run-time Edge Dot 实色高亮。
- `EdgeContextCard`、shadcn `Popover`、readonly Monaco JSON Viewer。
- Agent-Loop 微观拓扑展开。
- Drill-down 下钻模式。
- 工具栏 Lock 业务语义改造。
