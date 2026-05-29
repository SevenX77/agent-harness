# Round 28 Design — Feature Checklist Redesign

## §0 Charter / 黄金原则 Binding
本设计的最高优先级宪章是绝对执行 PM 于 2026-05-27 下达的不可动摇的黄金原则：“**做任何架构优化也好代码优化也好，功能一个都不能少！API 接口也是，说好开放哪些接口什么功能一个都不能少，黄金原则不可动摇... 不管改什么都必须最终对齐回去，除非我说要调整这几个文档**”。任何重构 PR 必须且只能以此原则为基准。在合并前，所有的功能特性、公开 API 符号与既定契约文档必须全量对齐；修改契约必须经 PM 显式书面批准。

由于“功能一个不少”无法单纯由机器自证，本设计的合规防线降级为**双轨制**，缺一不可：
1. **机器审计层 (CI 硬门)**：Catch class 包括 manifest 结构错误 / 路径锚点失效 / 65 符号 drift / 源文件未 mapped / hash 漂移 / FROZEN 改字等硬性指标破坏。
2. **PM/Reviewer 人审层**：Catch class 包括 新加特性时未列入 `features.yaml` / consumer-file 反推遗漏 / 业务特性描述模糊但通过了 schema 校验等机器无法捕获的语义丢失。CI 全绿不代表可以放松 Reviewer 的人工审查。

*(澄清注：md_to_json 自愈链路当前在 `tools/md_to_json.py:485-575`，与 `cognitive/md2json.py` / `md_patch.py` 共存，属已 hard化特性，无需作为债务恢复。)*

## §1 Framing (双层 ⊗ 跨层防退化矩阵 F3)
为破除基于物理代码目录罗列凑数的反模式，本文档确立 **F3（双层 ⊗ 跨层防退化矩阵）**框架作为合规清单的基础范式：

| 层次 | 构成主体 | 目的 / 行动要求 |
| ---- | ---- | ---- |
| **顶层 (业务可见层)** | 端到端业务特性 (Business Capabilities) | 锚定下游消费者真实可感知的系统能力，每一项是一句清晰的系统行为描述。 |
| **底层 (源码反向层)** | 源码文件全量反向覆盖审计 | 强制所有源码必须明确归类映射，消灭“无人认领”的暗逻辑和死代码。 |
| **跨层矩阵 (缝合防守)** | 每条业务特性的横向防守切面表 | 将分散在多处（代码、事件、异常、非功能约束）的防线聚合成 Reviewer 的“重构排雷地图”。 |

## §2 业务特性枚举方法
绝不允许凭个人记忆或凑数列举业务特性。所有的业务特性生成器只保留以下三处“契约锁”：
1. **公开 API 契约（65 个稳定符号）**：参考 `public-api-contract.md` 推导其背后的端到端业务特性。
2. **skill-spec 章节**：引擎直接对外的行为契约。
3. **Studio Copilot consumer-file**：明确来源为 `docs/engine/public-api-contract.md` 中每个符号下记录的 `Consumer files:` 字段。

*注：错误码与事件流仅作为“切面字段引用”，不作为业务特性的生成来源。*

## §3 源码反向覆盖审计
对 `packages/graph-agent/src/graph_agent/` 下的所有源文件（动态对账：文件总数及列表必须等于 CI 跑 `find packages/graph-agent/src/graph_agent -name '*.py'` 的实际输出，含或不含 examples 由配置决定）执行强制的**源码反向映射审计**。
每一个活动模块必须在测试校验体系中被判定为以下三类之一：
- **语义功能 (Feature)**：必须至少被 `features.yaml` 中一条业务特性的 `core_paths` 维度引用。CI 跑反向 cross-check，若未被任何核心代码路径引用，视同 Unclassified 失败。
- **实现细节 (Implementation Detail)**：**必须显式声明所属业务特性 ID**。没指向 = Unclassified = 测试 fail。
- **死债 (Dead Debt)**：**必须指向 exemption ID**（引用 round-27 `contract-exemptions.yaml` 机制），不能空标。

## §4 跨层防守切面定义
每条业务特性包含 5 个维度的**跨层防守切面图**：
- **核心代码路径 (Core File Paths & Anchors)**：实现该特性的具体跨层代码路径及关键行锚点。
- **绑定错误码 (Error Codes)**：细分为 Primary 与 Secondary 数组（引自 `11-error-code-spec.md`）。每个错误码至少有且仅有一个 Primary owner 特性。
- **抛出事件 (Observability Events)**：细分为 Primary 与 Secondary 数组（引自 `callbacks/events.py`）。每个事件有且仅有一个 Primary owner 特性。
- **非功能性契约 (Non-Functional Contracts)**：Token 配额、并发、严格状态隔离等约束。
- **守护测试 (Targeted Tests)**：`list[str]`（至少 1 个），不强制单数入口，精细化指向该特性的正确性断言。

## §5 守护测试设计
守护测试（Targeted Invariant Tests）必须从泛 E2E（Golden Data E2E）体系中剥离，形成专注的机制断言网：
- **职责划分**：Golden Data E2E 聚焦于宏观黑盒等价性；守护测试通过特权注入或白盒断言覆盖隐秘的底层业务约定。
- **覆盖领域**：LLM 占位符装配边界、Middleware 挂载与触发顺序、工具沙箱权限域隔离、黑板并发竞争、异常码死机恢复机制等。

## §6 文档冻结机制
复用 round-27 已有治理机制：
1. 新 `feature-compliance-checklist` 加进 `.github/CODEOWNERS`，强绑 `@SevenX77`。
2. 复用 YAML `status: FROZEN` frontmatter 格式锁定契约文档。
3. 扩展为 contract hash lock (新建或泛化 `test_contract_hash_lock.py`)，覆盖 `skill-spec/*` + `feature-compliance-checklist` + `public-api-contract`。
4. **删除业务特性的唯一通道**：走现有的 `contract-exemptions.yaml`，即 PR# + 理由 + 替代特性指向。
5. **外部治理前置条件**：branch protection required reviewers = `@SevenX77` 属于 GitHub settings 配置，不在 repo 文件内，CI 不证明此项，但为流程刚需。

## §7 迁移路径与 Deprecation 通道
1. **Cutover 期 CI 双跑 AND-gate**：新机制接入后，至少在一个 PR cycle 期间 CI 跑新旧联合检查（新旧两测试都必须 pass）。重叠期安全后才下架旧 `test_feature_traceability_matrix.py` 和旧清单。
2. **同 PR 修改免检条件**：新通道启用同 PR 必须同步把 `test_public_api_contract.py::test_exemptions_yaml_currently_empty_in_pr1` 改成 'shape valid' 校验，不再强断言空。
3. **Deprecation 通道**：业务特性删除只能通过 `contract-exemptions.yaml`，必含 (a) PM 显式批准 (b) PR#+理由+替代 (c) 写入 exemption，无例外。
4. **Rollback 计划**：cutover PR 合并后 24h 监控窗口内，若发现关键特性遗漏，**revert PR 必经 PM 显式批准**，不走 exemption 也不走任何 auto-approval 通道。

## §8 验收标准 (Acceptance Criteria)
我们的验收转为多维度的工程闭环判定（侯选生成 + PM 确认 + CI 校验三件套）：
1. **代码归类满覆盖**：所有源文件（通过 `find` 命令动态对账）100% 映射（Feature/Detail/Debt），不允许 Unclassified。
2. **契约锁倒推齐全**：65 个公开符号必须 100% 回溯关联到业务特性。
3. **矩阵防守面完整**：每项特性具备 5 个横向切面，所有 Error Code 和 Event 均被 Primary Owner 认领。
4. **Cutover 显式映射**：cutover PR 必须显式列出旧 30 项每一项的去向（保留 / 合并 / 拆分 / 降级 + exemption），并附带人工确认。

## §9 工程化落地实施：3 张机器可校验表
合规清单实施被拆分成 3 张机器可校验的 YAML 结构表，要求严格的 Schema：

1. **`features.yaml`**：
   - `id`: 正则 `^F-[a-z0-9-]+$`
   - `sources`: 多选，enum `[public-api, skill-spec, consumer-file]`，至少 1 个
   - `public_api_symbols`: 必须来自 65 清单
   - `skill_spec_sections`: 文件路径 + heading anchor (e.g., `docs/engine/skill-spec/05-finish-task-spec.md#workflow-finish-mode`)
   - `consumer_files`: 必须来自 public-api-contract.md 中记录的 Consumer files
   - `error_codes_primary` / `error_codes_secondary`
   - `events_primary` / `events_secondary`
   - `targeted_tests`: `list[str]`，pytest nodeid (`file::test_func`)，至少 1 个
   - `non_functional_contracts`: schema `{id, type: enum, description, evidence}` (type: `token-quota`, `concurrency`, `timeout`, `state-isolation` 等)，CI 校验非空 + type 在 enum 内

2. **`source_file_map.yaml`**：
   - `path`: 必须等于 CI 跑 `find` 的实际输出（动态对账，拒绝硬编码总数）
   - `classification`: enum `[feature, detail, debt]`
   - `feature_ids`: `list` (允许多个)；Detail 必填非空；Feature 类必填且必须被 `features.yaml` 对应特性的 `core_paths` 引用
   - `exemption_id`: Debt 必填，新增稳定 key 加入 `contract-exemptions.yaml` schema 扩展

3. **`contract_map.yaml`**：
   - public API axis: 65 符号
   - skill-spec axis: 14 文件 + 每文件 H2 章节 ID (不是任意 H3)
   - consumer-file axis: 来自 public-api-contract.md 中的 Consumer files 字段
   - 约束：每轴每条目必须反推映射到至少一条业务特性 (features.yaml) ID