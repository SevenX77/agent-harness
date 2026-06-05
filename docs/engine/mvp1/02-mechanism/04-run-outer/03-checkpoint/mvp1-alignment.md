---
module: 02-mechanism/04-run-outer/03-checkpoint
doc: mvp1-alignment
status: drafted（A 摘要成段;records 深度未迁完;B inner 未挂/data delta 未）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行外层）
---

# 03-checkpoint — 机制 B · 外层状态持久化 + 共享 base

> **Tier**: 机制层 B · 运行·外层(尺度无关) | **Owns**: **共享 checkpointer base**(建外层,经 `checkpoint_ns` 内外层共用)· 外层 blackboard 存储/delta/有界 · durability | **现状**: A 摘要成段;records 深度未迁完 | **Related**: `05-run-inner/08-messages-state`(内层 messages,双向)· `02-iterate`(图级 loop)· `data-contracts`(state schema)· `03-api-contract`(resume)

## 1. 定义
checkpoint = **一个共享 base**(LangGraph thread checkpointer,**建在外层 `builder.compile(checkpointer=)`**),节点/iterate/图级/**内层 agent loop** 都经 `checkpoint_ns` 挂同一个 saver(不另起内层 saver)。**两层各管各 state**:外层这边管 **blackboard**(`WorkflowState.data`);内层 messages 在 `08-messages-state`(经 `ns="<id>/agent"` 挂本 base)。

## 2. 数据流 / 机制
本域承接共享 checkpoint 的**外层/base 部分**(模型经多轮 PM 收敛):
- 唯一 base + `checkpoint_ns` 嵌套分层(尺度无关:graph⊃phase⊃iterate⊃agent loop)。
- **blackboard 存储纪律**:delta(`data` 通道补 delta reducer,去体积)+ 有界 accumulator(`{rolling_summary, recent_window[K], artifact_refs[]}`,全文→artifact)。
- delta/compact 跟**连乘大 N**,无固定次要层。durability 旋钮(D-test 定粒度)。
- 图级 loop=B(引擎包 loop-body)的 checkpoint 归 `02-iterate`(双向)。

## 3. 接口契约
`assemble_graph(..., checkpointer=)` 注入(归 `03-assemble`);嵌套 ns 寻址(外层 super-step ↔ 内层 agent step,经 `08-messages-state`);resume 寻址 `get_state_history`→选 checkpoint_id→update_state(归 `03-api-contract` C2);state schema 归 `data-contracts`。

## 4. 设计决策基础(用户原话)
> 两层各一套(2026-06-03 PM):"checkpoint 不是 in/out 分别单独一套吗?" → 一个共享 base、两层各管各 state(外 blackboard / 内 messages)。
> HITL 必须 checkpoint agent loop:"agent loop现在不做checkpoint, 那哪来的人类打断对话后继续这个功能?"

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| CK1 | 唯一 base + `checkpoint_ns` 嵌套,不另起内层 saver | 统一 resume(`get_state_history` 全局寻址) |
| CK2 | base 建外层(compile 时);内层经 ns 挂同一个 | base 在外层图 compile 建,内层 attach |
| CK4 | delta/compact 跟连乘大 N,无固定次要层 | 外层图循环 1000× 时外层 phase 累积档正是主战场 |
| CK5 | blackboard(本域)与 messages(`08-messages-state`)分治 | 两者增长源/兜底不同,挂错层白做 |

## 6. 测试关键点
1. 嵌套 ns 寻址续跑(D-test,头号风险,uncovered #3;与 `08-messages-state`/`02-middleware` 协同)。
2. blackboard delta:1000 遍 loop checkpoint 总体积 O(N) 非 O(N²)。
3. 有界 blackboard:喂第 k 遍上下文体积恒定。

## 7. 涉及 region / platform
engine 全权;studio 侧 resume_run/HITL UI 经 `03-api-contract` 消费。

## 8. gaps / 待设计
1. `data`(blackboard)通道 delta reducer(append-accumulator 友好)。
2. 有界 accumulator(`accumulate.merge` 加 rolling-summary)。
3. durability 取值(D-test)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `05-run-inner/08-messages-state`(内层 messages,**双向:共享 base**)· `02-iterate`(图级 loop)· `data-contracts` · `03-api-contract`(resume C2)
