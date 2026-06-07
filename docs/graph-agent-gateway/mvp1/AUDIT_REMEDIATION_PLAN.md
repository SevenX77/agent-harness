---
doc: remediation-plan
status: drafted（审计后续修复执行计划;待 owner 决策 3 个 gate + reviewer plan review 后执行）
binds_design: ./AUDIT_REPORT.md · ./DESIGN_UNITS_INDEX.md · ../../development/design-doc-standards/02-audit-standard.md
generated_on: 2026-06-06
---

# Gateway MVP1 审计修复执行计划

> 来源:独立审计(Claude)findings C1 / I1–I4 / M-a–M-f / Verification Gaps。
> 本计划 = 实施层文档(允许写实施顺序/依赖,不属设计 SSOT)。执行前需:① owner 拍 3 个决策 gate;② reviewer 过一遍 plan review;③ 代码/测试改动按 CCB 委派 Codex,文档改动 Claude 可直接做或委派,改完由 Claude 独立复审(因为 Claude 是本轮 auditor)。

## 决议与转向(2026-06-06,owner 直接拍板;CCB 桥接当时不可用,peer 评审跳过)

- **Gate 1**:边界单元**可复述当前模块需要的逻辑(作引用),不复述实现细节**;不硬卡复述,除非复述错误。→ I2 关闭(现复述指向正确 owner,无事实错误)。
- **Gate 2**:**不在 baseline 上多花时间**,尽快进实施,实施完 baseline 自然改。→ C1 的「12 baseline 补 R4 测试锚点表」**不做**;降级处理:AUDIT_REPORT 不再宣称"audit 完成 / R4 PASS",改标"design-ready, pending implementation"。
- **Gate 3**:2 个外围测试文件**作可行性参考保留**,在设计部分作决策证据引用("能这么做,因为测试过了")。→ I3 关闭(不还原、不单独提交,引为证据)。
- **战略转向**:停止对"实施前设计文档"的重审/重锁;审计 + 锁移到**实施之后**(届时 baseline = 真实代码 + 绿测,验证成本低)。实施前只维护三样:① 决策 + 原话(why);② 外部契约/接口(handoff);③ 已存在代码的 baseline。本计划 §2–§7 的大部分文档活儿据此**搁置**,仅保留可选的 AUDIT_REPORT 诚实性微调。

## 0. 执行者模型(RACI)

- **文档/Markdown/JSON-数据 改动**:Claude(设计者)可直接做,或委派 Codex。
- **Python 测试逻辑 改动**:委派 Codex(executor),遵 TDD(先 RED 再 GREEN)。
- **最终复审(code review 等价物)**:Claude 独立重验(本轮 Claude = auditor,不让 executor 自审)。
- **决策 gate**:owner(用户)拍板;Claude 不替 owner 决定边界/豁免类判断。

## 1. 决策 Gate(阻塞,先拍再动)

### Gate 1 ── I2:`studio-boundary-copilot-http` 边界单元能否复述 `(owner)` 切面?
现状:该单元在 `DESIGN_UNITS_INDEX.md:37` 把 base_url / capability / probe / 6态 / draft / route 契约这些**已被主单元 own** 的切面又标了一次 `(owner)`。
- 选项 a(推荐):改成 `(引)`/边界标记,指向各主 owner,不再标 owner → INDEX「切面×owner」去重扫描无歧义。
- 选项 b:保留复述,但在锁测试补「跨单元同切面只允许一个 owner 模块」断言兜底。
- 选项 c:owner 认定边界单元复述 owner 合规(语义=声明这些内核留 gateway 不归 studio),不改。
→ **需 owner 决定 a/b/c。** 影响 T2.2。

### Gate 2 ── C1:12 个 baseline 的测试锚点差异表怎么补?
现状:12 个 baseline 全部用编号散文写「Baseline / Alignment 差异」,无标准 `|维度|现状|目标|` 表、无「验是否按目标改了」行;R4 是硬规范要求必有此表。
- 选项 a(推荐):全部补标准三列表 + 「验是否按目标改了」行(范例见 `design-doc-standards/example/baseline-example.md:37-44`)。
- 选项 b:owner 显式豁免表格形态,保留散文,但每模块至少补一行「验是否按目标改了」测试锚点。
→ **需 owner 决定 a/b。** 影响 T1.2。

### Gate 3 ── I3:2 个范围外测试文件如何处置?
现状:`test_model_resolver_protocol.py`(加 `predict_context`、删 2 个 GraphAgentHarness 测试)、`test_predict_callable_bridge.py` 已改未提交,AUDIT_REPORT 动作流水未记账。
- 先做调查(T3.1)→ 再由 owner 定:并入本批 / 单独提交 / 还原。
→ **依赖 T3.1 调查结果 + owner 确认。**

## 2. Phase 1 ── Critical:修 R4 + AUDIT_REPORT 自评诚实性(C1)

### T1.1 修 AUDIT_REPORT 的 R0/R4 标签 + 撤回 R4 PASS
- 文件:`AUDIT_REPORT.md`(R0-R8 表 `:85-95`)。
- 动作:R0 标签「scope」→「内容正确(无自相矛盾)」;R4 标签「覆盖」→「职责分清 + 测试锚点」;scope 移到 Q5;R4 结论改为「FAIL/待修:12 baseline 缺测试锚点表」(Gate 2 落地后再回填 PASS)。
- 执行者:Claude(doc)。验收:R0-R8 标签与 `02-audit-standard.md:15-45` 逐条同名;R4 不再谎报 PASS。

### T1.2 给 12 个 baseline 补测试锚点差异表(依赖 Gate 2)
- 文件:`01..11/baseline.md` + `13-x-.../baseline.md`(共 12)。
- 动作:把现有散文「Baseline / Alignment 差异」升级为 `## baseline / alignment 差异(测试锚点)` + `|维度|现状|目标|` 表 + `> 验"是否按目标改了"` 行。维度从现有散文提取,例:
  - 03:base_url(现状 strip/rstrip → 目标 protocol canonicalize)、endpoint_id 生成器(现状只 v3 migration helper → 目标统一 canonical)。
  - 08:UI 态数(现状 5 含 needs_setup → 目标 6 取消 needs_setup 补 historical_ready)、状态写回(现状前端易失 → 目标后端 SSOT)。
  - 10:`RouteChatModelFactory`(现状无 → 目标新建)。11:`ProviderProfile`(现状无 → 目标新建)。
  - 09:调用方式(现状自研 `_call_*`/dict → 目标原生 ChatX)。predict 不在 12 内(单独文档,§3 已有契约表,补「验」行即可)。
- 执行者:Codex(批量,逐模块对照源码)或 Claude;改完 Claude 复审表内「现状」列是否仍对齐源码。
- 验收:`rg -c "^\| *维度 *\|" 12 个 baseline` 全 ≥1;每表下有「验是否按目标改了」行。

## 3. Phase 2 ── Important:锁机制完整性(I1, I2)

### T2.1 修单元锁快照预填弱点(I1)
- 文件:`_design-unit-lock-snapshot.json` (+ 可选 `test_gateway_doc_locks.py`)。
- 动作(主,推荐):drafted 期把 `units` 置空 `[]`,`_meta` 注明「units empty until first owner-approved lock」——与已为空的 `_audited-ready-hashes.json` 同构。这样首次有人把某单元在 INDEX 改 locked 时,`_collect_snapshot_violations` 第二循环(`:378-385`)会强制报「register the new lock」,恢复机器保险。
- 动作(硬化,可选):改 `_collect_snapshot_violations` 以 INDEX 的 locked 状态驱动比对(「INDEX locked ⟹ 快照必须存在且 locked 且字段一致」),关掉「INDEX locked + 快照 drafted」静默放行的缝。配 TDD:加合成测试「INDEX locked + 快照 drafted/缺失 → violation」。
- 执行者:JSON 置空 Claude/Codex;测试逻辑改 Codex(TDD)。
- 验收:`uv run pytest packages/graph-agent-gateway/tests/test_gateway_doc_locks.py -q` 仍 green;新增合成测试覆盖「锁迁移漏更新快照」场景。

### T2.2 处理边界单元 owner 复述(依赖 Gate 1)
- 文件:`DESIGN_UNITS_INDEX.md:37`(+ 选 b 时 `test_gateway_doc_locks.py`、`_design-unit-lock-snapshot.json` 的 owners 字段)。
- 动作:按 Gate 1 结果执行 a(改 `(引)`)/ b(补跨单元去重断言)/ c(不改,记决策原因)。
- 执行者:INDEX 改 Claude;测试断言 Codex。验收:选 a → `studio-boundary-copilot-http` 不再含已被他单元 own 的 `(owner)` 切面;选 b → 锁测试能拦「同切面两 owner」。

## 4. Phase 3 ── Important:范围卫生(I3, I4)

### T3.1 调查并处置 2 个范围外测试文件(配合 Gate 3)
- 动作:`git log -p` / `git blame` 查 `test_model_resolver_protocol.py`、`test_predict_callable_bridge.py` 改动来历;判断是否本轮、是否 102-pass 必需、删 GraphAgentHarness 测试属哪条工作。产出一句话来历 + 建议(并入/单独/还原),交 owner 拍 Gate 3。
- 执行者:Claude(调查)。验收:两文件来历写清;owner 决定其去向。

### T3.2 AUDIT_REPORT 框定加「审计 vs 实现」分界(I4)
- 文件:`AUDIT_REPORT.md`(结论段 `:16-20`)。
- 动作:结论段补一句明确分界:A01–A25 = 审计 + 文档修复;A28–A31 + 2 个 JSON 快照/exemption + INDEX 原子化 = 净新增实现(锁测试 TDD)。
- 执行者:Claude(doc)。验收:报告读者能一眼区分哪部分是审计、哪部分是实现。

## 5. Phase 4 ── Minor + 验证缺口

- **T4.1(M-e)** 修 `README.md:67` 重复链接(`chatx-provider-patterns.md` 写了两遍)→ 留一个。Claude。
- **T4.2(M-d)** 给 `gateway-doc-exemptions.json` 的 `file` 字段补路径遍历校验(与 hash 表 `:90` 同款 `..`/绝对路径拒绝),配 TDD 合成测试。Codex。
- **T4.3(Gap 1)** 跑类型检查:`uv run mypy packages/graph-agent-gateway/tests/test_gateway_doc_locks.py`(或项目 type-check),0 error。Codex/Claude。
- **T4.4(M-a)** 在 AUDIT_REPORT 残余风险里明说「drafted 文档当前无字节级保护,哈希锁唯一活体保险=拦未登记的 FROZEN」。Claude。
- **T4.5(M-b/M-c/M-f,均不阻断)** 记入 `docs/deferred-items.md`:三套 doc-hash-lock 可考虑抽公共;gateway 包测试耦合 repo root;`_canonicalize_design_units` 解析错与锁漂移共用一 test 的报错可分。不本批改。Claude 记账。

## 6. 最终验证(全部完成后)

1. `uv run pytest packages/graph-agent-gateway/tests/test_gateway_doc_locks.py -q` → 全 pass(含新增合成测试)。
2. `uv run pytest packages/graph-agent-gateway/tests -q` → ≥102 passed(+ 新增测试),1 xfailed。
3. `uv run mypy`(gateway tests)→ 0 error。
4. 机械复核重跑:frontmatter / binds_code 符号 / 链接 / 行号 / INDEX 单元 → 0 issue。
5. `rg -c "^\| *维度 *\|"` 12 baseline 全 ≥1(Gate 2=a 时)。
6. Claude 独立复审:R0-R8 标签正名、R4 不再谎报、快照保险恢复、边界单元处置一致、2 个测试文件有归属。
7. `git diff --check` → clean。

## 7. 依赖与排期建议

- 可立即并行(无 gate):T1.1、T3.1、T3.2、T4.1、T4.3、T4.4、T4.5、T2.1(主动作)。
- 等 Gate 2:T1.2。等 Gate 1:T2.2。等 Gate 3(=T3.1+owner):2 个测试文件去向。
- 建议序:拍 3 个 gate → Phase 1/2/3 并行 → Phase 4 → 最终验证 → reviewer plan review 已在前置,此处做 code review 等价的 Claude 复审 → 若 owner 要冻结,逐文件盖章入哈希锁(另立动作,非本计划)。

## 8. 明确不做(范围锁定)

- 不实现 MVP1 target 生产代码(`RouteChatModelFactory`/`ProviderProfile`/resolve skip/ChatX 迁移/predict 移交 engine)——那是独立 TDD 工程任务,不混进本审计修复。
- 不盖 FROZEN / 不把任何单元升 locked——owner 盖章前不动。
- 不顺手重构 gateway 生产代码——审计修复只动文档 + 锁测试治理。
