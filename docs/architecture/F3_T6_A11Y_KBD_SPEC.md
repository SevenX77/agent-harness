# F3_T6_A11Y_KBD_SPEC (无障碍与键盘导航)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务是 F3 阶段及整个 Skill Studio 打磨计划的最后一环。我们将通过完善 **ARIA (Accessible Rich Internet Applications)** 标签、优化 **Tab 键焦点流 (Focus Flow)** 以及引入 **方向键导航能力**，提升系统的包容性与操作效率。这不仅能让 Studio 符合现代 Web 的无障碍标准，更能让习惯于键盘驱动的 PM 实现“脱离鼠标”的深度研发体验。

## 2. PM 痛点

### 2.1 现状
*   **交互断层**: 许多核心面板（如 Trace 列表）只能通过鼠标精准点击，无法使用键盘快速上下浏览。
*   **焦点陷阱**: 打开模态框（Wizard）或侧边抽屉（Drawer）后，Tab 键可能依然在底层页面移动，导致操作迷失。
*   **语义模糊**: 纯图标按钮（如 Sidebar 的 + 号）由于缺乏 `aria-label`，对使用屏幕阅读器的用户完全不可用。

### 2.2 理想 UX
*   **焦点受控**: 打开向导或 Phase 编辑器时，焦点自动锁定在首个输入框，并在关闭时精准归还给原触发元素。
*   **极速浏览**: 在 Trace 视图中，使用 ↑/↓ 键即可在事件之间切换，且联动右侧详情自动展开。
*   **语义清晰**: 每个功能按钮均有明确的屏幕阅读器描述，确保信息的平权访问。

---

## 3. 实施 Sub-steps (a1 指南)

### T6.1: ARIA 语义补全与焦点管理 (1.5h)
1.  **语义化标注**: 
    *   `SkillSidebar`: 添加 `role="navigation"` 与 `aria-label="Skill List"`。
    *   `HeaderBar` 图标按钮: 补全 `aria-label`（如 "Lint code", "Save skill"）。
    *   `TracePanel`: 添加 `role="log"` 及 `aria-live="polite"`（针对实时流）。
2.  **Focus Trap 实现**: 
    *   在 `SkillCreatorWizard` 与 `PhaseDrawer` 打开时，拦截 Tab 键，使其仅在内部循环。
    *   关闭时，手动恢复 focus 到之前的触发点。

### T6.2: Trace 面板方向键支持 (1h)
1.  **快捷键监听**: 仅当 `TracePanel` 或其内部项被 focus 时，监听 ↑/↓。
2.  **逻辑联动**: 
    *   ↑/↓: 修改 `selectedEventId` 并自动触发 `scrollIntoView({ block: 'nearest' })`，确保选中项始终可见。
    *   Enter/Space: 切换当前选中事件的展开/折叠状态。

### T6.3: 画布节点键盘导航 (1h)
1.  **节点入栈**: 确保 ReactFlow 节点具有 `tabIndex={0}`。
2.  **节点跳转**: 利用 ReactFlow 内置的 `onNodesDelete` / `onSelectionChange` 配合键盘事件，支持使用方向键在已渲染的 Phase 节点间进行视觉焦点的初步切换。

### T6.4: 最终验证 (0.5h)
1.  使用浏览器控制台运行 a11y 检查工具（或 Lighthouse）。
2.  全流程单手操作演示：从新建技能到编辑 Prompt，再到运行并查阅 Trace，全程不触碰鼠标。

---

## 4. 风险与缓解
*   **Monaco 冲突**: Monaco 编辑器内部极度依赖方向键进行光标移动。
    *   *缓解*: 仅当焦点在编辑器外部（如 TracePanel 或 Sidebar）时才启用全局导航快捷键。
*   **浏览器默认行为**: ↑/↓ 本身会触发容器滚动。
    *   *缓解*: 在捕获事件后使用 `e.preventDefault()` 屏蔽原生滚动，改由逻辑受控滚动。

## 5. 验收 Checklist
- [ ] Tab 键可以访问到 UI 中的每一个功能按钮，且顺序符合直觉。
- [ ] 弹出向导时，底层元素变得不可选中（Focus Trap）。
- [ ] Trace 面板支持 ↑/↓ 键快速切选事件。
- [ ] 所有纯图标按钮在开发者工具中显示有明确的 `aria-label`。
- [ ] 导出报告（F3 T5）的 HTML 文件也保留了基本的 a11y 结构。

---

## F3 Phase 结项说明
至此，F3 计划的所有 6 项任务 Spec 已全部交付。Skill Studio 从核心闭环、效率工具到性能与健壮性打磨已完成全案工程规划，可转入全面实施。
