---
module: 02-mechanism/05-run-inner/02-middleware
doc: baseline
status: drafted（PR D 回写 2026-08-15:顺序契约扩为 8 槽——新增 Compaction(SummarizationMiddleware 包装 + sidecar 可观测);live 装配另前置 RuntimeInput/ToolHistoryIntegrity 2 槽,create_agent 共挂 10 个中间件）
---

# 02-middleware — Baseline(当下代码实现逻辑)

> **Scope**: 中间件链的基础设施现状:`factory.py`(链工厂)、`__init__.py`(顺序契约)、各槽类的真实 hook 行为。
> **现状一句话**:8 槽工厂 `build_middleware_chain`(`factory.py:35`)按 `MVP0_MIDDLEWARE_ORDER_CONTRACT`(`middleware/__init__.py:65`)返回 8 个槽;live AGENT phase 在 `_build_skill_node` 调用该工厂(`graph_assembler.py:2024`)后,再前置 RuntimeInput、ToolHistoryIntegrity 2 槽,共 10 个中间件传给 `create_agent(middleware=...)`(`graph_assembler.py:2068`)。契约 8 槽:前 3 槽负责协议/认知流/执行控制;第 4 槽 Compaction 做超窗摘要压缩(2026-08-15 决议 §3.6 从死家族迁入);Tracing/ToolError/LoopDetection 为 WS-E2 最小行为;ExitControl 为 WS-E8 退出闸。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. 顺序契约 + 工厂
`MVP0_MIDDLEWARE_ORDER_CONTRACT`(`middleware/__init__.py:65`)固定 8 槽顺序:①ProtocolValidation(T7)②CognitiveFlow(T8)③ExecutionControl(T9)④Compaction(2026-08-15 决议 §3.6)⑤Tracing ⑥ToolError ⑦LoopDetection ⑧ExitControl(WS-E8)。`build_middleware_chain(...)`(`factory.py:35`)按该顺序实例化 8 槽 → `tuple[AgentMiddleware, ...]`。
> **middleware 第一次出现需定义**:agent loop 的 hook 链(before/after_model、wrap_tool_call、after_agent),不改 loop 内核就能插校验/追踪/退出治理。

### 2. 契约 8 槽现状
| 槽 | 文件 | 现状 |
|---|---|---|
| ①ProtocolValidation | `protocol_validation.py` | **真实**:before/after_model 守 BusinessData 无 `_` 前缀等 |
| ②CognitiveFlow | `cognitive_flow.py` | **真实**:wrap_tool_call 截 finish_task(逻辑归 `03-cognitive`) |
| ③ExecutionControl | `execution_control.py` | **真实**:before/after_model 发 iteration 事件、检 dead-end/轻量 loop(**本域 own**) |
| ④Compaction | `compaction.py` | **真实**:sync/async `before_model` 组合 langchain `SummarizationMiddleware`(trigger=fraction 0.8 / keep=messages 20,P0-1 裁决);触发时把被移出的消息全文写 sidecar(`write_compaction_sidecar`,落 `flow.persistent_storage_config["run_dir"]` 下 `compaction/`)并发 `CompactionEvent(content_ref=sidecar 路径)`;model 缺 `profile["max_input_tokens"]` 时包 32k 兜底 shim;`model=None` 时惰性(链形不变)。逻辑细节归 `08-messages-state` |
| ⑤Tracing | `tracing.py` | **真实**:sync/async `wrap_tool_call` 调 handler 后原样返回结果;对 `ToolMessage` 结果用已有 `ToolCallEvent`/callback surface 发 phase/tool/args/result/duration_ms,`parent_node_id=None`,`node_type="tool"` |
| ⑥ToolError | `tool_error.py` | **真实**:sync/async `wrap_tool_call` 把普通 `Exception` 转 `ToolMessage(status="error")`;诊断含 phase/tool/call_id/异常类型/摘要;`GraphBubbleUp` 控制流原样 re-raise |
| ⑦LoopDetection | `loop_detection.py` | **真实**:`after_model` 在最近 ToolMessage 滑窗内按 tool name + content 重复计数;阈值命中时注入 `loop_detection_diagnostic` HumanMessage;按 signature 去重;不改 ExecutionControl dead-end/轻量 loop |
| ⑧ExitControl | `exit_control.py` | **真实**:before_model 记迭代预算、after_agent 检 finish_task 标记并 nudge/`jump_to "model"`(逻辑归 `05-exit-control`) |

### 3. 接入现状
live `_build_skill_node` 调 `build_middleware_chain(...)`(`graph_assembler.py:2024`)构造契约 8 槽——把 phase 已解析的 chat model 与 sidecar writer 显式注入 Compaction 槽(`:2036-2037`)——再前置 `RuntimeInputMiddleware` 与 `ToolHistoryIntegrityMiddleware` 2 槽(`:2053-2062`),共 10 个中间件传给 `create_agent(...)`(`:2068`)。Compaction 的槽位依据:它走 `before_model`(langchain 把所有 before_model 状态更新按链序应用在 model 节点之前),而 ToolHistoryIntegrity 的修复发生在更晚的 `wrap_model_call`(模型请求出口),所以压缩不可能破坏修复语义;槽位排在 ProtocolValidation 状态守卫之后、并保持 MVP-3 核心三槽仍是契约前缀。退出闸(after_agent)= 独立 `05-exit-control`、subagent 派发(wrap_tool_call)= 独立 `07-subagent`(都是 middleware 实现但职责独立成模块)。

## API
- `build_middleware_chain(...) -> tuple[AgentMiddleware, ...]`(`factory.py:35`,契约 8 槽;`compaction_model` / `compaction_sidecar_writer` 为 Compaction 槽的显式注入点)。
- `build_middleware_chain_cognitive_flow(phase_name)`(`factory.py:98`,单槽 helper;live AGENT phase 已改用 8 槽工厂)。

## Data Model / State
hook 读写 `WorkflowState`(flow/messages);各 hook 形态(before/after_model、wrap_tool_call、after_agent)。

## 当前边界(这个模块现在不是什么)
- **不 own 域专槽逻辑**:CognitiveFlow→`03-cognitive`、Tracing→`02-observability`、ToolError→`04-tools`、ProtocolValidation→`data-contracts`;本域只 own 链基础设施 + 纯 loop 卫生槽(ExecutionControl/LoopDetection)。
- **LoopDetection 不替代 ExecutionControl**:ExecutionControl 仍 own dead-end warning 和轻量 loop callback;LoopDetection 只做更硬的重复工具结果诊断。
- **不做 exit/nudge/subagent 新槽**:退出闸、nudge、subagent 派发仍归各自模块。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 接入 | live AGENT phase 传契约 8 槽 `build_middleware_chain`(`factory.py:35`)+ 前置 2 槽,共 10 中间件 | 保持 live 接线与顺序契约 |
| Compaction | 已 live(`compaction.py`,顺序契约第 4 槽;超窗摘要 + sidecar + CompactionEvent) | 保持;逻辑归 `08-messages-state` |
| Tracing/ToolError/LoopDetection | WS-E2 MVP1 最小 hook 行为 | 继续补齐更深 LLM tracing/loop 策略等后续目标 |

> **验"是否按 mvp1 改了"**:① live AGENT phase 是否传契约 8 槽 middleware(+前置 2 槽);② Tracing/ToolError/LoopDetection 是否有真实 hook 行为(Tracing 覆盖不减、ToolError 转 error ToolMessage、LoopDetection 不与 ExecutionControl 重复);③ 顺序契约回归测试(`tests/middleware/test_compaction.py` / `tests/core/test_gamma0_contract_tdd.py`)钉住 8 槽顺序。

## 读代码主路径提示
顺序契约 `__init__.py:65` → 工厂 `factory.py:35`(8 槽)/`:98`(单槽 helper)→ live 接线 `graph_assembler.py:2024`(工厂)+ `:2053-2062`(前置 2 槽)+ `:2068`(create_agent)→ 前 3 真实槽 `protocol_validation/cognitive_flow/execution_control.py` → Compaction `compaction.py` → WS-E2 槽 `tracing/tool_error/loop_detection.py` → 退出闸 `exit_control.py`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `01-agent-loop`(接入点)· `03-cognitive`/`06-seam/02-observability`/`04-tools`/`data-contracts`(域专槽,双向)· `05-exit-control`/`07-subagent`(独立模块)
