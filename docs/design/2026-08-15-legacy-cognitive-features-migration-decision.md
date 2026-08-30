# Legacy 认知功能簇迁移决议:先迁移、后整族删

日期:2026-08-15 · 状态:已批准(授权链见 §0),待按 §4 的 PR 切分实施 · 性质:权威决议文档(决策 + 关键设计决定 + 验收判据)

路径约定:本文中不带仓库前缀的相对路径(如 `core/state.py`、`middleware/__init__.py`、`cognitive/memory.py`、`tools/builtin/clarification_tool.py`)均指引擎包 `packages/graph-agent` 源码树内的模块;跨包文件一律写仓库全路径。引用格式统一为 `文件路径:行号`。

---

## 0. 决策(含授权链)

本决议规定引擎(`packages/graph-agent`)内 legacy 认知功能簇的处置方针:**先把冻结在死家族里的七项真缺口功能迁移到当前活路径上,迁移完成并通过验证后,再把死家族整族删除。** 本文给出七项功能的逐项迁移设计(§3)、实施顺序与 PR(Pull Request,合并请求)切分(§4)、迁移完成后的整族删除范围(§5)与设计源同步义务(§6)。

授权链——以下为用户裁决原话,按日期排列;本决议的全部设计决定均可回溯到这条链:

1. **2026-08-14**:「那第三个东西都已经收编到中间件了，当然就删咯」——针对 ValidationPhaseNode 残迹路径的删除裁决;该裁决随后被下一条扩展:删除的前提是功能已被活路径收编。
2. **2026-08-15**:「先把第三类功能迁移到现在的活路径上才能整族删」——本决议的总方针:七项真缺口功能(§1.2 的第三类)必须先迁入活路径,死家族才允许整族删除。
3. **2026-08-15**:「baseline是反应代码现实的文档，不是设计文档，要搞清楚，mvp1才是设计文档但是也应该有很多已经过时了」——文档分类学裁决:设计单元目录里的 baseline.md 记录代码现实,mvp1-alignment.md 是设计文档但内容可能过时。§6 的设计源同步义务据此制定。
4. **2026-08-15**:「这些功能是我清晰的记得我一个一个研究过加上去的，但是加错了地方，你可以找到相关的session记录，找到我的决策」——要求迁移设计以用户当年的原始决策为依据,不得凭现状代码倒推设计意图。§1.7 的决策考古与 §3 各节的「出生档案」据此撰写。
5. **2026-08-15**(对迁移框架的确认):「确认额，大多数都是middleware吧」——确认七项功能迁移后的承载形态以中间件(middleware)为主。

---

## 1. 背景与证据基础

### 1.1 死家族:引擎 src 内一个封闭的 import 闭包

引擎源码树内存在一个 14 模块的封闭 import 闭包(以下称「死家族」):

- `core/graph_builder.py`、`core/phase_executor.py`、`core/phase_node.py`
- `core/phase_nodes/{__init__,base,llm_phase_node,code_phase_node,validation_phase_node,factory,_helpers}.py`(7 个模块)
- `core/retry_router.py`、`core/nudge_injector.py`、`core/callback_bridge.py`、`core/tool_wrapper.py`

外加附着在死家族上的孤儿模块:`cognitive/{finish,middlewares,memory,ambiguity}.py`、`tools/builtin/{context_access,clarification_tool}.py`。

证据:对引擎 src 全量 131 模块构建的 AST(Abstract Syntax Tree,抽象语法树)import 图证明,上述闭包在 src 内零外部引用者——除了闭包内部互相 import,没有任何活代码 import 它们。

### 1.2 三类功能处置

对死家族承载的全部功能逐项盘点后,处置分三类:

- **第一类(约 16 项)**:已被活路径的等价机制替代,不需要迁移。
- **第二类(3 项)**:设计上已取消——execute/validate 节点对、图级跨相重试(retry_target)、validator 失败后自动重试。
- **第三类(7 项)**:真缺口——设计仍然需要、但实现只存在于死家族里的功能。**本决议的对象即这 7 项**,逐项审理见 §3(其中 §3.1–§3.6 六项给出迁移设计,§3.7 一项经审理判定其信息面已被活事件面覆盖、不迁移)。

### 1.3 活路径定义

「活路径」指引擎当前实际执行的装配与运行链路:

- 装配入口:`graph_assembler.assemble_graph`(由 `loader.py:494` 调用,`runner.py:72` 消费其产物)。
- 执行形态:langchain 的 `create_agent` + 9 槽中间件链。其中 7 槽由顺序契约常量 `MVP0_MIDDLEWARE_ORDER_CONTRACT` 钉死(`middleware/__init__.py:59-67`:ProtocolValidation、CognitiveFlow、ExecutionControl、Tracing、ToolError、LoopDetection、ExitControl),另有 2 槽在 `graph_assembler.py:2043-2053` 前置(RuntimeInputMiddleware、ToolHistoryIntegrityMiddleware)。
- 全部中间件继承 langchain 官方 `AgentMiddleware` 基类(`middleware/factory.py:8-9`)。
- 挂载点:`graph_assembler.py:2061-2068` 的 `create_agent(tools=all_tools, middleware=middleware_chain, state_schema=WorkflowState)`。

### 1.4 框架工具现状

今天活路径实际挂载的框架工具(由引擎自身定义并挂载、供模型调用的工具)只有:finish_task、read_reference、read_example,外加动态生成的 critic 工具(`graph_assembler.py:1986`、`:2291-2313`、`:2626-2642`)。

ask_clarification、log_ambiguity、update_working_memory、query_working_memory、read_artifact 一个都没挂——这五个认知工具是本决议 §3.1–§3.4 的迁移对象。

### 1.5 状态模型

- `WorkflowState`:TypedDict,三个键 data/flow/messages(`core/state.py:226-237`)。
- `FrameworkState`:Pydantic 模型,`extra="forbid"`(`core/state.py:179-223`),挂在 `WorkflowState` 的 flow 键下。
- 其中 `FrameworkState.working_memory`(`state.py:210`)已被活路径**借用**:存 iterate 执行痕迹(`graph_assembler.py:961-977` 写 iterate_executions 键),并以 "scratch" 名义对外暴露(`graph_assembler.py:2354`)。
- `FrameworkState.ambiguity_reports`(`state.py:212`)在活路径上零写入。

### 1.6 ctx 桥判死

`state.py:294` 的 `legacy_context_from_state` 与 `state.py:352` 的 `workflow_state_from_legacy_context` 是历史迁移遗留的 T2 兼容层,负责在 legacy 上下文字典(下称 ctx)与 `WorkflowState` 之间转换。src 内唯一调用者是死侧 `llm_phase_node.py:146`。

裁定:ctx 桥随死家族一起删除,连同其特征化测试 `packages/graph-agent/tests/core/test_state_legacy_context_characterization.py`。**因此本决议迁移后的所有认知工具一律不走 ctx 注入,统一走 CognitiveFlowMiddleware 拦截 + FrameworkState 读写**(§2「CognitiveFlowMiddleware 拦截」)。

### 1.7 决策考古:用户原始决策在哪里

七项功能的用户原始决策不在本仓的 Claude Code 会话记录里(本仓会话最早只到 2026-07-02),而在三处更早的档案:

1. **2026-04-27 九轮设计定稿**:git 历史 `docs.backup-2026-05-20/archive/superpowers_history/2026-04-27-prompt-schema-9round-final-plan.md`。本文中「九轮定稿」「Round N」「P0-x」「P1-x」均指该文档内的轮次与决议编号。
2. **plan.md**:随 root import 携带进本仓的规划文档。「root import」指本仓以上游仓代码为起点的初始导入;root import 之前的开发历史只存在于上游仓。
3. **.kiro spec 归档**:`.kiro/specs/` 下的工作规格存档。

另一项考古事实:`cognitive/memory.py`、`cognitive/ambiguity.py` 与双闸 nudge 常量出生于上游仓 AI-story-forge——该仓 2026-04-21 的 root commit 里它们已是成品,故其出生决策早于一切本仓可查记录。

---

## 2. 术语

- **活路径**:§1.3 定义的当前实际执行链路(graph_assembler 装配的 create_agent 图 + 9 槽中间件链)。
- **死家族**:§1.1 定义的 14 模块封闭 import 闭包及其附着孤儿模块;src 内零外部引用者。
- **中间件链**:`create_agent` 挂载的中间件序列——7 槽顺序契约 `MVP0_MIDDLEWARE_ORDER_CONTRACT` + 前置 2 槽,共 9 槽;全部继承 langchain 官方 `AgentMiddleware`。
- **CognitiveFlowMiddleware 拦截**:认知类框架工具不在工具函数体内实现行为,而由 CognitiveFlowMiddleware 按工具名拦截,在中间件内完成状态读写与流程路由;现拦 finish_task 与 ask_clarification 两个名字(`cognitive_flow.py:65-66`,分发门在 `:404`)。本决议将拦截名单扩展到全部认知工具。
- **装配层(graph_assembler)**:引擎把编译产物装配成可运行图的模块;工具挂载、模型解析、中间件链构造都发生在这里。
- **框架工具**:由引擎自身定义并挂载、供模型调用的工具;SKILL 声明与框架工具重名时,loader 报 `[F-v3-agent-tool-reserved]` 诊断拒绝。
- **opt-in(manifest.context_access)**:SKILL 清单(manifest)中的 context_access 声明;只有声明了对应能力名的 phase 才挂载对应工具,未声明即不挂载(默认强隔离)。
- **sidecar**:压缩(compaction)时被移出上下文的消息全文落盘文件,供事后追溯;CompactionEvent 的 content_ref 字段指向它。
- **attended / unattended**:有人值守 / 无人值守两种运行模式。attended 下 ask_clarification 触发 interrupt 等待人工回答;unattended 下由引擎本地自动回答、运行不中断。

---

## 3. 逐项迁移设计

每节按「出生档案 → 现状证据 → 目标设计 → 被弃项 → 验收判据」组织;§3.7 因判定不迁移,以「结论」代替目标设计与验收判据。

### 3.1 ask_clarification(默认挂载恢复)

**出生档案。** 九轮定稿 Round 6,用户质问上下文污染问题;Round 7 得出结论「逃生舱缺失」;P1-5 裁定「默认注入」。它因此是死侧唯一无条件挂载的工具(`llm_phase_node.py:494-497`)。

**现状证据。** 工具定义在 `tools/builtin/clarification_tool.py:8-29`:空壳函数体(真实行为由中间件拦截实现),`return_direct=True`,参数为 question / clarification_type(5 值 Literal)/ context / options。

拦截与续跑链条都还活着:

- CognitiveFlowMiddleware 的 `intercept_ask_clarification`(`cognitive_flow.py:319-348`):unattended 运行下本地生成中文自动回答;attended 运行下调用 interrupt_fn(默认 langgraph interrupt);捕获 RuntimeError "outside of a runnable context" 时降级为 needs_human_input。
- 三种 source 的路由(`cognitive_flow.py:858-887`):human_interrupt / unattended_auto_answer → `Command(goto="model")`;needs_human_input → goto END。
- runner 侧 HITL(human-in-the-loop,人工介入)检测:`runner.py:92` 的 `_HITL_TOOL_NAMES`、`:1678-1706` 的 checkpoint 扫描、`resume_skill`(`:506-641`)经 `:1729-1745` 的 `graph.update_state` 注入 ToolMessage 后续跑。

断裂点:活路径没挂这个工具——`graph_assembler.py:1986` 的 all_tools 集合中没有它,模型永远调不出来,上述整条链在活路径上是死码。

**目标设计。**

1. graph_assembler 无条件挂载 ask_clarification_tool 进 all_tools。
2. loader 白名单(`core/loader.py:1248` 的 framework_tool_names)加入 "ask_clarification":SKILL 声明该名字即报 `[F-v3-agent-tool-reserved]` 诊断,与 finish_task 同款处理。
3. `runner._HITL_TOOL_NAMES` 删除 "request_human_input"——全仓 src 无该工具定义,属纯预留死条目。

**被弃项。** 「按 phase 声明才挂载」方案被否:直接违背 P1-5「逃生舱必须无条件存在」的原始裁决。

**验收判据。**

1. unattended run 中模型调用 ask_clarification → 自动回答以 ToolMessage 回灌、goto model、run 不中断。
2. attended run → interrupt → runner 发 InterruptedEvent(含 question / clarification_type / options)+ RunEndedEvent 正常返回。
3. `resume_skill` 注入人工回答后续跑成功。
4. SKILL 里声明 ask_clarification → loader 报 `[F-v3-agent-tool-reserved]`。
5. 引擎门禁(mypy --strict + 三套 pytest)全绿。

### 3.2 update_working_memory

**出生档案。** 上游仓预置(root import 之前);2026-04-08 需求对照表把用户提出的「运行时积累标注」需求对应到此工具;设计动机为「强制显式规划 + 可审计执行轨迹」(当年 ARCHITECTURE 文档 §2)。

**现状证据。** 工具本体 `cognitive/memory.py:11-17`:写 `ctx["_working_memory"]`,本体不发事件——WorkingMemoryUpdateEvent 由死侧外层循环在 compaction checkpoint 时才发(`llm_phase_node.py:785`)。`FrameworkState.working_memory` 槽位存在(`state.py:210`),但已被活路径借用(iterate_executions 键 + "scratch" 暴露,见 §1.5)。

**目标设计。**

1. 新建空壳工具,与 clarification_tool 同款模式:`@tool` 装饰、docstring 即 schema、函数体返回占位;graph_assembler 无条件挂载。
2. CognitiveFlowMiddleware 新增拦截名 update_working_memory;handler 把 plan 文本写入 `state["flow"].working_memory` 的 "plan" 键(与 iterate_executions 键共存,经 `Command(update=...)` 回写)。
3. 每次接受更新即发 typed WorkingMemoryUpdateEvent(`callbacks/events.py:181`)——玻璃盒 tracing 原则,不再只在 compaction checkpoint 才发。
4. loader 白名单加入 "update_working_memory"。

**被弃项。**

1. 保留 ctx 注入签名——ctx 桥随死家族删除(§1.6),迁移后无 ctx 可注入。
2. 给 FrameworkState 新增独立字段——working_memory 槽位本来就是为此功能而建,活路径只是借用了 dict 中一个键;键级共存即可,schema 面不扩。
3. 沿用死侧「仅 checkpoint 时发事件」——可观测性差。

**验收判据。**

1. 工具调用后 `state["flow"].working_memory["plan"]` 为最新文本。
2. 每次调用发 WorkingMemoryUpdateEvent。
3. iterate_executions 既有行为不受影响(既有测试不破)。
4. 白名单诊断测试(SKILL 声明该名字被拒)。

### 3.3 log_ambiguity

**出生档案。** 用户裁决原话未找到——本仓全部 Claude Code transcripts(最早 2026-07-02)、九轮定稿、plan.md 均查过;该工具出生在 root import 之前的上游仓。当年文档审计(2026-06-04)已标注「迁移源未捕获用户原话,留回填槽位」(回填槽位状态见 §7)。设计语义有明确出处:「这不是阻塞流程的澄清请求,而是用于改进技能定义的反馈回路」——与 ask_clarification 的分界在于:log_ambiguity 不中断运行,记录后按最保守方案继续。

**现状证据。** 工具本体 `cognitive/ambiguity.py:17-28`:参数 question / ambiguity_type(5 值 Literal)/ decision / reason;append 到 `ctx["_ambiguity_reports"]`;返回 `{"status":"recorded",...}` JSON;发 AmbiguityLoggedEvent(`:79`);用正则从 question+reason 抽取 `@reference:xxx` / `@protocol:xxx` 填 related_refs / related_protocols(`:13-14`)。

`FrameworkState.ambiguity_reports`(`state.py:212`)活路径零写入。loader 白名单已含 "log_ambiguity"(`loader.py:1248`)但活路径不挂载该工具——白名单与现实脱节。

**目标设计。**

1. 空壳工具 + graph_assembler 无条件挂载。
2. CognitiveFlowMiddleware 拦截:append 到 `state["flow"].ambiguity_reports`,record 含 timestamp / phase / type / question / decision / reason;发 AmbiguityLoggedEvent(保留 `@reference` / `@protocol` 抽取);返回 recorded JSON 后 goto model,不中断。
3. 白名单不需改(名字已在)。

**被弃项。** `ctx is None` 降级分支——ctx 概念随死家族消失,中间件拦截点上状态一定存在。

**验收判据。**

1. 调用后 ambiguity_reports 追加一条完整 record。
2. AmbiguityLoggedEvent 发射且 related_refs / related_protocols 抽取正确。
3. run 不中断继续执行。
4. 挂载后白名单与实挂集合重新一致。

### 3.4 context_access 工具组(query_working_memory / read_artifact)

**出生档案。** 用户直接定调,九轮定稿 Round 8 第 3 条:「phase 间默认强隔离(messages=[] by-design)+按需挖掘机制(context_access opt-in)」。**opt-in 语义是用户裁定的,必须原样保留。**

**现状证据。** 工具本体 `tools/builtin/context_access.py`:query_working_memory 读 `ctx["_working_memory"]`(`:24-29`);read_artifact(`:31-57`)拒绝空名、拒绝 `_` 前缀、not-found 时列出可见名单、50_000 字符截断。

`Phase.context_access` 字段(`core/types.py:64-65`)在 src 内唯一读点在死侧 `llm_phase_node.py:244-261`;活路径 graph_assembler 全文无 context_access 引用。活路径 AgentNodeAST 是否已携带该字段——**实施期核实**;若无,则补 loader → AST → 装配层的传递。

**目标设计。**

1. opt-in 挂载:manifest.context_access 含 "working_memory" 才挂 query_working_memory(读 `flow.working_memory["plan"]`);含 "artifact" 才挂 read_artifact。
2. 两工具经 CognitiveFlowMiddleware 拦截、读 request.state——保持认知工具单一 owner 模式。
3. read_artifact 的活路径数据面(读哪个工件存储)——**实施期依 io/storage 现状定,TDD(test-driven development,测试驱动开发)先行**。
4. 50_000 字符截断与防护语义(拒 `_` 前缀、not-found 给名单)保留。

**被弃项。** 无条件挂载——直接违背 Round 8 opt-in 裁决。

**验收判据。**

1. manifest 无 context_access → 两工具都不挂(默认强隔离成立)。
2. 声明 working_memory → query_working_memory 可读到本相 plan。
3. 声明 artifact → read_artifact 可读、拒 `_` 前缀、not-found 给名单。
4. loader / AST 传递有测试钉住。

### 3.5 双闸 nudge(planning / selfcheck)

**出生档案。**

- 用户在 plan.md 悬决表第 1 行亲裁:「Nudge 还要不要?→保留但降权:默认 max_nudges=1」——已落入 `core/types.py:45-51`(Task 6.5 注释)。
- WS-E8 约束(`.kiro/specs/engine-mvp1/gemini-prompt-ws-e8-exit-gate.md:98`):「请保持它只是 middleware 侧适配器，不要复制一套不可解释的新 nudge 策略」;`requirements-ws-e8-exit-gate.md:44` 有同义的规范化表述。
- 迁移计划 `docs/design/agent-loop-planA-create-agent-migration.md:122`:「nudge 逻辑也现成…移植成 after_agent 闸的一部分」。

**现状证据。** `core/nudge_injector.py` 三个 gate:

- `try_selfcheck`(`:88-116`):check-before-increment(先检查预算再计数);`schema_validation=="failed"` 时直接返回校验错误文本、不计数。
- `try_planning`(`:118-134`):触发条件为模型有文本输出、且无 tool_calls、且 working memory 未更新。
- `try_standard`(`:136-151`):兜底闸。

预算逻辑在 `:166-187`:planning/standard 两闸是 increment-before-check(先计数再检查)的遗留 quirk,代码带 FIXME;全局上限 max_nudges×2。事件走旧式 `cb.on_nudge` 回调(`:189-206`),非 typed 事件。文案常量在 `cognitive/finish.py:80-97`(PLANNING_NUDGE 要求模型先调 update_working_memory、SELFCHECK_NUDGE、MIN_FINISH_REASONING_LEN=30)+ 递进文案 `build_standard_nudge_text`(`:118-130`)。结构化自检判定 `_has_structured_selfcheck`(`nudge_injector.py:208-226`)。

活路径一侧:ExitControlMiddleware 已有最小 nudge 与 typed NudgeEvent(`middleware/exit_control.py:169`)。现状 baseline(`docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/baseline.md:59`):「当前 WS-E8 live exit gate 没有复制或改写该模块,也没有新增 middleware-side nudge adapter」。目标设计(同目录 `mvp1-alignment.md:16`):after_agent 读 finish_task_result marker,无合格 finish → NudgeInjector 构 nudge + `jump_to "model"` 回灌。

**目标设计。**

1. NudgeInjector 的语义核心保留为**唯一 nudge 策略源**(WS-E8 可解释性约束),以中间件适配器形式并入 ExitControlMiddleware。
2. selfcheck / standard 两闸挂 after_agent hook:无合格 finish_task → 构造 nudge + `jump_to "model"` 回灌。
3. planning 闸挂 after_model hook:触发条件为模型有文本输出、且无 tool_calls、且 `flow.working_memory` 无 "plan" 键。
4. 事件统一为 typed NudgeEvent,删除旧式 on_nudge 通道。
5. 预算语义修复为一致的 check-before-increment(修掉 FIXME quirk;预发布无兼容包袱,first-principles 修在源头)。
6. max_nudges 默认 1、全局上限 2× 保持不变。
7. 依赖:PLANNING_NUDGE 文案要求模型调用 update_working_memory,故本项依赖 §3.2 先落地(PR 顺序见 §4)。

**被弃项。**

1. 在 CognitiveFlowMiddleware 里做 nudge——职责归属错误:nudge 是推进/退出控制,ExitControlMiddleware 已 own NudgeEvent。
2. 新写一套 nudge 策略——直接违背 WS-E8 约束原话。
3. 保留 increment-before-check quirk——带着已知缺陷迁移,违背 first-principles 修复纪律。

**验收判据。**

1. 三 gate 触发条件逐一单测(含 `schema_validation=="failed"` 不计数分支)。
2. max_nudges=1 预算与全局 2× 上限行为钉死。
3. NudgeEvent 携带 nudge 类型与计数。
4. 中间件顺序契约回归测试(`tests/graph_agent/conftest.py` pin)通过。
5. 无合格 finish 的 run 在预算耗尽后,仍按 ExitControlMiddleware 既有语义收敛。

### 3.6 compaction / 摘要压缩

**出生档案。**

- 尺度来源为用户原话:「写一部1000章的小说,或者分析拆解一部1000章的小说转成剧本」(2026-06-03,记录于 08-messages-state 设计源 §4)。
- 决策 HS4:「compact 是 1000 章可行性前提,非优化」。
- 九轮定稿 P0-1:用户批准 B 选项——显式挂 SummarizationMiddleware,trigger_fraction=0.8 / keep_messages=20。

**现状证据。** 死侧有两套压缩并存:

- **(a) langchain SummarizationMiddleware**:`llm_phase_node.py:277-282` 传参 → `cognitive/middlewares.py:466-483` 构造,`trigger=[("fraction",0.8)]`,`keep=("messages",20)`;`_ensure_summarization_profile`(`:54-65`)为缺 `profile["max_input_tokens"]` 的 model 包兜底,否则构造即炸。
- **(b) 自研 working-memory checkpoint 压缩**:触发条件为 plan_verified 且 wm_updated(`llm_phase_node.py:355-381`);sidecar 落盘在 `:383-400`;CompactionEvent 构造在 `:813-817`,含 content_ref。

设计源 gap:`docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/mvp1-alignment.md:51` 的 gap #1 与 `:18`:「summarization middleware + sidecar 从 legacy 死簇搬回 live(超窗摘要 + sidecar 存全文)」。注意:该文引用的死侧行号已全部漂移,以本决议行号为准(校正义务见 §6)。

依赖可用性:langchain 1.3.10 已锁定(`uv.lock:1222-1223`,版本约束在 `pyproject.toml:13`);SummarizationMiddleware 是 `langchain.agents.middleware` 的官方公开导出,与现有 9 槽链同属 AgentMiddleware 体系,无需新增依赖。

**目标设计。** 迁移 (a) 这套——它是用户 P0-1 裁决的对象,也是设计源 gap #1 指向的形态;参数 0.8 / 20 保持不变。具体:

1. 新建 `middleware/compaction.py`,包装 SummarizationMiddleware 并增加可观测性:触发摘要时把被移出上下文的消息全文写入 sidecar 文件,发 CompactionEvent(content_ref = sidecar 路径)。
2. `_ensure_summarization_profile` 兜底逻辑一起迁移。
3. 纳入中间件顺序契约:更新 `MVP0_MIDDLEWARE_ORDER_CONTRACT`、`middleware/factory.py` 的 by_contract_name、conftest 中的顺序回归测试。
4. 槽位约束:必须在模型调用前生效,且不得破坏 ToolHistoryIntegrityMiddleware 的修复语义;链内确切位置——**实施期按 langchain hook 语义定,并以顺序测试钉死**。

**被弃项。** 复活 (b) WM-checkpoint 压缩。理由:其触发条件(每轮 plan_verified + wm_updated)绑死在被 create_agent 迁移取代的旧认知循环形态上,活路径的 agent loop 已由 langchain 接管,该触发条件失去宿主;设计源 gap #1 指向的也是超窗摘要这套。(b) 的可观测性价值(sidecar + CompactionEvent)由 (a) 的包装层收编,不丢失。

**验收判据。**

1. 消息超窗(fraction 0.8)触发摘要,keep 20 条。
2. sidecar 文件含被移除消息全文,可事后追溯。
3. CompactionEvent 发射且 content_ref 指向 sidecar。
4. 不触发时零行为改变(既有全套引擎测试不破)。
5. 顺序契约测试更新并通过。
6. 无 profile 的 model 不炸(兜底测试)。

### 3.7 ModelResolvedEvent——判定已被替代,不迁移

**出生档案。** T-B2 工程立项(两行,估时 30 分钟);最近上位需求为 `plan.md:170`:「run 报告要有 Fallback 发生次数与原因」。

**现状证据。** 唯一构造点在死侧 `llm_phase_node.py:169`;字段 tier / role_name / resolved_model / thinking_enabled / model_override / call_chain(`events.py:572-587`)。活路径模型解析函数 `graph_assembler._resolve_phase_chat_model`(`:2188-2244`)零事件发射。

**替代证据。**

- 引擎侧:PromptCapturedEvent 携带 llm_role + resolved_model + loop_index(`events.py:292-303`);`LLMCallEvent.resolved_model` 由 LLMProviderChatModel 用 provider 实际应答的模型回填(`events.py:106`、`core/llm_provider.py:198-222`)。
- gateway 侧:LLMRouteDecisionEvent / LLMCallSettingsEvent 覆盖路由决策、endpoint、settings(`packages/graph-agent-gateway/src/graph_agent_gateway/call/tracing.py:31`、`:86`)。
- 上位需求(fallback 可观测)由 gateway 事件满足。

**结论。** ModelResolvedEvent 事件类不迁移,随整族删移除(§5);前端消费分支 `apps/studio/frontend/src/utils/trace.ts:85` 同批清理。

**被弃项。** 在 `_resolve_phase_chat_model` 补发射——信息与上述事件面重复,违反 DRY(Don't Repeat Yourself,同一事实只定义一处)/ 单一事实源。

---

## 4. 实施顺序与 PR 切分

- **PR A**:本决议文档(docs-only)。
- **PR B「认知工具回归活路径」**:§3.1 + §3.2 + §3.3 + §3.4。四项共享装配层挂载面与 CognitiveFlowMiddleware 拦截面,放一个 PR 内聚;TDD 先红后绿。
- **PR C「双闸 nudge 中间件适配」**:§3.5。依赖 PR B——PLANNING_NUDGE 文案要求模型调用 update_working_memory,该工具必须已挂载。
- **PR D「compaction 中间件」**:§3.6。独立成 PR:它改动中间件顺序契约,需要单独评审面。
- **PR E「整族删」**:§3.7 的事件删除 + §5 全部范围。前置条件 = PR B / C / D 已合并且真机验证通过。

每个实施 PR(B/C/D/E)的义务:

1. 引擎门禁全绿:`uv run mypy --strict packages/graph-agent/src` + 三套 pytest。
2. 同步更新对应设计单元的 baseline.md(§6)。
3. 合并后重建 vendor(AGENTS.md「Workflow Pipeline」第 7 条),然后真机冒烟。

---

## 5. 迁移完成后的整族删范围(PR E)

以下是概要清单;**PR E 开工时必须逐项重新核证零引用后才执行,本节不是免检通行证**:

1. 14 模块死家族闭包 + 附着孤儿(§1.1 清单)。其中 `cognitive/finish.py` 内被 §3.5 收编的常量迁至活侧后,整文件删除。
2. ctx 桥:`state.py` 的 `legacy_context_from_state` / `workflow_state_from_legacy_context` 及辅助函数(`_add_not_none_framework_values` / `_add_non_empty_framework_values` / `_add_copied_framework_values` / `_not_none_framework_pairs`)+ `packages/graph-agent/tests/core/test_state_legacy_context_characterization.py`。
3. 零发射点事件类(删前逐一核证):ValidationPassEvent、ValidationFailEvent、RetryEvent、RetryExhaustedEvent、ModelResolvedEvent、FinishTaskEvent(FinishTaskVerdictEvent 是活的,保留)、DeadEndPrunedEvent、AmbiguityReportEvent(AmbiguityLoggedEvent 迁活,保留)、HeartbeatEvent。ThreadCleanedUpEvent / InternalErrorEvent 零构造,但需核对公共 API 承诺后再定(**待定**)。

   **2026-08-15 PR E 重核结论(本节要求的逐项重核推翻了其中一条)**:
   - **DeadEndPrunedEvent 不删,保留**——它有活生产者:`ExecutionControlMiddleware`(活链第 3 槽)在
     `middleware/execution_control.py` 里经旧式 `on_dead_end_pruned` 回调发出,`_TraceCallback`
     再把它打包成 typed 事件写入 trace。本节起草时的清单把它误判为零发射点。
   - ThreadCleanedUpEvent / InternalErrorEvent 的**待定已裁决:删**——两者在删除前的源码树里只有类定义、
     零构造点,公共 API 契约文档同批收缩。
   - 其余七类经重核确认零发射点,按本节删除。
4. `callbacks/tracing.py` 中把旧式 on_* 回调重打包成上述死事件的分支(`:252-406` 区间逐个核对);`callbacks/base.py` 相应 dispatch 注册;公共 API `EXPECTED_CALLBACK_EVENT_VARIANTS` frozenset 同步收缩。
5. FrameworkState 死字段核对:ambiguity_reports 届时已被 §3.3 救活、working_memory 已被 §3.2 救活——两者不删;其余字段逐个重核。
6. Phase 死字段(`types.py` 中 retry_target 等设计取消项);`runner._HITL_TOOL_NAMES` 中的 "request_human_input"(若 PR B 未删)。
7. spec 清单文件 `source_file_map.yaml` / `features.yaml` 约 20 条目。
8. 前端死分支(apps/studio/frontend 内):`run-status-projection.ts:100` 的 FAILURE_EVENT_TYPES、`TraceStepRow.tsx:84`、`trace-category.ts:25`、`reportTemplates.ts:183`、`utils/trace.ts:126` / `:351` / `:85`;Studio backend 的 `run_report.py:169`。

**完成判据**:src 零引用证明(import 图重跑)+ 全套门禁 + vendor 重建 + `/studio-verify` 真机冒烟 + 五列报告(条目 / 操作 / 预期 / 实测 / 截图)。

---

## 6. 设计源同步义务

依据用户 2026-08-15 文档分类学裁决(§0 第 3 条:baseline.md = 代码现实,mvp1-alignment.md = 设计文档但可能过时):

1. 每个实施 PR 同步更新对应设计单元的 baseline.md:
   - 02-middleware:中间件链构成。
   - 03-cognitive:CognitiveFlowMiddleware 拦截名单扩展(PR B)。
   - 04-tools:框架工具集合(PR B)。
   - 05-exit-control:nudge 适配器落地(PR C)。
   - 08-messages-state:compaction 落地,gap #1 关闭(PR D)。
2. `08-messages-state/mvp1-alignment.md` 引用的死侧行号已漂移,PR D 落地时一并校正:`:275` → `:277-282`、`middlewares.py:466` → `:467`、sidecar `:381` → `:383`、CompactionEvent `:809` → `:813`;另 `graph_assembler.py:481` 的「单槽」表述已过时,现实为 9 槽链。
3. 涉及 audited-ready 哈希锁的文档,同一 PR 内重钉 `_audited-ready-hashes.json`。

---

## 7. 未决项

1. **role × context_access 耦合**:九轮定稿开放问题 4 从未裁决。本迁移不扩大范围——opt-in 语义原样保留;若将来 role 系统收编 context_access,再另行裁决。
2. **log_ambiguity 用户原话回填槽**:仍空缺(上游仓不可考);目前以设计语义出处为准(§3.3)。
3. **台账在册、不属本决议范围的漂移**(在此列出以免被误认为遗漏,本决议不处理):tools/ 目录机制未入设计 SSOT(single source of truth,单一事实源)、`tools/builtin/__init__.py` docstring 宣称的 `builtin.` 前缀特判与 loader 代码不符、HTTP 白名单缺 `phases/<id>/validator.py`、has_validator 硬编码 False。
