# graph-agent V2.1 GUIDE 文档修复 — Tasks

> **Status**: Tasks - Kiro Step 3  
> **Date**: 2026-05-16  
> **主笔**: a1 Codex  
> **Spec link**: `requirements.md` / `design.md`  
> **Scope**: 只修 `docs/graph_agent_docs/` 下 GUIDE 文档；不触碰 `.kiro/specs/graph-agent-v2.1/` 锁定主 spec。

## Critical Path 概览

5 个 doc fix/UX patch + 1 个验收 commit = 6 tasks，总估时约 **1h 55min**。T1-T5 可局部并行，但建议按文档文件顺序执行，T6 blocked by T1-T5。

---

## T1 (D-1): 澄清 `<python_callable>` 与 `<execute>` 标签关系

### 目标 (Goal)

在 `ARCHITECTURE.md` 所有高风险出现点标明 `<python_callable>` 是 schema 2.0 遗留，并指向新版 `LOGIC.md` 的 `<execute>`。

### 修改文件 + 行号

- `docs/graph_agent_docs/ARCHITECTURE.md`
- design.md 定位: §1 角色 C/D 附近 line 50/51；§2 编译期 FATAL 矩阵 line 84

### DoD (Definition of Done)

- `grep -n "<python_callable> (schema 2.0 遗留)" docs/graph_agent_docs/ARCHITECTURE.md` 命中 **3** 行。
- `grep -n "LOGIC.md.*<execute>" docs/graph_agent_docs/ARCHITECTURE.md` 至少命中 **2** 行。
- `grep -n "SKILL.md 出现 <python_callable> (schema 2.0 遗留)" docs/graph_agent_docs/ARCHITECTURE.md` 命中 **1** 行。

### 预估工时

15min

### 依赖

blocked_by: 无

### 风险

矩阵列宽或 markdown table 管道符容易被破坏，修改后需检查表格仍可渲染。

---

## T2 (D-2): 重写“孤儿 phase”定义

### 目标 (Goal)

消除 `SKILL_AUTHORING_GUIDE.md` §3.3 中“孤儿 phase 且不是起点”的逻辑悖论。

### 修改文件 + 行号

- `docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md`
- design.md 定位: §3.3 拓扑禁区，约 line 118

### DoD (Definition of Done)

- `grep -n "孤儿 phase: 无法从任何起点通过 depends_on 路径到达的非连通节点" docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` 命中 **1** 行。
- `grep -n "完全跟其他 phase 没有任何无向连通性" docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` 命中 **0** 行。
- `grep -n "且不是起点" docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` 命中 **0** 行。

### 预估工时

10min

### 依赖

blocked_by: 无

### 风险

不要顺手改 `depends_on` DSL 规则，只替换定义文本。

---

## T3 (D-3): 补全 Architecture 编译流程前端 Schema 出站链路

### 目标 (Goal)

在 `ARCHITECTURE.md` §4.1 ASCII 编译流程图补齐 AST → Frontend JSON Schema 的出站导出链路。

### 修改文件 + 行号

- `docs/graph_agent_docs/ARCHITECTURE.md`
- design.md 定位: §4.1 编译流程 ASCII art 及图后说明

### 修改要求

- 在现有 ASCII art 的 AST 层增加或确认 `SubgraphNodeAST` 节点。
- 在现有 ASCII art 中增加 `[Frontend JSON Schema]` 节点或等价 box。
- 从 `LogicNodeAST`、`SubgraphNodeAST`、`SkillNodeAST` 各画 1 条 ASCII 虚线指向 `[Frontend JSON Schema]`。
- 在图后补充说明: `这 3 条虚线代表 Q-4 决议: 3 类 AST Pydantic model 通过 .model_json_schema() 导出 JSON Schema 给前端消费 (IDE 自动补全 / canvas schema-driven UI 等)`。

### DoD (Definition of Done)

- `grep -n "Frontend JSON Schema" docs/graph_agent_docs/ARCHITECTURE.md` 至少命中 **1** 行。
- `grep -n "SubgraphNodeAST" docs/graph_agent_docs/ARCHITECTURE.md` 至少命中 **2** 行。
- `grep -n "model_json_schema()" docs/graph_agent_docs/ARCHITECTURE.md` 至少命中 **1** 行。
- `grep -nE "Frontend JSON Schema" docs/graph_agent_docs/ARCHITECTURE.md | wc -l` 输出 **2** 或更多。
- 人工检查: ASCII art 在 monospace 中能看到 `LogicNodeAST`、`SubgraphNodeAST`、`SkillNodeAST` 3 条虚线指向 `Frontend JSON Schema` box。

### 预估工时

20min

### 依赖

blocked_by: 无

### 风险

ASCII art 对齐和 box 字符较脆弱；修改后用 `sed` 检查 §4.1 附近片段，确认 box 完整且不得把这条链路画成 inputs validator 回流路径。

---

## T4 (UX-1): 在 Architecture 顶部增加跨文档阅读指引

### 目标 (Goal)

让首次阅读者打开 `ARCHITECTURE.md` 即看到三份 GUIDE 的推荐阅读顺序。

### 修改文件 + 行号

- `docs/graph_agent_docs/ARCHITECTURE.md`
- design.md 定位: 顶部引言或 §0 之前

### DoD (Definition of Done)

- `grep -n "阅读指引" docs/graph_agent_docs/ARCHITECTURE.md` 命中 **1** 行。
- `grep -n "理论篇.*实践篇一.*实践篇二" docs/graph_agent_docs/ARCHITECTURE.md` 命中 **1** 行。
- `sed -n '1,20p' docs/graph_agent_docs/ARCHITECTURE.md` 能看到该阅读指引。

### 预估工时

10min

### 依赖

blocked_by: 无

### 风险

不要把导航写成新的规范章节；它只是阅读 UX，不应改变架构语义。

---

## T5 (UX-2): 补充 LLM ReAct Phase 完整 SKILL.md 示例

### 目标 (Goal)

在 `SKILL_AUTHORING_GUIDE.md` 补一个可复制的 LLM ReAct phase 综合示例，覆盖 `<role>`、`<system_prompt>`、`<exit_contract>`。

### 修改文件 + 行号

- `docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md`
- design.md 定位: §4.3 或其他 LLM ReAct Phase 章节末尾

### DoD (Definition of Done)

- `grep -n "<role>" docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` 至少命中 **1** 行。
- `grep -n "<system_prompt>" docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` 至少命中 **1** 行。
- `grep -n "<exit_contract>" docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` 至少命中 **1** 行。
- 三个标签位于同一个 fenced codeblock 内；人工用 `sed` 检查该 codeblock 上下文不超过 **80** 行。
- 示例标题或引导句含 `SKILL.md` 与 `LLM ReAct` 字样。

### 预估工时

30min

### 依赖

blocked_by: 无

### 风险

示例必须保持 V2.1 合法，不要引入 schema 2.0 根 `SKILL.md` 旧拓扑写法。

---

## T6: 三重验收 + 单一提交

### 目标 (Goal)

对 T1-T5 做 grep、ASCII art、read-through 三重验收，并产出一个符合 SOP 的提交。

### 修改文件 + 行号

- 只验收并提交 T1-T5 修改过的文档文件。
- 预期文件: `docs/graph_agent_docs/ARCHITECTURE.md`、`docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md`

### DoD (Definition of Done)

- 执行 T1-T5 所有 grep DoD，结果全部符合期望。
- 人工检查 `ARCHITECTURE.md` §4.1 ASCII art，看到 3 条 AST → Frontend JSON Schema 虚线。
- 通读 `ARCHITECTURE.md`、`SKILL_AUTHORING_GUIDE.md`、`TOOL_DEVELOPMENT_GUIDE.md`，确认没有与 V2.1 主 spec 和三份 GUIDE 互相矛盾。
- `git diff -- .kiro/specs/graph-agent-v2.1` 无输出。
- 提交信息使用 `feat(graph-agent-docs): ...` 或 `refactor(graph-agent-docs): ...`，正文含 `Spec: .kiro/specs/graph-agent-v2.1-doc-fixes/`。

### 预估工时

30min

### 依赖

blocked_by: T1, T2, T3, T4, T5

### 风险

验收 commit 不应混入未关联代码或 V2.1 主 spec 改动；如果工作树已有无关改动，需拆分提交。

## 总工时估算

- T1 15min
- T2 10min
- T3 20min
- T4 10min
- T5 30min
- T6 30min
- **合计: 115min，约 1h 55min**
