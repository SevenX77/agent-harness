---
module: 02-mechanism/03-assemble
doc: mvp1-alignment
status: drafted（机制·装配期;A §2 装配机制 + create_agent 构造收口成段;W 工程决策依据(create_agent cluster 无 PM 原话,§4 已披露)）
aligns_with: ../../00-architecture-overview.md（§3 机制层 B·装配）
---

# 03-assemble — 机制 B · 装配机制

> **Tier**: 机制层 B · 装配期 | **Owns**: `graph_assembler`(phase→节点)· `_build_skill_node`(AGENT 闭包)· cognitive 模板**渲染** · `reference-reader`(装配期 builtin) | **现状**: ⏳ | **Related**: `01-compile`(上游 AST)· `skill-syntax`(模板语法)· `05-run-inner/01-agent-loop`(产出的内层 loop)· `compile-rules` §2.2(装配流契约)

## 1. 定义
assemble = 把可信 AST **装配成可运行 LangGraph 节点**(装配期):对每个 AGENT 节点收集 refs/tools/subagents → 跑 reference-reader → 渲染 cognitive 模板 → 建带 tools+prompt 的 Agent 节点。

## 2. 数据流 / 机制
`_build_skill_node`(AGENT phase 执行闭包构造)解析 model、收工具、subagent runtime map、prompt、finish_task。**核心迁移(从 01-agent-loop)**:把内部 `_skill_node` 的手写 ReAct loop 替换为一次 `create_agent` 构造 + 一次 invoke,tools 直接交 create_agent(不再手动 bind_tools)。reference-reader 失败只 WARN,不中断装配。
- cognitive 模板**语法**归 `skill-syntax`(契约 A),本域只做**渲染**(8 槽填充)——双向引用。

## 3. 接口契约
AST(`01-compile`)→ 节点装配契约;产出的执行闭包 → `05-run-inner/01-agent-loop` 运行;model 来自 `06-seam/01-models`、tools 来自 `04-tools`、middleware 来自 `02-middleware`、checkpointer 从外层 `assemble_graph(...,checkpointer=)` 传入。

## 4. 设计决策基础(决策依据)
本模块是**装配期机制收口**(`_build_skill_node` 把手写 loop 换成 create_agent 构造),决策为工程判断,无独立用户原话:
- **AS1**(手写 loop → create_agent 构造):LangChain 已提供工具循环/middleware/checkpointer,手写 = 重复造轮子。
- **AS3**(收口 live `assemble_graph`、不保留 `LLMPhaseNode` 双路线):现 SDK 入口实际走 assemble_graph,留双路线 = 维护分裂。
> ⚠️ 该 cluster(assemble/agent-loop/cognitive/tools)迁移源 2026-06-02 起草、未捕获用户原话;审计标注详见 `05-run-inner/01-agent-loop` §4(同一 create_agent 迁移决策,不重述)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| AS1 | `_skill_node` 手写 loop → `create_agent` 构造 | LangChain 已提供工具循环/middleware/checkpointer,手写=重复造轮子 |
| AS2 | cognitive 模板**渲染**在此,**语法**在 skill-syntax | 机制 vs 契约分层 |
| AS3 | 收口 live `assemble_graph` 路径,不保留 `LLMPhaseNode` 双路线 | 现状 SDK 入口实际走 assemble_graph |

## 6. 测试关键点
1. 失败测试先行:live `assemble_graph` 的 AGENT phase 调 `create_agent` 且传 6 槽 middleware。
2. 装配顺序:先全 AST → reference-reader → 模板渲染 → 绑 read_reference/read_example tools。

## 7. 涉及 region / platform
engine 全权。

## 8. gaps / 待设计
1. `_build_skill_node` 收口 create_agent 定稿(从 01-agent-loop 迁)。
2. reference-reader / builtin read tools 的归属(装配期 reader vs 运行期 read tools → `04-tools`)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `01-compile` · `01-contract/03-compile-rules`(装配流契约 §2.2)· `01-contract/02-skill-syntax`(模板语法,双向)· `05-run-inner/01-agent-loop` · `06-seam/01-models` · 代码现状 `core/graph_assembler.py:437-479`(_build_skill_node 入口)/`:510-562`(待替换手写 loop)
