# Codex 任务:建 studio 设计单元锁态快照 + 快照测试(FAIL 2 机器牙)

## 背景
studio 设计单元索引 `docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 登记 22 个横切设计单元的锁态。审计发现(见 `docs/design/studio-mvp1-lock-semantics-decision.md`):INDEX 是"活注册表"、**不入哈希锁**,所以"哪些单元 locked"这个状态没有机器强制、只是文字声明(违反 M8:状态标签没机器层不算锁)。

锁语义已改为 **owner-scoped 三态**(权威定义见 `docs/development/design-doc-standards/01-writing-standard.md` §1.6):
- `owned-lock ∈ {drafted, locked}` —— studio 自有切面是否锁住
- `external-binding ∈ {none, floating-draft, pinned-draft, frozen-pinned, stale}` —— 对外部 `(引)` 切面的绑定
- `integration-lock ∈ {unverified, locked}`(派生:owned-lock=locked 且 external∈{none,frozen-pinned} 才 locked)

INDEX 表当前 7 列:`| 单元 | 源 workflow | spans | binds_code | owned-lock | external-binding | integration-lock |`。现状:22 行 owned-lock=locked;12 个 integration-lock=locked、external-binding=none;10 个 external-binding=floating-draft、integration-lock=unverified。

## 要建的(参照现成 `apps/studio/backend/tests/test_doc_hash_lock.py` 的位置/模式)
1. **锁态快照** `docs/studio/mvp1/_design-unit-lock-snapshot.json`:把当前 INDEX 表里**每个单元**规范化成 canonical 记录 —— unit id、owned-lock、external-binding、integration-lock、owners(从 spans 提取的 owner 模块集)、external refs(`(引)` 的 engine/gateway 切面)。这是锁态基线。
2. **快照测试**(pytest,放 `apps/studio/backend/tests/`):
   - 解析 `DESIGN_UNITS_INDEX.md` 单元表 → 生成 canonical 形态;
   - 与快照比对,规则:
     - 快照里 `owned-lock=locked` 的单元,在 INDEX 必须**仍存在、仍 locked、owners/三态一致** —— 否则 FAIL(静默回退 / 换 owner / 删行)。
     - INDEX 里 `owned-lock=locked` 但快照没有的单元 → FAIL(新锁必须先刻意登记快照)。
     - INDEX 新增 `owned-lock=drafted` 的单元(不在快照)→ **允许**(活注册表可长新单元)。
     - 失败信息可操作(指明哪个单元怎么变了 + 怎么改:更新快照 / 走 exemption)。
   - 复用现有 exemption 机制(`apps/studio/backend/tests/studio-doc-exemptions.yaml`)或同款。
3. **快照防篡改**:`_design-unit-lock-snapshot.json` 必须 byte 级保护(否则有人同时改 INDEX + 快照就绕过)。建议加进 `docs/studio/mvp1/_audited-ready-hashes.json`(现成哈希锁底账,`test_doc_hash_lock.py` 会校验)——改快照须 owner 批准更新底账。你定最干净的接法。
4. 接入默认 pytest 收集。

## ⚠️ 需要你先反馈的(owner 解析格式 ⚠️3)
INDEX 的 spans 已拆成原子 `切面→\`模块\`(角色)` 条目(角色∈owner/消费/引/落点),`/` 合并已全消除。但**部分 studio 自有切面条目还没显式标 `(owner)`/`(消费)`**(如 `inline 展开/下钻/面包屑→\`canvas\``、`触发 UI→\`center-action-bar\``、`状态源→\`state-engine\``)。请你:
- 告诉我你的 owner 解析器需要的**确切格式**(每个 owner 切面都必须标 `(owner)`?未标的默认当什么?)。
- 我据此把 INDEX 里没标的条目补全 `(owner)/(消费)/(引)/(落点)`,让 owner 唯一性 + owners 集能被你的解析器干净读出。
- **即:owner 解析格式你定,INDEX 标记我来补(避免我瞎标 ownership);你不要改 INDEX 设计内容。**

## 铁律
- **不改那 63 份 FROZEN 文档、不改 `_audited-ready-hashes.json` 里现有 63 个 hash**(只可新增 snapshot 条目)。
- 不改 INDEX 的设计内容 / ownership(那是 studio 设计文档,Claude 域);你只建 snapshot + test + 反馈 owner 解析格式约定。
- 失败信息必须可操作。

## 交付
snapshot 文件 + 测试 +(如需)exemption / 底账接法;报告:测试路径、怎么跑、当前对 INDEX 是否全绿;以及你需要的 owner 解析格式约定(我据此补 INDEX 标记)。
