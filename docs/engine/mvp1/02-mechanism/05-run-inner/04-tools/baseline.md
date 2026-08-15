---
module: 02-mechanism/05-run-inner/04-tools
doc: baseline
status: drafted（WS-E2 回写 2026-06-09:7 个 builtin 工具 + create_agent tools;ToolError 普通异常转 error ToolMessage;action/tool 两套;2026-08-15 认知框架工具回归 live 挂载面）
---

# 04-tools — Baseline(当下代码实现逻辑)

> **Scope**: 内层 agent loop 里 LLM 可调用工具的现状:`ToolRegistry`(StructuredTool)、builtin 工具集、tool binding、ToolError 处理。
> **现状一句话**:tool = `ToolRegistry`(`actions.py:60`)产出的 `StructuredTool`(`_structured_tool` `:76`),与外层 LOGIC 的 `ActionRegistry`(`:25`)**两套独立注册表**(见 `graph-exec`)。引擎自带 **7 个 builtin 工具**(skill 经 `builtin.<name>` 引用)。live AGENT phase 现在把工具列表直接交给 `create_agent(tools=all_tools)`(`graph_assembler.py:1183`),并通过 `ToolErrorHandlingMiddleware` 把普通工具异常转为 `ToolMessage(status="error")` 喂回模型。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. tool 注册表(actions.py)
`ToolRegistry`(`:60`):`root_tools` / `for_phase(phase_id)`(`:71`)→ `_structured_tool(tool)`(`:69/76`)把 `ToolDef`(`:49`)转成 LangChain `StructuredTool`。与 `ActionRegistry`(`:25`,LOGIC action)**两套、不互通**(mvp1 决定**不统一** capability,见 mvp1-alignment TL2)。
> **StructuredTool 第一次出现需定义**:LangChain 带 args schema 的工具对象,LLM 按 schema 生成调用参数。

### 2. builtin 工具集(skill 可引用 `builtin.<name>`)
`tools/builtin/__init__.py` 导出 **9 个**:`ask_clarification_tool`、`update_working_memory_tool`、`log_ambiguity_tool`、`query_working_memory_tool`、`read_artifact_tool`(后四个在 `tools/builtin/cognitive_tools.py`,空壳、行为归 CognitiveFlowMiddleware,见 `03-cognitive`)、`parallel_map`、`make_read_file_tool`(read_file)、`read_declared_example`、`read_declared_reference`。loader 特判 `builtin.` 前缀的引用到这里。
> 注:`parallel_map` 既是 builtin 工具(内层 LLM 可调的"子 skill 并行展开")又与外层声明式 `iterate`/batch 重叠——两条 fan-out 路的取舍归 mvp1-alignment(断层#3)。

### 2b. 认知框架工具挂载面(2026-08-15 迁移决议 PR B,代码现实)
live AGENT phase 的 `_build_skill_node` 经 `_cognitive_framework_tools(phase_ast)`(`core/graph_assembler.py`)把认知工具并进 `all_tools`:

- **无条件挂载**:`ask_clarification`(P1-5「逃生舱必须无条件存在」)、`update_working_memory`、`log_ambiguity`——与 finish_task / read_reference / read_example 同为框架工具。
- **opt-in 挂载**:SKILL.md frontmatter 声明 `context_access`(`AgentNodeAST.context_access`,值域 `Literal["working_memory","artifact"]`,loader→AST→装配层传递)——含 `working_memory` 才挂 `query_working_memory`,含 `artifact` 才挂 `read_artifact`;不声明即不挂(Round 8 默认强隔离)。
- **保留名**:loader 白名单 `framework_tool_names`(`core/loader.py`)现为 8 个名字——finish_task / read_reference / read_example / log_ambiguity / ask_clarification / update_working_memory / query_working_memory / read_artifact;SKILL 在 `tools:` 里声明任何一个都报 `[F-v3-agent-tool-reserved]`。
- 测试锚:`tests/core/test_cognitive_tools_mounting.py`、`tests/core/test_reserved_tool_declaration.py`。

### 3. tool binding + ToolError
- binding:live `_build_skill_node` 合 `all_tools` 后直接传给 `create_agent(tools=all_tools)`(`graph_assembler.py:1183`)。
- ToolError:`middleware/tool_error.py` 已实现 sync/async `wrap_tool_call`。handler 正常返回时结果原样透传;普通 `Exception` 被转成 `ToolMessage(status="error")`,其 content 包含 phase、tool name、tool_call_id、异常类型和异常摘要;`langgraph.errors.GraphBubbleUp` 及其子类控制流原样 re-raise,不误包成普通工具错误。

## API
- `ToolRegistry.for_phase(phase_id) -> list[StructuredTool]`(`actions.py:71`)。
- builtin:`ask_clarification_tool` / `parallel_map` / `make_read_file_tool` / `query_working_memory` / `read_artifact` / `read_declared_example` / `read_declared_reference`(`tools/builtin/__init__.py`)。

## Data Model / State
tool 产 `StructuredTool`(带 args schema);执行结果转 `ToolMessage` 回 loop(见 `01-agent-loop` §3)。

## 当前边界(这个模块现在不是什么)
- **不和 action 互通**:两套注册表(spec 已固定 Action≠Tool,不统一)。
- **ToolError 不做错误码细分**:本 WS 只把普通工具异常转 error ToolMessage,不新增 Error V2 registry code,不改变 builtin 工具 schema。
- **ToolError 不处理控制流**:`GraphBubbleUp`/interrupt/HITL 类控制流继续向外冒泡,不被当作普通工具异常。
- **不做运行期沙箱**:purity 是编译规则(`compile-rules` / `01-compile`),本域不重复沙箱(运行期 jail = 伪需求,已撤)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| binding | 直接交 `create_agent(tools=all_tools)`(`graph_assembler.py:1183`) | 保持 create_agent tools binding |
| ToolError | 普通异常转 `ToolMessage(status="error")`;GraphBubbleUp 控制流 re-raise | 后续可补更细诊断/真实运行覆盖,但不改错误码 registry |
| action/tool | 两套注册表 | **不统一**(决定,TL2) |

> **验"是否按 mvp1 改了"**:① builtin 工具经 `create_agent(tools=...)` binding 后在 loop 可调、StructuredTool schema 正确;② 工具抛异常 → error ToolMessage(LLM 有机会恢复)、不崩 phase;③ action/tool 两套注册表边界不被糊在一起。

## 读代码主路径提示
注册表 `actions.py:49/60`(tool)对照 `:18/25`(action)→ builtin `tools/builtin/__init__.py` → binding `graph_assembler.py:1183` → ToolError `middleware/tool_error.py`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `04-run-outer/01-graph-exec`(action 对照,双向)· `02-middleware`(ToolError 槽,双向)· `03-assemble`(builtin read tools 绑定)· `01-compile`(purity,非本域沙箱)
