# graph-agent V2.1 GUIDE 文档修复 — Design

## 1. 整体策略
本次采用**一刀切 Patch**策略，在同一个 PR 中将 3 处缺陷（D-1 至 D-3）与 2 处体验优化（UX-1、UX-2）全部修复完毕。不引入新概念，仅在原 `docs/graph_agent_docs/` 目录下做局部增删改，以达到与 V2.1 Spec 的严格一致。

## 2. 缺陷与 UX 修复设计

### D-1: 澄清 `<python_callable>` 与 `<execute>` 标签关系
- **修改文件**: `docs/graph_agent_docs/ARCHITECTURE.md`
- **定位**: §1 角色 C (line 50) 和 角色 D (line 51) 说明 及 §2 编译期 FATAL 矩阵表 (line 84)
- **修复方案**:
  1. (line 50) *改前*: `不允许内联 <system_prompt> / <role> / <python_callable>`
     *改后*: `不允许内联 <system_prompt> / <role> / <python_callable> (schema 2.0 遗留)`
  2. (line 51) *改前*: `不允许 <python_callable> 或确定性 Python 副作用块`
     *改后*: `不允许 <python_callable> (schema 2.0 遗留) 或确定性 Python 副作用块。新版确定性执行请使用 LOGIC.md 的 <execute> 标签`
  3. (line 84) *改前*: `SKILL.md 出现 <python_callable>` | `LLM 节点不许确定性 Python`
     *改后*: `SKILL.md 出现 <python_callable> (schema 2.0 遗留)` | `LLM 节点不许确定性 Python。新版确定性执行请使用 LOGIC.md 的 <execute> 标签`
- **背书**: 结合 requirements R1.3 节点纯度约束，全面覆盖所有涉及该遗留标签的描述，防止混淆。

### D-2: 重写“孤儿 phase”的定义悖论
- **修改文件**: `docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md`
- **定位**: §3.3 拓扑禁区
- **修复方案**:
  - *改前*: `孤儿 phase: 完全跟其他 phase 没有任何无向连通性 (既不依赖任何 phase, 也没被任何 phase 依赖, 且不是起点)`
  - *改后*: `孤儿 phase: 无法从任何起点通过 depends_on 路径到达的非连通节点。`
- **背书**: 根据 V2.1 `depends_on` DSL 规则，非首节点缺属性直接报错，原定义存在逻辑冲突。

### D-3: 补全 Architecture 编译流程前端 Schema 导出反馈边
- **修改文件**: `docs/graph_agent_docs/ARCHITECTURE.md`
- **定位**: §4.1 编译流程图 (Mermaid block)
- **修复方案**:
  1. 在 mermaid 图表最右下角新增独立节点 `Frontend JSON Schema`（或 `IDE Schema Export`）。
  2. 在 AST 层补齐现存架构中遗漏画出的 `SubgraphNodeAST` 节点。
  3. 从 `LogicNodeAST`、`SubgraphNodeAST`、`SkillNodeAST` 分别画一条虚线指向 `Frontend JSON Schema`，体现出站链路。
  4. 在 mermaid 图结束后追加一段说明文本：`这 3 条虚线代表 Q-4 决议: 3 类 AST Pydantic model 通过 .model_json_schema() 导出 JSON Schema 给前端消费 (IDE 自动补全 / canvas schema-driven UI 等)`。
- **背书**: 落实 Q-4 决议：前端 JSON Schema 来源于 AST Pydantic model 的直接导出，而非复用 inputs validator 验证路径。

### UX-1: 增加跨文档阅读指引
- **修改文件**: `docs/graph_agent_docs/ARCHITECTURE.md`
- **定位**: 顶部引言或 §0 之前
- **修复方案**: 插入加粗的阅读向导块。
  - *插入文本*: `**阅读指引**: 理论篇 (本架构总览) → 实践篇一 (SKILL_AUTHORING_GUIDE) → 实践篇二 (TOOL_DEVELOPMENT_GUIDE)`

### UX-2: 补充 SKILL.md 全貌示例
- **修改文件**: `docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md`
- **定位**: §4.3 (或其他 LLM ReAct Phase 章节末尾)
- **修复方案**: 补充一个涵盖 `<role>`、`<system_prompt>` 和 `<exit_contract>` 的综合代码块示例，让读者“所见即所得”。

## 3. 冲突与风险控制
- **无分支冲突**: 本次修改仅限 `docs/graph_agent_docs/*.md`，与开发主干及当前 parent 的 `feat/state-mgmt-optimization-spec` 无物理文件重叠，冲突极低。
- **保护 V2.1 Spec**: 严格禁止触碰 `.kiro/specs/graph-agent-v2.1/` 目录下的任何历史存档。

## 4. 测试策略
- **人工走查**: 修复后通过 IDE 预览模式通读 3 份指南，确保格式与链接渲染正常。
- **Mermaid 验证**: 拷贝 `ARCHITECTURE.md` 的修改后图表在 Mermaid Live Editor 中渲染，看到独立的 `Frontend JSON Schema` 节点及 3 条代表导出的虚线，确保逻辑与语法未被破坏。
