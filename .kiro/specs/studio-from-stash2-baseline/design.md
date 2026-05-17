# Design: Architecture & Implementation

> **Status**: Draft v0.1
> **Date**: 2026-05-17
> **Author**: a2 (Gemini)

## §1 Data Flow

所有组件的联络全部上升至顶层 **`Workspace.tsx` React Context** 进行协调。

- 建立统一的 Context 管理 `navStack` (下钻路径)、`activeFiles` (当前打开的文件集合)。
- Canvas 节点双击、`AssetsPanel` 树节点点击，均直接调用 Context 的 `onFileOpen(path)`。
- Context 更新状态，驱动下游 `SplitEditor` 重新渲染，独立控制左侧或右侧 Monaco 加载新文件。

## §2 Frontend 改动文件清单

- `apps/studio/frontend/src/components/studio/Workspace.tsx`:
  - 包裹顶层 Context (管理 `navStack`, `activeFiles`)，提供 `onFileOpen` 统一分发管线。
- `apps/studio/frontend/src/components/studio/Panels.tsx` (`AssetsPanel`):
  - 改造 `manifestFiles()` 函数枚举并展示 V2.1 引擎定义的 `/phases` 和 `/io` 树。
- `apps/studio/frontend/src/components/studio/SplitEditor.tsx`:
  - 配置为容纳左右两个独立 `LazyMonacoPanel` 的布局，支持独立加载。
- `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx` / `MonacoPanel.tsx`:
  - 注入 `useDebounceCallback(1500ms)` 执行实时保存。
  - 在 `useEffect` 的 cleanup 阶段执行强行 `flush()`。
  - 添加写盘 HTTP 错误静默重试与 Toast 阻断逻辑。
- `apps/studio/frontend/src/components/studio/GraphCanvas.tsx` (or 现有 Canvas 容器):
  - Phase 节点 `onDoubleClick` 触发 Context `onFileOpen`。
  - Subgraph 节点 `onDoubleClick` 触发 Context `navStack.push()` 实现下钻。
- `apps/studio/frontend/src/components/studio/center-action-bar.tsx` (或 `Header.tsx`):
  - 基于 `navStack` 渲染 Breadcrumb 面包屑导航。

## §3 Backend 改动文件清单

- `apps/studio/backend/app/core/ports/metadata.py` (及 Adapters):
  - 基于现有的 71 行雏形，增建对 V2.1 `<skill_id>/phases/...` 与 `/io` 等层级路径的本地物理盘 I/O 读写。
- `apps/studio/backend/app/services/skills.py` & `routers/skills.py`:
  - 适配 V2.1 `compile_skill` / `run_skill` 新签名接驳。
  - 提供无状态写盘 Helper API，专供 Monaco 实时调用。
- `apps/studio/backend/app/services/file_watcher.py` (新增):
  - 启动 `watchfiles` 守护线程，建立 Echo 过滤机制以拦截从 Studio API 发起的自产出变更。
- `apps/studio/backend/app/services/event_bus.py`:
  - 将过滤后的外部 IDE 改动封装成 WebSocket `skill_changed` 消息推送。

## §4 实时保存策略 (Auto-save)

- **拦截输入**：OnChange 触发 1500ms Timer，剥离脏标记。
- **强制切出**：`useEffect` unmount 触发时调用 `flush()` 发起同步 HTTP POST 提交。
- **静默容错**：400/500 HTTP Error 启动后台指数退避重试 (Silent Retry)，连续 3 次报错触发屏幕警告 Toast/Banner 提示。

## §5 多端同步与防回环

1. **Echo Filter**: 后端通过时间戳比对或瞬时 Token，短路掉 `watchfiles` 对于由于 Studio API 所产出的写动作回调。
2. **WebSocket 派发**: 对于合法捕捉到的外部 IDE 改动下发 WS。
3. **前端多端冲突阻断**: 若前端某路径尚存 active 的 1500ms 防抖倒计时，此时收到针对同一路径的 Reload WS 事件，则立即中止 Reload 并抛出 Dialog: `Local vs Remote (Keep Local / Use Remote / Diff)` 交互。

## §6 Subgraph Drill-down

- Context 提供 `navStack: string[]`。
- 画布仅按栈顶环境渲染。面包屑从左至右依据 `navStack` 渲染路径节点，点击父层级即执行 `navStack.pop()`。下钻后所有层级代码全通透、全可写。

## §7 SplitEditor 双 Monaco

`SplitEditor` 接受两个 Monaco 的装填状态，左右宽度可调，互不干涉，实现如左侧预览 `SKILL.md` 右侧修改 `inputs.json` 的深层对比编辑，解决单文件导致的上下文缺失。

## §8 V2.1 Engine API 适配

对齐最新版本的 GraphAgent Manifest 及 Executor 数据结构，将新抛出的错误序列化为 JSON，供前端 Monaco 定位行级报错。
