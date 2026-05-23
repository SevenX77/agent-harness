# Tasks: Engine MVP0 Rebuild V0.3.0 Cutover

本文档只规划 `packages/graph-agent/src/` 与 `packages/graph-agent/tests/` 的 V0.3.0 graph_skill cutover 实施任务, 不包含 Studio backend / Studio frontend 实施。所有实现必须对齐 `docs/engine/skill-spec/` 字段级规范和 5 个 engine 子模块 MVP0 alignment 文档。

## 整体框架

### 预估总改动

| 区域 | 预计改动文件 | 预计行数 | 说明 |
|---|---:|---:|---|
| `packages/graph-agent/src/graph_agent/core/` | 12-16 | +1800 / -900 | `manifest.py`, `loader.py`, `compiler.py`, `runner.py`, `graph_assembler.py`, `cache.py`, `actions.py`, `phase_node.py`, 新增 `skill_resolver_protocol.py` 等 |
| `packages/graph-agent/src/graph_agent/cognitive/` | 2-3 | +500 / -250 | `prompt.py`, ambiguity / finish_task 相关 glue |
| `packages/graph-agent/src/graph_agent/runtime/` | 2-3 | +450 / -250 | `state.py`, 退役或删除 `exit_contract.py`, StateMapper / reducer |
| `packages/graph-agent/src/graph_agent/tools/` | 3-5 | +500 / -100 | 新增 builtin `read_reference.py`, `read_example.py`, tool registry glue |
| `packages/graph-agent/src/graph_agent/callbacks/` | 3-5 | +550 / -150 | TraceEventKind 扩充、V2 trace event payload、async logger |
| `packages/graph-agent/tests/` | 35-50 | +2500 / -1200 | core/unit/integration/e2e fixtures 全量同步 V0.3.0 schema |

预计净改动: src 约 25-32 文件, +3800 / -1650 行; tests 约 35-50 文件, +2500 / -1200 行。

### 拆 PR 策略

PM 已拍板按层切 3 PR: engine src / Studio backend / Studio frontend。本 cutover 只做 engine src, 一个 PR 入 main。PR 内可拆 8-12 个小 commit:

1. skill-resolution Protocol 独立 commit。
2. AST / manifest / loader schema commit。
3. GRAPH.md phases + inline IO commit。
4. Agent body XML + cognitive template commit。
5. StateMapper / Phase Wrapper commit。
6. Runtime DI / subgraph / subagent commit。
7. Builtin reference reader + tools commit。
8. Tracing events commit。
9. Error code / cleanup commit。
10. Integration / e2e fixtures commit。

### CI gate

按 SOP-05 cutover discipline: src 改 + tests 改必须同 PR 同步落地。任何 schema cutover 必须同步 unit + integration + e2e test, 不允许 PR-A 改业务、PR-B 再补测试。

Merge 前必须满足:

- `pytest packages/graph-agent/tests/` 全 green。
- `ruff check packages/graph-agent/src packages/graph-agent/tests` 全过。
- `mypy packages/graph-agent/src` 全过。
- 不跳 pre-commit / hooks。
- main 最近 3 次 CI green: `gh run list --branch main --limit 3`。
- 本 PR 不引入新的 `[F-v21-*]` 字符串。

## Task 树

### A. skill-resolution (NEW 模块, 先做)

#### A1. 新建 SkillResolverProtocol 骨架
- 改 files:
  - 新建 `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py`
  - 更新 `packages/graph-agent/src/graph_agent/core/__init__.py`
- 改 lines / 函数 / 类:
  - 新增 `class SkillResolutionError(Exception)`
  - 新增 `class SkillResolverProtocol(Protocol)` with `resolve_skill(skill_id: str) -> Path`
  - 禁止加入 `resolve_resource()`
- 依赖 tasks: 无
- 测试影响:
  - 新增 `packages/graph-agent/tests/core/test_skill_resolver_protocol.py`
  - 覆盖 Protocol import、invalid skill id helper、SkillResolutionError payload
- 风险点:
  - 当前代码可能没有 core public export 约定, 需要避免破坏 import path。
  - mypy 对 Protocol runtime check 需谨慎, 不要误用 `isinstance(protocol)`。

#### A2. compile_skill() + run_skill() 签名加 skill_resolver kwarg
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/compiler.py`
  - `packages/graph-agent/src/graph_agent/core/runner.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - 所有调用 `compile_skill()` / `run_skill()` 的 tests
- 改 lines / 函数 / 类:
  - `compile_skill(root, *, skill_resolver: SkillResolverProtocol | None = None, ...)`
  - `SkillLoader.compile_skill(..., skill_resolver=...)`
  - `run_skill(..., skill_resolver: SkillResolverProtocol, ...)`
  - 含 child skill 的图未注入 resolver 抛 `[F-v3-resolver-missing]`
- 依赖 tasks: A1
- 测试影响:
  - 更新 `packages/graph-agent/tests/core/test_v21_compiler_facade.py`
  - 更新 `packages/graph-agent/tests/core/test_runner_startup_invariants.py`
  - 新增 fixture `InMemorySkillResolver`
- 风险点:
  - 大量旧测试直接调用 `compile_skill(root)`; 需要对不含 child skill 的图允许 None, 或在 tests 中统一注入 no-op resolver。
  - CLI / `__main__` 调用可能仍缺 resolver, 需显式处理。

#### A3. 退役旧 subagent 物理路径扫描
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/manifest.py`
  - `packages/graph-agent/src/graph_agent/core/subagents.py`
- 改 lines / 函数 / 类:
  - 删除 / 迁移 `_resolve_subagent_root()` (`loader.py:447`)
  - 改 `_compile_subagent_metadata()` (`loader.py:340`) 从 `spec.path` 切到 `spec.target_skill`
  - 改 `_inject_subagent_tools()` (`loader.py:387`) metadata 存 `target_skill` / resolved root
  - 退役 `SubagentSpec.path`
- 依赖 tasks: A2, B1
- 测试影响:
  - 更新 `packages/graph-agent/tests/core/test_v21_subagents_loader.py`
  - 更新 `packages/graph-agent/tests/core/test_v21_subagent_executor.py`
  - 删除 path-based fixture 或迁移到 target_skill registry fixture
- 风险点:
  - 旧 fixture `tests/fixtures/subagent_minimal` 可能全是 path-based。
  - 需要一次性替换错误断言, 避免混用 `[F-v21-*]`。

#### A4. skill-resolution 测试闭环
- 改 files:
  - 新增 `packages/graph-agent/tests/core/test_skill_resolver_protocol.py`
  - 新增 / 更新 `packages/graph-agent/tests/fixtures/v030_skill_registry/`
- 改 lines / 函数 / 类:
  - `InMemorySkillResolver.resolve_skill`
  - registry miss -> `[F-v3-skill-not-registered]`
  - invalid Path -> `[F-v3-resolver-path-invalid]`
- 依赖 tasks: A1-A3
- 测试影响:
  - Unit: resolver missing / invalid id / unregistered / invalid path
  - Integration: parent Agent subagent target_skill compile success
- 风险点:
  - 文件 fixture 的 `GRAPH.md name` 与 registry id 必须一致, 否则错误定位混乱。

### B. skill-compilation (loader.py + AST)

#### B1. SkillNodeAST 替换为 AgentNodeAST
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/manifest.py`
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/cache.py`
- 改 lines / 函数 / 类:
  - `SkillNodeAST` -> `AgentNodeAST`
  - `mode: Literal["skill"]` -> `mode: Literal["agent"]`
  - 新增字段 `role`, `goal`, `steps`, `protocols`, `exit_contract`, `references`, `examples`, `subgraphs`, `tools`, `max_iterations`, `llm_role`, `io`
- 依赖 tasks: A1
- 测试影响:
  - 更新 `packages/graph-agent/tests/core/test_v21_ast_schema.py`
  - 更新 `packages/graph-agent/tests/core/test_manifest.py`
  - 更新 cache serialization tests
- 风险点:
  - cache hit 反序列化旧 SkillNodeAST 会失败; cutover 可选择 bump cache namespace。

#### B2. mode 三值化 + phase 文件 3 选 1 校验
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/manifest.py`
- 改 lines / 函数 / 类:
  - mode enum: `agent` / `logic` / `subgraph`
  - `SKILL.md -> mode: agent`, `LOGIC.md -> logic`, `SUBGRAPH.md -> subgraph`
  - 物理目录 `phases/<id>/` 恰好一个 node file
- 依赖 tasks: B1
- 测试影响:
  - 更新 `test_v21_loader.py`, `test_loader_subgraph_is_file.py`
  - 新增 duplicate node file / missing node file tests
- 风险点:
  - 旧测试 fixture 中 `mode: skill` 需全部迁移到 `mode: agent`。

#### B3. GRAPH.md `<phase />` XML 改为 `phases:` YAML list
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/manifest.py`
  - `packages/graph-agent/src/graph_agent/core/cache.py`
- 改 lines / 函数 / 类:
  - `_build_graph_manifest()`
  - `_validate_graph_topology()`
  - phase token / line span 从 YAML AST 获取
- 依赖 tasks: B2
- 测试影响:
  - 更新 `test_t11_phase_token_info.py`
  - 更新 graph topology fixtures
  - 新增 YAML phases list depends_on / cycle / island tests
- 风险点:
  - 旧 body XML phase parser 与新 YAML parser 不能双轨长期共存; cutover PR 应一次性迁移 fixtures。

#### B4. 根 IO 物理文件退役, 改 inline `io.inputs` / `io.outputs`
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/manifest.py`
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/cache.py`
- 改 lines / 函数 / 类:
  - 删除 `io_inputs_ref` / `io_outputs_ref` 作为正常路径
  - 发现 `io/inputs.json`, `io/outputs.json`, `io_inputs_ref`, `io_outputs_ref` 抛 `[F-v3-graph-io-physical-file-deprecated]`
  - `_validate_io_schema()` 改消费 inline dict
- 依赖 tasks: B3
- 测试影响:
  - 更新 `test_io_manager.py`, `test_compiler_schema_version_tolerance.py`
  - 新增 deprecated physical IO fatal tests
- 风险点:
  - cache key 以前收集 `io/*.json`; 需改为收集 `GRAPH.md` inline content。

#### B5. Agent body XML 5 类顶层标签解析
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/parser.py`
  - `packages/graph-agent/src/graph_agent/cognitive/prompt.py`
- 改 lines / 函数 / 类:
  - 允许 `<role>`, `<goal>`, `<step id name>`, `<protocol id>`, `<exit_contract>`
  - 禁止 `<steps>` 壳和未知顶层标签
  - 输出 Agent body AST
- 依赖 tasks: B1
- 测试影响:
  - 更新 `test_loader_xml_rendering.py`
  - 新增 role/goal/exit_contract missing / duplicate tests
- 风险点:
  - brief 中曾出现 workflow 字样, 但最终 skill-spec 以 5 类扁平标签为准。

#### B6. `@type:NAME` 7 类 Mention 静态可达性校验
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - 可新建 `packages/graph-agent/src/graph_agent/core/mentions.py`
- 改 lines / 函数 / 类:
  - Regex `@(subagent|tool|subgraph|protocol|step|reference|example):([a-zA-Z0-9_-]+)`
  - 校验 frontmatter registry + body protocol/step registry
  - target miss -> `[F-v3-mention-target-not-found]`
- 依赖 tasks: B5, A2
- 测试影响:
  - 新增 `packages/graph-agent/tests/core/test_v030_mentions.py`
  - 覆盖 7 类 success / target missing / syntax invalid
- 风险点:
  - 普通文本中的 `@` 不应误报; regex 残缺语法检测需小心。

#### B7. SUBGRAPH `target_skill` 解析 + IO 1:1 对齐
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/manifest.py`
- 改 lines / 函数 / 类:
  - `SubgraphNodeAST.target_skill`
  - resolver 调用 `resolve_skill(target_skill)`
  - 父 SUBGRAPH `io.inputs` / `io.outputs` 与 child `GRAPH.md io` 1:1 校验
- 依赖 tasks: A2, B4
- 测试影响:
  - 新增 `test_v030_subgraph_target_skill.py`
  - 覆盖 unregistered / IO mismatch / schema incompatible
- 风险点:
  - 递归 compile child graph 时需避免无限递归和 cache key 混乱。

#### B8. skill-compilation 测试同步
- 改 files:
  - `packages/graph-agent/tests/core/`
  - `packages/graph-agent/tests/integration/compiler/`
  - `packages/graph-agent/tests/fixtures/`
- 改 lines / 函数 / 类:
  - 迁移所有 V2.1 fixture 到 `schema_version: "0.3.0"`
  - 增加 v030 minimal graph fixtures
- 依赖 tasks: B1-B7
- 测试影响:
  - Unit + integration 全部更新
- 风险点:
  - pre-existing v21 tests 可能大量 fail; cutover PR 应删除或重命名旧语义测试, 不允许混跑两套 schema。

### C. execution-runtime (cognitive 装配 + DI 注入 + ActionRegistry)

#### C1. 退役 ExitContractRegistry
- 改 files:
  - `packages/graph-agent/src/graph_agent/runtime/exit_contract.py` (删除或 deprecated stub)
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `packages/graph-agent/src/graph_agent/cognitive/prompt.py`
- 改 lines / 函数 / 类:
  - 删除 per-turn `inject_exit_contract` / `strip`
  - system prompt 装配时 inline `{skill_exit_contract_inline}`
- 依赖 tasks: B5
- 测试影响:
  - 更新 `packages/graph-agent/tests/cognitive/test_prompt.py`
  - 更新 agent loop message history tests
- 风险点:
  - 旧测试可能断言 exit_contract 不进入 prompt history; 改为断言只在 system prompt 末尾出现一次。

#### C2. Cognitive Template 7 插槽装配
- 改 files:
  - `packages/graph-agent/src/graph_agent/cognitive/prompt.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- 改 lines / 函数 / 类:
  - `role`, `goal`, `thinking_style`, `knowledge_base`, `examples`, `ambiguity_feedback`, `protocol_citation`, `critical_reminders`, exit_contract inline
  - output_schema append to exit_contract末尾
- 依赖 tasks: C1, B5
- 测试影响:
  - 更新 `test_prompt.py`
  - 新增 prompt snapshot tests for reference/examples slots
- 风险点:
  - Prompt snapshot 可能脆弱; 建议断言关键 slots 而非整文逐字。

#### C3. SkillResolverProtocol DI 注入到 runtime
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/runner.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `packages/graph-agent/src/graph_agent/core/compiler.py`
- 改 lines / 函数 / 类:
  - run entry requires `skill_resolver`
  - child graph invoke uses resolver metadata
- 依赖 tasks: A2, B7
- 测试影响:
  - 更新 `test_runner_startup_invariants.py`
  - 新增 runtime resolver missing tests
- 风险点:
  - CLI path and test harness need fixture resolver injection.

#### C4. Builtin reference reader subagent 装配期调用 + fallback
- 改 files:
  - 新建 `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `packages/graph-agent/src/graph_agent/cognitive/prompt.py`
- 改 lines / 函数 / 类:
  - reader input contract `skill_id`, `phase_id`, `references`
  - timeout / error fallback raw excerpt 3000 tokens
  - WARN `[F-v3-reference-reader-failed]`
- 依赖 tasks: C2, D3
- 测试影响:
  - 新增 `test_reference_reader_builtin.py`
  - 覆盖 success / timeout / invalid output / fallback markdown
- 风险点:
  - 不要让 reader 失败阻断 Agent run; path invalid 仍是 compile fatal。

#### C5. `read_reference` + `read_example` builtin tools 注入
- 改 files:
  - 新建 `packages/graph-agent/src/graph_agent/tools/builtin/read_reference.py`
  - 新建 `packages/graph-agent/src/graph_agent/tools/builtin/read_example.py`
  - 更新 tool registry / graph assembler
- 改 lines / 函数 / 类:
  - Agent runtime 默认注入两个 builtin tools
  - tools 只能访问当前 Agent phase registry
- 依赖 tasks: B6, C2
- 测试影响:
  - 新增 `packages/graph-agent/tests/tools/test_builtin_resource_tools.py`
  - 覆盖 id not found / inline example / document example
- 风险点:
  - Tool payload 不能读跨 skill 未注册路径。

#### C6. subagent / SUBGRAPH 全走 SkillResolverProtocol
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `packages/graph-agent/src/graph_agent/core/runner.py`
- 改 lines / 函数 / 类:
  - User subagent dynamic tool uses `target_skill`
  - SUBGRAPH node uses resolved child graph
  - No `child_graph_path` public tool arg
- 依赖 tasks: A3, B7, D4
- 测试影响:
  - Update subagent executor tests
  - Add SUBGRAPH runtime isolated invoke tests
- 风险点:
  - Existing fan-out tests may assume path-based subagent fixtures.

#### C7. ActionRegistry runtime 一级寻址校验
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/actions.py`
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- 改 lines / 函数 / 类:
  - action name -> `<skill_root>/actions/<name>.py`
  - sandbox forbids `/`, `.`, `..`, absolute path, module path
  - runtime return dict + declared output fields only
- 依赖 tasks: B4
- 测试影响:
  - Update `test_v21_actions_loader.py`, `test_v21_actions_keys.py`
  - Add cross skill action forbidden tests
- 风险点:
  - Existing phase-local actions fixtures must migrate to root actions.

#### C8. execution-runtime integration / e2e tests
- 改 files:
  - `packages/graph-agent/tests/integration/`
  - `packages/graph-agent/tests/e2e/`
- 改 lines / 函数 / 类:
  - Minimal Agent run with cognitive template
  - Reference reader fallback
  - Builtin tools call
  - SUBGRAPH target skill invoke
- 依赖 tasks: C1-C7, D1-D4
- 测试影响:
  - Add v030 e2e fixtures
- 风险点:
  - Mock LLM fixtures must handle new prompt and tool calls.

### D. state-and-io-contract (Phase Wrapper + 黑板隔离)

#### D1. Input Funnel + StateMapper 切到 inline `io.inputs`
- 改 files:
  - `packages/graph-agent/src/graph_agent/runtime/state.py`
  - `packages/graph-agent/src/graph_agent/core/phase_node.py`
  - 可新建 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`
- 改 lines / 函数 / 类:
  - `filter_runtime_inputs(raw_inputs, schema)`
  - `StateMapper.build_phase_input`
  - `StateMapper.wrap_phase_output`
- 依赖 tasks: B4
- 测试影响:
  - 新增 `packages/graph-agent/tests/runtime/test_state_mapper.py`
  - Update phase node tests
- 风险点:
  - Unknown input policy needs match docs: strict unknown by default or explicit WARN drop.

#### D2. Phase Wrapper 覆盖 4 类节点
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/phase_node.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- 改 lines / 函数 / 类:
  - Wrapper for agent / logic / subgraph
  - Assembly-time wrapper for builtin reference reader
  - Common error normalization `[F-v3-runtime-state-mapping-failed]`
- 依赖 tasks: D1, C4
- 测试影响:
  - Update `test_phase_node.py`, `test_phase_nodes_m6.py`
  - Add wrapper per node type tests
- 风险点:
  - Refactor can double-wrap nodes if graph_assembler old logic remains.

#### D3. Builtin reference reader 黑板沙盒
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py`
  - `packages/graph-agent/src/graph_agent/runtime/state.py`
- 改 lines / 函数 / 类:
  - `ReaderSandboxState`
  - no parent data/messages inheritance
  - `flow.timeout_s` default 60
- 依赖 tasks: C4
- 测试影响:
  - Add reader sandbox tests
- 风险点:
  - Reader may need model resolver; keep dependency explicit, not global.

#### D4. A6 子图 SkillResolverProtocol 接轨
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`
- 改 lines / 函数 / 类:
  - child graph initial data = explicit input filtered by target `GRAPH.md io.inputs`
  - child flow deep copy + `subagent_depth + 1`
  - child messages empty
- 依赖 tasks: A2, B7, D1
- 测试影响:
  - Update `test_v21_subagent_executor.py`
  - Add parent data leak prevention tests
- 风险点:
  - Existing subagent tool result may expect parent data delta; migrate to tool result semantics.

#### D5. state-and-io tests
- 改 files:
  - `packages/graph-agent/tests/runtime/`
  - `packages/graph-agent/tests/core/test_phase_node.py`
- 改 lines / 函数 / 类:
  - smart reducer sequential overwrite vs parallel conflict
  - input funnel inline schema
  - child graph blackboard isolation
- 依赖 tasks: D1-D4
- 测试影响:
  - Unit + integration
- 风险点:
  - LangGraph reducer context may not expose super-step metadata; tests should encode chosen implementation detail.

### E. tracing-and-observability (trace event)

#### E1. AMBIGUITY_LOGGED trace event
- 改 files:
  - `packages/graph-agent/src/graph_agent/callbacks/events.py`
  - `packages/graph-agent/src/graph_agent/cognitive/ambiguity.py`
  - Tool wrapper / graph assembler where `log_ambiguity` runs
- 改 lines / 函数 / 类:
  - Add `TraceEventKind.AMBIGUITY_LOGGED`
  - Emit after successful `log_ambiguity` tool call
  - Payload: ambiguity_type, decision, reason, related refs/protocols
- 依赖 tasks: C2, C5
- 测试影响:
  - Update callbacks tests
  - Add ambiguity trace test
- 风险点:
  - Avoid duplicate frontend semantics: keep TOOL_CALL_END plus AMBIGUITY_LOGGED.

#### E2. BUILTIN_SUBAGENT_ENTER / EXIT / FALLBACK trace events
- 改 files:
  - `packages/graph-agent/src/graph_agent/callbacks/events.py`
  - `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py`
  - async logger / tracing callback
- 改 lines / 函数 / 类:
  - Add three event kinds
  - Emit around reference reader invocation
  - Fallback payload reason: remote_timeout / remote_error / config_missing / invalid_output
- 依赖 tasks: C4, D3
- 测试影响:
  - Add builtin reader trace event tests
- 风险点:
  - Assembly-time trace must have run_id/phase_id even before graph.invoke starts.

#### E3. Fallback trace payload
- 改 files:
  - `packages/graph-agent/src/graph_agent/callbacks/serialize.py`
  - `packages/graph-agent/src/graph_agent/callbacks/tracing.py`
- 改 lines / 函数 / 类:
  - `BuiltinSubagentTracePayload`
  - `fallback_reason`, `fallback_strategy`, `excerpt_token_limit`, warning message
- 依赖 tasks: E2
- 测试影响:
  - Snapshot JSON payload tests
- 风险点:
  - Keep payload small; never include full reference content.

#### E4. tracing tests sync
- 改 files:
  - `packages/graph-agent/tests/callbacks/`
  - `packages/graph-agent/tests/core/test_tracing_proxy.py`
- 改 lines / 函数 / 类:
  - Event enum snapshot
  - Tool event `tool_name` requirement
  - Reference reader fallback event order
- 依赖 tasks: E1-E3
- 测试影响:
  - Unit + integration
- 风险点:
  - Existing callback serializer may reject new enum values.

### F. 错误码 + log

#### F1. 退役所有 `[F-v21-*]`
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `packages/graph-agent/src/graph_agent/core/runner.py`
  - `packages/graph-agent/src/graph_agent/runtime/state.py`
  - tests that assert error strings
- 改 lines / 函数 / 类:
  - Replace helpers `_graph_fatal`, `_io_fatal`, `_actions_fatal` code prefixes
  - Ensure all codes exist in `docs/engine/skill-spec/11-error-code-spec.md`
- 依赖 tasks: A-F core implementations
- 测试影响:
  - Global grep test: no `[F-v21-` in `packages/graph-agent/src`
  - Update expected error strings
- 风险点:
  - Some archived docs or tests may still intentionally contain F-v21; grep should scope to src/tests, not docs backup.

#### F2. Standard error payload
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/exceptions.py`
  - `packages/graph-agent/src/graph_agent/callbacks/events.py`
  - `packages/graph-agent/src/graph_agent/core/runner.py`
- 改 lines / 函数 / 类:
  - Error payload fields: `code`, `level`, `stage`, `message`, `doc_link`
  - Include optional `skill_id`, `phase_id`, `field_path`, `source_path`
  - Runtime EXCEPTION event uses same payload
- 依赖 tasks: F1
- 测试影响:
  - Update `test_exceptions.py`
  - Add structured payload serialization test
- 风险点:
  - Avoid breaking public exception str too hard; keep human-readable message.

## CI Gate Checklist

Before PR merge:

- [ ] `pytest packages/graph-agent/tests/`
- [ ] `ruff check packages/graph-agent/src packages/graph-agent/tests`
- [ ] `mypy packages/graph-agent/src`
- [ ] `rg "\\[F-v21-" packages/graph-agent/src packages/graph-agent/tests` returns no unintended matches.
- [ ] `gh run list --branch main --limit 3` confirms recent main CI green.
- [ ] No skipped hooks, no `pytest -k` partial green presented as full green.
- [ ] Unit + integration + e2e tests updated in same PR as schema/runtime changes.

## High-risk Collision List

- Existing V2.1 fixtures use `mode: skill`, `<phase />` body tags, and physical `io/*.json`; they will fail until migrated together.
- Existing subagent fixtures use relative `path`; they must become registry `target_skill` fixtures with an injected resolver.
- Cache namespace must change or old cache snapshots will fail to hydrate into `AgentNodeAST`.
- Prompt snapshot tests will change significantly because exit_contract moves to system prompt tail with output_schema inline.
- StateMapper changes may expose pre-existing tests that assume full `state.data` visibility inside actions.
- Reference reader fallback must not block Agent runs; path validation remains compile-time fatal.
- Trace event enum expansion can break serializer snapshots.
- CLI / test helper callers must all provide `skill_resolver` and `model_resolver` or explicit test doubles.
