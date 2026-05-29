# Round 30 Tasks — P1/P2 External Quality Tools Onboarding

> Reminder: any PR that drifts 65 public API / 92 errors / 33 events / 53 H2 / 14 FROZEN docs / R28 5 mechanisms must stop immediately and escalate PM.

Test 文件位置规则：Round 30 config characterization tests 统一放在 `packages/graph-agent/tests/`。这是 monorepo 当前最近可复用的 pytest infrastructure；这些 tests 检查仓库根 `codecov.yml`、workflow、Sonar/CodeQL/Scorecard 配置，和 graph-agent 业务无关，仅借宿该测试目录。

## §1 4 PR 拆分总览

- [ ] PR-1 Codecov 接入
  - [ ] 范围：接入 Codecov coverage upload 与 report-only comment-bot。
  - [ ] 关键产物：`.github/workflows/ci.yml`、`codecov.yml`、root `pyproject.toml` `[tool.coverage.*]`。
  - [ ] Gate 策略：report-only；`fail_ci_if_error: false`；不进 branch protection。
  - [ ] 依赖关系：复用现有 `coverage-backend.xml` 与 matrix `coverage-graph-agent.xml`。
  - [ ] 并行流：stage 8 forward PM 后立即起 PR-2 spec/研发，不等 PM ack merge。

- [ ] PR-1.5 条件触发覆盖率补测
  - [ ] 范围：当 PR-1 Codecov 真实基线 `< 78%` 时，补 tests 提升至 80%。
  - [ ] 关键产物：仅测试文件。
  - [ ] Gate 策略：跑出基线后评估；不得改 src 行为。
  - [ ] 依赖关系：依赖 PR-1 Codecov dashboard 真实基线。

- [ ] PR-2 SonarCloud 接入
  - [ ] 范围：接入 SonarCloud scan，复用测试 job coverage artifact。
  - [ ] 关键产物：`.github/workflows/ci.yml` artifact upload/download + `sonar-scan` job、`sonar-project.properties`。
  - [ ] Gate 策略：Sonar Way 默认门 report-only；不阻断 PR merge。
  - [ ] 依赖关系：needs PR-1 artifact pattern；PR-2 src 实施前确认 SonarCloud organization/project/token 已就绪。
  - [ ] 并行流：stage 8 forward PM 后立即起 PR-3 spec/研发，不等 PM ack merge。

- [ ] PR-3 CodeQL 接入
  - [ ] 范围：新增 Python CodeQL workflow。
  - [ ] 关键产物：`.github/workflows/codeql.yml`。
  - [ ] Gate 策略：`security-extended` report-only；暂不加入 main branch protection require list。
  - [ ] 依赖关系：PUBLIC repo + GHAS free；需 action version verify。
  - [ ] 并行流：stage 8 forward PM 后立即起 PR-4 spec/研发，不等 PM ack merge。

- [ ] PR-4 Scorecard + SBOM + License + Dependabot
  - [ ] 范围：接入 OpenSSF Scorecard、SBOM artifact、license scan、Dependabot security updates。
  - [ ] 关键产物：`.github/workflows/scorecard.yml`、`scripts/generate_sbom.sh`、`scripts/check_licenses.sh`、repo settings Dependabot enable。
  - [ ] Gate 策略：`publish_results: true`；全 report-only；暂不加入 branch protection require list。
  - [ ] 依赖关系：PR-4 step 0 必须先 enable Dependabot security updates。
  - [ ] 并行流：stage 8 forward PM 后进入 round-30 汇总报告准备。

- [ ] Branch Protection 时机
  - [ ] PR-3 ship 时 CodeQL report-only，暂不加入 required status checks。
  - [ ] PR-4 ship 时 Scorecard report-only，暂不加入 required status checks。
  - [ ] 后续 PR-5 候选：CodeQL high/critical 真实基线与 Scorecard 分稳定后，由主控用 `gh api PATCH /repos/SevenX77/agent-harness/branches/main/protection` 加入 `required_status_checks`。

## §2 PR-1 Codecov 任务序列

- [ ] Stage 3 tests-first（a1 写，a2 audit）
  - [ ] 新增 `packages/graph-agent/tests/test_round30_pr1_codecov_config.py`。
  - [ ] 测试断言 `codecov.yml` 存在。
  - [ ] 测试断言 `codecov.yml` 含 `coverage.status.project.default`、`flags.backend`、`flags.graph-agent`。
  - [ ] 测试断言 `.github/workflows/ci.yml` 含 `codecov/codecov-action@v6` upload step。
  - [ ] 测试断言 root `pyproject.toml` 含 `[tool.coverage.run]` section。
  - [ ] 跑 targeted pytest，必须红灯 fail，因为 stage 4 尚未实施。

- [ ] Stage 4 src/config 实施（a1 写）
  - [ ] 落 `codecov.yml`，按 design §2.2。
  - [ ] 改 `.github/workflows/ci.yml`，在 `quality-gates` 加 backend Codecov upload step。
  - [ ] 改 `.github/workflows/ci.yml`，在 `graph-agent-tests` matrix 加 graph-agent Codecov upload step。
  - [ ] 加 root `pyproject.toml` `[tool.coverage.run]` 与 `[tool.coverage.report]`，按 design §2.3。
  - [ ] 保持 `fail_ci_if_error: false`，PR-1 只 report-only。

- [ ] Stage 5 audit + 跑 tests（a2 + 主控）
  - [ ] `test_round30_pr1_codecov_config.py` 绿灯。
  - [ ] PR-1 相关 tests 全绿。
  - [ ] 4 个 contract gate 全绿：`test_public_api_contract.py`、`test_contract_hash_lock.py`、`test_round28_contract_manifests.py`、`test_round28_invariant_guards.py`。
  - [ ] F-2 verify：核 `codecov-action@v6` 的 `files:` 字段语法与当前 action 文档一致。

- [ ] Stage 6 docs 同步
  - [ ] Owner：a2 主笔 `mvp0-alignment.md` 段 + a1 audit + a3 audit。
  - [ ] `mvp0-alignment.md` 加 round-30 PR-1 段。
  - [ ] 如 status 有变更，同步 `00-PROGRESS-STATUS.md` 对应 round-30 entry。

- [ ] Stage 7 PR-REPORT
  - [ ] a1 主笔 logic-explained 风格报告。
  - [ ] 按 Q7 模板填写 Codecov 4 flags 真实基线：`backend`、`py311`、`py312`、`py313`。
  - [ ] 写清 80% 目标与缺口补齐路径。

- [ ] Stage 8 forward PM
  - [ ] 主控转发 PR-REPORT 给 PM。
  - [ ] 立即起 PR-2 spec/研发，不等 PM ack merge。

- [ ] §2.X PR-1.5 决策门（post-stage 8, pre-PR-2）
  - [ ] Codecov 基线 `>= 78%`：跳过 PR-1.5，直接起 PR-2。
  - [ ] Codecov 基线 `< 78%`：强制起 PR-1.5，补 tests 提升至 80% 后再进 PR-2。
  - [ ] PR-1 step 8 forward PM 后，主控 24h 内访问 `https://app.codecov.io/gh/SevenX77/agent-harness` 拿基线。
  - [ ] 主控把 Codecov 4 flags 基线补进 PR-1 PR-REPORT 的 Q7 段。
  - [ ] 主控据此决策 PR-1.5 是否触发，不再询问 PM。

- [ ] Stage 9 PM ack merge
  - [ ] 等 PM ack 后，按 `[[project_staged_merge_workflow]]` merge feature branch 进 `stage/engine-v030`。

## §3 PR-2 SonarCloud 任务序列

- [ ] Stage 2.5 pre-PR-2 前置确认
  - [ ] 主控确认 PM 已在 `sonarcloud.io` 创建 organization `sevenx77`。
  - [ ] 主控确认 projectKey `SevenX77_agent-harness` 已创建。
  - [ ] 主控确认 `SONAR_TOKEN` 已关联到该 project。
  - [ ] 若未创建，escalate PM，不硬推 PR-2 src 实施。

- [ ] Stage 3 tests-first（a1 写，a2 audit）
  - [ ] Verify action version：跑 `curl https://api.github.com/repos/SonarSource/sonarqube-scan-action/releases | jq '.[0].tag_name'`，确认 action major 后再 lock 进 test 断言。
  - [ ] 新增 `packages/graph-agent/tests/test_round30_pr2_sonarcloud_config.py`，检查 `sonar-project.properties` 必含 organization/projectKey/sources/tests/coverage reportPaths。
  - [ ] 测试断言 `.github/workflows/ci.yml` 含 coverage artifact upload/download 与 `sonar-scan` job。
  - [ ] 测试断言 `sonar-scan` 使用 `SonarSource/sonarqube-scan-action@v8`、`fetch-depth: 0`、`SONAR_TOKEN`。
  - [ ] 跑 targeted pytest，必须红灯 fail，因为 stage 4 尚未实施。

- [ ] Stage 4 src/config 实施（a1 写）
  - [ ] D-2 verify：跑 `curl https://api.github.com/repos/SonarSource/sonarqube-scan-action/releases | jq '.[0].tag_name'`，确认 v8 latest stable；若不是，按 design §4.0 调整。
  - [ ] 新增 `sonar-project.properties`，按 design §3.3。
  - [ ] 改 `.github/workflows/ci.yml`，backend job 上传 `coverage-backend.xml` artifact。
  - [ ] 改 `.github/workflows/ci.yml`，graph-agent matrix 上传 `coverage-graph-agent.xml` artifact。
  - [ ] 新增 `sonar-scan` job，needs `[quality-gates, graph-agent-tests]`，下载 artifact 后跑 scan。
  - [ ] D-1 lock：SonarCloud 只看任一 Python 版 graph-agent coverage，推荐 3.11；不要求三版本全送 Sonar。
  - [ ] 保持 SonarCloud report-only，不配置 CI hard fail。

- [ ] Stage 5 audit + 跑 tests（a2 + 主控）
  - [ ] Sonar config characterization test 绿灯。
  - [ ] PR-2 相关 tests 全绿。
  - [ ] 4 个 contract gate 全绿。
  - [ ] 主控确认 workflow artifact pattern 不依赖 non-matrix `matrix.python-version`。

- [ ] Stage 6 docs 同步
  - [ ] Owner：a2 主笔 `mvp0-alignment.md` 段 + a1 audit + a3 audit。
  - [ ] `mvp0-alignment.md` 加 round-30 PR-2 段。
  - [ ] 同步 status entry，如有需要。

- [ ] Stage 7 PR-REPORT
  - [ ] 报 SonarCloud 4 轴首次基线：Reliability、Security、Maintainability、Technical Debt。
  - [ ] 若 PR-1.5 已 ship，同时补 Codecov 提升后数。
  - [ ] 列出 Sonar Way 失败项与 report-only 原因。

- [ ] Stage 8 forward PM
  - [ ] 主控转发 PR-REPORT 给 PM。
  - [ ] 立即起 PR-3 spec/研发，不等 PM ack merge。

## §4 PR-3 CodeQL 任务序列

- [ ] Stage 3 tests-first（a1 写，a2 audit）
  - [ ] Verify action version：跑 `curl https://api.github.com/repos/github/codeql-action/releases | jq '.[0].tag_name'`，确认 action major 后再 lock 进 test 断言。
  - [ ] 新增 `packages/graph-agent/tests/test_round30_pr3_codeql_config.py`，检查 `.github/workflows/codeql.yml` 存在。
  - [ ] 测试断言 workflow 使用 `github/codeql-action/init@v4` 与 `github/codeql-action/analyze@v4`。
  - [ ] 测试断言 `languages: python`、`build-mode: none`、`queries: security-extended`。
  - [ ] 测试断言 permissions 含 `actions: read`、`contents: read`、`security-events: write`。
  - [ ] 跑 targeted pytest，必须红灯 fail，因为 stage 4 尚未实施。

- [ ] Stage 4 src/config 实施（a1 写）
  - [ ] D-2 verify：跑 `curl https://api.github.com/repos/github/codeql-action/releases | jq '.[0].tag_name'`，确认 v4 latest stable。
  - [ ] 若 v4 不是 latest stable，按官方 release 回退 v3 或调整 spec 后再实施。
  - [ ] 新增 `.github/workflows/codeql.yml`，按 design §4.1。
  - [ ] 保持 PR-3 report-only，不加入 branch protection required list。

- [ ] Stage 5 audit + 跑 tests（a2 + 主控）
  - [ ] CodeQL workflow characterization test 绿灯。
  - [ ] PR-3 相关 tests 全绿。
  - [ ] 4 个 contract gate 全绿。
  - [ ] 主控确认 Code Scanning 有上传结果；若首次无 finding，也在报告中写 N=0。

- [ ] Stage 6 docs 同步
  - [ ] Owner：a2 主笔 `mvp0-alignment.md` 段 + a1 audit + a3 audit。
  - [ ] `mvp0-alignment.md` 加 round-30 PR-3 段。
  - [ ] 同步 status entry，如有需要。

- [ ] Stage 7 PR-REPORT
  - [ ] 报 CodeQL high/medium/low 首次基线。
  - [ ] 列 high/critical 真实问题与修复路径；N=0 明确写 0。
  - [ ] 说明 PR-3 report-only，未进 branch protection。

- [ ] Stage 8 forward PM
  - [ ] 主控转发 PR-REPORT 给 PM。
  - [ ] 立即起 PR-4 spec/研发，不等 PM ack merge。

## §5 PR-4 Scorecard + SBOM + License + Dependabot 任务序列

- [ ] Stage 2.5 / step 0 repo settings 前置
  - [ ] 主控跑 `gh api -X PUT /repos/SevenX77/agent-harness/automated-security-fixes` enable Dependabot security updates。
  - [ ] Verify：`gh api /repos/SevenX77/agent-harness/vulnerability-alerts` returns 204。
  - [ ] 若 enable 或 verify 返回 404 / 403 / 权限不足 / 非 204，escalate PM，不硬推 PR-4 src 实施。
  - [ ] 该步骤不在 PR diff 内，但必须在 PR-4 ship 前完成。

- [ ] Stage 3 tests-first（a1 写，a2 audit）
  - [ ] Verify action version：跑 `curl https://api.github.com/repos/ossf/scorecard-action/releases | jq '.[0].tag_name'`，确认 action version 后再 lock 进 test 断言。
  - [ ] 新增 `packages/graph-agent/tests/test_round30_pr4_scorecard_sbom_license_config.py`，检查 `.github/workflows/scorecard.yml` 存在。
  - [ ] 测试断言 workflow 使用 `ossf/scorecard-action@v2.4.3`、`results_format: sarif`、`publish_results: true`。
  - [ ] 测试断言 workflow 不含 workflow-level `env` / `defaults`，并使用 job-level `id-token: write`。
  - [ ] 新增 SBOM/license scripts characterization test，检查 `scripts/generate_sbom.sh` 与 `scripts/check_licenses.sh` 存在并含关键命令。
  - [ ] 跑 targeted pytest，必须红灯 fail，因为 stage 4 尚未实施。

- [ ] Stage 4 src/config 实施（a1 写）
  - [ ] D-2 verify：跑 `curl https://api.github.com/repos/ossf/scorecard-action/releases | jq '.[0].tag_name'`，确认 v2.4.3。
  - [ ] 新增 `.github/workflows/scorecard.yml`，按 design §5.1。
  - [ ] 新增 `scripts/generate_sbom.sh`，按 design §5.2。
  - [ ] 新增 `scripts/check_licenses.sh`，按 design §5.3。
  - [ ] F-1 verify：跑 `uvx pip-licenses --fail-on="GPL;AGPL"` 实测 CLI 语法，确认空格/分号/等号形式哪个可用后再写脚本。
  - [ ] 保持 PR-4 report-only，不加入 branch protection required list。

- [ ] Stage 5 audit + 跑 tests（a2 + 主控）
  - [ ] Scorecard/SBOM/license characterization tests 绿灯。
  - [ ] PR-4 相关 tests 全绿。
  - [ ] 4 个 contract gate 全绿。
  - [ ] 主控确认 Scorecard SARIF 上传到 Security tab。
  - [ ] 主控确认 SBOM artifact 产出。
  - [ ] 主控确认 license scan 风险清单可读。

- [ ] Stage 6 docs 同步
  - [ ] Owner：a2 主笔 `mvp0-alignment.md` 段 + a1 audit + a3 audit。
  - [ ] `mvp0-alignment.md` 加 round-30 PR-4 段。
  - [ ] 同步 status entry，如有需要。

- [ ] Stage 7 PR-REPORT
  - [ ] 报 Scorecard X/10。
  - [ ] 报 SBOM artifact 路径。
  - [ ] 报 license 风险清单。
  - [ ] 报 Dependabot security updates 状态。
  - [ ] 说明 PR-4 report-only，未进 branch protection。

- [ ] Stage 8 forward PM
  - [ ] 主控转发 PR-REPORT 给 PM。
  - [ ] 进入 round-30 汇总报告准备。

## §6 4 PR 全 ship 后 round-30 汇总报告

- [ ] Owner：a1 主笔（logic-explained 风格）+ a2 honesty audit + a3 audit + 主控 forward PM。
- [ ] 主控起 round-30 汇总报告并 forward PM。
- [ ] 汇总 Codecov 4 flags 最终基线：`backend`、`py311`、`py312`、`py313`。
- [ ] 汇总 SonarCloud 4 轴最终基线：Reliability、Security、Maintainability、Technical Debt。
- [ ] 汇总 CodeQL high/medium/low 最终基线。
- [ ] 汇总 Scorecard X/10。
- [ ] 汇总 SBOM artifact 路径。
- [ ] 汇总 license 风险清单。
- [ ] 汇总 Dependabot security updates 状态。
- [ ] 给出与“对标世界级”目标的差距补齐路径，明确下个 round 推进项。

### §6.1 round-30 完结边界 + round-31 scope

- [ ] Round 30 完结边界：PR-1 / PR-2 / PR-3 / PR-4 全部 ship，且 4 PR 全 ship 后汇总报告 forward PM。
- [ ] Round 31 候选 scope：PR-5 候选，评估 branch protection required status checks，把 CodeQL + Scorecard 从 report-only 切向硬门（仅当真实基线稳定）。
- [ ] Round 31 不在 Round 30 scope；主控不在 Round 30 内开 PR-5。

## §7 黄金原则 verify (SOP-06)

- [ ] 每个 PR ship 前先验证 4 个 test 文件真实存在；路径不对就 grep 实际位置修正。
  - [ ] `packages/graph-agent/tests/test_public_api_contract.py`
  - [ ] `packages/graph-agent/tests/test_contract_hash_lock.py`
  - [ ] `packages/graph-agent/tests/test_round28_contract_manifests.py`
  - [ ] `packages/graph-agent/tests/test_round28_invariant_guards.py`

- [ ] 每个 PR ship 前必须跑 4 个 contract gate：
  - [ ] `uv run pytest packages/graph-agent/tests/test_public_api_contract.py --tb=short -q`
  - [ ] `uv run pytest packages/graph-agent/tests/test_contract_hash_lock.py --tb=short -q`
  - [ ] `uv run pytest packages/graph-agent/tests/test_round28_contract_manifests.py --tb=short -q`
  - [ ] `uv run pytest packages/graph-agent/tests/test_round28_invariant_guards.py --tb=short -q`

- [ ] 每个 PR ship 前确认：
  - [ ] 65 public API symbols 不漂。
  - [ ] 92 error codes 不漂。
  - [ ] 33 event types 不漂。
  - [ ] 53 skill-spec H2 不漂。
  - [ ] 14 FROZEN docs SHA 不漂。
  - [ ] R28 5 mechanisms 不漂。
