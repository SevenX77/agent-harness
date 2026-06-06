# Studio MVP1 锁语义决策:owner-scoped 三态(codex 审计后)

**日期**: 2026-06-05 · **状态**: 已决,Phase A 实施中 · **不回滚 63 档 FROZEN**

## 背景
studio MVP1 把 63 份设计文档 FROZEN + 哈希锁(commit `924ff4c`)后,经 codex 对抗式审计(prompt 见 [`studio-mvp1-frozen-audit-prompt.md`](./studio-mvp1-frozen-audit-prompt.md)),**机械层全 PASS**,但报两个**治理层 FAIL**:
- **FAIL 1**:INDEX 把 22 单元全标 `locked`,但其中 **10 个**依赖 engine/gateway 的 `(引)` 外部切面,而那些外部文档全是 `drafted`、无哈希锁。按标准"单元 `locked` = 各切面锁住",这 10 个是**过度声明(假信心)**。
- **FAIL 2**:登记锁态的 `DESIGN_UNITS_INDEX.md` 自身**不入哈希锁**(活注册表),锁态(谁 locked)只是文字声明、无机器强制 —— 违反 M8(状态标签没机器层不算锁)。

## 三方收敛(Claude + Gemini + codex)
独立咨询 Gemini(prompt 见 [`studio-mvp1-locksemantics-gemini-prompt.md`](./studio-mvp1-locksemantics-gemini-prompt.md))与 codex,三方一致:
1. **不回滚** 63 档 FROZEN(机械层干净)。
2. **owner-scoped 锁**:studio 锁自己拥有的切面即可,**不被 engine/gateway 冻结节奏卡死**(否则 studio 永远锁不了 = 过度耦合,且诱导造假)。
3. "22/22 locked" 必须**重新措辞**为诚实表述。
4. 外部 `(引)` 防漂移靠**结构化台账 + pin SHA**(非 markdown 文字)。
5. 活注册表的锁态靠**锁态快照(单独哈希)+ 快照测试**保护(非冻整个文件)。codex 补强:纯结构化不变量测试不够(挡不住"把 locked owner 悄悄换成另一个 owner"),必须有**快照基线**对比。

## 决策:owner-scoped 三态模型
单一 `unit-lock` 拆三维(权威定义写进 [`../development/design-doc-standards/01-writing-standard.md`](../development/design-doc-standards/01-writing-standard.md) §1.6):
- **`owned-lock`** ∈ {drafted, locked}:studio **自有/消费/适配/落点**切面是否审过 + 盖章 + 落在已 FROZEN 哈希档里。
- **`external-binding`** ∈ {none, floating-draft, pinned-draft, frozen-pinned, stale}:对外部 `(引)` 切面(owner=`engine:*`/`gateway:*`)的绑定状态。
- **`integration-lock`**(派生) ∈ {unverified, locked}:`locked` ⟺ `owned-lock=locked` 且 `external-binding ∈ {none, frozen-pinned}`。

**现状诚实表述**:22/22 `owned-lock=locked`;**12 个纯 studio 单元** `external-binding=none`、`integration-lock=locked`;**10 个单元** `external-binding=floating-draft`、`integration-lock=unverified`(踩在 engine/gateway 还在 drafted 的契约上)。

10 个外部依赖单元:`subgraph-path-inline-drilldown`、`predict-execution`、`run-execution-node-status`、`golden-per-agent-node`、`phase-field-whitelist`、`debug-resume-checkpoint`、`trace-dot-blackboard`、`settings-six-state-provider-health`、`model-group-role-materialization`、`copilot-sdk-test-parity`。

## 实施(分两期)
**Phase A(现在):**
1. `01-writing-standard.md` §1.6:owner-scoped 三态语义。(Claude)
2. `DESIGN_UNITS_INDEX.md`:单列锁态 → 三列;诚实措辞;拆 `/` 合并切面 + 显式 `(owner/消费/引/落点)` 标记(⚠️3)。(Claude)
3. `_design-unit-lock-snapshot.json`(锁态快照,入哈希锁)+ 快照测试(防静默回退 / 换 owner / 删行;新单元默认只能 drafted;locked 单元改 owner/spans 须更新快照或 exemption)。(codex,prompt 见 [`studio-mvp1-locksnapshot-prompt.md`](./studio-mvp1-locksnapshot-prompt.md))

**Phase B(推迟,记 `docs/deferred-items.md`):**
4. **外部引用哈希台账**(pin 每个 `(引)` 的外部 doc SHA + commit + expected_status)。**推迟理由**:engine(36 档)/gateway 现全 `drafted`、天天改,现在 pin = 钉移动靶 = 持续误报 = 逼人逃避写文档(Gemini 警告的过度行政化)。等外部系统冻结 / 稳定再逐个 `floating-draft`→`pinned-draft`→`frozen-pinned`。当前用 `external-binding=floating-draft` 诚实标注。
5. (更远期)engine/gateway 输出 `contract-manifest.json`(只 hash 契约字段 / 错误码 / API 签名,不 hash 整篇 Markdown)+ studio 侧可执行契约测试。

## 不回滚声明
63 档 FROZEN(commit `924ff4c`)保持不动。本次修复是**纯增量**:改标准语义 + INDEX 重标 + 加快照机器锁。

## 实施进展(2026-06-06)
- **commit `8906a29`**:标准 §1.6 owner-scoped 三态 + INDEX 三态锁列 + 诚实措辞 + 拆切面;决策 / 咨询 prompt 存档。(**FAIL 1 闭合**)
- **commit `59f2fb2`**:INDEX spans 规范化为 codex owner 解析格式(**⚠️3 闭合**,81 条目 parser 自检通过)。
- **commit `80fd930`**:codex 建快照测试 `apps/studio/backend/tests/test_design_unit_lock_snapshot.py` + `_design-unit-lock-snapshot.json`(入哈希底账 count 64);codex M4 ownership 复核 → Claude 据 baseline 修正 3 个 gateway 簇单元(`gateway`=消费边界 owner、`llm-copilot-http-api`=HTTP 壳 owner,`settings-six-state` owners 不再为空)。(**FAIL 2 闭合**)
- **M4 对抗验证**:改 INDEX owner→快照测试 FAIL;篡改快照→哈希测试 FAIL;还原→5 passed。
- **待**:codex 最终 M4 复核 ownership 修正(prompt 见 [`studio-mvp1-locksnapshot-review-prompt.md`](./studio-mvp1-locksnapshot-review-prompt.md));Phase B(外部 pin 台账)仍推迟至 engine/gateway 稳定。
