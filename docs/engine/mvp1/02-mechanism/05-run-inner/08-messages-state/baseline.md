---
module: 02-mechanism/05-run-inner/08-messages-state
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；messages 已用 DeltaChannel,compaction 搁浅 legacy,HITL resume 未接 live）
---

# 08-messages-state — Baseline(当下代码实现逻辑)

> **Scope**: 内层 messages 状态生命周期的现状:messages 持久化(`state.py` 的 DeltaChannel)、summarization/compaction、HITL/resume。
> **现状一句话**:内层 messages 用 **DeltaChannel 增量快照通道**(`state.py:214`,`snapshot_frequency=50`)已 live;但 **summarization/compaction 搁浅在 legacy `phase_nodes`**(`llm_phase_node.py:84/138` 的 `save_compaction_sidecar`,**不在** live `assemble_graph` 路径);HITL `resume` 未接 live(`resume_run`=501,见 `03-api-contract`)。

## UI/UX
N/A。

## 前端逻辑
N/A —— studio debug/续跑 UI 经 `03-api-contract` 消费。

## 后端功能

### 1. messages 持久化:DeltaChannel(已 live)
`WorkflowState.messages`(`state.py:214`)= `Annotated[list[AnyMessage], DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)]`——增量快照通道:每步只存 delta,每 50 步一全量快照(reducer `_messages_delta_reducer` `:28`)。这是 messages 经 checkpoint 持久化的底座(挂 `03-checkpoint` 的 base)。
> **DeltaChannel 第一次出现需定义**:LangGraph 的增量通道——对增长型列表(如对话历史)只存变化 + 周期快照,避免每 super-step 全量(去体积)。

### 2. summarization / compaction(搁浅 legacy,非 live)
`save_compaction_sidecar`(`phase_nodes/llm_phase_node.py:84/138`)在 **legacy phase_nodes 死簇**里——超窗摘要 + sidecar 存全文。**live `assemble_graph` 路径没有 compaction**(待从死簇搬回 live)。`execution_control.py:201` 的 `_summarize_recent_failures` 是"失败摘要"(不同于 messages compaction)。

### 3. HITL / resume(未接 live)
HITL(`interrupt()` 中断 → 人改 context → resume)与节点级 `resume_run` 在 live 未闭环:`resume_run` 端点 501(`apps/studio/.../runs.py`),`ResumeReq.context_overrides` 字段定义了但零消费(见 `03-api-contract` / `02-iterate` baseline)。

## API
- `WorkflowState.messages`(`state.py:214`,DeltaChannel)/ `_messages_delta_reducer`(`:28`)。
- (目标)`resume_run(run_id, from, context_overrides?)`(归 `03-api-contract` C2)。

## Data Model / State
`messages: list[AnyMessage]`(DeltaChannel,`state.py:214`)——内层对话历史(对照外层 `data` blackboard,归 `03-checkpoint`)。

## 当前边界(这个模块现在不是什么)
- **compaction 不在 live**:搁浅 legacy phase_nodes(`llm_phase_node.py:84`),live 路径无摘要有界化。
- **HITL resume 未闭环**:`resume_run`=501,context_overrides 零消费。
- **messages 未挂内层 ns**:当前内层 agent loop 不挂 checkpoint(见 `03-checkpoint`),mvp1 要经 `ns="<id>/agent"` 挂共享 base。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| messages 持久化 | DeltaChannel 已 live(`state.py:214`) | 经 `ns="<id>/agent"` 挂共享 base |
| compaction | 搁浅 legacy(`llm_phase_node.py:84`) | 搬回 live(超窗摘要 + sidecar 存全文) |
| HITL/resume | 501、零消费 | interrupt + 同 base 续跑 + context_overrides |

> **验"是否按 mvp1 改了"**:① interrupt → 人改 context → resume 从对话断点恢复(嵌套 ns 寻址 D-test);② messages summarization 触发后有界、sidecar 存全文;③ compaction 是否从死簇搬回 live。

## 读代码主路径提示
messages 通道 `state.py:214` + reducer `:28` → compaction 搁浅点 `phase_nodes/llm_phase_node.py:84/138` → resume 缺口 `03-api-contract`/`02-iterate` baseline。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `04-run-outer/03-checkpoint`(共享 base,双向:外 blackboard/内 messages)· `02-middleware`(summarization 中间件)· `data-contracts`(messages 通道)· `03-api-contract`(resume)
