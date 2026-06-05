---
module: 02-mechanism/05-run-inner/02-middleware
doc: mvp1-alignment
status: drafted（机制·运行内层;A 链基础成段;B live 只接单槽且 3 槽 no-op）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行内层）
---

# 02-middleware — 机制 B · 6 槽中间件链(运行内层)

> **Tier**: 机制层 B · 运行·内层 | **Owns**: 6 槽链**基础设施**(顺序/工厂/hook 契约)+ loop 卫生槽(ExecutionControl 迭代/dead-end、LoopDetection) | **现状**: A 链基础成段;B live 只接单槽且 3 槽 no-op | **Related**: 域专槽逻辑归各域:CognitiveFlow→`03-cognitive`、Tracing→`06-seam/02-observability`、ToolError→`04-tools`、ProtocolValidation→`data-contracts`;subagent/exit 各自独立模块

## 1. 定义
middleware = 内层 agent loop 的 **6 槽 hook 链**(经 `create_agent(middleware=build_middleware_chain(...))` 接入)。本域 own **链本身**(顺序契约、工厂、AgentMiddleware hook 形态)+ **纯 loop 卫生槽**;**域专槽的逻辑归各域**(本域只写槽位 + 概述 + 链到域 detail,双向引用)。

## 2. 数据流 / 机制
6 槽顺序:①ProtocolValidation(守 BusinessData 无 `_` 前缀,逻辑→`data-contracts`)②CognitiveFlow(截 finish_task/ask_clarification,逻辑→`03-cognitive`)③ExecutionControl(发 iteration 事件、检 dead-end/轻量 loop,**本域 own**)④Tracing(发微观事件,逻辑→`02-observability`)⑤ToolError(工具异常转 error ToolMessage,逻辑→`04-tools`)⑥LoopDetection(loop 保护,**本域 own**)。+ 退出闸(after_agent)= 独立 `05-exit-control` 模块、subagent 派发(wrap_tool_call)= 独立 `07-subagent` 模块(都是 middleware 实现但独立职责)。

## 3. 接口契约
`build_middleware_chain(...) -> tuple[AgentMiddleware, ...]` 交 create_agent;各 hook 形态(before/after_model、after_agent、wrap_tool_call)。

## 4. 设计决策基础(用户原话)
> 域专槽归域(2026-06-03 PM):跨切内容"非自己 scope 的部分写完整逻辑 + 引用 detail,两侧双向引用防 drift"。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| MW1 | 本域 own 链基础设施 + 纯卫生槽;域专槽逻辑归各域 | 职责归属(机制相同≠同模块);双向引用防 drift |
| MW2 | LoopDetection 实现前先复核 ExecutionControl 已有轻量 loop | 避免重复注入 |

## 6. 测试关键点
1. live `assemble_graph` AGENT phase 传 6 槽 middleware(与 `01-agent-loop` 联动)。
2. 后三槽实现后:Tracing 覆盖不减(→observability)、ToolError 转 error ToolMessage(→tools)、LoopDetection 不与 ExecutionControl 重复。

## 7. 涉及 region / platform
engine 全权。

## 8. gaps / 待设计
1. 后三槽(Tracing/ToolError/LoopDetection)从 no-op 实现到位(逻辑归各域,kiro)。
2. `parallel_map` × 6 槽链(断层#3,与 `02-iterate`/`04-tools`)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3(§6 跨切纪律)· `03-cognitive`/`06-seam/02-observability`/`04-tools`/`data-contracts`(域专槽,双向)· `05-exit-control`/`07-subagent` · `01-agent-loop`
