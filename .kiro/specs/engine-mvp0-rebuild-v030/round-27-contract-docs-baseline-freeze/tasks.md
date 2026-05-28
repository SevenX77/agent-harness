# Round 27 Tasks: Contract Docs Baseline Freeze PR1 Gatekeeper

## Cutover Discipline

本 PR 是 PR1 "Gatekeeper"：只建立真实契约防线，不做边界清理，不重构业务代码，不修改 `packages/graph-agent/src/**`。

核心判据：
- 被生产消费者实际使用的就是契约。API 契约、防漂移测试、审计清单必须覆盖完整 65 符号表面，而不是只覆盖 `graph_agent.__all__` 的 18 个符号。
- 65 符号 = `graph_agent.__all__` 18 个稳定导出 + `CONSUMER-API-INVENTORY.md` 发现的 47 个非 `__all__` 外部依赖符号。
- `_predict_internal` 现状在本 PR 中按事实冻结，并标记为“既定事实契约 / 已知债务”；不得在本 PR 中重构、改 import、移动模块或设计新公开接口。该边界清理属于 PR2。
- 所有 expected API 名称、字段名、hash baseline 必须硬编码。禁止从当前模块、`__all__`、inventory 或 Markdown 动态生成 expected 后再和自身比较。
- 黄金原则硬门：65 符号一个不能漏。Audit Agent 会 100% 核对 inventory、API 文档、防漂移测试三方一致，任何遗漏即不合格。

PR1 允许改动范围：
- 新建 `docs/engine/public-api-contract.md`
- 新建 `docs/engine/feature-compliance-checklist.md`
- 新建 `packages/graph-agent/tests/test_public_api_contract.py`
- 新建 `packages/graph-agent/tests/test_feature_traceability_matrix.py`
- 新建 `packages/graph-agent/tests/test_skill_spec_hash_lock.py`
- 新建 `packages/graph-agent/tests/contract-exemptions.yaml`
- 新建 `.github/CODEOWNERS`
- 修改 `docs/engine/skill-spec/` 下 14 份文档，且仅允许添加 `status: FROZEN` frontmatter 与 DO-NOT-EDIT 注释
- 保留 / 更新本任务文件 `.kiro/specs/engine-mvp0-rebuild-v030/round-27-contract-docs-baseline-freeze/tasks.md`

明确禁止：
- 不修改 `packages/graph-agent/src/**`
- 不改 `apps/**`、`scripts/**`
- 不改既有 spec 的 `design.md`、`requirements.md`、`research.md`、`CONSUMER-API-INVENTORY.md`
- 不改 `docs/engine/` 其他既有文档正文
- 不使用 skip / xfail / collect_ignore / 弱断言规避防线
- 不 commit

65 符号冻结清单：
- `run_skill`
- `WorkflowResult`
- `compile_skill`
- `CompileResult`
- `assemble_graph`
- `CompiledSkill`
- `CompiledStateGraph`
- `BlackboardState`
- `LocalWorkspaceResolver`
- `SkillManifest`
- `serialize_skill`
- `Callback`
- `LoggingCallback`
- `MetricsCallback`
- `TracingCallback`
- `GraphAgentError`
- `SkillLoadError`
- `SkillCompilationError`
- `AgentNodeAST`
- `AgentSkillDef`
- `AmbiguityReportEvent`
- `BaseMockStrategy`
- `CallbackEvent`
- `CompactionEvent`
- `CompileIssue`
- `DeadEndPrunedEvent`
- `ExecutionError`
- `FinishTaskEvent`
- `GoldenCase`
- `GoldenCaseStrategy`
- `GraphManifest`
- `GraphPhaseRef`
- `GraphSkillDef`
- `HeuristicStubStrategy`
- `IoInput`
- `LLMCallEvent`
- `LLMClientManager`
- `LLMFallbackEvent`
- `LogicNodeAST`
- `MockStrategy`
- `NudgeEvent`
- `PathDiff`
- `PersonaSkillDef`
- `PhaseEndEvent`
- `PhaseRecord`
- `PhaseStartEvent`
- `PredictGatewayChatModel`
- `PredictResult`
- `PredictTracingCallback`
- `ProviderDef`
- `ResolvedProvider`
- `RetryEvent`
- `SkillCompileError`
- `SkillLoader`
- `SkillResolutionError`
- `SubgraphNodeAST`
- `ToolCallEvent`
- `ValidationFailEvent`
- `WorkingMemoryUpdateEvent`
- `assemble_phase_record`
- `compute_diff`
- `load_config`
- `parse_skill_file`
- `serialize_graph`
- `to_jsonable_dict`

## Tasks

### 1. Docs: 新建 65 符号公开 API 契约文档

Goal:
- 建立基于真实消费表面的 API 契约文档，覆盖完整 65 符号。
- 明确区分 18 个 `__all__` 稳定导出、47 个非 `__all__` 外部依赖、12 个 `_predict_internal` 已知债务。

Files:
- 新建 `docs/engine/public-api-contract.md`

Steps:
- 以 `CONSUMER-API-INVENTORY.md` 和 `packages/graph-agent/src/graph_agent/__init__.py` 为事实来源，整理 65 符号章节。
- 对每个符号追踪真实来源模块，使用 AST / `inspect` 获取函数签名、类字段、Pydantic model fields、dataclass fields 或异常继承关系。
- 每个符号章节必须包含：
  - Symbol name
  - Source module
  - Consumer files
  - Contract status: `@stable`
  - Signature 或 Fields
  - Preconditions
  - Postconditions
  - Drift risk notes
- `_predict_internal` 来源符号必须额外标注：`De Facto Contract / Known Debt`，并说明本 PR 只冻结现状，PR2 再做边界清理。
- 6 个 vendor-only 符号（`AgentSkillDef`、`GraphSkillDef`、`IoInput`、`PersonaSkillDef`、`CompileIssue`、`parse_skill_file`）必须纳入冻结清单，但在文档中标注 `vendor-only / 待核实是否仍需`，不要和 live 依赖混写。
- 文档必须包含 sibling 排除声明：`docs/engine/` 下除 `skill-spec` 以外的其余讲解类子目录属于 Logic-Explained Docs，不属于本次不可动摇契约基线。
- 不把 `skill-spec` Markdown 格式规范混入 Python API 契约；二者在文档中保持独立边界。

Acceptance:
- `docs/engine/public-api-contract.md` 覆盖 65 符号，符号名与本 tasks 的 65 清单、`CONSUMER-API-INVENTORY.md`、防漂移测试三方一致。
- 每个符号都有 Signature 或 Fields、Preconditions、Postconditions、`@stable`。
- 12 个 `_predict_internal` 符号全部标注 `De Facto Contract / Known Debt`。
- 文档包含 sibling 排除声明。
- `rg -n "TODO|TBD|待补|unknown|不确定|以后补" docs/engine/public-api-contract.md` 无输出。

### 2. Test: 新建 65 符号字段级 API 防漂移测试

Goal:
- 用 CI 锁定 65 个真实契约符号的名称集合、来源模块、函数签名、类字段和关键继承关系。
- 防止“符号还在但字段/参数漂移”的隐性破坏。

Files:
- 新建 `packages/graph-agent/tests/test_public_api_contract.py`
- 新建 `packages/graph-agent/tests/contract-exemptions.yaml`

Steps:
- 在测试中硬编码 65 符号 expected 清单，包含每个符号的 canonical source module。
- 使用 `importlib` / `inspect` / Pydantic model metadata / dataclass metadata 检查真实对象。
- 对函数类符号断言参数名、必填/可选结构、默认值、关键类型注解和返回注解，至少覆盖：
  - `run_skill`
  - `compile_skill`
  - `assemble_graph`
  - `serialize_skill`
  - `serialize_graph`
  - `assemble_phase_record`
  - `compute_diff`
  - `load_config`
  - `parse_skill_file`
  - `PredictGatewayChatModel`
- 对 Pydantic / dataclass / model 类做字段级断言，至少覆盖 callback events、manifest AST、Predict models、Compile result/issue、Workflow result、Blackboard state。
- 字段级断言必须包含已知高风险字段，例如：
  - `PathDiff` 必须包含 `added`、`removed`
  - `PhaseRecord` 必须包含 phase 名称、类型、inputs、outputs 等当前事实字段
  - callback event models 必须保留事件 payload 所需字段
  - manifest AST models 必须保留 Studio serializer / validator 使用字段
- 测试读取 `packages/graph-agent/tests/contract-exemptions.yaml`，但仅允许显式登记的 PR/PM 批准项豁免；未登记漂移必须 fail。
- `contract-exemptions.yaml` schema 必须能表达：
  - PR 号或变更编号
  - PM 批准说明
  - 被豁免的符号名、字段名、签名项或 hash key
  - 到期或后续清理说明
- 当前 PR1 初始文件应为空豁免或仅包含 schema 示例注释，不得预先放行真实破坏。

Acceptance:
- `uv run pytest packages/graph-agent/tests/test_public_api_contract.py` 通过。
- 测试中 expected 65 清单为硬编码常量，不从当前模块、inventory、Markdown 或 `__all__` 动态生成。
- 任意删除 65 符号之一、改变 canonical source module、删除关键字段或破坏核心签名都会导致测试失败。
- `contract-exemptions.yaml` 存在，schema 可审计，测试会读取并校验豁免结构。

### 3. Docs + Test: 新建功能合规清单与可追溯矩阵

Goal:
- 将“功能一个都不能少”从 Markdown 清单升级为可验证的 Feature Traceability Matrix。
- 每条功能必须绑定现存测试，误删测试或写错测试路径时 CI 报错。

Files:
- 新建 `docs/engine/feature-compliance-checklist.md`
- 新建 `packages/graph-agent/tests/test_feature_traceability_matrix.py`

Steps:
- 使用 AST / `rg` 穷尽扫描 `packages/graph-agent/src/graph_agent` 与 `packages/graph-agent/tests`，按代码事实提炼功能，不凭印象。
- 清单按 5 类生命周期组织：
  - Loading & Parsing
  - Compilation & Validation
  - Execution & Routing
  - State & Blackboard
  - Observability & Errors
- 每条功能必须具体到“核心行为 + 边界能力”，并附上：
  - Code facts: 具体模块、函数、类
  - Consumer relevance: 如 Studio / gateway / scripts 是否依赖
  - `[Covered By: packages/graph-agent/tests/...::test_name]`
- `test_feature_traceability_matrix.py` 解析 Markdown 中所有 `[Covered By: ...]` 标签。
- 测试必须校验：
  - 每个标签路径存在
  - 每个 `test_name` 在目标文件中存在
  - 被引用测试可被 pytest 单独收集
  - 引用列表不为空
- 最终验证需运行矩阵引用的测试集合，确保当前全部 PASS。

Acceptance:
- 功能清单覆盖 5 类生命周期，且每条功能都有 `[Covered By: ...]` 标签。
- `uv run pytest packages/graph-agent/tests/test_feature_traceability_matrix.py` 通过。
- 删除任一被引用测试或改名时，矩阵测试失败。
- `rg -n "TODO|TBD|待补|凭印象|unknown|不确定" docs/engine/feature-compliance-checklist.md` 无输出。

### 4. Docs + Test: Additive-Only 冻结 skill-spec 并建立 SHA-256 哈希锁

Goal:
- 给 14 份 `skill-spec` 文档加冻结标记，并用 SHA-256 snapshot 锁住注入后的完整内容。
- 防止后续绕过 `status: FROZEN` 悄悄修改正文、空格或代码块。

Files:
- 修改 `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`
- 修改 `docs/engine/skill-spec/01-physical-layout.md`
- 修改 `docs/engine/skill-spec/02-graph-md-spec.md`
- 修改 `docs/engine/skill-spec/03-logic-md-spec.md`
- 修改 `docs/engine/skill-spec/04-subgraph-md-spec.md`
- 修改 `docs/engine/skill-spec/05-agent-md-spec.md`
- 修改 `docs/engine/skill-spec/06-cognitive-template-spec.md`
- 修改 `docs/engine/skill-spec/07-mention-syntax-spec.md`
- 修改 `docs/engine/skill-spec/08-resource-mechanisms-spec.md`
- 修改 `docs/engine/skill-spec/09-builtin-modules-spec.md`
- 修改 `docs/engine/skill-spec/10-skill-resolver-protocol-spec.md`
- 修改 `docs/engine/skill-spec/11-error-code-spec.md`
- 修改 `docs/engine/skill-spec/12-compile-runtime-flow-spec.md`
- 修改 `docs/engine/skill-spec/README.md`
- 新建 `packages/graph-agent/tests/test_skill_spec_hash_lock.py`

Mandatory order:
- 必须先对 14 份文档注入 `status: FROZEN` frontmatter 与 DO-NOT-EDIT 注释。
- 然后再对“注入后的完整文件内容”计算 SHA-256。
- 最后把这些注入后 hash 写入 `test_skill_spec_hash_lock.py` 的硬编码 baseline。
- 反向顺序不允许：如果先算 hash 再注入冻结标记，注入动作本身会破坏 hash baseline。

Steps:
- 对每个文件检查是否已有 YAML frontmatter。
- 若已有 frontmatter，仅添加或更新 `status: FROZEN`，不重排无关字段。
- 若无 frontmatter，在文件最顶部新增最小 frontmatter：
  ```yaml
  ---
  status: FROZEN
  ---
  ```
- 在 frontmatter 后、正文前注入唯一冻结注释：
  ```markdown
  <!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->
  ```
- 严禁改正文标题、段落、列表、代码块、空行语义或已有规范内容。
- 在 `test_skill_spec_hash_lock.py` 中硬编码 14 个文件路径和注入后 SHA-256 baseline。
- SHA-256 计算必须固定使用二进制读取（例如 `Path.read_bytes()`）直接对仓库字节算 hash；如选择文本规范化方案，则必须统一 normalize 行尾 CRLF→LF 并 strip 尾随空行，且测试与 baseline 生成使用同一规范。优先使用二进制读取，避免不同环境行尾或尾随换行差异导致误红。
- 测试读取 `contract-exemptions.yaml`；只有显式登记 PR 号、PM 批准说明和对应 hash key 的变更才允许放行。

Acceptance:
- 14 个文件均有 `status: FROZEN`。
- 14 个文件均有完全一致的 DO-NOT-EDIT 注释。
- 除 frontmatter 与冻结注释外，14 个文件正文 diff 为 0。
- `uv run pytest packages/graph-agent/tests/test_skill_spec_hash_lock.py` 通过。
- 任意修改 14 份冻结文档的正文、空格或代码块都会导致 hash lock 测试失败，除非 `contract-exemptions.yaml` 有合法批准记录。

### 5. Enforcement: 建立 contract-exemptions 批准门与 CODEOWNERS 授权绑定

Goal:
- 将 PM 的 “unless explicitly approved” 落为可审计文件，而不是口头约定。
- 所有契约破坏都必须通过同一个批准门留下记录。
- 防止任何人直接修改 `contract-exemptions.yaml` 自我放行，必须把批准门和契约基线文件绑定到 CODEOWNERS 人工 review。

Files:
- 新建 `packages/graph-agent/tests/contract-exemptions.yaml`
- 新建 `.github/CODEOWNERS`
- 由以下测试读取：
  - `packages/graph-agent/tests/test_public_api_contract.py`
  - `packages/graph-agent/tests/test_skill_spec_hash_lock.py`

Steps:
- 定义 YAML schema，至少包含：
  - `version`
  - `exemptions`
  - `pr`
  - `pm_approval`
  - `reason`
  - `symbols`
  - `fields`
  - `hashes`
  - `expires_or_cleanup`
- 测试必须拒绝结构不完整的豁免记录。
- 测试必须拒绝无 PR 号、无 PM 批准说明、无具体 symbol/field/hash key 的宽泛豁免。
- PR1 不应包含实际破坏项；如需示例，只能用注释说明 schema。
- 新建 `.github/CODEOWNERS`，使用 PM 或 PM 指定负责人 / 团队作为 owner；实施时不得留下 `<placeholder>`、`TODO` 或无效 GitHub owner。
- CODEOWNERS 至少必须覆盖以下契约基线路径：
  - `.github/CODEOWNERS`
  - `packages/graph-agent/tests/contract-exemptions.yaml`
  - `docs/engine/skill-spec/**`
  - `docs/engine/public-api-contract.md`
  - `docs/engine/feature-compliance-checklist.md`
  - `packages/graph-agent/tests/test_public_api_contract.py`
  - `packages/graph-agent/tests/test_feature_traceability_matrix.py`
  - `packages/graph-agent/tests/test_skill_spec_hash_lock.py`
- CODEOWNERS 文件本身只是声明 owner，不会单独强制 review。PM 合并前必须在 GitHub 远端完成具名 ops 动作：对目标受保护分支开启 branch protection 的 `Require review from Code Owners`，否则批准门只有留痕、没有授权防御。
- PR 描述或合并检查记录必须显式写明 branch-protection ops 状态：已开启，或由 PM 指定负责人确认在哪个分支开启。

Acceptance:
- `contract-exemptions.yaml` 存在且可被测试解析。
- API drift 与 hash lock 测试都读取同一个 exemptions 文件。
- 宽泛豁免、缺字段豁免、未登记漂移均无法放行。
- `.github/CODEOWNERS` 存在，并覆盖 `packages/graph-agent/tests/contract-exemptions.yaml`。
- `.github/CODEOWNERS` 覆盖 14 份 `docs/engine/skill-spec/` 冻结文档、`docs/engine/public-api-contract.md`、`docs/engine/feature-compliance-checklist.md` 和三份防漂移测试文件。
- `.github/CODEOWNERS` 使用真实 PM / 指定负责人 owner，不包含 placeholder。
- branch-protection `Require review from Code Owners` 被明确记录为 PM 合并前远端 ops 动作。

### 6. Verification: PR1 纯 Additive 范围与三方一致性核验

Goal:
- 验证 PR1 只建立防线，且 inventory、API 文档、防漂移测试对 65 符号完全一致。

Files:
- No additional files expected.

Commands:
- `uv run pytest packages/graph-agent/tests/test_public_api_contract.py`
- `uv run pytest packages/graph-agent/tests/test_feature_traceability_matrix.py`
- `uv run pytest packages/graph-agent/tests/test_skill_spec_hash_lock.py`
- `python - <<'PY'` 脚本读取 `CONSUMER-API-INVENTORY.md`、`docs/engine/public-api-contract.md`、`packages/graph-agent/tests/test_public_api_contract.py`，核对 65 符号集合完全一致。
- `rg -n "TODO|TBD|待补|凭印象|unknown|不确定|以后补" docs/engine/public-api-contract.md docs/engine/feature-compliance-checklist.md`
- `rg -n "De Facto Contract / Known Debt" docs/engine/public-api-contract.md`
- `rg -n "status: FROZEN|DO NOT EDIT: Golden principle contract baseline" docs/engine/skill-spec`
- `rg -n "contract-exemptions.yaml|docs/engine/skill-spec|public-api-contract.md|feature-compliance-checklist.md|test_public_api_contract.py|test_feature_traceability_matrix.py|test_skill_spec_hash_lock.py" .github/CODEOWNERS`
- `git diff --name-only`

Acceptance:
- 三个防线测试全部通过。
- 65 符号在 inventory、API 文档、API 防漂移测试中三方一致。
- 12 个 `_predict_internal` 符号在文档和测试中按现状冻结，并标记为已知债务。
- `docs/engine/public-api-contract.md` 明确 sibling 排除声明。
- `.github/CODEOWNERS` 存在、覆盖批准门与契约基线文件，并在 PR 记录中明确 branch-protection `Require review from Code Owners` 合并前 ops 动作。
- `git diff --name-only` 白名单只包含：
  - `.kiro/specs/engine-mvp0-rebuild-v030/round-27-contract-docs-baseline-freeze/tasks.md`
  - `.github/CODEOWNERS`
  - `docs/engine/public-api-contract.md`
  - `docs/engine/feature-compliance-checklist.md`
  - `packages/graph-agent/tests/test_public_api_contract.py`
  - `packages/graph-agent/tests/test_feature_traceability_matrix.py`
  - `packages/graph-agent/tests/test_skill_spec_hash_lock.py`
  - `packages/graph-agent/tests/contract-exemptions.yaml`
  - `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`
  - `docs/engine/skill-spec/01-physical-layout.md`
  - `docs/engine/skill-spec/02-graph-md-spec.md`
  - `docs/engine/skill-spec/03-logic-md-spec.md`
  - `docs/engine/skill-spec/04-subgraph-md-spec.md`
  - `docs/engine/skill-spec/05-agent-md-spec.md`
  - `docs/engine/skill-spec/06-cognitive-template-spec.md`
  - `docs/engine/skill-spec/07-mention-syntax-spec.md`
  - `docs/engine/skill-spec/08-resource-mechanisms-spec.md`
  - `docs/engine/skill-spec/09-builtin-modules-spec.md`
  - `docs/engine/skill-spec/10-skill-resolver-protocol-spec.md`
  - `docs/engine/skill-spec/11-error-code-spec.md`
  - `docs/engine/skill-spec/12-compile-runtime-flow-spec.md`
  - `docs/engine/skill-spec/README.md`
- `git diff --name-only | rg "^packages/graph-agent/src/"` 无输出。
