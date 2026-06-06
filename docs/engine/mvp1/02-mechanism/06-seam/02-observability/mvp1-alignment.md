---
module: 02-mechanism/06-seam/02-observability
doc: mvp1-alignment
status: drafted（机制·接缝;主体迁自 trace/api;边操作事件源 11-io 未迁全）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·接缝）
---

# 02-observability — 机制 B · 可观测(跨层接缝)

> **Tier**: 机制层 B · 跨层接缝 | **Owns**: 可观测**事件流**(33 类 typed event)· trace.jsonl · 序列化 · metrics(= callbacks 系统) | **现状**: 主体迁入;边操作事件源 11-io 未迁全 | **Related**: `02-middleware`(Tracing 槽,双向)· `07-subagent`(lifecycle 事件)· `03-api-contract`(事件协议)· `data-contracts`

## 1. 定义
observability = 引擎执行的**可观测事件流**——把"发生了什么"以 33 类 typed `CallbackEvent`(phase_start/llm_call/tool_call…)发出:`event_subscriber` 回调 + `trace.jsonl`(落盘 SSOT)+ WS。**它是事件流,不是"所有返回的消息"**(messages 归 `08-messages-state`/`cognitive`,RunResult 归 `data-contracts`)。

## 2. 数据流 / 机制
外层 phase 事件 + 内层**微观事件**(带 `parent_node_id` 挂回外层节点)。内层 **Tracing 中间件**(发 llm_call/tool_call 微观事件)是内层发射器,**实现在 `02-middleware` 槽 4,逻辑归本域**(双向引用)。有些事件**内嵌内容快照**(`LLMCallEvent.messages`、`CompactionEvent.content_ref`)= 为 trace 复制,不拥有消息状态。

## 3. 接口契约
事件 schema(`_EventBase` + `event_type` 判别,SSOT=`callbacks/events.py`)+ emit 机制 → `03-api-contract`(事件协议);**回调必须覆盖所有事件类型**(新增类型须同步所有回调)。

## 4. 设计决策基础(用户原话)
> callbacks 是什么(2026-06-03 PM):"callback是指所有返回的消息吗?" → 不是,是可观测事件流(33 类 event),不是 messages/RunResult。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| OB1 | callbacks = 可观测事件流,非"所有消息" | 事件(发生了 X)≠ messages(对话)≠ RunResult(返回) |
| OB2 | 内层 Tracing 发射器逻辑归本域,实现在 middleware 槽 | 机制相同≠同模块,双向引用 |
| OB3 | 回调覆盖全事件类型 | 新增事件须同步所有回调(防遗漏) |
| OB4 | 边操作事件成系列(3 新 + 2 已有),按 edge 聚合;并联节点输入分发**各发一条** | dot = 节点间全部操作可观测;机制在 `graph-exec`、事件在本域(源 11-io E5) |

## 6. 测试关键点
1. 迁到 create_agent 后现有 LLMCallEvent/ToolCallEvent 覆盖不减(D-test)。
2. 微观事件 `parent_node_id` 正确关联外层 phase 节点。
3. trace.jsonl 一行一 event;predict trace usage 归零。

## 7. 涉及 region / platform
engine 全权;trace 被 studio trace-inspector 消费(前端挂载归 studio)。

## 8. gaps / 待设计
1. V4 trace 增补:微观拓扑事件(`parent_node_id`)、**3 个边操作事件**(`BlackboardReduceEvent` 输出并入黑板 / `InputDispatchEvent` 输入按 io.inputs 切片喂节点·**并联各一条** / `InputFileInjectedEvent` 文件注入;+ 已有 `ArtifactSavedEvent`/`CompactionEvent` 同归"边操作"族,前端点 dot 按 `from_phase`/`to_phase`(edge)聚合该族 + 黑板快照)、Prompt 三视图、reducer 前后态 diff(REQ-7 单列)。源 11-io,机制落点在 `graph-exec`(双向)。
2. **subagent lifecycle 事件缺(A2)**(与 `07-subagent` 协同)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `02-middleware`(Tracing 槽,双向)· `07-subagent`(lifecycle)· `03-api-contract`(事件协议)· `data-contracts`
