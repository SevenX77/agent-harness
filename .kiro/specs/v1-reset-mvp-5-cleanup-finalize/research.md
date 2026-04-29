# MVP-5 Research — Cleanup & Finalize (The Road to 1.0.0)

## 1. 背景与动机 (Why)

MVP-1 到 MVP-4 序列完成了框架的**“核心换发电机”**工程：状态彻底物理拆分（WorkflowState）、架构了独立的数据校验与搬运引擎（SchemaEngine / IOManager）、重建了基于节点多态的执行流（PhaseNode + 4 Middlewares）。

然而，当前版本（含 MVP-4 完工后）仍然带着浓重的“历史包袱”：
- `ruff check` 仍在报错，有大量残留的未使用导入和代码异味。
- `mypy --strict` 只覆盖了重构的新模块，旧有庞大体系（如 models / providers / harness）仍处于类型裸奔状态。
- 测试覆盖率（71%）尚未达到工业级的 95% 门禁。
- 散落的旧文件（如 `io/manager.py`）和过期测试（`test_strict_v2.py`）成了认知负债。

**MVP-5 是 v1-reset 序列的最后冲刺**。如果不做 MVP-5，重构带来的类型安全红利将被边缘模块的脆弱性对冲，调用方（PM 和开发者）也无法获得一个符合 `1.0.0` 工业级标准的交付物。MVP-5 的核心目标是：**还清最后的技术债，锁死工程门禁，正式发布 1.0.0**。

---

## 2. 范围拆解 (What)

MVP-5 被严格限定在以下 6 个收尾子领域。

### 2.1 全库 ruff 拍平
- **现状**: `ruff check src/core/graph_agent/` 仍报 60+ errors（主要类型: F401 / F841 / B904 / I001 / UP037 / SIM* 等）。
- **目标**: 0 errors。
- **Hazards**: 自动修复（`--fix`）极易引发语义误伤（尤其是 `SIM` 简化逻辑和 `UP` 语法升级）。在处理 `harness.py` 等入口文件的 `F401`（unused imports）时，可能会破坏依赖于惰性加载（lazy import）或隐式暴露的 API。
- **子任务粒度建议**: 按 Rule 类别逐个拆分 Commit（例：先消灭所有 F 系列，再处理 B 系列），高危 Rule 必须人工（a2/a1）审核。

### 2.2 全库 mypy --strict
- **现状**: 仅 16 个新增的核心基建模块通过了 `mypy --strict`。外围的 `cognitive/`（如果有残留）、`harness.py`、适配器层等仍有大量 Any 和隐式类型。
- **目标**: 全库 `mypy --strict` zero issues。
- **Hazards**: 这是 MVP-5 最不可控的工作包。由于强依赖于 LangChain / LangGraph，可能会撞上底层 Stub 缺失或外部 API 签名模糊的问题；强行标注类型可能会引发连环爆炸，需要大量使用 `TypeGuard`、显式 `cast` 甚至重构部分入参。
- **子任务粒度建议**: 从依赖树的“叶子”模块向“根”模块（如 `harness.py`）反向推进。

### 2.3 Coverage 提升至 95%
- **现状**: 覆盖率约为 71%（排除废弃测试后）。
- **目标**: 整体覆盖率 ≥ 95%。
- **Hazards**: 低覆盖区集中在“难测区域”（如 `callback_bridge.py` 17%, `skill_tool_factory.py` 0%, Provider 适配层）。这些区域强依赖外部状态或大模型副作用，强行补单测容易写出毫无价值的“Mock 测试”（即测自己写的 Mock 而非实际逻辑）。
- **策略**: 补充关键路径的集成测试；对纯副作用模块进行合理的解耦或提供 Dummy Provider Fixtures。
- **子任务粒度建议**: 按文件列清单，从低到高逐个攻破。

### 2.4 旧 io/manager.py 处置
- **现状**: 旧版的 `src/core/graph_agent/io/manager.py` 仍然存在，但实际上其职责在 MVP-2/3 已被 `core/io_manager.py` 完全替代。
- **目标**: 彻底砍除。
- **Hazards**: 删除前必须进行全库深度 Grep 审计，如果有残留的隐藏 Caller 未迁移，直接删除将导致线上 Crash。
- **子任务粒度建议**: 1 个“Audit + 物理删除”的原子 Commit。

### 2.5 test_strict_v2.py 处置
- **现状**: `tests/graph_agent/core/validators/test_strict_v2.py` 含有 14 个因 Pydantic 模型收紧（`extra="forbid"`）而长期失败的 Stale 测试，目前仅靠 CI 配置中的 `--ignore` 续命。
- **目标**: 彻底删除。
- **Hazards**: 这些测试曾是某种早期 Strict 模式设计的映射；需要确认这些老旧契约是否已经被 ProtocolValidationMiddleware 完全覆盖。如果是，则可放心删除。
- **子任务粒度建议**: 1 个原子 Commit。

### 2.6 1.0.0 RELEASE_NOTES 升级
- **现状**: 当前为 "Phase 1 中间发布" 状态，包含了大量的 Known Limitations。
- **目标**: 升级为正式的 `graph_agent 1.0.0 — final release`，展示真实的工程门禁达标数据。
- **Hazards**: 宣发越界（“吹牛”复发）。必须确保文档上写明的“0 warnings”、“95% coverage”与 CI 系统的真实拦截脚本严格咬合。
- **子任务粒度建议**: 1 个文档草拟 Commit + a2/a1 双重“诚实度 Audit”。

---

## 3. 工程门禁 (Acceptance Criteria)

在宣发 1.0.0 之前，主干必须强制满足以下不变量（CI Hard Fail）：
- [ ] `ruff check src/core/graph_agent/` 报 **0 errors**。
- [ ] `mypy --strict src/core/graph_agent/` 报 **zero issues**。
- [ ] `pytest` 全库执行通过（包含取消对 `test_strict_v2.py` 的 ignore 屏蔽后）。
- [ ] 全库 Coverage **≥ 95%**。
- [ ] 4 大核心 SKILL（text-segmentation 等）Compile 正常且 E2E Smoke 未出现性能/行为退步。
- [ ] `context["_X"]` 模式的全库彻底灭绝（0 Hits）。
- [ ] 旧 `io/manager.py` 已从文件系统中消失。
- [ ] a2 出具 1.0.0 Release Notes 的“诚实度 Audit” PASS 报告。

---

## 4. 估时与子任务规模

*   **Ruff 拍平**: 4-6h（按 Rule 分类拆解 Commit，人工复核避免语义被毁）。
*   **Mypy Strict**: 8-12h（深水区，Legacy 代码的隐式 Any 是个庞大的债坑）。
*   **Coverage 提升**: 6-8h（依赖 Fixture 的构造质量）。
*   **废土清理 (io/manager + strict_v2)**: 2h。
*   **Release Notes 升级**: 1-2h。
*   **预计总工时**: **21-30h wall-clock**。
*   **预计子任务总数**: 12-16 个。

---

## 5. 跟 MVP-4 的依赖关系

MVP-5 是建立在 MVP-4 之上的收尾战。虽然部分工作可以并行，但存在以下硬性阻塞点（Blockers）：
1.  **上下文彻底洁净**: 只有等 MVP-4 彻底重画了 `phase_executor` 并将 `cognitive/middlewares.py` 物理抹除后，MVP-5 才能去验证 `context["_X"]` 的 0 残留。
2.  **准确的 Ruff 统计**: MVP-4 会砍掉大量带有 Unused Imports 的旧模块（如 `phase_executor.py`）。MVP-5 必须在 MVP-4 **Merge 后** 再执行 Ruff 拍平，否则会浪费算力去修马上就要被删除的代码。
3.  **单测靶点的稳定**: MVP-4 对 Executor 的多态拆分会重构部分控制流。MVP-5 必须等这些 Node 稳定后，再投入精力将其 Coverage 刷到 95%。

---

## 6. 风险点评估 (按严重性)

1.  **[High] Mypy 修复的“深水炸弹”**: Legacy 代码中隐藏了大量非标字典传递。开启 Strict 模式可能会触发类型检查器的链式报错，导致工时从预估的 12h 膨胀至 20h+。
2.  **[Medium] 覆盖率的伪要求**: 为了凑 95% 指标，AI（或人类）可能会写出“只测 Mock”的无效测试。必须要求对核心集成节点进行真实的断言，而非追求字面行数。
3.  **[Medium] 诚实度反弹**: 撰写 1.0.0 Release Notes 时，模型可能会再度使用夸大其词的模板语言。必须通过 a2 架构师进行最终的词汇 Audit。
4.  **[Low] 自动格式化误杀**: Ruff `--fix` 在清理 Unused Import 时，若误删了动态加载必需的包，会在运行时才引发隐蔽 Crash。
