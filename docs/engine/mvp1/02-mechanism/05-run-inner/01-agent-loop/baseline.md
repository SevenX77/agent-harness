---
module: 02-mechanism/05-run-inner/01-agent-loop
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；live = 手写 ReAct loop + 单槽 middleware）
---

# 01-agent-loop — Baseline(当下代码实现逻辑)

> **Scope**: AGENT phase 内层执行闭包 `_skill_node` 的装配与逐轮 ReAct loop；6 槽 middleware 工厂现状；与 `create_agent` 目标的差距。
> **现状一句话**:AGENT phase 的内层执行,用的是 `graph_assembler.py` 里**手写的 `for _ in range(max_turns)` ReAct 循环**(`_skill_node`),只接了**单个** CognitiveFlow 中间件——**没有**用 LangChain `create_agent`,**也没有**接 6 槽 middleware 链(6 槽工厂 `build_middleware_chain` 已存在,但 live 路径不调它)。这是 mvp1 要迁移的起点。

## UI/UX
N/A —— 纯 backend Python library,无 UI。AGENT loop 的过程只通过 trace 事件(`LLMCallEvent`/`ToolCallEvent`)和最终 `RunResult` 暴露,渲染归 studio。

## 前端逻辑
N/A —— React 前端不直接调 agent loop;它消费的是引擎产出的 `trace.jsonl` / `RunResult`。

## 后端功能

### 1. 主入口到内层 loop 的当前链路
SDK 顶层入口 `run_skill`(`core/runner.py:376`)/ `predict_skill`(`:163`)收 skill 路径 + 输入,经 `_run_skill_dict`(`:456`)判定 V0.3.0 skill root 后进 `_run_v030_skill_dict`(`:623`)。该函数 `resolve_checkpointer("auto")`(`:663`)→ `compile_skill`(`:666`)→ `assemble_graph(..., checkpointer=)`(`:667`)。
> **`create_agent` 第一次出现需定义**:LangChain 封装好的 "model↔tool ReAct 循环" 构造器,一次声明 `model`/`tools`/`system_prompt`/`middleware`/`checkpointer` 即得一个可 `invoke` 的 agent。**当前代码不用它**,而是自己手写循环(见 §3)。

### 2. AGENT phase 闭包的装配 `_build_skill_node`
`_build_skill_node`(`core/graph_assembler.py:423`)在装配期为每个 AGENT phase 构造执行闭包:
- `_resolve_phase_chat_model`(`:437`)解析该 phase 的模型(provider 差异下沉 gateway,见 `06-seam/01-models`)。
- 收工具:业务工具 `compiled.tools.for_phase`(`:452`)+ 资源工具(`:453`)+ subagent 工具映射 `_subagent_tool_map`/`_subagent_runtime_map`(`:455-465`)+ framework 工具 `_build_framework_tools`(`:466`)+ `finish_task`(`:474`)。
- 合成 `all_tools`(`:479`)+ `all_tools_by_name`(`:480`)。
- **关键现状**:`cognitive_flow = build_middleware_chain_cognitive_flow(phase_name=phase_id)`(`:481`)—— 只拿到**单个** `CognitiveFlowMiddleware`,不是 6 槽链。
> **`finish_task` 第一次出现需定义**:AGENT phase 的"交卷"工具,LLM 把最终 Markdown 交给它,引擎解析+校验后落 `data`(逻辑归 `03-cognitive`)。

### 3. 手写 ReAct loop `_skill_node` 的逐轮生命周期
执行闭包 `_skill_node`(`:483`)是真正跑的内层 loop:
1. 无模型 → 抛 `SkillLoadError([F-v3-agent-llm-role-unknown])`(`:487-492`)。
2. `flow = state["flow"].model_dump()`(`:495`);messages = `SystemMessage(_agent_system_prompt(...))` + `state["messages"]`(`:497-507`)。
3. `model = _bind_tools_if_supported(phase_chat_model, all_tools)`(`:508`)—— **手动 `bind_tools`**(定义 `:688`),非交给 create_agent。
4. `for _ in range(max_turns)`(`:511`;`max_turns = phase_ast.max_iterations`,`:510`):
   - `response = model.invoke(prompt_messages)`(`:513`),发 `LLMCallEvent`(`:515-524`)。
   - `tool_calls = response.tool_calls`(`:526`);**为空直接 `break`**(`:527-528`)—— 当前"裸退点",无 finish_task 合格性检查。
   - 每个 tool call:未知工具 `_graph_fatal`(`:532-533`);subagent 工具走 `_invoke_subagent_tool_t21`(`:536`),普通工具 `tool.invoke(call_args)`(`:546`);发 `ToolCallEvent`(`:547-555`);追加 `ToolMessage`(`:556-562`)。
   - `cognitive_flow.handle_finish_task_tool_result(...)`(`:563-570`):命中合格 finish_task → `return finish_response`(`:571-572`)结束 phase。
5. loop 自然结束(无 tool_calls)→ 返回 `{"flow", "messages", data_updates?}`(`:573-576`)。

### 4. 6 槽 middleware 工厂的现状(已存在,未接 live)
`build_middleware_chain`(`middleware/factory.py:29`)按 `MVP0_MIDDLEWARE_ORDER_CONTRACT`(`middleware/__init__.py:58`)返回 6 槽:ProtocolValidation / CognitiveFlow / ExecutionControl / Tracing / ToolError / LoopDetection。**但 live 的 `_build_skill_node` 只调单槽版 `build_middleware_chain_cognitive_flow`(`factory.py:68`)**,6 槽工厂目前没接进执行路径。
> **`middleware` 第一次出现需定义**:agent loop 的 hook 链(`before/after_model`、`wrap_tool_call`、`after_agent`),用来在不改 loop 内核的前提下插校验/追踪/退出治理。

## API
- `_build_skill_node(phase_id, phase_doc, phase_ast, compiled, chat_model, model_resolver, max_patch_attempts, callbacks, skill_resolver, _loading_stack, _compilation_cache, predict_context) -> _skill_node`(`graph_assembler.py:423-436`)——内部装配 API,返回 LangGraph node 闭包。
- `_skill_node(state: WorkflowState, config: RunnableConfig|None) -> dict | WorkflowState`(`:483-486`)——LangGraph 节点,读 `state["flow"]/["messages"]`,返回 state delta。
- `build_middleware_chain(...) -> tuple[AgentMiddleware, ...]`(`factory.py:29`,6 槽)vs `build_middleware_chain_cognitive_flow(phase_name) -> ...`(`:68`,单槽,live 在用)。

## Data Model / State
`_skill_node` 读写 `WorkflowState`(字段归 `data-contracts`):读 `state["flow"]`(框架字段,`.model_dump()` 成可变 dict)、`state["messages"]`(对话历史);返回 `{"flow":..., "messages":..., "data": data_updates?}`(`:573-576`)。它**不直接写业务黑板 `data`**——业务输出经 `finish_task` 落 `data`(归 `03-cognitive`);messages 持久化/checkpoint 归 `08-messages-state`。

## 当前边界(这个模块现在不是什么)
- **不是 create_agent**:loop 手写(`:511`),不是 LangChain agent。
- **不是 6 槽**:只接单槽 CognitiveFlow(`:481`);Tracing/ToolError/LoopDetection 未进 live。
- **没有退出闸**:无 tool_calls 直接 break(`:527-528`),没有 after_agent 合格性 gate(归 `05-exit-control`)。
- **内层不挂 checkpoint**:当前 loop 不在内层挂 checkpointer(mvp1 要经 `ns="<id>/agent"` 挂共享 base,归 `08-messages-state`/`03-checkpoint`)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标(alignment) |
|---|---|---|
| loop 内核 | 手写 `for _ in range(max_turns)`(`:511`)+ 手动 `bind_tools`(`:508/688`) | 一次 `create_agent` 构造 + 一次 `agent.invoke` |
| middleware | 单槽 `build_middleware_chain_cognitive_flow`(`:481`) | 6 槽 `build_middleware_chain`(`factory.py:29`) |
| 退出 | 无 tool_calls 裸退 break(`:527-528`) | after_agent 退出闸(`05-exit-control`) |
| 内层 checkpoint | 无 | 经 ns 挂共享 base(`08-messages-state`) |

> **验"代码是否按 mvp1 改了"**:① live AGENT phase 是否改调 `create_agent`、手写 loop 是否消失;② 是否传 6 槽 middleware(`build_middleware_chain` 取代单槽);③ 无 tool_calls 是否走 after_agent 闸而非裸 break。

## 读代码主路径提示
`run_skill`(`runner.py:376`)→ `_run_v030_skill_dict`(`:623`)→ `assemble_graph`(`graph_assembler.py:88`)→ AGENT 分支 `_build_skill_node`(`:423`)→ 闭包 `_skill_node`(`:483`)→ 手写 loop `:511`。6 槽工厂对照 `middleware/factory.py:29`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `03-assemble`(`_build_skill_node` 构造)· `02-middleware`(6 槽)· `03-cognitive`(finish_task)· `05-exit-control`(退出闸)· `06-seam/01-models`(模型解析)· `08-messages-state`(messages/checkpoint)
