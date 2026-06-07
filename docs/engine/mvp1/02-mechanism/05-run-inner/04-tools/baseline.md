---
module: 02-mechanism/05-run-inner/04-tools
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；7 个 builtin 工具 + 手动 bind_tools；ToolError no-op；action/tool 两套）
---

# 04-tools — Baseline(当下代码实现逻辑)

> **Scope**: 内层 agent loop 里 LLM 可调用工具的现状:`ToolRegistry`(StructuredTool)、builtin 工具集、tool binding、ToolError 处理。
> **现状一句话**:tool = `ToolRegistry`(`actions.py:60`)产出的 `StructuredTool`(`_structured_tool` `:76`),与外层 LOGIC 的 `ActionRegistry`(`:25`)**两套独立注册表**(见 `graph-exec`)。引擎自带 **7 个 builtin 工具**(skill 经 `builtin.<name>` 引用)。live 把工具**手动 `bind_tools`**(`graph_assembler.py:508`,见 `01-agent-loop`),`ToolError` 中间件仍是 **no-op**(16 行)。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. tool 注册表(actions.py)
`ToolRegistry`(`:60`):`root_tools` / `for_phase(phase_id)`(`:71`)→ `_structured_tool(tool)`(`:69/76`)把 `ToolDef`(`:49`)转成 LangChain `StructuredTool`。与 `ActionRegistry`(`:25`,LOGIC action)**两套、不互通**(mvp1 决定**不统一** capability,见 mvp1-alignment TL2)。
> **StructuredTool 第一次出现需定义**:LangChain 带 args schema 的工具对象,LLM 按 schema 生成调用参数。

### 2. builtin 工具集(skill 可引用 `builtin.<name>`)
`tools/builtin/__init__.py` 导出 **7 个**:`ask_clarification_tool`、`query_working_memory`、`read_artifact`、`parallel_map`、`make_read_file_tool`(read_file)、`read_declared_example`、`read_declared_reference`。loader 特判 `builtin.` 前缀的引用到这里。
> 注:`parallel_map` 既是 builtin 工具(内层 LLM 可调的"子 skill 并行展开")又与外层声明式 `iterate`/batch 重叠——两条 fan-out 路的取舍归 mvp1-alignment(断层#3)。

### 3. tool binding + ToolError
- binding:live `_build_skill_node` 合 `all_tools`(`graph_assembler.py:479`)后 `_bind_tools_if_supported` **手动 bind**(`:508`)。mvp1 改为直接交 `create_agent(tools=...)`。
- ToolError:`middleware/tool_error.py`(16 行)**no-op**——工具抛异常当前不转 error ToolMessage(逻辑归本域,实现在 `02-middleware` 槽 5)。

## API
- `ToolRegistry.for_phase(phase_id) -> list[StructuredTool]`(`actions.py:71`)。
- builtin:`ask_clarification_tool` / `parallel_map` / `make_read_file_tool` / `query_working_memory` / `read_artifact` / `read_declared_example` / `read_declared_reference`(`tools/builtin/__init__.py`)。

## Data Model / State
tool 产 `StructuredTool`(带 args schema);执行结果转 `ToolMessage` 回 loop(见 `01-agent-loop` §3)。

## 当前边界(这个模块现在不是什么)
- **不和 action 互通**:两套注册表(spec 已固定 Action≠Tool,不统一)。
- **ToolError 还没逻辑**:no-op(工具异常当前会直接冒泡,见 `01-agent-loop` 手写 loop)。
- **不做运行期沙箱**:purity 是编译规则(`compile-rules` / `01-compile`),本域不重复沙箱(运行期 jail = 伪需求,已撤)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| binding | 手动 `bind_tools`(`graph_assembler.py:508`) | 直接交 `create_agent(tools=...)` |
| ToolError | no-op(`tool_error.py`,16 行) | 工具异常转 error ToolMessage、不崩 phase |
| action/tool | 两套注册表 | **不统一**(决定,TL2) |

> **验"是否按 mvp1 改了"**:① builtin 工具经 binding 后在 loop 可调、StructuredTool schema 正确;② 工具抛异常 → error ToolMessage(LLM 有机会恢复)、不崩 phase;③ 手动 bind_tools 是否被 create_agent 取代。

## 读代码主路径提示
注册表 `actions.py:49/60`(tool)对照 `:18/25`(action)→ builtin `tools/builtin/__init__.py` → binding `graph_assembler.py:479/508` → ToolError 空壳 `middleware/tool_error.py`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `04-run-outer/01-graph-exec`(action 对照,双向)· `02-middleware`(ToolError 槽,双向)· `03-assemble`(builtin read tools 绑定)· `01-compile`(purity,非本域沙箱)
