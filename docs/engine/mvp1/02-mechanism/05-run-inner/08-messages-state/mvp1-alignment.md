---
module: 02-mechanism/05-run-inner/08-messages-state
doc: mvp1-alignment
status: audited-ready（**U5 单元锁定 2026-06-05**;WS-E5/E7 回写:WorkflowState.messages DeltaChannel + AGENT namespace checkpoint + Engine HITL resume_skill 已 live;PR D 回写 2026-08-15:compaction(summarization + sidecar)已迁入活路径,gap #1 关闭;Studio resume 产品仍待实现;文件未 FROZEN）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行内层）
---

# 08-messages-state — 机制 B · 内层 messages 状态(运行内层)

> **Tier**: 机制层 B · 运行·内层 | **Owns**: 内层 messages 持久化(DeltaChannel)· summarization(摘要有界化)· HITL/interrupt/resume | **现状**: Delta + AGENT namespace checkpoint + Engine HITL resume + compaction(CompactionMiddleware)live;Studio route 后续 | **Related**: `04-run-outer/03-checkpoint`(共享 base,**双向**)· `02-middleware`(summarization 中间件)· `data-contracts`(messages 通道)· `03-api-contract`(resume)

## 1. 定义
messages-state = 内层 agent loop 的 **messages 状态生命周期**(对照外层 `03-checkpoint` 的 blackboard):messages 持久化(DeltaChannel)+ summarization(messages 增长时摘要有界化)+ HITL(经 `interrupt()` 中断、人改 context 后 resume)。WS-E5 后,AGENT messages 已经经 `agent:<phase>` / `iter{k}.agent:<phase>` namespace 挂 `03-checkpoint` 的共享 base;WS-E7 后,Engine `resume_skill` 已能注入 HITL ToolMessage。两层共享 base、各管各 state(外 blackboard / 内 messages,双向引用)。

## 2. 数据流 / 机制
承接共享 checkpoint 的**内层/messages 部分** + agent-loop 的 summarization。

> **现状 vs 目标**:**live 今天已有** `WorkflowState.messages` 的 `DeltaChannel(snapshot_frequency=50)` 通道(`state.py:237`)、AGENT namespace checkpoint、`interrupt()` 原语(`cognitive_flow.py:292`)、Engine `resume_skill` 的 HITL ToolMessage 注入,以及 **summarization/compaction**(PR D 2026-08-15:`middleware/compaction.py` 的 `CompactionMiddleware`,顺序契约第 4 槽,fraction 0.8 / keep 20 + sidecar 全文 + `CompactionEvent.content_ref`)。**仍未 live**:Studio HTTP `resume_run` 仍是 501 桩(`runs.py:70`)。

**阶段边界的 messages 语义(用户裁决,九轮定稿 Round 8 第 3 条)**:一个阶段的 agent 以
**空 messages** 起步——`messages = []` by-design,加"按需挖掘"(`context_access` opt-in)。
阶段之间的数据只走黑板:阶段在 `io.inputs` 里声明它消费什么,就只拿到什么;上游阶段的对话记录
不是第二条入口。这条规则约束的是**递给阶段什么**,不约束**运行留下什么**——阶段产出的 messages
仍然并回全局 `WorkflowState.messages` 通道,所以整次运行的对话记录、checkpoint 与 HITL resume
都建立在完整历史之上。落点:`runtime/state_mapper.py` 的 `select_declared_inputs`;同形的
SUBGRAPH(`graph_assembler.py:1638`)与 subagent(`:2916`)本来就是这个语义。
理由与现场证据见 `.kiro/specs/decision-2026-08-16-a-phase-opens-its-own-conversation.md`。

messages 两条存储纪律(与 `03-checkpoint` blackboard 同构、各管各;**下为目标模型**):
- **delta(去体积,无损)**:`DeltaChannel`(`state.py:237`,`_messages_delta_reducer:28`,**`snapshot_frequency=50`**——每 50 步存全量 snapshot、中间存 diff;经 ns 入共享 base,每 model/tool 步存档)。snapshot 频率 = 平衡旋钮(小=体积大、大=回放/resume 慢,需实测)。
- **compact(有界,有损/外移)**:summarization——超窗触发的摘要中间件(实现在 `02-middleware`,逻辑本域)+ sidecar 存全文(`CompactionEvent.content_ref`)。
- **compact 是 1000 章可行性前提(= `03-checkpoint` CK6)**:不 compact 则上下文 O(N²) 爆窗口(第 1000 章塞 999 章超所有模型);compact 后 O(N)。
- HITL:`interrupt()`(`cognitive_flow.py:292`;`:95` `_interrupt_fn or interrupt`、`:300` `source="human_interrupt"`)中断 → `update_state` 套 context_overrides / 注入 ToolMessage → 带该 checkpoint 重 invoke。

## 3. 接口契约
messages 经 `agent:<phase>` / `iter{k}.agent:<phase>` namespace 挂 `03-checkpoint` base(live;双向);Engine `resume_skill(run_id, checkpoint_id|checkpoint_ns, context_overrides?, human_response?)` 已 live;Studio `resume_run(...)` HTTP route 仍是 501 桩;messages 通道 = `WorkflowState.messages` + `DeltaChannel` reducer(`state.py:214`,归 `data-contracts`)。

## 4. 设计决策基础(用户原话)
> 两层各管各 state(2026-06-03 PM):checkpoint 一个共享 base,外管 blackboard、内(本域)管 messages。
> HITL 必须 checkpoint agent loop:"agent loop现在不做checkpoint, 那哪来的人类打断对话后继续这个功能? 我和外层langgraph对话个啥? 都没有llm调用"
> 极限场景(compact 的尺度来源):"写一部1000章的小说, 或者分析拆解一部1000章的小说转成剧本"

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| HS1 | messages 经 ns 挂 `03-checkpoint` 共享 base(不另起 saver) | 两层共享 base、各管各 state |
| HS2 | summarization = 内层有界化(vs 外层 blackboard compact) | 外/内主轴,挂错层白做 |
| HS3 | HITL `interrupt()` + 同 base 续跑 | mid-conversation 续跑成立 |
| HS4 | **compact(summarization)是 1000 章可行性前提,非优化**(= `03-checkpoint` CK6) | 不 compact 上下文 O(N²) 爆窗口;compact 后 O(N) |

## 6. 测试关键点
1. Engine `resume_skill` 注入 HITL response 后,从对话断点恢复(嵌套 ns 寻址 D-test,与 `03-checkpoint`/`02-middleware` 协同)。
2. messages summarization 触发后有界、不丢关键上下文;sidecar 存全文。
3. predict mock 仍能模拟 summarization 形态(承 09 G5,→ `06-seam/01-models`)。

## 7. 涉及 region / platform
engine 全权;HITL 暴露给 studio debug/续跑(`03-api-contract`)。

## 8. gaps / 待设计
1. ~~summarization middleware + sidecar 从 legacy 死簇搬回 live~~ **已关闭(PR D,2026-08-15 决议 §3.6)**:live 实现 = `middleware/compaction.py` 的 `CompactionMiddleware`(顺序契约第 4 槽,包装 langchain `SummarizationMiddleware`,fraction 0.8 / keep 20 + sidecar 全文落盘 + `CompactionEvent.content_ref`;代码现实见本单元 baseline §2)。live 装配已非「单槽 cognitive_flow」——现实为契约 8 槽 + 前置 2 槽的 10 槽链(`02-middleware` baseline)。死侧原实现待 PR E 整族删,行号按决议 §6.2 校正为:配置 `phase_nodes/llm_phase_node.py:277-282`、底座 `cognitive/middlewares.py:467`、sidecar 写 `llm_phase_node.py:383`、CompactionEvent 构造 `:813`。
2. Studio `resume_run` thin route + context 篡改边界(与 `03-checkpoint`/`02-iterate`)。
3. **持久化边界(源 uncovered #3)**:messages 通道只写可序列化的 messages + 标记;middleware 内 callback/runtime/compiled graph **不得入 checkpoint state**(与 `03-checkpoint` §8 #4 共,防 nested state 污染)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `04-run-outer/03-checkpoint`(共享 base,**双向:外 blackboard/内 messages**)· `02-middleware`(summarization 中间件)· `data-contracts`(messages 通道)· `03-api-contract`(resume)
