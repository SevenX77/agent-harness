---
module: 02-mechanism/05-run-inner/02-middleware
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；6 槽工厂存在,live 只接单槽;后 3 槽 no-op）
---

# 02-middleware — Baseline(当下代码实现逻辑)

> **Scope**: 6 槽中间件链的基础设施现状:`factory.py`(链工厂)、`__init__.py`(顺序契约)、6 个槽类(哪些真实、哪些 no-op)。
> **现状一句话**:6 槽工厂 `build_middleware_chain`(`factory.py:29`)存在,按 `MVP0_MIDDLEWARE_ORDER_CONTRACT` 返回 6 个槽;但 **live AGENT 闭包只接单槽** `build_middleware_chain_cognitive_flow`(`:68`,见 `01-agent-loop`/`03-assemble`)。6 槽里**前 3 真实**(ProtocolValidation/CognitiveFlow/ExecutionControl)、**后 3 是 no-op 空壳**(Tracing/ToolError/LoopDetection,各 16 行)。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. 顺序契约 + 工厂
`MVP0_MIDDLEWARE_ORDER_CONTRACT`(`middleware/__init__.py:58`)固定 6 槽顺序:①ProtocolValidation(T7)②CognitiveFlow(T8)③ExecutionControl(T9)④Tracing ⑤ToolError ⑥LoopDetection(后 3 标 TBD/PR γ0)。`build_middleware_chain(...)`(`factory.py:29`)按该顺序实例化 6 槽 → `tuple[AgentMiddleware, ...]`。
> **middleware 第一次出现需定义**:agent loop 的 hook 链(before/after_model、wrap_tool_call、after_agent),不改 loop 内核就能插校验/追踪/退出治理。

### 2. 6 槽现状(3 真 3 空)
| 槽 | 文件 | 现状 |
|---|---|---|
| ①ProtocolValidation | `protocol_validation.py`(213 行) | **真实**:before/after_model 守 BusinessData 无 `_` 前缀等 |
| ②CognitiveFlow | `cognitive_flow.py`(984 行) | **真实**:wrap_tool_call 截 finish_task(逻辑归 `03-cognitive`) |
| ③ExecutionControl | `execution_control.py`(343 行) | **真实**:before/after_model 发 iteration 事件、检 dead-end/轻量 loop(**本域 own**) |
| ④Tracing | `tracing.py`(16 行) | **no-op 空壳**(逻辑归 `02-observability`) |
| ⑤ToolError | `tool_error.py`(16 行) | **no-op 空壳**(逻辑归 `04-tools`) |
| ⑥LoopDetection | `loop_detection.py`(16 行) | **no-op 空壳**(本域 own,实现前先复核 ExecutionControl 已有轻量 loop) |

### 3. 接入现状
live `_build_skill_node` 只调 `build_middleware_chain_cognitive_flow`(`factory.py:68`,单个 CognitiveFlow),**没接 6 槽**(见 `01-agent-loop` §4)。退出闸(after_agent)= 独立 `05-exit-control`、subagent 派发(wrap_tool_call)= 独立 `07-subagent`(都是 middleware 实现但职责独立成模块)。

## API
- `build_middleware_chain(...) -> tuple[AgentMiddleware, ...]`(`factory.py:29`,6 槽,目标)。
- `build_middleware_chain_cognitive_flow(phase_name)`(`:68`,单槽,live)。

## Data Model / State
hook 读写 `WorkflowState`(flow/messages);各 hook 形态(before/after_model、wrap_tool_call、after_agent)。

## 当前边界(这个模块现在不是什么)
- **不 own 域专槽逻辑**:CognitiveFlow→`03-cognitive`、Tracing→`02-observability`、ToolError→`04-tools`、ProtocolValidation→`data-contracts`;本域只 own 链基础设施 + 纯 loop 卫生槽(ExecutionControl/LoopDetection)。
- **后 3 槽还没逻辑**:no-op 空壳。
- **没接进 live**:6 槽工厂在,live 只用单槽。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 接入 | live 单槽(`factory.py:68`) | live 接 6 槽 `build_middleware_chain`(`:29`) |
| 后 3 槽 | no-op(各 16 行) | Tracing/ToolError/LoopDetection 实现到位(逻辑归各域) |

> **验"是否按 mvp1 改了"**:① live AGENT phase 是否传 6 槽 middleware;② 后 3 槽是否从 no-op 实现到位(Tracing 覆盖不减、ToolError 转 error ToolMessage、LoopDetection 不与 ExecutionControl 重复)。

## 读代码主路径提示
顺序契约 `__init__.py:58` → 工厂 `factory.py:29`(6 槽)/`:68`(单槽 live)→ 前 3 真实槽 `protocol_validation/cognitive_flow/execution_control.py` → 后 3 空壳 `tracing/tool_error/loop_detection.py`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `01-agent-loop`(接入点)· `03-cognitive`/`06-seam/02-observability`/`04-tools`/`data-contracts`(域专槽,双向)· `05-exit-control`/`07-subagent`(独立模块)
