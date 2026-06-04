# Tasks: Engine MVP0 Rebuild V0.3.0 Cutover

本文档规划 V0.3.0 graph_skill cutover 的原子实施任务: `packages/graph-agent/src/`、`packages/graph-agent/tests/`、以及为 `SkillResolverProtocol` hard cutover 必需的 Studio backend / frontend / Tauri 配套改动。所有实现必须对齐 `docs/engine/mvp0/skill-spec/` 字段级规范和 engine 子模块 MVP0 alignment 文档, 不做任何向后兼容。

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

### 单 PR 原子切换策略

按 PM 2026-05-23 原则和 a1+a2 cross-verify 收敛结论, 本 cutover 采用**单 PR 原子切换**: engine src + graph-agent tests + Studio backend (`StudioSkillResolver` + import endpoint) + Studio frontend (Assets Panel SUBGRAPH 类目) + Studio Tauri (`pick_folder` command) 放进同一 cutover PR。PR 内拆 8-12 个小 commit 分层 review; main 只接受原子切换后的完整状态。依据: `docs/engine/mvp0/skill-spec/10-skill-resolver-protocol-spec.md:63-75` 要求含 child graph 的入口强注入 resolver, 缺 resolver FATAL, 拆 PR 会产生兼容 fallback 或 broken main。

1. skill-resolution Protocol 独立 commit。
2. AST / manifest / loader schema commit。
3. GRAPH.md 双轨拓扑 + inline IO commit。
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
  - 大量旧测试直接调用 `compile_skill(root)`; 含 child skill 的测试必须统一注入 resolver fixture, 不允许靠 fallback / mock resolver 掩盖 missing resolver。
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
  - 内部 discriminator 从 `mode: Literal["skill"]` 切到 `mode: Literal["agent"]`, 但作者不写 `mode:` frontmatter
  - 新增字段 `role`, `goal`, `steps`, `protocols`, `examples`, `references`, `subgraphs`, `tools`, `max_iterations`, `llm_role`, `io`
- 依赖 tasks: A1
- 测试影响:
  - 更新 `packages/graph-agent/tests/core/test_v21_ast_schema.py`
  - 更新 `packages/graph-agent/tests/core/test_manifest.py`
  - 更新 cache serialization tests
- 风险点:
  - cache hit 反序列化旧 SkillNodeAST 会失败; cutover 可选择 bump cache namespace。

#### B2. phase 文件名推导类型 + phase 文件 3 选 1 校验
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/manifest.py`
- 改 lines / 函数 / 类:
  - 物理文件名推导内部类型: `SKILL.md -> agent`, `LOGIC.md -> logic`, `SUBGRAPH.md -> subgraph`
  - Loader 注入内部 AST `mode`, 作者不在 phase frontmatter 写 `mode:`
  - 物理目录 `phases/<id>/` 恰好一个 node file
- 依赖 tasks: B1
- 测试影响:
  - 更新 `test_v21_loader.py`, `test_loader_subgraph_is_file.py`
  - 新增 duplicate node file / missing node file tests
- 风险点:
  - 旧测试 fixture 中 `mode: skill` / `mode: agent` / `mode: logic` / `mode: subgraph` frontmatter 需全部删除, 类型由文件名决定。

#### B3. GRAPH.md 回归双轨: frontmatter phases 注册 + body `<phase>` 拓扑
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/manifest.py`
  - `packages/graph-agent/src/graph_agent/core/cache.py`
- 改 lines / 函数 / 类:
  - `_build_graph_manifest()` 读取 `schema_version: "v0.3.0"`、inline `io`、frontmatter `phases: list[str]`
  - `_extract_phase_attrs()` / phase token parser 读取 body `<phase depends_on output>name</phase>` 作为 DAG 拓扑
  - `_validate_graph_topology()` 校验 frontmatter phase 名、body phase 名、物理目录三者一致
- 依赖 tasks: B2
- 测试影响:
  - 更新 `test_t11_phase_token_info.py`
  - 更新 graph topology fixtures
  - 新增双轨不一致 / body depends_on unknown / cycle / island / output phase tests
- 风险点:
  - frontmatter `phases` 只注册名字, `depends_on` 不在 frontmatter; 旧纯 YAML topology parser 不能作为 truth source。

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
  - 允许 `<role>`, `<goal>`, `<step id name>`, `<protocol id>`, `<example id>`
  - 禁止 `<steps>` 壳和未知顶层标签
  - 禁止 `<exit_contract>`; exit_contract 只在 cognitive template hardcode
  - 输出 Agent body AST
- 依赖 tasks: B1
- 测试影响:
  - 更新 `test_loader_xml_rendering.py`
  - 新增 role/goal missing / duplicate、example parse、exit_contract forbidden tests
- 风险点:
  - brief 中曾出现 workflow 字样, 但最终 skill-spec 以 5 类扁平标签为准。

#### B6. `@type:NAME` 7 类 Mention 静态可达性校验
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - 可新建 `packages/graph-agent/src/graph_agent/core/mentions.py`
- 改 lines / 函数 / 类:
  - Regex `@(subagent|tool|subgraph|protocol|step|reference|example):([a-zA-Z0-9_-]+)`
  - 校验 frontmatter registry + body protocol/step/example registry
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
  - 迁移所有 V2.1 fixture 到 `schema_version: "v0.3.0"` + GRAPH 双轨
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
  - system prompt 末尾 hardcode `<exit_contract>` 并拼接 `{output_schema}`
- 依赖 tasks: B5
- 测试影响:
  - 更新 `packages/graph-agent/tests/cognitive/test_prompt.py`
  - 更新 agent loop message history tests
- 风险点:
  - 旧测试可能断言 exit_contract 不进入 prompt history; 改为断言只在 system prompt 末尾出现一次。

#### C2. Cognitive Template 8 插槽装配
- 改 files:
  - `packages/graph-agent/src/graph_agent/cognitive/prompt.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- 改 lines / 函数 / 类:
  - 8 固定容器: `role`, `goal`, `thinking_style`, `knowledge_base`, `examples`, `ambiguity_feedback`, `protocol_citation`, `critical_reminders`
  - 使用 ground truth placeholder: `{llm_role_prefix_section}`, `{skill_steps_splat}`, `{aligned_concepts_and_critical_corrections_markdown}`, `{reference_registry_listing}`, `{skill_examples_inline}`, `{example_registry_listing}`, `{skill_protocols_splat}`, `{output_schema}`
  - `<exit_contract>` 作为 template 末尾 hardcode block, output_schema append 到其中
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
  - 覆盖 id not found / body inline example / document example
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
  - action name -> phase-local `phases/<phase_id>/actions/<name>.py` or Engine/Studio common action registry
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
  - Ensure all codes exist in `docs/engine/mvp0/skill-spec/11-error-code-spec.md`
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

### G. Schema Cleanup (按 PM 2026-05-23 原则: 对齐 docs mvp0, 不做任何向后兼容)

本节实施 PM 2026-05-23 拍板 hard cutover: V2.1 主路径 + codemod + schema 2.0 stub + V2.1 fixture + 旧 test + context_mapping 全链路 + python_callable + 伪需求 docs-frontmatter-schema 全清, 不留向后兼容代码 / fallback / mock.

#### G1. V2.1 main path 全删
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/runner.py`
  - `packages/graph-agent/src/graph_agent/core/compiler.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `packages/graph-agent/src/graph_agent/runtime/state.py`
- 改 lines / 函数 / 类:
  - 删除 `runner.py:456-525` `_run_v21_skill_dict()`。
  - 删除 `runner.py:274` 调用 `_run_v21_skill_dict` 的 dispatch 分支。
  - 删除 `compiler.py` 中 V2.1 兼容代码; 实施时 grep `_run_v21|v21_` 确认范围。
  - 删除 `graph_assembler.py` 中 V2.1 兼容; SUBGRAPH / subagent 只走 `target_skill` + `SkillResolverProtocol`。
  - 删除 `runtime/state.py` 中 V2.1 `BlackboardState` path; V0.3.0 state shape 以 `data.inputs` / `data.phase_outputs` / `data.scratch` 为准。
- 依赖 tasks: A-F V0.3.0 replacements complete.
- 测试影响:
  - 删除 / 重写仍断言 V2.1 runner/compiler/assembler/state 的 tests。
  - 增加 grep guard: `rg "_run_v21_skill_dict|v21_|sub_skill_ref|BlackboardState" packages/graph-agent/src packages/graph-agent/tests` 无 active V2.1 main-path 残留。
- 风险点:
  - 不允许把旧路径改名成 V0.3.0 facade; 语义必须来自 `docs/engine/mvp0/skill-spec/`.

#### G2. codemod 全删
- 改 files:
  - 删除 `packages/graph-agent/src/graph_agent/codemod/v21_migrator.py`
  - 删除 `packages/graph-agent/src/graph_agent/codemod/` 目录, 如清空
- 改 lines / 函数 / 类:
  - 删除整个 schema 2.0 -> V2.1 migration helper; 该文件约 454 行, V0.3.0 不需要。
  - 删除所有 imports / CLI references / tests that mention `v21_migrator`.
- 依赖 tasks: G1, B8 fixture migration.
- 测试影响:
  - 删除 codemod unit / golden fixtures。
  - grep guard: `rg "v21_migrator|codemod_v20" packages/graph-agent/src packages/graph-agent/tests` 无 active match.
- 风险点:
  - 不保留 dry-run helper; 保留会暗示 schema 2.0 / V2.1 迁移仍是 supported path.

#### G3. schema 2.0 parser stub 全删
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/parser.py`
- 改 lines / 函数 / 类:
  - 删除 `parser.py:230-245` `parse_skill_file` stub。
  - 删除 `locate_line_for_pydantic_loc` 旧 AST line 定位器和死依赖。
  - 检查 parser.py 是否还有 V2.1 / schema 2.0 残留: `rg "schema_version|parse_skill_file" packages/graph-agent/src/graph_agent/core/parser.py`.
- 依赖 tasks: B3/B4 V0.3.0 GRAPH 双轨 + inline IO parser complete.
- 测试影响:
  - 删除仍 import `parse_skill_file` 或 `locate_line_for_pydantic_loc` 的 tests。
  - V0.3.0 source-span tests 后续由 parser implementation 新增, 不保留旧 test skip。
- 风险点:
  - 删除 stub 后 public import 可能断; 这是 hard cutover, 不补 compatibility shim.

#### G4. V2.1 fixture 全清
- 改 files:
  - 删除 `packages/graph-agent/tests/fixtures/canvas_serializer/with_comments_v21/`
  - 删除 `packages/graph-agent/tests/fixtures/codemod_v20/{multi_phase,complex}/SKILL.md`
  - 删除 `packages/graph-agent/tests/fixtures/subagent_minimal/GRAPH.md` 和 `phases/main/subskills/echo_expert/GRAPH.md`
  - 删除 `packages/graph-agent/tests/fixtures/fake_canvas_fanout/`
  - 新建 V0.3.0 minimal fixtures covering `GRAPH.md`, `SKILL.md`, `LOGIC.md`, and `SUBGRAPH.md`
- 改 lines / 函数 / 类:
  - 实施时 grep `schema_version.*"2\\.[01]"|<python_callable>` 确认完整清单。
  - 旧 `mode: skill`, phase frontmatter `mode:`, physical `io/*.json`, relative subskill paths, and `<python_callable>` fixtures must not remain in active tests.
  - GRAPH.md active fixtures must use `schema_version: "v0.3.0"` + frontmatter `phases: [name]` + body `<phase depends_on="input">name</phase>` dual track.
- 依赖 tasks: B1-B8 parser and schema tasks.
- 测试影响:
  - Update integration/e2e fixtures to `schema_version: "v0.3.0"`.
  - Add target_skill registry fixture and resolver fixture for child graph coverage.
- 风险点:
  - Fixture deletion must be paired with test deletion/rewrite so CI does not silently point at missing paths.

#### G5. #14 test_compiler_line_locations 直接删
- 改 files:
  - 删除 `packages/graph-agent/tests/core/test_compiler_line_locations.py`
  - `packages/graph-agent/src/graph_agent/core/parser.py`
- 改 lines / 函数 / 类:
  - 删除 `parser.py:230-245` `locate_line_for_pydantic_loc` / old AST line-location helper.
  - 不加 `@pytest.mark.skip`; 不保留 deferred V2.1 test.
- 依赖 tasks: G3.
- 测试影响:
  - CI 不再包含 V2.1 line-location test。
  - V0.3.0 GRAPH dual-track source-span test 在 parser cutover implementation 中重新添加。
- 风险点:
  - 新测试必须围绕 V0.3.0 AST and source spans, not V2.1 Pydantic loc behavior.

#### G6. context_mapping 全链路清
- 改 files:
  - 删除 `packages/graph-agent/src/graph_agent/io/context_resolver.py`
  - 更新 / 删除 `packages/graph-agent/src/graph_agent/core/harness.py`
  - 更新 / 删除 `packages/graph-agent/src/graph_agent/core/validators/prompt_quality.py`
  - 更新 / 删除 `packages/graph-agent/src/graph_agent/core/validators/template_variables.py`
  - 删除 `packages/graph-agent/src/graph_agent/skills/builtin/md-patch/`
  - 删除 `packages/graph-agent/src/graph_agent/tools/md_to_json.py`
  - 删除含 `context_mapping` 的 fixtures, especially `tests/fixtures/codemod_v20/**/SKILL.md`
- 改 lines / 函数 / 类:
  - 删除 `harness.py:356-362, 371, 847, 851` context_mapping entry/internal refs; 如果 legacy harness 只服务旧 schema, 可整体删除。
  - 删除 `prompt_quality.py:186` implicit context_mapping validation。
  - 删除 `template_variables.py:27, 44` placeholder validation tied to context_mapping。
  - 删除 builtin md-patch and `md_to_json.py`; V0.3.0 docs have zero hits for this builtin path.
- 依赖 tasks: D1-D5 StateMapper / Phase Wrapper complete; G2/G4 codemod fixtures removed.
- 测试影响:
  - Delete context resolver unit tests and old validator tests.
  - Update tests to assert schema properties / required fields, not context_mapping aliases.
- 风险点:
  - Do not mark context_mapping as deprecated in active user docs; remove it to avoid teaching a dead entry point.

#### G7. python_callable 全清
- 改 files:
  - `packages/graph-agent/src/graph_agent/core/manifest.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - V2.1 LOGIC fixtures
- 改 lines / 函数 / 类:
  - `manifest.py:143` 删除 `python_callable: str`, 改为 `actions: list[str]` per `docs/engine/mvp0/skill-spec/03-logic-md-spec.md:24`.
  - `graph_assembler.py:170-171` 改为迭代 `actions`.
  - `loader.py:1043, 1094, 1108` 改 `actions:` 解析。
  - `<python_callable>` fixtures 在 G4 一并清。
- 依赖 tasks: B5 LOGIC actions parser, C2 action runtime.
- 测试影响:
  - Add tests for action list parsing, missing action file, invalid action name, and undeclared output.
  - grep guard: `rg "python_callable|<python_callable>" packages/graph-agent/src packages/graph-agent/tests` no active matches.
- 风险点:
  - Do not rename `python_callable`; remove it. MVP0 LOGIC only uses `actions:`.

#### G8. docs-frontmatter-schema 砍
- 改 files:
  - 删除 `.kiro/specs/docs-frontmatter-schema/`
- 改 lines / 函数 / 类:
  - Remove `design.md` and `tasks.md` from that directory.
  - Ensure engine cutover docs no longer list docs frontmatter schema as finalized implementation scope.
- 依赖 tasks: none.
- 测试影响:
  - Docs-only cleanup; no src/test change.
- 风险点:
  - Do not replace it with another engine blocker. Docs metadata can be reopened as a separate docs hygiene task later.

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

- Existing V2.1 fixtures use `mode: skill`, self-closing `<phase />` tags with `id/src`, and physical `io/*.json`; they will fail until migrated to `schema_version: "v0.3.0"` + GRAPH dual-track together.
- Existing subagent fixtures use relative `path`; they must become registry `target_skill` fixtures with an injected resolver.
- Cache namespace must change or old cache snapshots will fail to hydrate into `AgentNodeAST`.
- Prompt snapshot tests will change significantly because exit_contract moves to system prompt tail with output_schema inline.
- StateMapper changes may expose pre-existing tests that assume full `state.data` visibility inside actions.
- Reference reader fallback must not block Agent runs; path validation remains compile-time fatal.
- Trace event enum expansion can break serializer snapshots.
- CLI / test helper callers must all provide `skill_resolver` and `model_resolver` or explicit test doubles.
