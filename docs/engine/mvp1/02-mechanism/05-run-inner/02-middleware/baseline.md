---
module: 02-mechanism/05-run-inner/02-middleware
doc: baseline
status: drafted（WS-E2 回写 2026-06-09:6 槽 live 接入 create_agent;后 3 槽 Tracing/ToolError/LoopDetection 已有最小 MVP1 hook 行为;U7 锁）
---

# 02-middleware — Baseline(当下代码实现逻辑)

> **Scope**: 6 槽中间件链的基础设施现状:`factory.py`(链工厂)、`__init__.py`(顺序契约)、6 个槽类的真实 hook 行为。
> **现状一句话**:6 槽工厂 `build_middleware_chain`(`factory.py:29`)按 `MVP0_MIDDLEWARE_ORDER_CONTRACT` 返回 6 个槽,且 live AGENT phase 已在 `_build_skill_node` 中调用该工厂并传给 `create_agent(middleware=...)`(`graph_assembler.py:1165/1181`)。6 槽均为真实 hook 参与者:前 3 槽负责协议/认知流/执行控制;后 3 槽已有 WS-E2 最小行为(Tracing tool callback、ToolError 普通异常转 error ToolMessage、LoopDetection 重复工具结果诊断)。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. 顺序契约 + 工厂
`MVP0_MIDDLEWARE_ORDER_CONTRACT`(`middleware/__init__.py:58`)固定 6 槽顺序:①ProtocolValidation(T7)②CognitiveFlow(T8)③ExecutionControl(T9)④Tracing ⑤ToolError ⑥LoopDetection(后 3 标 TBD/PR γ0)。`build_middleware_chain(...)`(`factory.py:29`)按该顺序实例化 6 槽 → `tuple[AgentMiddleware, ...]`。
> **middleware 第一次出现需定义**:agent loop 的 hook 链(before/after_model、wrap_tool_call、after_agent),不改 loop 内核就能插校验/追踪/退出治理。

### 2. 6 槽现状(6 槽均接入,后三槽为 MVP1 最小实现)
| 槽 | 文件 | 现状 |
|---|---|---|
| ①ProtocolValidation | `protocol_validation.py`(213 行) | **真实**:before/after_model 守 BusinessData 无 `_` 前缀等 |
| ②CognitiveFlow | `cognitive_flow.py`(984 行) | **真实**:wrap_tool_call 截 finish_task(逻辑归 `03-cognitive`) |
| ③ExecutionControl | `execution_control.py`(343 行) | **真实**:before/after_model 发 iteration 事件、检 dead-end/轻量 loop(**本域 own**) |
| ④Tracing | `tracing.py` | **真实**:sync/async `wrap_tool_call` 调 handler 后原样返回结果;对 `ToolMessage` 结果用已有 `ToolCallEvent`/callback surface 发 phase/tool/args/result/duration_ms,`parent_node_id=None`,`node_type="tool"` |
| ⑤ToolError | `tool_error.py` | **真实**:sync/async `wrap_tool_call` 把普通 `Exception` 转 `ToolMessage(status="error")`;诊断含 phase/tool/call_id/异常类型/摘要;`GraphBubbleUp` 控制流原样 re-raise |
| ⑥LoopDetection | `loop_detection.py` | **真实**:`after_model` 在最近 ToolMessage 滑窗内按 tool name + content 重复计数;阈值命中时注入 `loop_detection_diagnostic` HumanMessage;按 signature 去重;不改 ExecutionControl dead-end/轻量 loop |

### 3. 接入现状
live `_build_skill_node` 调 `build_middleware_chain(...)`(`graph_assembler.py:1165`)构造 6 槽,并把 `middleware=middleware_chain` 传给 `create_agent(...)`(`:1181`)。`factory.py` 当前把 callbacks 传给 ExecutionControl 和 Tracing;ToolError/LoopDetection 当前只接 phase/config 默认值。退出闸(after_agent)= 独立 `05-exit-control`、subagent 派发(wrap_tool_call)= 独立 `07-subagent`(都是 middleware 实现但职责独立成模块)。

## API
- `build_middleware_chain(...) -> tuple[AgentMiddleware, ...]`(`factory.py:29`,6 槽,目标)。
- `build_middleware_chain_cognitive_flow(phase_name)`(`:71`,单槽 helper;live AGENT phase 已改用 6 槽工厂)。

## Data Model / State
hook 读写 `WorkflowState`(flow/messages);各 hook 形态(before/after_model、wrap_tool_call、after_agent)。

## 当前边界(这个模块现在不是什么)
- **不 own 域专槽逻辑**:CognitiveFlow→`03-cognitive`、Tracing→`02-observability`、ToolError→`04-tools`、ProtocolValidation→`data-contracts`;本域只 own 链基础设施 + 纯 loop 卫生槽(ExecutionControl/LoopDetection)。
- **LoopDetection 不替代 ExecutionControl**:ExecutionControl 仍 own dead-end warning 和轻量 loop callback;LoopDetection 只做更硬的重复工具结果诊断。
- **不做 exit/nudge/subagent 新槽**:退出闸、nudge、subagent 派发仍归各自模块。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 接入 | live AGENT phase 已传 6 槽 `build_middleware_chain`(`factory.py:29`) | 保持 6 槽 live 接线与顺序 |
| 后 3 槽 | Tracing/ToolError/LoopDetection 已有 WS-E2 MVP1 最小 hook 行为 | 继续补齐更深 LLM tracing/loop 策略等后续目标 |

> **验"是否按 mvp1 改了"**:① live AGENT phase 是否传 6 槽 middleware;② 后 3 槽是否有真实 hook 行为(Tracing 覆盖不减、ToolError 转 error ToolMessage、LoopDetection 不与 ExecutionControl 重复)。

## 读代码主路径提示
顺序契约 `__init__.py:58` → 工厂 `factory.py:29`(6 槽)/`:71`(单槽 helper)→ live 接线 `graph_assembler.py:1165/1181` → 前 3 真实槽 `protocol_validation/cognitive_flow/execution_control.py` → 后 3 MVP1 最小槽 `tracing/tool_error/loop_detection.py`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `01-agent-loop`(接入点)· `03-cognitive`/`06-seam/02-observability`/`04-tools`/`data-contracts`(域专槽,双向)· `05-exit-control`/`07-subagent`(独立模块)
