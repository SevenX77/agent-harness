---
spec: split-editor-focus-enhancement
status: Draft
target_goal: "Split Editor 双屏模式的 active focus 状态机, 支持选中窗口打开文件"
linked_code_paths:
  - apps/studio/frontend/src/components/studio/SplitEditor.tsx:59
  - apps/studio/frontend/src/components/studio/Workspace.tsx:113
  - apps/studio/frontend/src/components/studio/WorkspaceContext.tsx
linked_specs:
  - docs/studio/STUDIO_LAYOUT_SPEC.md
  - .kiro/specs/studio-frontend-v21-multifile-editor/
last_updated: 2026-05-19
---

# Research: Split Editor Focus Enhancement

## 1. 业内 Split Editor Focus 实现参考

### 1.1 VS Code Split Editor Focus
- **怎么做的**: VS Code 将每个编辑器区域抽象为 `EditorGroup`。当用户在某一个 `EditorGroup` 中点击时，该 Group 获得全局焦点（顶部标题栏字体变亮，未聚焦的 Group 标题栏变灰）。在文件树（Explorer）中单击文件，总是在当前获得焦点的 `EditorGroup` 中打开或替换当前 Tab。
- **能借鉴什么**: “谁聚焦，谁承受操作”是符合心智的铁律。我们必须让左侧树的点击行为紧密绑定这个虚拟的“EditorGroup”焦点概念。

### 1.2 IntelliJ IDEA Split Editor
- **怎么做的**: IDEA 有一套类似的选中状态。不过其特点是：如果你通过快捷键（如 Shift+Enter）或特定的中键点击，可以强制把文件甩到“对面”的未聚焦窗体里去。
- **能借鉴什么**: 对于 MVP，我们遵循最简单的“在焦点处打开”。

## 2. 当前代码 Gap 分析

通过审查现有代码库 `file:line`：

- **打开逻辑硬编码**: 在 `apps/studio/frontend/src/components/studio/Workspace.tsx:113` 处的 `handleFileOpen` 函数中，决定打开哪一侧的代码是这样的：
  `const targetSide = side ?? (splitMode && current.left ? "right" : "left")`
  这里完全没有 `Focus` 的概念，纯粹根据“有没有开启双屏，左侧满了没有”来机械分配。
- **无全局焦点状态**: 在 `WorkspaceContext.tsx` 定义中，仅有 `activeFileDetails`, `splitMode` 等，没有 `activeFocusSide` 的记录。
- **UI 容器缺失拦截**: 在 `SplitEditor.tsx` 中，两个 `LazyMonacoPanel` 并排渲染，外部并没有包裹能够响应 `onClick` 或 `onFocusCapture` 的外层边框容器来追踪哪一侧正在被用户操作。

## 3. 改动范围与状态流转估算

为了引入焦点机制，我们需要评估这会对现有的 React 状态流转产生多大冲击：

### 状态机追加
需要在 `WorkspaceContext` 中引入：
```typescript
type EditorSide = "left" | "right";
const [activeFocusSide, setActiveFocusSide] = useState<EditorSide>("left");
```

### 联动流转
1. **触发设置焦点 (Setter)**:
   - 在 `SplitEditor.tsx` 的两侧渲染区增加 `onFocusCapture={() => setActiveFocusSide("left")}`。由于 Monaco 是在 iframe/worker 内部捕获事件，通常原生的 onClick 可能不管用，必须使用捕获阶段（Capture Phase）的事件，或侦听 Monaco instance 的 `onDidFocusEditorText` 回调。
2. **消费焦点 (Consumer)**:
   - 修改 `Workspace.tsx` 的 `handleFileOpen`：
     `const targetSide = side ?? activeFocusSide`
3. **视觉注入**:
   - `SplitEditor.tsx` 动态计算 className：`className={activeFocusSide === "left" ? "ring-2 ring-primary" : ""}`。

## 4. 关键技术决策点

在进入 Design 阶段前，需确认：
1. **单模式焦点行为**: 当退出 Split Editor 回到单 Editor（比如只有 `left` 时），是否显式保留高亮边框？还是在单窗口时自动隐藏这圈蓝框以减少视觉噪音？（通常单窗口不需要提示焦点）。
2. **Monaco 焦点陷阱**: Monaco 编辑器会拦截大部分的键盘和鼠标事件。如何优雅且非侵入性地探知用户点击了 Monaco 内部的某处？是通过包装层的 `onMouseDownCapture` 还是通过 Monaco API (`editor.onDidFocusEditorWidget`)？

## 5. 推荐方向

我建议：
- **纯粹的 Monaco API 拦截**: 尽量使用 Monaco Editor 实例提供的聚焦事件，这样能确保“光标切过去”与“Focus 态切过去”实现 100% 的同频，不会产生边框亮了但无法打字的割裂。
- **隐去单窗口边框**: 仅在 `splitMode === true` 的情况下渲染 active focus 的边框，保持单屏环境下的极简视觉。

## 相关文档
- [STUDIO_LAYOUT_SPEC.md](../../../docs/studio/STUDIO_LAYOUT_SPEC.md)
- [studio-frontend-v21-multifile-editor](../../.kiro/specs/studio-frontend-v21-multifile-editor/design.md)
