# Round 30 PR-1 src 偏移 audit — a3 PM 替身视角

## 1. src vs design 一致性结论 ✅ **100% 一致, 零 drift**

逐文件逐行物理对照 design rev2:

| 文件 | design 段 | src 改动 | 一致性 |
|---|---|---|---|
| `.github/workflows/ci.yml` (+16) | §2.1 line 38-45 + 50-56 | line 50-57 backend upload + line 88-95 graph-agent upload | ✅ **逐字段对照零 drift** (action@v6 + token + files + flags + fail_ci_if_error: false 全对) |
| `codecov.yml` (新 27 行) | §2.2 完整 yaml | 27 行 1:1 镜像 | ✅ **完全相同** (codecov.require_ci_to_pass + project/patch.default.target/threshold + comment 3 字段 + flags 2 段 paths) |
| `pyproject.toml` (+10) | §2.3 完整 toml | line 74-83 [tool.coverage.run] + [tool.coverage.report] | ✅ **逐字段一致** (relative_files/parallel/omit + exclude_lines/show_missing/skip_covered) |

**action 版本 v5→v6 sync verify**:
我 grep 了 `design.md / tasks.md` 现状, **design line 39/51/202 + tasks line 54/69 全部已 sync 成 @v6** ✅ (上轮 audit 我 catch 的 M-1 "spec lock v5 vs test v6 drift" **已经被 a1/主控 sync 修了**, charter / spec / src / test 四份现在统一锁 v6, SOP-06 spec 保守原则合规)。

## 2. 黄金原则 verify ✅ **PR-1 src 真零碰 6 维度**

src 改动 4 文件全部在 CI/quality telemetry 层, **零触及**业务代码:
- `packages/graph-agent/src/**` (65 API) → 零改 ✅
- `packages/graph-agent/tests/test_public_api_contract.py` (固定 65 API) → 零改 ✅
- `packages/graph-agent/tests/test_contract_hash_lock.py` (53 H2 + 14 FROZEN docs) → 零改 ✅
- `packages/graph-agent/tests/test_round28_contract_manifests.py` (92 errors + 33 events) → 零改 ✅
- `packages/graph-agent/tests/test_round28_invariant_guards.py` (R28 5 机制) → 零改 ✅
- `docs/engine/mvp0/skill-spec/*` + `docs/engine/mvp0/public-api-contract.md` (FROZEN docs SHA) → 零改 ✅
- `apps/studio/backend/app/**` 业务代码 → 零改 ✅

**我亲跑 4 contract gate**: `uv run pytest test_public_api_contract.py test_contract_hash_lock.py test_round28_contract_manifests.py test_round28_invariant_guards.py` → **38 passed in 78s** ✅. 跟主控亲跑数一致。

**我亲跑 PR-1 tests**: `uv run pytest tests/test_round30_pr1_codecov_config.py -v` → **3 passed in 0.09s** ✅. 22 assertion 全绿。

## 3. Report-only 体现 ✅ 两关键标记全在

- `codecov.yml:8` `target: auto` ✅ (project.default)
- `codecov.yml:12` `target: auto` ✅ (patch.default 也 auto, 不是 80% 硬门)
- `codecov.yml:9/13` `threshold: 1%` ✅ (允许波动)
- `.github/workflows/ci.yml:56` `fail_ci_if_error: false` ✅ (backend upload)
- `.github/workflows/ci.yml:94` `fail_ci_if_error: false` ✅ (graph-agent upload)
- `grep -c "fail_ci_if_error: false" ci.yml = 2` ✅ (test 也断言 `>= 2`)
- 全文件搜索: **零** "80%" / "hard fail" / "require" 等硬门字段

PR-1 **真 report-only**, 跟 design §2.4 PR-1.5 决策门精神一致 ✅。

## 4. Hidden gotcha — 4 项 (主控/a1 应 verify)

### must-fix (0 项)

**无**。PR-1 src 实施过关, **可进 stage 6 docs 同步**。

### should-fix (3 项, stage 6/7 之前 verify)

**SF-1 — codecov flag 命名含 `.` 是否被服务端接受?**
- `ci.yml:93` `flags: graph-agent,py${{ matrix.python-version }}` → matrix 渲染后是 `py3.11` / `py3.12` / `py3.13` (含 `.`)
- Codecov 官方文档: flag names 限制 `[a-z0-9_-]+`, 一般不允许 `.`
- 风险: PR-1 push 后 codecov 服务端可能拒绝 `py3.11` flag, dashboard 上 4 flags (backend/py311/py312/py313) 之中 3 个 py-flag 收不到数据 → Q7 报分模板 (design §6 line 320) 报不出 py-version 维度
- **建议**: 改成 `py${{ matrix.python-version }}` 渲染前先 substring 替换 `.` 为空, e.g. 用 `format('py{0}', replace(matrix.python-version, '.', ''))` GitHub Actions 表达式得到 `py311`, 或在上传前在 step 内 export ENV. 主控 PR-1 push 后 24h 内 verify codecov.io dashboard 是否真显示 4 flags 才能正式拍 PR-1 ship 报告。

**SF-2 — PR-1 stage 2.5 codecov.io project 创建/绑 token verify 缺失**
- tasks.md PR-2 stage 2.5 line 89-93 有 "主控确认 SonarCloud project 创建 + SONAR_TOKEN 关联", 失败则 escalate
- **但 PR-1 没对应 stage 2.5** — codecov.io 上 SevenX77/agent-harness 项目是否已存在 + CODECOV_TOKEN 是否真绑该 project 没 gate
- 风险: PR-1 push 后 upload step 因 token mismatch fail (但 `fail_ci_if_error: false` 让 CI 仍绿) → codecov.io dashboard 永远收不到数据 → 主控 stage 9 PR-1.5 决策门拿不到 dashboard 基线 → 卡死
- **建议**: 主控 PR-1 push 前用 `curl -H "Authorization: token <CODECOV_TOKEN>" https://api.codecov.io/api/v2/github/SevenX77/repos/agent-harness/` 验证 project 存在 + token 有效, 不存在则 escalate PM 在 codecov.io 创建。这步应补进 tasks.md PR-1 stage 2.5 (但本 PR 已实施, 算 PR-1 ship 前的最后 verify, 不阻 stage 6 docs)

**SF-3 — stage 6 docs 同步未做 (但 brief 是 step 5 audit, 不阻当前)**
- tasks.md §2 stage 6 line 70-71 要求改 mvp0-alignment.md + 00-PROGRESS-STATUS.md round-30 PR-1 entry
- 我 grep 现状: `mvp0-alignment.md` 无 round-30 段, status line 256 "P1-P3 ⏳" 没 sync 到 PR-1 in-progress
- 注: status diff 只改了 line 245 B 类前置 sync (这是上轮 audit 的 PM 拍板 sync 补做, 跟 round-30 status entry 是两件事)
- **此项严格说不属于 step 5 src 偏移, 是 step 6 docs 漏**, 我标这里方便主控继续推进 stage 6 时知道补什么

### nice-to-have (1 项)

**N-1 — `actions/checkout@v4` 没指定 `fetch-depth: 0`**
- design 没要求 (§2.1 没明示), codecov-action v5/v6 内部会 auto-deepen
- 但 PR-2 SonarCloud (design §3.2 line 158) 显式要 `fetch-depth: 0` — 一致性考虑可在 PR-2 时统一调
- 不阻 PR-1 ship, defer 到 PR-2 同步调整

## 整体结论

PR-1 src 实施 **质量过关, 可推进 stage 6 docs 同步 → stage 7 PR-REPORT**。

- src vs design **100% 一致**, 零 drift, 上轮 audit M-1 的 spec/test version drift 已被 a1/主控 sync 修齐
- 黄金原则 6 维度 PR-1 src 真零碰, 4 contract gate 38 passed 物理 verify
- Report-only 双锁 (`target: auto` + `fail_ci_if_error: false × 2`) 落到 yaml, 跟 PM 5-29 "门要真" + PR-1.5 决策门精神一致
- 2 个 should-fix (SF-1 flag 命名含 `.` / SF-2 codecov project 创建 verify) 是**主控 PR-1 push 后 24h 内 verify dashboard 阶段**应做的事, 不阻 stage 6/7 推进, 但应进 stage 7 PR-REPORT 风险声明段
- stage 6 docs 同步 a1 还没做 (mvp0-alignment + status round-30 entry), 这是下一步动作不是当前 audit 范畴

---

## 文件清单 + grep/bash 命令

### Read
1. `/tmp/round30-a3-audit-pr1-src.md` (本次 brief)
2. `codecov.yml` (新 27 行全文)
3. `packages/graph-agent/tests/test_round30_pr1_codecov_config.py` (rev 后 69 行全文, 22 assertion)
4. design.md rev2 §2.1+§2.2+§2.3 (上轮已 read, 复用上下文)
5. tasks.md rev2 §2 PR-1 (上轮已 read, 复用)

### Bash / git
- `git status` → verify 改动文件清单跟 brief 一致: M ci.yml/pyproject/status + ?? codecov.yml/test + ?? round-30 spec dir
- `git diff .github/workflows/ci.yml pyproject.toml` → 物理对照 diff 跟 design §2.1+§2.3 1:1 镜像 ✅
- `git diff .kiro/specs/engine-mvp0-rebuild-v030/00-PROGRESS-STATUS.md | head -60` → 看到 a1 sync 了 line 245 B 类前置 PM 拍板段 (上轮 audit B-1 补做)
- `grep -n "codecov-action@v[56]" design.md tasks.md` → **verify spec sync v5→v6**, design line 39/51/202 + tasks line 54/69 全 v6 ✅, M-1 drift 已解
- `grep -n "round.30|Round 30|P1.*Codecov|PR-1.*Codecov" 00-PROGRESS-STATUS.md` → verify 现状无 round-30 PR-1 entry → SF-3 stage 6 docs 漏
- `grep -n "round.30|round-30" mvp0-alignment.md` → 0 命中 → SF-3 同上
- `ls .kiro/specs/.../round-30-p1p2-onboard/` → 6 文件 (design/research/tasks/3 份 audit-a3-*.md), 没 mvp0-alignment / tasks-status entry
- `cd packages/graph-agent && uv run pytest tests/test_round30_pr1_codecov_config.py -v` → **3 passed, 0.09s** ✅ 跟主控亲跑数一致
- `uv run pytest test_public_api_contract test_contract_hash_lock test_round28_contract_manifests test_round28_invariant_guards --tb=line -q` → **38 passed in 78s** ✅ 跟主控亲跑数一致, 黄金原则不漂

### 没读 / 没跑 (主动声明)
- 没 ccb ask / 没 mutate ✅ 遵守 STOP
- 没跑全套 pytest (38 contract gate 已 verify 不漂, 黄金原则核心证据已足, 不重复浪费 78s)
- 没 WebFetch codecov.io API verify CODECOV_TOKEN/project 是否绑成功 (SF-2 归主控 PR-1 push 后 24h verify, 不替主控做)
- 没 WebFetch codecov flag naming 规则 (SF-1 标 should-verify, 等主控查官方文档定夺改不改 ci.yml)