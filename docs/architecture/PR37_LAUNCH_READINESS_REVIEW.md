# PR #37 Launch Readiness Review (Skill Studio)

**版本**: 1.0
**日期**: 2026-05-05
**评审者**: a2 Gemini (资深 SaaS Launch 专家)

---

## 1. Executive Summary

**Verdict: CONDITIONAL PASS (Ready for internal trial after M0 Fixes)**

PR #37 是一个史诗级的变更，成功完成了从 Monorepo 物理架构到 F1-F3 完整研发端 UX 的构建。代码结构清晰，SDK 边界稳固，且引入了大量提升 PM 生产力的核心工具（Batch Runner, Golden Diff, Phase Editor）。尽管 80 个 commits 带来了较高的回归风险，但基于目前的测试覆盖和 UX 完整度，**建议在修复 3 项 P0 风险后，启动为期 1 周的内部 Dogfooding。**

**整体质量评分: 8.8 / 10**

---

## 2. Q1 整体质量评分

| 维度 | 分数 | 评价 |
| :--- | :--- | :--- |
| **代码质量** | 9.0 | 成功解耦了 App.tsx，组件化程度极高；SDK 导出严格遵循“深模块”准则。 |
| **架构设计** | 9.5 | 六边形架构（Ports & Adapters）落地扎实，真正实现了 Local-First 且 Cloud-Ready。 |
| **测试覆盖** | 8.0 | `graph-agent` 拥有 1000+ 测试保障；但 E2E 测试仅覆盖了 3 个核心流，覆盖面偏窄。 |
| **UX 完整度** | 8.5 | 研发闭环已成型，快捷键、草稿恢复等“长尾打磨”项超出了 MVP 预期。 |

**加权平均分: 8.8**

---

## 3. Q2 Launch Risks (Pre-launch)

| # | Risk | 严重度 | 现象 | 复现路径 | 建议修复 | 估算 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **SDK 回归** | P0 | 37 个 deferred fails 虽大多是路径问题，但可能掩盖真实的逻辑 Break。 | 运行 `uv run pytest packages/graph-agent/tests` | 将 Fails 降至 10 以内（仅保留第三方 API 依赖）。 | 4h |
| 2 | **并发子进程竞争** | P1 | `RunManager` 主进程写入与子进程产出在极高频 Batch Run 下可能存在写冲突。 | 启动 20+ 并发 Batch Run。 | 在 `StorageBackend` 增加简单的文件锁或重试机制。 | 3h |
| 3 | **Monaco 冲突** | P1 | `usePhaseSync` 的双向绑定在长文本编辑时可能产生“光标跳动”。 | 编辑 >500 行的 Prompt 字段。 | 增加 `isChangingFromDrawer` 锁，屏蔽反向更新。 | 2h |
| 4 | **E2E 路径硬编码** | P0 | `_backend_runner.py` 仍引用旧 `src/core`，CI 环境可能跑的是旧代码。 | 在全新 CI 容器运行 E2E。 | 彻底清理所有残留的 `src/core` 字符串引用。 | 1h |

---

## 4. Q3 必修 Backlog (M0 Launch 前)

1.  **[P0] 修复 E2E 基础设施**: 修正 `_backend_runner.py` 的物理路径，确保 CI 跑在 `packages/graph-agent` 源码上。
2.  **[P0] 强制收敛 Mypy**: 修复残留的 5 个 `mypy --strict` 错误，特别是 `parallel_map.py` 的类型不匹配，防止 SDK 运行时崩溃。
3.  **[P1] Batch 状态持久化**: 目前 Batch 状态仅存在于内存，刷新页面会丢失 Batch 进度。建议写入 `studio.db`。

---

## 5. Q4 Launch Path 推荐

**推荐路径：Phased Release (内部灰度)**

1.  **T+0 (Immediate)**: 修复 Q3 中的 2 个 P0 项。
2.  **T+1 (Split PR)**: 考虑到 80 commits 风险，建议将 PR #37 拆分为：
    *   **PR 37a**: Monorepo Base + SDK Contract (物理结构变更)。
    *   **PR 37b**: Studio Backend Refactor (Ports/Adapters)。
    *   **PR 37c**: Studio Frontend Full Polish (F1-F3 UI)。
3.  **T+3 (Dogfooding)**: 分发给 3 名核心 PM 进行为期 3 天的深度使用。
4.  **T+7 (Merge to Main)**: 收集反馈并修复后正式 Merge。

---

## 6. Q5 Post-launch Backlog (F5+)

*   **Tauri Native Integration**: 将目前的 Webview 封装为原生桌面应用，支持物理读写本地 `~/.config/graph-agent`。
*   **Prompt A/B Testing**: 支持在 History 中直接发起“变体运行”，对比同一 Input 在不同 Prompt 版本下的差异。
*   **AI Copilot**: 在 Phase Editor 侧边栏增加“AI 修改建议”，根据 Trace 错误自动推荐优化后的 Prompt。
*   **Multi-User MetaStore**: 实现真实的 PostgreSQL Port，支持多 PM 协作与 Skill 共享。

---

## 7. 测试覆盖 Gap 实测

*   **Skipped Tests**: 仅 3 处。
    *   `test_security.py`: Symlink 受限。
    *   `test_execution_control.py`: 状态机边界。
    *   `test_mvp1_smoke.py`: 环境依赖。
*   **TODO 现状**:
    *   `apps/studio/`: 约 12 处（主要在 Batch 执行逻辑和 a11y 细节）。
    *   `graph_agent/`: 5 处（主要是 V2 发送 API 的占位）。

---

## 8. 总结与风险点

**主要风险**: 物理路径变更后，外部 CI/CD 脚本、Dockerfile 及其它隐形依赖可能未同步更新。
**结论**: 结构非常优秀，架构演进符合“深模块”与“整洁架构”原则，修复 P0 后即可发布。
