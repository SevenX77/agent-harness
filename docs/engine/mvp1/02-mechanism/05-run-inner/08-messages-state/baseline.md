---
module: 02-mechanism/05-run-inner/08-messages-state
doc: baseline
status: audited-ready（PR D 回写 2026-08-15:compaction 已迁入活路径——CompactionMiddleware(顺序契约第 4 槽)包装 langchain SummarizationMiddleware(fraction 0.8 / keep 20)+ sidecar 全文落盘 + CompactionEvent(content_ref);Studio resume_run 仍 501）
---

# 08-messages-state — Baseline(当下代码实现逻辑)

> **Scope**: 内层 messages 状态生命周期的现状:messages 持久化(`state.py` 的 DeltaChannel)、AGENT 内层 namespace checkpoint、summarization/compaction、HITL/resume。
> **现状一句话**:内层 messages 用 **DeltaChannel 增量快照通道**(`state.py:237`,`snapshot_frequency=50`)已 live;AGENT create_agent 路径已通过 `NamespaceCheckpointer` 复用外层共享 base 并写入 `agent:<phase>` namespace,graph iterate 内组合为 `iter{k}.agent:<phase>`;WS-E7 `resume_skill` 已能向 pending tool call 注入结构化 HITL `ToolMessage`;**summarization/compaction 已 live**(2026-08-15 决议 §3.6 PR D:`middleware/compaction.py` 的 `CompactionMiddleware`,顺序契约第 4 槽);Studio HTTP `resume_run` 仍是 501。

## UI/UX
N/A。

## 前端逻辑
N/A —— studio debug/续跑 UI 经 `03-api-contract` 消费。

## 后端功能

### 1. messages 持久化:DeltaChannel(已 live)
`WorkflowState.messages`(`state.py:237`)= `Annotated[list[AnyMessage], DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)]`——增量快照通道:每步只存 delta,每 50 步一全量快照(reducer `_messages_delta_reducer` `:28`;`:49-55` 显式处理 `RemoveMessage(REMOVE_ALL_MESSAGES)`——compaction 的消息重写正是走这条协议)。这是 messages 经 checkpoint 持久化的底座(挂 `03-checkpoint` 的 base)。
> **DeltaChannel 第一次出现需定义**:LangGraph 的增量通道——对增长型列表(如对话历史)只存变化 + 周期快照,避免每 super-step 全量(去体积)。

### 1.5 AGENT 内层 namespace checkpoint(WS-E5 已 live)
live `assemble_graph` 的 AGENT phase 走 LangChain `create_agent(..., state_schema=WorkflowState, checkpointer=NamespaceCheckpointer(base,"agent:<phase>"))`。当外层 graph 提供 checkpointer 时,内层 AGENT 使用同一个 base saver,同一 `thread_id` 下可通过 `checkpoint_ns="agent:<phase>"` 读取内层 checkpoint。若 AGENT 跑在 graph-level iterate 内,namespace 组合为 `iter{k}.agent:<phase>`,因此轮次与 agent/phase scope 同时保留。

这一步解决 checkpoint namespace/共享 base;WS-E7 又补上 Engine `resume_skill` 的 HITL ToolMessage 注入。messages summarization、有界化 sidecar、Studio resume UI/HTTP 仍未接 live。

### 2. summarization / compaction(已 live,2026-08-15 决议 §3.6 PR D)
live 实现 = `middleware/compaction.py` 的 `CompactionMiddleware`(顺序契约第 4 槽,`middleware/__init__.py:65`;链构成归 `02-middleware`):

- **压缩本体**:组合(非继承)langchain 官方 `SummarizationMiddleware`,参数 `trigger=[("fraction", 0.8)]` / `keep=("messages", 20)`(P0-1 裁决,常量 `COMPACTION_TRIGGER_FRACTION`/`COMPACTION_KEEP_MESSAGES`,`compaction.py:54-55`)。触发检测不碰 langchain 内部:调用内层 `before_model` 后对比其返回的 messages 更新与入参 state——`None`=未触发(零行为改变),非 `None` 时按消息 id 差集识别被移出的消息(`_removed_messages`,`compaction.py:279`)。
- **sidecar 全文落盘**:`write_compaction_sidecar`(`compaction.py:77`)把被移出消息经 `message_to_dict` 无损写入 `<run_dir>/compaction/<phase>-NNN.json`(UTF-8);run_dir 取自 `flow.persistent_storage_config["run_dir"]`(runner 在 `runner.py:2107` 写入——runner 是唯一知道该执行落 `runs/` 还是 `predicts/` 的调用方,见 `io/run_layout.py`)。state 无 run_dir 时降级:压缩照常、`content_ref=None` + warning,不中断 run。
- **CompactionEvent**:每次触发发 typed 事件(`events.py:202`),字段 `removed_message_count`(本次改名,原 `removed_pairs`——摘要压缩移除的是 N 条消息不是 pair)+ `removed_summary` + `content_ref`(= sidecar 路径)。
- **profile 兜底**:model 缺 `profile["max_input_tokens"]` 时包 `_SummarizationReadyModel` shim(fallback 32_000,`SUMMARIZATION_FALLBACK_MAX_INPUT_TOKENS`,语义自死侧 `_ensure_summarization_profile` 迁移),否则 fraction trigger 构造即炸。
- **装配注入**:`graph_assembler.py:2036-2037` 把 phase 已解析 chat model 与 sidecar writer 显式传入工厂。

死侧原实现(`phase_nodes/llm_phase_node.py` 的配置与 sidecar 写入、`cognitive/middlewares.py` 的底座构造)已随 2026-08-15 决议 §5 的整族删除移除,查阅原样以 git 历史为准。`execution_control.py` 的 `_summarize_recent_failures` 是"失败摘要"(不同于 messages compaction)。

### 3. HITL / resume(Engine live,Studio route 未接)
`interrupt()` **原语 live**(`cognitive_flow.py:33` import / `:95` `_interrupt_fn or interrupt` / `:292` 调用 / `:300` `source="human_interrupt"`)。WS-E7 后,Engine `resume_skill` 要求 `human_response={content, tool_call_id?}`,会校验 selected checkpoint 内存在 pending tool call,并通过 `ToolMessage(content=..., tool_call_id=...)` 更新 state 后重 invoke。Studio `resume_run` 端点仍 501(`apps/studio/backend/app/routers/runs.py:70` `raise_not_implemented`),`ResumeReq.context_overrides` 字段定义了但零消费(见 `03-api-contract`)。

## API
- `WorkflowState.messages`(`state.py:237`,DeltaChannel)/ `_messages_delta_reducer`(`:28`)。
- `CompactionMiddleware` / `write_compaction_sidecar` / `CompactionSidecarWriter`(`middleware/compaction.py`;工厂注入点 `factory.py:35` 的 `compaction_model`/`compaction_sidecar_writer`)。
- `runner.py:resume_skill`(Engine 进程内 HITL/context override resume);Studio `resume_run(run_id, ...)` route 后续薄接。

## Data Model / State
`messages: list[AnyMessage]`(DeltaChannel,`state.py:237`)——内层对话历史(对照外层 `data` blackboard,归 `03-checkpoint`)。compaction sidecar = `<run_dir>/compaction/<phase>-NNN.json`(run 目录内,随 run 留存/清理)。

## 当前边界(这个模块现在不是什么)
- **Studio HITL resume 未闭环**:`resume_run`=501,context_overrides 零消费;Engine `resume_skill` 已能注入 HITL ToolMessage。
- **messages 已有内层 ns checkpoint,但不是完整 Studio HITL 产品**:AGENT 内层已按 `agent:<phase>` / `iter{k}.agent:<phase>` 写入共享 base;Engine 可从 checkpoint 恢复,但用户界面选择 checkpoint、HTTP 投影和错误展示仍未闭环。
- **compaction 不做前端投影**:CompactionEvent 目前无 Studio 前端消费分支(核对于 2026-08-15,前端零 compaction 引用);事件与 sidecar 先保证引擎侧可追溯。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| messages 持久化 | DeltaChannel 已 live(`state.py:237`);AGENT 内层经 `agent:<phase>` / `iter{k}.agent:<phase>` 挂共享 base | HITL/resume 能消费这些 checkpoint 从内层断点续跑 |
| compaction | **已 live**(`middleware/compaction.py`,契约第 4 槽;超窗摘要 + sidecar 全文 + CompactionEvent) | 保持;死侧副本已随整族删除移除 |
| HITL/resume | Engine `resume_skill` 已消费 pending tool call + overrides;Studio HTTP route 仍 501 | Studio 薄接 Engine resume 并提供用户态 checkpoint/HITL 工作流 |

> **验"是否按 mvp1 改了"**:① 同一 base/thread 是否能区分外层 `""` 和 AGENT `agent:<phase>` checkpoint;② graph iterate 内 AGENT checkpoint 是否保留 `iter{k}.agent:<phase>`;③ Engine `resume_skill` 能注入 HITL response 并从对话断点恢复;④ Studio HTTP/UI resume 是否闭环(仍未 live);⑤ messages summarization 触发后有界、sidecar 存全文、CompactionEvent.content_ref 指向 sidecar(已 live,行为测试 `tests/middleware/test_compaction.py`)。

## 读代码主路径提示
messages 通道 `state.py:237` + reducer `:28` → compaction live 实现 `middleware/compaction.py`(工厂 `factory.py:35`、装配注入 `graph_assembler.py:2036-2037`、run_dir 面 `runner.py:2107`)→ resume 缺口 `03-api-contract`/`02-iterate` baseline。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `04-run-outer/03-checkpoint`(共享 base,双向:外 blackboard/内 messages)· `02-middleware`(summarization 中间件)· `data-contracts`(messages 通道)· `03-api-contract`(resume)
