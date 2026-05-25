# round-14 PR 需求: Task B skill-compilation cutover

署名：a2
日期：2026-05-25

## 1. 核心目标
本轮的核心目标是完成 `skill-compilation` 模块的硬切换，让引擎编译器彻底对齐 `00-FORMAT-GROUND-TRUTH.md`，执行 V0.3.0 的静态编译契约。

**隔离声明**：引擎核心和测试用例必须 100% 遵守新规范。但 `skills/` 下的真实业务 skill (如 text-segmentation) 仅作 corpus，它们在本轮由于规范冲突无法编译，要求在测试套件中使用 `xfail` 隔离挂起。

## 2. 功能需求清单
*   **AST 重组 (B1)**: `SkillNodeAST` 退役，所有基于 `SKILL.md` 的解析映射为 `AgentNodeAST`。
*   **推导式类型 (B2)**: 废除 frontmatter 手写 `mode:` 要求，由物理文件名 `SKILL.md` / `LOGIC.md` / `SUBGRAPH.md` 唯一决定相类型，并执行严格的三选一与防歧义校验。如果在 phase 的 frontmatter 中出现任何 `mode:` 字段，直接作为未知字段报错。
*   **双轨拓扑 (B3)**: `GRAPH.md` 必须且只能从 frontmatter `phases` 获取名字注册，从 body `<phase>` 标签提取 `depends_on` 拓扑，并校验二者与物理目录的三方一致性。
*   **强联 IO (B4)**: 退役任何指向 `io/inputs.json` 等物理文件及 `io/outputs.json` 的引用，`GraphManifest.io` 改为内联的必填项。
*   **扁平 Body (B5)**: Agent 节点的 body 只提取 5 类扁平标签 (`<role>`, `<goal>`, `<step>`, `<protocol>`, `<example>`)。禁止出现嵌套壳或 `<exit_contract>`。
*   **Mention 校验 (B6)**: 对 body 中出现的 `@type:NAME` 执行精确的局部 / 全局 registry 可达性检查。
*   **子图安全 (B7)**: Subgraph 必须对 `target_skill` 执行 DI 解析，并在编译期严格校验父图 io 与子图根 io (`GraphManifest.io`) 的 inputs 和 outputs 的 1:1 properties 对齐。

## 3. 验收标准
1.  `manifest.py` 与 `loader.py` 中不存在任何对 `SkillNodeAST`、`<python_callable>` 的调用或属性残留。
2.  测试断言 `_validate_mode_matches_filename` 函数已被删除。
3.  编译器遇到含有 `mode: skill` (或任何 `mode:` 字段) 的遗留文件，直接抛出 `[F-v3-graph-schema-unknown-field]`（或对应 domain 的未知字段错误）；遇到带有 `io_inputs_ref` / `io_outputs_ref` 或存在物理 `io/*.json` 文件的图，强制阻断并抛出弃用错误。
4.  解析 `GRAPH.md` 遇到缺失 YAML phases、缺失 body `<phase>` 标签、或二者 name 与物理目录不一致的情况，准确抛出对应的错误码（特别是名字和物理目录不一致时抛出 `[F-v3-graph-phase-name-mismatch]`）。DAG 存在环、孤岛、缺失 output 标记等均能准确抛出专用错误码。
5.  测试断言 phase 文件中如果出现 `schema_version`、`graph_skill_id` 或 `phase_id` 必须触发非法报错；同时断言 Agent、Logic、Subgraph 三类节点全部成功读取了 `validator: boolean`。
6.  `conftest.py` 中上次被无差别隔离的 46 个 XPASS 相关用例（包括 `test_gamma2_child_graph_isolation.py` 等 V0.3 新功能）恢复 active green。其余编译期测试基于 `schema_version: "v0.3.0"` 运行通过。

## 4. 激活的关键错误码 [F-v3-*] (关键子集，完整见 tasks)
本轮实施必须精确命中以下错误码，严禁“一码多用”：

*   `[F-v3-graph-schema-version-mismatch]`: 当 `schema_version` 不是 `"v0.3.0"`（带 v）时。
*   `[F-v3-graph-io-physical-file-deprecated]`: 当发现遗留物理 IO 文件或引用时。
*   `[F-v3-graph-phase-mode-ambiguous]`: 当 phase 目录下有多个有效类型的节点文件时。
*   `[F-v3-graph-phase-node-missing]`: 当 phase 目录下没有任何有效的 LOGIC/SUBGRAPH/SKILL 文件时。
*   `[F-v3-graph-phases-missing]`: 当 `GRAPH.md` 缺少 frontmatter `phases` 列表时。
*   `[F-v3-graph-phase-name-mismatch]`: 当 body `<phase>` name 或 frontmatter registered name 与物理目录名不一致时。
*   `[F-v3-graph-phase-id-invalid]`: 当 body `<phase>` 标签缺失，或拓扑解析失败的基础 ID 错误时。
*   `[F-v3-graph-phase-id-duplicate]`: 当注册了重复的 phase name 时。
*   `[F-v3-graph-depends-unknown]`: 当拓扑依赖 (`depends_on`) 引用了未注册的 phase name，或首节点未使用 `input` 时。
*   `[F-v3-graph-phase-cycle]`: 当 DAG 中存在环时。
*   `[F-v3-graph-phase-island]`: 当存在从 input 不可达的孤岛 phase 时。
*   `[F-v3-graph-output-phase-invalid]`: 当没有正确标注 output 结束节点时。
*   `[F-v3-agent-body-tag-unknown]`: 当在 `SKILL.md` body 中使用了非白名单标签（如 `<steps>`, `<exit_contract>` 等）时。
*   `[F-v3-subgraph-io-mismatch]`: 当父子图 IO Schema 的 inputs 或 outputs properties 不双向严格等同时。
*   `[F-v3-mention-target-not-found]`: 当 `@type:NAME` 找不到对应的 registered 目标时。