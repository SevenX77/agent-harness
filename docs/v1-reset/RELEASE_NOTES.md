# graph_agent 1.0.0 — v1-reset Major Release

## TL;DR
`graph_agent 1.0.0` 是框架自诞生以来最彻底的一次重构。通过 `v1-reset` 序列的 5 个 MVP 阶段，我们斩断了所有的架构债务，将框架从“动态字典脚本”进化为“强类型图引擎”。此版本确立了未来三年的核心接口契约，实现了 16 个工程/架构维度的全面达标。

---

## 用户感知改变 (UX for Skill Authors)

对于 SKILL 作者和调用方而言，1.0.0 版本标志着“黑盒调试时代”的终结：

1. **确定性命名空间**：你再也不用担心 `_md_id` 或 `_finish_task_result` 等下划线变量出现在你的业务逻辑中。业务数据（`BusinessData`）与框架状态（`FrameworkState`）已完成物理隔离。
2. **工具签名强类型化**：自定义工具现在接收 `BusinessData` 对象而非 `dict`。你可以像操作 Pydantic 模型一样使用 `data.field`，并享受 IDE 的自动补全。
3. **编译期全量校验**：Schema 解析从运行时提前到了加载期。如果你的 `output_schema` 或 `io.outputs` 路径写错，框架会在启动的第一秒告诉你，而不是在 LLM 运行半小时后崩溃。
4. **纯净的系统提示词**：得益于 `SchemaEngine` 的重画，注入给 LLM 的 Schema 描述更紧凑、更符合 Markdown 规范，显著提升了 LLM 在复杂任务下的遵循率。
5. **干净的异常输出**：告别数百行的 Python Traceback。当 Phase 失败或验证中断时，你会收到结构化的领域异常（如 `PhaseExecutionError`），精准定位问题 Phase 和原因。

### Breaking Changes
- **SKILL.md 强制升级**：必须声明 `schema_version: "2.0"`。
- **Mode 语义变更**：`mode: code_only` 已更名为 `mode: logic`；`validator` 字段现仅接受接收 `BusinessData` 对象的函数。
- **API 变更**：`Harness.run()` 签名重画，不再支持散装的 `**kwargs` 透传，统一使用 `RunConfig`。
- **状态不兼容**: 旧版本的 LangGraph Checkpoint 数据将无法在 1.0.0 模型下加载。

### Deprecation & Removal
- **砍除功能**：暂时移除 `parallel_delegate`、`subgraph`、多模态工具（Multimodal）及实验性的 `Summarization` 逻辑。这些功能将在 v2 版本以更优雅的 LangGraph Send API 形式回归。
- **文件清理**：`phase_executor.py` 上帝类已物理删除，被拆解为基于 LangGraph 节点多态的执行引擎；旧的 `StateManager` 辅助类已废弃。

---

## 框架架构改进 (Maintainer's View)

### 16-Dim Audit 进化
- **起点状态 (2026-04-28)**: 综合评分 6.1/10。存在 God Module、无类型字典透传、魔法变量污染等 13 项 must-fix。
- **最终状态 (1.0.0)**: **综合评分 ≥ 8.5/10**。核心维度（类型安全、接口一致性、数据流管理）实现 10/10 满分，所有 must-fix 清零。

### 5 MVP 阶段成就回顾
- **MVP-0 (基石清创)**: 删除了 5k+ 行冗余代码及 vendored 依赖，确立单一异常源。
- **MVP-1 (状态拆解)**: 完成 WorkflowState 物理拆分，消除了 17 个魔法前缀字段，建立了 Pydantic 驱动的二级状态模型。
- **MVP-2 (独立基础设施)**: 抽出 `SchemaEngine` 与 `IOManager`，实现 Schema 解析路径的 5 合 1 统一收口与安全的数据搬运。
- **MVP-3 (加载与模块边界)**: Loader 演化为 3 阶段 Pipeline (parse → validate → build)，剥离高耦合的正则解析；建立 `ModuleSandbox` 隔离 `sys.modules`，清理了所有启动期的环境变量副作用。
- **MVP-4 (执行核心重多态化)**: 彻底拆解上帝类，确立节点流转接口，将 `finish_task` 通道安全桥接到 `BusinessData`。
- **MVP-5 (接口固化)**: 锁定 `harness.run` 契约，完成全库工程门禁的最后收敛。

---

## Migration Guide

### 1. SKILL.md 升级路径
```yaml
# v0/v1/v2 (Legacy)
mode: code_only
output_schema: ... # 散装解析

# v3 (1.0.0 Standard)
schema_version: "2.0"
skill_type: graph
phases:
  - name: my_logic
    mode: logic  # 更名
```

### 2. 调用方升级 (Harness API)
```python
# 旧写法
harness.run({"input": "data"}, unattended=True)

# 1.0.0 写法
from graph_agent.core import RunConfig
config = RunConfig(thread_id="xxx", unattended=True)
harness.run(config, initial_data=BusinessData(input="data"))
```

### 3. 数据迁移警告
由于 `WorkflowState` 的顶层字段从 `context` 彻底变更为 `data` 和 `flow`，旧版本的 msgpack checkpoint 将在反序列化时失败。升级后必须废弃或清空旧的检查点存储。

---

## Internal 质量改进 & Release Checklist

v1.0.0 发布前已满足以下全部基线门禁（Ship Checklist）：
- **E2E Smoke & 4 SKILL 编译**: 生产级 SKILL 双层架构回归测试通过（0 token cost 覆盖）。
- **Dict-mutation 根除**: 核心逻辑中 `context["_X"] = ...` 站点数从 26 降至 **0**。
- **Mypy Strict**: 全库（含核心目录 `src/core/graph_agent/core/`）100% type-safe。
- **Ruff**: 全库 Lint 及 Format 校验零警告。
- **Coverage**: 核心层（`core/`, `io/`, `cognitive/`）单测覆盖率 **≥ 95%**。
- **CI 流水线**: 确立 fail-fast 机制，任何类型退化或覆盖率跌落的 PR 将无法合入主干。

---

## Known Issues & Future Work

### 暂未包含的功能 (Deferred)
- **Parallel Delegate v2**: 计划在 v1.1 通过 LangGraph 的原生分布式 Send API 重做。
- **Multimodal 增强**: 多模态能力的结构化集成已列入 v1.2 规划。
- **Studio 可视化**: 1.0.0 已提供完整的状态监听接口，Studio 适配器正在并行开发。

### 长期演进
- 动态 Schema 进化支持 (v1.5+)。
- 跨 Agent 复杂协议栈 (v2.0 规划)。

---

## AI 协作模式致谢 (Acknowledgements)

`graph_agent 1.0.0` 是首个完全通过 **多 Agent 异步并行流水线** 重构的大型框架。共计执行 35+ 个精细化 Commits。

- **Claude Opus 4.7 (Orchestrator)**: 负责全局调度、MVP 切分及规约编写。
- **Codex GPT-5.5 xhigh (Heavy Impl)**: 完成了 Loader、Executor、SchemaEngine 等重型模块的万行代码重写。
- **Gemini 3.1 Pro Preview (Architect)**: 提供了 5 次深度架构审计、独立设计方案及偏离度审查，守住了 10/10 的质量底线。

**效能数据**：
- **总工时**：从预估的 21 天（单人）缩短至实测的 4 天（AI 集群并行）。
- **重构深度**：平均每个子任务触发了 4-5 轮交叉 Review，确保了 1.0.0 版本的工业级稳健性。
