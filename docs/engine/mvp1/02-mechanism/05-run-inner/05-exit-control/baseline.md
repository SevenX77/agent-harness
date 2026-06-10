---
module: 02-mechanism/05-run-inner/05-exit-control
doc: baseline
status: implemented-audited（WS-E8 exit gate 已接入 create_agent middleware 链路）
---

# 05-exit-control - Baseline（当前代码实现逻辑）

> **Scope**: AGENT phase 退出治理现状：`ExitControlMiddleware`、`finish_task` marker 放行、无完成信号 nudge、预算耗尽失败。
> **现状一句话**: live AGENT 路径已接入 `after_agent` 退出闸；合格 `finish_task` 不再由 `CognitiveFlowMiddleware` 直接 `goto=END`，而是先写入 `FrameworkState.finish_task_result` marker，再由 `ExitControlMiddleware.after_agent` 观察 marker 后放行成功结束。

## UI/UX

N/A。

## 前端逻辑

N/A。

## 后端功能

### 1. ExitControlMiddleware（已实现）

`middleware/exit_control.py` 定义 `ExitControlMiddleware`，作为 LangChain `AgentMiddleware` 接入 `create_agent` 链路。

当前职责：

- `before_model`：当当前 phase 显式声明 `finish_task` 时，在 `flow.working_memory` 中累加 phase-scoped 迭代计数，键名形如 `exit_control_iteration_{phase_name}`。
- `after_agent`：统一裁决 AGENT phase 是否允许结束。
- 合格 `finish_task_result` 存在且 `schema_validation == "passed"` 时，返回 `{"jump_to": "end"}` 放行。
- 无合格完成 marker 且预算未耗尽时，返回 `{"jump_to": "model"}` 让 agent loop 继续。
- 无 tool calls 且无完成 marker 时，额外注入一条可见 `HumanMessage` nudge，文案包含 `finish_task`，提醒模型提交最终输出。
- 预算耗尽时抛出 `GraphAgentFatalError`，错误文本包含 `[F-v3-agent-exit-control-failed]`。

### 2. 显式接线（已实现）

`graph_assembler._build_skill_node` 在装配 AGENT phase 时显式判断 `phase_ast.tools` 是否声明 `"finish_task"`：

- 若声明了 `finish_task`，设置 `finish_task.return_direct = True`。
- 将 `has_finish_task` 显式传入 `build_middleware_chain(...)`。

`middleware/factory.py` 将 `has_finish_task` 传给 `ExitControlMiddleware`。`middleware/__init__.py` 将 `"ExitControl"` 注册为 middleware order contract 的第 7 个 slot，既有 6 个 slot 的相对顺序保持不变：

`ProtocolValidation -> CognitiveFlow -> ExecutionControl -> Tracing -> ToolError -> LoopDetection -> ExitControl`

### 3. finish_task 成功路径（已调整）

`CognitiveFlowMiddleware._handle_finish_task` 仍负责：

- 校验 `finish_task` 入参和业务 schema。
- 写入 `FrameworkState.finish_task_result`。
- 保留 `reasoning`、`diagnostics_md`、`business_data_md`、`schema_validation`、`business_data_parsed` 等 marker 语义。
- 写入解析后的业务输出。

已移除 accepted `finish_task` 返回 `Command(..., goto=END)` 的直接结束行为。成功出口现在由 `ExitControlMiddleware.after_agent` 统一放行。

### 4. NudgeInjector（既有模块，未作为 exit gate 策略引擎接入）

`core/nudge_injector.py` 的 `NudgeInjector`、`NudgeOutcome`、`build_standard_nudge_text` 仍是既有 nudge 状态机能力。当前 WS-E8 live exit gate 没有复制或改写该模块，也没有新增 middleware-side nudge adapter。

当前 `ExitControlMiddleware` 的 no-tool-call nudge 是局部、最小实现：直接向 messages 注入一条包含 `finish_task` 的 `HumanMessage`，满足“模型可见 nudge 并继续 loop”的退出治理契约。

## API

- `ExitControlMiddleware(phase_name, callbacks, has_finish_task)`：AGENT phase 退出闸 middleware。
- `build_middleware_chain(..., has_finish_task=False)`：显式传入当前 phase 是否声明 `finish_task`。
- `MVP0_MIDDLEWARE_ORDER_CONTRACT`：现包含第 7 个 `"ExitControl"` slot。
- 错误码：`[F-v3-agent-exit-control-failed]`，注册为运行期 FATAL。

## Data Model / State

- `FrameworkState.finish_task_result`：`finish_task` 成功 marker，仍由 `CognitiveFlowMiddleware` 写入。
- `FrameworkState.working_memory`：当前用于保存 exit-control 迭代计数，键名形如 `exit_control_iteration_{phase_name}`。该计数跟随单次 graph invoke / thread 的 flow state，不存放在 middleware 实例字段上，因此同一个 compiled graph 连续多次 invoke 时不会串用预算。
- `BusinessData`：只接收 `finish_task` 解析出的业务输出，不承载 exit-control 内部计数。

## 当前边界（这个模块现在不是什么）

- 不是 WS-E2 的 tracing / tool-error / loop-detection 真实实现；这些 slot 仍保持各自既有行为。
- 不是 checkpoint / resume / state migration 方案；没有修改 `checkpointer.py`、`state.py`、`runner.py`、`result.py`。
- 不是完整 nudge 策略重写；core `NudgeInjector` 仍独立存在，exit gate 只做最小可见 nudge。
- `flow.working_memory` 中的 `exit_control_iteration_{phase_name}` 是当前实现的内部可见计数；后续若需要更强隔离或隐藏，可在状态治理专题中收口。

## baseline / alignment 差异（测试锚点）

| 维度 | 当前 baseline | mvp1 目标 |
|---|---|---|
| 退出裁决 | `ExitControlMiddleware.after_agent` 统一裁决 | 已对齐：合格 finish_task 才 END |
| 成功路径 | `CognitiveFlow` 写 marker 和业务输出，不再直接 `goto=END` | 已对齐：成功出口落在 after_agent gate |
| 无 tool calls | exit gate 注入包含 `finish_task` 的 nudge 并回到 model，预算耗尽失败 | 已对齐：不得裸退成功 |
| 耗尽 | 抛出包含 `[F-v3-agent-exit-control-failed]` 的 `GraphAgentFatalError` | 已对齐：明确失败/诊断 |
| 预算作用域 | 迭代计数存入当前 flow state，不存 middleware 实例字段 | 已对齐：同 graph 复用不串预算 |

## 验证锚点

- `packages/graph-agent/tests/core/test_ws_e8_exit_gate_red.py`
  - `test_agent_without_finish_task_returns_explicit_failure`
  - `test_no_tool_calls_gets_nudged_back_to_model_before_success`
  - `test_max_iterations_exhaustion_is_failure_not_empty_success`
  - `test_finish_task_marker_preserves_schema_fields_and_business_output`
  - `test_finish_task_success_must_pass_through_after_agent_exit_gate`
  - `test_exit_gate_iteration_budget_is_scoped_to_each_graph_invoke`
- 回归覆盖：
  - WS-E1 create_agent core / e2e / Gamma0 contract
  - Gamma2 subagent isolation / state IO
  - WS-E1 logic / iterate / subgraph IO
  - middleware topology / cognitive flow schema gate / nudge injector

## 读代码主路径提示

`graph_assembler._build_skill_node` 显式识别 `finish_task` 并传入 `has_finish_task` -> `middleware/factory.py` 构造第 7 个 `ExitControlMiddleware` slot -> `CognitiveFlowMiddleware._handle_finish_task` 写 marker 和业务输出 -> `ExitControlMiddleware.after_agent` 观察 marker 后放行，或 nudge / 耗尽失败。

## 交叉引用（链接，不复制）

mvp1-alignment（目标）· `02-middleware`（本域=after_agent 中间件）· `03-cognitive`（finish_task marker，双向）· `07-subagent`（对称）· `data-contracts`（finish_task_result）
