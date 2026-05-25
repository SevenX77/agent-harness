# round-14 PR 需求: Task B skill-compilation cutover

署名：a2
日期：2026-05-25

## 1. 核心目标
本轮 (Task B) 的核心目标是完成 `skill-compilation` 模块的硬切换 (hard cutover)，引擎编译器彻底退役 V2.1 的旧规范，全面拥抱 V0.3.0 的声明式、强类型编译契约。

**注意**：真实 fixture skill（如 `skills/text-segmentation` 等）作为测试 corpus，其 V0.3.0 迁移是后续独立 task，本轮保持 isolate (使用 xfail 挂起)。本轮硬切换仅针对编译器核心及相关单元/集成测试 fixture。

具体来说，就是要强制推行 AST 的节点类型更新 (`mode: agent`)、根文件 `GRAPH.md` 的 YAML 化 (`phases` 列表和 inline `io`)、文件目录与节点模式的强绑定，以及子图调用的协议级对接和严格输入输出对齐。

## 2. 覆盖的子任务
- **B1**: `SkillNodeAST` 退役，全面切至 `AgentNodeAST`，统一 `mode: agent`。
- **B2**: `mode` 三值化 (`agent`, `logic`, `subgraph`)，每个 phase 目录下强制 3 选 1，不允许模棱两可。
- **B3**: 废弃 `GRAPH.md` 中的 `<phase/>` XML 标签，改为从 YAML frontmatter `phases:` 列表中读取图拓扑。
- **B4**: 废弃物理的 `io/inputs.json` 与 `io/outputs.json` 文件及其引用，强制使用 inline `io.inputs` 与 `io.outputs`。
- **B7**: `SUBGRAPH.md` 的 `target_skill` 静态解析与子图根 IO 的 1:1 严格对齐校验。
- **B8**: 测试框架与 Fixtures 同步迁移至 `schema_version: "0.3.0"`。

## 3. 验收标准
- `manifest.py` 中不存在 `SkillNodeAST`。
- 不再支持 `mode: skill`。
- `GRAPH.md` 包含任何 `<phase/>` 均不再作为拓扑依据。
- 在 `loader.py` 中发现任何指向物理 IO 文件的引用或存在 `io/*.json` 文件，必须抛出 `[F-v3-graph-io-physical-file-deprecated]` 错误，阻断编译。
- 编译 `SUBGRAPH.md` 时，通过 `SkillResolverProtocol` 解析子图，若父子 IO 字段不对齐，必须抛出 `[F-v3-subgraph-io-mismatch]`。
- 所有现存的引擎编译和装配单元测试必须 100% 绿灯，不留被 Skip 的过时测试（真实 skill 的 e2e 隔离测试除外）。

## 4. 关键错误码清单
- `[F-v3-agent-mode-invalid]`: 当 `SKILL.md` 的 mode 不为 `agent` 时。
- `[F-v3-graph-phase-mode-ambiguous]`: 当 phase 目录下有多个有效 mode 的文件时。
- `[F-v3-graph-phase-node-missing]`: 当 phase 目录下没有任何有效 node 文件时。
- `[F-v3-graph-phases-missing]`: 当 `GRAPH.md` 缺少 `phases` frontmatter 列表时。
- `[F-v3-graph-phase-id-invalid]`: 当拓扑依赖 (`depends_on`) 引用的 phase id 未在图节点声明中时。
- `[F-v3-graph-io-physical-file-deprecated]`: 发现遗留物理 IO 文件或引用时。
- `[F-v3-subgraph-io-mismatch]`: 父子图 IO Schema 不匹配时。