# Round 30 tasks.md Audit — a3 PM 替身视角

## 整体结论 (3 句话)

tasks.md (241 行 7 章) **总体合格可实施**, 跟 design rev2 lock 一致性 ≈ **95%**, tests-first 顺序合规 (每 PR stage 3 红灯 → stage 4 实施 → stage 5 verify), 黄金原则 verify 真覆盖 (4 contract gate 在 §2-§5 每 PR stage 5 + §7 belt+suspenders 双锁)。

我上轮 audit design 的 7 项修订 (C-1 守门测试清单 / D-1 D-1 lock matrix XML 决定 / D-2 action 版本 verify / D-3 Dependabot enable 绑 step / E-1 PR-1.5 决策门 / E-2 branch protection / E-3 Q7 时机表) **全部继承且映射到 tasks 具体 stage 步骤** ✅。

但有 **6 should-fix + 2 nice-to-have**, 不阻 a1 开始 PR-1 tests-first, 但建议主控 sync a1 修一轮再进 stage 3。

---

## A. tasks vs design 一致性 ✅ 95%

| design 段 | tasks 映射 | verify |
|---|---|---|
| §0 prerequisite | (tasks.md 未单列, 假定继承) | ⚠️ 可补 |
| §1 PR 拆分 + 节奏 | §1 (6 个 PR 含 PR-1.5 + branch protection 时机) | ✅ 一致 |
| §1.1 Branch Protection 时机 | §1 line 41-44 复述 | ✅ 一致 |
| §2.1-§2.3 Codecov 配置 | §2 stage 3-4 | ✅ 一致 |
| §2.4 PR-1.5 决策门 | §2 stage 9 line 82-85 | ⚠️ 命名错位, 见 S-1 |
| §3.1 SonarCloud 前置 | §3 stage 2.5 line 89-93 | ✅ 一致 |
| §3.2-§3.3 lock 决策 | §3 stage 4 line 107 D-1 lock | ✅ 一致 |
| §4.0 Action 版本 verify | §3-§5 stage 4 各 D-2 verify | ✅ 一致 |
| §4.1 CodeQL workflow | §4 stage 3-4 | ✅ 一致 |
| §5.1-§5.3 Scorecard/SBOM/License | §5 stage 3-4 | ✅ 一致 |
| §5.4 Dependabot step 0 | §5 stage 2.5 / step 0 line 165-168 | ⚠️ 失败 gate 缺, 见 S-3 |
| §6 Q7 报分模板 + 时机表 | §2-§5 stage 7 + §6 汇总 | ✅ 一致 |
| §7 影响范围 | (tasks.md 未单列, 假定继承) | ⚠️ 可补 |
| §8 黄金原则 4 gate | §7 line 222-240 | ✅ 一致 |

零真正的偏离 / 偷换概念, 仅几处命名 + 失败措辞 + owner 不全。

## B. tests-first 顺序合规 ✅

每个 PR 都严格 stage 3 (红灯 fail) → stage 4 (src/config 变绿) → stage 5 (audit + 4 gate) → stage 6 (docs) → stage 7 (PR-REPORT) → stage 8 (forward PM) → 立刻起 N+1, **符合 SOP-08 step 3→4→5→6→7→8 + 宪法 10 并行流** ✅.

`stage 2.5` 前置 (PR-2 SonarCloud project / PR-4 Dependabot enable) **不破坏 tests-first**, 因为是 repo-level 外部依赖, 不动代码。

## C. 黄金原则 verify 真覆盖 ✅

- §2-§5 每个 PR stage 5 line 66/113/147/188 都明确 "4 个 contract gate 全绿"
- §7 line 222-240 额外明确 4 个 test 路径 + 4 个 pytest 跑法 + 6 维度不漂 (belt+suspenders 双锁)
- 4 路径我已物理 verify 存在 (上轮 audit design 时跑过 `ls packages/graph-agent/tests/`)

## D. PR-2/PR-4 前置 gate 真锁死 — PR-2 ✅ / PR-4 ⚠️

**PR-2 stage 2.5 (§3 line 89-93)** ✅ 真锁死:
- 4 项确认 + "若未创建, escalate PM, **不硬推 PR-2 src 实施**" — 失败 gate 措辞清晰

**PR-4 stage 2.5 / step 0 (§5 line 165-168)** ⚠️ **缺失败 gate**:
- 写了"主控跑 gh api enable + verify 204 returns + 必须在 PR-4 ship 前完成"
- **但没说**"若 enable fail / gh 未认证 / 返回 4xx, escalate PM, 不硬推 PR-4 src 实施"
- 跟 PR-2 stage 2.5 失败措辞不对称 = 风险口

## E. branch protection scope — design ↔ tasks 一致 ✅

design §1.1 line 22-29 + tasks §1 line 41-44 + tasks §4 stage 4 line 142 + §5 stage 4 line 183 + §4 stage 7 line 157 + §5 stage 7 line 202 — **6 处都一致**: PR-3/PR-4 暂不加入 branch protection required list, 后续 PR-5 候选评估后再加, PR-REPORT 透明给 PM. **没漏 scope** ✅。

---

## F. 缺陷分级

### must-fix (0 项)

无。tasks.md 不阻 a1 开始 stage 3 tests-first 准备。

### should-fix (6 项, 建议 a1 修一轮再进 stage 3)

- **S-1** §2 stage 9 line 82-85 "PR-1.5 决策门" 命名跟 SOP-08 step 9 (PM ack merge) 概念错位。
  - SOP-08 step 9 = PM ack merge, 是 PR-1 自身的 ack step
  - tasks 把 PR-1.5 决策门塞进 stage 9 = 混淆 PR-1 ack vs 后续 PR 决策
  - **修法**: 改名 "**Post-stage 8 PR-1.5 决策门 (内部, 不抛 PM)**" 或单独列一节 §2.x, 避开"stage 9" 标号

- **S-2** §3 stage 3 line 96 / §4 stage 3 line 132 / §5 stage 3 line 171 没给具体 test 文件名 (vs §2 stage 3 line 49 给了 `test_round30_pr1_codecov_config.py`)。
  - 不一致 → a1 实施时要二次决定文件名 → 命名漂移风险
  - **修法**: 补 `test_round30_pr2_sonarcloud_config.py` / `test_round30_pr3_codeql_config.py` / `test_round30_pr4_scorecard_config.py` 三个文件名

- **S-3** §5 stage 2.5 / step 0 缺失败 gate (vs PR-2 stage 2.5 有 "escalate PM 不硬推" 措辞)
  - **修法**: 加 "若 `gh api PUT` 返回 4xx / gh 未认证 / verify 204 失败, escalate PM, 不硬推 PR-4 src 实施"

- **S-4** Stage 6 docs 同步 + §6 4 PR 汇总报告没标 owner
  - 其他 stage 都标 (如 stage 3 "a1 写 a2 audit", stage 7 "a1 主笔 logic-explained 风格")
  - stage 6 line 70/117/151/194 仅说"加段", 没说谁主笔
  - §6 汇总报告也没标 owner
  - **修法**: stage 6 标 "主控落盘 + a1 行文核对 + a3 audit"; §6 标 "a1 主笔 logic-explained 风格 + a2 honesty audit + a3 audit"

- **S-5** §2 stage 9 line 85 "主控亲跑 Codecov dashboard 拿数" 时机歧义
  - PR-1 stage 8 forward PM 后立即 stage 9 — 此时 PR-1 **还没 merge main**, dashboard 只有 PR branch 的 coverage (PR comment-bot 给的 PR 增量数), 不是 main baseline
  - 选 (a) 等 PR-1 merge 后再 stage 9 → 违反宪法 10 并行流; 选 (b) 用 PR branch 数 → 决策依据是 PR 增量而非 main 全量
  - **修法**: 明确 "stage 9 决策依据 = PR-1 branch 全量 coverage (Codecov PR comment 给的 `coverage of HEAD` 数), 不等 PR-1 merge"

- **S-6** PR-5 候选 / round-31 scope 边界没明确
  - design §1.1 + §6 line 332 + tasks §1 line 44 + §6 line 218 "明确下个 round 推进项" — 4 处提及 PR-5 但都没说**何时启动 / 归 round-30 还是 round-31**
  - **修法**: tasks.md §6 line 218 末尾或 §1 line 44 加 "**PR-5 候选默认 defer round-31, 不在 round-30 scope**", 防 a1/主控将来在 round-30 范围里偷偷加 PR-5

### nice-to-have (2 项)

- **N-1** §2 stage 3 line 49 `test_round30_pr1_codecov_config.py` 放 `packages/graph-agent/tests/` — 该 test 检查仓库根的 `codecov.yml` + `ci.yml`, 跟 graph-agent 业务无关。本仓现在仅 3 处 tests 目录 (graph-agent/tests + studio backend/tests + studio tests-e2e), 没 root tests/, 所以放 graph-agent/tests **是 monorepo 默认**, 可接受。可在 tasks.md 注一行说明, 避免后续 reviewer 困惑。

- **N-2** D-2 action 版本 verify (§3 stage 4 line 102 / §4 stage 4 line 139 / §5 stage 4 line 178) 都放 stage 4。design §4.0 line 200 说"实施 PR 开始前必须先确认 action 版本" — stage 4 是实施开始, OK. 但**更早一点放 stage 3 (写 tests-first 时就验证 action 版本**) 也合理, 避免 stage 3 测试 assert action@v4 但 stage 4 verify 后发现要回退 v3 → tests 立刻要改。可考虑 stage 3 内做 verify, 再 lock 进 test 断言。

---

## G. 整体建议

tasks.md **可推进 stage 3 准备**, 但建议主控 sync a1 修 S-1 ~ S-6 这 6 项 (10-15 分钟工作量), 然后进 stage 3 tests-first 红灯阶段。S-1 (stage 9 命名错位) 和 S-3 (PR-4 失败 gate) 优先修, 避免 a1 实施时被概念漂误导。

---

## 文件清单 + grep 命令

### Read
1. `/tmp/round30-a3-audit-tasks.md` (本次 brief)
2. `.kiro/specs/engine-mvp0-rebuild-v030/round-30-p1p2-onboard/tasks.md` (本次 audit 目标, 全文 241 行 7 章)
3. `.kiro/specs/engine-mvp0-rebuild-v030/round-30-p1p2-onboard/design.md` (rev2 lock, 全文 374 行 8 章 + §1.1 子节, 完整对照 cross-reference)
4. (上轮 audit design 已 read: research.md / 00-PROGRESS-STATUS.md / .github/dependabot.yml / scripts/ 等, 本次 rely on 上轮上下文不重读)

### Bash
- `ls .kiro/specs/engine-mvp0-rebuild-v030/round-30-p1p2-onboard/` → verify 4 文件全 landed: `design.md` + `research.md` + `tasks.md` + `audit-a3-design.md` (上轮 audit 也落盘了, ✅ a3 audit 流程闭环)

### 没读 (主动声明)
- `audit-a3-design.md` 全文 (我上轮 audit 自产, 直接复用记忆 + design rev2 已修 7 项已 verify, 不重读)
- a1 / a2 对 tasks.md 的 audit 原文 (没收到, 我作为 PM 替身独立 audit, 不替 a1 工程视角 verify)
- 4 contract gate test 文件物理存在 (上轮 audit 已物理 verify 过 `packages/graph-agent/tests/test_public_api_contract.py` 等 4 路径存在, 本轮 rely)