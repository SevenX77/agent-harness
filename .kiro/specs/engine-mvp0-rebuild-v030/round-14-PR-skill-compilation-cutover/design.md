# round-14 PR 设计: Task B skill-compilation cutover (a2 主笔 design)

署名：a2
日期：2026-05-25

## 任务背景
V0.3.0 引擎升级中，A (skill-resolution) 和 D (state-io) 已完成。本次设计专注于 Task B (skill-compilation) 剩余的硬切换任务 (B1-B4, B7, B8)。B 任务是后续 execution-runtime 彻底告别旧 AST 和旧 IO 的前置依赖。

本设计严格遵循 SOP-06，不做任何兼容回退 (hard cutover)，直接将 V2.1 AST 和 `GRAPH.md` 旧规范全面切除，替换为 V0.3.0 标准。

**关于真实 Skill 迁移的特别说明**:
`skills/` 目录下的真实 skill（如 text-segmentation, event-extraction）目前是用于测试 Studio 和 Engine 功能的 corpus，处于半迁移态且多版本并存。由于原型期旨在发现问题并跑通 Engine 机制，**本轮 round-14 的硬切换将使这些 skill 无法编译**。本轮硬切**不负责**迁移真实 skill，而是让这些 skill 保持 isolated (xfail) 状态，将它们的 V0.3.0 迁移作为后续独立任务处理。

## §0.5 继承字段表 (Grepped 现状 vs Round-14 改动)

以下是从现存的 `manifest.py`, `loader.py` 及 schema 规范中整理的受影响或继承的字段，并标注了本次 round-14 是否改动。

| AST / 范围 | 字段 | 类型 | 当前状态 | Round-14 改动 | 理由 |
|---|---|---|---|---|---|
| **GraphManifest** | `schema_version` | Literal | `"2.1"` 或 `"0.3.0"` | **[BREAKING]** 改为强制 `"0.3.0"` | V2.1 彻底退役。 |
| **GraphManifest** | `io_inputs_ref` | string | `io/inputs.json` | **[BREAKING]** 删除 | B4 要求物理 IO 文件退役。 |
| **GraphManifest** | `io_outputs_ref` | string | `io/outputs.json` | **[BREAKING]** 删除 | 同上。 |
| **GraphManifest** | `io` | PhaseIOSchema | 可选 | **[BREAKING]** 改为必填 | B4 要求 inline `io.inputs` / `io.outputs`。 |
| **GraphManifest** | `phases` | list | GraphPhaseRef | **[BREAKING]** 从 XML 标签提取改为纯 YAML 列表 | B3 要求 `<phase />` 退役。 |
| **NodeAST** | `mode` | Literal | `skill`, `logic`, `subgraph` | **[BREAKING]** `skill` -> `agent`，且严格三选一 | B1 & B2 要求。 |
| **PhaseAST** | `SkillNodeAST` | class | 存在 | **[BREAKING]** 删除类，由 `AgentNodeAST` 替代 | B1 核心目标。 |
| **SubgraphNodeAST** | `target_skill`| string | registry id | **[BREAKING]** 添加强 IO 对齐逻辑 | B7 核心目标。 |
| **SubgraphNodeAST** | `io` | PhaseIOSchema | 可选 | **[BREAKING]** 改为必填 | B7 要求父子图 IO 对齐。 |

---

## 具体设计与迁移路径

### B1. SkillNodeAST → AgentNodeAST
- **改动点 [BREAKING]**:
  - `manifest.py` 中删除 `SkillNodeAST`。`PhaseAST` 联合类型只保留 `LogicNodeAST | SubgraphNodeAST | AgentNodeAST`。
  - 所有 `SKILL.md` 的 `mode` 必须声明为 `agent`。
- **跨 Round 影响**:
  - D (state-io) 中的 `PhaseWrapper` 已经在 `graph_assembler.py` 覆盖了 `"agent"` 和 `"skill"` 两种 `node_kind`。本次改动后，assembler 里的 `"skill"` 路由将被清理，只认 `"agent"`。
- **迁移路径**:
  - **AST/Loader**: `loader.py` 解析 `SKILL.md` 时直接映射到 `AgentNodeAST`，失败则抛 Fatal `[F-v3-agent-mode-invalid]`。
  - **Fixtures**: 将 `tests/fixtures/` 下所有 `SKILL.md` 里的 `mode: skill` 批量替换为 `mode: agent`。

### B2. mode 三值化 + phase 文件 3 选 1 校验
- **改动点 [NEW]**:
  - 强制执行物理目录与 `mode` 的双向绑定：`SKILL.md` (agent)、`LOGIC.md` (logic)、`SUBGRAPH.md` (subgraph)。
  - `loader.py` 中 `_discover_phase_files` 若在一个目录下发现多个相文件（如既有 `LOGIC.md` 又有 `SKILL.md`）直接抛 `[F-v3-graph-phase-mode-ambiguous]`。
  - 若 phase 目录下缺少有效的节点文件，抛出具体的 `[F-v3-graph-phase-node-missing]` 错误（从原先混用的 `[F-v3-graph-phase-id-invalid]` 拆分出来，以便精确定位缺失文件的场景）。

### B3. GRAPH.md `<phase/>` XML → `phases:` YAML list
- **改动点 [BREAKING]**:
  - `loader.py` 的 `_build_graph_manifest` 不再从 Markdown body 提取 `<phase />` 标签。
  - `GraphManifest.phases` 直接依赖 YAML frontmatter 的 `phases:` 列表映射。若 frontmatter 无 `phases:` 则抛 `[F-v3-graph-phases-missing]`。
  - 拓扑解析时若 `depends_on` 或阶段依赖中出现了未声明/非法的 phase id，则抛出专门的 `[F-v3-graph-phase-id-invalid]`。
  - **漏读迁移点补全①**: `loader.py:166` 处的 `_phase_refs_to_raw_attrs` 及其周边回退逻辑将被完全删除，不再把 YAML 逆向兼容成 XML AST 属性。
- **迁移路径**:
  - **Loader**: 移除 `_first_src`、`<phase>` regex 提取逻辑。
  - **Fixtures**: 将所有 `GRAPH.md` 里的 `<phase id="xxx" src="phases/xxx" depends_on="yyy" />` 转移至顶层 frontmatter 的 `phases:` 列表中。

### B4. 根 IO 物理文件退役 → inline `io.inputs` / `io.outputs`
- **改动点 [BREAKING]**:
  - 彻底删除 `io_inputs_ref` / `io_outputs_ref`。
  - `GraphManifest.io` 改为强制必填项。
  - `loader.py` 若在 skill 根目录发现 `io/inputs.json` 或 frontmatter 包含 `io_inputs_ref`，直接抛出 `[F-v3-graph-io-physical-file-deprecated]`。
  - **漏读迁移点补全②**: `graph_serializer.py:92-93` 用于序列化 `GRAPH.md` 时使用了 `io_inputs_ref` 和 `io_outputs_ref`，这块 `_render_fresh_graph` 必须重写为序列化 inline `io` dict。
- **迁移路径**:
  - **Loader**: 删除 `_validate_io_schema`（旧物理文件读取逻辑），只保留 `_validate_inline_io_schema`。
  - **Cache**: 缓存收集策略中剔除 `io/*.json` 的扫描。
  - **Fixtures**: 删除所有 fixture 目录下的 `io/` 文件夹。将原 JSON schema 的内容合并到 `GRAPH.md` 的 YAML frontmatter `io:` 字段下。

### B7. SUBGRAPH `target_skill` 解析 + 子图 IO 1:1 对齐校验
- **改动点 [NEW]**:
  - `SubgraphNodeAST` 必须包含 `io` (inputs/outputs)。
  - `loader.py` 编译 `SUBGRAPH.md` 时，通过 `SkillResolverProtocol.resolve_skill(target_skill)` 定位子图并编译子图的 `GRAPH.md`。
  - 静态校验：父 `SUBGRAPH.md io.inputs.properties` 必须完全等同于子 `GRAPH.md io.inputs.properties`，不同则抛 `[F-v3-subgraph-io-mismatch]`；outputs 同理。
- **跨 Round 对账确认**:
  - PR δ 已经加入了 `SkillResolverProtocol`，B7 这里就是真正的消费端。

### B8. skill-compilation 测试同步
- **改动点 [BREAKING]**:
  - 所有 integration/e2e 和 parser unit tests 统一断言 `schema_version: "0.3.0"`。
  - 清理/重命名专门测试 V2.1 fallback 逻辑的 test case（如测试 `io/inputs.json` 加载的测试要直接改为测试抛出 deprecated 错误）。