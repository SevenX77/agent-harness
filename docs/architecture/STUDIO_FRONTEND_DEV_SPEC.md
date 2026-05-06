# STUDIO_FRONTEND_DEV_SPEC

**版本**: 1.0
**日期**: 2026-05-05
**作者**: a2 Gemini (资深前端架构师 + Skill Studio 产品设计专家)

---

## 0. Executive Summary

随着 Monorepo 物理拆分和 SDK 契约的稳固，Skill Studio 进入了**体验打磨期**。当前前端（`apps/studio/frontend`）虽已具备基础的编辑、绘图与运行能力，但在 PM 研发全流程上仍存在“输入靠手写、调试靠眼找、对比靠心算”的痛点。

本 Spec 定义了三阶段的前端优化路径：
1.  **F1 (核心闭环)**：修复 Mypy/E2E 遗留问题，实现技能创建向导、输入 Playground 及 Trace 过滤，确保 PM 能独立完成“创建-运行-调试”闭环。
2.  **F2 (效率提升)**：引入 Golden Diff 可视化、表单化 Phase 编辑及快捷键系统。
3.  **F3 (专业深度)**：支持版本回滚、多场景批量测试及主题自定义。

---

## 1. Section A: 前端打磨计划

### 1.1 现状扫描
*   **架构**：React + ReactFlow + Monaco Editor + XTerm.js。
*   **能力**：
    *   ✅ 技能树实时可视化（ReactFlow）。
    *   ✅ Markdown 全量编辑（Monaco）。
    *   ✅ 基础运行与 Trace 时间轴展示。
    *   ✅ 实时文件同步（WebSocket）。
*   **不足**：`App.tsx` 逻辑过重（1300+ 行），UI 组件化程度低，缺乏面向 PM 的非代码编辑入口。

### 1.2 PM 工作流场景与 Gap 分析

| 场景 | 现有 UX | 理想 UX | 核心 Gap |
| :--- | :--- | :--- | :--- |
| **新建技能** | 无入口，需手动在 OS 创建目录 | “New Skill” 按钮 + 类型选择向导 | 缺少创建向导 (Wizard) |
| **编辑 Prompt** | 在 1000 行 Markdown 中寻找 | 侧边栏表单或点击流程节点直接编辑 | 缺少节点到代码的跳转 |
| **测试输入** | 手写/粘贴 JSON 字符串 | 自动根据 `io.inputs` 生成表单表单 | 缺少 Input Playground |
| **调试 Fail** | 滚动长长的 Trace 列表 | 过滤错误事件，高亮异常节点 | 缺少 Trace 搜索与过滤 |
| **质量评估** | 观察日志输出 | 与 Golden Baseline 左右分屏 Diff | 缺少 Diff 可视化 |
| **提交代码** | 切换到外部终端 git push | UI 内置“一键同步/提交” | 缺少 Git 集成 |

### 1.3 改进 Backlog

| 名称 | 描述 | 优先级 | 估算 | 涉及文件 | 依赖 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Skill Creator** | 弹窗向导，设置技能名、类型 (Agent/Graph) 并生成模板 | P0 | 8h | `App.tsx`, 新建组件 | Backend API |
| **Input Playground** | 解析 `SkillManifest` 自动生成输入表单，替代 JSON 粘贴 | P0 | 12h | `App.tsx`, `Playground.tsx` | - |
| **Trace Filter** | 支持按 Phase 名、事件类型（LLM/Tool/Error）进行过滤 | P0 | 6h | `App.tsx` | - |
| **Jump to Line** | 点击 ReactFlow 节点或 Trace 错误，Monaco 自动跳转至对应行 | P0 | 4h | `App.tsx` | - |
| **Golden Diff** | 集成 `compare` API，展示当前 Run 与 Golden 的字段级对比 | P1 | 16h | `DiffView.tsx` | Backend API |
| **Phase Form** | 点击节点弹出侧边栏，表单化修改 Phase 的 prompt/role/tools | P1 | 24h | `PhaseEditor.tsx` | - |
| **Run History** | 侧边栏展示该技能的历史运行记录，支持一键重放 (Replay) | P1 | 8h | `App.tsx` | Backend API |
| **Shortcuts** | `Cmd+S` 保存, `Cmd+Enter` 运行, `Cmd+P` 搜索技能 | P1 | 4h | `hooks/useShortcuts.ts` | - |

### 1.4 Phase 划分与 F1 Task Breakdown

#### Phase F1: 核心研发闭环 (1-2 周)
*   **Task 1: 项目瘦身与组件化** (2d)
    *   将 `TracePanel`, `SkillSidebar`, `Playground` 从 `App.tsx` 提取为独立文件。
*   **Task 2: 创建向导与模板** (1.5d)
    *   实现 `/api/skills` POST 接口对接。
*   **Task 3: 输入 Playground** (2d)
    *   实现 JSON Schema 到表单的动态渲染。
*   **Task 4: Trace 增强** (1.5d)
    *   增加搜索框与状态过滤器。

---

## 2. Section B: Mypy 5 Errors Fix

在根目录运行跨 Workspace 检查时残留的 5 个错误及修复方案：

1.  **`graph_agent/core/serialize.py:61`**: `Unused "type: ignore"`
    *   *修法*：物理删除该行注释。
2.  **`studio/backend/app/services/terminal_manager.py:14`**: `ptyprocess` 缺失类型声明
    *   *修法*：在 `apps/studio/backend/pyproject.toml` 中确认已装，并在 `mypy.ini` 中添加 `[[tool.mypy.overrides]] module = "ptyprocess.*" ignore_missing_imports = True`。
3.  **`graph_agent/core/checkpointer.py:69`**: 找不到 `langgraph.checkpoint.postgres`
    *   *修法*：这是可选依赖，当前仅使用 SQLite。在 `mypy.ini` 中对 `langgraph.*` 设置 `ignore_missing_imports = True`。
4.  **`graph_agent/tools/builtin/parallel_map.py:236`**: 返回值类型不匹配 (WorkflowResult vs dict)
    *   *修法*：修改 `parallel_map.py` 中的类型注解，或在返回前显式调 `.model_dump()`（如果该工具契约要求 dict）。
5.  **`graph_agent/core/harness.py:104`**: 同第 3 项。

---

## 3. Section C: E2E 测试修复

### 3.1 基础设施补全
1.  **依赖注入**：在根目录 `pyproject.toml` 的 `[dependency-groups]` 下添加 `e2e = ["playwright>=1.40"]`。
2.  **环境初始化**：
    ```bash
    uv sync --group e2e
    uv run playwright install chromium
    ```

### 3.2 路径与 Fixture 修正
*   **`apps/studio/tests-e2e/_backend_runner.py`**：
    *   将 `REPO_ROOT / "studio-backend"` 修正为 `REPO_ROOT / "apps/studio/backend"`。
    *   将 `REPO_ROOT / "src/core"` 修正为 `REPO_ROOT / "packages/graph-agent/src"`。
*   **`conftest.py`**：
    *   确认 `STUDIO_TEST_PORT` 动态分配逻辑，防止并行运行冲突。

---

## 4. 整合实施 Plan

1.  **Immediate (0.5d)**：修复 Section B (Mypy) 与 Section C (E2E)，恢复 CI 全绿。
2.  **Iteration F1 (1.5 周)**：
    *   组件化拆分。
    *   实现新建向导。
    *   实现输入表单。
3.  **Validation**：PM 试用 F1 版本，收集反馈调整 F2。

---

## 5. 验收 Checklist

- [ ] `uv run mypy --strict` 跨 workspace 报告 0 errors。
- [ ] `uv run pytest apps/studio/tests-e2e` 3 个核心流全绿。
- [ ] 前端侧边栏出现“+ New Skill”按钮，且能成功创建文件。
- [ ] 运行技能前可以预览并填写基于 Pydantic 定义的输入表单。
- [ ] Trace 列表中可以一键隐藏 `llm_call` 细节，仅看 `phase` 和 `error`。

---

## 6. 风险与 Open Questions

1.  **Monaco 与 ReactFlow 同步**：双向绑定可能存在性能损耗。
    *   *缓解*：使用 `debounce` 延迟同步。
2.  **Git 集成边界**：Studio 是否应该具备 `commit/push` 能力？
    *   *决策*：初期仅通过 FileWatcher 监听外部 Git 行为，UI 暂不提供 Git 操作，避免冲突。
