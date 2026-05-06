# F3_T4_DRAFT_RECOVERY_SPEC (草稿恢复与崩溃保护)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在为 Skill Studio 建立一套稳健的“防丢”机制。目前 PM 在 Monaco 编辑器中进行大规模 Prompt 调整时，若遇到浏览器意外刷新、崩溃或误关 Tab，所有未保存的改动将彻底丢失。我们将引入基于 `localStorage` 的实时草稿持久化机制，配合页面退出拦截（beforeunload）与启动时的草稿恢复向导，确保每一行 Prompt 改动都能被安全找回。

## 2. PM 痛点

### 2.1 现状
*   **事故感强**: 在调试复杂的技能逻辑时，PM 可能会花费数小时打磨 Prompt，一旦误操作刷新页面，工作成果清零，挫败感极强。
*   **状态不透明**: 当前 UI 缺乏显式的“未保存（Dirty）”状态提示，PM 往往不确定当前所看的内容是否已成功落盘。

### 2.2 理想 UX
*   **自动保存**: 编辑器内容每秒自动增量序列化至本地存储，用户无感。
*   **退出拦截**: 存在未保存改动时，关闭页面会弹出浏览器标准警告，防止误关。
*   **恢复向导**: 重新打开同一技能时，若检测到本地草稿比磁盘文件更新，主动弹出对话框询问：“检测到未保存的草稿，是否恢复？”并展示简要差异。

## 3. 设计决策

### 3.1 存储策略
*   **技术选型**: 采用 `localStorage`。虽然其有 5MB 限制，但对于单体 `SKILL.md`（通常 < 100KB）而言绰绰有余。
*   **键名规范**: `studio:draft:{skill_id}`。
*   **数据结构**: `{ content: string, timestamp: number, baseHash: string }`。

### 3.2 触发与同步
*   **监听机制**: 挂载在 `MonacoPanel` 的 `onChange` 事件上，设置 1000ms 的 `debounce` 延迟，避免高频 I/O 影响输入流畅度。
*   **冲突处理**: 若磁盘文件已被外部改动（如 git pull），恢复草稿前需提醒用户可能存在的冲突。

---

## 4. 前端组件设计

### 4.1 目录结构
```
apps/studio/frontend/src/
├── hooks/
│   └── useDraftPersist.ts        # 核心 Hook，管理持久化逻辑
└── components/draft/
    ├── DraftRestoreModal.tsx     # 恢复提示模态框
    └── UnsavedIndicator.tsx      # 顶部 HeaderBar 的圆点提示
```

### 4.2 状态流转
1.  `Monaco` 内容变动 -> `useDraftPersist` 更新 `isDirty: true` -> 写入本地存储。
2.  用户点击 `Save` (T3.1) -> 后端写入成功 -> `clearDraft()` -> `isDirty: false`。
3.  页面加载 -> `hasDraft()` ? -> 弹出 `DraftRestoreModal`。

---

## 5. 实施 Sub-steps (a1 指南)

### T4.1: `useDraftPersist` Hook 实现 (2h)
1.  实现核心状态机：管理 `isDirty` 状态。
2.  集成 `lodash.debounce` (或手动实现) 处理写入逻辑。
3.  提供 `restore()`、`discard()` 辅助函数。

### T4.2: 交互增强与 UI 集成 (2h)
1.  **HeaderBar 改动**: 在技能名称旁边增加一个橙色小圆点（`UnsavedIndicator`），仅在 `isDirty` 时显示。
2.  **实现 `DraftRestoreModal`**: 展示草稿保存时间，提供“立即恢复”与“忽略”按钮。

### T4.3: 页面生命周期挂载 (1h)
1.  在 `App.tsx` 的全局 Effect 中添加 `beforeunload` 监听器：
    ```typescript
    window.addEventListener('beforeunload', (e) => {
      if (isAnySkillDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    });
    ```
2.  确保在切换 Skill 时也能触发类似的检查。

### T4.4: 验证与验收 (1h)
1.  手动模拟浏览器崩溃（直接 Kill 进程或强刷）。
2.  验证暗色模式适配。
3.  验证点击“保存”后，草稿被正确清理且小圆点消失。

---

## 6. 风险点与缓解
*   **存储空间满**: 长期不清理过期草稿。
    *   *缓解*: 在应用启动时，清理 7 天前未被访问的草稿键值对。
*   **版本过期**: 恢复了一个月前的草稿到最新的技能上。
    *   *缓解*: 在草稿中记录 `baseHash`（当前文件的最后修改时间或内容哈希），恢复前进行对比，偏差过大时强制要求用户先查看 Diff。

## 7. 验收 Checklist
- [ ] 修改 Prompt 后 1s 内，LocalStorage 中出现对应的 `studio:draft:*` 数据。
- [ ] 未保存时，HeaderBar 显示橙色小圆点。
- [ ] 强刷页面后，弹出“检测到草稿”提示，且点击恢复后内容完美还原。
- [ ] 点击侧边栏其他技能，若有未保存内容，弹出系统拦截确认。
- [ ] 点击“Save”后，LocalStorage 对应键值被清除。
