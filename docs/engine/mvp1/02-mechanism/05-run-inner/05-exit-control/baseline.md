---
module: 02-mechanism/05-run-inner/05-exit-control
doc: baseline
status: audited-ready（WS-E8 exit gate + 双闸 nudge 适配器已落地,2026-08-15 迁移决议 §3.5）
---

# 05-exit-control - Baseline（当前代码实现逻辑）

> **Scope**: AGENT phase 退出治理现状：`ExitControlMiddleware`、`NudgePolicy` 策略模块、`finish_task` marker 放行、双闸 nudge、预算耗尽失败。
> **现状一句话**: live AGENT 路径的退出闸已携带完整 nudge 策略——策略语义(三闸 + 文案 + 预算 + 结构化自检判定)从死侧 `core/nudge_injector.py` + `cognitive/finish.py` 迁入 `middleware/nudge_policy.py` 成为唯一策略源,`ExitControlMiddleware` 作为唯一适配器消费它:planning 闸挂 `after_model`,selfcheck/standard 闸挂 `after_agent`,每次注入发 typed `NudgeEvent`,预算耗尽显式失败。

## UI/UX

N/A。

## 前端逻辑

N/A。

## 后端功能

### 1. NudgePolicy 策略模块（`middleware/nudge_policy.py`,唯一策略源）

纯决策逻辑,无 IO、无事件、无 message 构造(注入与事件归适配器)。承载:

- **三闸**:`try_planning`(有文本输出、无 tool_calls、`working_memory` 无 "plan" 键)/ `try_selfcheck`(finish payload:schema failed → 原样回显校验错误文本且**不计数**;过结构化自检 bar → 不 nudge;否则 SELFCHECK_NUDGE)/ `try_standard`(有文本无 tool_calls 的兜底,`build_standard_nudge_text` 递进文案:1→温和,2→"[系统警告] 这是第二次提醒"+600 字截断回显,3+→严重警告)。
- **文案常量**:PLANNING_NUDGE / SELFCHECK_NUDGE / MIN_FINISH_REASONING_LEN=30 从死侧 `cognitive/finish.py` 迁入本模块(死侧文件已随整族删除移除)。
- **预算**:统一 check-before-increment——条件命中但预算不足时**不**计数(死侧 planning/standard 的 increment-before-check FIXME quirk 已按迁移决议 §3.5 目标设计 5 修复,`tests/middleware/test_nudge_policy.py` 钉死反例序列);per-kind 上限 `max_nudges`(默认 1,用户裁决 Task 6.5),全局上限 `max_nudges * 2`。
- **结构化自检判定** `_has_structured_selfcheck`:business_data_md 非空且 schema passed、或 diagnostics_md ≥30 字、或 reasoning ≥30 字,任一满足即放行。

### 2. ExitControlMiddleware 适配器（`middleware/exit_control.py`）

- `before_model` / `abefore_model`:按 thread 键累加迭代计数(`_iterations_by_thread`,实例字段、非 flow 通道——flow 写入会与同超步其他 flow 写者竞争 reducer-less LastValue 通道);无合格 finish 且超 `max_iterations`(读 `config.configurable.max_iterations`)→ 抛 `[F-v3-agent-exit-control-failed]`。
- `after_model` / `aafter_model`(**planning 闸**,`@hook_config(can_jump_to=["model"])`):无合格 finish 时咨询 `try_planning`;命中 → 注入 PLANNING_NUDGE `HumanMessage` + 发 NudgeEvent + `jump_to "model"`。jump 在 loop 结束前发生,因此同一回合不会再被 after_agent 教育(同一失败只教育一次)。plan 存在性读 `flow.working_memory` 的 `WORKING_MEMORY_PLAN_KEY`("plan",公共常量定义在 `cognitive_flow.py`,写方 CognitiveFlow / 读方 ExitControl 共享同一契约)。
- `after_agent` / `aafter_agent`(**selfcheck / standard 闸**):
  - 合格 marker(`schema_validation == "passed"` 且 `phase_name` 是本相)→ 放行(返回 None;`jump_to "end"` 会无限重入 after_agent,2026-08-14 复现)。
  - 迭代耗尽 → fatal。
  - 尾消息有 tool_calls → `jump_to "model"`(工具活动按迭代预算继续,不算 nudge 条件)。
  - 本相 unqualified finish marker 存在 → `try_selfcheck`(活路径上 CognitiveFlow 只写合格 marker,此分支为防御性;策略语义由单测钉死)。
  - `try_standard` 命中 → 注入 + NudgeEvent + `jump_to "model"`。
  - 预算耗尽(`budget_exhausted`)→ 抛 `[F-v3-agent-exit-control-failed]`(消息含 nudge 计数快照)——多次 nudge 仍无合格 finish 不静默 END。
  - 策略无意见(尾部无 AI 文本,如 loop 结束在 ToolMessage 上)→ `jump_to "model"`,迭代预算治理。
- nudge 计数与迭代计数同款 per-thread 隔离(`_nudge_policy_by_thread`):同一 compiled graph 复用时每个 invoke 预算独立(`test_nudge_budget_is_scoped_per_graph_invoke` 钉死)。
- **事件**:每次注入发 typed `NudgeEvent`(phase_name / nudge_count=该类第几次 / nudge_type=planning|selfcheck|standard / message 整句),经 `_safe_emit_event`;死侧旧式 `on_nudge` 回调通道不在活侧存在。

### 3. 接线（factory / assembler）

- `middleware/factory.py` `build_middleware_chain(..., max_nudges=DEFAULT_MAX_NUDGES)` 构造第 7 slot `ExitControlMiddleware(phase_name, callbacks, max_nudges)`。
- `graph_assembler._build_skill_node` 不传 `max_nudges`(AgentNodeAST 尚无该字段,活路径按默认 1 运行);`finish_task.return_direct = True` 为**无条件**设置(v0.3.0 认知模板恒挂 finish_task,声明内建名反而是 `[F-v3-agent-tool-reserved]` 诊断)。
- 顺序契约不变:`ProtocolValidation -> CognitiveFlow -> ExecutionControl -> Tracing -> ToolError -> LoopDetection -> ExitControl`(+ 前置 RuntimeInput、ToolHistoryIntegrity 两槽)。

### 4. 与 CognitiveFlowMiddleware 的分工（同一失败不双重教育）

- **CognitiveFlow = 环内纠错**:finish_task 提交被 schema/business 校验驳回时,以 `_REJECTION_PREFIX` + 错误清单作 ToolMessage 回给模型并继续循环;这是"校验纠错",不消耗 nudge 预算——与死侧 try_selfcheck 的 `schema_validation=="failed"` 不计数分支同一语义,但活侧由 CognitiveFlow 独家承担(驳回不写 marker,循环不落到 after_agent)。
- **ExitControl = 出口治理**:只在 loop 试图结束时行动。planning 闸在 after_model 抢先 jump,使该回合不会同时落入 after_agent 的 standard 闸。
- 附带修复(同 PR):CognitiveFlow 的 update_working_memory / log_ambiguity 拦截 Command 摘除了 `goto="model"`——ToolNode 内的 Command goto 会与 tools→model 常规边双路由,把循环分叉成两条并行 model 车道(幻影回合);回灌由常规边负责。`_reject_finish` 与澄清分支的同款 goto 属遗留缺陷,另行处置(见交付台账)。

## API

- `NudgePolicy(max_nudges=1)`:`try_planning` / `try_selfcheck` / `try_standard` → `NudgeDecision(text, kind, count, counted, budget_exhausted)`;`counts()` 快照。
- `ExitControlMiddleware(phase_name, callbacks, max_nudges)`:AGENT phase 退出闸 + nudge 适配器。
- `build_middleware_chain(..., max_nudges=1)`。
- `WORKING_MEMORY_PLAN_KEY`(`middleware/cognitive_flow.py`):working memory 计划键的公共契约常量。
- 错误码:`[F-v3-agent-exit-control-failed]`(迭代耗尽与 nudge 预算耗尽共用,消息区分)。
- 事件:`NudgeEvent(phase_name, nudge_count, nudge_type, message)`。

## Data Model / State

- `FrameworkState.finish_task_result`:finish_task 成功 marker,仍由 `CognitiveFlowMiddleware` 写入(含 `phase_name` 标注)。
- `FrameworkState.working_memory["plan"]`:planning 闸的触发依据(存在即视为已有计划;该键跨 phase 存续,前一 phase 写过 plan 会抑制后续 phase 的 planning 闸——迁移决议 §3.5 目标设计 3 的字面语义)。
- 迭代计数与 nudge 计数都在 middleware 实例字段按 thread 键存放,不进 flow 通道。

## 当前边界（这个模块现在不是什么）

- 不是 checkpoint / resume / state migration 方案。
- 不替代 CognitiveFlow 的 finish_task 校验驳回流(见分工)。
- 死侧 `core/nudge_injector.py` / `cognitive/finish.py` 已随 2026-08-15 决议 §5 的整族删除移除;本模块是 nudge 策略的唯一所在。

## baseline / alignment 差异（测试锚点）

| 维度 | 当前 baseline | mvp1 目标 |
|---|---|---|
| 退出裁决 | `after_agent` 统一裁决,合格 finish_task 才放行 | 已对齐 |
| nudge 策略 | `NudgePolicy` 唯一策略源 + ExitControl 唯一适配器(WS-E8「middleware 侧适配器,不复制新策略」) | 已对齐:alignment §8 gap 2「NudgeInjector 策略收口」关闭 |
| 三闸挂点 | planning=after_model,selfcheck/standard=after_agent + `jump_to "model"` 回灌 | 已对齐 |
| 事件 | typed NudgeEvent(类型+计数),无 on_nudge 通道 | 已对齐 |
| 预算 | check-before-increment;max_nudges 默认 1;全局 2×;耗尽显式失败 | 已对齐(quirk 已修) |
| 耗尽 | `[F-v3-agent-exit-control-failed]` `GraphAgentFatalError` | 已对齐 |

## 验证锚点

- `packages/graph-agent/tests/middleware/test_nudge_policy.py`——三闸触发条件、schema-failed 不计数分支、预算/上限、quirk 修复反例、递进文案与 600 字截断。
- `packages/graph-agent/tests/middleware/test_nudge_exit_gate_adapter.py`——planning/standard 图级触发、NudgeEvent 字段、预算耗尽显式失败、per-invoke 预算隔离。
- `packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py`——退出闸既有语义回归(首记 nudge 现为 PLANNING_NUDGE)。
- `packages/graph-agent/tests/middleware/test_cognitive_tools_interception.py`——state-tool Command 无 goto(双路由分叉回归钉)。
- 回归覆盖:middleware topology / gamma0 contract / tool-call history integrity。

## 读代码主路径提示

`graph_assembler._build_skill_node` → `middleware/factory.build_middleware_chain(max_nudges)` 构造第 7 slot → `CognitiveFlowMiddleware._handle_finish_task` 写 marker → `ExitControlMiddleware.after_model`(planning 闸)/ `.after_agent`(selfcheck/standard 闸 + 放行/失败)→ `middleware/nudge_policy.NudgePolicy` 出决定。

## 交叉引用（链接，不复制）

mvp1-alignment（目标）· `02-middleware`（本域=after_model/after_agent 中间件）· `03-cognitive`（finish_task marker + WORKING_MEMORY_PLAN_KEY,双向）· `07-subagent`（对称）· `data-contracts`（finish_task_result）· 迁移决议 `docs/design/2026-08-15-legacy-cognitive-features-migration-decision.md` §3.5
