# Research: Contract Docs Baseline Freeze

## 1. Landscape & State (当前现状分析)

### 1.1 文件标准规范 (skill-spec/*)
现状：位于 `docs/engine/mvp0/skill-spec/` 目录，已形成非常成熟且体系化的 14 份标准文档（覆盖物理布局、解析、路由、错误码等各环节）：
- 00-FORMAT-GROUND-TRUTH.md
- 01-physical-layout.md
- 02-graph-md-spec.md
- 03-logic-md-spec.md
- 04-subgraph-md-spec.md
- 05-agent-md-spec.md
- 06-cognitive-template-spec.md
- 07-mention-syntax-spec.md
- 08-resource-mechanisms-spec.md
- 09-builtin-modules-spec.md
- 10-skill-resolver-protocol-spec.md
- 11-error-code-spec.md
- 12-compile-runtime-flow-spec.md
- README.md
**结论**：规范本身内容足够支撑冻结要求，唯一缺失的是明确宣示其“已封版、不可修改”状态的强制性标识。

### 1.2 公开 API 现状 (Host API Surface)
现状：之前并无统一的 API 文档。
实证数据（经 AST 解析确认）：公开 API 表面积由 `packages/graph-agent/src/graph_agent/__init__.py` 的 `__all__` 变量定义，确切暴露了 18 个核心符号：
- 执行与输出: `run_skill`, `WorkflowResult`
- 静态分析与加载: `compile_skill`, `CompileResult`, `assemble_graph`, `CompiledSkill`, `CompiledStateGraph`, `SkillManifest`, `serialize_skill`
- 解析器与状态: `LocalWorkspaceResolver`, `BlackboardState`
- 监控回调: `Callback`, `LoggingCallback`, `MetricsCallback`, `TracingCallback`
- 异常定义: `GraphAgentError`, `SkillLoadError`, `SkillCompilationError`
**结论**：API 边界已收敛并稳定，具备文档化并写入防漂移测试的条件。

### 1.3 功能清单现状
现状：目前引擎并无一个“所有核心功能/能力”的集中对照清单。
风险：在复杂的重构（如 `MVP0-rebuild`）中，很容易因为重写模块而丢失边角特性。
**结论**：需从头提炼并输出一份严谨的矩阵清单。

### 1.4 文档消费者模式
除了研发工程师（人）之外，这类契约文档的关键消费者还包含 Studio Copilot (LLM Agent)。
**结论**：要求文档必须使用标准化的 Markdown 结构，避免含糊描述，且针对“不可修改”的提示需要用 LLM 最敏感的 `<!-- DO NOT EDIT -->` 等系统指令形式呈现。