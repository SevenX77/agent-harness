---
module: 02-mechanism/03-assemble
doc: baseline
status: drafted（现状对齐 pinned 代码 7cd4b9c；装配 = assemble_graph 建 StateGraph + 按类型建节点闭包）
---

# 03-assemble — Baseline(当下代码实现逻辑)

> **Scope**: 把可信 AST(`CompiledSkill`)装配成可运行 LangGraph 的机制:`assemble_graph`(建 `StateGraph`、按拓扑加 node/edge)、`_build_phase_node`(按 AST 类型分发 LOGIC/SUBGRAPH/AGENT)、`_build_skill_node`(AGENT 闭包构造)、reference-reader(装配期 builtin)、cognitive 模板渲染。
> **现状一句话**:`assemble_graph`(`graph_assembler.py:88`)建 `StateGraph(WorkflowState)`(`:106`),遍历 phases 用 `_build_phase_node`(`:158`)按类型建节点闭包、连 START/dep/END 边,末 `builder.compile(checkpointer=)`(`:151`)出 `CompiledStateGraph`(`:75`)。AGENT 闭包 `_build_skill_node`(`:423`)在装配期收工具 / 渲染 prompt / 建 finish_task;它产出的 loop 内核见 `01-agent-loop`。

## UI/UX
N/A —— 纯 backend。装配产物是内存里的 `CompiledStateGraph`,无 UI。

## 前端逻辑
N/A。

## 后端功能

### 1. assemble_graph:建图 + 加节点 + 连边
`assemble_graph(compiled, *, checkpointer=, ...)`(`:88`):
1. `builder = StateGraph(WorkflowState)`(`:106`)。
   > **`StateGraph`(LangGraph)第一次出现需定义**:声明式图执行框架——声明 node + edge,运行时按依赖调度 node、用 reducer 合并各 node 返回的 state delta。
2. 遍历 phases:每 phase `builder.add_node(...)`(`:117`),node 函数由 `_build_phase_node`(`:158`)按 AST 类型给。
3. 连边:无依赖 phase 接 `START`(`:139`),有依赖从每个 dep 连(`:143`),终点接 `END`(`:147`)。
4. `builder.compile(checkpointer=checkpointer)`(`:151`)→ `CompiledStateGraph`(`:75/150`,含 compiled graph + 原 CompiledSkill + phase ids + edges)。

### 2. _build_phase_node:按类型分发三种节点
`_build_phase_node`(`:158`)按 phase AST 类型选闭包:
- **LOGIC** → `_build_logic_node`(`:325`)——确定性 action 节点(执行范式归 `04-run-outer/01-graph-exec`)。
- **SUBGRAPH** → `_build_subgraph_node`(`:363`)——递归编译+装配 child skill,执行时父 data 启动子图、回 delta。
- **AGENT** → `_build_skill_node`(`:423`)——内层 agent loop 闭包(见 §3)。
- phase 声明 batch 时,经 `_wrap_phase_runtime_node`(`:287`)包成 `_build_batch_wrapped_node`(`:240`)。

### 3. _build_skill_node:AGENT 闭包的装配(本域负责"建",loop 内核归 01-agent-loop)
`_build_skill_node`(`:423`)装配期做:解析模型 `_resolve_phase_chat_model`(`:437`)、`_build_reference_reader_markdown`(`:445`)、收业务/资源/subagent/framework 工具(`:452-471`)、建 `finish_task`(`build_finish_task_tool` import `:32`,调 `:474`)、合 `all_tools`(`:479`)、接 `build_middleware_chain_cognitive_flow`(`:481`,**单槽,现状**)。返回执行闭包 `_skill_node`(`:483`,逐轮 ReAct loop 归 `01-agent-loop`)。

### 4. reference-reader(装配期 builtin)+ cognitive 模板渲染
- `_build_reference_reader_markdown`(`:829`)在装配期把 phase 声明的 references 读成 markdown 注入 prompt;失败只 WARN、不中断装配。
- cognitive 模板渲染:`apply_v030_cognitive_template`(import `:36`,用 `:804`)把 8 槽 cognitive 模板渲染成 system prompt——**模板语法**归 `skill-syntax`,本域只**渲染**。

## API
- `assemble_graph(compiled, *, chat_model=None, checkpointer=None, max_patch_attempts=3, ...) -> CompiledStateGraph`(`:88-100`)——装配 API,输入须是 `CompiledSkill`(非文件入口)。
- `CompiledStateGraph`(`:75`)——含 `.graph`(已 `compile()` 的 LangGraph,可直接 `.invoke`)。

## Data Model / State
图 state = `WorkflowState`(`:106`,字段归 `data-contracts`)。装配本身无运行 state;产出的 graph 在运行时(`graph-exec`)才读写 state。checkpointer 由外层传入 `builder.compile(checkpointer=)`(`:151`,归 `03-checkpoint`)。

## 当前边界(这个模块现在不是什么)
- **不是 compiler**:输入已是校验过的 `CompiledSkill`,不重新校验(归 `01-compile`)。
- **不是 loop 内核**:它**建** AGENT 闭包,逐轮 ReAct loop 执行归 `01-agent-loop`。
- **AGENT 现状接单槽**:`build_middleware_chain_cognitive_flow`(`:481`),mvp1 要换 `create_agent` + 6 槽。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| AGENT 闭包内核 | 手写 loop + 单槽(`:481/483`) | `create_agent` 构造 + 6 槽(`01-agent-loop`) |
| LLMPhaseNode 双路线 | 并存(`phase_nodes/`,死簇) | 收口 live `assemble_graph` 单路径 |
| 装配顺序 | 现状 | 先全 AST → reference-reader → 模板渲染 → 绑 read tools |

> **验"是否按 mvp1 改了"**:① `_build_skill_node` 是否改用 `create_agent` + 6 槽;② `phase_nodes/` 第二路线是否删;③ AGENT phase 是否传 6 槽 middleware。

## 读代码主路径提示
`assemble_graph`(`:88`)→ `_build_phase_node`(`:158`,三类分发)→ AGENT 看 `_build_skill_node`(`:423`)→ reference-reader `:829`、cognitive 渲染 `:804`。LOGIC/SUBGRAPH 看 `:325`/`:363`。

## 交叉引用(链接, 不复制)
mvp1-alignment(目标)· `01-compile`(上游 AST)· `01-contract/02-skill-syntax`(模板语法,双向)· `05-run-inner/01-agent-loop`(产出的 loop)· `04-run-outer/01-graph-exec`(LOGIC/SUBGRAPH 执行)· `06-seam/01-models`(模型)· `03-checkpoint`(checkpointer 传入)
