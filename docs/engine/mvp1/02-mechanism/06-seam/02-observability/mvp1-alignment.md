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
外层 phase 事件 + 内层**微观事件**(带 `parent_node_id` 挂回外层节点)。内层发射器有两个,各自贴着它报告的那件事(OB6):**Tracing 中间件**套在工具执行外面,发 `tool_call_started`/`tool_call`(**实现在 `02-middleware` 槽 4,逻辑归本域**,双向引用);**chat model** 在 `_generate` 内部发一次往返的**两半**——请求 provider **之前**发 `prompt_captured`,拿到回答**当场**发 `llm_call`。两半同一个 owner,所以事件序列在一个 phase 内严格交替(开始、结束、下一个开始),不会出现"开始堆在前面、结束攒在 phase 末尾"。有些事件**内嵌内容快照**(`LLMCallEvent.response_data`、`CompactionEvent.content_ref`)= 为 trace 复制,不拥有消息状态;prompt 只随开始那半走一次(`PromptCapturedEvent.resolved_prompt`),`LLMCallEvent.messages` 恒为 `None`——同一份 prompt 在一次 trace 里不复制两遍。

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
| OB6 | **一步的开始和结束,都由执行这一步的那个单元自己发**,不由包在某类调用方外面的装饰器发、也不由事后读消息列表的人补发。LLM 往返的两半都发自 chat model 内部(`LLMProviderChatModel._generate` / `PredictGatewayChatModel._generate`):请求 provider **之前**发 `prompt_captured`,拿到回答**当场**发 `llm_call`;工具调用的开始事件 `tool_call_started` 发自 Tracing 中间件(它就套在工具执行外面) | 两个失效模式,同一个病根。①**装饰器**只对"以它预期的方式调用模型"的调用方生效:旧实现 `TracingClientProxy` 拦 `.invoke()`,只有 LLM phase 节点那样调;AGENT phase 把模型交给 `create_agent`,LangChain 走 `_generate`,于是**耗时最长的那条路一个开始信号都没有**——一次 5 分钟的 phase 在 UI 上全程空白(实测 2026-08-09)。②**事后读消息列表**的人只能在 phase 跑完后一次性补发所有 `llm_call`,于是这个 phase 开出去的每一步都要等到 phase 结束才关得上:一次 162 秒的 run 报成功之后,trace 里仍有 5 步在转圈(实测 2026-08-09,修复前)。放到调用点后,新增节点类型不可能漏发、没有能被绕过的包装层、开始与结束也不可能来自两个不同的 owner。代价:模型多背 `sub_run_id`/`group_key`/`parent_node_id`/`node_type` 四个只用于上报的字段 |
| OB8 | **做决定的报每一次决定,只做断言的只报断言失败**:一个组件的输出会改变后续控制流,它就是决定者,每一次决定都发事件(`ExitControlMiddleware` 的五个退出决策 → `AgentExitDecisionEvent`);不改变控制流的检查是断言,只在失败时发(`ProtocolValidationMiddleware` → `ProtocolViolationEvent`) | 引擎其实一直把这些句子写出来了,只是写成 `logger.info` —— 而循环最常见的结局(提交被接受、阶段正常结束)因此对每一个运行的读者都不存在(实测:真实 8 阶段 run 里,结束了 4 个阶段的那个组件贡献 0 条事件)。反过来,给「每次都通过」的断言加事件只会把 trace 淹掉:一个阶段每次模型调用要断言两次 |
| OB7 | **调用方自带的 chat model(`run_skill(mock_llm=...)`)从 Port 进,不从 model 层进**——`ChatModelProvider` 把它适配成 `LLMProvider`,仍由 `LLMProviderChatModel` 驱动 | OB6 把上报责任放在"引擎自己写的 model"身上,那么引擎驱动的每个 model 都必须是这一种,否则外来 model 跑的 run 单纯因为"不是我们写的"而失去全部 `llm_call`(实测:改动后 5 个断言 llm_call 的用例直接失灵)。外来 chat model 本质就是"另一种回答方式"= provider 变体,按稳定依赖原则它归 Adapter 层。副产品:`_resolve_phase_chat_model` 里那条平行的 `chat_model` 分支删掉,phase 之上只剩一种 model、一个 reporter、一套事件 |
| OB9 | **一次 run 里的每一条事件都要说清自己发生在哪个子图里——包括不是引擎造的那些。**网关不依赖引擎,所以它自己造 `llm_route_decision` / `llm_call_settings` 两种事件,而引擎从前把回调清单**原样**交给它:于是这两种是全程唯一绕过 `_safe_emit_event` 的事件,也就是唯一学不到 `subgraph_path` 的事件。修法是在交界处**由引擎把它们复述成引擎自己的事件**(`_GatewayEventSink`),再从引擎自己的出口发出去。**不是**给网关的事件加一个 `subgraph_path` 字段——「图会嵌套」是引擎的概念,往网关里塞它就是把上层概念漏进底座 | 实测 run `2026-08-20T10-27-18_a98f6ba5`:这两种事件是该 run trace 里仅有的 `subgraph_path: null`,同一个阶段的其它事件都写着 `segmentation`。于是 run 报告把**同一个阶段记成了两个节点**——`segmentation/segment` 带着它真实的执行,外加一个跑了 `0×` 的幽灵 `segment` 行。这与 `_EventBase.subgraph_path` 字段注释里记的run `2026-08-19T01-56-15_d0733362` 是同一个病根的第二次发作:**裸阶段名不是身份**。顺带把引擎早就声明、却从来没有人构造过的那两个类(它们一直列在 `CallbackEvent` 联合里)变成真的 |
| OB10 | **一次 run 花了多少,由它报告过的调用累加得出,不从跑完的图状态里读。**token 计数退出 `flow`:`runner._prepare_v030_event_sink` 挂一个 run 作用域的 `_RunSpendLedger` 累加每一条 `LLMCallEvent`,`_run_metrics_from_graph_result` 读它。旧路整条删除(`token_accounting.account_llm_call`/`fold_spend`/`spend_of`、`graph_assembler` 读消息列表折账那段、`_SpendHarvest`/`_accounting_from_zero`、`FrameworkState.metrics`、`ExecutionControlMiddleware.collect_metrics`),不留第二份账 | 把账记在图状态里,就得回答"N 个并联分支各写一次、通道只留一个,怎么合并"——而分支写进去的是「继承的基数 + 自己的花费」,这种值合并起来只有覆盖(漏账)或相加(基数被数 N 遍)两条死路。实测 run `2026-08-20T11-30-38_df572662` 少算 169737(22.9%);离线三分支扇出只活下来一条(55/35 → 33/21)。计数放到**调用发生的那一刻**之后,并联、iterate、子图、子代理、`finish_task` 的 md-patch 修复调用一律自动计入——尤其最后一个:它直接 `chat_model.invoke(...)`,压根不经过任何阶段节点的返回值,任何"记得写通道"式的方案都覆盖不到它。借的是 OpenTelemetry/Prometheus 的观测纪律(计数在被观测的操作里发生);拒绝的是继续在图状态里做 G-Counter。代价:`resume` 后只统计续跑那一段——与 `trace.jsonl` 被清空重写(`emit.py:24`)后 `report.md` 的口径一致,两者说同一句话比各说各话重要 |
| OB11 | **阶段的花费不写在阶段事件上,由它发出的调用相加得出。**`PhaseEndEvent.metrics` 删除 —— 连同 `TracingCallback` 里把它转写进 trace 载荷的那一行、`PredictTracingCallback` 那条「把 metrics 清零再传下去」的路径、以及 `LoggingCallback` 那句永远打印 `metrics={}` 的日志。一个阶段花了多少,答案是它发出的那些 `LLMCallEvent` 之和 —— 这正是 `run_report._account_nodes` 逐节点 `tokens in/out` 那一列的算法,也是 `TracingCallback` 自己在 `_record_llm_call` 里累加的 `phase["input_tokens"]` | 这个字段**从声明的那天起就没有被填过一次**:全仓唯一构造 `PhaseEndEvent` 的地方(`graph_assembler`)从不传它。实测真机 run `2026-08-20T13-14-59_14582c6b`:42 条 `phase_end`,42 条 `metrics={}`,其中包括真调过 4 次模型的阶段。**一个永远为空的声明字段不是「还没填」,是一句谎话**——读者无法从类型上分辨「这个阶段没花钱」和「没人填这个字段」,而类型说的是前者。两条修法里选删除而不是填上,理由与 OB10 同源:填上就等于让同一个问题有第二个答案,而 OB10 前一天刚把这种结构从 run 级总账里拆掉,填这里等于让它在下一层原样长回来。**留下的缺口另记**:`LLMCallEvent` 不带执行 id,所以「这次调用属于该阶段的**哪一次**执行」目前由报告按「此刻哪个执行开着」推断;实测同一个 run 里 `aggregate`/`extrac`/`settings` 三个阶段各有两次执行同时开着,4 次调用落在这种时刻(台账 E15) |
| OB12 | **每一条事件都说清自己发生在哪一次阶段执行里。**`_EventBase` 增 `phase_execution_id`(`PhaseStartEvent`/`PhaseEndEvent` 收窄为必填 —— 开合执行的那两条不能对「开的是哪一次」含糊),由 `_safe_emit_event` 从 `wrap_edge_transition` 维持的作用域统一盖章,和 `subgraph_path` 同一处、同一套写法。宿主侧 `run_report._account_nodes` 改为按事件自报的执行 id 记账,只在事件没自报时才回落到「当前开着的那一个」 | `llm_call` 从前不带执行 id,于是报告只能按顺序推断归属,并且**它自己的注释把这个前提写明了**:「an `llm_call` carries no execution id of its own, and the trace is ordered」。**扇出让这个前提不成立**:实测 run `2026-08-20T13-14-59_14582c6b`,`aggregate`/`extrac`/`settings` 三个阶段各有**两次执行同时开着**,全 run **4 次**调用正好落在这种窗口里,记在谁头上取决于谁最后开的。离线复现更露骨:两次执行交错、各发一次调用,报告把**两次调用都记在第二次执行**上,还凭空多算出第三次执行(`phase_end` 弹错了栈)。**这是 OB10 同一个错误前提的下一层**:那里是「跑完回头读状态」重建总账,这里是「按位置推断」重建归属 —— 都在让读者复原生产者本来就知道的事实。盖章而不是逐个 emitter 传参,理由同 OB6/OB9:**要求每个 emitter 记得传的字段,迟早有一个 emitter 忘记**;而作用域本来就存在 —— 执行 id 是 `wrap_edge_transition` 为了给迁移命名目的地时铸出来的,`PhaseStartEvent` 用的就是它,一次铸造一个 id |
| OB13 | **一次阶段执行结束时,要说清它是怎么结束的,而不只是说它结束了。**`PhaseEndEvent` 增必填 `status`(`completed` / `failed`),取名和取值都与 `RunEndedEvent.status` 一致 —— 阶段报告自己的结局与 run 报告自己的结局是同一种句子,另起一个名字只会让每个读者先学会区别才敢相信任何一个。**阶段生命周期同时从被包节点的外面搬进 `PhaseWrapper` 内部**(`state_mapper`,由宿主注入 `PhaseLifecycle`,`graph_assembler._PhaseEventLifecycle` 实现):判定成败的那一步 —— `wrap_phase_output` 里跑的输出 validator —— 本来就在 wrapper 里,生命周期套在外面就必然在 `phase_end` 已经发出去之后才跑。宿主侧 `run_report._Execution.reported_failed` 读它;画布侧一行不改 —— `run-status-projection` 早就写着「事件自报的 status 一律相信」 | 实测 run `2026-08-20T15-44-03_98726d7c`:阶段 `impossible` 的 validator 拒绝了提交,run 以 `[F-v3-agent-validator-failed]` 崩掉,而**该阶段自己发出的每一条事件都读起来像成功** —— `finish_task` verdict=`accepted`、exit decision=`exit_success`、`phase_end` 不带任何结果。于是画布把杀死这次 run 的那个节点画成 **Success**,run 报告给它 **ok**,全 run 唯一的失败信号是 run 级 `run_ended status=crashed`。**两个读者都没读错**:它们读的那条事件确实什么都没说(台账 E17)。这是 OB11 的另一面 —— 那里删掉一个从没被填过的字段(类型说「这个阶段没花钱」,真相是「没人填」),这里补上一个从来不存在的字段(类型只说「它结束了」,而读者要问的是「怎么结束的」);判据同样是**让非法状态不可表示**:必填,于是「结束了但没说怎么结束」写不出来。选择搬生命周期、而不是在 validator 失败处补发一条事件,理由与 OB6 同源:**一步的成败由执行这一步的那个单元自己报**,在别处补发等于让第二个 owner 去描述它没有执行的事。代价:`PhaseWrapper` 多一个可选依赖(注入的 lifecycle);builtin reference reader 那条本来就不上报的路径保持不上报。**当时留下的缺口**:阶段输入构建失败(必填输入缺失)时执行根本没有开过,于是 `phase_start`/`phase_end` 一条都没有,画布上那个节点停在 idle —— 已由 **OB14** 收口 |
| OB14 | **阶段取自己声明的输入,是这次执行的第一步,不是它有没有资格存在的前提。**`StateMapper.build_phase_input` 一个方法做了两件事:把黑板投影成这个阶段声明要的那份切片,以及判断切片够不够跑。拆成 `select_declared_inputs`(纯投影,永不拒绝)和 `require_declared_inputs`(输入契约,缺必填就以 `[F-v3-runtime-state-mapping-failed]` 致命退出)。**报告这个阶段收到了什么**的那条路径(`_emit_input_dispatch` 造 `InputDispatchEvent`)从此只调投影;契约检查搬进 `PhaseWrapper`、放在 `lifecycle.opened` **之后** —— 于是输入拿不到的阶段照样发 `phase_start` + `phase_end(status="failed")`,画布画它失败、报告有它这一行 | 这是 OB13 的镜像:那边确立「跑输出 validator 是这次执行的最后一步,所以 validator 拒绝= 这次执行失败」,这边确立「取输入是它的第一步,所以取不到 = 这次执行失败」。两边都在回答同一个问题 —— **哪些步骤算在这次执行里面** —— 而把某一步挪到执行外面,结果一定是那一步失败时没有任何事件说得出话。**病根有两处,缺一不可**:① 契约检查跑在生命周期开启之前;② 更早的一处 —— `_emit_input_dispatch` 调的是那个融合方法,而它在 wrapper **之前**执行,所以真正先杀死 run 的是**报告路径**,「报告一件事」不该顺带「否决这件事」。离线夹具实证(`missing-input-fixture`:上游把 `note` 声明为可选输出却从不写,下游把 `note` 声明为必填输入 —— 编译干净通过,只在运行时崩):修前 `second` 的事件是 `edge_start → edge_end → run_ended`,**连 `input_dispatch` 都没有**,一条事件都不提这个阶段;修后是 `edge_start → input_dispatch → edge_end → phase_start → phase_end(failed)`,事件顺序一格没动。**边界照实说**:投影本身若抛错(黑板 `flow` 结构损坏一类)仍然什么都不发 —— 那是「状态本身坏了」,不是「这个阶段失败了」,不在本条范围内(台账 E18) |
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
5. **OB6:结束事件必须在这一次调用返回时发,不能等 phase 结束。** 判据是
   **严格交替**——跑一个会调多次模型的 AGENT phase,`prompt_captured`/`llm_call`
   必须成对相间(开始、结束、下一个开始),且 `phase_end` 之前两者计数相等
   (`tests/core/test_llm_step_closes_when_the_call_returns.py`)。只断言
   "两种事件都出现过"会漏掉这次的缺陷:两种都在,错的是全部结束都挤在末尾,
   于是每一步在 UI 上都关不上。
6. **OB7:调用方自带的 model 与引擎自己的 model 产出同一套事件。**
   用一个只会返回固定回答、且 `invoke` 不接任何多余 kwarg 的 chat model 走
   `ChatModelProvider`,事件序列同样是 `prompt_captured` → `llm_call`(同上文件)。

7. **OB9:网关造的事件也要带子图作用域。** 单元层钉一条:把一个网关形状的
   `llm_route_decision`(用桩对象写出它的 `model_dump`,**不 import 网关**——引擎不依赖它,
   这正是同一份契约要写两遍的原因)投进 `_GatewayEventSink`,在 `active_subgraph_path`
   有值时收到的必须是引擎自己的 `LLMRouteDecisionEvent` 且 `subgraph_path` 已填
   (`tests/callbacks/test_an_event_names_its_subgraph.py`)。同一处再钉两条边界:根层发出的
   作用域是 `None` 而不是空串;引擎没有对应类的网关事件**照原样送达**——不带作用域比凭空消失好,
   一种新网关事件类型悄悄从所有 trace 里蒸发要等很久才会有人发现。

8. **OB13:阶段结束时要说清成败,validator 算在里面。** 两条钉在同一个 fixture 的两种形态上:
   干净跑通的阶段 `phase_end.status == "completed"`;validator 一律拒绝的阶段
   `phase_end.status == "failed"`,而且**仍然有** `phase_end`(阶段开了不关,
   节点在画布上永远转圈)。`tests/core/test_a_phase_says_how_it_ended.py`。
   只断言"这次 run 失败了"会漏掉这次的缺陷:run 级从一开始就说了自己崩了,缺的是阶段级。

9. **OB14:输入拿不到的阶段也要开合执行。** 夹具 `missing-input-fixture` 让上游把 `note` 声明为可选输出而从不写、下游把 `note` 声明为必填输入,跑一次:下游阶段既有 `phase_start` 也有 `phase_end.status == "failed"`,两者的 `phase_execution_id` 相同。`tests/core/test_a_phase_that_never_got_its_input.py`。同一份文件里钉住第二条:上游阶段仍然 `completed` —— 否则夹具可能在上游就崩了,而断言照样是绿的。单元层再钉一条(`tests/runtime/test_state_mapper.py`):`select_declared_inputs` 面对缺失的必填字段**不许抛**,那是 `require_declared_inputs` 的事 —— 这一条是防止有人把两半重新焊回去。
   宿主侧另钉一条:`phase_end` 说 failed 的节点在 run 报告里不是 `ok`
   (`apps/studio/backend/tests/services/test_the_report_believes_a_phase_that_failed.py`)。

## 7. 涉及 region / platform
engine 全权;trace 被 studio trace-inspector 消费(前端挂载归 studio)。

## 8. gaps / 待设计(设计已定,实现归 kiro;reducer-diff 见 OB5)
1. **V4 trace 增补(目标事件,impl 归 kiro)**:
   - **微观拓扑事件 = 已落地(2026-08-08;2026-08-09 按 OB6 换发射点)**:一个 agent phase 的 `LLMCallEvent`/`ToolCallEvent` 带 `parent_node_id`(=该 agent phase_id)+ `node_type="agent"`,并带 `resolved_model` = provider 在响应上报的实际模型(fallback chain 决定的模型只有逐次调用才为真)。**`LLMCallEvent` 现在发自 chat model**(node 归属由构建 model 的 `_resolve_phase_chat_model` 交给它),`ToolCallEvent` 仍由 agent 节点事后读消息列表补发(那些调用返回时确实没人在场,所以按"已经结束"上报、不编造开始时刻)。**「token 累计与事件上报分家」这条 2026-08-08 的安排已于 2026-08-20 撤销(OB10)**:当时让 agent 节点读消息列表、把 token 折进 `flow.metrics`,理由是"metrics 是 phase 拥有的状态,model 不碰";实际后果是**同一个问题有了两个答案**,而事后读消息列表的那个答案漏掉了所有不往消息列表里追加的调用。现在 token 只在事件上报的那一刻累加一次,详见下面第 4 条。读 usage 的那段逻辑仍收敛在 `token_accounting.token_usage_of` 一处。(修复前:agent 路径逐次 llm_call 有 token 但 `metrics.json` 恒为 0,且全 trace 无模型名。)
   - **run 级 token 汇总 = 已落地(2026-08-08;累计处已于 2026-08-20 换掉,见下面第 4 条)**:`metrics.json` 从此报告真实 token,不再结构性恒为 0。(修复前:`_run_v030_skill_dict` 无论两条 phase 路径累计了什么,都只返回 `{"wall_time_sec": ...}`,`metrics.json` 的 token 字段结构性恒为 0——实测 2026-08-08 exp-b-round7 run `2026-08-08T12-53-23_f90d8d60`:11 次 llm_call 合计 120073 input token,`metrics.json` 仍写 `total_tokens: 0`。)**当天写下的「`flow.metrics` 是本次 run 花费的唯一累计处」这句话已作废**:图状态从来就不是唯一累计处,只是当时唯一被读的那一处;下面第 4 条把累计处整个搬走了。
   - **迭代下的花费同样计入 = 已落地(2026-08-20)**:`iterate`(batch / loop,阶段级与图级共四条路径)把每个 item / 每一轮跑在一个**子状态**上,跑完把子状态整个丢掉——阶段级换成 `_phase_outputs_delta` 的通道增量,图级换回原始 state。子状态里记着的东西,只要幸存者不带,就没了:`phase_execution_ids` 当初已经被手工牵出来过一次,**token 花费是掉进同一个洞的第二样东西**。因此 2026-08-08 那条「`flow.metrics` 是唯一累计处」的结论,在 iterate 之下**从来没有成立过**——实测普通 run `2026-08-19T05-21-45`:trace 里 84 次调用合计 687613/98592,`metrics.json` 写 0/0/0;`2026-08-19T06-22` 那次报的 147414/21323 恰好等于全图**唯一三个不在 iterate 下**的阶段之和。
     **修法(取舍写明)**:计数器只能靠**相加**合并,所以每个 item / 每一轮的账**从零起算**(`_accounting_from_zero`),它报回来的就是**它自己花了多少**;父层把这些增量加进自己的那一份(`_SpendHarvest`)。借的是 G-Counter 的纪律——每个 worker 只报自己的增量、合并即加法,LangGraph 自己的 `Annotated[int, operator.add]` 通道与 Prometheus counter 同理;**没借它的通道本身**,因为一个 batch item 是被当作普通函数调用跑起来的,压根不写通道。拒绝的另一条路是「让子状态继承 run 的累计总数、回来再取差」:N 个兄弟各自继承同一个基数,相加会把基数数 N 遍。
     **不变量与门禁**:一次 run 报出的花费,必须等于**它自己报告过的那些调用**之和(`tests/core/test_iterate_token_accounting.py::_assert_totals_match_the_calls`)。这样写而不是钉死一个数字,是为了让没人写过夹具的拓扑也被它挡住。这条不变量同时**关掉了 `report.md` 与 `metrics.json` 打架的可能**:前者按定义就是 trace 里 `llm_call` 事件之和(`apps/studio/backend/app/services/run_report.py:200-202`),后者是 `result.metrics`(`core/runner.py:1980`),不变量成立即两者相等。(打架实测:同一个 run 目录 `2026-08-19T06-58-15_179d1440`,`report.md` 写 27009,`metrics.json` 写 0。)
     **这条不变量当时并没有真正成立**——它只被 iterate 的两个夹具执行,而不变量本身覆盖的是"任何拓扑";并联扇出这条拓扑没人写夹具,于是照旧漏账。见下面第 4 条。
   - **一次 run 花了多少 = 它报告过的那些调用之和,不是图状态里剩下的那份账(2026-08-20 裁决 OB10)**:
     **实测**:装着 iterate 修复的 vendor 跑出来的 run `2026-08-20T11-30-38_df572662`,`report.md` 写 `626900/114065/740965`,同目录 `metrics.json` 写 `474586/96642/571228`——**同一次 run,同一块屏,少算 169737(22.9%)**。离线复现只要三个并联阶段:trace 报 5 次调用 55/35,`metrics` 报 33/21,**三条分支只活下来一条**。
     **根因**:每个阶段把账写成「它继承到的基数 + 它自己花的」再塞进 `flow` 通道,而 `flow` 是**保留最后一个写入者**的通道。并联的 N 个阶段在同一个超步里各写一次,通道只留一份,另外 N-1 份连同它们自己的花费一起消失。这不是 iterate 那个洞的复发,是**同一条错误前提的第二种表现**:凡是把"继承来的总数"当作账本内容往下传,合并方式就只剩覆盖或双计,没有第三种。
     **裁决(取舍写明)**:token 计数**退出图状态**。一次 run 花了多少,由**它报告过的 `LLMCallEvent`** 累加得出——`runner._prepare_v030_event_sink` 里挂一个 run 作用域的 `_RunSpendLedger`,`_run_metrics_from_graph_result` 读它。理由是这条路**在物理上不可能漏**:计数发生在调用发生的那一刻,而不是事后回头读"活下来的那份状态";于是并联、iterate、子图、子代理、`finish_task` 的 md-patch 修复调用、以及任何将来直接 `chat_model.invoke(...)` 而不往消息列表里追加的调用者,一律自动计入,不需要谁预先想到它。
     **借了什么、拒了什么**:借的是 OpenTelemetry / Prometheus 的观测纪律——**计数在被观测的操作里发生,不在事后的状态快照里重建**;拒绝的是继续在图状态里做 G-Counter(给 `flow.metrics` 单独开一条带 `operator.add` reducer 的通道)。后者能修好并联这一处,却仍然要求"每一个可能花钱的路径都记得写通道",而 md-patch 那次修复调用就是没写通道的反例——它压根不经过任何阶段节点的返回值。**同时删掉旧路**(不向后兼容):`callbacks/token_accounting`(`account_llm_call`/`fold_spend`/`spend_of`)、`graph_assembler` 里读消息列表折账那段与 `_SpendHarvest`/`_accounting_from_zero`、`FrameworkState.metrics`、以及只服务于它的 `ExecutionControlMiddleware.collect_metrics`(无生产调用方)全部移除,不留第二份账。
     **代价**:`resume` 之后 `metrics.json` 只统计续跑那一段。这是**刻意接受**的,因为 `_TraceJsonlSink.__init__` 本来就把 `trace.jsonl` 清空重写(`callbacks/emit.py:24`),`report.md` 早就只统计续跑那一段;两者口径一致比两者各说各话更重要。要让它统计整次 run,得先让 trace 跨 resume 追加——那是另一件事,不在这条裁决里。
     **不变量与门禁**:同上一条,并新增并联扇出的夹具(`tests/core/test_parallel_token_accounting.py`)。三个夹具(batch / loop / 并联)现在共用同一条断言。
   - **3 个边操作事件**(`BlackboardReduceEvent` 输出并入黑板 / `InputDispatchEvent` 输入按 io.inputs 切片喂节点·**并联各一条** / `InputFileInjectedEvent` 文件注入)+ 已有 `ArtifactSavedEvent`/`CompactionEvent` 同归"边操作"族,前端点 dot 按 `from_phase`/`to_phase`(edge)聚合该族 + 黑板快照(OB4,机制落点 `graph-exec`,双向;源 11-io E5)。
     - **字段草案(studio 消费契约,2026-06-06 定;impl 归 kiro 时按此建类)** —— 三者共享(继承 `_EventBase` 的 `event_type`/`run_id`/`thread_id`/`seq`/`ts`)+ edge 聚合字段:
       - **共有**:`from_phase: str | None`(源节点 id;图入口为 `None`)· `to_phase: str`(目标节点 id)· `changed_keys: list[str]`(本次操作触及的黑板 key)· `blackboard_snapshot: dict[str, Any]`(操作后黑板快照,供 OB5 前端按 phase 边界近似 reducer-diff)。事件类型本身 = 操作类型(判别字段 `event_type`,无需另设 `op`)。
       - **`BlackboardReduceEvent` 专有**:`reducer: str`(reducer 名/策略,取自 `iterate.accumulate.merge` 声明,如 `merge`/`append`/`override`;**声明式元数据,非引擎算的 authoritative diff**——逐 reducer 前后态 diff = 前端近似 OB5)。
       - **`InputDispatchEvent` 专有**:`dispatched_keys: list[str]`(按 `io.inputs` 切给该节点的 key)· `branch_index: int | None`(并联/iterate 扇出时的分支/item 序号,让前端把并联分发画成各自的边;非并联为 `None`)。
       - **`InputFileInjectedEvent` 专有**:`file_ref: str`(注入文件路径/ref)· `target_field: str`(文件内容注入到的黑板字段名)。
   - **Prompt 三视图 = 已满足**(2026-06-06 核实):`PromptCapturedEvent`(`events.py:217`)已同时带 `template_source`(模板)+ `variables`(喂入变量)+ `resolved_prompt`(渲染后)三视图——无需补(06 #7 待办关闭)。
2. **做决定的报每一次决定,只做断言的只报断言失败(OB8,2026-08-20 落地)**:
   `ExitControlMiddleware` 是决定"这个 agent 阶段继续还是停下"的那个闸,它有五个答案,
   其中四个**只写成 `logger.info(...)`**——也就是写在运行的读者永远不会看的地方。后果是
   循环**最常见的那个结局也最看不见**:一个阶段因为提交被接受而正常结束,trace 里只看到
   `finish_task`、verdict、`phase_end`,没有任何一行说"闸同意了"。实测 2026-08-20 的真实
   8 阶段 run(`.workspace/runs/2026-08-19T06-58-15_179d1440/trace.jsonl`):77 条事件、
   4 个 agent 阶段,来自结束了这四个阶段的那个组件的事件数为 **0**。这正是 E4「只给结果
   不给过程」最字面的形态——引擎其实**已经把这些句子写出来了**,只是写成了 print 级日志。
   **裁决**:新增 `AgentExitDecisionEvent`(`agent_exit_decision`),闸的**每一个**答案都发,
   取值是封闭集合 `exit_success` / `continue_tool_work` / `continue_nudged` / `continue_open`
   ——封闭是为了让"读者遇到一个没有读法的决定"在类型层就不可表示。**五个决策点全覆盖**,
   包括挂在 `after_model` 的 planning gate:它在 `after_agent` 还没轮到之前就把循环打回去,
   同样是一次决定(写这条测试时实测发现的,原本以为只有四个)。
   **与 `NudgeEvent` 并存不重复**:nudge 带的是**对模型说了什么**,决定事件带的是**闸对此做了什么**。
   **边界(这条规则的另一半)**:`ProtocolValidationMiddleware` 只做断言——它通过时什么都不改变,
   而且每次模型调用要跑两次,给它加"检查通过"事件是纯噪声。所以它维持只在失败时发
   `ProtocolViolationEvent`。判据不是"重不重要",是**这个组件的输出会不会改变后续控制流**:
   会,就是决定,每次都报;不会,就是断言,只报失败。
   门禁:`tests/callbacks/test_a_turn_says_why_it_ended.py`(正常结束的阶段必须自己说出来、
   决定必须早于它结束的那个 `phase_end`、被 nudge 的一轮报"继续"而不是"结束")。

3. **观察者必须在决策者外面(2026-08-20 落地)**:`ToolCallStartedEvent` 从 2026-06 就
   定义好、导出、镜像进前端事件表、被 `TraceStepRow` 消费,却**只对 skill 自带工具生效**;
   `finish_task` / `update_working_memory` / `ask_clarification` 这些框架工具一次都没被宣告过
   ——而它们才是一个 agent 阶段大部分时间在调的东西。
   **根因是顺序,不是少了发射点**:`CognitiveFlowMiddleware` 排在 `TracingMiddleware` 前面,
   而它对自己拦下的工具**直接作答、不调 `handler(request)`**,于是包括观察者在内的整条
   wrapper 链被跳过。实测 2026-08-20:一个先调 `update_working_memory` 再调 `finish_task`
   的阶段产出 2 条 `tool_call`、0 条 `tool_call_started`,给
   `TracingMiddleware.wrap_tool_call` / `awrap_tool_call` 各挂一个探针,两边都是 0 次调用。
   **裁决**:`MVP0_MIDDLEWARE_ORDER_CONTRACT` 把 `Tracing` 放到**第 1 位**。一个能被决策者
   跳过的观察者,观察的不是这个系统,而是别人的控制流剩给它的那个子集。借的是 Django
   `MIDDLEWARE` 与 Express `app.use` 的既有约定——日志/追踪层注册在最外面,所以下层 auth
   短路掉的请求它照样看得见;**没借**它们的「响应也逐层回穿」那部分,因为这里的 wrapper
   是一次性 handler 链,不需要。移动的代价为零:Tracing 只实现工具钩子,所以
   ProtocolValidation 依旧排在每一个**读状态**的中间件之前。
   **配套的去重**:观察者一旦生效,以 `ToolMessage` 作答的调用由它 close,而 agent 节点
   事后扫消息列表本来就是为了兜住那些以 `Command` 作答、永远不 close 的调用——两边同时在,
   同一次调用会被报两遍。所以「报告这次调用」的含义收紧为「除非已经报过」,这份记忆归
   阶段那**唯一一个** `StepReporter`(`tracing/steps.py`)。
   门禁:`tests/callbacks/test_a_tool_is_announced_when_it_starts.py`(每次调用先宣告后报告、
   每次调用只报告一次)、`tests/middleware/test_chain_topology.py`(Tracing 排在每个会抢答的
   中间件之前;状态守卫仍排在每个读状态的中间件之前)。
3. **subagent lifecycle 事件(A2)**:builtin subagent 已有 `BuiltinSubagentEnter/Exit/FallbackEvent`(`events.py:178/188/198`);**用户 subagent** 的 lifecycle 事件待补(与 `07-subagent` 协同,impl 归 kiro)。
4. **reducer 前后态 diff(REQ-7)= 前端近似(OB5)**:OB4 边操作事件已带黑板快照,前端按 phase 边界(`PhaseStart`/`PhaseEnd` + 边操作族)近似"哪个 reducer 改了哪个 key";engine-authoritative 逐 reducer diff 事件 = deferred enhancement,**不在 mvp1 engine 范围**(PM 2026-06-06 选 A)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `02-middleware`(Tracing 槽,双向)· `07-subagent`(lifecycle)· `03-api-contract`(事件协议)· `data-contracts`
