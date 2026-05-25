# round-14 PR 设计: Task B skill-compilation cutover

署名：a2
日期：2026-05-25

## 任务背景
本轮 (Task B 组) 核心目标是彻底落地 `skill-compilation` (编译期) 的 V0.3.0 静态契约。由于先前的错误理解 (删去 `<phase>` 改纯 YAML) 已被废弃，本轮重做必须 100% 对齐 `00-FORMAT-GROUND-TRUTH.md` 定义的规则。

认知模板 (Cognitive Template) 8 插槽装配 (C2 任务) **不包含**在本轮。本轮仅负责解析出 AST。

## 继承字段表 (字段级重构指引)

| 文件/AST | 字段 | 类型 | Round N-1 现状 | Round-14 改法 | 理由 |
|---|---|---|---|---|---|
| **GraphManifest** | `schema_version` | Literal | `"2.1"` 或 `"0.3.0"` | **[BREAKING]** 改为强制 `"v0.3.0"` (必须带 `v`) | 严格对齐 ground truth。 |
| **GraphManifest** | `io_inputs_ref` | string | `io/inputs.json` | **[BREAKING]** 删除 | 物理 IO 文件退役。 |
| **GraphManifest** | `io_outputs_ref` | string | `io/outputs.json` | **[BREAKING]** 删除 | 同上。 |
| **GraphManifest** | `io` | PhaseIOSchema | 可选 | **[BREAKING]** 强制必填 inline `io` | 取代物理文件。 |
| **NodeAST** | `mode` | Literal | `skill`, `logic`, `subgraph` | **[BREAKING]** 删 frontmatter 校验, 作者不可写 | 文件名推导 mode，如果 frontmatter 存在 `mode:` 则作为非法字段直接 fatal。内部 discriminator 注入 `agent`/`logic`/`subgraph`。 |
| **PhaseAST** | `SkillNodeAST` | class | AST 共存 | **[BREAKING]** 彻底删除类 | 仅保留 `AgentNodeAST`。 |
| **SubgraphNodeAST**| `io` | PhaseIOSchema | 可选 | **[BREAKING]** 强制必填 | 父子图 IO 对齐。 |
| **AgentNodeAST** | `<exit_contract>` | XML tag | 存在于 `SKILL.md` body | **[BREAKING]** 在 body 中禁止 | 移至 C2 模板硬编码。 |
| **AgentNodeAST** | `<example>` | XML tag | 存在于 `content` 字段 | **[NEW]** body `<example id>` | 拆分 document 与 inline 案例。 |
| **AgentNodeAST** | `python_callable`| string | 存在 | **[BREAKING]** 从 V2.1 彻底删除 | Agent/Skill path 删 python_callable; LOGIC 用 `actions` 注册/执行。 |

## B1 & B2: 文件名推导类型与 AST 切至 AgentNodeAST
**实施路线**:
- `src/graph_agent/core/manifest.py`: 删除 `SkillNodeAST`。`PhaseAST` 联合类型只留 `LogicNodeAST | SubgraphNodeAST | AgentNodeAST`，且 `AgentNodeAST.mode = Literal["agent"]`。
- `src/graph_agent/core/loader.py`:
    - 删除 `_validate_mode_matches_filename` 函数。
    - 读取 phase 文件时，根据文件名（`SKILL.md`, `LOGIC.md`, `SUBGRAPH.md`）显式向 `frontmatter` 字典中注入对应的 `mode: "agent"/"logic"/"subgraph"`。
    - **[NEW] 严禁多余元数据**: 校验 phase frontmatter 如果包含了 `mode`、`schema_version`、`graph_skill_id` 或 `phase_id`，立刻抛出 `[F-v3-*-unknown-field]` 类别的致命错误。
    - 如果一个 `phases/<id>` 目录下没有有效的节点文件，抛出 `[F-v3-graph-phase-node-missing]`。如果存在多个（如同时存在 SKILL.md 和 LOGIC.md），抛出 `[F-v3-graph-phase-mode-ambiguous]`。
- **Test 同步**: 删除所有 test fixture 中手写的 `mode: ...`。将失败断言同步为对应的 `unknown-field` 错误码。断言 3 类 phase 都成功装载了 `validator` (默认为 false)。

## B3: GRAPH.md 双轨制拓扑 (Frontmatter + Body)
**实施路线**:
- `src/graph_agent/core/loader.py`:
    - 在 `_build_graph_manifest` 中解析 YAML 必须拿到 `phases: list[str]`，无则抛 `[F-v3-graph-phases-missing]`。
    - **恢复 XML 解析**: 在解析 body 时，重新启用或补充 `<phase depends_on output>name</phase>` 正则提取逻辑。
    - 在 `_validate_graph_topology` 阶段：
        1. 校验 body 中所有提取出的 phase name 集合 == frontmatter `phases` 集合 == 物理目录 `phases/<name>` 集合。发现重复注册抛 `[F-v3-graph-phase-id-duplicate]`；名字与物理目录不一致抛 `[F-v3-graph-phase-name-mismatch]`；其他缺漏匹配抛 `[F-v3-graph-phase-id-invalid]`。
        2. 校验 body `depends_on` 属性：必须引用于 frontmatter 列表中；入口点必须是 `"input"`，否则抛 `[F-v3-graph-depends-unknown]`。
        3. 构建图连通性，校验有无环 `[F-v3-graph-phase-cycle]` 和不可达的孤岛 `[F-v3-graph-phase-island]`。
        4. 校验存在正确标注了 `output` 属性的终点 `[F-v3-graph-output-phase-invalid]`。
- **Test 同步**: 所有 fixture 的 `GRAPH.md` 必须写成双轨（既有 yaml 也有 body phase 标签）。

## B4: 根 IO 物理文件退役 (Inline IO)
**实施路线**:
- `src/graph_agent/core/manifest.py`: 从 `GraphManifest` 中删除 `io_inputs_ref` / `io_outputs_ref`。将 `io` 字段变更为不带 default 值的必填。
- `src/graph_agent/core/loader.py`: 如果在根目录发现 `io/inputs.json` 或 `io/outputs.json`，或在 yaml 里发现 `io_inputs_ref` / `io_outputs_ref`，抛 `[F-v3-graph-io-physical-file-deprecated]`。
- **Test 同步**: 移除 `tests/fixtures/` 中所有的 `io` 文件夹。修改所有 yaml frontmatter 加入 inline `io`。

## B5: Agent Body 5 类扁平标签解析
**实施路线**:
- `src/graph_agent/core/parser.py` (或 loader 中对应处):
    - 解析 `SKILL.md` body 时只提取 `<role>`, `<goal>`, `<step>`, `<protocol>`, `<example>`。
    - 若出现 `<steps>` 等复数壳，或直接出现 `<exit_contract>`，抛 `[F-v3-agent-body-tag-unknown]`。
    - 将提取的内容组装并送给 `AgentNodeAST` (不用负责 C2 cognitive 组装)。

## B6: `@type:NAME` 7 类 Mention 可达性校验
**实施路线**:
- `src/graph_agent/core/loader.py`: 在解析完 AST 后，针对 Agent body 文本执行统一正则 `@(subagent|tool|subgraph|protocol|step|reference|example):([a-zA-Z0-9_-]+)`。
- 按静态域查找：例如 `@example:E1` 必须在 body 的 `<example id="E1">` 或 frontmatter `examples[id="E1"]` 中。找不到则抛 `[F-v3-mention-target-not-found]`。

## B7: SUBGRAPH target_skill 解析 + IO 对齐
**实施路线**:
- `src/graph_agent/core/loader.py`: 编译 `SUBGRAPH.md` 时，必须调用 `skill_resolver.resolve_skill(ast.target_skill)` 编译出 child root 的 `GraphManifest`。
- 双向对比：校验当前 parent phase AST 的 `io.inputs` / `io.outputs` properties 键集与被解析出子图 `GraphManifest.io.inputs` / `outputs` 的键集严格 1:1 等价。不一致抛 `[F-v3-subgraph-io-mismatch]`。

## B8: 测试同步真迁移 (不 xfail 掩盖)
**实施路线**:
- 撤销 `tests/conftest.py` 中对 46 个 xpassed 及其它能跑通的 V0.3 测试的 blanket xfail。
- 把真实的 `GRAPH.md` fixture 的 `schema_version` 全改为 `"v0.3.0"`。
- **不迁移真实 skill**：`skills/text-segmentation` 等非测试 fixture 的 skill 保持 xfail 挂起，作为未来独立 task 处理。本轮仅确保编译器和引擎核心测试全绿。