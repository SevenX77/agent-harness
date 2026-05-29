# Round 30 design.md Audit — a3 PM 替身视角

## 结论 (3 句话)

design 总体**合格可实施**: 跟 research rev3 一致, 跟 PM 5-29 拍板对齐, charter sync 已物理 verify (`00-PROGRESS-STATUS.md:244` 真有 PM 拍定全部解锁段), 黄金原则 6 维度声明不动且 grep 实证 design 内零 src/** 真改动。

但有 **3 should-fix 漏 scope + 3 工程隐患 + 4 nice-to-have**。建议主控派 a1 工程视角 verify 一次再进 tests-first 阶段。

---

## A. 跟 research rev3 一致性 ✅

design vs research rev3 **无 drift**, 工程细节更具体 (yaml / 路径 / cron 都写到位)。仅 1 处时间点差异:
- research rev3 Q4 line 27 "charter line 245 仍待 sync" — research 写时 sync 未完成
- design §0 line 5 "主控已同步 charter" — design 写时 sync 已完成
- 我物理 verify charter `00-PROGRESS-STATUS.md:244` 真有 "**B 类前置 (2026-05-29 PM 拍定全部解锁)**" 段, **CODECOV_TOKEN / SONAR_TOKEN / PUBLIC / publish_results / Dependabot enable** 五项全列, ✅ **真 sync**, 不是 hallucinate

## B. 跟 PM 5-29 拍板一致性 ✅

design §0 五项前置全对齐 charter. 1 个小问题:

- **B-1 nice-to-have**: design §0 line 7 "a1 本地 `gh` 未登录, 补充只读验证 `git ls-remote https://github.com/SevenX77/agent-harness.git HEAD` 可读" — git ls-remote 公开仓可匿名读, 但**私有仓 + token cached 也能读**, 不构成 visibility=PUBLIC 的强证据。以 charter 为权威 (主控已 `gh repo edit --visibility public` 执行) 即可, design 这句"只读验证"措辞应改"辅助验证, 以主控 charter sync 时 gh repo edit 为权威"。

## C. 黄金原则 verify 节覆盖度 ⚠️ should-fix

design §8 line 317-325 声明 6 维度不动 + 结尾"PR-1/2/3/4 合并前仍需跑对应 contract guard", 但**没显式列守门测试名字**, 对比 round-29 design §4 明确列 4 个 test 文件路径 (`test_public_api_contract.py` / `test_contract_hash_lock.py` / `test_round28_contract_manifests.py` / `test_round28_invariant_guards.py`)。

**C-1 should-fix**: §8 应补具体守门测试清单, 否则 a1 实施 PR-1/2/3/4 时 "对应 contract guard" 含糊, 可能漏跑。建议在 §8 末尾加:

> PR-1/2/3/4 合并前每个 PR 必须跑 4 个 contract gate:
> - `tests/test_public_api_contract.py`
> - `tests/test_contract_hash_lock.py`
> - `tests/test_round28_contract_manifests.py`
> - `tests/test_round28_invariant_guards.py`

✅ **src 改动暗藏 verify**: grep `src/|packages/graph-agent/src|apps/studio/backend/app` 命中 5 处, 4 处是 codecov flag/sonar.sources/边界声明, 1 处是 §7 line 311 边界声明 `src/**` 不动, **零暗藏 src 真改动**, 合规。

## D. 4 PR 拆分合理性

PR 顺序 (Codecov→Sonar→CodeQL→Scorecard) 合理, 依赖正确 (Sonar 依赖 Codecov 的 XML artifact)。

**3 工程隐患** (should-fix-in-impl):

- **D-1 should-fix**: §3.2 line 124-130 graph-agent matrix 上传 artifact 名带 `py${{ matrix.python-version }}` 区分, 但**内部文件路径 `coverage-graph-agent.xml` 同名**。§3.2 line 174 自己 acknowledge "若 Sonar 必须看三版本, 应在上传前重命名为 `coverage-graph-agent-<py>.xml`" — **但 design 没 lock 这个决定**, 留给 a1 实施时撞坑。建议 design 现在就 lock: PR-2 Sonar **看一份 (任选 3.11 版)** 或 **看三版本 (上传前重命名)**, 二选一明确。

- **D-2 should-verify**: §4.1 line 204/210 + §5.1 line 247 用 `github/codeql-action@v4`, 跟 research rev3 line 20 一致。但 github/codeql-action 历史稳定 tag 一般是 v3, v4 是否真 GA 我没法 WebFetch verify。**应让 a1 工程视角 curl https://github.com/github/codeql-action/releases 确认 v4 是 latest stable, 还是要回退 v3**。同理 §2.1 codecov-action@v5 也应 a1 verify。

- **D-3 should-fix**: §5.4 line 282-284 Dependabot security updates "应通过 GitHub repo setting/API 启用 ... 主控后续可用 `gh api` ... 实际 endpoint/权限需在 PR-4 前 ... 确认后再执行" — 把执行项写成 TBD, **没绑进任何 PR step**。应明确: **PR-4 step 4 (src 实施前)** 主控用 `gh api -X PUT /repos/SevenX77/agent-harness/automated-security-fixes` enable, 否则 PR-4 ship 后 Scorecard 跑出来 Dependabot-Updates 分项仍低, Q7 报分撞 "为何 enable 了分还低" 解释成本。

## E. 漏 scope (design 该写但没写)

- **E-1 should-fix — PR-1.5 决策门**: design §1 表 PR-1.5 写"(可选), 跑出基线后评估", 但**评估阈值是什么**? 建议明确:
  - 基线 ≥ 78% → 跳过 PR-1.5, 直接 PR-2
  - 基线 < 78% → 强制 PR-1.5
  - 否则会变成 PR-1 ship 后"PR-1.5 谁拍"的二次 escalation

- **E-2 should-fix — PR-3/4 status check 进 branch protection?**: design §1 PR-3/4 加新 workflow `codeql.yml` / `scorecard.yml`, 这两个新 workflow 的 status check 要不要加进 main 分支 branch protection require list? 不加 = 新工作流接了但不强制通过 = 跟宪法 5 "门要真" 冲突。design 应说明 PR-3/4 ship 时是否同步更新 branch protection (或显式声明 report-only 阶段暂不 require)。

- **E-3 should-fix — Q7 报分时机**: §6 Q7 模板对的, 但**没绑具体 PR 时机**。建议加表:
  | PR | PR-REPORT 必含基线项 |
  |---|---|
  | PR-1 ship | Codecov 4 flags 首次基线 |
  | PR-2 ship | SonarCloud 4 轴首次基线 + (若 PR-1.5 已 ship) Codecov 提升后数 |
  | PR-3 ship | CodeQL 高/中/低首次基线 |
  | PR-4 ship | Scorecard X/10 + SBOM artifact 路径 + license 风险 + Dependabot 状态 |
  另: 4 PR 全 ship 后**是否 round-30 汇总报分**, design 应明确。

- **E-4 nice-to-have — PR-2 sonar-scan job needs 失败兜底**: §3.2 `needs: [quality-gates, graph-agent-tests]` 串联, 任一 needs fail 则 sonar-scan 跳过 → Sonar 仪表盘断流。可选加 `if: always()` 让 sonar 用 partial XML 继续, 或显式声明 "needs fail = sonar 跳过, 接受断流"。

- **E-5 nice-to-have — branch protection / repo settings 改动算 [BREAKING] 否?**: PR-4 enable Dependabot security updates 可能要修 branch protection (allow Dependabot bypass), 这是 repo settings 不是文件改动。design §7 / §8 应说明: "repo settings 操作不算源码 [BREAKING], 但需在 PR-REPORT 留迹让 PM 知晓", 否则违反 SOP-06 spec 保守原则的精神 (PM 看不到的改动等于没说)。

## F. nice-to-have 工程细节

- **F-1**: §5.3 line 274 `pip-licenses --fail-on="GPL;AGPL"` 实际 CLI 语法 a1 应 verify (是空格 / 分号 / 等号 等)。
- **F-2**: §2.1 codecov-action@v5 `files:` 字段语法跟 v4 是否兼容, a1 应 verify。
- **F-3**: §6 Q7 谁负责读 dashboard 报基线 (主控 / a1) 没明确, 流程角色不清。

## 整体建议

design **可进 tests-first 阶段**, 但建议主控**先用一轮 ccb ask a1** 做工程视角 audit, 覆盖 D-1 ~ D-3 (matrix XML 同名锁决 / codeql-action v4 verify / Dependabot enable 绑 PR step)。同时 a2 出 rev2 补 C-1 (守门测试清单), E-1 (PR-1.5 决策门), E-2 (branch protection require), E-3 (Q7 时机表)。这 7 项补完, design 真正 lock 进 tests-first。

C-1 / E-1 / E-2 是 **must-fix-before-tests-first** (避免 PR 实施时再撞 escalation); D-1 / D-2 / D-3 / E-3 是 **should-fix-in-impl** (a1 工程视角解决可继续); 其他 nice-to-have 不阻 design 进。

---

## 文件清单 + grep 命令

### Read
1. `/tmp/round30-a3-audit-design.md` (本次 brief)
2. `.kiro/specs/engine-mvp0-rebuild-v030/round-30-p1p2-onboard/design.md` (本次 audit 目标, 全文 326 行)
3. `.kiro/specs/engine-mvp0-rebuild-v030/round-30-p1p2-onboard/research.md` (rev3 lock 版, 全文 59 行, 对比 drift)
4. `.kiro/specs/engine-mvp0-rebuild-v030/00-PROGRESS-STATUS.md:240-255` (verify charter sync 真完成)
5. `.github/dependabot.yml` (全文, verify design §5.4 引用真实)
6. `apps/studio/backend/pyproject.toml` (头 40 行, verify 无现有 `[tool.coverage.run]`, design §2.3 加根共享配置合理)
7. (上轮 audit 已读: ci.yml / 根 pyproject / graph-agent pyproject / CODEOWNERS / round-29 design — 本轮复用上下文)

### Bash / grep
- `ls .kiro/specs/engine-mvp0-rebuild-v030/round-30-p1p2-onboard/` → 只有 `design.md` + `research.md`, **verify**: tasks.md / requirements.md 未生成, design 仍是 spec 起步阶段 (合理, 等 design lock 才进 tasks-first)
- `sed -n '240,255p' 00-PROGRESS-STATUS.md` → **物理 verify charter line 244 真有 "B 类前置 (2026-05-29 PM 拍定全部解锁)"** 段, 5 项全列, **跟 design §0 一致, 不是 hallucinate**
- `ls .github/` + `cat .github/dependabot.yml` → **verify dependabot.yml 真存在 + pip + github-actions weekly 都已配** (design §5.4 line 280 引用准确)
- `ls /home/sevenx/coding/agent-harness/scripts/` → **verify scripts/ 真存在** (design §5.2/§5.3 加 `generate_sbom.sh` + `check_licenses.sh` 合理)
- `grep -n "src/|src\*\*|packages/graph-agent/src|apps/studio/backend/app" design.md` → 5 命中, **全是 codecov flag / sonar.sources / 边界声明, 零真改 src/**, 合规
- `grep -n "test_public_api_contract|test_contract_hash_lock|test_round28|test_skill_spec" design.md` → **0 命中**, **verify C-1 漏 catch**: §8 黄金原则 verify 没列守门测试名字

### 没读 (主动声明)
- a1 工程视角 audit 原文 (没收到, 假定 a1 已 audit 过 codecov-action@v5 / codeql-action@v4 / sonarqube-scan-action@v4 / scorecard-action@v2.4.3 这些 action 版本号, 不替 a1 做工程 verify)
- WebFetch verify github/codeql-action releases / codecov-action v5 changelog (D-2 / F-2 工程细节, 归 a1 责任, 我标 should-verify 即可)
- branch protection 现状 (无 gh auth, 无法 `gh api /repos/.../branches/main/protection`, E-2 必须主控用 gh 实证)