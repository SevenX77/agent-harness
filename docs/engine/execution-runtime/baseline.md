# execution-runtime (engine) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Graph 执行装配调度、主入口生命周期 run_skill、节点重试、subagent / call_subgraph 动态工具注入 (audit A4/A5)
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

runtime 的状态不会直接渲染成 Studio 面板。用户能看到的只是调用结果、异常、trace 文件或上层 Studio 自己包装后的状态；这些 UI 不属于本 engine runtime baseline。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

React 前端不会直接调用 `assemble_graph()` 或 LangGraph `graph.invoke()`。本文件只描述 Python runtime 如何把编译产物变成可执行图，以及节点执行时如何读写 state。

## 后端功能

### public `run_skill()` 生命周期

当前顶层入口是 `run_skill(skill_path, ..., **inputs) -> RunResult`，定义在 `packages/graph-agent/src/graph_agent/core/runner.py:161` 到 `packages/graph-agent/src/graph_agent/core/runner.py:173`。它会记录开始时间，然后调用 `_run_skill_dict()`，成功时把 raw dict 包成 `RunResult(success=True, context=...)`，代码在 `packages/graph-agent/src/graph_agent/core/runner.py:182` 到 `packages/graph-agent/src/graph_agent/core/runner.py:224`。

V0.3 skill root 的真实执行分支是 `_run_v030_skill_dict()`，定义在 `packages/graph-agent/src/graph_agent/core/runner.py:468` 到 `packages/graph-agent/src/graph_agent/core/runner.py:518`。它做的事很直接：接收 callbacks 参数、导入 `compile_skill` 和 `assemble_graph`、根据 `mock_llm` 得到 `chat_model`、编译 skill、装配 graph、再调用 `graph.invoke()`。

这条链路就是 audit 总结的 V2.1 主路径：`run_skill -> compile_skill -> SkillLoader.compile_skill -> assemble_graph -> LangGraph graph.invoke`，背景见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:31`。`CompiledSkill` 的结构和构建细节见 [skill-compilation/baseline.md#后端功能](../skill-compilation/baseline.md#后端功能)。

### 初始 state

`_run_v030_skill_dict()` 调用 `graph.invoke()` 时传入：

- `"data": dict(inputs)`，见 `packages/graph-agent/src/graph_agent/core/runner.py:505`。
- `"flow": {}`，见 `packages/graph-agent/src/graph_agent/core/runner.py:506`。
- `"messages": []`，见 `packages/graph-agent/src/graph_agent/core/runner.py:507`。
- `"run_id": run_id`，见 `packages/graph-agent/src/graph_agent/core/runner.py:508`。

这里的 `data` 是业务黑板，`flow` 是框架控制字段，`messages` 是 LLM 对话历史。三字段 state 语义和 reducer 细节见 [state-and-io-contract/baseline.md#data-model--state](../state-and-io-contract/baseline.md#data-model--state)。

### LangGraph 装配

`assemble_graph(compiled, *, chat_model=None, max_patch_attempts=3)` 定义在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:60`。`LangGraph` 第一次出现时需要定义：它是一个 Python 图执行框架，开发者声明 node 和 edge，运行时按依赖关系调度 node，并用 reducer 合并 node 返回的 state delta。

装配器创建 `StateGraph(BlackboardState)`，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:63`。随后它按 `compiled.manifest.phases` 遍历 phase，给每个 phase 加 node，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:68` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:76`。node 的具体函数由 `_build_phase_node()` 按 AST 类型分发，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:99` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:113`。

edge 装配根据 `depends_on` 完成：没有依赖的 phase 连接 `START`，有依赖的 phase 从每个 dep 连边，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:78` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:85`。终点 phase 连接 `END`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:87` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:89`。

返回值是 `CompiledStateGraph`，包含编译后的 graph、原始 `CompiledSkill`、phase ids 和 edge 列表，定义在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:41` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:47`，构造在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:91` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:96`。

### LOGIC node 生命周期

LOGIC node 是确定性 Python action 节点。`_build_logic_node()` 定义在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:116` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:138`。

运行时逻辑是：

1. 复制当前 `state.data` 成 `before` 和 `data`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:130`。
2. 用 `Context(data, phase_id=..., run_id=...)` 包装这份 data，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:130`。`Context` 是 action 读写黑板的 facade，例如 action 可以 `ctx.get("text")` 或 `ctx.update(clean_text="...")`。
3. 调用 action，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:131`。
4. 用 `_dict_delta(before, data)` 找出 action 通过 Context 修改出来的变化，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:132`。
5. 如果 action 显式 `return dict`，再做输出 key 校验并合入 updates，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:133` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:135`。
6. 有更新就返回 `{"data": updates}`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136`。

`_dict_delta()` 的含义是 "只交回变化的 key"，实现是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:508` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:509`。

### SUBGRAPH node 生命周期

`SUBGRAPH` 第一次出现时需要定义：它是图里的一个固定节点，执行到这个 phase 时自动调用另一个完整 V2.1 skill 子图。`_build_subgraph_node()` 定义在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:141` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:174`。

装配时，runtime 会解析子 skill root，递归 `SkillLoader(...).compile_skill(sub_root)`，再递归 `assemble_graph(sub_compiled, chat_model=...)`，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:147` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:153`。

执行时，SUBGRAPH node 把父图当前 `data` 整体复制为 `before_data`，然后用同一份 data 启动子图，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:164`。子图结束后，runtime 比较子图最终 `data` 和父图运行前 `data`，把 delta 作为 `{"data": data_updates}` 回到父图，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:165` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:172`。

这个机制会和 `shallow_dict_merge` 互动；如果 delta 写了父图已有 key，当下 reducer 会认为冲突。具体 reducer 行为见 [state-and-io-contract/baseline.md#data-model--state](../state-and-io-contract/baseline.md#data-model--state)。

### SKILL node 生命周期

`SKILL` 第一次出现时需要定义：它是 LLM ReAct phase，LLM 会拿 system prompt、tools 和 `finish_task` 工具循环工作，直到交卷或达到轮次上限。`_build_skill_node()` 定义在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:177` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:298`。

SKILL node 先收集业务 tools、subagent 动态 tools、critic/reviewer/auditor 类 framework tools，再构建 `finish_task`，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:184` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:226`。`finish_task` 第一次出现时需要定义：它是 LLM phase 的结束工具，LLM 把 Markdown 结果交给它，engine 解析并在成功时写入 `data[phase_id]`。

如果 `chat_model` 是 `None`，SKILL node 会直接抛 `RuntimeError("[F-v21-graph] SKILL phase requires chat_model")`，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:233` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。这对应 audit P0-1：public `run_skill()` 不传 mock 或真实 model 时，V2.1 SKILL phase 路径跑不起来，见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:123`。

有模型时，SKILL node 初始化 `flow` 和 `messages`，把 `SystemMessage(content=phase_ast.system_prompt)` 放在 messages 开头，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:236` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:240`。然后最多循环 `MAX_REACT_TURNS = 8` 轮，常量在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:37`。

每轮会 `inject_exit_contract(messages, phase_ast.exit_contract)`，调用模型，再把 `prompt_messages` 和 response 一起保存回 `messages`，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:243` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:246`。这就是 audit P1-3 的当前现状：exit_contract 会进入历史并在下一轮重复累积，见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:322`。

如果模型调用普通 tool，runtime 直接 `tool.invoke(call_args)`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:266` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:267`。如果模型调用 subagent tool，则走 `_invoke_subagent_tool_t21()`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:256` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:265`。

如果 tool name 是 `finish_task` 且结果 `ok`，runtime 把 `result["data"]` 写到 `data_updates[phase_id]`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:275` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:291`。这解释了当前 SKILL phase 输出默认进 `data[phase_id]`，不是展开到顶层。

### subagent 子调度

`subagent` 是 SKILL phase 里的动态工具，工具名是 `call_subagent_<name>`。编译期注入规则见 [skill-compilation/baseline.md#后端功能](../skill-compilation/baseline.md#后端功能)。

runtime 侧先把 `compiled.subagents_by_phase` 映射成 tool name，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:301` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:308`。随后 `_subagent_runtime_map()` 为每个 subagent 再编译并装配子图，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:374` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:389`。

工具调用入口 `_invoke_subagent_tool_t21()` 会读取 `current_subagent_depth(flow)` 并调用 `assert_subagent_depth_allowed()`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:311` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:324`。它还会维护 `flow["subagent_validation_retries"]`，并用 `validate_subagent_tool_args()` 校验 LLM 传入参数，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:325` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:352`。

批量执行由 `_invoke_subagent_many_t24()` 完成，默认并发是 3，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:418` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:479`。单个子任务 `_invoke_subagent_once_t23()` 的初始 child data 是 `{**before_data, **input_data}`，也就是父图全量 data 加显式 input，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:392` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:410`。

audit P1-2 指出 subagent depth 只写入 child config metadata，没有写回 child flow，见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:277`。当前代码证据是 `_subagent_runnable_config()` 在 metadata 写 `"subagent_depth": depth + 1`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:482` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:505`；但 `_invoke_subagent_once_t23()` 传给子图的 `"flow"` 仍是 `parent_state.get("flow", {})`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:400` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:404`。

### `call_subgraph` 的当前状态

`call_subgraph` 第一次出现时需要定义：它是指 "LLM 在 SKILL phase 内主动调用一个完整 graph skill" 的工具能力，和固定流程中的 SUBGRAPH phase 不同。当前代码有 SUBGRAPH phase，也有 subagent tool，但没有独立的 `call_subgraph_<name>` 动态工具族。

audit A5 把这个缺口列为 agent phase 需要 call_subgraph 工具，见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:675`。当前 `_build_skill_node()` 只把 business tools、critic tools、`finish_task` 放进 `all_tools`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:184` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:227`；subagent 工具来自 `compiled.subagents_by_phase`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:301` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:308`。没有同级的 subgraphs registry 或 `call_subgraph` 注入。

audit A4 说 subagent 抽象层级过重，见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:625`。当前实现确实要求 subagent path 是完整 skill root 且有 `GRAPH.md`，编译期证据在 `packages/graph-agent/src/graph_agent/core/loader.py:477` 到 `packages/graph-agent/src/graph_agent/core/loader.py:482`，runtime 也按完整图编译和装配，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:381` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:388`。

## API

### `run_skill`

`run_skill()` 的 Python API 在 `packages/graph-agent/src/graph_agent/core/runner.py`。它接受必填 keyword-only `workspace_dir: Path`，并接受 `mock_llm`、`thread_id`、`unattended`、`event_subscriber`、`artifact_saver`、`initial_context`、`cleanup_checkpoints_on_finish`、`skill_resolver`、`model_resolver` 和 `**inputs`。`trace_dir` 与 public `callbacks` 已从 public 签名删除；trace 与 run artifacts 统一写入 `<workspace_dir>/runs/<run_id>/`。

V0.3 分支里，runner 创建 `_CompositeEventSink` 并透传给 `assemble_graph`；默认 `_TraceJsonlSink` 写 `<workspace_dir>/runs/<run_id>/trace.jsonl`，可选 `_SubscriberSink` 调 public `event_subscriber(event)`。旧 public callbacks list 已被 T3 event_subscriber cutover 替代。

V2.1 `mock_llm` 的语义是：如果没有传 mock，则 `chat_model=None`；如果传了 mock，则把 mock 当作 chat model 给 `assemble_graph()`，代码在 `packages/graph-agent/src/graph_agent/core/runner.py:467` 到 `packages/graph-agent/src/graph_agent/core/runner.py:469`。因此现在 public API 没有在 V2.1 分支自动解析真实 LLM provider。

### `assemble_graph`

`assemble_graph(compiled, *, chat_model=None, max_patch_attempts=3)` 是 runtime 装配 API，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:60`。它要求输入已经是 `CompiledSkill`，因此不是文件系统入口。

返回的 `CompiledStateGraph.graph` 是已经 `builder.compile()` 后的 LangGraph graph，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:91` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:96`。调用方可以直接 `.invoke(state)`，而 `run_skill()` 就是在 `packages/graph-agent/src/graph_agent/core/runner.py:503` 调用这一层。

### node 内部工具 API

runtime 内部工具调用以 LangChain tool 形态运行。普通 tool 调用 `tool.invoke(call_args)`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:267`。subagent tool 的 API 则是统一接收 `inputs` 数组，由 `validate_subagent_tool_args()` 校验，入口在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:332` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:339`。

## Data Model / State

### `BlackboardState` 在 runtime 里的读写

`BlackboardState` 是 LangGraph 状态主 dict，含 `data`、`flow`、`messages`、`run_id`。字段定义见 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`，详细语义见 [state-and-io-contract/baseline.md#data-model--state](../state-and-io-contract/baseline.md#data-model--state)。

runtime 所有节点都读这个 state：

- LOGIC 读 `state.get("data", {})` 并返回 data delta，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136`。
- SUBGRAPH 把父图 data 传给子图，再返回子图 data delta，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:172`。
- SKILL 读 `flow` 和 `messages`，成功时返回 `flow`、`messages` 和可选 `data`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:236` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:296`。

### audit bug 覆盖状态

P0-1：`run_skill()` 无真实 LLM 路径。现状是 `run_skill()` 的 V2.1 分支不解析真实模型，`chat_model` 只有 `mock_llm` 能填，见 `packages/graph-agent/src/graph_agent/core/runner.py:467`；SKILL node 无模型直接 `RuntimeError`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:233` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。

P1-2：subagent depth 没进入 child flow。现状是 depth 写进 RunnableConfig metadata，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:492` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:496`，child state flow 仍取 parent flow，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:400` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:404`。

P1-3：exit_contract 累积。现状是每轮把注入后的 `prompt_messages` 保存回 `messages`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:243` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:246`。

P1-4：callbacks/trace 未接 V0.3 主线（已过时）。T3 后现状是 V0.3 `_run_v030_skill_dict()` 创建 `_CompositeEventSink` 并透传给 graph assembly；即使不传 `event_subscriber`，引擎也会自动用 `_TraceJsonlSink` 写 `trace.jsonl`（含 run start/end、phase events、crashed 黑匣子）。

A4/A5：subagent 目前是完整 graph skill，call_subgraph tool 尚不存在。现状分别见 `packages/graph-agent/src/graph_agent/core/loader.py:477` 到 `packages/graph-agent/src/graph_agent/core/loader.py:482` 和 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:184` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:227`。

### 当前执行阶段的边界

runtime 不是 compiler。它不会重新检查 `GRAPH.md` 的 phase id 是否重复，因为这些校验已经在 `SkillLoader.compile_skill()` 内完成，入口是 `packages/graph-agent/src/graph_agent/core/loader.py:142`，拓扑校验入口是 `packages/graph-agent/src/graph_agent/core/loader.py:730`。runtime 假设 `CompiledSkill` 已经是结构化输入。

runtime 也不是完整 harness。旧 harness 中 callbacks、artifact saver、IOManager、checkpoint/resume 的语义仍在旧路径里出现，例如默认 callbacks 创建在 `packages/graph-agent/src/graph_agent/core/runner.py:284` 到 `packages/graph-agent/src/graph_agent/core/runner.py:286`。但是 V0.3 `_run_v030_skill_dict()` 只接收并透传 callbacks，不负责自动创建旧 harness 的默认 callback 组合，所以不能把旧 harness 能力自动套到 V0.3 graph runtime 上。

runtime 不是输入 schema 漏斗。`_run_v030_skill_dict()` 的 `data` 只来自 `dict(inputs)`，见 `packages/graph-agent/src/graph_agent/core/runner.py:503` 到 `packages/graph-agent/src/graph_agent/core/runner.py:508`。也就是说 runtime 当前不会在入口按 `io/inputs.json` reject 未声明字段。

runtime 也不是 phase-level IO mapper。LOGIC、SUBGRAPH、subagent 都围绕同一个 `data` 黑板运转：LOGIC 用 Context 包装 data，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136`；SUBGRAPH 用父 data 启动子图，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:164`；subagent child data 是父 data 加 input item，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:398` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:403`。

### 常见调用结果形态

`_run_v030_skill_dict()` 最终返回普通 dict，而 `run_skill()` 再把它包装成 `RunResult`。V2.1 raw dict 里包含 `run_id`、`context`、`metrics`、`trace_path`、`wall_time_sec`，构造位置是 `packages/graph-agent/src/graph_agent/core/runner.py:480` 到 `packages/graph-agent/src/graph_agent/core/runner.py:518`。

其中 `context` 来自最终 graph state 的 `data`，见 `packages/graph-agent/src/graph_agent/core/runner.py:514`。这意味着最终返回值不是 `flow`，也不是 `messages`，而是业务黑板。`flow` 里可能有 `finish_task_result` 或 critic metrics，但当前 public result 不把整份 flow 暴露为 context。

`RunResult` 包装发生在 `run_skill()` 成功分支，见 `packages/graph-agent/src/graph_agent/core/runner.py:211` 到 `packages/graph-agent/src/graph_agent/core/runner.py:224`。失败包装只捕获 `GraphAgentError`，见 `packages/graph-agent/src/graph_agent/core/runner.py:195` 到 `packages/graph-agent/src/graph_agent/core/runner.py:209`；而 P0-1 的 SKILL phase 无模型错误当前是裸 `RuntimeError`，抛出位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:233` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:234`。

### 读代码时的主路径提示

读 runtime 建议先看 `run_skill()`，位置是 `packages/graph-agent/src/graph_agent/core/runner.py:161`。然后跳到 `_run_v030_skill_dict()`，位置是 `packages/graph-agent/src/graph_agent/core/runner.py:468`。再跳到 `assemble_graph()`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55`。

理解节点时按三类看：LOGIC 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:116`，SUBGRAPH 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:141`，SKILL 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:177`。理解 subagent 时从 `_subagent_tool_map()` 开始，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:301`，再看 `_invoke_subagent_tool_t21()`，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:311`。
