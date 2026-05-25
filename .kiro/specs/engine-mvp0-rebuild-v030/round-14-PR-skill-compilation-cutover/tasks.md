---
spec: engine-mvp0-rebuild-v030/round-14-PR-skill-compilation-cutover
phase: PR skill-compilation cutover tasks
owner: a1 audit+tasks / a2 design+requirements+research / a3 final gate
工程量: 48h = tests 6h + B1 7h + B2 5h + B3 7h + B4 7h + B7 8h + B8 6h + gate 2h
---

# PR round-14: Skill Compilation Cutover Tasks

## §0 Scope 和继承边界

本 PR 只做 Task B skill-compilation hard cutover: B1-B4, B7, B8。不改 A 的 `SkillResolverProtocol` 语义, 不改 D 的三区 state / `PhaseWrapper` 语义, 不重开 B5/B6。

继承事实:

- `SkillResolverProtocol` 已存在, child skill 入口必须显式注入 resolver。
- `AgentNodeAST` 已存在, 但 `SkillNodeAST` / `mode: skill` 仍是 active path。
- `GraphManifest` 仍允许 `schema_version: "2.1"` 和 `"0.3.0"`。
- `GRAPH.md` 仍存在 XML `<phase/>` 与 YAML `phases:` 双轨。
- root IO 仍存在 physical `io/inputs.json` / `io/outputs.json` 与 inline `io` 双轨。
- `SubgraphNodeAST.target_skill` 已必填, 但父子 IO 1:1 静态校验未完成。

Hard cutover 点:

- 不保留 V2.1 loader/cache/serializer fallback。
- 不保留 `SkillNodeAST` / `mode: skill` active path。
- 不保留 `GRAPH.md` body XML `<phase/>` 拓扑。
- 不保留 physical root IO 文件或 `io_inputs_ref` / `io_outputs_ref` 引用。
- 同 PR 同步 engine tests、fixtures、serializer/cache、Studio backend schema/template 受影响面。

## §1 依赖图

```text
r14.1 Tests-first red suite
  ├─> r14.2 B1! AgentNodeAST-only AST
  │     └─> r14.3 B2! mode 三值化 + phase file 3 选 1
  │           └─> r14.4 B3! GRAPH.md YAML phases cutover
  │                 └─> r14.5 B4! inline root IO cutover
  │                       └─> r14.6 B7! SUBGRAPH IO 1:1 校验
  └─> r14.7 B8! fixtures / serializer / cache / Studio sync
        └─> r14.8 CI gate + grep guard
```

必须串行:

- `r14.1` 必须先写红灯, 覆盖 old schema 仍被接受、XML/physical IO fallback、SUBGRAPH IO mismatch 未拦截。
- `r14.2-r14.6` 按 AST -> phase discovery -> graph topology -> root IO -> child IO 顺序推进。
- `r14.7` 必须跟随所有 schema cutover, 统一迁移 tests/fixtures/Studio 触点。

可并行:

- `r14.7` 中 fixture 迁移、serializer 测试迁移、Studio backend 测试迁移可在 B3/B4 接口稳定后并行。

## §2 r14.1: Tests-first red suite (6h)

**WHY**: 本 PR 是 breaking schema cutover。先写红灯证明旧分支仍 active, 避免实现只改模型不切断 loader/runtime 入口。

**Files**:

- 新增 `packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py`
- 修改 `packages/graph-agent/tests/core/test_v21_loader.py`
- 修改 `packages/graph-agent/tests/core/test_v21_graph_serializer.py`
- 修改 `packages/graph-agent/tests/core/test_compiler_schema_version_tolerance.py`
- 修改 `apps/studio/backend/tests/test_models.py`
- 修改 `apps/studio/backend/tests/services/test_skills_folder_import.py`

**WHAT**:

- 红灯: `schema_version: "2.1"` compile fatal, 不再 coerce / tolerate。
- 红灯: phase `SKILL.md mode: skill` fatal `[F-v3-agent-mode-invalid]`。
- 红灯: Pydantic `TypeAdapter(PhaseAST)` / AST parser 直接反序列化 `{"mode": "skill", ...}` payload 时失败, 不只依赖 loader 逻辑校验。
- 红灯: 同一 phase 目录同时存在 `SKILL.md` / `LOGIC.md` / `SUBGRAPH.md` 多个节点文件 fatal `[F-v3-graph-phase-mode-ambiguous]`。
- 红灯: `GRAPH.md` body 中 `<phase/>` 不再作为 topology 来源; 缺 YAML `phases:` fatal `[F-v3-graph-phases-missing]`。
- 红灯: `io/inputs.json`, `io/outputs.json`, `io_inputs_ref`, `io_outputs_ref` 任一存在 fatal `[F-v3-graph-io-physical-file-deprecated]`。
- 红灯: SUBGRAPH 父 `io` 与 child root `GRAPH.md io` inputs/outputs properties 不一致 fatal `[F-v3-subgraph-io-mismatch]`。
- 红灯: `serialize_graph()` fresh/original round-trip 产出 YAML `phases:` + inline `io`, 不再产出 XML IO/phase tag。

**Cutover discipline**:

- 本 task 只写/改 tests, 不改 src。
- 不加 `xfail` / `skip`。

**验收**:

- 新测试在当前 main 下失败, 且失败点分别指向 legacy schema、XML、physical IO、SUBGRAPH IO mismatch。

**依赖**: none。

## §3 r14.2: B1! AgentNodeAST-only AST (7h)

**WHY**: `SkillNodeAST` 是后续 legacy runtime/exit_contract/cache/schema 双轨的根。必须先收敛 PhaseAST discriminator。

**Files**:

- `packages/graph-agent/src/graph_agent/core/manifest.py`
- `packages/graph-agent/src/graph_agent/core/loader.py`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/src/graph_agent/core/cache.py`
- `apps/studio/backend/app/services/skills.py`
- `packages/graph-agent/tests/golden/schema/`

**WHAT**:

- 删除 `SkillNodeAST` class 和 public export。
- `PhaseAST = LogicNodeAST | SubgraphNodeAST | AgentNodeAST`。
- `SKILL.md` 只允许 `mode: agent`; `mode: skill` 抛 `[F-v3-agent-mode-invalid]`。
- 删除 graph assembler 中 `SkillNodeAST` 分支和 `node_kind="skill"`。
- 更新 Studio backend schema registry, 不再导出 `"skill": SkillNodeAST.model_json_schema()`。
- 更新 golden schema: 删除 `skill_node_ast.schema.json`, 更新 `phase_ast_union.schema.json`。

**迁移路径**:

- 所有 active fixture `mode: skill` -> `mode: agent`。
- 旧 `system_prompt` / `exit_contract` style phase fixture 改为 B5 已 ship 的 `<role>` / `<goal>` / `<step>` / `<protocol>` Agent body。
- cache snapshot 不能 rehydrate old `SkillNodeAST`; namespace 在 B8 bump。

**验收**:

- `rg -n "SkillNodeAST|mode: Literal\\[\\\"skill\\\"\\]|node_kind=\\\"skill\\\"" packages/graph-agent/src apps/studio/backend/app` 无 active 命中。
- `pytest packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py -k agent_mode -v` 通过。

**依赖**: `r14.1`。

## §4 r14.3: B2! mode 三值化 + phase file 3 选 1 (5h)

**WHY**: v0.3 phase node kind 必须由物理文件和 frontmatter mode 双向绑定, 不能靠旧 loader 宽松推断。

**Files**:

- `packages/graph-agent/src/graph_agent/core/loader.py`
- `packages/graph-agent/src/graph_agent/core/manifest.py`
- `packages/graph-agent/tests/core/test_v21_loader.py`
- `packages/graph-agent/tests/core/test_loader_subgraph_is_file.py`

**WHAT**:

- mode enum 严格为 `agent` / `logic` / `subgraph`。
- `SKILL.md -> mode: agent`, `LOGIC.md -> mode: logic`, `SUBGRAPH.md -> mode: subgraph`。
- 重写 `_discover_phase_files`: 每个 `phases/<id>/` 恰好一个 node file。
- 多个 node file fatal `[F-v3-graph-phase-mode-ambiguous]`。
- 缺 node file fatal `[F-v3-graph-phase-node-missing]`。

**迁移路径**:

- active tests 中所有 helper 改成生成唯一 node file。
- 删除 `SKILL.md` 可接受 `mode: skill` 的分支。

**验收**:

- `rg -n "yaml_mode in \\{\\\"agent\\\", \\\"skill\\\"\\}|elif mode == \\\"skill\\\"|mode == \\\"skill\\\"" packages/graph-agent/src/graph_agent/core/loader.py` 无 active 命中。
- duplicate / missing node file tests 通过。

**依赖**: `r14.2`。

## §5 r14.4: B3! GRAPH.md YAML phases cutover (7h)

**WHY**: XML `<phase/>` 与 YAML `phases:` 双轨让 topology、line span、serializer 全部维持旧语义。Topology truth source 必须只剩 frontmatter。

**Files**:

- `packages/graph-agent/src/graph_agent/core/loader.py`
- `packages/graph-agent/src/graph_agent/core/manifest.py`
- `packages/graph-agent/src/graph_agent/core/graph_serializer.py`
- `packages/graph-agent/src/graph_agent/core/cache.py`
- `packages/graph-agent/tests/core/test_t11_phase_token_info.py`
- `packages/graph-agent/tests/core/test_v21_graph_serializer.py`
- `packages/graph-agent/tests/core/test_v21_loader.py`

**WHAT**:

- 删除 `_extract_phase_attrs`, `_extract_phase_token_info`, `_phase_refs_to_raw_attrs` active path。
- `GraphManifest.phases` 只来自 YAML frontmatter `phases:`。
- 重构 `_validate_graph_topology`: 入参从 `list[_RawPhaseAttrs]` 改为消费 `manifest.phases` (`list[GraphPhaseRef]`), 不再依赖 XML raw attrs / line span carrier。
- 缺 `phases:` fatal `[F-v3-graph-phases-missing]`。
- `depends_on` 引用未知 phase id fatal `[F-v3-graph-phase-id-invalid]`。
- 空 list / duplicate / cycle / missing src / invalid src 由 YAML phase refs 触发对应 graph-domain fatal。
- `graph_serializer.py` 从 XML token rewrite 改为 YAML frontmatter rewrite / fresh render。
- phase token line/span 测试改为 YAML key/value 定位或删除 XML token contract。

**迁移路径**:

- 所有 `GRAPH.md` body `<phase ... />` 转为:
  - `phases:`
  - `- id: <id>`
  - `src: phases/<id>`
  - `depends_on: [...]`
- serializer tests 统一断言 YAML, 不再断言 XML token preservation。

**验收**:

- `rg -n "<phase\\b|_extract_phase_attrs|_phase_refs_to_raw_attrs|_PHASE_RE|_phase_line" packages/graph-agent/src/graph_agent/core packages/graph-agent/tests/core` 无 active legacy 命中。
- YAML topology success / cycle / duplicate / island tests 通过。

**依赖**: `r14.3`。

## §6 r14.5: B4! inline root IO cutover (7h)

**WHY**: StateMapper 和 SUBGRAPH IO 校验依赖 root `GRAPH.md io` 是唯一 schema 来源。physical IO fallback 会绕过 v0.3 编译契约。

**Files**:

- `packages/graph-agent/src/graph_agent/core/manifest.py`
- `packages/graph-agent/src/graph_agent/core/loader.py`
- `packages/graph-agent/src/graph_agent/core/graph_serializer.py`
- `packages/graph-agent/src/graph_agent/core/cache.py`
- `apps/studio/backend/app/services/skills.py`
- `apps/studio/backend/app/services/validator.py`
- `apps/studio/backend/tests/`

**WHAT**:

- 删除 `GraphManifest.io_inputs_ref` / `io_outputs_ref`。
- `GraphManifest.io: PhaseIOSchema` 改为必填。
- `loader.py` 发现 `io/inputs.json`, `io/outputs.json`, `io_inputs_ref`, `io_outputs_ref` 直接 fatal `[F-v3-graph-io-physical-file-deprecated]`。
- 删除 `_validate_io_schema` active path, 只保留 inline schema validation。
- `graph_serializer.py` 删除 `<input>/<output>` XML tokenizing 正则 `_IO_RE` 和 `"io"` token kind, fresh/original render inline `io` dict。
- `cache.py` 不扫描 `io/*.json`; cache key 只依赖 `GRAPH.md` + phase node/action/tool files。
- Studio backend blank graph/template/import/export 同步 inline `io`。

**迁移路径**:

- fixture `io/*.json` 内容合并到 `GRAPH.md frontmatter io.inputs/io.outputs`。
- 删除 active fixture 的 `io/` 目录。
- Studio tests 由 physical bundle 改为 inline `GRAPH.md` bundle。

**验收**:

- `rg -n "io_inputs_ref|io_outputs_ref|io/inputs\\.json|io/outputs\\.json|_validate_io_schema" packages/graph-agent/src apps/studio/backend/app packages/graph-agent/tests apps/studio/backend/tests` 无 active legacy 命中。
- deprecated physical IO fatal tests 通过。

**依赖**: `r14.4`。

## §7 r14.6: B7! SUBGRAPH target_skill IO 1:1 校验 (8h)

**WHY**: PR delta 只完成 resolver smoke。B7 要把 SUBGRAPH 当函数调用, 在编译/装配前确认父 phase IO 与 child root IO 完全一致。

**Files**:

- `packages/graph-agent/src/graph_agent/core/loader.py`
- `packages/graph-agent/src/graph_agent/core/manifest.py`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/tests/core/test_v030_subgraph_target_skill.py`
- `packages/graph-agent/tests/fixtures/v030_skill_registry/`

**WHAT**:

- `SubgraphNodeAST.io` 改为必填。
- 编译/装配 SUBGRAPH 时通过 `resolve_skill_root(skill_resolver, target_skill)` 加载 child root。
- 校验 parent SUBGRAPH `io.inputs` 与 child `GraphManifest.io.inputs` 1:1 等价。
- 校验 parent SUBGRAPH `io.outputs` 与 child `GraphManifest.io.outputs` 1:1 等价。
- mismatch fatal `[F-v3-subgraph-io-mismatch]`, payload 包含 parent phase id、target_skill、side(inputs/outputs)。
- 防止递归 target_skill 循环导致无限 compile; 使用现有 cache/visited guard 或新增 compile stack guard。

**迁移路径**:

- 所有 SUBGRAPH fixture 必须声明 `io`。
- child fixture root 必须是 v0.3 inline IO。

**验收**:

- unregistered / missing resolver / inputs mismatch / outputs mismatch / success tests 通过。
- `pytest packages/graph-agent/tests/core/test_v030_subgraph_target_skill.py -v` 通过。

**依赖**: `r14.5`。

## §8 r14.7: B8! fixtures / serializer / cache / Studio sync (6h)

**WHY**: Cutover PR 不能只改 src。所有 active unit/integration/e2e fixture 和 app-facing schema surface 必须同 PR 对齐。

**Files**:

- `packages/graph-agent/tests/core/`
- `packages/graph-agent/tests/integration/`
- `packages/graph-agent/tests/fixtures/`
- `packages/graph-agent/tests/golden/`
- `packages/graph-agent/src/graph_agent/core/cache.py`
- `packages/graph-agent/src/graph_agent/codemod/v21_migrator.py`
- `packages/graph-agent/src/graph_agent/skills/builtin/`
- `apps/studio/backend/app/services/skills.py`
- `apps/studio/backend/app/templates/`
- `apps/studio/backend/tests/`
- `apps/studio/frontend/tests/e2e/`

**WHAT**:

- active graph-agent tests 全部迁移到 `schema_version: "0.3.0"`。
- 旧 v21 parser/cache/serializer 测试改名为 v030 或删除过时断言。
- codemod/golden 若保留为历史迁移测试, 必须隔离在非 active compile path; 若仍 active, 输出改 v0.3。
- built-in/example skill 若仍被 tests/import endpoint 扫描, 迁移或隔离。
- 顶层 `skills/` 真实 skill corpus 本轮不迁移; 必须从 round-14 active compile/import/test 路径隔离, 后续独立 task 处理, 不能作为隐式兼容 fallback 的理由。
- Studio backend API/model/import tests 改为 v0.3 GraphManifest / inline IO / YAML phases。
- Studio frontend e2e fixture 中 `schema_version: "2.0"` 仅允许非 graph skill legacy UI 测试; graph import/run fixture 必须 v0.3。
- bump cache namespace from `graph-agent-v21` to `graph-agent-v030`.

**验收**:

- `rg -n "schema_version: [\"']2\\.[01][\"']|schema_version\\\": \\\"2\\.[01]\\\"|mode: skill|<phase\\b|<input src|<output src|SkillNodeAST|io_inputs_ref|io_outputs_ref" packages/graph-agent/src packages/graph-agent/tests apps/studio/backend/app apps/studio/backend/tests apps/studio/frontend/tests skills` 仅剩明确注释/历史 codemod golden/已隔离真实 skill corpus, 且不在 active compile/import path。
- cache dir string 不再含 `graph-agent-v21`。

**依赖**: `r14.2-r14.6`。

## §9 r14.8: CI gate + grep guard (2h)

**WHY**: 本 PR 清理范围大, merge 前必须用 grep guard 防止 legacy 分支回流。

**Files**:

- 无业务文件; 可更新 CI 脚本/PR checklist 如仓库已有约定。

**WHAT / gate**:

- `pytest packages/graph-agent/tests/ -v`
- `pytest apps/studio/backend/tests/ -v`
- `ruff check packages/graph-agent/src packages/graph-agent/tests apps/studio/backend/app apps/studio/backend/tests`
- `mypy packages/graph-agent/src`
- grep guard:
  - `rg -n "SkillNodeAST|mode: Literal\\[\\\"skill\\\"\\]|mode: skill" packages/graph-agent/src packages/graph-agent/tests apps/studio/backend skills`
  - `rg -n "<phase\\b|<input src|<output src|_extract_phase_attrs|_PHASE_RE|_IO_RE" packages/graph-agent/src packages/graph-agent/tests apps/studio/backend skills`
  - `rg -n "io_inputs_ref|io_outputs_ref|io/inputs\\.json|io/outputs\\.json|_validate_io_schema" packages/graph-agent/src packages/graph-agent/tests apps/studio/backend skills`
  - `rg -n "schema_version.*2\\.[01]|graph-agent-v21" packages/graph-agent/src packages/graph-agent/tests apps/studio/backend skills`

**验收**:

- CI gate 全绿。
- grep guard 无 active legacy 命中; 如保留历史 codemod golden, PR report 必须逐条说明为何不在 active compile/import path。

**依赖**: `r14.7`。
