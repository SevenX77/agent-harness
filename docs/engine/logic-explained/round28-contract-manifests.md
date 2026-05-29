# Round 28 Contract Manifests 运行逻辑人话版

署名: Codex  
日期: 2026-05-28  
定位: 解释 Round 28 的契约 manifest 怎么保护"功能/API 一个都不能少"。本文按字段解释, 不做源码导览。

## §1 Round 28 引擎契约系统总览

Round 28 的目标是把旧的 30 项人工 checklist 升级成机器可检查、人工可审阅的契约系统。黄金原则是: 已经对外承诺的功能、API、错误码、事件、源码职责和消费者入口, 不能在没人发现的情况下减少。

系统由 3 个 manifest、1 个 validator、1 个 CI gate 和 3 组测试一起工作:

```text
features.yaml
  说明有哪些业务能力, 每个能力由哪些源码、错误码、事件和测试守住

source_file_map.yaml
  说明每个 graph_agent 源文件属于哪个业务能力, 或只是哪个能力的实现细节

contract_map.yaml
  说明 public API symbol、skill-spec H2、consumer entry 分别映射到哪些业务能力

validate_round28_manifest.py
  加载 manifest, 做跨文件检查, 失败时输出 R28_* 错误并返回非 0

CI gate
  在 graph-agent tests 后运行 validator, 失败就阻断 PR

dual-run tests
  旧 checklist hard lock + 新 manifest fixtures + 5 类机制 guard 一起跑
```

Round 28 当前基线是 35 个业务 feature、92 个 concrete `[F-v3-*]` 错误码、33 个 callback event、121 个源码 `.py` 文件、65 个 public API symbol、53 个 skill-spec H2 section。

## §2 features.yaml 字段级翻译

`features.yaml` 的顶层字段是 `features`。它是一个列表, 每个列表项是一条业务能力。

### `features[*].id`

含义: 业务 feature 标识符。当前命名形状是 `F-<domain>-<capability>`, 例如 `F-runtime-execution` 和 `F-vendor-contract-debt`。  
为什么要有: 它是其他 manifest 引用 feature 的主键。没有稳定 id, source file、public API、skill-spec H2 都无法指向同一个业务能力。  
失败信号: schema 会拒绝不符合 `^F-[a-z0-9-]+$` 的 id。validator 当前会在被引用但不存在时输出 `R28_CONTRACT_FEATURE_DANGLING`。如果后续把重复 id 提升为显式 validator 错误, 对应语义是 `R28_FEATURE_ID_DUPLICATE`。

### `features[*].description`

含义: PM 和 reviewer 能读懂的业务说明, 解释这个 feature 守住什么能力。  
为什么要有: 防止用 `F-all-error-code-owners` 这类 umbrella 名字把多个业务能力糊成一条。  
失败信号: schema 要求非空字符串。空描述会被 schema validation 拒绝, 对应语义是 `R28_FEATURE_DESCRIPTION_EMPTY`。

### `features[*].feature_boundary.kind`

含义: feature 的边界类型。允许值只有 `public-method`、`lifecycle-behavior`、`externally-observable-behavior`。  
为什么要有: reviewer 需要知道这个能力是对外方法、生命周期行为, 还是外部能观察到的行为。  
失败信号: schema enum 拒绝其他值, 对应语义是 `R28_FEATURE_BOUNDARY_KIND_INVALID`。

### `features[*].feature_boundary.evidence`

含义: 一句证据, 说明为什么这个 feature 属于当前边界。  
为什么要有: 防止只写分类不写理由。  
失败信号: schema 要求非空。空值会在 schema validation 阶段失败。

### `features[*].sources`

含义: feature 的来源清单。常见来源包括 public API、skill-spec、source-file-map。  
为什么要有: 业务能力不是凭空造出来的, 它必须能追溯到公开符号、spec H2、consumer entry 或源码职责。  
失败信号: schema 要求至少一项。缺失或空数组会被拒绝。

### `features[*].public_api_symbols`

含义: 可选字段, 列出该 feature 直接守住的 public API symbol。  
为什么要有: 公开符号是下游集成的稳定入口, 必须能追到业务能力。  
失败信号: 如果 public API symbol 在 `contract_map.yaml` 中漏映射, validator 输出 `R28_PUBLIC_API_UNMAPPED`。

### `features[*].skill_spec_sections`

含义: 可选字段, 列出该 feature 直接对应的 skill-spec Markdown anchor。  
为什么要有: skill-spec 是 frozen contract。feature 如果来自某段 spec, 必须指向真实文件和真实 anchor。  
失败信号: schema 限定文件必须来自现有 skill-spec 文件名集合。validator 遇到不存在文件或空 anchor 输出 `R28_SKILL_SPEC_ANCHOR_MISSING`。

### `features[*].consumer_files`

含义: 可选字段, 记录 consumer 入口。`kind` 允许 `stable-export`、`vendor-only-debt`、`live-consumer`。  
为什么要有: 有些契约不是源码直接调用, 而是 stable export 或 vendor-only debt。它们也必须被追踪。  
失败信号: schema enum 拒绝非法 `kind`。contract map 漏 vendor-only 六项时 validator 输出 `R28_VENDOR_ONLY_UNMAPPED`。

### `features[*].core_paths`

含义: 这个 feature 的核心源码路径子集。每项至少有 `path`, 可选 `anchor`。  
为什么要有: feature 必须落到具体实现文件, 但不能把全部 121 个文件塞进一个 feature。  
失败信号: schema 要求至少一项。`source_file_map.yaml` 中 `classification: feature` 的文件如果没有出现在对应 feature 的 `core_paths`, validator 输出 `R28_FEATURE_FILE_NOT_IN_CORE_PATHS`。

### `features[*].error_codes_primary`

含义: 这个 feature 主拥有的 concrete `[F-v3-*]` 错误码列表。  
为什么要有: 每个错误码都代表一个用户可见的失败语义。它必须恰好属于一个主业务能力。  
失败信号: 同一个错误码被两个 feature primary 拥有时输出 `R28_PRIMARY_OWNER_DUPLICATE`。完整 manifest 中有错误码没有 primary owner 时输出 `R28_PRIMARY_OWNER_MISSING`。

### `features[*].error_codes_secondary`

含义: 这个 feature 次级关联的错误码列表。  
为什么要有: 一个错误码可能影响多个能力, 但只能有一个 primary owner。secondary 用来表达影响关系, 不改变主责。  
失败信号: schema 要求每项匹配 `[F-v3-*]` 格式。primary 缺失仍由 `R28_PRIMARY_OWNER_MISSING` 报告。

### `features[*].events_primary`

含义: 这个 feature 主拥有的 `CallbackEvent` union variant。  
为什么要有: event 是外部观察 runtime 行为的方式, 每个 event 都必须有一个业务主责。  
失败信号: 同一个 event 被两个 feature primary 拥有时输出 `R28_PRIMARY_OWNER_DUPLICATE`。完整 manifest 中有 event 没有 primary owner 时输出 `R28_PRIMARY_OWNER_MISSING`。

### `features[*].events_secondary`

含义: 这个 feature 次级关联的 event。  
为什么要有: 表达影响关系, 但不改变 event 的主责。  
失败信号: schema 要求名称以 `Event` 结尾。primary 缺失仍由 `R28_PRIMARY_OWNER_MISSING` 报告。

### `features[*].non_functional_contracts`

含义: 非功能契约列表。每项有 `id`、`type`、`description`、`evidence`。当前 `type` 允许 `token-quota`、`concurrency`、`timeout`、`state-isolation`、`sandbox`、`ordering`、`compatibility`、`observability`、`determinism`、`security`、`performance`、`other`。  
为什么要有: 有些能力不是 API 形状, 而是顺序、隔离、兼容、可观察性。它们仍然是黄金原则的一部分。  
失败信号: schema 要求四个字段都存在且文本非空。非法 type 会被 schema enum 拒绝。

### `features[*].targeted_tests`

含义: 至少一个 pytest nodeid。  
为什么要有: 每个业务能力必须有一个可收集的测试入口作为最低 guard。  
失败信号: schema 要求非空数组和 `tests/...::test...` 格式。validator 用 `pytest --collect-only` 收集失败时输出 `R28_TARGETED_TEST_UNCOLLECTABLE`。

## §3 source_file_map.yaml 字段级翻译

`source_file_map.yaml` 的顶层字段是 `files`。它必须覆盖 `packages/graph-agent/src/graph_agent/**/*.py` 下的所有 `.py` 文件。

### `files[*].path`

含义: 源文件路径, repo-root 相对路径。  
为什么要有: 每个源码文件都必须被分类, 否则新增代码可能绕过 feature 审计。  
失败信号: manifest 漏掉真实源码文件时 validator 输出 `R28_SOURCE_FILE_UNMAPPED`。如果后续加入显式存在性检查, 不存在路径对应语义是 `R28_SOURCE_FILE_NOT_EXIST`。

### `files[*].classification`

含义: 文件分类。允许值是 `feature`、`detail`、`debt`。  
为什么要有: `feature` 文件是业务能力核心实现, `detail` 文件是某个能力的实现细节, `debt` 文件是已批准的临时债务。  
失败信号: schema enum 拒绝其他值, 对应语义是 `R28_CLASSIFICATION_INVALID`。

### `files[*].feature_ids`

含义: 当 `classification: feature` 时必填, 是拥有这个核心源码文件的 feature id 数组。  
为什么要有: 一个核心文件可以支撑多个能力, 所以这里允许数组。  
失败信号: schema 要求 feature 文件必须有 `feature_ids`。validator 还会检查该 `path` 是否出现在对应 feature 的 `core_paths`, 否则输出 `R28_FEATURE_FILE_NOT_IN_CORE_PATHS`。

### `files[*].feature_id`

含义: 当 `classification: detail` 时使用, 是这个细节文件服务的单个父 feature。  
为什么要有: helper、package marker、re-export glue 也必须有业务归属, 不能变成无人负责的实现细节。  
失败信号: schema 要求 id 格式是 `F-*`。如果后续把 dangling 检查扩展到 source map, 对应语义是 `R28_FEATURE_ID_DANGLING`。

### `files[*].exemption_id`

含义: 当 `classification: debt` 时必填, 格式是 `EX-0000-name`。  
为什么要有: debt 不能永久无主。每个 debt 文件必须能追到 PM 批准的 exemption。  
失败信号: schema 要求格式 `^EX-[0-9]{4}-[a-z0-9-]+$`。debt 文件缺少 exemption 时 validator 输出 `R28_DEBT_EXEMPTION_REQUIRED`。如果后续加入 foreign-key 检查, dangling exemption 对应语义是 `R28_EXEMPTION_ID_DANGLING`。

## §4 contract_map.yaml 字段级翻译

`contract_map.yaml` 有三条轴: public API symbol、skill-spec H2、consumer entry。

### `public_api_symbols.<SymbolName>.feature_ids`

含义: 每个 public API symbol 映射到至少一个 feature id。当前基线是 65 个 symbol。  
为什么要有: 下游只看到 API symbol, reviewer 必须能从 symbol 找到业务能力和测试。  
失败信号: schema 要求每个 entry 有非空 `feature_ids`。validator 发现 public API contract 里的 symbol 未映射时输出 `R28_PUBLIC_API_UNMAPPED`。vendor-only 六项漏掉时输出 `R28_VENDOR_ONLY_UNMAPPED`。

### `skill_spec_sections.<filename>#<H2>.feature_ids`

含义: 每个 frozen skill-spec H2 映射到至少一个 feature id。当前基线是 53 个 H2。  
为什么要有: spec 是契约文本, 每段 H2 都必须能落到业务能力, 防止文档和实现分叉。  
失败信号: schema 要求每项有非空 `feature_ids`。如果后续把 H2 全覆盖检查提升为 validator 显式错误, 对应语义是 `R28_H2_UNMAPPED`。

### `consumer_files[*].kind`

含义: consumer entry 类型。允许 `stable-export`、`vendor-only-debt`、`live-consumer`。  
为什么要有: stable export、vendor-only debt、真实调用方的审计意义不同, 不能混成一个普通文件路径。  
失败信号: schema enum 拒绝非法 kind, 对应语义是 `R28_CONSUMER_KIND_INVALID`。

### `consumer_files[*].path`

含义: live consumer 的路径。  
为什么要有: 真实调用方是反推业务能力的重要证据。  
失败信号: schema 要求非空字符串。当前 validator 主要检查 feature id 引用是否存在。

### `consumer_files[*].symbol`

含义: stable export 或 vendor-only debt 的 symbol 名。  
为什么要有: 这些 entry 不是 live file, 但仍然是契约占位。vendor-only debt 必须指向 `F-vendor-contract-debt`。  
失败信号: vendor-only 六项缺失时 validator 输出 `R28_VENDOR_ONLY_UNMAPPED`。

### `consumer_files[*].feature_ids`

含义: 每条 consumer entry 映射到至少一个 feature id。  
为什么要有: consumer 只能通过 feature 被审计, 不能孤立存在。  
失败信号: schema 要求非空数组。validator 发现引用不存在的 feature id 时输出 `R28_CONTRACT_FEATURE_DANGLING`。

## §5 validator 行为翻译

入口命令:

```bash
python packages/graph-agent/scripts/validate_round28_manifest.py \
  packages/graph-agent/spec/features.yaml \
  packages/graph-agent/spec/source_file_map.yaml \
  packages/graph-agent/spec/contract_map.yaml
```

输入: argv 是一个或多个 YAML 路径。CI 传入 3 个正式 manifest。测试 fixture 可以只传一个 YAML。  
输出: 成功时 exit code 是 0。失败时向 stderr 打印一行或多行 `R28_*` 错误, exit code 是 1。没有传 argv 时 exit code 是 2。

当前 validator 实际输出的 `R28_*` 错误码如下:

| 错误码 | 何时触发 | 修法 |
|---|---|---|
| `R28_TARGETED_TEST_UNCOLLECTABLE` | 某个 `targeted_tests` nodeid 无法被 pytest collect | 改成真实存在、可 collect 的 pytest nodeid |
| `R28_PRIMARY_OWNER_DUPLICATE` | 同一个 error code 或 event 出现在两个 feature 的 primary 字段 | 只保留一个 primary owner, 其他 feature 改 secondary |
| `R28_SKILL_SPEC_ANCHOR_MISSING` | feature 写了 skill-spec section, 但文件不存在或 anchor 为空 | 改成真实 skill-spec 文件和 H2 anchor |
| `R28_PRIMARY_OWNER_MISSING` | 完整 features manifest 没有覆盖全部 92 error codes 或 33 events | 给遗漏的 error code/event 指派一个 primary owner feature |
| `R28_RUNTIME_COMPAT_FEATURE_MISSING` | `src/graph_agent/patches/**/*.py` 没有被 runtime compatibility feature 的 `core_paths` 覆盖 | 把 patch 文件放入 `F-runtime-compatibility-patches.core_paths` 或同类 compatibility feature |
| `R28_SOURCE_FILE_UNMAPPED` | source map 漏掉真实 `src/graph_agent/**/*.py` 文件 | 把新增文件加入 `source_file_map.yaml` |
| `R28_DEBT_EXEMPTION_REQUIRED` | `classification: debt` 的 source file 没有 `exemption_id` | 增加有效 exemption id, 或改为 feature/detail 并绑定 feature |
| `R28_FEATURE_FILE_NOT_IN_CORE_PATHS` | source map 说某文件是 feature, 但该文件不在对应 feature 的 `core_paths` | 同步 `features.yaml.core_paths` 或修正 source map feature id |
| `R28_PUBLIC_API_UNMAPPED` | public API contract 中的 symbol 没有出现在 contract map | 给该 symbol 加 `feature_ids` 映射 |
| `R28_VENDOR_ONLY_UNMAPPED` | 6 个 vendor-only/de facto contract symbol 有任意漏项 | 在 public API axis 和 consumer axis 中保留 vendor-only debt entry |
| `R28_CONTRACT_FEATURE_DANGLING` | contract map 引用了不存在的 feature id | 改成 `features.yaml` 中存在的 id, 或新增真实 feature |
| `R28_CUTOVER_OVERLAP_ATTESTATION_MISSING` | cutover fixture 没有证明 24h overlap 和至少 1 个独立 green PR | 在 cutover 记录中补足 overlap 和 green PR 证据 |

Validator 的边界: 它不判断 feature 描述是否"写得好"。语义完整性仍要 reviewer 人审。它负责让漏文件、漏 API、漏 owner、漏测试、漏 CI 的问题不能静默通过。

## §6 CI gate 行为

CI gate 在 `.github/workflows/ci.yml:80-85`:

```yaml
- name: validate round28 contract manifests
  run: |
    uv run python packages/graph-agent/scripts/validate_round28_manifest.py \
      packages/graph-agent/spec/features.yaml \
      packages/graph-agent/spec/source_file_map.yaml \
      packages/graph-agent/spec/contract_map.yaml
```

它运行在 `graph-agent-tests` job 中。前置 step 是 `.github/workflows/ci.yml:72-78` 的 graph-agent pytest:

```yaml
uv run pytest packages/graph-agent/tests \
  --tb=short -q \
  --cov=packages/graph-agent/src/graph_agent \
  --cov-report=xml:coverage-graph-agent.xml \
  --cov-report=term
```

CI 行为是:

1. PR 或 push 触发 workflow。
2. 安装 Python 和依赖。
3. 先跑 graph-agent tests。
4. 再跑 Round 28 validator。
5. 如果 validator exit code 非 0, 该 matrix job 失败, PR 不能视为 green。

这一步的价值是把 manifest 变成合并前硬门, 不是只留在本地脚本里。

## §7 dual-run 守护机制

Round 28 仍保留 dual-run, 因为这是契约迁移, 不是普通文档替换。

### `test_feature_traceability_matrix.py`

这是旧 checklist guard 的升级版。它现在锁住 Round 28 baseline:

- `features.yaml` 必须正好 35 个 feature。
- `feature-compliance-checklist.md` 必须正好 35 个 H3。
- checklist 必须正好 35 个 coverage refs。
- 每个 coverage ref 必须指向真实存在且可 collect 的 pytest nodeid。

这相当于把 Round 27 的 30 strict hard lock 升级为 Round 28 的 35 strict hard lock。

### `test_round28_contract_manifests.py`

这是新 manifest guard。它有 18 个 fixture-based tests, 覆盖 schema shape、vendor-only 六项、non-functional evidence、skill-spec anchor、hash lock rename、source file coverage、contract map 三轴、targeted tests collect、checklist FROZEN、hash drift、exemption schema、validator catch classes、primary owner、source-file reverse mapping、cutover overlap、runtime compatibility patches。

### `test_round28_invariant_guards.py`

这是 5 类机制守护测试:

- prompt template 保留 8 个关键 slot。
- middleware 挂载顺序保持 observation before control。
- tool sandbox 保留写入和逃逸形状的防线。
- blackboard state 保留 inputs、phase outputs、scratch 的明确边界。
- error registry 保留 code、level、stage、doc link 的 metadata shape。

### 不动的 frozen docs

Round 27 frozen docs 仍然不动: `docs/engine/public-api-contract.md` 和 `docs/engine/skill-spec/*.md`。Round 28 frozen doc 是 `docs/engine/feature-compliance-checklist.md`, 它已经由 `features.yaml` 反向生成并带有 FROZEN frontmatter。
