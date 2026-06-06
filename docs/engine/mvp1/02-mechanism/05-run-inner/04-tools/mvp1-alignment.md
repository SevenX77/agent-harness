---
module: 02-mechanism/05-run-inner/04-tools
doc: mvp1-alignment
status: drafted（机制·运行内层;action/tool 不统一已定 2026-06-04(TL2);§2 tool 生命周期 + ToolError 行为已成段、现状/目标 demarcate;ToolError 实现(tool_error.py no-op→error ToolMessage)归 kiro）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行内层）
---

# 04-tools — 机制 B · agent 工具(运行内层)

> **Tier**: 机制层 B · 运行·内层 | **Owns**: builtin 工具 · tool binding(给 create_agent)· builtin read 工具(read_reference/read_example)· ToolError 处理逻辑 | **现状**: ⏳(capability 决定不统一;builtin/binding live;ToolError 待实现) | **Related**: `04-run-outer/01-graph-exec`(action 对照面)· `02-middleware`(ToolError 槽)· `03-assemble`(builtin read tools 绑定)

## 1. 定义
tools = **内层 agent loop 里 LLM 可调用的工具**(`StructuredTool`):builtin 工具 + 把业务/framework 工具 binding 给 `create_agent(tools=...)`。与外层 **action**(`graph-exec` 的 LOGIC,确定性,引擎调)分属**两套注册表**。

## 2. 数据流 / 机制
tool 生命周期(内层 agent loop 内,四步):
1. **注册**:`ToolDef` → `ToolRegistry`(`actions.py:60`)`for_phase` 产出 `StructuredTool`(带 args schema);与外层 `ActionRegistry`(action)**两套独立注册表、不互通、无桥**(TL2 不统一;代码里历史把 action 混叫 "tool" 是死簇,待清)。
2. **binding**:phase 的 tools(frontmatter `tools[]` + builtin)绑给 agent——**目标**直接交 `create_agent(tools=...)`;**现状**是手动 `_bind_tools_if_supported`(`graph_assembler.py:508`,见 `01-agent-loop`)。
3. **调用**:LLM 在 ReAct loop 按 schema 生成 tool 调用 → 执行 → 结果转 `ToolMessage` 回 loop(`01-agent-loop` §3)。
4. **ToolError(目标,现 no-op)**:工具抛异常 → 转 **error ToolMessage**(把异常喂回 LLM、给恢复机会)、**不崩 phase**;逻辑归本域、实现在 `02-middleware` 槽 5(双向)。**现状** `middleware/tool_error.py` 是 no-op(16 行)、异常直接冒泡 → 归 kiro 实现。
- **builtin 工具**(7 个,skill 经 `builtin.<name>` 引用):清单见 `baseline §2`;`read_reference`/`read_example` 在 `03-assemble` prompt 完成前绑定。
> 运行期工具沙箱 = 伪需求(已撤);purity 是编译规则(`compile-rules`),扫描器在 `01-compile`——本域不重复沙箱。

## 3. 接口契约
tool binding → `create_agent(tools=...)`(不再手动 `bind_tools`);builtin read 工具(`read_reference`/`read_example`)在 `03-assemble` prompt 完成前绑定。

## 4. 设计决策基础(决策依据)
决策已定(非"待挖掘"):**action/tool 不统一为 capability**(2026-06-04 拍板)。依据为工程边界判断:
- 外层 LOGIC 的 action = 纯函数 `<name>(read-only dict) -> dict`(引擎调、确定性);内层 tool = `StructuredTool`(LLM 调、带 schema)。二者调用方、确定性、副作用边界本质不同,spec 已固定 `Action ≠ Tool`,统一只会把两套语义糊在一起、无收益。
> ⚠️ 该 cluster 迁移源未捕获用户原话;审计标注见 `01-agent-loop` §4。action 干净契约的完整论证见 `04-run-outer/01-graph-exec` LE1-3(双向)。

## 5. 决策 + 动机(含**待决重点**)
| ID | 决策 | 动机 / 状态 |
|---|---|---|
| TL1 | tool = 内层 LLM 调;action = 外层引擎调(`graph-exec`) | 外/内主轴,两套注册表 |
| TL2 | **action/tool 不统一为 capability**(决定 2026-06-04) | LOGIC 干净 action = 纯函数 `<name>(read-only dict)->dict`(引擎调、确定性)vs tool = StructuredTool(LLM 调)—— 本质不同、spec 已固定边界,统一无收益 |

## 6. 测试关键点
1. builtin 工具经 binding 后在 agent loop 可调、StructuredTool schema 正确。
2. ToolError:工具抛异常 → error ToolMessage(LLM 有机会恢复),不崩 phase。
3. (若统一)capability 在 LOGIC(action)与 AGENT(tool)两路径行为分流正确。

## 7. 涉及 region / platform
engine 全权。

## 8. gaps / 待设计(⏳ 多为 live + 待实现)
1. **action/tool capability = 不统一**(决定,见 TL2)——LOGIC 干净契约后二者本质差异更明确,无统一收益。
2. **builtin + binding = 文档化 live**:StructuredTool binding 给 create_agent(`_structured_tool`,actions.py:76)、builtin read 工具(read_reference/read_example)live。
3. **ToolError 待实现**:`middleware/tool_error.py` 现 no-op → 工具异常转 error ToolMessage(逻辑本域,实现在 `02-middleware` 槽 5)。
4. **断层#3**:`parallel_map` × 6 槽中间件链(与 `02-iterate`/`02-middleware`)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3(§3 易混边界 · 断层#3)· `04-run-outer/01-graph-exec`(action)· `02-middleware`(ToolError 槽,双向)· `03-assemble`(builtin read tools)· `01-compile`(purity,非本域沙箱)
