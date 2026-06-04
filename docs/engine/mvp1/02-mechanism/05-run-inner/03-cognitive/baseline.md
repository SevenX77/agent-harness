---
module: 02-mechanism/05-run-inner/03-cognitive
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；live 接简化版 md2json,rich 三态未接;goto=END 绕过退出闸）
---

# 03-cognitive — Baseline(当下代码实现逻辑)

> **Scope**: finish_task 显式提交 + 校验路由 + 输出解析/patch 的现状:`cognitive_flow.py`(截获+校验)、`cognitive/md2json.py`(简化版,live)、`tools/md_to_json.py`(rich 三态,未接 live)、`cognitive/md_patch.py`。
> **现状一句话**:CognitiveFlow `wrap_tool_call`(`cognitive_flow.py:348`)在工具循环里截 finish_task;**live 接的是简化版 `parse_finish_markdown`**(`graph_assembler.py:644` 导入,`cognitive_flow.py:550/604` 用),**rich 版 `md_to_json`(三态分流)存在但没接 live**。成功 finish_task 现走 `goto=END`(`:511`)——**直接结束 phase、绕过退出闸**(mvp1 要改 marker 交 `05-exit-control`)。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. finish_task 截获(cognitive_flow.py)
`CognitiveFlowMiddleware.wrap_tool_call`(`:348`)在工具循环截 finish_task / ask_clarification;`handle_finish_task_tool_result`(`:198`)处理结果。invalid → `goto="model"` 回模型(`:455/698/750`);成功 → `goto=END`(`:511/765`)**直接结束**。
> **finish_task 第一次出现需定义**:AGENT phase 的"交卷"工具,LLM 把最终 Markdown 交给它,引擎解析+校验后落 `data`。

### 2. 校验:简化版(live)vs rich 三态(存在未接)
- **live**:简化版 `parse_finish_markdown`(`cognitive/md2json.py:26`,185 行)→ `Md2JsonResult` + `validation_errors`(`build_finish_task_tool` `finish_task.py:30/151`)。
- **rich(存在未接)**:`tools/md_to_json.py` 的 `md_to_json`(`:515`)三态分流——`report.all_valid`(`:556`)直接过 / `report.semantic_only`(`:560`)抛 `SemanticValidationError`(`:171`)打回主 agent 重生成 / 结构错走 surgical md-patch(只抽失败 `##` block)。`parse_md`(`:284`)+ `diagnose`(`:454`)。
- 业务规则错:`_run_business_validator`(`cognitive_flow.py:637`)Pydantic 后跑 phase validator,失败返 `[Business]` 前缀。

### 3. 输出 patch
`cognitive/md_patch.py`(`LLMMdPatchClient`)只修 structural/mechanical;semantic 不交 patcher 猜值。

## API
- `wrap_tool_call(...)`(`cognitive_flow.py:348`)/ `handle_finish_task_tool_result(...)`(`:198`)。
- `md_to_json(md_text, schema, *, skill_resolver)`(`tools/md_to_json.py:515`,rich)vs `parse_finish_markdown(...)`(`cognitive/md2json.py:26`,简化,live)。

## Data Model / State
finish_task 入参 markdown → 解析成 validated BusinessData(落 `data`);校验错经 flow 反馈。md2json 输出形状(`Md2JsonResult` / list[BaseModel])。

## 当前边界(这个模块现在不是什么)
- **live 不走 rich 三态**:接的是简化版 `parse_finish_markdown`(rich `md_to_json` 存在未接)。
- **成功 finish_task 现 `goto=END`**(`:511`):绕过退出闸(mvp1 改 marker)。
- **两套 md2json 并存**:`cognitive/md2json`(简化,待退役)vs `tools/md_to_json`(rich,接回目标)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 校验 | 简化 `parse_finish_markdown`(`md2json.py:26`) | rich `md_to_json` 三态分流(`md_to_json.py:515`) |
| 退出 | `goto=END`(`:511`)直接结束 | 写 marker、交 `05-exit-control` after_agent 闸 |
| 重复 | `cognitive/md2json` + `tools/md_to_json` 并存 | 退役简化版、收口 rich |

> **验"是否按 mvp1 改了"**:① 结构错→REFORMAT / 语义错→打回主 agent(三态分流是否生效);② 成功 finish_task 是否经 after_agent 闸、不再 `goto=END`;③ 简化版是否退役。

## 读代码主路径提示
`wrap_tool_call`(`cognitive_flow.py:348`)→ `handle_finish_task_tool_result`(`:198`)→ live 解析 `_parse_finish_markdown`(`:604`)/ rich `md_to_json`(`tools/md_to_json.py:515`)→ 业务校验 `_run_business_validator`(`:637`)。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `02-middleware`(CognitiveFlow 槽 2,双向)· `05-exit-control`(退出闸,双向)· `01-contract/02-skill-syntax`(模板语法)· `03-assemble`(模板渲染)
