---
spec: split-editor-focus-enhancement
status: Draft
target_goal: "Split Editor 双屏模式的 active focus 状态机, 支持选中窗口打开文件"
linked_code_paths:
  - apps/studio/frontend/src/components/studio/SplitEditor.tsx:59
  - apps/studio/frontend/src/components/studio/Workspace.tsx:108
  - apps/studio/frontend/src/components/studio/WorkspaceContext.tsx
linked_specs:
  - docs/studio/STUDIO_LAYOUT_SPEC.md
  - .kiro/specs/studio-frontend-v21-multifile-editor/
last_updated: 2026-05-19
---

# Requirement: Split Editor Focus Enhancement

## 1. 问题陈述 (Problem Statement)
### 1.1 现状痛点
当前的 Split Editor 仅仅支持左右双开，但缺失了一个最核心的 IDE 机制：“活动焦点”（Active Focus）。
目前代码在打开文件时，逻辑粗暴地写死在 `handleFileOpen` 中：如果有双开模式，就永远去挤占另一侧，完全没有考虑到用户希望“在当前我正在看的这个槽位中打开新文件”的自然诉求。

### 1.2 为什么需要这个 spec
- **PM 原话引用**: "关于 split editor 插一嘴，开启 split 模式后，两个编辑窗口要有选中状态，选中窗口点击文件，就在选中的窗口打开文件。"
- **状态机缺失**: 我们在更新 `STUDIO_LAYOUT_SPEC` 时发现，不仅视觉上缺少对选中槽位的高亮边框，在 `WorkspaceContext` 状态机的流转里也缺少 `activeFocusSide` 这个关键指针，必须以新的独立 Spec 来补充开发这一增强特性。

## 2. 用户故事 (User Stories)
1. **As a PM**, I want 在双开代码窗口时，点击其中一个，该窗口周围出现明显的焦点高亮，so that 我清楚地知道我当前的操作主要作用于哪个窗体。
2. **As a PM**, I want 当我在左侧窗口聚焦时，在文件树里单击一个新文件，它能在左侧窗口覆盖打开，so that 右侧的参考代码不会被意外替换掉。
3. **As a PM**, I want 关闭 active focus side 的编辑窗口时，系统能智能退回到单一视图或者把焦点转移给剩下的窗口，so that 我不需要重新建立上下文。

## 3. Acceptance Criteria
### User Story 1 (视觉 Focus)
- **Given** PM 在 Split Editor 双屏模式下点击某一侧编辑窗口, **When** 点击发生时, **Then** THE SYSTEM SHALL 将该窗口标记为 active focus side (视觉上加边框 / 高亮)。
- **Given** 当前 Focus 在左侧，**When** 用户点击右侧编辑器区域，**Then** THE SYSTEM SHALL 立即将焦点视觉效果切换到右侧，同时取消左侧的高亮。

### User Story 2 (Focus 绑定打开)
- **Given** 左侧已被标记为 active focus side，**When** PM 选中 active focus side 后从 AssetsPanel 单击文件 `A.md`, **Then** THE SYSTEM SHALL 在 active focus side 编辑窗口（即左侧）打开该文件 (而不是默认的去右侧新建)。

### User Story 3 (关闭回退机制)
- **Given** 左侧为 active focus 且有左右双屏，**When** PM 关闭 active focus side 编辑窗口, **Then** THE SYSTEM SHALL 把另一窗口（右侧）设为 active focus, 或在只剩一个文件时完全退出 split 模式。

## 4. 范围 (In Scope vs Out of Scope)
### In Scope
- SplitEditor 组件中关于左右两侧槽位的事件拦截与 Focus 样式注入。
- `WorkspaceContext` 中 `activeFocusSide` 状态的增加及分发。
- 修改 `Workspace.tsx` 中的 `handleFileOpen`，依据 Focus 状态来决定打开侧。

### Out of Scope
- 多 Tab 支持（横向堆叠数十个文件 Tab不在MVP0范围）。
- 窗口的任意拖拽停靠（Docking / Floating Layout），超出本次增强范畴。

## 5. 依赖与前置条件
- 依赖于现有的 `.kiro/specs/studio-frontend-v21-multifile-editor/` 所打下的双开基建。
- 受制于 `docs/studio/STUDIO_LAYOUT_SPEC.md` 中定义的布局规范。

## 6. 关键约束
- **无缝光标集成**: 记录 Active Focus 不能影响 Monaco 编辑器自身的光标截获行为。不能出现“点了一下外层容器获取 Focus，但要再点一下 Monaco 才能打字”的割裂感。
- **兜底默认值**: 如果因任何异常导致 `activeFocusSide` 丢失，默认降级指向 `left`。

## 相关文档
- [STUDIO_LAYOUT_SPEC.md](../../../docs/studio/STUDIO_LAYOUT_SPEC.md)
