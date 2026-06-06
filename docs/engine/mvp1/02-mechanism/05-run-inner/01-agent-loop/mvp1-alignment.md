---
module: 02-mechanism/05-run-inner/01-agent-loop
doc: mvp1-alignment
status: drafted（机制·运行内层;A §2 create_agent 迁移机制成段;W 工程决策(§4 已披露);B live 手写 loop=目标态 demarcate）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行内层）
---

# 01-agent-loop — 机制 B · agent loop 编排(运行内层)

> **Tier**: 机制层 B · 运行·内层(LLM 驱动) | **Owns**: `create_agent` 编排(model↔tool ReAct) | **现状**: ⏳ | **Related**: `03-assemble`(构造它)· `02-middleware` · `03-cognitive` · `04-tools` · `06-seam/01-models` · `08-messages-state`(checkpoint)

## 1. 定义
agent-loop = AGENT phase 里跑的**内层 ReAct 循环**:`create_agent(model, tools, middleware, checkpointer)` 编排 model↔tool 来回,直到 finish_task。是外层 graph-exec 在 AGENT 节点委派的内层执行。

## 2. 数据流 / 机制
核心:把现状手写 `for _ in range(max_turns)` 的 ReAct loop(`graph_assembler.py:483-576`,逐手调 `model.invoke`/`tool.invoke`、手拼 `ToolMessage`、无 tool_calls 时直接 `break` 裸退)**替换为一次 `create_agent` 构造 + 一次 `agent.invoke`**——LangChain `create_agent` 已封装工具循环,签名吃 `model`/`tools`/`system_prompt`/`middleware`/`checkpointer`(`langchain/agents/factory.py:658-673`)。装配参数:`model=GatewayChatModel`(provider 差异下沉 gateway,引擎不分支)、`tools=business+framework+finish_task+subagent`、`middleware=build_middleware_chain(6 槽:ProtocolValidation/CognitiveFlow/ExecutionControl/Tracing/ToolError/LoopDetection)`、`checkpointer` 经 `ns="<id>/agent"` 挂外层共享 base(归 `08-messages-state`/`03-checkpoint`)。构造点在 `03-assemble` 的 `_build_skill_node`。**收口 live `assemble_graph` 单一路径,不保留并存的 `LLMPhaseNode` 第二条 create_agent 风格 loop**(现 SDK 入口实际走 assemble_graph,留双路线 = 第三条分裂)。

## 3. 接口契约
`create_agent` 签名(model/tools/system_prompt/middleware/checkpointer);model 吃 `GatewayChatModel`(`06-seam/01-models`,provider 差异归 gateway,引擎不分支);tools/middleware/cognitive 各归其域。

## 4. 设计决策基础(决策依据)
本模块是**引擎内部机制收口**(手写 loop 迁回 `create_agent`),决策属工程理由,依据有二:
- **AL2 = 核心决策**(model 吃 `GatewayChatModel`、provider 差异下沉 gateway,编排不被 provider 格式统一推翻)——源自工作区铁律「核心决策不可被配套条件推翻」:曾踩坑为 API 统一丢掉 ToolRunner、手写劣化 loop → 内容质量崩。
- **AL1**(手写 loop → create_agent):LangChain 现成提供工具循环 / middleware hook / checkpointer / jump,手写 = 重复造轮子,还得自己处理 tool-call 消息配对、return-direct、middleware 顺序、checkpoint 交互。
> ⚠️ 审计标注(2026-06-04):本模块及配套 `03-assemble`/`03-cognitive`/`04-tools` 的迁移源(2026-06-02 起草,早于 06-03 三层重构)**从未捕获用户原话**——它们是工程迁移文档,决策为工程判断。上述即真实依据,非省略;若后续有 PM 对 agent loop 取舍的原话,补进此节。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| AL1 | 手写 ReAct loop → `create_agent` | LangChain 已提供工具循环/middleware/checkpointer/jump |
| AL2 | `model=GatewayChatModel`,provider 差异归 gateway | 核心决策:编排不被 provider 格式统一推翻 |

## 6. 测试关键点
1. D-test-3:`create_agent(model=GatewayChatModel)` 端到端,gateway usage/thinking blocks/tool-call metadata 不丢。
2. live `assemble_graph` AGENT phase 调 create_agent 且传 6 槽 middleware。

## 7. 涉及 region / platform
engine 全权;model 接缝 ↔ gateway(独立子系统)。

## 8. gaps / 待设计
1. 内层是否给 phase agent 也传 checkpointer(已收口:经 ns 挂同一个,见 `08-messages-state`)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `03-assemble`(构造)· `02-middleware` · `03-cognitive` · `04-tools` · `06-seam/01-models` · `08-messages-state` · 代码现状 `core/graph_assembler.py:483-576`(待替换的 live 手写 loop)· `middleware/factory.py:29-65`(6 槽工厂)
