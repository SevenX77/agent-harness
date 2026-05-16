# graph-agent V2.1 GUIDE 文档修复 — Requirements

**Spec**: graph-agent-v2.1-doc-fixes
**Status**: Requirements (Kiro Step 2)
**Date**: 2026-05-16
**Author**: a2 (Gemini, 委托 PM Claude)

## R0. 项目背景
V2.1 架构升级核心及 3 份开发者指南已随 `PR #45` (commit `a53e72c` / `7e9456d`) 合入 `main`。本 Spec 仅聚焦于修复 T0.6 交付的指南文档中存在的 3 处内容缺陷与 2 处体验优化 (UX enhancement)。不重启 V2.1 架构开发，仅做文档层面的 Bugfix。

## R1-R5 功能需求 (Doc Fixes & UX)

**R1 (D-1): 澄清 `<python_callable>` 与 `<execute>` 标签关系**
- **现状**: `ARCHITECTURE.md` 的 FATAL 矩阵及 Subgraph / LLM Phase 描述中将 `<python_callable>` 列为非法标签，但未说明它是 schema 2.0 遗留；同时未与新版 `LOGIC.md` 的 `<execute>` 标签形成认知对应。
- **修复目标**: 明确 `<python_callable>` 为被废弃的遗留产物，并告知用户新版确定性执行应使用 `LOGIC.md` 中的 `<execute>`。
- **验收**: 矩阵及相关 Phase 描述中包含对 `<python_callable>` 遗留身份的加注说明。

**R2 (D-2): 重写“孤儿 phase”的定义悖论**
- **现状**: `SKILL_AUTHORING_GUIDE.md` §3.3 将孤儿定义为“完全跟其他 phase 没有任何无向连通性……**且不是起点**”。
- **修复目标**: 消除与起点的逻辑悖论（因为缺 depends_on 属性的非首节点会直接报另一个错）。
- **验收**: 文本变更为“无法从任何起点通过 depends_on 路径到达的非连通节点”。

**R3 (D-3): 补全 Architecture 编译流程前端 Schema 导出反馈边**
- **现状**: `ARCHITECTURE.md` §4.1 的 Mermaid 流程图中，遗漏了从三类 AST Pydantic model 导出反哺的前端契约链路，容易被误解为回流 JSONSchema validator。
- **修复目标**: 新增前端 schema 消费节点，补充 3 条虚线边，体现 Q-4 决议中 AST 自动 export JSON Schema 的闭环出站链路。
- **验收**: Mermaid 图内包含单独的 `Frontend JSON Schema` 节点并有 3 条源自 AST 的虚线。

**R4 (UX-1): 增加跨文档阅读指引**
- **现状**: 读者打开任意指南后缺乏全局阅读顺序指导。
- **修复目标**: 在 `ARCHITECTURE.md` 顶部提供一条清晰的进阶路线。
- **验收**: 文件顶部包含 `理论篇 (架构总览) → 实践篇一 (Skill 编写) → 实践篇二 (Tool/Action 开发)` 字样的导航建议。

**R5 (UX-2): 补充 SKILL.md 全貌示例**
- **现状**: `SKILL_AUTHORING_GUIDE.md` 缺少对最核心的 LLM ReAct Phase 的全节点组装代码块示例。
- **修复目标**: 补充包含 `<role>`、`<system_prompt>` 与 `<exit_contract>` 的综合示例块，降低零基础上手门槛。
- **验收**: `SKILL_AUTHORING_GUIDE.md` 中存在包含上述三个标签的完整 markdown/xml codeblock。

## R6-R7 非功能需求 (NFR)

- **R6 (一致性)**: 修复后，3 份 GUIDE 之间，以及它们与 V2.1 主 Spec (`.kiro/specs/graph-agent-v2.1/`) 必须 100% 对齐，不允许制造新的矛盾。
- **R7 (可读性)**: 零基础新作者依照修复后的指南，能够无歧义地从 0 写出一个合法的 V2.1 GRAPH skill。

## Q-N 已决议题

- **Q-1**: Action 返回值表述 — 辩论后达成共识，原缺陷撤回，认定“返回值类型不限”与“推荐 None”在 Python 语义下兼容，不构成实质缺陷。
- **Q-2**: 修复边界锁定 — 本 Spec 不开新工作流，不动 `.kiro/specs/graph-agent-v2.1/` 锁定的 source of truth，一刀切 Patch。
- **Q-3 (Round 3 新增)**: 原 D-1 (TOOL_DEV §5.3 幽灵引用) 经第三轮 filesystem 实证撤回。§5.3 在 `TOOL_DEVELOPMENT_GUIDE.md:310` 真实存在，引用合法。原审计两轮均漏掉 grep `### 5.` 子小节，这是事实核验失败，不是新的缺陷。
