# state-and-io-contract (engine) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: BlackboardState 规约 (data/flow/messages)、Reducer 并发冲突控制、阶段级 IO 隔离、Runtime Input 漏斗 (audit A1/A2/A3/A6)
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

状态合并、IO schema、黑板隔离都发生在 Python engine 内存里，不直接渲染 UI。上层如果要展示 phase 输入输出，需要另行从运行结果或 trace 中读取。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

React 不持有 `BlackboardState`，也不执行 reducer。Studio 的 state store 和这里的 engine state 是两套不同东西。

## 后端功能

### 当前状态模型总览 {#cross-state-blackboard-fields}

`BlackboardState` 是 LangGraph 状态主 dict，定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:35` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:41`。`TypedDict` 第一次出现时需要定义：它是 Python typing 里的 "带固定字段说明的 dict"，运行时仍然像普通 dict，但类型检查器知道有哪些 key。

当前字段是：

- `data`: 业务数据黑板，带 `shallow_dict_merge` reducer，见 `packages/graph-agent/src/graph_agent/runtime/state.py:38`。
- `flow`: 框架控制状态，普通 dict，见 `packages/graph-agent/src/graph_agent/runtime/state.py:39`。
- `messages`: LLM 对话消息，带 LangGraph `add_messages` reducer，见 `packages/graph-agent/src/graph_agent/runtime/state.py:40`。
- `run_id`: 本次运行 id，见 `packages/graph-agent/src/graph_agent/runtime/state.py:41`。

Reducer 第一次出现时需要定义：它是 LangGraph 合并 node 返回值的函数。例如两个节点都返回 `{"data": {...}}`，LangGraph 需要知道这些 dict 如何合并。当前 `data` 的 reducer 是 `shallow_dict_merge`，`messages` 的 reducer 是 `add_messages`。

这份 state 在 runtime 中如何被 LOGIC/SKILL/SUBGRAPH 节点读写，详见 [execution-runtime/baseline.md#后端功能](../execution-runtime/baseline.md#后端功能)。

### `shallow_dict_merge`

`shallow_dict_merge(left, right)` 定义在 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:32`。它只合并顶层 key，不做深层递归合并。

当前语义是：

1. `left` 为空就返回 `right` 的浅拷贝，见 `packages/graph-agent/src/graph_agent/runtime/state.py:19` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:20`。
2. `right` 为空就返回 `left` 的浅拷贝，见 `packages/graph-agent/src/graph_agent/runtime/state.py:21` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:22`。
3. 遍历 `right.items()`，如果 key 已经在 `left` 里，抛 `GraphAgentFatalError("[F-v21-state-conflict] ...")`，见 `packages/graph-agent/src/graph_agent/runtime/state.py:24` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:30`。
4. 没冲突才写入 merged，见 `packages/graph-agent/src/graph_agent/runtime/state.py:31` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:32`。

这就是 audit P0-3 的根因：它想防并行分支写同一 key，但在顺序 phase 更新已有 key 时也会冲突。audit P0-3 位置是 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:177`。

### data 的当前读写面

当前 runtime input 直接进入 `data`。`_run_v21_skill_dict()` 把 `**inputs` 变成 `dict(inputs)`，作为 graph 初始 state 的 `data`，见 `packages/graph-agent/src/graph_agent/core/runner.py:471` 到 `packages/graph-agent/src/graph_agent/core/runner.py:477`。这里没有调用 `io/inputs.json` 做 runtime 校验、过滤、默认值填充或类型转换。

LOGIC node 通过 `Context` 读写 `data`。它复制 `state.data`，执行 action 后用 `_dict_delta()` 计算变化，再返回 `{"data": updates}`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136`。

SUBGRAPH node 把父图当前 `data` 直接传给子图，子图结束后再 diff 出 delta 合回父图，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:172`。

SKILL node 不直接拿一个 `Context`。它主要通过 prompt、tools、subagents 和 `finish_task` 工作。`finish_task` 成功后，runtime 写 `data_updates[phase_id] = result.get("data", {})`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:275` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:291`。

### flow 的当前读写面

`flow` 是控制状态，不是业务输出。SKILL node 会复制 `state.flow`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:236` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:237`。`finish_task` 结果写进 `flow["finish_task_result"]`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:275` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:276`。

subagent 参数校验次数写在 `flow["subagent_validation_retries"]`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:325` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:330`。critic 工具指标写在 `flow["critic_metrics"]`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:279` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:288`。

`flow` 没有显式 reducer。它在 `BlackboardState` 里只是 `dict[str, Any]`，见 `packages/graph-agent/src/graph_agent/runtime/state.py:39`。这意味着它不像 `data` 那样有自定义冲突检测，也不像 `messages` 那样有 `add_messages` 追加语义。

### messages 的当前读写面

`messages` 是 LLM 对话历史。它用 LangGraph `add_messages` reducer，见 `packages/graph-agent/src/graph_agent/runtime/state.py:7` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:8` 和 `packages/graph-agent/src/graph_agent/runtime/state.py:40`。

SKILL node 初始 messages 是 `[SystemMessage(...), *state.get("messages", [])]`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:238`。每轮 ReAct 会把 response 和 tool messages 继续 append，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:243` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:274`。

因为 `inject_exit_contract()` 产生的 `prompt_messages` 会被保存回 `messages`，`exit_contract` 当前也会进入长期历史，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:243` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:246`。

### IOManager 和 legacy context resolver

`IOManager` 是旧 SKILL.md 驱动 workflow 的声明式 IO helper，不是 V2.1 `run_skill(**inputs)` 的入口漏斗。它定义在 `packages/graph-agent/src/graph_agent/io/manager.py:27` 到 `packages/graph-agent/src/graph_agent/io/manager.py:43`，输入来源支持 runtime/file，输出目标支持 artifact_manager/file，说明写在 `packages/graph-agent/src/graph_agent/io/manager.py:1` 到 `packages/graph-agent/src/graph_agent/io/manager.py:13`。

`IOManager.load_inputs(**runtime_args)` 会按 `io_config["inputs"]` 逐项读取 runtime 或 file 输入，见 `packages/graph-agent/src/graph_agent/io/manager.py:65` 到 `packages/graph-agent/src/graph_agent/io/manager.py:106`。但 V2.1 `_run_v21_skill_dict()` 没有调用它；V2.1 入口直接 `dict(inputs)`，见 `packages/graph-agent/src/graph_agent/core/runner.py:473`。

`ContextResolver` 是旧 `context_mapping` 表达式引擎，定义在 `packages/graph-agent/src/graph_agent/io/context_resolver.py:22` 到 `packages/graph-agent/src/graph_agent/io/context_resolver.py:40`。它把 `{input.scene.scene_id}` 这类表达式从 raw inputs 中解析出来，核心方法在 `packages/graph-agent/src/graph_agent/io/context_resolver.py:41` 到 `packages/graph-agent/src/graph_agent/io/context_resolver.py:59`。V2.1 主线没有把它作为 per-phase input mapping 使用。

## API

### State API

本模块的直接 API 是 `BlackboardState` 和 `shallow_dict_merge`，由 `packages/graph-agent/src/graph_agent/runtime/state.py:44` 暴露在 `__all__`。`BlackboardState` 给 `StateGraph(BlackboardState)` 使用，装配点在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:63`。

`shallow_dict_merge` 不是给业务作者直接调用的常规 public API，但它是 state 合并契约的一部分。任何 node 返回 `{"data": ...}` 都会走这个 reducer，因此它的冲突语义会影响 LOGIC、SUBGRAPH、SKILL 三类节点。

### IO API

根级 V2.1 IO 文件由 compiler 校验，而不是 runtime API 校验。`GraphManifest` 默认 `io_inputs_ref` 和 `io_outputs_ref` 分别是 `io/inputs.json`、`io/outputs.json`，见 `packages/graph-agent/src/graph_agent/core/manifest.py:53` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:54`。编译期 `_validate_io_schema()` 校验这些文件，见 `packages/graph-agent/src/graph_agent/core/loader.py:874` 到 `packages/graph-agent/src/graph_agent/core/loader.py:900`。

legacy `IOManager` 的 API 是 `load_inputs()` 和 `save_outputs()`，分别在 `packages/graph-agent/src/graph_agent/io/manager.py:65` 和 `packages/graph-agent/src/graph_agent/io/manager.py:108`。它们说明旧 IO 系统仍在代码中，但不是当前 V2.1 graph runner 的实际 input funnel。

## Data Model / State

### audit A1：缺 runtime input funnel

audit A1 位置是 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:507`。当前实现是 `run_skill(**inputs) -> data = dict(inputs)`，代码证据在 `packages/graph-agent/src/graph_agent/core/runner.py:471` 到 `packages/graph-agent/src/graph_agent/core/runner.py:477`。

这意味着当下 runtime 不按 `io/inputs.json` 过滤未知字段、不校验类型、不填默认值，也不把输入分发到 phase-level input。`io/inputs.json` 的当下作用主要是编译期 schema 文件合法性、LOGIC context 写键允许集、subagent 工具入参模型来源，而不是 runtime 入口漏斗。

### audit A2：所有节点读全量 data，缺 phase-level IO contract

audit A2 位置是 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:547`。当前 LOGIC 和 SUBGRAPH 都直接拿全量 `state.data`：LOGIC 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:130`，SUBGRAPH 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:160`。

当前 `SkillNodeAST` 也没有 phase-level `io` 字段，只有 prompt、exit_contract、tools、subagents，见 `packages/graph-agent/src/graph_agent/core/manifest.py:83` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:90`。因此没有 "这个 phase 只能读哪些字段、只能写哪些字段" 的正式状态契约。

### audit A3：SUBGRAPH 修改父图 key 的冲突场景

audit A3 位置是 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:588`。当前 SUBGRAPH 用父图全量 data 启动子图，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:164`。子图完成后 `_dict_delta(before_data, result_data)` 取变化，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:165` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:168`。

如果这个 delta 包含父图已经有的 key，`data` reducer 会按冲突处理，因为 `shallow_dict_merge` 在 key 已存在时抛错，见 `packages/graph-agent/src/graph_agent/runtime/state.py:24` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:30`。所以当下 SUBGRAPH 没有父子黑板边界。

### audit A6：agent-called graph 黑板隔离缺失

audit A6 位置是 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:734`。当前 subagent tool 调用子图时，child data 是 `{**before_data, **input_data}`，代码在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:398` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:403`。

这说明子 graph 默认可以看到父 graph 全量业务黑板，再叠加 LLM 显式传入的 input。结果不会自动合回父图 data，而是作为 tool result 回给父 LLM；但子图执行期间的读取边界仍然不是隔离的。这个现状也和 engine-flow 文档对 subagent 初始 data 的解释一致，见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-engine-flow-explained__by-codex-2026-05-20.md:837`。

### audit P0-3：顺序覆盖冲突

P0-3 是 state 模块最直接的已验证 bug，位置是 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:177`。当前 `shallow_dict_merge({"foo": 1}, {"foo": 2})` 会抛 `[F-v21-state-conflict]`，因为实现不区分顺序更新和并行 fan-in 冲突，见 `packages/graph-agent/src/graph_agent/runtime/state.py:24` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:30`。

这个问题被 LOGIC 和 SUBGRAPH 都触发：LOGIC 返回 `{"data": updates}`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136`；SUBGRAPH 返回 `{"data": data_updates}`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:169` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:170`。只要 updates 里有已有 key，就会进入 reducer 冲突路径。

### 当前数据契约的实际心智模型

当下最准确的心智模型不是 "每个 phase 有自己的输入对象和输出对象"，而是 "整张图共享一块顶层业务黑板 `data`"。engine-flow 文档也这样总结，见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-engine-flow-explained__by-codex-2026-05-20.md:1239`。

这块黑板从 `_run_v21_skill_dict()` 的 `dict(inputs)` 开始，见 `packages/graph-agent/src/graph_agent/core/runner.py:473`。LOGIC 可以通过 `Context` 直接读写它，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:130` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:131`。SKILL 通过 `finish_task` 间接写 `data[phase_id]`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:275` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:291`。SUBGRAPH 通过子图 delta 改它，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:165` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:172`。

因此，`io/inputs.json` 和 `io/outputs.json` 在当下不能理解成自动数据路由表。它们在编译期被 `_validate_io_schema()` 校验，见 `packages/graph-agent/src/graph_agent/core/loader.py:874` 到 `packages/graph-agent/src/graph_agent/core/loader.py:900`；output schema keys 会约束 LOGIC action 返回 key，见 `packages/graph-agent/src/graph_agent/core/loader.py:964` 到 `packages/graph-agent/src/graph_agent/core/loader.py:989`；终点 SKILL phase 的 `finish_task` 会使用 output schema，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:215` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:225`。

### 与 skill-compilation 的双向关系

state-and-io-contract 依赖 skill-compilation 提供根级 IO schema 和 phase AST。根级 `GraphManifest` 的默认 input/output refs 在 `packages/graph-agent/src/graph_agent/core/manifest.py:53` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:54`，实际 schema 校验在 `packages/graph-agent/src/graph_agent/core/loader.py:874` 到 `packages/graph-agent/src/graph_agent/core/loader.py:900`。编译侧细节见 [skill-compilation/baseline.md#后端功能](../skill-compilation/baseline.md#后端功能)。

反过来，编译阶段的写键检查无法独立保证 runtime state 安全，因为最终是否冲突由 `shallow_dict_merge` 决定，见 `packages/graph-agent/src/graph_agent/runtime/state.py:13` 到 `packages/graph-agent/src/graph_agent/runtime/state.py:32`。这就是为什么本 feature 要单独记录 P0-3、A1、A2、A3、A6，而不是只放在 compiler 文档里。

### 读代码时的主路径提示

读 state contract 建议先看 `BlackboardState`，位置是 `packages/graph-agent/src/graph_agent/runtime/state.py:35`。再看 `shallow_dict_merge()`，位置是 `packages/graph-agent/src/graph_agent/runtime/state.py:13`。然后回到 `_run_v21_skill_dict()` 看初始 state，位置是 `packages/graph-agent/src/graph_agent/core/runner.py:451`。

如果要理解每类 phase 对 state 的影响，看 LOGIC node 的 `Context` 包装，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127`；看 SUBGRAPH node 的 child state，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:155`；看 SKILL node 的 `finish_task` 写入，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:275`；看 subagent child data，位置是 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:398`。

如果要理解 legacy IO 和 V2.1 IO 的差别，看 `IOManager.load_inputs()`，位置是 `packages/graph-agent/src/graph_agent/io/manager.py:65`，再对比 V2.1 `dict(inputs)`，位置是 `packages/graph-agent/src/graph_agent/core/runner.py:473`。这两个路径现在不是同一套入口。
