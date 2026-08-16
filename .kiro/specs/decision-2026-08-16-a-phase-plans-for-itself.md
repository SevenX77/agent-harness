# 决议:一个相位为它自己做计划

- 日期:2026-08-16
- 范围:`packages/graph-agent/src/graph_agent/runtime/state_mapper.py`(`StateMapper.build_phase_input`)
- 前置:`.kiro/specs/decision-2026-08-16-a-phase-opens-its-own-conversation.md`(PR #838,commit `01f5cdde`)
  在「已知遗留」第 2 条明写:`flow.working_memory` 是**第二条**跨相位通道,
  「是否同样隔离需要单独裁决——这次不动」。本决议就是那条裁决。
- 用户裁决:2026-08-16,方向由 operator 判定后交付实施。

## 决策

`flow.working_memory` **按相位隔离**:`build_phase_input` 递给相位的 flow 副本,
`working_memory` 清空为 `{}`。相位从一份空白的工作记忆开始,自己记的计划只属于自己。

写回路径(`wrap_phase_output`)与全局 flow 通道**不动**。与 #838 同一个落点、同一条规则:
**改的是"递给相位什么",不是"运行留下什么"。**

## 这是新立的一条裁决,不是对齐既有设计

必须如实说明:设计源**没有**规定过 `working_memory` 的相位边界。九轮定稿 Round 8 第 3 条
与设计哲学第 2 条(`docs.backup-2026-05-20/archive/superpowers_history/2026-04-27-prompt-schema-9round-final-plan.md:79,97`)
点名的都只有 `messages`,#838 已经据此把 `messages` 归零。`working_memory` 不在那条裁决的
字面范围内,所以本次是**新立一条规则**,论据来自代码内部的自相矛盾与工具契约本身,不来自
一句现成的设计原文。

## 论据(逐条现场核验,均为本次亲自打开文件确认)

### 一、同一个类里三十行外就有正解

`packages/graph-agent/src/graph_agent/middleware/exit_control.py:136-150`
`_own_finish_payload` 的 docstring 与实现:

> ```python
> def _own_finish_payload(self, state: AgentState[Any]) -> dict[str, Any] | None:
>     """Return THIS phase's finish_task marker, qualified or not.
>
>     The framework state carries the previous phase's marker across the
>     boundary, so only a marker labelled with this phase's name counts.
>     """
>     ...
>     if finish_result.get("phase_name") != self._phase_name:
>         return None
> ```

它已经指认了病灶:**框架状态会把上一个相位的东西带过边界,所以必须按相位名过滤**。

同一个文件 `:152-157`,紧邻的下一个方法,对**完全相同形状的跨边界值**零过滤:

> ```python
> def _working_memory_has_plan(self, state: AgentState[Any]) -> bool:
>     flow = state.get("flow")
>     working_memory = getattr(flow, "working_memory", None) if flow else None
>     if isinstance(flow, dict):
>         working_memory = flow.get("working_memory")
>     return isinstance(working_memory, dict) and WORKING_MEMORY_PLAN_KEY in working_memory
> ```

它只问「这个 dict 里有没有 `plan` 这个键」。同一个类,同一份 `flow`,同一条边界,
一个记得过滤、一个不记得。

### 二、写入端手里握着相位名,却写进一个不带相位名的常量键

`packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:706-719`:

> ```python
> plan = str(args.get("plan") or "")
> raw_memory = state["flow"].working_memory
> working_memory = dict(raw_memory) if isinstance(raw_memory, dict) else {}
> working_memory[self._WORKING_MEMORY_PLAN_KEY] = plan
> next_state = StateManager.update_framework(state, working_memory=working_memory)
> ...
> _safe_emit_event(
>     self._callbacks,
>     WorkingMemoryUpdateEvent(
>         phase_name=self._phase_name,
>         ...
> ```

键名是常量,`cognitive_flow.py:80`:

> ```python
> WORKING_MEMORY_PLAN_KEY = "plan"
> ```

同一段代码在 13 行之内既用了不带相位名的常量键落盘,又把 `self._phase_name` 填进事件。
相位身份就在手边,存的时候没用上。

### 三、要写进这个槽的内容,按定义就是相位局部的

`packages/graph-agent/src/graph_agent/middleware/nudge_policy.py:40-48`,`PLANNING_NUDGE` 原文:

> ```
> [系统提示] 在执行任何业务工具之前，你必须先调用 update_working_memory 记录你的执行计划。计划应包含：
> 1. 本阶段的目标是什么
> ...
> ```

第一句就是「**本阶段**的目标是什么」。一份写着"本阶段目标"的计划,拿到下一个相位去当作
"计划已存在"的证据,是把 A 相位的答案当成了 B 相位的答案。

### 四、`working_memory` 不是跨相位挖掘通道 —— 它的孪生兄弟才是

两个工具的 docstring 就是模型看到的契约本身。
`packages/graph-agent/src/graph_agent/tools/builtin/cognitive_tools.py:54-55`:

> ```python
> def query_working_memory_tool() -> str:
>     """Read the current working-memory plan text recorded by update_working_memory."""
> ```

`:60-61`:

> ```python
> def read_artifact_tool(name: str) -> str:
>     """Read a named business artifact (an earlier phase's named output)."""
> ```

`query_working_memory` 承诺的是「**由 update_working_memory 记下的**那份计划」——读回自己记的;
`read_artifact` 承诺的是「**某个更早相位的**具名输出」——这才是追溯前序上下文的那一个。
所以 `context_access` 的两个取值分工明确(`core/manifest.py:305` 的
`Literal["working_memory", "artifact"]`;`core/graph_assembler.py:2435-2439` 按值挂载):
`artifact` 管跨相位,`working_memory` 管相位内。

隔离之后 `query_working_memory` 返回的**正是它 docstring 承诺的东西**,不是被削弱。
在此之前它可能返回上游相位的计划,那才是与契约不符。

### 五、写回安全性的机理(本次亲自验证并用测试钉死)

`runtime/state_mapper.py:477-490` 的 `PhaseWrapper._wrapped` 把**原始全局 state** 交给
`wrap_phase_output`,后者(`:313-326`)按"变化键"出 delta:

> ```python
> if isinstance(flow_updates, FrameworkState):
>     before_flow = state["flow"].model_dump()
>     after_flow = flow_updates.model_dump()
>     flow_delta = {key: value for key, value in after_flow.items() if before_flow.get(key) != value}
> ```

`core/state.py:225-231` 把 `working_memory` 列入按键并集字段:

> ```python
> _FLOW_DICT_MERGE_FIELDS = (
>     "phase_execution_ids", "metrics", "critic_metrics",
>     "subagent_validation_retries", "working_memory",
> )
> ```

`core/state.py:302-308` 的 reducer 做按键 dict 并集:

> ```python
> for key in _FLOW_DICT_MERGE_FIELDS:
>     if key in delta and isinstance(delta[key], dict) and isinstance(merged.get(key), dict):
>         delta[key] = {**merged[key], **delta[key]}
> ```

于是两种情形都安全:

- **相位没记计划** → 递进去的是 `{}`,原样递回来,delta 里带一个 `working_memory: {}`
  (与全局值不同,所以进 delta),并集后 `{**全局, **{}} == 全局` → **空操作**;
- **相位记了计划** → delta 是 `{"plan": ...}`,并集后只覆盖 `plan` 一个键。

关键风险是 `iterate_executions`:`core/graph_assembler.py:981-1003` 的
`_with_graph_iterate_signal` 在**同一个 `working_memory` dict** 里追加图级 batch/loop 的
执行记账(`:1002` `working_memory["iterate_executions"] = executions`,调用点 `:1028` / `:1097`)。
按键并集是这两个写入方互不相干的唯一保障。**这一点用两条测试钉死**(见验收判据 b/c),
否则隔离会悄悄吃掉 iterate 记账。

## 修在哪一层,以及为什么不是另一层

改 `StateMapper.build_phase_input`,不是改 `_working_memory_has_plan` 的判据。

- **不在 `exit_control.py` 改成"按相位名存/按相位名读"**:那样要把
  `working_memory["plan"]` 改成 `working_memory[phase_name]["plan"]` 之类的分区结构,
  引入一层新的数据形状,而 `query_working_memory`(`cognitive_flow.py:793-811`)、
  `_with_graph_iterate_signal`、trace 投影三处都得跟着改。真正的问题不是"读的人没过滤",
  而是"**这个值本来就不该跨过边界**"——上游 `messages` 的同源缺陷 #838 已经在
  `build_phase_input` 这一层解决,同一条边界上的第二条通道理应在同一处收口。
  在读侧加过滤是症状补丁;在递侧不给,是病因修复。
- **不在 `cognitive_flow.py` 写入侧改**:写入侧改不了"上一个相位留下的值会被下一个相位读到"
  这件事,只能改"留下的是什么形状"。边界仍然是漏的。
- **不动写回与全局通道**:全局 `flow.working_memory` 仍然累积每个相位记的计划,
  checkpoint、trace、HITL resume 一律不变。这与 #838 是同一条规则,不是两套语义。

## 借了什么、拒绝了什么

**借的是进程式的参数传递语义**——被调用方拿到的是显式声明的参数,不是调用方的栈帧。
直接参照物是本仓自己已有的同形实现:#838 之后 `build_phase_input` 已经对 `messages`
这么做了(`state_mapper.py:167-189`),SUBGRAPH 节点与 subagent 也早就是 `messages=[]`。
本次是把同一条语义补齐到同一个边界上的第二个字段,不是引入新语义。

**借的第二样是 Kubernetes `Lease.holderIdentity` 一类"租约必须指名持有者"的思路的反面用法**:
既然 `_own_finish_payload` 已经证明"跨边界的值必须能指认它属于谁",而 `working_memory`
的槽位设计上就不带持有者标识(常量键 `"plan"`),那么正确的收敛方向不是给它补一个持有者字段
(那会把一个相位局部的便签本升级成一张全局注册表),而是**不让它跨边界**。取舍点在于:
补持有者字段换来的是"跨相位可读且不串台"的能力,而按论据四,跨相位读取这件事已经由
`read_artifact` 负责了,再补一条是重复建设。

**拒绝的是"在 `_working_memory_has_plan` 里按相位名过滤"**。它更小、改动更省,但它把
`working_memory` 固化成一个跨相位共享、靠读侧纪律维持正确的全局结构——下一个读它的人还得
再记一次过滤,而 `exit_control.py` 自己就是"同一个类里一个记得一个不记得"的现成反例。

**拒绝的是"连写回一起停"**。写回停掉,`iterate_executions` 与整份计划记录都会从
checkpoint 里消失,代价没有对应收益。

## 明确不采用的两条错误论据(前一轮调研踩过,记此以免复发)

1. **不拿 MVP0 的「`scratch={}`、`messages=[]`,阻断草稿和 ReAct 对话跨 phase 泄漏」当依据。**
   已用 `git show 353fbb8a^` 核实:那次提交**之前**,`scratch`(`data` 三区里的业务草稿区)
   与 `working_memory`(挂在 `flow` 上)**同时存在**,是两条独立血脉,不存在前后身关系。
   今天 trace 上把 working_memory 显示成 `"scratch"`
   (`core/graph_assembler.py:2505` `"scratch": state["flow"].working_memory or {}`)
   是 `353fbb8a` 那次**无文档改名**造成的纯代码漂移。该漂移另记为遗留(见下),
   不构成本次的设计依据。
2. **不把本缺陷描述成"安全闸被绕过"。** `middleware/nudge_policy.py:164`:
   > ```python
   > if not latest_content or has_tool_calls or has_plan:
   >     return _NO_NUDGE
   > ```
   三者是**或**关系——模型只要调了任何工具,这道闸本来就不触发。准确表述是:
   **一个只空谈不动手的下游相位,本该吃到的那一记 planning nudge,被上游相位的残留 plan
   静默吃掉了**,它拿到的是一句泛泛的 standard nudge。

## 验收判据

测试文件:`packages/graph-agent/tests/runtime/test_phase_working_memory_isolation.py`
(两个顺序 AGENT 相位;alpha 先空谈吃一记 planning nudge、再 `update_working_memory` 记下计划、
最后 finish;beta 首轮同样只出文本不调工具)。

a. **下游相位仍拿得到属于它自己的 planning nudge**:beta 的 NudgeEvent 序列必须是
   `["planning"]`,且第二次模型调用收到的 HumanMessage 含 `PLANNING_NUDGE` 原文。
   隔离前实测为 `["standard"]`。
b. **隔离不吃掉 iterate 记账**:全局 `working_memory` 同时带 `iterate_executions` 与
   上游 `plan` 时,相位写入自己的 plan,折叠后 `iterate_executions` 原样保留、`plan` 被覆盖。
c. **没记计划就是空操作**:相位原样递回空槽,折叠后全局 `working_memory` 分毫不动。
d. **相位边界行为在每次运行上一致**(盯非确定性,见遗留 3):同一场景连跑 3 次,
   alpha/beta 的 nudge 类型序列与两个相位开场的 `scratch` 观测值必须三次全等。

## 已知遗留(明写,不装作解决)

1. **`working_memory` 在相位内部仍是一个无结构的公共 dict。** `plan` 键由
   `cognitive_flow.py` 写,`iterate_executions` 键由 `graph_assembler.py` 写,
   两者靠 reducer 的按键并集共处,没有 schema 约束谁能写哪个键
   (`core/state.py:211` `working_memory: Any = Field(default_factory=dict)`)。
   本次不动它:隔离解决的是跨边界串台,不是槽内的类型缺失。
2. **trace 上的 `"scratch"` 命名是一次无文档改名的残留。**
   `core/graph_assembler.py:2505` 把 `flow.working_memory` 投影成 `"scratch"` 字段,
   而 MVP0 语境里的 `scratch` 是 `data` 三区里的业务草稿区,是**另一样东西**。
   `353fbb8a` 之后二者被同一个名字指代。本次隔离顺带改变了这个字段的可观测值
   (相位开场从"继承上游"变成 `{}`),但**没有**订正命名。订正需要单独确认
   Studio trace 投影层与既有 golden 是否依赖该字段名,另立一条。
3. **一次未坐实的非确定性观察。** 前一轮调研中,最初 3 次运行 `working_memory`
   **没有**跨边界,此后 50+ 次稳定复现泄漏;编译缓存、编码、pytest capture、
   hash 随机化均已排除,**未找到成因**。该观察因此不作为任何论据使用,
   仅以验收判据 d 的确定性测试长期盯住:一旦相位边界行为再次翻覆,它会以测试失败的形式
   出现,而不是又一段口述故事。
4. **未做真机/真跑验证。** 本次只交离线证据(单测 + 全门禁)。
   「隔离之后下游相位不再借上游的计划蒙混过关」在机制上必然,但要真跑一次带真实模型的
   skill 才算现场坐实——与 #838 的遗留 3 同性质,未做。
