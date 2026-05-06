# PR #37 合并决策辩论 (SDK 架构冲突分析)

**版本**: 1.0 (Round 1)
**日期**: 2026-05-05
**评审者**: a2 Gemini (资深 SDK 架构师 & 迁移专家)

---

## 1. Executive Summary

**Verdict: 强烈推荐方案 C (双路径并存 / Compatibility Shim)**。

PR #37 追求的“深模块”架构与 User 在 main 分支上实施的“非破坏性包装”产生了显著的兼容性冲突。User 的 `video-analysis` 项目高度依赖 25+ 个公共 API 及已删除的多模态工具。直接合并 PR #37 将破坏 User 的现有交付链，而退回旧架构则会牺牲 Studio 的工程质量。**方案 C 通过引入“Legacy Shim”包，既保留了面向未来的 12 API 精简 SDK，又为老旧项目提供了平滑的过渡路径。**

---

## 2. 4 选项 Trade-off 对照表

| 选项 | 核心策略 | 优点 (Pros) | 缺点 (Cons) | 风险等级 |
| :--- | :--- | :--- | :--- | :--- |
| **A** | **PR #37 现状合入** | 架构最纯净；彻底践行 Ousterhout 准则；维护成本最低。 | **严重破坏兼容性**；`video-analysis` 无法一键升级；User 信任度下降。 | 🔴 高 (逻辑破坏) |
| **B** | **全面回退至 25 API** | 100% 兼容现有项目；合并阻力最小。 | SDK 极其臃肿；暴露过多内部细节；违反“深模块”原则。 | 🟡 中 (技术债) |
| **C** | **双路径 (Shim)** | **兼顾架构与兼容**；新项目用精简版，旧项目用 Shim 版；明确弃用路径。 | 初始配置稍复杂；需要维护两个包入口。 | 🟢 低 (受控过渡) |
| **D** | **重命名为 Engine** | 匹配 User 命名偏好。 | 仅解决表面名称，未解决 API 深度的架构冲突。 | 🟡 中 (语义模糊) |

---

## 3. Q2 推荐理由 (First Principles)

**推荐方案 C (双路径并存)**。理由如下：

1.  **契约分离原则**: Studio PM 的研发需求（简单、快速、稳定）与 `video-analysis` 的生产需求（多模态、复杂编排、历史继承）已产生物理偏移。不应强行用一套 API 掩盖两类完全不同的交互深度。
2.  **受控弃用 (Managed Deprecation)**: 专业 SDK 升级应遵循 `物理移动 -> Shim 转发 -> DeprecationWarning -> 物理删除` 的四部曲。PR #37 跳过了中间两步，而方案 C 补齐了这些环节。
3.  **User 意图对齐**: User 在迁移文档中明确提到“symlink 将被 real tree 替换”。方案 C 正好顺应了这一预期，同时接住了 User 没预料到的 API 变更冲击。

---

## 4. Q3 实施 Plan (方案 C)

1.  **物理落盘**: 保持 PR #37 的物理结构：源码位于 `packages/graph-agent`。
2.  **SDK 2.0 发布**: `packages/graph-agent` 作为主线 SDK，仅暴露 12 个核心 API。
3.  **改造 Shim**: 将 User 的 `packages/graph-agent-engine` 改造为 **Thin Shim**:
    *   删除 symlink。
    *   在 `__init__.py` 中从 `graph_agent` 导入 12 个新 API，并从子模块（如 `graph_agent.core.loader`）导入 13 个 demoted API。
    *   对 13 个 demoted 符号增加 `DeprecationWarning`。
4.  **恢复多模态**: 将被删除的 `understand_video.py` 等 4 个文件放回 `packages/graph-agent/src/graph_agent/legacy/`，并由 Shim 重新导出。
5.  **交付**: `video-analysis` 仍使用 `graph-agent-engine` 包，其导入路径无需大规模重构。

---

## 5. 给 User 的一句话总结

**“我们保留您喜欢的包名和所有 API 兼容性（通过 graph-agent-engine Shim），同时把核心源码搬进更现代的 Monorepo 结构，为 Studio 腾出干净的舞台。”**

---

## 6. Open Question

*   **多模态工具的归属**: 长期来看，`understand_video` 等工具是否应该剥离为独立的 `graph-agent-tools-multimodal` 包？目前建议先放在 `legacy/` 目录随引擎分发，以最低成本解决 `video-analysis` 的阻断问题。
