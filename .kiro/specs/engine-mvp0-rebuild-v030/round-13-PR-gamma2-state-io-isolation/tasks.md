---
spec: engine-mvp0-rebuild-v030/round-13-PR-gamma2-state-io-isolation
phase: PR gamma2 tasks
owner: a1 主笔 / a2 design+requirements+research / a3 final gate
工程量: 45h = D1 8h + D2 8h + D3 7h + D4 10h + D5 12h
---

# PR gamma2: State/IO Isolation Tasks

## §0 Scope 和继承边界

PR gamma2 只做 State/IO Isolation。它承接 PR alpha / gamma0 / beta / delta 已 ship 的边界:

- 不改 `ModelResolverProtocol`。
- 不改 Agent AST 的 `exit_contract` 移除结论。
- 不改 `validator: bool` 字段语义。
- 不改 middleware order contract。
- 不改 `CognitiveFlowMiddleware` 已接管 `finish_task` / `ask_clarification` 的事实。
- 不改 `SkillResolverProtocol` 的 `target_skill` / resolver 强制注入结论。

本 PR 的 hard cutover 点:

- `BlackboardState.data` 从扁平 dict 改为三区结构: `inputs` / `phase_outputs` / `scratch`。
- child graph / subagent / builtin reference reader 不得继承 parent `data` 或 `messages`。
- phase output 不再写扁平顶层 key, 必须写入 `data.phase_outputs[phase_id]`。
- 现有 flat `state["data"]` 测试和 runtime 写回路径必须同 PR 迁移, 不保留 fallback。

## §1 依赖图

```text
gamma2.1 Tests-first red suite (D5 partial)
  ├─> gamma2.2 D1 state shape + input funnel
  │     ├─> gamma2.3 D2 phase wrapper 4 node kinds
  │     │     ├─> gamma2.4 D3 builtin reference reader sandbox
  │     │     └─> gamma2.5 D4 child graph/subagent isolation
  │     │             └─> gamma2.6 D4 cross-round finish_task/writeback cutover
  └─> gamma2.7 D5 migration + full green
        └─> gamma2.8 docs sync + PR report
```

必须串行:

- `gamma2.1` 必须最先落地, 红灯先证明 parent leak / input drop / read-only inputs / cross-round writeback 冲突真实存在。
- `gamma2.2` 必须先于 `gamma2.3-gamma2.6`, 因为 wrapper 和 child isolation 都依赖三区 state shape。
- `gamma2.6` 必须在 `gamma2.5` 后, 因为 finish_task 写回要落到同一套 `phase_outputs` 语义。
- `gamma2.7` 最后迁移旧 flat-data 测试并跑全量 gate。

可并行:

- `gamma2.3` wrapper 接入和 `gamma2.4` reference reader runtime 可在 D1 接口稳定后并行。
- `gamma2.5` child isolation 的 SUBGRAPH 与 subagent case 可并行写测试, 但合并时必须共享同一个 child input funnel。

## §2 gamma2.1: Tests-first isolation red suite (D5 partial, 5h)

**WHY**: 本 PR 是 breaking state cutover。先写红灯能防止实现时只改类型、不真正切断 parent leak。

**Files**:

- `packages/graph-agent/tests/runtime/test_state_mapper.py:15`
- `packages/graph-agent/tests/runtime/test_state_reducer.py:5`
- `packages/graph-agent/tests/core/test_v21_subagent_executor.py:104`
- `packages/graph-agent/tests/core/test_v21_graph_assembly.py:117`
- `packages/graph-agent/tests/middleware/test_cognitive_flow.py:135`
- 新增 `packages/graph-agent/tests/runtime/test_gamma2_state_io_isolation.py`
- 新增 `packages/graph-agent/tests/core/test_gamma2_child_graph_isolation.py`

**WHAT**:

- 写 Parent Leak Prevention 红灯: child SUBGRAPH / subagent 看不到 parent `scratch`, parent transient top-level data, parent `messages`。
- 写 Input Funnel Drop 红灯: raw input 中未声明字段被丢弃, 不进入 `data.inputs`。
- 写 Inputs Read-only 红灯: phase/action/tool 试图修改 `data.inputs` 时抛 `[F-v3-runtime-state-mapping-failed]`。
- 写 `phase_outputs` 红灯: phase 产出必须在 `data.phase_outputs[phase_id]`, 不再落扁平 `data[phase_id]`。
- 写跨 round 红灯: `handle_finish_task_tool_result` 当前 `cognitive_flow.py:878` 写 `data={phase_name: final_write}`, 新测试应失败并标为 `[CUTOVER SIGNAL]`。
- 写 grep guard 红灯:
  - `grep -RIn "response_state\\[\"data\"\\] = {phase_name" packages/graph-agent/src` 必须后续无命中。
  - `grep -RIn "child_data = {\\*\\*before_data" packages/graph-agent/src` 必须后续无命中。

**Cutover discipline**:

- 本 task 只写 tests, 不写 src。
- 红灯必须是真断言, 不允许只测 import / placeholder。
- 如果旧测试因红灯失败, 不跳过; 后续 src task 服从红灯。

**验收**:

- 新增/修改测试在当前 src 下失败, 且失败点对应 parent leak / flat writeback / read-only inputs。
- 不引入 `xfail` / `skip`。

**依赖**: none。

## §3 gamma2.2: D1 Input Funnel + normalized state shape (8h)

**WHY**: R6 要求 runtime 只通过 StateMapper / Phase Wrapper 读写 `data.inputs`, `data.phase_outputs`, `data.scratch`。当前 `state.py:38` 仍是扁平 `dict[str, Any]` + `shallow_dict_merge`。

**Files**:

- `packages/graph-agent/src/graph_agent/runtime/state.py:13`
- `packages/graph-agent/src/graph_agent/runtime/state.py:35`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:24`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:43`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:52`
- `packages/graph-agent/tests/runtime/test_state_mapper.py:15`
- `packages/graph-agent/tests/runtime/test_state_reducer.py:5`

**WHAT**:

- 新增 `BlackboardData` TypedDict:
  - `inputs: dict[str, Any]`
  - `phase_outputs: dict[str, dict[str, Any]]`
  - `scratch: dict[str, Any]`
- 将 `BlackboardState.data` 改为 `BlackboardData`。
- 替换 `shallow_dict_merge` 为能理解三区的 reducer:
  - `inputs` 仅初始化合并; 运行中重复写入为 fatal。
  - `phase_outputs[phase_id]` 按 phase id 合并。
  - `scratch` 可按当前 PR 明确策略合并, 同 key 并发冲突仍 fatal。
- 改 `filter_runtime_inputs(raw_inputs, schema)` 输出 canonical root inputs。
- 改 `StateMapper.build_phase_input` 从 `data.inputs` + 上游 `data.phase_outputs` 构造 phase-local view, 不暴露整张 parent blackboard。
- 改 `StateMapper.wrap_phase_output` 将输出写入 `data.phase_outputs[phase_id]`, 并拒绝未声明输出 key。
- 保留错误码 `[F-v3-runtime-state-mapping-failed]`。

**Cutover discipline**:

- 所有仍断言 `state["data"] == {"business_key": ...}` 的 tests 必须同 PR 迁移。
- 不提供 flat `data` 兼容 facade。
- 不把旧 `shallow_dict_merge` 留成 active path。

**验收**:

- D1 红灯 tests 变绿。
- `grep -RIn "Shared LangGraph blackboard state for V2.1" packages/graph-agent/src/graph_agent/runtime/state.py` 无命中。
- `grep -RIn "shallow_dict_merge" packages/graph-agent/src/graph_agent/runtime packages/graph-agent/tests/runtime` 无 active 旧语义命中。
- `pytest packages/graph-agent/tests/runtime/test_state_mapper.py -v` 通过。

**依赖**: `gamma2.1`。

## §4 gamma2.3: D2 Phase Wrapper 4 类节点接入 + double-wrap guard (8h)

**WHY**: D1 只是 state shape。D2 要确保 agent / logic / subgraph / builtin reference reader 都从同一套 wrapper 进入和退出, 否则仍会有节点绕过 StateMapper。

**Files**:

- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:72`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:164`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:171`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:196`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:298`
- `packages/graph-agent/tests/runtime/test_state_mapper.py:43`
- `packages/graph-agent/tests/core/test_v21_graph_assembly.py:117`

**WHAT**:

- 让 `PhaseWrapper` 明确接收 `phase_id`, `input_schema`, `output_schema`, `node_kind`。
- 接入 4 类节点:
  - Agent node
  - LOGIC node
  - SUBGRAPH node
  - builtin reference reader node
- 增加 double-wrap guard:
  - 同一 node 不能被同一 wrapper 重复包装。
  - child graph 顶层不能被 parent wrapper 二次包裹。
- wrapper 返回 patch 时只允许修改 `data.phase_outputs[phase_id]`, `data.scratch`, allowed `flow`, `messages`。
- wrapper 捕获普通异常并归一为 `[F-v3-runtime-state-mapping-failed]`, 不吞原异常上下文。

**Cutover discipline**:

- 不保留“某类节点仍直接读写 flat data”的旁路。
- 如果 LOGIC action 仍依赖 flat ctx, 同 PR 调整测试和 action ctx 输入面。

**验收**:

- wrapper tests 覆盖 4 类 node kind。
- double-wrap test 能证明重复包装会被拒绝或无副作用地阻止。
- `grep -RIn "PhaseWrapper(StateMapper" packages/graph-agent/src/graph_agent/core/graph_assembler.py` 后续只允许统一 factory/helper 入口, 不允许散落多处直接 new。

**依赖**: `gamma2.2`。

## §5 gamma2.4: D3 builtin reference reader runtime + sandbox activation (7h)

**WHY**: design §3.4 要求不仅激活 `ReaderSandboxState` stub, 还要新建 builtin reference reader runtime。当前 `find packages/graph-agent/src/graph_agent -name '*reference_reader*'` 无源码实体。

**Files**:

- 新增 `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py`
- 可新增 `packages/graph-agent/src/graph_agent/core/builtin_subagents/__init__.py`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:94`
- `packages/graph-agent/tests/runtime/test_state_mapper.py:52`
- 新增 `packages/graph-agent/tests/core/test_gamma2_reference_reader_sandbox.py`

**WHAT**:

- 新建 reference reader runtime entity。
- 完整激活 `ReaderSandboxState`:
  - `data.skill_id`
  - `data.phase_id`
  - reference list / reader input payload
  - `flow.timeout_s = 60`
  - `messages = []`
  - isolated `run_id`
- reader 不读取 parent `data`, parent `messages`, parent `scratch`。
- reader 超时/失败按 WARN fallback 语义接到现有 tracing/error payload, 不阻断正常 Agent execution。

**Cutover discipline**:

- 不把 reference reader 做成普通 subagent 复用 parent runtime state。
- 不通过全局 singleton/model resolver 隐式取依赖; 依赖必须显式传入。

**验收**:

- reader sandbox test 证明 parent data/messages 不进入 reader。
- timeout 默认值 test 固定为 60。
- `grep -RIn "class ReaderSandboxState" packages/graph-agent/src` 只保留一个定义。
- `grep -RIn "reference_reader" packages/graph-agent/src/graph_agent/core/builtin_subagents packages/graph-agent/tests/core` 有 runtime + tests 命中。

**依赖**: `gamma2.2`, 可与 `gamma2.3` 并行。

## §6 gamma2.5: D4 SUBGRAPH/subagent child input isolation (6h)

**WHY**: R8 要求 child graph 从 explicit input filtered by target root `io.inputs` 开始, 不继承 parent data。当前 SUBGRAPH 在 `graph_assembler.py:216-219` 传整包 `before_data`; subagent 在 `graph_assembler.py:579-580` 暴力合并 parent data。

**Files**:

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:196`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:215`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:573`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:580`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:687`
- `packages/graph-agent/tests/core/test_v21_subagent_executor.py:104`
- 新增/修改 `packages/graph-agent/tests/core/test_gamma2_child_graph_isolation.py`

**WHAT**:

- SUBGRAPH child input:
  - 只使用 wrapper 已构造的显式 phase input。
  - 再用 child root `GRAPH.md io.inputs` funnel 过滤。
  - child `data.inputs` 等于 canonical explicit input。
  - child `messages = []`。
  - child `flow` 只 deep copy allowed control keys, 写入 `subagent_depth + 1`。
- subagent tool child input:
  - 删除 `child_data = {**before_data, **input_data}`。
  - 只使用 tool argument `input_data` 进入 child funnel。
  - parent data / scratch / messages 不进入 child。
- child result:
  - subagent 结果作为 tool result 返回给 parent Agent。
  - SUBGRAPH phase output 经 parent phase `io.outputs` 包装到 `data.phase_outputs[subgraph_phase_id]`。

**Cutover discipline**:

- 禁止“按字段名从父 `data.inputs` / `data.phase_outputs` 自动扫值”作为 child input fallback。
- 如果测试出现缺输入, 应让父 phase 显式传参, 不恢复 parent data merge。

**验收**:

- Parent Leak Prevention 红灯变绿。
- `grep -RIn "child_data = {\\*\\*before_data" packages/graph-agent/src` 无命中。
- `grep -RIn "\"data\": before_data" packages/graph-agent/src/graph_agent/core/graph_assembler.py` 无命中。
- `pytest packages/graph-agent/tests/core/test_v21_subagent_executor.py -v` 通过或已迁移为 gamma2 isolation tests。

**依赖**: `gamma2.2`, `gamma2.3`。

## §7 gamma2.6: D4 cross-round finish_task / wrap_phase_output / _dict_delta cutover (4h)

**WHY**: design §2 明确 round-11/12 已 ship 的 `handle_finish_task_tool_result` 写回路径会撞三区 state。`cognitive_flow.py:878 response_state["data"] = {phase_name: final_write}` 失败是 `[CUTOVER SIGNAL]`, 不是 bug。

**Files**:

- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:870`
- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:878`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:52`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:187`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:687`
- `packages/graph-agent/tests/middleware/test_cognitive_flow.py:135`
- `packages/graph-agent/tests/middleware/test_cognitive_flow.py:350`

**WHAT**:

- 改 `_finish_task_accept_response` 写回:
  - 从 `data={phase_name: final_write}` 改为 `data.phase_outputs[phase_name] = final_write`。
  - 不写 `data.inputs`。
  - 不把 diagnostics / schema gate 临时对象写到 public phase output 外层。
- 改 `wrap_phase_output` 让 middleware finish_task / graph assembler node patch 都进入同一套 `phase_outputs`。
- 改 `_dict_delta` 或删除其对 flat data 的依赖:
  - 不用扁平 before/after diff 判断 child output。
  - 对三区 patch 做结构化合并。
- 更新 middleware tests 的 `new_data["items"]` 断言为 `new_data["phase_outputs"][phase_name]["items"]` 或等价 helper。

**Cutover discipline**:

- 不新增兼容函数把 `phase_outputs[phase_id]` 展平成 `data[phase_id]`。
- 不把 `[CUTOVER SIGNAL]` 红灯改弱; 必须改 src 让它绿。

**验收**:

- `grep -RIn "response_state\\[\"data\"\\] = {phase_name" packages/graph-agent/src` 无命中。
- `grep -RIn "_dict_delta(before_data" packages/graph-agent/src/graph_agent/core/graph_assembler.py` 无 child isolation 旧语义命中。
- `pytest packages/graph-agent/tests/middleware/test_cognitive_flow.py -v` 通过。

**依赖**: `gamma2.5`。

## §8 gamma2.7: D5 isolation test migration + full green (7h)

**WHY**: D1-D4 会让旧 flat `state["data"]` 测试大面积失败。D5 收口要把旧测试迁移到 V0.3.0 三区语义, 防止 CI 靠旧断言证明旧世界。

**Files**:

- `packages/graph-agent/tests/runtime/test_state_mapper.py:15`
- `packages/graph-agent/tests/runtime/test_state_reducer.py:5`
- `packages/graph-agent/tests/core/test_v21_compiler_facade.py:37`
- `packages/graph-agent/tests/core/test_v21_graph_assembly.py:117`
- `packages/graph-agent/tests/core/test_v21_subagent_executor.py:104`
- `packages/graph-agent/tests/core/test_state_manager.py:27`
- `packages/graph-agent/tests/core/test_build_graph_nodes.py:119`
- `packages/graph-agent/tests/middleware/test_cognitive_flow.py:135`

**WHAT**:

- 迁移 `test_state_mapper.py`:
  - 断言 `data.inputs`, `data.phase_outputs`, `data.scratch`。
  - 断言 unknown input drop。
  - 断言 inputs read-only fatal。
- 迁移 `test_v21_subagent_executor.py`:
  - 保留 subagent depth 行为。
  - 改 parent data leak prevention。
  - 改 child result tool semantics。
- 迁移 graph assembly tests:
  - flat `data` invoke fixture 改为 normalized state helper。
  - output 断言改为 `phase_outputs`。
- 增加 shared test helper:
  - `normalized_state(inputs=..., phase_outputs=..., scratch=..., messages=...)`
  - 避免每个测试手写不一致 state shape。

**Cutover discipline**:

- 不通过 `pytest -k` 局部绿替代全量。
- 不把旧 flat-data tests 标 skip/xfail。
- 不删除高价值覆盖; 能迁移就迁移。

**验收**:

- `pytest packages/graph-agent/tests/runtime -v` 通过。
- `pytest packages/graph-agent/tests/core/test_v21_subagent_executor.py -v` 通过或文件已按 gamma2 命名迁移。
- `pytest packages/graph-agent/tests/middleware/test_cognitive_flow.py -v` 通过。
- `grep -RIn "state\\[\"data\"\\]\\[\" packages/graph-agent/tests/runtime packages/graph-agent/tests/core packages/graph-agent/tests/middleware` 无需改的 active flat-data 断言已清理或逐项登记。

**依赖**: `gamma2.2-gamma2.6`。

## §9 gamma2.8: SOP-08 Step 6 docs sync + Step 7 PR report (post-implementation)

**WHY**: gamma2 是 state shape breaking PR。源码过 gate 后必须同步 docs, 否则后续 E/F/G 会引用旧 flat state 语义。

**Files**:

- `docs/engine/state-and-io-contract/logic-explained.md`
- `docs/engine/state-and-io-contract/mvp0-alignment.md`
- `docs/engine/state-and-io-contract/baseline.md`
- `.kiro/specs/engine-mvp0-rebuild-v030/round-13-PR-gamma2-state-io-isolation/PR-REPORT.md`

**WHAT**:

- docs sync:
  - 字段级翻译 `BlackboardData.inputs / phase_outputs / scratch`。
  - 翻译 `StateMapper.build_phase_input`, `wrap_phase_output`, child funnel, reader sandbox。
  - 明确 round-11/12 finish_task 写回为何在 gamma2 改。
- PR report:
  - PM-friendly 三段: 设计 / 实现 / 验收。
  - 写清 tests-first、audit、full gate 结果。

**Cutover discipline**:

- docs sync 必须跟当前 src 行为一致, 不写目标态空话。
- PR report 不放大段代码 / line diff, 开发者参考区块可列路径和 commit。

**验收**:

- docs 中不再把 flat `data` 描述为 active runtime contract。
- PR report 列明 isolation tests 和 grep guard 结果。

**依赖**: `gamma2.7`。

**工时**: 不计入 D1-D5 45h implementation, 作为 SOP-08 ship buffer 执行。

## §10 CI Gate Checklist

Before PR merge:

- [ ] `pytest packages/graph-agent/tests/`
- [ ] `pytest packages/graph-agent/tests/runtime/ -v`
- [ ] `pytest packages/graph-agent/tests/core/test_v21_subagent_executor.py -v` 或迁移后的 gamma2 isolation equivalent
- [ ] `pytest packages/graph-agent/tests/middleware/test_cognitive_flow.py -v`
- [ ] `pytest apps/studio/backend/tests/`
- [ ] `ruff check packages/graph-agent/src packages/graph-agent/tests`
- [ ] `mypy packages/graph-agent/src`
- [ ] `grep -RIn "response_state\\[\"data\"\\] = {phase_name" packages/graph-agent/src` 返回 0
- [ ] `grep -RIn "child_data = {\\*\\*before_data" packages/graph-agent/src` 返回 0
- [ ] `grep -RIn "\"data\": before_data" packages/graph-agent/src/graph_agent/core/graph_assembler.py` 返回 0
- [ ] `grep -RIn "Shared LangGraph blackboard state for V2.1" packages/graph-agent/src/graph_agent/runtime/state.py` 返回 0
- [ ] `gh run list --branch main --limit 3` 确认最近 3 个 main CI green
- [ ] 不跳 hooks, 不用 `pytest -k` 局部绿冒充 full green
- [ ] unit + integration + e2e tests 和 src cutover 同 PR 同步

## §11 High-risk Collision List

- `cognitive_flow.py:878` flat writeback 失败是 `[CUTOVER SIGNAL]`, 不是 regression。按 SOP-06 breaking migration 改成 `phase_outputs`。
- `graph_assembler.py:187` 和 `graph_assembler.py:687` 的 `_dict_delta` 依赖 flat before/after data。D4 必须重构或删除这个依赖。
- `graph_assembler.py:216-219` SUBGRAPH 透传 parent `before_data`, 是 R8 直接违反点。
- `graph_assembler.py:579-580` subagent 合并 parent data, 是 parent leak 的主入口。
- `test_state_mapper.py:40-46`, `test_v21_subagent_executor.py:136-148`, `test_cognitive_flow.py:135/350` 等旧断言会红, 属于 expected cutover cost。
- `core/builtin_subagents/reference_reader.py` 当前不存在; D3 是新建 runtime, 不是只改 stub。
- State shape breaking 可能波及 Studio trace / API snapshot。若出现 Studio backend tests red, 只能迁移到新 payload, 不恢复 flat data。
