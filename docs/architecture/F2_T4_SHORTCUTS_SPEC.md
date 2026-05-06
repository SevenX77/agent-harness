# F2_T4_SHORTCUTS_SPEC (Keyboard Shortcuts & Palette)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在为 Skill Studio 引入一套完整的键盘驱动工作流。通过实现全局快捷键监听与命令面板（Command Palette），PM 可以摆脱繁琐的鼠标点击，实现保存、运行、技能切换及命令探索的“盲打”体验。核心组件包括支持模糊搜索的 `CommandPalette`、`SkillPalette` 以及可视化快捷键指南，显著提升专业用户的研发效率。

## 2. PM 痛点

### 2.1 现状与挑战
*   **交互效率低**: 频繁在“修改-保存-运行-看结果”之间切换，每次都需要寻找小小的按钮，打断思考流。
*   **发现成本高**: Studio 功能日益增多（Wizard, Diff, History），PM 不知道有哪些高级功能可用。
*   **切换不便**: 当项目中有 20+ 个 Skill 时，在侧边栏滚动寻找目标 Skill 非常低效。

### 2.2 理想 UX
*   **快如闪电**: `Cmd+S` 瞬间保存并触发 Lint，`Cmd+Enter` 立即运行。
*   **一键搜索**: `Cmd+P` 弹出搜索框，输入关键字秒切技能。
*   **全能面板**: `Cmd+K` 列出所有可用命令（新建、暗色模式切换、打开 CLI 等）。
*   **无处不在的帮助**: 按 `?` 弹出快捷键清单，无需翻阅文档。

## 3. 关键技术设计

### 3.1 快捷键冲突处理
*   **上下文感知**: 当焦点在 `input`, `textarea` 或 Monaco 编辑器内部时，全局快捷键（如 `Cmd+S`）应优先由组件自身处理或静默，避免干扰正常文字输入。
*   **统一分发**: 使用 `useGlobalShortcuts.ts` 集中管理 `keydown` 事件，并通过 `preventDefault` 拦截浏览器默认行为。

### 3.2 模糊搜索算法
*   对于技能搜索和命令过滤，采用简单的子串匹配（Substring Match）或简单的权重算法（Score based on match position），确保搜索体验流畅。

---

## 4. 前端组件设计

### 4.1 目录结构
```
apps/studio/frontend/src/
├── components/shortcuts/
│   ├── CommandPalette.tsx     # 主命令面板 (Cmd+K)
│   ├── SkillPalette.tsx       # 技能快速切换 (Cmd+P)
│   └── ShortcutsCheatSheet.tsx # 快捷键清单 (?)
├── hooks/
│   └── useGlobalShortcuts.ts  # 全局键盘事件注册 Hook
└── utils/
    └── hotkeys.ts             # 跨平台映射 (Cmd vs Ctrl)
```

### 4.2 快捷键注册清单

| 快捷键 | 动作 | 目标方法 |
| :--- | :--- | :--- |
| `Cmd/Ctrl + S` | 保存并 Lint | `handleSave()` |
| `Cmd/Ctrl + Enter` | 运行技能 | `handleRun()` |
| `Cmd/Ctrl + P` | 快速搜索技能 | `setSkillPaletteOpen(true)` |
| `Cmd/Ctrl + K` | 全令面板 | `setCommandPaletteOpen(true)` |
| `Cmd/Ctrl + N` | 新建技能 | `setCreatorOpen(true)` |
| `Esc` | 关闭当前弹窗 | `closeModals()` |
| `?` (Shift + /) | 显示帮助 | `setCheatSheetOpen(true)` |

---

## 5. 实施 Sub-steps (a1 指南)

### T4.1: 全局快捷键基础设施 (1h)
1.  实现 `useGlobalShortcuts.ts`:
    *   监听 `window.keydown`。
    *   封装 `isInputFocused()` 工具函数。
2.  在 `App.tsx` 中挂载此 Hook，并绑定首批核心动作（Save, Run, Create）。

### T4.2: 命令面板与技能搜索 (2h)
1.  **SkillPalette**: 
    *   渲染 Modal。
    *   列表显示所有 `skills`，支持模糊过滤。
    *   选中后调用 `onSelectSkill`。
2.  **CommandPalette**:
    *   注册静态命令列表（"Toggle Dark Mode", "Open Terminal", "New Skill"）。
    *   选中后触发对应回调。

### T4.3: Shortcuts Cheat Sheet (1h)
1.  实现 `ShortcutsCheatSheet.tsx`:
    *   分组展示快捷键及其描述。
    *   支持 `?` 键触发。

### T4.4: 联调与平台适配 (0.5h)
1.  确保在 Windows 下自动识别 `Ctrl` 替代 `Cmd`。
2.  确保 Monaco 编辑器的内部快捷键（如搜索）不被全局拦截。

---

## 6. 风险点与缓解
*   **Monaco 冲突**: Monaco 有自己的快捷键系统。
    *   *缓解*: 仅在 Monaco 失去焦点或特定非冲突键时触发全局逻辑，或者在 `onEditorMount` 中将 Studio 核心快捷键注入 Monaco。
*   **快捷键遮蔽**: 某些系统快捷键可能无法被拦截。
    *   *缓解*: 避免使用浏览器核心快捷键（如 `Cmd+T`, `Cmd+W`）。

## 7. 验收 Checklist
- [ ] 在编辑 `SKILL.md` 时按 `Cmd+S` 成功保存。
- [ ] 按 `Cmd+P` 并输入部分名字，能成功切换到对应技能。
- [ ] 按 `Esc` 能关闭当前打开的所有 Drawer 和 Modal。
- [ ] 按 `?` 弹出清晰的快捷键说明界面。
- [ ] 暗色模式下 Palette 样式美观。
