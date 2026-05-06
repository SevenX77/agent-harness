# F3 Phase Plan (Long-tail Polish & Performance)

**版本**: 1.0
**日期**: 2026-05-05
**周期**: 1-2 周
**目标**: 在 F1 (核心闭环) 和 F2 (效率提升) 的基础上，针对 PM 的批量测试、大型技能性能以及系统健壮性进行深度打磨，使 Studio 达到 1.0.0 正式版水平。

---

## §1 F3 Phase 任务列表

| ID | 任务名称 | 描述 | 优先级 | 估算 | 关联组件 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **T1** | **批量测试 (Batch Runner)** | 支持为同一技能加载多个 JSON 输入并并行/顺序执行，对比汇总结果。 | P0 | 12h | `Playground`, `History` |
| **T2** | **虚拟滚动 (Virtual Trace)** | 针对 1000+ 事件的超长 Trace，引入虚拟列表技术，消除浏览器卡顿。 | P1 | 8h | `TracePanel` |
| **T3** | **模板库与 Fork** | 支持从内置模板（如数据提取、对话机器人）快速创建技能，或 Fork 现有技能。 | P1 | 8h | `CreatorWizard` |
| **T4** | **草稿恢复与崩溃保护** | 在 `localStorage` 实时保存未保存的 Prompt 编辑内容，防止意外刷新丢数据。 | P2 | 6h | `usePhaseSync`, `App.tsx` |
| **T5** | **导出运行报告** | 支持将 Trace 详情与 Golden Diff 导出为 Markdown 或 PDF 格式供团队评审。 | P2 | 8h | `History`, `DiffView` |
| **T6** | **a11y 与键盘导航** | 完善 Tab 顺序、ARIA 标签，并增加通过方向键切换 Trace 事件的能力。 | P2 | 4h | 全局 |

**总工时估算**: 46 小时 (约 6 dev-days)。

---

## §2 F3 Task 1 详细 Spec: 批量测试 (Batch Runner)

### 2.1 Executive Summary
为了验证 Prompt 的鲁棒性，PM 需要在多个测试用例上验证其效果。目前只能一个个手动运行，效率低下。本任务将实现一个“批量运行器”，允许用户上传或从 `test_inputs/` 目录选择多个 JSON 文件，一次性触发运行，并提供一个概览视图对比各用例的通过情况。

### 2.2 PM 痛点
*   **重复劳动**: 改了一行 Prompt，需要手动点 10 次 Run 来确保 10 个测试用例都没退化。
*   **对比困难**: 无法一眼看出哪些用例过了，哪些失败了，必须手动切历史记录看。
*   **缺乏统计**: 没有“通过率”的概念，难以对技能质量进行整体定性。

### 2.3 前端设计
*   **Batch 面板**: 在 `InputPlayground` 旁增加 `Batch` 切换按钮。
*   **用例列表**: 展示 `workspaces/<id>/test_inputs/` 下的所有文件，支持勾选。
*   **执行视图**: 
    *   进度条显示执行状态。
    *   汇总表：用例名 | 状态 | 耗时 | Token 消耗 | 结果摘要。
*   **对比模式**: 自动与每个用例对应的 Golden 记录（如有）进行静默对比，标出 Fail 项。

### 2.4 实施 Sub-steps

#### T1.1: 后端批量执行接口 (4h)
1.  在 `routers/runs.py` 增加 `POST /api/skills/{id}/batch-run`。
2.  逻辑：接收 `input_ids` 列表，在后台并发启动多个子进程 Run。
3.  返回 `batch_id` 以供前端轮询。

#### T1.2: Batch Runner UI 组件 (4h)
1.  `components/playground/BatchRunner.tsx`: 选择器 UI，列出所有可用测试输入。
2.  `components/history/BatchSummary.tsx`: 汇总表展示。
3.  集成 `BatchPlayground` 到 `HeaderBar` 或 `RightPanel`。

#### T1.3: 执行逻辑与状态轮询 (3h)
1.  实现 `useBatchRun` hook：管理 batch 状态。
2.  由于 WebSocket 仅支持单次 Run，批量运行建议采用长轮询 `GET /api/batch/{id}` 或在单路 WS 中推送带 `sub_run_id` 的事件。

#### T1.4: 验证与验收 (1h)
1.  验证同时跑 5 个用例时 UI 不假死。
2.  验证批量结果能正确写入 `History`。

### 2.5 验收 Checklist
- [ ] 勾选 3 个测试文件并点击“Run Batch”。
- [ ] 页面显示 3 个任务的实时进度。
- [ ] 结束后显示一个汇总表，标注每个用例的 Success/Fail。
- [ ] 点击汇总表中的某一项能跳转到该次运行的详细 Trace。

---

## §3 后续 F3 Task 简短 Brief

### T2: 虚拟滚动 (Virtual Trace)
随着技能复杂度增加，Trace 数量可能过千。本任务将重构 `TracePanel`，引入虚拟化渲染技术（仅渲染可视区域内的 DOM），确保即使在长时间运行后，滚动操作依然丝滑，内存占用保持稳定。

### T3: 模板库与 Fork
建立一个内置的技能仓库（Scaffold），提供标准化的 `Agent` 和 `Graph` 模板。PM 点击“New Skill”时可以从模板开始，而非面对空白页。同时支持“Clone”功能，允许将别人的优质技能一键复制到自己的工作区。

### T4: 草稿恢复与崩溃保护
监听 Monaco 的内容变更，实时将其序列化到 `IndexedDB` 或 `localStorage`。如果浏览器意外关闭或刷新，再次打开同一技能时自动检测到未保存草稿，并询问用户是否恢复，将“事故感”降到最低。

### T5: 导出运行报告
为 `History` 和 `DiffView` 增加“Export”按钮。调用浏览器的打印功能（通过定制 CSS 实现良好的打印布局）生成 PDF，或导出一个包含完整 Trace payload 的自包含 HTML 文件，方便 PM 将研发结果汇报给技术或业务负责人。
