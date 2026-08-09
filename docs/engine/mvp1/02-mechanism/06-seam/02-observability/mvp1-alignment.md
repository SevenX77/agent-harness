---
module: 02-mechanism/06-seam/02-observability
doc: mvp1-alignment
status: drafted（**U9 单元锁定 2026-06-06**;33 event 流 live、V4 trace 增补成段(微观拓扑/边操作 OB4/subagent lifecycle 目标归 kiro、Prompt 三视图核实已满足、reducer-diff=前端近似 OB5)、现状/目标 demarcate;文件未 FROZEN——参与 U7/U9）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·接缝）
---

# 02-observability — 机制 B · 可观测(跨层接缝)

> **Tier**: 机制层 B · 跨层接缝 | **Owns**: 可观测**事件流**(33 类 typed event)· trace.jsonl · 序列化 · metrics(= callbacks 系统) | **现状**: 33 event 流 live;V4 增补(微观拓扑/边操作/subagent lifecycle)目标归 kiro,Prompt 三视图已满足,reducer-diff=前端近似(OB5) | **Related**: `02-middleware`(Tracing 槽,双向)· `07-subagent`(lifecycle 事件)· `03-api-contract`(事件协议)· `data-contracts`

## 1. 定义
observability = 引擎执行的**可观测事件流**——把"发生了什么"以 33 类 typed `CallbackEvent`(phase_start/llm_call/tool_call…)发出:`event_subscriber` 回调 + `trace.jsonl`(落盘 SSOT)+ WS。**它是事件流,不是"所有返回的消息"**(messages 归 `08-messages-state`/`cognitive`,RunResult 归 `data-contracts`)。

## 2. 数据流 / 机制
外层 phase 事件 + 内层**微观事件**(带 `parent_node_id` 挂回外层节点)。内层发射器有两个,各自贴着它报告的那件事(OB6):**Tracing 中间件**套在工具执行外面,发 `tool_call_started`/`tool_call`(**实现在 `02-middleware` 槽 4,逻辑归本域**,双向引用);**chat model** 自己在请求 provider 前发 `prompt_captured`、由 phase 节点在拿到回答后发 `llm_call`。有些事件**内嵌内容快照**(`LLMCallEvent.messages`、`CompactionEvent.content_ref`)= 为 trace 复制,不拥有消息状态。

> **⚠️ 现状 vs 目标**:33 类 typed event + `trace.jsonl` 落盘 **live**(`events.py:56-443`/`emit.py:15`)。但**内层 Tracing 中间件 emit = no-op 现状**(`02-middleware` 后 3 槽空壳,微观 llm_call/tool_call 事件经中间件发射 = 目标)。V4 trace 增补(微观拓扑 `parent_node_id`/3 边操作事件/subagent lifecycle)= **目标事件、归 kiro**(§8);Prompt 三视图**已满足**(§8 #1);reducer-diff = **前端近似**(OB5,engine 不加 authoritative 事件)。

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
| OB6 | **"某一步开始了"由执行这一步的那个单元自己发**,不由包在某类调用方外面的装饰器发。LLM 往返的开始事件 `prompt_captured` 发自 chat model 内部(`LLMProviderChatModel._generate`,在请求 provider **之前**);工具调用的开始事件 `tool_call_started` 发自 Tracing 中间件(它就套在工具执行外面) | 装饰器只对"以它预期的方式调用模型"的调用方生效:旧实现 `TracingClientProxy` 拦 `.invoke()`,只有 LLM phase 节点那样调;AGENT phase 把模型交给 `create_agent`,LangChain 走 `_generate`,于是**耗时最长的那条路一个开始信号都没有**——一次 5 分钟的 phase 在 UI 上全程空白(实测 2026-08-09)。放到调用点后,新增节点类型不可能漏发、也没有能被绕过的包装层。代价:模型现在多背 `sub_run_id`/`group_key` 两个只用于上报的字段,换掉的是"同一事实两个 owner" |
| OB5 | reducer 前后态 diff(REQ-7)= **前端近似**(从 OB4 边操作事件带的黑板快照 + phase 边界比对),engine **不加** authoritative 逐 reducer diff 事件(PM 2026-06-06 选 A) | 边操作事件已带黑板快照、足够前端近似"哪个 key 变了";authoritative 逐 reducer emit = 引擎复杂度↑、调试边际价值↓,deferred(工程取舍,非业务判断) |

## 6. 测试关键点
1. 迁到 create_agent 后现有 LLMCallEvent/ToolCallEvent 覆盖不减(D-test)。
2. 微观事件 `parent_node_id` 正确关联外层 phase 节点。
3. trace.jsonl 一行一 event;predict trace usage 归零。
4. **OB6:开始事件必须先于工作发生,且 AGENT phase 也要有。** 两层各钉一条:
   单元层——provider 被要求干活时,`prompt_captured` 已经发出去了;端到端层——
   跑一个 AGENT phase,事件序列里 `prompt_captured` 出现在 `llm_call` 之前
   (`tests/core/test_llm_call_announces_its_start.py`)。只测"事件类型存在"
   会漏掉这次的缺陷:事件类型一直都在,缺的是它出现的**时机和路径**。

## 7. 涉及 region / platform
engine 全权;trace 被 studio trace-inspector 消费(前端挂载归 studio)。

## 8. gaps / 待设计(设计已定,实现归 kiro;reducer-diff 见 OB5)
1. **V4 trace 增补(目标事件,impl 归 kiro)**:
   - **微观拓扑事件 = 已落地(2026-08-08)**:agent 节点(`graph_assembler._build_skill_node`)发出的 `LLMCallEvent`/`ToolCallEvent` 现在带 `parent_node_id`(=该 agent phase_id)+ `node_type="agent"`,并同时补齐两件同源事实:①`LLMCallEvent.resolved_model` = provider 在响应上报的实际模型(fallback chain 决定的模型只有逐次调用才为真);②该节点的 token 经 `callbacks/token_accounting.account_llm_call` 折进 `flow.metrics`——与 legacy LLM phase node 的 `_HarnessCallbackBridge` 共用同一条累计规则,两条路径不会对"这次 run 花了多少"给出不同答案。(修复前:agent 路径逐次 llm_call 有 token 但 `metrics.json` 恒为 0,且全 trace 无模型名。)
   - **run 级 token 汇总 = 已落地(2026-08-08)**:`flow.metrics` 是本次 run 花费的唯一累计处,`runner._run_metrics_from_graph_result` 把跑完的图状态投影成 run 的 metrics(wall time 由 runner 自己测量后叠加),`metrics.json` 因此报告真实 token。(修复前:`_run_v030_skill_dict` 无论两条 phase 路径累计了什么,都只返回 `{"wall_time_sec": ...}`,`metrics.json` 的 token 字段结构性恒为 0——实测 2026-08-08 exp-b-round7 run `2026-08-08T12-53-23_f90d8d60`:11 次 llm_call 合计 120073 input token,`metrics.json` 仍写 `total_tokens: 0`。)
   - **3 个边操作事件**(`BlackboardReduceEvent` 输出并入黑板 / `InputDispatchEvent` 输入按 io.inputs 切片喂节点·**并联各一条** / `InputFileInjectedEvent` 文件注入)+ 已有 `ArtifactSavedEvent`/`CompactionEvent` 同归"边操作"族,前端点 dot 按 `from_phase`/`to_phase`(edge)聚合该族 + 黑板快照(OB4,机制落点 `graph-exec`,双向;源 11-io E5)。
     - **字段草案(studio 消费契约,2026-06-06 定;impl 归 kiro 时按此建类)** —— 三者共享(继承 `_EventBase` 的 `event_type`/`run_id`/`thread_id`/`seq`/`ts`)+ edge 聚合字段:
       - **共有**:`from_phase: str | None`(源节点 id;图入口为 `None`)· `to_phase: str`(目标节点 id)· `changed_keys: list[str]`(本次操作触及的黑板 key)· `blackboard_snapshot: dict[str, Any]`(操作后黑板快照,供 OB5 前端按 phase 边界近似 reducer-diff)。事件类型本身 = 操作类型(判别字段 `event_type`,无需另设 `op`)。
       - **`BlackboardReduceEvent` 专有**:`reducer: str`(reducer 名/策略,取自 `iterate.accumulate.merge` 声明,如 `merge`/`append`/`override`;**声明式元数据,非引擎算的 authoritative diff**——逐 reducer 前后态 diff = 前端近似 OB5)。
       - **`InputDispatchEvent` 专有**:`dispatched_keys: list[str]`(按 `io.inputs` 切给该节点的 key)· `branch_index: int | None`(并联/iterate 扇出时的分支/item 序号,让前端把并联分发画成各自的边;非并联为 `None`)。
       - **`InputFileInjectedEvent` 专有**:`file_ref: str`(注入文件路径/ref)· `target_field: str`(文件内容注入到的黑板字段名)。
   - **Prompt 三视图 = 已满足**(2026-06-06 核实):`PromptCapturedEvent`(`events.py:217`)已同时带 `template_source`(模板)+ `variables`(喂入变量)+ `resolved_prompt`(渲染后)三视图——无需补(06 #7 待办关闭)。
2. **subagent lifecycle 事件(A2)**:builtin subagent 已有 `BuiltinSubagentEnter/Exit/FallbackEvent`(`events.py:178/188/198`);**用户 subagent** 的 lifecycle 事件待补(与 `07-subagent` 协同,impl 归 kiro)。
3. **reducer 前后态 diff(REQ-7)= 前端近似(OB5)**:OB4 边操作事件已带黑板快照,前端按 phase 边界(`PhaseStart`/`PhaseEnd` + 边操作族)近似"哪个 reducer 改了哪个 key";engine-authoritative 逐 reducer diff 事件 = deferred enhancement,**不在 mvp1 engine 范围**(PM 2026-06-06 选 A)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `02-middleware`(Tracing 槽,双向)· `07-subagent`(lifecycle)· `03-api-contract`(事件协议)· `data-contracts`
