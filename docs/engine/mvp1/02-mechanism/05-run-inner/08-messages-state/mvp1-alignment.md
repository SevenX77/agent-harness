---
module: 02-mechanism/05-run-inner/08-messages-state
doc: mvp1-alignment
status: drafted（机制·运行内层;✅/⏳ 内层 messages 状态生命周期）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行内层）
---

# 08-messages-state — 机制 B · 内层 messages 状态(运行内层)

> **Tier**: 机制层 B · 运行·内层 | **Owns**: 内层 messages 持久化(DeltaChannel)· summarization(摘要有界化)· HITL/interrupt/resume | **现状**: ✅ / ⏳ | **Related**: `04-run-outer/03-checkpoint`(共享 base,**双向**)· `02-middleware`(summarization 中间件)· `data-contracts`(messages 通道)· `03-api-contract`(resume)

## 1. 定义
messages-state = 内层 agent loop 的 **messages 状态生命周期**(对照外层 `03-checkpoint` 的 blackboard):messages 持久化(DeltaChannel)+ summarization(messages 增长时摘要有界化)+ HITL(经 `interrupt()` 中断、人改 context 后 resume)。**经 `ns="<id>/agent"` 挂 `03-checkpoint` 的共享 base**——两层共享 base、各管各 state(外 blackboard / 内 messages,双向引用)。

## 2. 数据流 / 机制
承接共享 checkpoint 的**内层/messages 部分** + agent-loop 的 summarization:
- messages 持久化:`DeltaChannel`(`state.py:214`,snapshot_frequency=50,每 model/tool 步存档,经 ns 入共享 base)。
- summarization:超窗触发的摘要中间件(实现在 `02-middleware`,逻辑本域)+ sidecar 存全文(`CompactionEvent.content_ref`)。
- HITL:`interrupt()`(`cognitive_flow.py:292`)中断 → `update_state` 套 context_overrides / 注入 ToolMessage → 带该 checkpoint 重 invoke。

## 3. 接口契约
messages 经 `ns="<id>/agent"` 挂 `03-checkpoint` base(双向);`resume_run(run_id, from, context_overrides?)`(归 `03-api-contract` C2);messages 通道(`AgentState.messages` + DeltaChannel reducer)归 `data-contracts`(langgraph 底座)。

## 4. 设计决策基础(用户原话)
> 两层各管各 state(2026-06-03 PM):checkpoint 一个共享 base,外管 blackboard、内(本域)管 messages。
> HITL 必须 checkpoint agent loop:"agent loop现在不做checkpoint, 那哪来的人类打断对话后继续这个功能?"

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| HS1 | messages 经 ns 挂 `03-checkpoint` 共享 base(不另起 saver) | 两层共享 base、各管各 state |
| HS2 | summarization = 内层有界化(vs 外层 blackboard compact) | 外/内主轴,挂错层白做 |
| HS3 | HITL `interrupt()` + 同 base 续跑 | mid-conversation 续跑成立 |

## 6. 测试关键点
1. interrupt → 人改 context → resume,从对话断点恢复(嵌套 ns 寻址 D-test,与 `03-checkpoint`/`02-middleware` 协同)。
2. messages summarization 触发后有界、不丢关键上下文;sidecar 存全文。
3. predict mock 仍能模拟 summarization 形态(承 09 G5,→ `06-seam/01-models`)。

## 7. 涉及 region / platform
engine 全权;HITL 暴露给 studio debug/续跑(`03-api-contract`)。

## 8. gaps / 待设计
1. summarization middleware + sidecar **从 legacy 死簇搬回 live**(现搁浅 `phase_nodes/llm_phase_node.py:809`)。
2. `resume_run` context 篡改边界(与 `03-checkpoint`/`02-iterate`)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `04-run-outer/03-checkpoint`(共享 base,**双向:外 blackboard/内 messages**)· `02-middleware`(summarization 中间件)· `data-contracts`(messages 通道)· `03-api-contract`(resume)
