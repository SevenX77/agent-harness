# F2_T3_RUN_HISTORY_SPEC (Run History & 一键 Replay)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在为 PM 提供实验追踪与快速复现的能力。目前跑过的技能记录（Run）仅存在于本地磁盘，前端缺乏统一的可视化列表。我们将引入 **History Tab**，支持查看该技能的所有历史运行记录，展示状态、耗时及 Token 消耗。核心功能包括 **一键 Replay**（使用历史输入重新发起运行）及 **对比历史记录**（复用 F2-T1 的 Diff 引擎进行横向评估）。

## 2. PM 痛点

### 2.1 现状
*   **记录不可见**: 跑完一个技能并关闭 Studio 后，之前的运行记录难以找回，必须深入 `workspaces/` 目录查看 JSON 文件。
*   **复现困难**: 如果想用“昨天调通的那个输入”再跑一遍，PM 需要手动打开历史 JSON，复制 `input_data` 并粘贴到现在的 Playground 中。
*   **缺乏统计**: 无法直观看到最近 10 次运行中哪次最便宜、哪次最快，或者哪次开始出现了回归报错。

### 2.2 理想 UX
*   **历史长廊**: 在右侧面板新增“History”标签页，按时间倒序排列所有 Run。
*   **快照预览**: 点击列表项可快速查看当时的输入参数、输出结果摘要及详细 Metrics。
*   **一键复跑**: 点击列表项旁的“Replay”图标，立即以相同的输入配置发起一次新运行。
*   **差异审计**: 支持选中任意历史记录与当前输出进行可视化 Diff。

## 3. 后端 API 契约

### 3.1 改造 `models/runs.py`
在 `RunMetadata` 中增加可选的输入摘要，方便列表展示：
```python
class RunMetadata(BaseModel):
    # ... 现有字段
    input_summary: str | None = None  # e.g. "chapter=001, count=5"
```

### 3.2 完善 `routers/runs.py`
1.  **`list_runs` 增强**: 确保返回列表按 `started_at` 降序排列。
2.  **`GET /api/skills/{skill_id}/runs/{run_id}`**: 确保 `RunDetail` 包含完整的 `input_data`（用于 Replay）。
3.  **`DELETE /api/skills/{skill_id}/runs/{run_id}`**: 实现单个记录的物理删除（清理文件夹）。

---

## 4. 前端组件设计

### 4.1 目录结构
```
apps/studio/frontend/src/
├── components/history/
│   ├── HistoryPanel.tsx       # 主入口，展示 Table
│   ├── RunListRow.tsx         # 单行渲染
│   └── RunInspector.tsx       # 详情预览抽屉（Drawer）
└── hooks/
    └── useRunHistory.ts       # 封装 SWR 列表抓取与删除逻辑
```

### 4.2 触发机制
在 `RightPanel.tsx` 的 Tabs 中增加 `history` 项：
```tsx
['history', HistoryIcon, 'History']
```

### 4.3 Replay 逻辑
1.  用户点击 Replay 按钮。
2.  前端通过 `GET /api/skills/.../runs/{run_id}` 获取原始 `input_data`。
3.  调用 `App.tsx` 共享的 `handleRun` 方法，并注入该数据。
4.  自动切换至 `Trace` Tab 观察新运行。

---

## 5. 实施 Sub-steps (a1 指南)

### T3.1: 后端接口完善 (2h)
1.  修改 `app/services/run_manager.py`: 实现 `list_runs` 倒序逻辑。
2.  在 `routers/runs.py` 中补全 `DELETE` 端点实现。
3.  更新 `RunMetadata` 模型增加 `input_summary`（解析 `input_data.json` 获取前两个 Key 作为摘要）。

### T3.2: 历史列表组件 (3h)
1.  实现 `HistoryPanel.tsx`: 使用响应式表格，列包含：Status (Icon), Time (Relative), Input Summary, Cost, Duration。
2.  实现 `useRunHistory` hook: 集成分页逻辑（初版仅前端分页或 Limit 50）。
3.  集成 Lucide 图标（`History`, `RefreshCw` 用于 Replay）。

### T3.3: 详情预览与 Replay (2h)
1.  实现 `RunInspector.tsx`: 点击列表行弹出，分栏展示 Input JSON 和 Output JSON。
2.  编写 Replay 联动逻辑：点击后将数据同步至 `pasteJson` 状态并触发 `onRun`。

### T3.4: 验证与集成 (1h)
1.  验证不同状态（Success/Failed/Running）在列表中的表现。
2.  验证删除历史记录后，磁盘目录被正确清理。
3.  适配暗色模式。

---

## 6. 风险点与缓解
*   **磁盘 I/O 压力**: 列表过长时扫描 `runs/` 目录变慢。
    *   *缓解*: 后端增加 `LRU` 缓存 `list_runs` 结果，仅在文件变动时刷新。
*   **Replay 兼容性**: 历史输入可能包含当前 `SKILL.md` 已删除的字段。
    *   *缓解*: Replay 前先将数据载入 Playground 允许用户二次确认/修改。

## 7. 验收 Checklist
- [ ] RightPanel 出现“History”标签页。
- [ ] 列表按时间最新排在最前。
- [ ] 点击 Replay 按钮能成功发起一次新的运行。
- [ ] 列表支持一键删除旧的运行记录。
- [ ] 在历史详情中可以看到当时运行消耗的 Token 总数。
