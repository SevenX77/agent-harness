# Round 30 Design — P1/P2 External Quality Tools Onboarding

## §0 Prerequisite
- PM 2026-05-29 已拍定仓库公开与徽章公开：`visibility=PUBLIC`，OpenSSF Scorecard `publish_results: true`。
- 主控已同步 charter：`.kiro/specs/engine-mvp0-rebuild-v030/00-PROGRESS-STATUS.md:245` 记录 `CODECOV_TOKEN`、`SONAR_TOKEN`、PUBLIC、badge publish、Dependabot 本期 enable。
- GitHub secrets 已配置：`CODECOV_TOKEN` 与 `SONAR_TOKEN`。本设计不新增明文 token，也不在仓库内落 secret。
- 仓库实际可见性由主控验证：`gh repo view SevenX77/agent-harness --json visibility,isPrivate` 输出 `{"visibility":"PUBLIC","isPrivate":false}`。a1 本地 `gh` 未登录，`git ls-remote https://github.com/SevenX77/agent-harness.git HEAD` 仅作为公网可读的辅助验证。
- 主控 sync 现 working tree 干净，base branch 为 `wc/round30-p1p2-onboard`，base commit 为 `c736251`。
- 本 stage 只新增本 `design.md`；所有 CI、workflow、pyproject、script 变更均留给后续 PR 实施。

## §1 PR 拆分 + 节奏
| PR | 范围 | 关键产物 | gate 策略 |
|---|---|---|---|
| PR-1 | Codecov 接入 | `.github/workflows/ci.yml` + `codecov.yml` + coverage 配置 | report-only, comment-bot |
| PR-1.5 (条件触发) | 补 tests 提升覆盖率至 80 | 仅加测试 | Codecov 基线 < 78% 时强制；基线 >= 78% 时跳过 |
| PR-2 | SonarCloud 接入 | `.github/workflows/ci.yml` artifact + `sonar-scan` job + `sonar-project.properties` | Sonar Way 默认门 report-only |
| PR-3 | CodeQL 接入 | `.github/workflows/codeql.yml` | `security-extended` report-only，后期 high/critical 硬门 |
| PR-4 | Scorecard + SBOM + License + Dependabot | `.github/workflows/scorecard.yml` + SBOM script + license check + Dependabot settings | `publish_results: true`，全 report-only |

并行流策略按宪法 10 执行：PR_N step 8 forward PM 报告后立即起 PR_N+1 spec/研发，不等待 PM ack merge；合并动作仍异步等待 PM 拍板。

### §1.1 Branch Protection 时机
PR-3 ship 时 CodeQL workflow report-only，暂不加入 main branch protection require list。

PR-4 ship 时 Scorecard workflow report-only，暂不加入 main branch protection require list。

后续单独 PR（PR-5 候选）评估 CodeQL high/critical 真实基线与 Scorecard 分数稳定性后，由主控用 `gh api PATCH /repos/SevenX77/agent-harness/branches/main/protection` 加入 `required_status_checks`。

这与宪法 5 “门要真”一致：report-only 阶段不假装 enforced。

## §2 PR-1 Codecov 具体配置
### §2.1 `ci.yml` 改动
当前 CI 已产出 4 份 coverage XML：`quality-gates` job 产出 1 份 `coverage-backend.xml`，`graph-agent-tests` matrix 在 Python 3.11/3.12/3.13 各产出 1 份 `coverage-graph-agent.xml`。PR-1 只上传真实存在于当前 job workspace 的文件。

在 `quality-gates` job 的 backend pytest 后添加：

```yaml
- name: Upload backend coverage to Codecov
  uses: codecov/codecov-action@v6
  with:
    token: ${{ secrets.CODECOV_TOKEN }}
    files: coverage-backend.xml
    flags: backend
    fail_ci_if_error: false
```

在 `graph-agent-tests` job 的 matrix pytest 后添加：

```yaml
- name: Upload graph-agent coverage to Codecov
  uses: codecov/codecov-action@v6
  with:
    token: ${{ secrets.CODECOV_TOKEN }}
    files: coverage-graph-agent.xml
    flags: graph-agent,${{ matrix.py_flag }}
    fail_ci_if_error: false
```

`graph-agent-tests.strategy.matrix` 使用 explicit include 映射 `python-version` -> `py_flag`：`3.11 -> py311`、`3.12 -> py312`、`3.13 -> py313`。Codecov flag 不允许 `.`，不得直接拼 `py${{ matrix.python-version }}`。

`fail_ci_if_error: false` 是 PR-1 report-only 的关键；PR-2 以后等基线达到 80% 再切硬阻断。

### §2.2 [NEW] `codecov.yml`
仓库根新增：

```yaml
codecov:
  require_ci_to_pass: true

coverage:
  status:
    project:
      default:
        target: auto
        threshold: 1%
    patch:
      default:
        target: auto
        threshold: 1%

comment:
  layout: "reach, diff, flags, files"
  behavior: default
  require_changes: false

flags:
  backend:
    paths:
      - apps/studio/backend/app/
  graph-agent:
    paths:
      - packages/graph-agent/src/graph_agent/
```

### §2.3 coverage 配置
PR-1 需要确认 coverage 配置被 root CI 实际读取。由于现有 pytest 从仓库根执行，优先方案是在 root `pyproject.toml` 增加共享配置；若选择 package-local `pyproject.toml`，CI 必须显式加 `--cov-config`，否则 coverage 可能仍读取 root 配置。

推荐 root 共享配置：

```toml
[tool.coverage.run]
relative_files = true
parallel = true
omit = ["*/tests/*", "*/migrations/*"]

[tool.coverage.report]
exclude_lines = ["pragma: no cover", "raise NotImplementedError"]
show_missing = true
skip_covered = false
```

如后续确需 package-local 差异配置，则分别落到 `packages/graph-agent/pyproject.toml` 与 `apps/studio/backend/pyproject.toml`，并同步在 CI pytest 命令传 `--cov-config=<path>`。

### §2.4 PR-1.5 决策门
PR-1 ship 拿到 Codecov 真实基线后，按阈值决定：

- 基线 >= 78%：跳过 PR-1.5，直接进 PR-2。
- 基线 < 78%：强制 PR-1.5，补 tests 提升至 80%，再进 PR-2。

主控亲跑 Codecov dashboard 拿数，写进 PR-1 报告，不再询问 PM。

## §3 PR-2 SonarCloud 具体配置
### §3.1 前置
- 在 `sonarcloud.io` 控制台创建 organization，推荐 `sevenx77`。
- 创建 project，推荐 `sonar.projectKey=SevenX77_agent-harness`。
- 将既有 `SONAR_TOKEN` GitHub secret 绑定到该 project。SonarQube Scan action 只执行扫描，不负责自动创建 Cloud project。

### §3.2 `ci.yml` 改动：跨 job artifact 共享
GitHub Actions job workspace 不共享。PR-2 不应假设 PR-1 上传给 Codecov 的 XML 能被 Sonar job 直接看到，必须用 artifact 串联或在 Sonar job 重跑 tests。本设计采用 artifact 串联。

在 `quality-gates` job 的 backend coverage 生成后添加：

```yaml
- name: Upload backend coverage artifact
  uses: actions/upload-artifact@v4
  with:
    name: coverage-backend
    path: coverage-backend.xml
```

在 `graph-agent-tests` matrix job 的 graph-agent coverage 生成后添加：

```yaml
- name: Upload graph-agent coverage artifact
  uses: actions/upload-artifact@v4
  with:
    name: coverage-graph-agent-py${{ matrix.python-version }}
    path: coverage-graph-agent.xml
```

新增 `sonar-scan` job：

```yaml
sonar-scan:
  needs: [quality-gates, graph-agent-tests]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0
    - name: Download coverage artifacts
      uses: actions/download-artifact@v4
      with:
        pattern: coverage-*
        merge-multiple: true
    - name: SonarQube Scan
      uses: SonarSource/sonarqube-scan-action@v4
      env:
        SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
        SONAR_HOST_URL: https://sonarcloud.io
```

Artifact 命名禁止在 non-matrix job 引用 `matrix.python-version`；backend 与 graph-agent matrix 使用独立名称，避免表达式在 `quality-gates` 中解析失败。

### §3.3 [NEW] `sonar-project.properties`
仓库根新增：

```properties
sonar.organization=sevenx77
sonar.projectKey=SevenX77_agent-harness
sonar.host.url=https://sonarcloud.io

sonar.sources=packages/graph-agent/src,apps/studio/backend/app
sonar.tests=packages/graph-agent/tests,apps/studio/backend/tests
sonar.python.version=3.11,3.12,3.13

sonar.python.coverage.reportPaths=coverage-backend.xml,coverage-graph-agent.xml

sonar.exclusions=**/migrations/**,**/__pycache__/**
sonar.test.exclusions=**/fixtures/**
```

**lock 决策**：PR-2 SonarCloud 看任一 Python 版的 graph-agent coverage XML，推荐 Python 3.11，跟 backend 单版本一致。不要求三版本覆盖率全送 Sonar；Codecov 已负责 matrix 聚合，Sonar 主要负责 code smell、security、maintainability 与单份 coverage 关联。

Artifact 重命名（如 `coverage-graph-agent-3.11.xml`）留给后续 PR 评估，不在 PR-2 scope。

### §3.4 渐进策略
PR-2 ship 时 SonarCloud dashboard 使用 "Sonar Way" 默认 quality gate，但 CI 不配置 hard fail。等 Codecov M1 真实基线与 Sonar "Coverage on new code >= 80%" 目标一致后，再由后续 PR 切硬门。

## §4 PR-3 CodeQL 具体配置
### §4.0 Action 版本 verify
各实施 PR 开始前必须先确认 action 版本仍是当前稳定推荐：

- PR-1：`curl https://api.github.com/repos/codecov/codecov-action/releases | jq '.[0].tag_name'`，确认 `codecov-action@v6` 仍可用且是推荐 major；若官方推荐 major 改变，实施前更新 spec。
- PR-2：`curl https://api.github.com/repos/SonarSource/sonarqube-scan-action/releases | jq '.[0].tag_name'`，确认 `sonarqube-scan-action@v4` 仍是 latest stable；若不是，按官方 release 调整。
- PR-3：`curl https://api.github.com/repos/github/codeql-action/releases | jq '.[0].tag_name'`，确认 `github/codeql-action@v4` 是 latest stable；若不是，回退 v3 或按官方 release 调整。
- PR-4：`curl https://api.github.com/repos/ossf/scorecard-action/releases | jq '.[0].tag_name'`，确认 `ossf/scorecard-action@v2.4.3` 仍是 stable；若不是，按官方 release 调整。

### §4.1 [NEW] `.github/workflows/codeql.yml`
```yaml
name: "CodeQL"

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"

permissions:
  actions: read
  contents: read
  security-events: write

jobs:
  analyze:
    name: Analyze (Python)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Initialize CodeQL
        uses: github/codeql-action/init@v4
        with:
          languages: python
          build-mode: none
          queries: security-extended
      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v4
```

Python 是解释型语言，`build-mode: none` 是必须配置。PR-3 初期只上报 Code Scanning；后续等首轮 high/critical 基线清零后再评估硬门。

## §5 PR-4 Scorecard + SBOM + License + Dependabot
### §5.1 [NEW] `.github/workflows/scorecard.yml`
```yaml
name: "Scorecard"

on:
  push:
    branches: [main]
  schedule:
    - cron: "0 7 * * 1"

permissions: read-all

jobs:
  analysis:
    name: Scorecard analysis
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Run analysis
        uses: ossf/scorecard-action@v2.4.3
        with:
          results_file: results.sarif
          results_format: sarif
          publish_results: true
      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v4
        with:
          sarif_file: results.sarif
```

Scorecard `publish_results: true` 有 workflow 完整性限制：不设置 workflow-level `env` / `defaults`，不设置 workflow-level write permissions，只有 Scorecard job 使用 `id-token: write`，job 内 steps 只使用允许列表中的 actions。

### §5.2 [NEW] SBOM 生成
Python 生态主选 `cyclonedx-bom`；`syft` 保留给 container/image 场景。新增 `scripts/generate_sbom.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

uvx cyclonedx-bom -o sbom.json
```

PR-4 CI 跑完上传 `sbom.json` artifact；Release attach 作为后续发布治理增强，不阻塞本轮接入。

### §5.3 [NEW] License check
新增 `scripts/check_licenses.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

uvx pip-licenses --format=markdown --with-urls > LICENSES.md
uvx pip-licenses --fail-on="GPL;AGPL"
```

PR-4 初期建议 report-only；若发现 GPL/AGPL 依赖，先在 PR-REPORT 中列出依赖路径与替代方案，再决定是否切硬门。

### §5.4 Dependabot 配置
现有 `.github/dependabot.yml` 已配置 root pip 与 GitHub Actions weekly updates。本期只需确认：
- `.github/dependabot.yml` 是否需要补注释或分组调整。
- Dependabot security updates 不在 `dependabot.yml` 中配置，应通过 GitHub repo setting/API 启用。

**PR-4 step 0（src 实施前）**：主控跑 `gh api -X PUT /repos/SevenX77/agent-harness/automated-security-fixes` enable Dependabot security updates。

Verify：`gh api /repos/SevenX77/agent-harness/vulnerability-alerts` returns 204。

这步不在 PR diff 内（是 repo settings），但必须在 PR-4 ship 前完成；否则 Scorecard 跑出 Dependabot-Updates 分项低，Q7 报分会撞解释。

## §6 Q7 报分模板
PR-1 / PR-2 / PR-3 / PR-4 ship 时，PR-REPORT 必须给 PM 呈现“量差距 + 补齐路径”，禁止只报“CI 绿 / 接入成功”。

- Codecov：当前覆盖率 XX% / 目标 80%；按 `backend`、`graph-agent`、`py311/py312/py313` flags 列缺口；给出 75 -> 80 的补测路径。
- SonarCloud：Reliability、Security、Maintainability、Technical Debt 四轴基线；列 Sonar Way 失败项；说明哪些项暂 report-only。
- CodeQL：`security-extended` high/medium/low 数量；列 high/critical 具体类型与修复计划；N=0 也要明确写 0。
- Scorecard：当前 XX / 10；实时查 `https://api.securityscorecards.dev/projects/github.com/SevenX77/agent-harness`，对标项目分数也实时查，不硬编码；列低分项和低成本修复路径。
- SBOM / License / Dependabot：列 SBOM artifact 路径、license 风险清单、Dependabot security update 状态。

| PR | PR-REPORT 必含基线项 |
|---|---|
| PR-1 ship | Codecov 4 flags（backend/py311/py312/py313）首次基线 |
| PR-2 ship | SonarCloud 4 轴首次基线 + 若 PR-1.5 已 ship，补 Codecov 提升后数 |
| PR-3 ship | CodeQL 高/中/低首次基线 |
| PR-4 ship | Scorecard X/10 + SBOM artifact 路径 + license 风险 + Dependabot 状态 |
| 4 PR 全 ship 后 | 主控起 round-30 汇总报告 forward PM |

## §7 影响范围 (SOP-06)
后续 PR 计划新增文件：
- `[NEW] codecov.yml`
- `[NEW] sonar-project.properties`
- `[NEW] .github/workflows/codeql.yml`
- `[NEW] .github/workflows/scorecard.yml`
- `[NEW] scripts/generate_sbom.sh`
- `[NEW] scripts/check_licenses.sh`

后续 PR 计划修改文件：
- `.github/workflows/ci.yml`：加 Codecov upload、coverage artifact upload、`sonar-scan` job。
- `.github/dependabot.yml`：保留现有 pip + github-actions weekly；如需要仅做分组/注释微调。security updates 通过 repo settings/API 启用。
- `pyproject.toml` 或 package-local pyproject：加 coverage 配置；若 package-local，CI 必须传 `--cov-config`。
- `.kiro/specs/engine-mvp0-rebuild-v030/00-PROGRESS-STATUS.md`：同步 round-30 status entry。

后续 PR 不动文件：
- `src/**`
- `tests/**`，除非进入 PR-1.5 补覆盖率专门 PR。
- contract specs / frozen skill-spec docs，除非 PM 另行批准。

本 stage 已执行边界：只新增本 `design.md`；未修改 `src/**`、`tests/**`、workflow yaml、pyproject。

## §8 黄金原则 verify (SOP-06)
- 65 public API：不动，因本轮只接外部质量工具。
- 92 errors：不动。
- 33 events：不动。
- 53 H2：不动。
- 14 FROZEN docs SHA：不动。
- R28 5 机制：不动。

所有 `[NEW]` 文件都是 CI/quality telemetry 配置或脚本；修改文件均为 CI、Dependabot、coverage 配置与 status 文档，不改变 runtime 行为。PR-1/2/3/4 合并前仍需跑对应 contract guard，证明外部工具接入没有污染引擎契约。

PR-1/2/3/4 合并前每个 PR 必须跑 4 个 contract gate：

- `packages/graph-agent/tests/test_public_api_contract.py`
- `packages/graph-agent/tests/test_contract_hash_lock.py`
- `packages/graph-agent/tests/test_round28_contract_manifests.py`
- `packages/graph-agent/tests/test_round28_invariant_guards.py`

a1 实施时先验证这 4 个 test 文件真实存在（`find` / `ls` 实证）；路径不对就 `grep` 实际位置并修正。
