# Round 28 Tasks — Feature Checklist Redesign

## Cutover Discipline

本轮是 schema / contract manifest cutover：新增 F3 manifest YAML 与 schema，迁移旧 `docs/engine/feature-compliance-checklist.md` 和 `packages/graph-agent/tests/test_feature_traceability_matrix.py`。同 PR 必须同步文档、manifest、unit / integration / e2e 可用测试与 CI gate，不允许拆成“业务 PR-A + 测试 PR-B”。

- 新旧 traceability gate 必须 AND 双跑至少 1 个独立 PR 在 `main` green merged 后，且 dual-run overlap 不少于 24h：旧 `test_feature_traceability_matrix.py` 与新 manifest CI 都必须 pass。安全 overlap 后，才允许在同一个原子 cutover PR 下架旧 checklist 和旧测试。
- 严禁 admin override 跳过 CI 合入 `main`。
- 旧 30 项必须在 cutover PR 中逐项列出归宿：保留 / 合并 / 拆分 / 降级 + exemption。
- Cutover PR 合并后 24h 监控窗口内发现关键遗漏，revert 必须经 PM 显式批准，不走 auto-approval。

## Golden Principle Binding

PM 黄金原则是合并硬门：功能 / API 一个都不能少。`feature-compliance-checklist`、`public-api-contract.md`、`skill-spec/*` 均为 Additive-Only 契约面，修改、删除、降级必须有 PM 显式书面批准。

`md_to_json` 事实澄清：`md_to_json` 自愈链路当前在 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:485-575`，与 `packages/graph-agent/src/graph_agent/cognitive/md2json.py` / `packages/graph-agent/src/graph_agent/cognitive/md_patch.py` 共存，属已 hard 化特性，无需作为“待恢复债务”处理。

采用 design v3 §0 双轨制：

- CI 硬门只证明结构、路径、hash、65 符号、源文件映射、FROZEN 漂移等机器可判定事项。
- PM / Reviewer 人审负责语义完整性：新增特性是否漏列、consumer-file 反推是否漏项、业务描述是否模糊。CI 全绿不等于功能完整。

## Tests-First Rule

每个 Task 必须按 TDD 执行：

1. 先写红灯 tests / CI 校验 / fixture，并交 a2 audit。
2. 红灯确认后，a1 才写实现或 manifest 内容让测试变绿。
3. src + tests 不允许同一步混写；撞到既有测试失败时，a1 停下 escalates PM，不准硬改测试规避。
4. 本 tasks.md 只定义后续实施顺序；当前轮不修改 src / tests / docs/engine。

## A-Series Preconditions

### Task A0 — Feature 边界规则入 schema

- 红灯：fixture 层先给出 3 个 invalid `features.yaml` 样例，分别缺失公开方法 / 生命周期阶段表现 / 外部可感知确定性行为边界，manifest validator 必须 fail。
- 绿灯：在 `round28-manifest-schema.yaml` 中加入 `feature_boundary.kind` enum: `public-method`, `lifecycle-behavior`, `externally-observable-behavior`，并要求 `description` 非空。
- Acceptance：a2 audit pass + a3 audit pass。

### Task A1 — Vendor-only 6 项进入 F3 矩阵

决策：6 个 vendor-only / de facto contract 符号全部进入 F3 矩阵，不走永久豁免：`AgentSkillDef`, `GraphSkillDef`, `IoInput`, `PersonaSkillDef`, `CompileIssue`, `parse_skill_file`。

- 红灯：fixture 层提供缺少 vendor-only 6 项任意一项的 `contract_map.yaml`，manifest validator 必须 fail。
- 绿灯：在 `features.yaml` 中使用 `contract_status: vendor-only` 或 `vendor-only-debt` 标记。5 个当前无 live exported definition 的符号 `AgentSkillDef`, `GraphSkillDef`, `IoInput`, `PersonaSkillDef`, `parse_skill_file` 标 `vendor-only-debt`；`CompileIssue` 是 live dataclass / issue contract，单独标 `vendor-only`。6 项均由 public API contract 与 consumer files 防漂移，不允许永久 exemption 消失。
- Acceptance：6 项逐名出现在 `contract_map.yaml` public API axis，且 a2 audit pass + a3 audit pass。

### Task A2 — Non-functional contract 开放词汇表

- 红灯：schema test 覆盖 `non_functional_contracts` 必须含 `{id, type, description, evidence}`，`description` 与 `evidence` 非空；未知 type 必须用 `other`，并给出说明。
- 绿灯：type enum 至少包含 `token-quota`, `concurrency`, `timeout`, `state-isolation`, `sandbox`, `ordering`, `compatibility`, `observability`, `performance`, `other`；允许后续 additive 扩展。
- Acceptance：a2 audit pass + a3 audit pass。

### Task A3 — 示例路径与 anchor 全部真实化

- 红灯：grep / schema test 禁止不存在的 illustrative examples，例如 `docs/engine/skill-spec/05-finish-task-spec.md#workflow-finish-mode`。
- 绿灯：所有 schema 示例换成已 grep verify 的真实路径和 H2 anchor，例如 `docs/engine/skill-spec/05-agent-md-spec.md#body-xml-扁平化容器`、`docs/engine/skill-spec/06-cognitive-template-spec.md#8-大插槽布局拓扑`。
- Acceptance：a2 audit pass + a3 audit pass。

### Task A4 — Hash lock 单文件 rename

- 红灯：test discovery 断言只存在一个 contract hash lock test，不允许新增平行 hash-lock test。
- 绿灯：rename `packages/graph-agent/tests/test_skill_spec_hash_lock.py` -> `packages/graph-agent/tests/test_contract_hash_lock.py`，并泛化覆盖 `docs/engine/skill-spec/*`、`docs/engine/public-api-contract.md`、新版 `docs/engine/feature-compliance-checklist.md`。
- Acceptance：a2 audit pass + a3 audit pass。

### PM External Verify — Branch Protection Attestation

这不是 a1 实施任务，必须写进 PR report：PM 实际操作 GitHub branch protection settings，确认 required reviewers 包含 `@SevenX77`，截图或链接存档。CI 不证明此项。

## Implementation Tasks

### Task 1 — Schema 锁定

目标：新建 `packages/graph-agent/spec/round28-manifest-schema.yaml`，锁定 `features.yaml`、`source_file_map.yaml`、`contract_map.yaml` 的机器可校验 schema。

Tests first:
- 新增红灯 pytest，读取 schema 并用最小 invalid fixtures 断言失败：缺 `description`、缺 `core_paths`、无 `targeted_tests`、错误 `feature_boundary.kind`、Debt 无 `exemption_id`、consumer entry kind 非法、pytest nodeid 不可收集。
- 红灯必须覆盖 A0-A4 的 schema 约束。

Implementation:
- `features.yaml` schema 必须定义 `core_paths: list[{path, anchor?}]`，`description: non-empty string`，`sources` enum，`consumer_files` entry kind: `file`, `stable-export`, `vendor-only-debt`。
- `features.yaml` schema 必须定义 `targeted_tests: list[str]`，minimum length 1；红灯断言每个 feature 至少 1 个 targeted test。
- `features.yaml` schema 必须定义 4 个切面数组：`error_codes_primary: list[str]`, `error_codes_secondary: list[str]`, `events_primary: list[str]`, `events_secondary: list[str]`。
- `source_file_map.yaml` schema 中，`classification=feature` 的 entry 必须满足跨文件约束：该 path 至少出现在 `features.yaml[*].core_paths[*].path` 一次；schema 文件记录 MUST，Task 9 validator 实现 cross-check。
- `source_file_map.yaml` schema 中，`classification=debt` 时 `exemption_id` 是 required non-empty string。
- `contract-exemptions.yaml` schema 必须新增 `exemption_id` primary key，正则 `^EX-[0-9]{4}-[a-z0-9-]+$`，在 `contract-exemptions.yaml` 内唯一；其他 YAML（如 `source_file_map.yaml`）只能把它作为 foreign key 引用，不能重新定义。
- `source_file_map.yaml` 扫描边界必须有配置字段：`include_globs` / `exclude_globs`，默认包含 `packages/graph-agent/src/graph_agent/**/*.py`，不硬编码 121。
- `targeted_tests` 使用完整 pytest nodeid，CI 用 `pytest --collect-only` 验证。

Acceptance:
- schema 自身 lint 通过。
- invalid fixtures 全红，valid minimal fixture 绿。
- a2 audit pass + a3 audit pass。

### Task 2 — `features.yaml` 第一版 v0

目标：基于 65 公开符号、14 份 skill-spec H2、public-api-contract Consumer files 反推业务特性，生成不凑数的第一版 `features.yaml` v0；先用现有 30 项 checklist 的 `[Covered By: ...]` 作为 `targeted_tests` baseline，避免与 Task 5 形成循环依赖。

Tests first:
- 红灯断言每条 feature 有 `id`, `description`, `feature_boundary`, `sources`, `core_paths`, `targeted_tests`, 5 个切面字段。
- 红灯断言错误码与事件只允许作为 primary / secondary 切面，不允许作为 feature source。
- 红灯断言 6 个 vendor-only 符号均有 feature 映射。

Implementation:
- feature 数量不设固定值，预计 40-80；以语义完整为准。
- `targeted_tests` v0 从旧 `docs/engine/feature-compliance-checklist.md` 30 项 `[Covered By: ...]` 抽取并映射到对应 feature；不能先等待 Task 5 新测试。
- 必须枚举 `src` 中所有 monkey-patch / compat shim / runtime hook 模块，反推并建立 runtime compatibility feature，避免 Task 3 source mapping 将这些模块误标为 detail/debt。
- 每个 concrete `[F-v3-*]` 错误码必须有且只有一个 primary owner feature；模板 `[F-v3-*]` 与 `[F-v3-<domain>-<specific>]` 必须过滤。
- 每个 `CallbackEvent` union variant 必须有且只有一个 primary owner feature；以 union variants 为准，不扫孤立类。

Acceptance:
- `features.yaml` 全部 target tests 可 collect。
- feature 描述能对应 research §4 三轨边界。
- a2 audit pass + a3 audit pass。

### Task 3 — `source_file_map.yaml`

目标：把 `packages/graph-agent/src/graph_agent/**/*.py` 全量映射为 `feature` / `detail` / `debt`。

Tests first:
- 红灯断言动态 `find packages/graph-agent/src/graph_agent -name '*.py'` 输出与 `source_file_map.yaml` path 集合完全一致，受 include / exclude config 控制。
- 红灯断言 `classification=feature` 的文件必须被某个 feature 的 `core_paths` 引用。
- 红灯断言 `classification=detail` 必须有非空 `feature_ids`。
- 红灯断言 `classification=debt` 必须有 `exemption_id`，且能在 `contract-exemptions.yaml` 中找到。

Implementation:
- 允许 `feature_ids` 多值，处理跨功能 glue 文件。
- `__init__.py`、compat shim、builtin skill support、patch 模块、empty package marker 必须明确归类，不允许 Unclassified。
- 分类决策表：
  - `__init__.py`：若导出 public / package API，归 `feature` 或 `detail` 并指向对应 API feature；纯 re-export glue 归 `detail`。
  - `patches/` 与 monkey patch 文件：归 `feature`，必须指向 runtime compatibility / provider compatibility feature。
  - 空 `validators/__init__.py`、package marker：归 `detail`，指向加载 / 包边界 feature。
  - builtin skill subdirs、`skills/builtin/**` 支撑代码：归 `feature` 或 `detail`，必须绑定 builtin skill / md-patch / resource tool feature。
  - compat shim / legacy import bridge：归 `detail`，必须绑定被保护的兼容 feature；若已无 consumer 才能走 `debt` + exemption。
  - generated / cache / sandbox helper：默认 `detail`，必须指向其服务的 public API 或 runtime feature。

Acceptance:
- 所有源文件 100% 映射。
- 无硬编码总数依赖；文件增删会触发 CI 红灯。
- a2 audit pass + a3 audit pass。

### Task 4 — `contract_map.yaml`

目标：建立 65 public API symbols、14 skill-spec 文件 H2 section、Consumer files 三轴到 feature id 的映射。

Tests first:
- 红灯断言 65 符号来自 `test_public_api_contract.py` / `public-api-contract.md` 的 SSOT，任何漏项 fail。
- 红灯断言 skill-spec axis 只采 14 份 frozen Markdown 的 H2，不采任意 H3。
- 红灯断言 Consumer files 解析自 `public-api-contract.md`，并区分 `file`, `stable-export`, `vendor-only-debt`。

Implementation:
- 每轴每项至少映射一个 `features.yaml` id。
- Vendor-only 6 项按 A1 纳入 public API axis，不走永久豁免。
- `stable-export` 与 `vendor-only-debt` consumer entries 仅作为 contract placeholder / governance axis，不等同真实 consumer-file；其业务反推必须绑定到 API compatibility / vendor debt feature，不得伪造成真实文件消费。

Acceptance:
- 65 symbols、skill-spec H2、consumer entries 均无 unmapped。
- 映射到不存在 feature id 时 CI fail。
- a2 audit pass + a3 audit pass。

### Task 5 — Targeted Invariant Tests

目标：按 design §5 补强机制级守护测试，不用泛 E2E 代替；完成后产生 `features.yaml` v1 回填。

Tests first:
- 先新增或标注红灯测试清单，覆盖 LLM 占位符装配边界、Middleware 挂载与触发顺序、工具沙箱权限域隔离、黑板状态隔离 / 并发竞争、复杂错误码分支与恢复。
- a2 audit 先确认这些测试确实是机制断言，不是空跑覆盖率。

Implementation:
- 让相关实现或 manifest 绑定测试变绿。
- 每个新增守护测试必须回填到 `features.yaml.targeted_tests`，形成 Task 2 v1；不得删除 Task 2 v0 从旧 30 项继承来的有效 baseline test。

Acceptance:
- 目标测试全部可单独 collect / run。
- manifest 中所有 `targeted_tests` 指向真实 pytest nodeid。
- 每个 `features.yaml.targeted_tests[]` 项都能被 `pytest --collect-only` 收到。
- a2 audit pass + a3 audit pass。

### Task 6 — Cutover

目标：新 F3 manifest 与旧 30 项 checklist 原子切换。

Tests first:
- 新旧 gate AND 双跑红灯：旧 `test_feature_traceability_matrix.py` 与新 manifest validator 任一失败都阻断。
- 新增 cutover mapping test，要求旧 30 项逐项有去向：保留 / 合并 / 拆分 / 降级 + exemption。

Implementation:
- overlap 至少 1 个独立 PR 在 `main` green merged 后且 dual-run overlap 不少于 24h，才允许原子删除旧 `packages/graph-agent/tests/test_feature_traceability_matrix.py` 与旧 `docs/engine/feature-compliance-checklist.md`，替换为新版 frozen checklist / manifest 输出。
- `.github/CODEOWNERS` 必须新增 / 保留 `docs/engine/feature-compliance-checklist.md @SevenX77`，与 round-27 契约文档同标准。
- 新版 `docs/engine/feature-compliance-checklist.md` 顶部必须添加 YAML frontmatter：
  ```yaml
  ---
  status: FROZEN
  ---
  ```
  并紧随 frontmatter 添加冻结注释：
  ```markdown
  <!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->
  ```
- PR report 写 24h rollback 监控要求。

Acceptance:
- 新旧 overlap 阶段 AND pass。
- 下架旧 gate 的 PR 含完整旧 30 项去向表。
- CODEOWNERS 绑定存在，新 checklist FROZEN frontmatter + DO-NOT-EDIT 注释存在。
- a2 audit pass + a3 audit pass。

### Task 7 — Contract Hash Lock

目标：按 A4 rename 并泛化 hash lock。

Tests first:
- 红灯断言 `test_skill_spec_hash_lock.py` 不再存在，`test_contract_hash_lock.py` 是唯一 hash lock。
- 红灯断言 `public-api-contract.md` 与新版 `feature-compliance-checklist.md` hash drift 会 fail。

Implementation:
- rename 单文件并扩展 expected hash baseline。
- hash lock 覆盖 `packages/graph-agent/spec/round28-manifest-schema.yaml`，防止 schema 自身被静默改成二阶后门。
- 继续读取 `contract-exemptions.yaml`，但 hash exemption 必须包含 PM approval、PR、reason、expiry / cleanup。

Acceptance:
- 任一 frozen contract 文档未经 exemption 改动都会 fail。
- schema hash drift 未经 exemption 会 fail。
- a2 audit pass + a3 audit pass。

### Task 8 — Exemption Schema 放开空断言

目标：把 PR1 的 “exemptions 必须为空” 改成 shape-valid governance。

Tests first:
- 红灯 fixture：缺 `exemption_id`、缺 PM approval、缺 replacement feature、空 reason、过期 cleanup 均 fail。
- 红灯断言当前 `contract-exemptions.yaml` 空列表仍 shape-valid。

Implementation:
- 修改 `test_public_api_contract.py::test_exemptions_yaml_currently_empty_in_pr1` 为 shape-valid 校验。
- 扩展 schema 支持 `exemption_id`、`replacement_feature_ids`、`affected_features`、`expires_or_cleanup`；`exemption_id` 使用正则 `^EX-[0-9]{4}-[a-z0-9-]+$`，作为 `contract-exemptions.yaml` 内唯一 primary key，供 `source_file_map.yaml` debt 以 foreign key 反向引用。

Acceptance:
- 空 exemptions pass；填入合法 deprecation / debt exemption pass；非法 exemption fail。
- a2 audit pass + a3 audit pass。

### Task 9 — Manifest CI 校验脚本

目标：新增 pytest / CI gate 校验 F3 manifest 完整性。

Tests first:
- 红灯 fixtures 覆盖：路径不存在、anchor 不存在、65 符号漏映射、源文件未映射、错误码无 primary owner、事件无 primary owner、targeted test 不可 collect、FROZEN hash drift。

Implementation:
- 新增 manifest validator pytest，接入 `.github/workflows/ci.yml` graph-agent tests。
- 校验范围包括 schema 结构、路径锚点、public API drift、source map 完整性、contract map 完整性、hash lock、FROZEN frontmatter。
- 实现 Task 1 记录的跨表 cross-check：`classification=feature` path 必须至少出现在 `features.yaml[*].core_paths`；`targeted_tests` 每项必须可 collect；每个 concrete 错误码 / union event variant 必须恰好 1 个 primary owner。

Acceptance:
- CI 硬门能 catch design §0 machine audit layer 的全部 class。
- 报错信息必须指出 manifest path、field path、缺失 item 和修复方向。
- a2 audit pass + a3 audit pass。

## Verification Commands

后续实施 PR 至少运行：

```bash
uv run pytest packages/graph-agent/tests/test_public_api_contract.py -q
uv run pytest packages/graph-agent/tests/test_contract_hash_lock.py -q
uv run pytest packages/graph-agent/tests/test_round28_manifest_contract.py -q
uv run pytest packages/graph-agent/tests --tb=short -q
```

只读审计辅助命令：

```bash
find packages/graph-agent/src/graph_agent -name '*.py' | sort
rg -n "Consumer files|^## " docs/engine/public-api-contract.md docs/engine/skill-spec
rg -n "CallbackEvent|event_type" packages/graph-agent/src/graph_agent/callbacks/events.py
rg -n "\[F-v3-" docs/engine/skill-spec/11-error-code-spec.md
```
