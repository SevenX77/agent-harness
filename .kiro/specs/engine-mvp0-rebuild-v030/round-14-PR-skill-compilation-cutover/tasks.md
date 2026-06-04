---
spec: engine-mvp0-rebuild-v030/round-14-PR-skill-compilation-cutover
phase: PR skill-compilation cutover tasks
owner: a1 tasks / a2 design+requirements+research / a3 gate
scope: Task B only, tests-first, [BREAKING] SOP-05 cutover
---

# PR round-14: Skill Compilation Cutover Tasks

## §0 Scope

本 PR 只做 Task B skill-compilation 静态编译契约硬切换: B1-B8。C2 Cognitive Template 8 插槽装配不在本轮, 只保证 Agent AST 能解析出 C2 后续需要的 role/goal/steps/protocols/examples/resources。

唯一格式权威: `docs/engine/mvp0/skill-spec/00-FORMAT-GROUND-TRUTH.md`。

[BREAKING] cutover discipline:

- src 改 + tests/fixtures 改必须同 PR 同步落地。
- 第一批任务只写红灯测试, 不改 src。
- 禁止用 `xfail` / blanket quarantine 掩盖本轮 V0.3 contract tests。
- round-14 WIP 与已 merge 污染都要 sweep: `graph_serializer.py` schema/version/body phase、`loader.py` hardcoded `"0.3.0"`、pre-existing v030 fixtures 纯 YAML、tests 中 `"0.3.0"` 无 v。
- `skills/` 下真实业务 skill corpus 本轮不迁移, 仅允许明确隔离在非 active compile/import path。

## §1 依赖图

```text
r14.1 Tests-first red suite
  ├─> r14.2 B1 AgentNodeAST-only AST
  │     └─> r14.3 B2 filename-derived phase type
  │           └─> r14.4 B3 GRAPH.md dual-track topology
  │                 └─> r14.5 B4 inline root IO
  │                       └─> r14.6 B5 Agent body 5 tags
  │                             └─> r14.7 B6 mention reachability
  │                                   └─> r14.8 B7 SUBGRAPH target_skill + IO
  └─> r14.9 B8 fixture/test/cache/serializer sweep
        └─> r14.10 grep + CI gate
```

## §2 r14.1: Tests-first red suite

**目标**: 先写失败测试锁定 design.md / requirements.md 的验收标准和错误码。此 task 只改 tests/fixtures, 不改 src。

**Files**:

- `packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py` 新增
- `packages/graph-agent/tests/core/test_compiler_schema_version_tolerance.py`
- `packages/graph-agent/tests/core/test_v21_loader.py` 或迁移为 `test_v030_loader.py`
- `packages/graph-agent/tests/core/test_v21_graph_serializer.py` 或迁移为 `test_v030_graph_serializer.py`
- `packages/graph-agent/tests/core/test_gamma0_contract_tdd.py`
- `packages/graph-agent/tests/core/test_gamma2_child_graph_isolation.py`
- `packages/graph-agent/tests/core/test_gamma2_phase_outputs_flow.py`
- `packages/graph-agent/tests/core/test_gamma2_reference_reader_sandbox.py`
- `packages/graph-agent/tests/core/test_delta_skill_resolution_red.py`
- `packages/graph-agent/tests/core/test_skill_resolver_protocol.py`
- `packages/graph-agent/tests/core/test_compiler_line_locations.py`
- `packages/graph-agent/tests/core/validators/test_tool_paths_escape.py`

**Red tests**:

- `schema_version: "0.3.0"` fatal `[F-v3-graph-schema-version-mismatch]`; `"v0.3.0"` pass.
- phase frontmatter 写任意 `mode:` fatal/validation fail; 不要求作者写 `mode`, loader 从 filename 注入内部 discriminator。
- phase frontmatter 写 `schema_version` / `graph_skill_id` / `phase_id` fatal, 按对应 phase domain unknown-field 错误处理。
- `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 三类 phase 都能装载 `validator: boolean`, 缺省为 `false`; 非 boolean fatal 对应 domain validator/type 错误。
- `SkillNodeAST` / `mode: skill` TypeAdapter path fail。
- phase 目录多节点文件 fatal `[F-v3-graph-phase-mode-ambiguous]`。
- phase 目录无节点文件 fatal `[F-v3-graph-phase-node-missing]`。
- GRAPH.md 缺 frontmatter `phases: list[str]` fatal `[F-v3-graph-phases-missing]`。
- GRAPH.md 缺 body `<phase>` 或 body/frontmatter 注册缺漏 fatal `[F-v3-graph-phase-id-invalid]`。
- body/frontmatter phase name 与物理目录名不一致 fatal `[F-v3-graph-phase-name-mismatch]`。
- body `<phase depends_on>` 引用未知 phase 或入口非 `input` fatal `[F-v3-graph-depends-unknown]`。
- body `output` 标记非法 fatal `[F-v3-graph-output-phase-invalid]`。
- 物理 `io/inputs.json` / `io/outputs.json` / `io_inputs_ref` / `io_outputs_ref` fatal `[F-v3-graph-io-physical-file-deprecated]`。
- Agent body 只接受 `<role>`, `<goal>`, `<step>`, `<protocol>`, `<example>`; `<steps>` / `<protocols>` / `<exit_contract>` fatal `[F-v3-agent-body-tag-unknown]`。
- `@example:E1` 同时覆盖 body `<example id="E1">` 和 frontmatter document example registry。
- missing mention fatal `[F-v3-mention-target-not-found]`。
- SUBGRAPH parent/child `io.inputs.properties` 或 `io.outputs.properties` 不一致 fatal `[F-v3-subgraph-io-mismatch]`。
- `graph_serializer.serialize_graph()` fresh render 输出 `"v0.3.0"` + frontmatter phase names + body `<phase depends_on ...>name</phase>`, 不输出纯 YAML topology。
- `tests/conftest.py` blanket xfail 去掉后, gamma0/gamma2/delta/skill_resolver/line_locations 文件保持 active red/green, 不 xfail 掩盖。

**依赖**: none。

**验收**: 新增/迁移测试在当前实现下红灯, 且红灯原因分别落到上述错误码或缺失行为。

## §3 r14.2: B1 AgentNodeAST-only AST

**目标**: 退役 `SkillNodeAST`, 仅保留 Agent/Logic/Subgraph AST。

**Files / functions**:

- `packages/graph-agent/src/graph_agent/core/manifest.py`
  - 删除 `SkillNodeAST`
  - `PhaseAST = Annotated[LogicNodeAST | SubgraphNodeAST | AgentNodeAST, Field(discriminator="mode")]`
  - `AgentNodeAST.mode = Literal["agent"]`
  - `AgentNodeAST.examples` 拆为 body inline example AST + frontmatter document examples 所需结构
  - 删除 `python_callable` 从 Agent/Skill path 残留
- `packages/graph-agent/src/graph_agent/core/loader.py`
  - 删除 `SkillNodeAST` import 和分支
  - `_build_phase_document()` 只构建 `AgentNodeAST` for `SKILL.md`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - 删除 `SkillNodeAST` branch / `node_kind="skill"`
- `packages/graph-agent/src/graph_agent/core/cache.py`
  - cache hydrate/dump 不再引用 SkillNodeAST
- `apps/studio/backend/app/services/skills.py`
  - schema registry 仅保留 `"agent": AgentNodeAST`

**Test sync**:

- 更新 `test_v21_ast_schema.py`, `test_v21_codemod.py`, `test_v21_loader.py`, integration smoke 中旧 `SkillNodeAST` import。

**依赖**: r14.1。

**验收**:

- `rg -n "class SkillNodeAST|SkillNodeAST|mode: Literal\\[\\\"skill\\\"\\]|node_kind=\\\"skill\\\"" packages/graph-agent/src apps/studio/backend/app` 无 active 命中。

## §4 r14.3: B2 filename-derived phase type

**目标**: 作者不写 `mode:`; phase 类型由 `SKILL.md` / `LOGIC.md` / `SUBGRAPH.md` 文件名推导, loader 注入内部 discriminator。

**Files / functions**:

- `packages/graph-agent/src/graph_agent/core/loader.py`
  - `_PHASE_FILE_TO_MODE = {"SKILL.md": "agent", "LOGIC.md": "logic", "SUBGRAPH.md": "subgraph"}`
  - 删除 `_validate_mode_matches_filename()`
  - `_discover_phase_files()` 保证每个 `phases/<id>/` 恰好一个节点文件
  - phase frontmatter 预校验禁止 `mode`, `schema_version`, `graph_skill_id`, `phase_id`; 命中后抛对应 `F-v3-*-unknown-field` fatal, 不进入 legacy mode 纠正分支
  - `_build_phase_document()` 在 Pydantic validate 前 `data["mode"] = mode`
  - 若 frontmatter 已含 `mode`, 按 unknown/forbidden field fatal, 不再做“纠正 mode”错误
- `packages/graph-agent/src/graph_agent/core/manifest.py`
  - phase AST 内部保留 `mode` discriminator, 但文档输入不要求该字段
  - `LogicNodeAST.validator: bool = False`, `SubgraphNodeAST.validator: bool = False`, `AgentNodeAST.validator: bool = False`

**Test sync**:

- 删除 active fixtures 的 `mode: agent` / `mode: logic` / `mode: subgraph` / `mode: skill`。
- 删除 active fixtures 的 phase-level `schema_version` / `graph_skill_id` / `phase_id`。
- 增加三类 phase `validator` 缺省 false、显式 true/false、非 boolean 失败测试, 覆盖 `LogicNodeAST`。
- duplicate node file / missing node file tests 精确断言 `[F-v3-graph-phase-mode-ambiguous]` / `[F-v3-graph-phase-node-missing]`。

**依赖**: r14.2。

**验收**:

- `rg -n "_validate_mode_matches_filename|frontmatter\\.get\\(\\\"mode\\\"\\)|yaml_mode|mode: skill|mode: agent|mode: logic|mode: subgraph|^schema_version:|^graph_skill_id:|^phase_id:" packages/graph-agent/src packages/graph-agent/tests` 无 active fixture/loader 依赖命中; 内部 AST `mode` 字段和 root `GRAPH.md schema_version` 除外。

## §5 r14.4: B3 GRAPH.md dual-track topology

**目标**: GRAPH.md 双轨制: frontmatter `phases: list[str]` 只注册名字; body `<phase depends_on output>name</phase>` 是 DAG 拓扑事实来源。

**Files / functions**:

- `packages/graph-agent/src/graph_agent/core/manifest.py`
  - `GraphManifest.schema_version = Literal["v0.3.0"]`
  - `GraphManifest.phases: list[str]`
  - 删除 `GraphPhaseRef.src/depends_on` 作为 frontmatter topology 结构; 若仍需 runtime topo, 使用 loader 解析出的内部 graph topology model
- `packages/graph-agent/src/graph_agent/core/loader.py`
  - `_build_graph_manifest()` 校验 `"v0.3.0"`、frontmatter `phases: list[str]`
  - 恢复/重写 `_extract_phase_attrs()` 或等价函数, 解析 body `<phase depends_on="..." output>name</phase>`
  - `_extract_phase_token_info()` 保留用于 body phase source spans, 但适配新 tag 形态
  - `_validate_graph_topology(graph_path, manifest.phases, body_phase_refs, skill_root)` 校验:
    - frontmatter names == body names == physical dirs
    - body/frontmatter name 与 physical dir mismatch -> `[F-v3-graph-phase-name-mismatch]`
    - duplicate name -> `[F-v3-graph-phase-id-duplicate]`
    - unknown dependency / bad input dependency -> `[F-v3-graph-depends-unknown]`
    - cycle -> `[F-v3-graph-phase-cycle]`
    - island -> `[F-v3-graph-phase-island]`
    - invalid/missing output mark -> `[F-v3-graph-output-phase-invalid]`
    - missing body `<phase>` -> `[F-v3-graph-phase-id-invalid]`
- `packages/graph-agent/src/graph_agent/core/graph_serializer.py`
  - `_render_fresh_graph()` 输出 frontmatter phase names + body `<phase>` lines
  - 修 `graph_serializer.py:34/41`: schema_version 加 `v`, body phase 序列化回双轨, 不产出纯 YAML topology
- `packages/graph-agent/src/graph_agent/core/cache.py`
  - cache graph metadata 使用双轨 topo digest

**Merged pollution sweep**:

- `loader.py:642/647` 附近 hardcoded `"0.3.0"` 改 `"v0.3.0"`。
- `packages/graph-agent/tests/fixtures/v030_agent_demo/GRAPH.md`、`registry/echo_agent/GRAPH.md` 等纯 YAML fixture 加 body `<phase>`。
- 十余处 tests helper 中 `schema_version: "0.3.0"` 改 `"v0.3.0"`。

**依赖**: r14.3。

**验收**:

- `rg -n "schema_version: [\"']0\\.3\\.0[\"']|schema_version\\\": \\\"0\\.3\\.0\\\"|Literal\\[\\\"0\\.3\\.0\\\"\\]|must be exactly \\\"0\\.3\\.0\\\"" packages/graph-agent/src packages/graph-agent/tests apps/studio/backend` 无 active 命中。
- `rg -n "depends_on:\\s*\\[|src:\\s*phases/" packages/graph-agent/tests packages/graph-agent/src` 无 active GRAPH topology fixture 命中。

## §6 r14.5: B4 inline root IO

**目标**: root IO 只来自 GRAPH.md frontmatter `io.inputs` / `io.outputs`; 物理 IO 文件和 ref 字段 fatal。

**Files / functions**:

- `packages/graph-agent/src/graph_agent/core/manifest.py`
  - 删除 `io_inputs_ref`, `io_outputs_ref`
  - `GraphManifest.io: PhaseIOSchema` 必填
- `packages/graph-agent/src/graph_agent/core/loader.py`
  - `_reject_deprecated_physical_io(root)`
  - `_build_graph_manifest()` 发现 `io_inputs_ref` / `io_outputs_ref` fatal
  - 删除 `_resolve_io_ref()` / `_validate_io_schema()` active path
  - `_validate_inline_io_schema()` 作为唯一 root IO validator
- `packages/graph-agent/src/graph_agent/core/graph_serializer.py`
  - 删除 `_IO_RE` / `<input src>` / `<output src>` rewrite
  - fresh render inline `io`
- `packages/graph-agent/src/graph_agent/core/cache.py`
  - 不扫描 `io/*.json`

**Test sync**:

- 删除 active fixtures 的 `io/inputs.json`, `io/outputs.json`。
- helper 把 schema inline 到 GRAPH.md。

**依赖**: r14.4。

**验收**:

- `rg -n "io_inputs_ref|io_outputs_ref|io/inputs\\.json|io/outputs\\.json|_validate_io_schema|_resolve_io_ref" packages/graph-agent/src packages/graph-agent/tests apps/studio/backend` 无 active 命中。

## §7 r14.6: B5 Agent body 5 tags

**目标**: Agent body AST 解析 5 类扁平标签: role/goal/step/protocol/example。禁止复数壳和 exit_contract。

**Files / functions**:

- `packages/graph-agent/src/graph_agent/core/loader.py`
  - `_parse_agent_body()`
  - `_extract_agent_steps()`
  - `_extract_agent_protocols()`
  - 新增 `_extract_agent_examples()`
  - `extract_raw_blocks()` allowed tags 增加 `example`, 删除 `exit_contract`
- `packages/graph-agent/src/graph_agent/core/manifest.py`
  - 新增 `AgentExample` 或等价 body inline example AST
  - `AgentNodeAST.examples_inline` / `examples` 命名以 design 最终字段为准, 但 frontmatter `examples` 仅 document registry
  - 删除 `ExampleSpec.type/content`

**Test sync**:

- `<exit_contract>` fatal `[F-v3-agent-body-tag-unknown]`。
- `<example id>` parse success, duplicate/empty/invalid id fail。
- frontmatter `examples` only `{id,path,summary}`。

**依赖**: r14.5。

**验收**:

- `rg -n "exit_contract|ExampleSpec.*content|type: inline|inline_examples_splat|document_examples_registry|<steps>|<protocols>" packages/graph-agent/src packages/graph-agent/tests` 无 active polluted contract 命中; allowed docs/comments 必须说明非 active。

## §8 r14.7: B6 mention reachability

**目标**: Agent body `@type:NAME` 精确静态可达。

**Files / functions**:

- `packages/graph-agent/src/graph_agent/core/mentions.py`
  - `MENTION_RE = r"@(subagent|tool|subgraph|protocol|step|reference|example):([a-zA-Z0-9_-]+)"`
  - `scan_mentions()`
  - `first_broken_mention()`
- `packages/graph-agent/src/graph_agent/core/loader.py`
  - `_validate_agent_mentions(path, ast, body)`
  - domains:
    - `subagent`: frontmatter `subagents[].name`
    - `tool`: frontmatter `tools[]` + builtin `finish_task`, `read_reference`, `read_example`, `log_ambiguity`
    - `subgraph`: frontmatter `subgraphs[].name`
    - `protocol`: body `<protocol id>`
    - `step`: body `<step id>`
    - `reference`: frontmatter `references[].id`
    - `example`: body `<example id>` + frontmatter document `examples[].id`

**Test sync**:

- success and target-missing for all 7 domains.
- malformed mention fatal `[F-v3-mention-syntax-invalid]`.
- target missing fatal `[F-v3-mention-target-not-found]`.

**依赖**: r14.6。

**验收**:

- `pytest packages/graph-agent/tests/core/test_v030_mentions.py -v` 或等价 mention tests 通过。

## §9 r14.8: B7 SUBGRAPH target_skill + IO 1:1

**目标**: SUBGRAPH 编译期通过 resolver 找 child graph, 并校验 parent phase IO 与 child root IO 1:1。

**Files / functions**:

- `packages/graph-agent/src/graph_agent/core/manifest.py`
  - `SubgraphNodeAST.io: PhaseIOSchema` 必填
  - `target_skill` 保持必填
- `packages/graph-agent/src/graph_agent/core/loader.py`
  - `_validate_subgraph_io_contracts(phase_docs, skill_resolver=...)`
  - compile child root via `resolve_skill_root()` / `SkillLoader(...).compile_skill(...)`
  - missing resolver fatal `[F-v3-resolver-missing]`
  - mismatch fatal `[F-v3-subgraph-io-mismatch]`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  - 使用 compiled metadata, 不做路径 fallback
- `packages/graph-agent/tests/fixtures/v030_skill_registry/`
  - child graph fixtures 用 `"v0.3.0"` + GRAPH dual-track + inline IO

**Test sync**:

- target_skill unregistered / resolver invalid path / missing resolver / inputs mismatch / outputs mismatch / success。

**依赖**: r14.5; tests 可在 r14.1 先写红灯。

**验收**:

- `pytest packages/graph-agent/tests/core/test_delta_skill_resolution_red.py packages/graph-agent/tests/core/test_skill_resolver_protocol.py -v` 通过。

## §10 r14.9: B8 fixtures, conftest, serializer, cache sweep

**目标**: 真迁移 tests/fixtures, 撤销 blanket xfail, 不重复上次 46 xpass 误隔离。

**Files / functions**:

- `packages/graph-agent/tests/conftest.py`
  - 删除 round-14 blanket xfail 列表 / marker 注入
  - 仅保留明确非本轮真实 skill corpus xfail, 且不能覆盖 gamma0/gamma2/delta/new v030 tests
- `packages/graph-agent/tests/core/`
  - gamma0/gamma2/delta/skill_resolver/line_locations helpers 全部改 `"v0.3.0"` + dual-track + inline IO + no mode
  - v21-only tests 真删/真迁移, 不 blanket xfail
- `packages/graph-agent/tests/fixtures/`
  - `v030_agent_demo/GRAPH.md`, registry child graphs, fake canvas/core fixtures 全部 dual-track
- `packages/graph-agent/src/graph_agent/core/cache.py`
  - namespace bump: no `graph-agent-v21`
  - digest includes GRAPH.md body phase topology
- `packages/graph-agent/src/graph_agent/core/graph_serializer.py`
  - serializer tests cover `"v0.3.0"` and body `<phase>`
- `apps/studio/backend/app/services/skills.py`
  - blank/template/import examples if active graph import path uses this schema

**Merged pollution sweep**:

- `graph_serializer.py:34/41`: `"v0.3.0"` and body `<phase>` render.
- `loader.py:642/647`: hardcoded `"0.3.0"` strings.
- pre-existing `v030_agent_demo/GRAPH.md` and registry child graph pure YAML fixtures.
- all active test helpers hardcoding `schema_version: "0.3.0"`.

**依赖**: r14.2-r14.8.

**验收**:

- `pytest packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py -v`
- `pytest packages/graph-agent/tests/core/test_gamma0_contract_tdd.py packages/graph-agent/tests/core/test_gamma2_child_graph_isolation.py packages/graph-agent/tests/core/test_gamma2_phase_outputs_flow.py packages/graph-agent/tests/core/test_gamma2_reference_reader_sandbox.py packages/graph-agent/tests/core/test_delta_skill_resolution_red.py packages/graph-agent/tests/core/test_skill_resolver_protocol.py packages/graph-agent/tests/core/test_compiler_line_locations.py -v`
- full `pytest packages/graph-agent/tests/ -rX` shows `0 xpassed`.

## §11 r14.10: grep guard + CI gate

**目标**: merge 前防止旧 schema 或错误前提回流。

**Grep guard**:

- No schema without v:
  - `rg -n 'schema_version:\\s*["'\\'']0\\.3\\.0["'\\'']|schema_version.*0\\.3\\.0|Literal\\["0\\.3\\.0"\\]|must be exactly "0\\.3\\.0"' packages/graph-agent/src packages/graph-agent/tests apps/studio/backend`
- Every active GRAPH fixture has body phase:
  - `rg -l 'schema_version:\\s*"v0\\.3\\.0"' packages/graph-agent/tests packages/graph-agent/src apps/studio/backend | xargs -r grep -L '<phase\\b'` must be empty or documented non-GRAPH false positives.
- No author-written phase mode:
  - `rg -n '^mode:\\s*(skill|agent|logic|subgraph)\\b' packages/graph-agent/tests packages/graph-agent/src apps/studio/backend skills`
- No physical IO active path:
  - `rg -n 'io_inputs_ref|io_outputs_ref|io/inputs\\.json|io/outputs\\.json|_validate_io_schema|_resolve_io_ref' packages/graph-agent/src packages/graph-agent/tests apps/studio/backend`
- No deleted AST:
  - `rg -n 'SkillNodeAST|mode: Literal\\["skill"\\]|node_kind="skill"|python_callable' packages/graph-agent/src packages/graph-agent/tests apps/studio/backend`
- No pure-YAML topology implementation:
  - `rg -n 'depends_on:\\s*\\[|src:\\s*phases/|_phase_refs_to_raw_attrs|_PHASE_RE|_phase_line' packages/graph-agent/src packages/graph-agent/tests apps/studio/backend`

**CI commands**:

- `pytest packages/graph-agent/tests/ -rX`
- `ruff check packages/graph-agent/src packages/graph-agent/tests`
- `mypy packages/graph-agent/src`

**依赖**: r14.9。

**验收**:

- CI green。
- `0 xpassed`。
- grep guard 无 active pollution; any historical/codemod exception must be listed in PR report with path and why not active.
