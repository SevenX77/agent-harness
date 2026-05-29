# Round 30 P1/P2 Research Rev3: Codecov, SonarCloud, CodeQL, OpenSSF Scorecard

## Q1: Codecov 接入方案
业界推荐 Python 项目 Codecov 接入最佳实践:
- **XML 覆盖率报告聚合**: 经查 `ci.yml` 现状，将产出 **4份 XML** (backend 1 份来自 quality-gates job，graph-agent 3 份来自 matrix Python 3.11/3.12/3.13 job)。实际上传策略为：在 backend job 跑完用 `flags: backend` 上传，在 graph-agent matrix 每个 Python 版 job 跑完用 `flags: py311/py312/py313` 或 `flags: graph-agent` 上传，Codecov 服务端会自动聚合。
- **Action 步骤**: 引入 `codecov/codecov-action@v5`（官方最新推荐为v5），通过 `with.token: ${{ secrets.CODECOV_TOKEN }}` 并指定 `files: coverage-backend.xml,coverage-graph-agent.xml`（按实际 job 存在的产物上传对应 file）进行上传。
- **演进节奏 (必修 M1)**:
  - **PR-1**: 接入 Codecov `report-only` 模式，搭配 comment-bot，跑出真实的基线（如 75%）给 PM。
  - **PR-1.5 (可选)**: 主控与 a1 评估缺少的模块覆盖率，补齐 tests 以提升。
  - **PR-2**: 基线达到 80% 后，切换至 80% 硬阻断，并在 `codecov.yml` 配置 `coverage.status.project.default.threshold` 允许合理的波动范围 (如 ±1%)。

## Q2: SonarCloud 接入方案
- **Action 步骤**: 使用官方推荐的 `SonarSource/sonarqube-scan-action@v4`。
- **前置依赖**: PM 必须先在 `sonarcloud.io` 控制台手动建好 organization 和 projectKey (本仓 = `SevenX77_agent-harness`)，且配置好 mandatory 的 `SONAR_TOKEN` secret，Action 不能纯自动创建项目。
- **跨 Job 覆盖率共享**: Sonar job 与 pytest job 独立 workspace。需要使用 `actions/upload-artifact@v4` 在测试 job 上传生成的 `coverage-backend.xml` 和 `coverage-graph-agent.xml`，再在 Sonar job 用 `actions/download-artifact@v4` 下载；或显式将 Sonar step 和 test 放同 job 单 Python 版本重跑。
- **配置文件**: 设置 `sonar.tests=packages/graph-agent/tests,apps/studio/backend/tests`，并指定 `sonar.python.coverage.reportPaths=coverage-backend.xml,coverage-graph-agent.xml` (真实存在的两份产物路径)。
- **渐进策略 (E-3)**: PR-2 接入 SonarCloud 时使用 `report-only` (暂不启用 Sonar Way 硬门，尤其其要求 Coverage on new code ≥ 80%)，避免出现 Codecov M1 同源的 80% 假门坑。

## Q3: CodeQL 接入方案
- **Action 步骤**: 仓库 PUBLIC 状态 GHAS 自动免费。调用 `github/codeql-action/init@v4`，并显式配置 `with.build-mode: none` (Python 不需编译)，随后调用 `github/codeql-action/analyze@v4`。
- **触发频率**: 推荐 `pull_request` 和 `push` (针对 main 分支) 触发，结合 weekly `cron` schedule。
- **Query suite**: 推荐使用 `security-extended`。

## Q4: OpenSSF Scorecard 接入方案
- **Action 步骤**: 使用 `ossf/scorecard-action@v2.4.3`。
- **必备权限与约束**: 需要赋予 job `permissions: security-events: write, id-token: write, contents: read`。当 `publish_results: true` 时有严格 workflow 限制：不允许在 workflow 级别设置 env/defaults，`id-token: write` 只能赋给 Scorecard job，且 job 内部 steps 必须在允许列表。
- **发布配置**: 设定 `publish_results: true`（charter `.kiro/specs/...:245` 仍待 sync 公开仓拍板，但 2026-05-29 PM 已物理拍定，主控 sync 中）。
- **18 项 Check 与现状**: 实际得分跑过才知道，需在 PR-REPORT 给 PM 报分（无法凭代码库文件单方预测 Branch-Protection 得分，因其配在 repo settings 级别）。

## Q5: 4 工具集成进现有 ci.yml 的总体策略
- **新建 workflow 还是合并**: Codecov 和 SonarCloud 涉及现有 coverage 产物，修改现有 `ci.yml`；CodeQL 和 Scorecard 耗时且独立，建立 `.github/workflows/codeql.yml` 和 `.github/workflows/scorecard.yml`。
- **拆解实施与并行流**: 采用 4 个独立 PR 分步接入 (Codecov -> SonarCloud -> CodeQL -> Scorecard)。执行并行流策略：PR_N step 8 稳定后直接起 PR_N+1 spec/研发，合并操作异步等 PM ack。

## Q6: 风险 / 遗漏维度的建议
- **4 维度补齐建议**:
  - **SBOM (建议补 P2)**: Python 生态主选 `cyclonedx-bom` (直读 pyproject + uv.lock，出 CycloneDX SBOM)；备选 `syft` (用于 container 场景)。
  - **License (建议补 P2)**: 推荐 `pip-licenses` 检查 GPL 入侵。
  - **Dependabot**: 主控默认本期 enable (跟 Scorecard 同 PR 顺手)，标 "[默认 enable, PM 后续 verify; 若 defer 改 disable]"。
  - **生态回归**: Defer 到 P3，跨框架大版本升级成本高，作为独立 Charter 推进。
- **Fork PR Secret 风险**: `[DEFER until 外部 PR 出现]`。已 acknowledge (E-7 N2)：当前仓单人主导 (@SevenX77)，无外部贡献者，此 gotcha 暂搁，外部 PR 出现时再补。

## Q7: PR-REPORT 报分模板
接入后向 PM 的报分必须体现“量差距 + 补齐路径”：
- **首次接 Codecov**:
  - 现状基线：XX% / 目标：80%
  - 对标基准：若公开 dashboard 可查则对标，否则维护自家趋势曲线。
  - 差距补齐路径：缺少的模块及其测试覆盖计划。
- **首次接 Scorecard**:
  - 现状基线：XX / 10（需实时 `curl https://api.securityscorecards.dev/projects/github.com/<owner>/<repo>` 查最新数，不硬编码）。
  - 对标基准：Temporal 5.4 / Prefect 6.8 / Pydantic 7.3 / Ray 5.8（数字随上游变化，必须实时查）。
  - 差距补齐路径：低分项分析与改进动作。
- **首次接 SonarCloud**:
  - 现状基线 (4 轴)：Reliability, Security, Maintainability, Tech Debt。
  - 对标基准：查 sonarcloud.io 公开 dashboard，对标世界级 Python 项目同 SonarCloud 4 轴；如不可查则维护自身趋势。注意 Sonar Way 默认门 (Coverage on new code ≥ 80%) 等需同 Codecov M1 步调绕坑。
  - 差距补齐路径：核心坏味道与技术债优先级。
- **首次接 CodeQL**:
  - 现状基线：security-extended 套件发现 高/中/低 各 N1/N2/N3 个问题（N=0 兜底）。
  - 差距补齐路径：漏洞类型与修复指南。
