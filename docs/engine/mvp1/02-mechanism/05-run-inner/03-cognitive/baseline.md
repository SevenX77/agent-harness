---
module: 02-mechanism/05-run-inner/03-cognitive
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；live 接简化版 md2json,rich 三态未接;goto=END 绕过退出闸;2026-08-15 拦截名单扩至全部认知工具）
---

# 03-cognitive — Baseline(当下代码实现逻辑)

> **Scope**: finish_task 显式提交 + 校验路由 + 输出解析/patch 的现状:`cognitive_flow.py`(截获+校验)、`cognitive/md2json.py`(简化版,live)、`tools/md_to_json.py`(rich 三态,未接 live)、`cognitive/md_patch.py`。
> **现状一句话**:CognitiveFlow `wrap_tool_call`(`cognitive_flow.py:348`)在工具循环里截 finish_task;**live 接的是简化版 `parse_finish_markdown`**(`graph_assembler.py:644` 导入,`cognitive_flow.py:550/604` 用),**rich 版 `md_to_json`(三态分流)存在但没接 live**。成功 finish_task 现走 `goto=END`(`:511`)——**直接结束 phase、绕过退出闸**(mvp1 要改 marker 交 `05-exit-control`)。

## 2026-08-15 拦截名单扩展(legacy 认知功能迁移 PR B,代码现实)

依据 `docs/design/2026-08-15-legacy-cognitive-features-migration-decision.md` §3.1–§3.4,CognitiveFlowMiddleware 的拦截名单从 finish_task / ask_clarification 两个名字扩展到**全部六个认知工具**(类常量 `_INTERCEPTED_TOOLS`,`middleware/cognitive_flow.py`):

- **finish_task / ask_clarification**:原有路径不变(下文各节仍准确)。
- **update_working_memory**(无条件挂载):拦截后把 plan 文本写入 `state["flow"].working_memory` 的 `"plan"` 键(与 iterate 的 `iterate_executions` 键共存,经 `Command(update=...)` 回写、`goto="model"`),**每次接受更新即发 typed `WorkingMemoryUpdateEvent`**(不再像死侧只在 compaction checkpoint 发)。
- **log_ambiguity**(无条件挂载):拦截后 append 到 `state["flow"].ambiguity_reports`(record 含 timestamp/phase/type/question/decision/reason),发 `AmbiguityLoggedEvent`(保留 `@reference:` / `@protocol:` 正则抽取填 related_refs / related_protocols),给模型回 `{"status":"recorded",...}` JSON、`goto="model"` 不中断。
- **query_working_memory / read_artifact**(opt-in 挂载,见 `04-tools` baseline):拦截后只读 request.state、返回普通 ToolMessage。query_working_memory 读 `flow.working_memory["plan"]`,空则 `"(empty)"`;read_artifact 读 `state["data"]` 业务命名空间,保留死侧防护语义(拒空名、拒 `_` 前缀、not-found 列可见名单、50_000 字符截断,错误一律以工具文本回模型而非抛异常)。
- 六个工具的空壳本体(只带 schema、函数体不可达)在 `tools/builtin/clarification_tool.py` 与 `tools/builtin/cognitive_tools.py`;**迁移后一律不走 ctx 注入**(ctx 桥随死家族待删,决议 §1.6)。
- runner 侧 HITL 探测集合 `runner._HITL_TOOL_NAMES` 收缩为 `{"ask_clarification"}`(删除 src 内无定义的死条目 `request_human_input`)。
- 测试锚:`tests/middleware/test_cognitive_tools_interception.py`(拦截行为+事件)、`tests/core/test_cognitive_tools_mounting.py`(挂载与 opt-in)。

> ✅ **审计核实(2026-06-05,graph-exec 式逐条对 pinned `7cd4b9c`)**:本 baseline 全部 `file:line` claim 命中真实代码——`cognitive_flow.py`(在 `middleware/`)198/348/455/511/604/637/698/750/765 · `md2json.py:26`(185 行)· `tools/md_to_json.py` 171/284/454/515/556/560 · `graph_assembler.py`(在 `core/`)644 · `cognitive/finish_task.py` 30/151,**零 drift**。`goto=END 绕过退出闸` 系准确记录的 live 现状(非 bug)。唯一可精化:body 用裸文件名,完整路径为 `middleware/cognitive_flow.py` / `core/graph_assembler.py`。

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
