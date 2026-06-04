---
module: 02-mechanism/05-run-inner/07-subagent
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；派发 helper 已存在,但内联在手写 loop、未收进 wrap_tool_call 中间件）
---

# 07-subagent — Baseline(当下代码实现逻辑)

> **Scope**: 运行期子代理派发的现状:`graph_assembler.py` 的 subagent helper(`_invoke_subagent_tool_t21` / `_invoke_subagent_once_t23` / `_subagent_runtime_map`)、`subagents.py`(depth/校验)。
> **现状一句话**:运行期子代理派发的 helper 都在(`_invoke_subagent_tool_t21` `graph_assembler.py:1057` 等),但当前是**内联在手写 ReAct loop 里**调用(`_skill_node` 命中 subagent 工具时调 `:536`),**还没收进 `create_agent` 的 `wrap_tool_call` 中间件**。lifecycle 事件(start/end/error)缺(A2)。区别于 SUBGRAPH(编译期子图,归 `02-resolver`/`01-compile`,断层#7)。

## UI/UX
N/A。

## 前端逻辑
N/A。

## 后端功能

### 1. 派发 helper(graph_assembler.py)
- `_subagent_tool_map(phase_id, compiled)`(`:692`):把 `compiled.subagents_by_phase` 映射成 `call_subagent_<name>` 工具名。
- `_subagent_runtime_map(...)`(`:1120`):为每个 subagent 预编译 + 装配 child graph(runtime map)。
- `_invoke_subagent_tool_t21(...)`(`:1057`):派发入口——读 depth(`current_subagent_depth`)→ `assert_subagent_depth_allowed`(`subagents.py:155`)→ 维护 `flow["subagent_validation_retries"]`(`:1071`)→ 校验参数 → 调 child。
- `_invoke_subagent_once_t23(...)`(`:1158`):单次子任务,child config 保留 `parent_run_id`(`:1091/1227/1245`)、`subagent_depth`、tags。

### 2. depth / 校验(subagents.py)
`SubagentValidationFailure`(`subagents.py:16`)、`current_subagent_depth(flow)`(`:150`)、`assert_subagent_depth_allowed(depth)`(`:155`)。

### 3. 当前接入点(内联,非中间件)
现 `_skill_node`(手写 loop)命中 `call_subagent_*` 工具时直接 `_invoke_subagent_tool_t21`(`graph_assembler.py:536`)。**mvp1 要收进 `wrap_tool_call` 中间件**(`SubagentDispatchMiddleware`),让 create_agent 路径下也走 engine dispatcher。
> **wrap_tool_call 第一次出现需定义**:middleware hook,包住每次工具调用——可拦截/改写/派发特定工具(这里:把 `call_subagent_*` 派发成一次 child graph 运行)。

## API
- `_invoke_subagent_tool_t21(tool_name, subagent, args, state, flow, runtime, parent_config)`(`:1057`)——派发入口。
- `assert_subagent_depth_allowed(depth)`(`subagents.py:155`)/ `current_subagent_depth(flow)`(`:150`)——depth guard。

## Data Model / State
读 `state`/`flow`(WorkflowState),维护 `flow["subagent_validation_retries"]`(`:1071`)、`subagent_depth`、child config 的 `parent_run_id`(`:1091`)。child data = 父全量 data + input。

## 当前边界(这个模块现在不是什么)
- **运行期,不是编译期**:派发是运行时(LLM tool call 触发);SUBGRAPH 是编译期子图(归 `02-resolver`,断层#7)。
- **现内联、未中间件化**:helper 在,但挂在手写 loop 里,没做成 `wrap_tool_call` 中间件。
- **lifecycle 事件缺(A2)**:start/end/error 事件未补(归 `02-observability`)。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 接入 | 内联在手写 loop(`graph_assembler.py:536`) | 收进 `wrap_tool_call` 中间件(独立模块) |
| create_agent 下 | 不适用(无 create_agent) | create_agent 路径仍走 engine dispatcher(depth/隔离/parent metadata 保留) |
| lifecycle 事件 | 缺(A2) | 补 start/end/error(→ `02-observability`) |
| DI | runtime map 预备 | 中间件只消费已备 map,不全局找 resolver(SA3) |

> **验"是否按 mvp1 改了"**:① create_agent 路径下 subagent 仍走 engine dispatcher(depth/隔离/parent metadata 保留);② subagent lifecycle 事件补全、trace 不缺子代理段。

## 读代码主路径提示
`_subagent_tool_map`(`:692`)→ `_subagent_runtime_map`(`:1120`)→ 派发入口 `_invoke_subagent_tool_t21`(`:1057`)→ 单次 `_invoke_subagent_once_t23`(`:1158`);depth 看 `subagents.py:150/155`;现接入点 `_skill_node` `:536`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `02-middleware`(本域=wrap_tool_call 中间件)· `02-resolver`(SUBGRAPH 对照,断层#7)· `06-seam/02-observability`(lifecycle)· `05-exit-control`(对称)
