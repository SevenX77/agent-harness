# F3_T5_EXPORT_REPORT_SPEC (导出 Run 报告)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在为 Skill Studio 引入标准化研发成果导出能力。目前 PM 评估和汇报研发进度时，只能通过截图或口头描述，缺乏结构化、可追溯的文档支持。我们将实现基于 **Markdown** 和 **HTML** 的报告导出功能，覆盖单次运行（Single Run）、对比运行（Compare Run）及批量运行（Batch Run）三种场景。导出的报告将包含完整的输入、输出摘要、关键指标（Metrics）及 Trace 概览，方便贴入团队 Wiki 或 Slack 进行同步评审。

## 2. PM 痛点

### 2.1 现状
*   **汇报困难**: 跑完一个复杂的 Skill 后，如果输出效果极佳，PM 很难通过一个简单的链接或文件将其展示给其他团队成员，往往只能截长图。
*   **存档缺失**: 历史运行数据虽然在本地，但缺乏一键生成“研发周报”或“测试报告”的入口。
*   **对比断层**: 修改 Prompt 前后的质量对比（Golden Diff）仅存在于 Studio UI 中，无法导出为文本进行离线评审。

### 2.2 理想 UX
*   **一键导出**: 在历史记录行或对比视图顶部，点击 [Export] 按钮即可下载报告。
*   **多格式支持**:
    *   **Markdown**: 纯文本、结构化，适合开发者粘贴至 Notion / GitHub / Slack。
    *   **HTML (Self-contained)**: 带样式的单文件，可在浏览器中完美复现 Studio 的 Trace 视觉效果，适合非技术决策者查阅。
*   **场景覆盖**: 支持导出单次运行详情，以及当前 Run 与基准（Golden）的差异报告。

## 3. 设计决策

### 3.1 导出范围与格式
*   **单次运行报告**: Header (Skill ID, Time) + Input JSON + Output JSON + Metrics (Tokens, Cost) + Trace Timeline Summary。
*   **对比运行报告**: 左右分栏格式展示差异 + 相似度得分 (Similarity Score)。
*   **批量运行汇总**: 成功率统计表格 + 各用例结果摘要。
*   **PDF 说明**: 由于前端生成 PDF 需引入庞大的 jsPDF 库，V1 优先支持 HTML 导出，用户可通过浏览器“打印为 PDF”自行转换，保持项目轻量。

### 3.2 技术实现
*   **无库依赖**: 采用字符串模板拼接（Template Strings）生成内容。
*   **下载机制**: 使用浏览器 `Blob` 与 `URL.createObjectURL` 触发本地下载。

---

## 4. 前端组件设计

### 4.1 目录结构
```
apps/studio/frontend/src/
├── components/export/
│   ├── ExportButton.tsx          # 带下拉菜单的导出按钮
│   └── ExportFormatPicker.tsx    # 格式/范围选择模态框
└── utils/
    └── reportTemplates.ts        # 核心渲染逻辑（Markdown/HTML 生成）
```

### 4.2 报告内容结构 (Markdown 示例)
```markdown
# Skill Run Report: [Skill ID]
- **Run ID**: [run_id]
- **Status**: ✅ Success
- **Time**: 2026-05-05 14:00
- **Total Tokens**: 1,200 ($0.03)

## Input
```json
{ ... }
```

## Output
```json
{ ... }
```

## Trace Summary
- [phase-1] started
- [llm_call] generated 500 tokens
...
```

---

## 5. 实施 Sub-steps (a1 指南)

### T5.1: 报告模板引擎实现 (3h)
1.  实现 `reportTemplates.ts`:
    *   `renderMarkdown(data: ReportData): string`: 处理各种运行类型的文本拼接。
    *   `renderHTML(data: ReportData): string`: 注入基础 Tailwind-lite CSS 确保导出的 HTML 也有美观样式。
2.  处理特殊字符转义，防止 JSON 中的符号破坏 Markdown 语法。

### T5.2: 导出组件与交互 (2h)
1.  实现 `ExportButton.tsx`: 提供“Export as Markdown”和“Export as HTML”选项。
2.  实现下载辅助函数：支持自定义文件名 `<skill_id>_<timestamp>.[ext]`。

### T5.3: UI 全局集成 (2h)
1.  **History Tab**: 在每一行记录的末尾增加 [Export] 小图标。
2.  **Diff Tab**: 在对比视图顶部增加 [Export Comparison] 按钮。
3.  **Batch Result**: 在批量运行结束后，提供“Download Batch Report”按钮。

### T5.4: 验证与验收 (1h)
1.  验证导出内容在主流 Markdown 编辑器（如 Obsidian, VS Code）中的渲染效果。
2.  验证导出的 HTML 在无网络环境下（内联 CSS）的视觉表现。
3.  测试超大 Trace (500+ 事件) 导出时的性能。

---

## 6. 风险点与缓解
*   **编码问题**: 某些特殊语言（如日语/俄语）可能在导出时出现乱码。
    *   *缓解*: 统一使用 UTF-8 编码并添加 BOM 头（如果是 Windows 兼容性需要）。
*   **Trace 数据量过大**: 导致浏览器内存溢出。
    *   *缓解*: V1 对导出的 Trace 条目数进行截断（例如仅保留前 100 条及所有错误事件）。

## 7. 验收 Checklist
- [ ] HistoryTab/DiffView 中均出现导出入口。
- [ ] 点击“Export as Markdown”能下载 `.md` 文件且格式正确。
- [ ] 导出的文件包含该次运行的所有 Token 成本信息。
- [ ] 对比报告中包含 Similarity Score。
- [ ] 暗色模式下导出的 HTML 样式依然清晰可读。
