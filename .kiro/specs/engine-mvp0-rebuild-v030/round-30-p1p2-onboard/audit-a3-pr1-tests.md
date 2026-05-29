# Round 30 PR-1 tests 红灯 audit — a3 PM 替身视角

## 1. 红灯纯度结论 ✅

我亲跑 `cd packages/graph-agent && uv run pytest tests/test_round30_pr1_codecov_config.py -v`, **3/3 失败, 红灯纯净**:

- test 1: `codecov.yml` 不存在 → `.exists()` False → assert 失败
- test 2: `codecov-action@v6` 字符串不在 `ci.yml`
- test 3: `pyproject.toml` 无 `[tool.coverage]` 段 → `KeyError: 'coverage'`

3 失败原因都直接对应 "src 未实施", **不是测试本身 bug, 红灯纯净** ✅。

## 2. 7 项 assertion vs design 覆盖 — **覆盖率 ≈ 50%**, 多个 report-only 关键漏断言

design §2.1+§2.2+§2.3 共 **18 项硬要求**, test 真覆盖 9 项, 漏 9 项:

| design 要求 | test 覆盖 |
|---|---|
| §2.1 (1) backend upload step 存在 | ⚠️ 只断言字符串 `codecov-action` 在 workflow, 没 grep 具体 step |
| §2.1 (2) graph-agent upload step 存在 | ⚠️ 同上, 共享一个 in-string 断言 |
| §2.1 (3) backend `files: coverage-backend.xml` + `flags: backend` | ❌ **未断言** |
| §2.1 (4) graph-agent `files: coverage-graph-agent.xml` + `flags: graph-agent,py${{ matrix.python-version }}` | ❌ **未断言** |
| §2.1 (5) **`fail_ci_if_error: false`** (report-only 关键) | ❌ **未断言** → M-3 |
| §2.1 (6) `token: ${{ secrets.CODECOV_TOKEN }}` | ✅ test 2 line 31 |
| §2.2 (7) `codecov.require_ci_to_pass: true` | ❌ 未断言 |
| §2.2 (8) **`project.default.target: auto + threshold: 1%`** (report-only 关键) | ⚠️ 只断言 `isinstance(project_default, dict)` → M-2 false positive |
| §2.2 (9) `patch.default.target/threshold` | ❌ 未断言 |
| §2.2 (10) `comment.layout/behavior/require_changes` | ❌ 未断言 |
| §2.2 (11) `flags.backend.paths` 含 `apps/studio/backend/app/` | ✅ test 1 line 23 |
| §2.2 (12) `flags.graph-agent.paths` 含 `packages/graph-agent/src/graph_agent/` | ✅ test 1 line 24 |
| §2.3 (13) `tool.coverage.run.relative_files = true` | ✅ test 3 line 38 |
| §2.3 (14) `tool.coverage.run.parallel = true` | ✅ test 3 line 39 |
| §2.3 (15) `tool.coverage.run.omit = [...]` | ❌ 未断言 |
| §2.3 (16) `tool.coverage.report.exclude_lines = [...]` | ❌ 未断言 |
| §2.3 (17) `tool.coverage.report.show_missing = true` | ❌ 未断言 |
| §2.3 (18) `tool.coverage.report.skip_covered = false` | ❌ 未断言 |

## 3. 缺陷分级

### must-fix (3 项, 阻 stage 4 src 实施)

**M-1 — action 版本号跟 spec 不一致, 严重 drift**
- test 2 line 30: `assert "codecov/codecov-action@v6" in workflow`
- design §2.1 line 39/51 + §4.0 PR-1 verify line 202 + tasks §2 stage 3 line 52: **全部锁 `@v5`**
- a1 单方面写 `@v6` = 跟 lock 后的 spec 偏离 (违反 SOP-06 spec 默认保守: 没经 sync design 不能擅自改 spec)
- **修法**:
  - 选 (a) a1 先按 tasks §2 stage 5 line 67 F-2 verify 跑 `curl https://api.github.com/repos/codecov/codecov-action/releases | jq '.[0].tag_name'`, 真是 v6 → **sync design §2.1 + §4.0 + tasks §2 stage 3 改成 v6** + 给主控/PM 报版本号更新 + 再让 test 留 v6
  - 选 (b) 真是 v5 latest → test 改回 v5
  - 当前状态 test 直接进 stage 4, a1 会按 test 锁的 v6 写 src → 跟 design v5 偏离, **下游 audit (stage 5) 撞 spec/src 不一致**

**M-2 — test 1 line 20 `assert isinstance(project_default, dict)` 是 false positive 漏洞**
- 该断言**不锁 `target: auto`**, src 实施时把 `target: 80%` (硬门) 写进去 test 也 pass
- 直接违反 design §2.4 PR-1 "report-only" 核心目标 + 宪法 5 "门要真"
- **修法**: 加 `assert project_default["target"] == "auto"` + `assert project_default["threshold"] == "1%"`

**M-3 — test 2 没断言 `fail_ci_if_error: false`**
- design §2.1 line 44/56 + line 59 "fail_ci_if_error: false 是 PR-1 report-only 的关键"
- test 漏掉 → src 写 `fail_ci_if_error: true` (硬门) test 仍通过 → 跟 M-2 同根 report-only 假门
- **修法**: 加 `assert workflow.count("fail_ci_if_error: false") >= 2` (backend + graph-agent 各一次)

### should-fix (4 项, 覆盖率不足但不阻 stage 4)

**S-1** test 2 漏断言 `files: coverage-backend.xml` + `files: coverage-graph-agent.xml` (design §2.1 (3)(4))
- 风险: src 实施时 files 字段写错路径, test 也 pass, Codecov dashboard 收不到 XML

**S-2** test 2 漏断言 `flags: backend` + `flags: graph-agent,py${{ matrix.python-version }}` (design §2.1 (3)(4))
- 风险: flags 错 → Codecov 仪表盘 4 flags (backend/py311/py312/py313) 维度断流 → Q7 报分模板 (design §6 line 320) 报不出 4 flags 数据

**S-3** test 1 漏断言 `codecov.require_ci_to_pass: true` (design §2.2 (7))
- 风险: src 实施时漏掉这一字段, CI 失败但 Codecov 状态依然给绿 → main 流入污染数据

**S-4** test 1 漏断言 `patch.default` + `comment` 段 (design §2.2 (9)(10))
- 风险: PR comment-bot 缺失 → PR-1 stage 8 给 PM forward 报告时看不到 PR 增量覆盖率 → 跟 design §2.4 / tasks §2 stage 9 "主控亲跑 dashboard 拿数" 时机依据冲突

### nice-to-have (3 项)

- **N-1** test 3 漏断言 `omit / exclude_lines / show_missing / skip_covered` (design §2.3 (15)-(18))
- **N-2** test 1 没显式 try/except 包 `yaml.safe_load`, 如果 codecov.yml 出现语法错就抛异常, test 看似 fail 但不是因为业务断言, 错信号
- **N-3** test 文件无 docstring / 注释关联 design §X.Y, 后续 reviewer 难 cross-reference

## 整体建议

测试**红灯纯度过关**, 但 **覆盖率 50% + 2 处 report-only 关键 false positive (M-2/M-3) + 1 处 action 版本 spec drift (M-1)**, 不能直接进 stage 4 src 实施。

建议主控 sync a1 修 M-1/M-2/M-3 这 3 项 must-fix (10 分钟工作量), 再决定 S-1~S-4 是否本轮补全 (推荐补全, 跟 SOP-08 tests-first 精神一致 — tests 越完整越锁死 src 偏移)。N-1~N-3 可 defer 进 stage 5 audit 时补充。

M-1 优先级最高, 因为如果 v6 真是 a1 工程 verify 后的新结论, **必须先 sync design v5→v6 留迹**, 不能 a1 单方面在 test 里改 spec lock 值 (违反 SOP-06)。

---

## 文件清单 + grep/bash 命令

### Read
1. `/tmp/round30-a3-audit-pr1-tests.md` (本次 brief)
2. `packages/graph-agent/tests/test_round30_pr1_codecov_config.py` (本次 audit 目标, 全文 40 行)
3. design rev2 lock §2.1+§2.2+§2.3 (上轮 audit 已 read, 复用 — 重点 line 39/44/51/56/59 + §2.2 codecov.yml 全 yaml + §2.3 pyproject.toml 全 toml)
4. tasks.md rev2 lock §2 PR-1 任务序列 stage 3 (上轮 audit 已 read, 复用 — line 49-54 显式列 4 项 test 断言要求)

### Bash
- `cd packages/graph-agent && uv run pytest tests/test_round30_pr1_codecov_config.py -v` → **3 failed, 0 passed**, 红灯纯净 verify ✅
- 失败信号 read 后 verify 真原因 = src 未落, 不是 test bug

### grep (内嵌在 read 中)
- 对 design.md `@v5` vs test `@v6` 对照, **catch M-1 spec drift**
- 对 design.md `fail_ci_if_error: false` 出现位置 (line 44/56/59) vs test 断言, **catch M-3 漏断言**
- 对 design.md `target: auto` (line 71) vs test 仅 `isinstance(dict)`, **catch M-2 false positive**

### 没读 / 没跑 (主动声明)
- 没派任务 / 没 ccb ask / 没动文件 ✅ 遵守 STOP 规则
- 没读 codecov.yml / ci.yml 现有 codecov 接入状态 (上轮已 verify codecov.yml 不存在 + ci.yml 无 codecov-action), 复用上下文
- 没 WebFetch codecov-action v5 vs v6 实际 release tag (M-1 verify 归 a1 责任, tasks §2 stage 5 F-2 verify step 已锁)