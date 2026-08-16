# 决议:边(edge)升为与节点平级的运行分段,事件发送端统一到唯一线路

- 日期:2026-08-15
- 状态:已裁决,待实施
- 影响模块:engine(`packages/graph-agent`)· Studio 后端(`apps/studio/backend`)· Studio 前端(`apps/studio/frontend`)
- 前置决议:`docs/design/2026-08-15-legacy-cognitive-features-migration-decision.md`(死家族迁移与整族删)

---

## 0. 授权链(用户原话,逐字)

本决议的全部授权来自以下三句裁决与一条工作方式指令:

1. 「DeadEndPrunedEvent该怎么处理，合到正规的线路里去」
2. 「edge指的是一个node到下一个中间的过程，是需要的，把engine该补的补齐」
3. 「tracing要把edge和node作为平级的运行分段，流中的一个节点」
4. 「不要问我这类问题，按照原则自己判断。你能问我的只有：目标不清晰，目标效果不清晰；原则不清晰或者有冲突。自己推进直到目标完成」

第 4 条把三个待裁问题(旧钩子翻译层是否同批删除、上游执行标识用单数还是复数、PR 拆分顺序)交回执行者按仓库原则自行判断。本决议第 4 节逐条记录判断结果与所依据的原则条文。

## 1. 问题:引擎里没有"边执行"这个对象

Studio 画布上,两个节点之间的连线承载一段真实发生的过程——上游节点结束之后、下游节点开始之前的全部操作(黑板 reduce 与聚合、输入文件注入、输出落盘、截断与摘要)。设计源对它的定义是权威的:

> dot = 两节点之间的"中间节点"(langgraph edge),代表**上节点 end 后、下节点 start 前的所有操作**(黑板 reduce/聚合、输入文件注入、输出落盘、截断/摘要/存储)。点 dot → ① 看该刻黑板内容 ② 看"上节点 end→下节点 start"的全部操作记录。
> —— `docs/studio/mvp1/01_workflows/04_run-and-verify.md` D 节「核心概念:线上 dot = 节点间状态机转移点」

引擎当前没有任何代码单元对应这段过程。边的操作寄生在**下游节点包装器的开头**:`core/graph_assembler.py:1178` 在进入目标 phase 前调用 `_emit_input_dispatch(...)`,黑板 reduce 在 `:922` 与 `:1077`。三处都是节点执行路径上的副作用,不是一个有身份、有边界、有时长的执行对象。

由此产生三个可观察症状,每一个都是同一个缺失的投影:

1. **边事件写不出自己从哪来。** `_emit_blackboard_reduce`(`core/graph_assembler.py:759-777`)构造 `BlackboardReduceEvent(from_phase=None, ...)` —— `from_phase` 恒为 `None`,不是没填,是结构上无从填起。
2. **`input_dispatch` 的来源是推断值。** `_emit_input_dispatch` 通过 `_current_phase_from_state(state)` 取 `state.flow.current_phase`,语义是"最近一个跑过的 phase"。单链拓扑下它碰巧等于上游,扇入与并联下不唯一。
3. **前端已在替引擎推断,并把这一点写进了注释。** `apps/studio/frontend/src/utils/trace-scope.ts:23` 原文:「so it is attributed to the edge whose UPSTREAM phase persisted」。

三模块接口握手审计对此有更早的记录,并把它列为最大功能缺口:

> **判定**:最大功能缺口——**studio 建在前、engine impl 在后**;studio canvas 微观/dot/逐轮视图在 engine 补这些事件前**渲染不出**。非签名 mismatch,是 impl 时序。
> —— `docs/engine/mvp1/_api-handshake-audit.md` §3.2

该审计点名的三个边操作事件(`blackboard_reduce` / `input_dispatch` / `input_file_injected`)此后已在引擎实现,故 §3.2 已部分过期;仍然欠缺的是标识类字段 `edge_transition_id` / `phase_execution_id` / `iteration`,以及节点内部微观拓扑所需的 `parent_node_id` / `node_type`。

**结论:先补字段是错的修法。** 缺失字段是缺失所有者的症状——没有一个对象负责"一次 A→B 的转移",就没有任何代码位置能生成一致的转移标识。修复必须落在缺失的那一层:先让"转移"成为引擎里的一个执行对象,标识与字段随之自然可得。

## 2. 目标(正向定义)

实施完成后,系统满足以下四条:

1. **引擎把一次运行表述为一条执行段序列**,段有且只有两类:**节点段**与**边段**。两类段在事件模型中形状相同——各有唯一标识、各由一对边界事件界定、段内事件通过标识归属于本段。
2. **一次边转移即使没有发生任何操作,也在事件流中占一段**。空段是有信息的:它说明这次转移未做任何黑板变换。
3. **消费方不做归属推断**。Studio 前端与后端按事件自带的标识分段与记账;任何"按 phase_name 猜边归属"的代码删除。
4. **事件发送端只有一条线路**:构造 typed event,交 `callbacks/emit.py` 的 `_safe_emit_event(callbacks, event)`。发送端不直接调用任何 `on_*` 钩子,也不自行遍历回调列表。

## 3. 设计

### 3.1 转移所有者的位置

转移段的开启与关闭放在**下游节点包装器的头部**——即今天 `_emit_input_dispatch` 所在的位置(`core/graph_assembler.py:1178` 附近):进入下游 phase、派发输入之前开段,`phase_start` 之前关段。

这不是新增执行机制,而是给已经发生在那里的过程一个名字。选择该位置的理由:langgraph 的边是路由而非可执行单元,"上游结束到下游开始之间"这段时间在实现上唯一可观测的锚点就是下游包装器的入口。

### 3.2 事件契约(引擎)

新增两个事件类,与 `phase_start` / `phase_end` 严格对称:

- `edge_start` —— 字段:`edge_transition_id`、`from_phases`、`to_phase`、`from_phase_execution_ids`、`to_phase_execution_id`、`branch_index`
- `edge_end` —— 字段:同上,外加 `changed_keys`、`blackboard_snapshot`(该次转移结束时派发给下游的黑板内容)、`operation_count`

现有三个边操作事件(`blackboard_reduce` / `input_dispatch` / `input_file_injected`)增加 `edge_transition_id` 字段,取值为其所属转移段的标识。

节点侧对称补齐:`phase_start` / `phase_end` 及节点段内事件携带 `phase_execution_id`。

### 3.3 关键设计决定

**D1 · 边界事件成对,不用"首个事件即开段"的隐式边界。** 隐式边界无法表达空转移(零操作的边会在 trace 上整段消失),与目标第 2 条直接冲突。显式成对边界同时给出该段的时长。

**D2 · `phase_execution_id` 与 `AgentLoopIterationEvent.iteration` 是两个不同概念,不合并、不复用字段名。** 前者标识"同一个节点的第几次执行"(外层 iterate/batch 循环产生多次执行);后者标识"一次节点执行内部 agent 的第几个回合"。两者取值范围与生命周期都不同,共用一个名字会在循环场景下产生无法诊断的错位。

**D3 · 上游执行标识用复数 `from_phase_execution_ids`。** 扇入拓扑下,一次进入下游的转移在语义上汇合了多个上游执行;写成单数只能靠"取最近一个"来填,那正是本决议要消灭的推断。依据仓规「让非法状态不可表示」:能被类型表达的约束不留给运行期猜测。单上游时该列表长度为 1,不设特例。

**D4 · 边段的标识是"一次转移",不是"一条边"。** 循环中同一条边被走 N 次即 N 个 `edge_transition_id`;并联扇出中同一上游执行分发到 K 个下游即 K 个转移段。

**D5 · 消费方按标识分段,不按名字分组。** 前端 trace 的分段依据从 `phase_name` 改为执行段标识,节点段与边段平级呈现;`utils/trace-scope.ts` 中依据上游 phase 推断边归属的逻辑及其注释一并删除。

**D6 · 前端 `edge_transition` 幽灵分支删除,由 `edge_end` 取代。** `apps/studio/frontend/src/lib/edge-context.ts:18-20` 接受一个引擎从未发出、任何设计文档也从未定义的事件类型 `edge_transition`(设计源中 `edge_transition_id` 是**字段名**)。该分支连同其测试夹具删除;dot 的"跑后"一态改读 `edge_end`——它才是承载该次转移完整快照的事件。

**D7 · 发送端统一到 `_safe_emit_event`,接收端的旧钩子翻译层同批删除。** 依据仓规「不向后兼容 …… 换掉旧设计就在**同一个改动里删干净旧路径**」。具体:
- `middleware/execution_control.py:258` 的 `cb.on_dead_end_pruned(...)` 与 `:176-186` 手搓的回调遍历,改为 `_safe_emit_event`;
- `callbacks/base.py` 中 8 个 `on_*` 钩子与 `_dispatch_legacy_event` 翻译层删除;
- 接收方 `callbacks/logging_cb.py` / `callbacks/metrics.py` / `callbacks/tracing.py` / `core/_predict_internal/tracing.py` 改为重写 `on_event` 并按事件类型分派。

**D8 · 后端按段记账。** `apps/studio/backend/app/services/run_report.py` 的按节点错误记账要认识边段:发生在边段内的错误归该边段,不再计入下游节点。

### 3.4 明确不在本决议范围内

`parent_node_id` / `node_type` —— 三模块握手审计与上述字段并列提出,但它们解决的是**节点内部**的微观拓扑(agent 子事件树,对应 `04_run-and-verify.md` atom D9「agent 节点 '+' 内联展开执行子树」),与边分段是两个独立问题。合并进来会让引擎侧改动失去可审边界。单独排期。

## 4. 执行者按原则自裁的三条(用户授权第 4 句)

| 待裁项 | 裁决 | 依据 |
|---|---|---|
| 旧钩子翻译层是否同批删除 | **同批删除**(D7) | `AGENTS.md`「Development Principles」第 1 条:不向后兼容,禁止 legacy 别名与兼容层,换掉旧设计就在同一改动里删干净旧路径 |
| 上游执行标识单数还是复数 | **复数**(D3) | `AGENTS.md`「Coding Standards」:让非法状态不可表示;以及本决议第 1 节要消灭的正是"取最近一个"式推断 |
| PR 拆分与顺序 | **四个 PR,顺序 0 → A → B → C** | `AGENTS.md`「Coding Standards」单一职责:一个任务一个 PR,不夹带无关重构;顺序由数据依赖决定——消费方不能先于生产方改 |

## 5. 实施切分

| PR | 范围 | 依赖 |
|---|---|---|
| **0** | 发送端归位 + 旧钩子翻译层删除(D7) | 无 |
| **A** | 引擎:转移所有者 + `edge_start`/`edge_end` + `edge_transition_id` + `phase_execution_id`(3.1/3.2/D1-D4) | 0 |
| **B** | 前端:执行段分段模型 + scope 改读标识 + 删除幽灵分支(D5/D6) | A |
| **C** | 后端:按段记账(D8) | A |

每个 PR 独立过门禁(`AGENTS.md`「CI Gates」全部),独立合并。

## 6. 验收判据

实施完成的判定,逐条可机械核验:

1. **唯一发送线路**:`grep` 全引擎源码,`\.on_(phase_start|phase_end|llm_call|tool_call|nudge|working_memory_update|dead_end_pruned|compaction)\(` 的**发送端**调用为 0 处;`callbacks/base.py` 中不再存在这 8 个钩子与 `_dispatch_legacy_event`。
2. **边段成对且完整**:任取一条真实 run 的 `trace.jsonl`,`edge_start` 与 `edge_end` 条数相等;每个 `edge_transition_id` 恰好出现一次 start 与一次 end;段内所有边操作事件的 `edge_transition_id` 都能在 start 集合中找到。
3. **空转移不消失**:构造一条无黑板变换的边,其 run 的 trace 中仍有该转移的 `edge_start`/`edge_end` 一对。
4. **节点执行可区分**:构造一个被外层循环执行 3 次的节点,其 `phase_start` 携带 3 个互不相同的 `phase_execution_id`。
5. **消费方零推断**:前端 `utils/trace-scope.ts` 中不再存在按 `phase_name` 判定边归属的分支;`lib/edge-context.ts` 中不再出现字符串 `edge_transition`。
6. **前端分段平级**:Trace 面板对一条真实 run 渲染出的分段序列中,节点段与边段交替出现,且边段数等于该 run 的 `edge_start` 条数。
7. **后端按段记账**:发生在边段内的错误出现在报告的该边段名下,不出现在下游节点名下。
8. **门禁**:`AGENTS.md`「CI Gates」全部本地跑绿(ruff / mypy --strict ×2 / mypy 后端 / pytest ×3 / 前端 lint+typecheck+test+build / pip-audit)。
9. **真机**:合并后按 `.claude/skills/studio-verify` 在真窗口逐项点验并交五列报告;未取得实测的条目不打勾。
