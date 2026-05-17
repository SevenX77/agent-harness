# Domain A · Engine (`packages/graph-agent/`)

> Engine = V2.1 SDK 内核, 负责把 `SKILL.md` / `GRAPH.md` / `LOGIC.md` 解析、编译、执行成可跑的 LangGraph 工作流。
>
> Studio 工作台是 Engine 的 GUI 客户端 — 所有"能不能解析"、"能不能跑"的底层判断都在 Engine 这一层。

← 回 [docs/](../README.md) | 当前基线: [STUDIO-BASELINE-2026-05-17.md](../STUDIO-BASELINE-2026-05-17.md)

---

## Living 文档清单

| 文档 | 描述 | Status |
|---|---|---|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 引擎整体架构图 + Loader/Compiler/Executor 数据流 | 🔧 V2.1-STALE (待 a2 audit 改写) |
| [CONFIG_REFERENCE.md](./CONFIG_REFERENCE.md) | 配置项参考 (llm_roles.yaml + env var) | 📝 GAP-CAPABILITY (待补漏字段) |
| [COMPILER_RULES.md](./COMPILER_RULES.md) | strict compile rules v2 — 编译期校验规则 | ✅ Living |
| [TOOL_DEVELOPMENT_GUIDE.md](./TOOL_DEVELOPMENT_GUIDE.md) | 写自定义 tool 的指南 | 🔧 V2.1-STALE (待 a2 audit 改写) |

**已 archive 5 份 (V1 时代写的, V2.1 cutover 后核心概念 `GraphAgentHarness` / `script/validators.py` 单文件结构等已不存在)**: IMPLEMENTATION.md / USER_GUIDE.md / INTEGRATION_GUIDE.md / COGNITIVE_LOOP_GUIDE.md / FRAMEWORK_UNDERSTANDING.md → 已移到 [../archive/v1-era/](../archive/v1-era/) 历史保留。V2.1 替代版等 a2 audit 阶段产出后回填到 Living 表格。

---

## 公开 API surface (从 `packages/graph-agent/src/graph_agent/__init__.py` 实测)

13 个稳定 export, 跨 module 边界用这些, 不进 internal:

```python
# Execution
run_skill, WorkflowResult

# Static analysis
compile_skill, CompileResult, SkillManifest, serialize_skill

# Observability
Callback, LoggingCallback, MetricsCallback, TracingCallback

# Exceptions
GraphAgentError, SkillLoadError, SkillCompilationError
```

Internal helpers (`Phase`, `WorkflowState`, `IOManager`, `ContextResolver`, `ModelResolver`, `GraphAgentHarness`, `parse_skill_file`, `load_workflow_from_md`, etc.) 在 `graph_agent.core.*` / `graph_agent.io.*` / `graph_agent.models.*` 下, **不在 ABI 内**, 下游 (Studio backend / 测试) 不应直接依赖。

---

## 当前已知技术债

- V1 → V2.1 migration test `test_v3_run_one_chapter_honors_invariants` 本地 fail (CI skip)
- `packages/graph-agent-engine/` 空死 legacy package, 待 archive
