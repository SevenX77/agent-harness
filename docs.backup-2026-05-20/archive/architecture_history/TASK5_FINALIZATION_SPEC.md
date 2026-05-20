# TASK5_FINALIZATION_SPEC

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务为 Monorepo 重构的收尾阶段。核心目标是解决因物理拆分导致的测试路径失效（Deferred Test Fails），完成 `run_manager.py` 与 Port 抽象的最后缝合，引入 `import-linter` 强制执行 SDK 与 Studio 的架构边界，并恢复被 Stash 的前端 Dark Mode 改动。最后，通过全量锁定的环境验证，确保项目以健康的 1.0.0-RC 状态交付。

## 2. 当前状态扫描

### A. `run_manager.py` 进程边界分析
*   **主进程**: 负责 Run 的生命周期管理、Metadata 持久化、WebSocket 事件转发。需接入 `StorageBackend` 和 `MetadataStore`。
*   **子进程 (`_run_worker_main`)**: 负责实际的 `run_skill` 执行。由于 `multiprocessing` 无法跨进程传递异步 Port 实例或复杂的 Pydantic 配置，子进程内部将保持简单的 `Path` 操作（写入临时 `metrics.json` 等），由主进程在任务结束后通过 Port 进行统一收集和转存。

### B. Deferred Test Fails 原因分析
*   **路径假设失效**: 迁移后，`packages/graph-agent` 的测试代码通过 `Path(__file__).parents[3]` 计算得到的 `ROOT` 指向了 `packages/` 目录，导致无法找到根目录下的 `skills/`。
*   **资源定位**: 部分 Smoke Test 依赖根目录的 `config/llm_roles.yaml`。
*   **分类统计**: 37 个 Fail 中，约 80% 属于“路径找不到”类别，20% 属于“子进程路径硬编码”。

### C. Stash 状态
*   `stash@{0}`: `frontend-dark-mode-WIP-pre-monorepo`。包含对原 `studio-frontend/src` 下 3 个文件的修改。

---

## 3. 收尾子任务 Sub-steps (a1 指南)

### T5.1: `run_manager.py` Wire-in 补完 (0.2d)
1.  **主进程持久化**:
    *   在 `start_run` 中，使用 `metadata_store.save_run_metadata()` 记录初始状态。
    *   在 `_drain_process_queue` 结束处，使用 `storage_backend.write_text()` 转存子进程产出的 `final_state.json`。
2.  **子进程保持现状**: `_run_worker_main` 内部继续使用 `Path` 操作写入本地 `run_dir`。

### T5.2: 修复路径失效测试 (0.3d)
1.  **修正 `ROOT` 宏**:
    *   将 `packages/graph-agent/tests/` 下所有文件的 `ROOT = Path(__file__).resolve().parents[3]` 修正为 `parents[4]` 或相对于包根目录。
    *   **关键文件**: `test_build_graph_nodes.py`, `test_loader_pipeline.py`, `test_md_to_json.py`。
2.  **修正资源 lookup**:
    *   修复 `graph_agent/bootstrap.py` 中对 `config/llm_roles.yaml` 的查找逻辑，支持从项目根目录或环境变量读取。

### T5.3: `import-linter` 架构契约 (0.1d)
1.  **安装**: `uv add import-linter --dev`。
2.  **配置**: 创建根目录 `.importlinter`。
```ini
[importlinter]
root_packages =
    graph_agent
    app

[importlinter:contract:1]
name = SDK 严禁依赖 Studio 业务代码
type = forbidden
source_modules = graph_agent
forbidden_modules = app

[importlinter:contract:2]
name = Studio 严禁绕过 SDK 访问内部模块
type = forbidden
source_modules = app
forbidden_modules =
    graph_agent.core.io_manager
    graph_agent.core.state
    graph_agent.core.phase_node
```
3.  **运行**: `uv run lint-imports`。

### T5.4: 恢复 Frontend Dark Mode (0.1d)
由于目录已移动，无法直接 `stash pop`。
1.  **提取补丁**: `git stash show -p stash@{0} > dark_mode.patch`。
2.  **修正路径**: 将 patch 文件中的 `studio-frontend/src/` 批量替换为 `apps/studio/frontend/src/`。
3.  **应用补丁**: `git apply dark_mode.patch`。
4.  **校验**: 启动 Vite 验证暗色模式是否生效。

### T5.5: 全量验证与交付 (0.3d)
1.  **更新文档**:
    *   更新根目录 `README.md`，反映 `packages/` 和 `apps/` 的新布局。
    *   创建 `CHANGELOG.md`，记录 SDK 收敛及 Monorepo 重构的关键 Breaking Changes。
2.  **最终校验流**:
    *   `uv sync`: 锁定依赖。
    *   `cd packages/graph-agent && uv run pytest`: Fail 应降至 20 以下（主要为第三方 API 依赖）。
    *   `cd apps/studio/backend && uv run pytest`: 28/28 Pass。
    *   `uv run mypy --strict .`: 跨 Workspace 类型检查全绿。

---

## 4. 风险点与缓解

1.  **Stress Process Boundaries**: 子进程写入与主进程通过 Port 读取可能存在时序竞争。
    *   *缓解*: 仅在 `process.join()` 后或接收到 `status: success` 信号后再通过 Port 进行最终转存。
2.  **Import-linter 误报**:
    *   *缓解*: 如有必要的反向依赖（如测试 Mock），使用 `ignore_imports` 标记。
3.  **Patch 应用失败**: 如果 `git apply` 因前端代码已有变动而冲突。
    *   *缓解*: 让 a1 根据 `git stash show -p` 的差异手动恢复 UI 改动。

## 5. 验收 Checklist
- [ ] `packages/graph-agent` 的测试 Fails 数量显著下降。
- [ ] `import-linter` 成功拦截非法导入。
- [ ] 前端暗色模式恢复并正常运行。
- [ ] `README.md` 与项目实际物理结构一致。
- [ ] `uv.lock` 已同步并提交。

## 6. 工时估算
*   **总计**: 约 5.5h (0.7 dev-day)。
