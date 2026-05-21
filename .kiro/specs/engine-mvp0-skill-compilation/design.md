# Engine MVP0 — skill-compilation Design

## §0.5 继承字段表 (round N-1 = main HEAD 现状, MVP0 默认不动)

### Pydantic models (manifest.py)

| 字段 | 类型 | 含义 | MVP0 是否改 |
|---|---|---|---|
| `GraphManifest.schema_version` | `Literal["2.1"]` | Schema 版本 | 不改 |
| `GraphManifest.name` | `str` | 技能名 | 不改 |
| `GraphManifest.description` | `str` | 描述 | 不改 |
| `GraphManifest.io_inputs_ref` | `str` | 根 input schema 路径 | 不改 |
| `GraphManifest.io_outputs_ref` | `str` | 根 output schema 路径 | 不改 |
| `GraphManifest.phases` | `list[GraphPhaseRef]` | 阶段声明列表 | 不改 |
| `GraphManifest.metadata` | `dict[str, Any]` | 额外元数据 | 不改 |
| `GraphPhaseRef.id` | `str` | 阶段 ID | 不改 |
| `GraphPhaseRef.src` | `str` | 阶段源码相对路径 | 不改 |
| `GraphPhaseRef.depends_on` | `list[str]` | 拓扑前置依赖 | 不改 |
| `_BaseNodeAST.name` | `str \| None` | 节点名 | 不改 |
| `_BaseNodeAST.raw_blocks` | `dict[str, str]` | 未解析区块 | 不改 |
| `_BaseNodeAST.metadata` | `dict[str, Any]` | 元数据 | 不改 |
| `SkillNodeAST.system_prompt` | `str` | LLM phase system prompt | 不改 |
| `SkillNodeAST.exit_contract` | `str` | finish_task 契约 | 不改 |
| `SkillNodeAST.tools` | `list[str]` | LLM 可调工具列表 | 不改 |
| `SkillNodeAST.subagents` | `list[SubagentSpec]` | 子代理列表 | 不改 |
| `LogicNodeAST.python_callable` | `str` | action 函数引用 | 不改 |
| `SubgraphNodeAST.sub_skill_ref` | `str` | 子图挂载引用 | 不改 |
| `SubagentSpec.name` | `str` | 子代理名 | 不改 |
| `SubagentSpec.path` | `str` | 子代理路径 | 不改 |
| `SubagentSpec.description` | `str` | 描述 | 不改 |
| `CompiledSkill.subagents_by_phase` | `dict` | 子代理元数据字典 | 不改 (P1-1 已修) |
| `CompiledSkill.phase_tokens` | `dict` | AST 定位 Token | 不改 (P1-1 已修) |

### `[NEW]` 新增 (不破坏现有)
- `PhaseIOSchema` `[NEW]` — 新 Pydantic 模型，用于封装节点级别的 input/output schema 字典。
- `SkillNodeAST.io: PhaseIOSchema | None = None` `[NEW]` — 候选 A（软兼容）路径下的新增选填字段。
- `LogicNodeAST.io: PhaseIOSchema | None = None` `[NEW]` — 同上，针对 Logic 节点的选填字段。
- `CompileIssue` 字段增强 `[NEW]` — 增加对 Canvas 高亮至关重要的属性：`code` (错误码), `phase_id` (节点), `field_name` (缺失字段), `path`, `line`。

### `[BREAKING]` 修改现有 (必须 PM 拍板)
- `SkillNodeAST.io: PhaseIOSchema = Field(...)` `[BREAKING]` — A7 硬强制路径。如果拍板此项，必须修改所有现有的 V2.1 Fixture。
- `LogicNodeAST.io: PhaseIOSchema = Field(...)` `[BREAKING]` — 同上。
- `compile_skill() -> CompiledSkill` 签名修改为 `compile_skill() -> tuple[CompiledSkill | None, CompileResult]` `[BREAKING]` — 结构化抛出 Issue 时，调用方必须感知 CompileResult 的变更。

## §1. P1-1 cache 元数据补全 (已完成, ship by a1)
P1-1 目标是使缓存读取后能够具备和冷编译完全等价的状态信息，解决 `CompiledSkill` 恢复时子代理注册工具丢失及 Token 源码定位遗失的问题。

a1 提交的实现已合并至 `cache.py`。方案在序列化字典中增加了完整的 `subagents_by_phase` 原始字段与 `phase_tokens`。在重水化过程中，使用现存的 `build_subagent_input_model` 在内存中精确重建了动态 Pydantic Class。经 a2 review 确认该设计正确、无越界，并且由测试 `test_cache_hit_restores_subagents_by_phase` 和 `test_cache_hit_restores_phase_tokens` 覆盖，该项已完成。

## §2. P2-2 cache 写失败降级 (已完成, ship by a1)
P2-2 的目标是将缓存保存作为一种可选性能优化，如果写入发生目录权限错误等 `OSError` 时不中断正常编译流程。

a1 提交的实现为 `cache.py` 内部的 `save_to_cache` 包裹了 `try...except OSError` 结构，并触发一个 `warnings.warn` 降级反馈。经测试 `test_cache_write_failure_warns_and_returns_compiled_skill` 验证降级逻辑能正确返回 CompiledSkill，未干预核心逻辑。该项已完成。

## §3. A7 SKILL.md frontmatter 必须 io dict

### §3.1 设计候选 A: [BREAKING] 硬强制
- **描述**：在 `manifest.py` 中强制为执行节点添加 `io: PhaseIOSchema = Field(...)`。任何缺失 `io` 字典的节点文件直接触发 Pydantic `ValidationError` 并截断流程。
- **冲击文件**：`packages/graph-agent/src/graph_agent/core/manifest.py:59-90` (AST 定义)。所有涉及 V2.1 格式的 Fixture (`fake_canvas_fanout`, `canvas_serializer`, `v21_assembly`, `subagent_minimal`) 将因缺少 `io:` frontmatter 全部报错。
- **理由**：能够给予 A8 最坚实的基础：所有节点均有严格的自述契约。
- **迁移路径**：必须用脚本或手动给每一个 `LOGIC.md` / `SKILL.md` 追加诸如 `io: {inputs: {}, outputs: {}}` 的最小空白结构。
- **兼容性**：不兼容。将破坏当前的 `main` 分支。

### §3.2 设计候选 B: [NEW] 软兼容
- **描述**：在 AST 层面设定 `io: PhaseIOSchema | None = None` 为选填。当解析器未能找到 `io` 字段时静默允许。
- **冲击文件**：仅 AST 结构 `manifest.py`，不影响任何其他模块或现有 Fixture。
- **理由**：不阻碍其他功能代码的快速合并和迭代，避免对测试资产产生雪崩效应。
- **迁移路径**：无迁移要求。
- **兼容性**：100% 兼容。但缺点是 A8 数据流校验时遇到空 `io` 只能无视，起不到实质性的拦截作用。

### §3.3 设计候选 C: [BREAKING/Soft] 中间路径
- **描述**：在 AST 中设定 `io` 为默认可选，但在 `loader.py` 的解析阶段人工校验。如果为 `None`，抛出一个严重的 `CompileWarning`，预告下个里程碑变为 `SkillCompileError`。
- **冲击文件**：`manifest.py`, `loader.py:158-167`。
- **理由**：给存量代码提供喘息时间，但会在 CLI 或日志中大量产生预警噪音。
- **迁移路径**：通过查看警告信息逐一修正旧代码。
- **兼容性**：目前阶段完全兼容，警告层面干扰。

### §3.4 推荐 + 拍板项
- **推荐**：推荐候选 C（中间路径）。由于目前正在构建 A8 前置条件，直接炸毁测试环境会导致构建流水线长时瘫痪，发出强力的 CompileWarning 给后续任务指明修改方向更为可控。
- **PM 拍板 Q-A7 (新)**：对于 `io` frontmatter，是直接走 [BREAKING] (候选A) 直接瘫痪当前资产倒逼全量修正，还是先走中间预警路径 (候选C)？

## §4. A8 图级 IO 数据流静态校验

### §4.1 设计候选 A: [NEW] 仅进行 Key 可见性检查
- **描述**：在 `loader.py` 底部增加 `_validate_phase_io_dataflow` 函数，按拓扑序遍历阶段，仅通过字典键 (`keys()`) 比对来确认下游必需的 input 是否能在前置节点的 output（或全局 inputs）中找到。
- **冲击文件**：`packages/graph-agent/src/graph_agent/core/loader.py:142-177` (主编排增加一层拦截校验)。
- **理由**：轻量，执行快，能快速拦截绝大多数典型的“字段遗漏”连通性错误。
- **迁移路径**：作为新校验层加入，无历史包袱。
- **兼容性**：兼容，只需在节点带有合法 io 时触发。

### §4.2 设计候选 B: [NEW] 全面的 JSON Schema 类型交集校验
- **描述**：除了 Key 比对外，进一步核查输入与输出声明的 JSON Schema Type，以确认下游请求 `number` 时上游是否恰好提供 `number` 或兼容类型。
- **冲击文件**：同候选 A，但需要引入复杂的三方 Schema 比对模块。
- **理由**：最安全，但工程量极其庞大且在当下 MVP0 过于超前。
- **迁移路径**：需要复杂开发。

### §4.3 推荐 + 拍板项
- **推荐**：候选 A。满足 MVP0 的防御要求，性能损耗最小。
- **PM 拍板 Q-A8 (新)**：数据流静态校验是仅实现轻量级 Key 连通性检查 (候选A)，还是追求全面的 Schema Type 合法性推演 (候选B)？

## §5. 结构化 CompileIssue

### §5.1 设计候选 A: [BREAKING] 修改 compile_skill 签名
- **描述**：废弃直接返回 `CompiledSkill`，改成返回 `(CompiledSkill | None, CompileResult)`，强制所有下游对齐处理。
- **冲击文件**：`compiler.py:40-65`，以及整个 execution-runtime 中调用 `compile_skill` 的入口和所有测试文件。
- **理由**：这是标准的静态分析/编译器规约范式。
- **迁移路径**：全局重构，包括 runner/assembler 必须重写。
- **兼容性**：不兼容，全盘打碎重建。

### §5.2 设计候选 B: [NEW] 在异常类内嵌 Issue 列表
- **描述**：维持主流程直接返回 `CompiledSkill`，一旦出错，依然抛出 `SkillCompileError` / `GraphAgentError`，但为异常扩展 `self.issues = [...]` 属性。
- **冲击文件**：`exceptions.py` 及 `loader.py` 内部报错触发处。
- **理由**：改动成本微乎其微。执行层不需要动，只有想抓取结构化错误的 FastAPI 层才需要 Catch 异常并读取 `issues`。
- **迁移路径**：对现有代码无伤。
- **兼容性**：向上兼容。

### §5.3 推荐 + 拍板项
- **推荐**：候选 B。为了不过早打乱尚未稳定的 Runtime 调度层，将问题结构化封存在异常对象内是投入产出比最高的选择。
- **PM 拍板 Q-ISSUE (新)**：结构化错误的传递方式，是激进地采用 [BREAKING] 改变签名 (候选A)，还是保守地封装在 Python 异常属性里 (候选B)？

## §6. 测试策略
- a1 已经完成了涵盖缓存命中、深层重建、异常回退的四个 cache test，证明缓存侧稳定。
- **A7/A8 Unit Tests**：需要在 `test_v21_loader.py` 内部增加对于各种错误断崖的测试（e.g. `test_missing_io_raises_warning`, `test_dataflow_missing_key_creates_issue`），通过提供特定的 mock manifest 检测拦截拦截效能。
- **结构化错误 Tests**：只需编写简单的捕获测试，保证 Catch 到异常对象时，提取出来的 `code` / `line` 正确即可。
- **LLM/e2e**：无需在此添加 LLM Mock。编译系统本身脱离运行时。

## §7. 实施顺序
1. PM 审核本文档并对 Q-A7、Q-A8、Q-ISSUE 做出拍板。
2. PM 拍板后指派 task，让工程师/Agent 进行对应的 [BREAKING] 或增量调整。
3. 针对 A7 修改 Fixture（如有必要）。
4. 植入 `PhaseIOSchema` 和 A8 数据流比对算法。
5. 实装结构化错误映射与发出。