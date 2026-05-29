# Engine MVP0 Alignment

## Round 28 Contract Manifests Status

Round 28 is complete as the manifest-based upgrade of the Round 27 feature checklist. The old strict checklist guard has been upgraded from a 30 item hard lock to a 35 feature hard lock: `features.yaml` has 35 business features, `feature-compliance-checklist.md` has 35 H3 entries, and the checklist has 35 collectable coverage references.

The current Round 28 manifest baseline is:

- `packages/graph-agent/spec/features.yaml`: 35 independently named business features. The manifest assigns exactly one primary owner for each of the 92 concrete `[F-v3-*]` error codes and each of the 33 `CallbackEvent` variants.
- `packages/graph-agent/spec/source_file_map.yaml`: all 121 `packages/graph-agent/src/graph_agent/**/*.py` files are mapped. The current clustering is 61 `feature` files and 60 `detail` files, with no unclassified source file.
- `packages/graph-agent/spec/contract_map.yaml`: the public API axis covers 65 symbols, the skill-spec axis covers 53 H2 sections, and the consumer axis covers stable exports, live consumers, and 6 vendor-only debt entries.
- `packages/graph-agent/scripts/validate_round28_manifest.py`: validates target test collection, primary owner uniqueness and completeness, source file coverage, feature/core-path reverse mapping, vendor-only coverage, public API coverage, contract feature id references, runtime compatibility patches, cutover attestation, and skill-spec anchor existence.
- `.github/workflows/ci.yml`: the graph-agent matrix job runs the Round 28 validator after the graph-agent pytest step. Any non-zero validator exit blocks the CI job.

The dual-run guard is intentionally still present. `packages/graph-agent/tests/test_feature_traceability_matrix.py` remains as the upgraded checklist guard and now locks the Round 28 baseline at 35. `packages/graph-agent/tests/test_round28_contract_manifests.py` is the fixture-based manifest guard with 18 tests. `packages/graph-agent/tests/test_round28_invariant_guards.py` adds 5 mechanism guards for prompt slots, middleware ordering, tool sandboxing, blackboard state mapping, and error registry shape.

Round 27 frozen contract docs remain unchanged: `docs/engine/public-api-contract.md` and `docs/engine/skill-spec/*.md` are still protected by the contract hash lock. Round 28 freezes `docs/engine/feature-compliance-checklist.md` as a generated checklist from `features.yaml`.

## Round 29 Complexity Gate & C901 Refactoring Status

Round 29 is complete as an internal refactor-only complexity gate pass. It enabled the graph-agent ruff C901 gate and refactored the remaining 13 high-complexity `src/graph_agent` helpers without changing the public contract, event surface, or frozen engine docs.

`packages/graph-agent/pyproject.toml` now has a package-local `[tool.ruff]` section with `extend = "../../pyproject.toml"`, `[tool.ruff.lint].extend-select = ["C901"]`, `[tool.ruff.lint.mccabe].max-complexity = 10`, and `[tool.ruff.lint.per-file-ignores]."scripts/**" = ["C901"]`. The two script-only validator violations (`_validate_features` at `scripts/validate_round28_manifest.py:130` and `main` at `scripts/validate_round28_manifest.py:246`) are intentionally exempted because the Round 28 manifest validator is a one-off contract gate script, not runtime engine code.

The 13 refactored src helpers are:

1. `execute` (`core/phase_nodes/llm_phase_node.py:80`, C901 44-><=10) — split into `_prepare_phase_runtime`, model resolve, tools, middleware, cognitive loop, and finalize helpers.
2. `run` (`core/harness.py:435`, C901 25-><=10) — split initial state, persistent preflight, RunContext, graph invoke, and success/crash finalize paths.
3. `on_event` (`callbacks/base.py:139`, C901 14-><=10) — converted to a Strategy/Table dispatcher pattern with legacy dispatch, typed-only dispatch, and per-event dispatchers.
4. `resume` (`core/harness.py:949`, C901 13-><=10) — split tool-call lookup, runtime inputs restore, storage restore, and heartbeat stop.
5. `parse_output_example` (`tools/dynamic_schema.py:71`, C901 12-><=10) — split output-example extraction, line classification, item-header parsing, and field-line parsing.
6. `_build_type_runtime` (`tools/dynamic_schema.py:316`, C901 12-><=10) — split scalar, `Literal[...]`, list runtime, and list enum validation.
7. `_parse_block_data` (`tools/md_to_json.py:332`, C901 12-><=10) — split block-line classification, nested-field flush, and list nested-child parsing.
8. `_coerce_value` (`cognitive/md2json.py:88`, C901 11-><=10) — split JSON-like parsing, integer/number/boolean scalar coercion, and array fallback.
9. `_validate_cross_references` (`config/llm_config.py:359`, C901 11-><=10) — split model-provider, role-model, and role-provider validation.
10. `_normalise_type` (`core/_predict_internal/stub.py:115`, C901 11-><=10) — split string alias normalization into a table-backed helper.
11. `_violation_for_call` (`core/purity.py:130`, C901 11-><=10) — split name-call and attribute-call purity violation checks.
12. `legacy_context_from_state` (`core/state.py:167`, C901 21-><=10) — split not-None, non-empty, and copied metadata buckets while preserving shallow-copy and `_`-field behavior.
13. `_wrap_tool_for_langchain` (`core/tool_wrapper.py:102`, C901 24-><=10) — split signature parsing, schema field construction, context/plain invocation helpers, and `StructuredTool` assembly.

Verification evidence from the Round 29 implementation run:

- `uv run ruff check --select C901 packages/graph-agent/`: 0 violations.
- Characterization baseline: 100 tests passed.
- Contract gates: 38 tests passed for public API, contract hash lock, Round 28 manifests, and Round 28 invariant guards.
- Full graph-agent test suite: 1171 passed, 2 skipped, 19 xfailed.

Golden contract invariants did not drift: 0 new `CallbackEvent` classes, 0 new public defs, `events.py` unchanged, and the 65 public API symbols, 92 error codes, 33 events, 53 skill-spec H2 sections, and Round 28 five mechanism guards all stayed stable.

Round 29 also locked the helper baseline with 8 characterization test files:

- `tests/tools/test_dynamic_schema_characterization.py` — `parse_output_example` and `_build_type_runtime`, 23 cases.
- `tests/tools/test_md_to_json_helpers_characterization.py` — `_parse_block_data`, 7 cases.
- `tests/cognitive/test_md2json_characterization.py` — `_coerce_value`, 14 cases.
- `tests/config/test_llm_config_characterization.py` — `_validate_cross_references`, 6 cases.
- `tests/core/test_predict_stub_characterization.py` — `_normalise_type`, 12 cases.
- `tests/core/test_purity_characterization.py` — `_violation_for_call`, 14 cases.
- `tests/callbacks/test_on_event_characterization.py` — `on_event`, legacy Strategy/Table dispatch plus typed-only and fallback behavior.
- `tests/core/test_state_legacy_context_characterization.py` — `legacy_context_from_state`, shallow-copy semantics, `_`-field preservation, and invariant assertions.

## Round 30 P1/P2 External Quality Tools Onboarding — PR-1 Codecov

Round 30 P1/P2 接入 4 大外部质量工具: Codecov / SonarCloud / CodeQL / OpenSSF Scorecard. 拆 4 PR + 并行流 (按 design §1 + tasks §1).

PR-1 Codecov 已 ship (本 PR), 后续 PR-2/3/4 起独立 spec.

PR-1 内容:
- 新增 `codecov.yml` (仓库根) — 含 `coverage.status.project.default.target: auto` + `flags.backend` + `flags.graph-agent` 双 flag 维度; `fail_ci_if_error: false` 双 step (PR-1 report-only key)
- 改 `.github/workflows/ci.yml` — backend `quality-gates` job + graph-agent matrix job 各加 `codecov/codecov-action@v6` upload step
- matrix include 显式映射 `py_flag` (3.11→py311 / 3.12→py312 / 3.13→py313), 绕开 codecov flag 命名规则禁 `.` 限制
- 加 root `pyproject.toml` `[tool.coverage.run]` (`relative_files=true` / `parallel=true` / `omit`) + `[tool.coverage.report]` (`exclude_lines` / `show_missing` / `skip_covered`)

PR-1 是 report-only 接入: `fail_ci_if_error: false`, dashboard 显示基线但不阻 merge.

主控 PR-1 ship 后 24h 内访问 https://app.codecov.io/gh/SevenX77/agent-harness 拿 4 flags (backend/py311/py312/py313) 真实覆盖率基线, 写进 PR-REPORT Q7 模板 + 决策 PR-1.5 触发与否 (基线 < 78% → 强制 PR-1.5).

Verification evidence from the Round 30 PR-1 run:
- pytest test_round30_pr1_codecov_config.py: 3 passed (22 assertion, M-2/M-3 防 false positive 关键)
- 4 contract gate (test_public_api_contract / test_contract_hash_lock / test_round28_contract_manifests / test_round28_invariant_guards): 38 passed
- 黄金原则 verify: 65 public API / 92 errors / 33 events / 53 H2 / 14 FROZEN docs / R28 5 机制 — 全零碰

Audit chain:
- a2 思路复核 (cancel 早, design rev2 已 OK)
- a3 PM 替身 audit 三轮 (design rev2 7 catch / tasks rev2 6+2 catch / PR-1 src 偏移 3 should-fix), 全 a1 接受落地
- 主控 grep + pytest + curl 实证全程

## Round 30 P1/P2 External Quality Tools Onboarding — PR-2 SonarCloud

PR-2 SonarCloud 已 ship (本 PR), 接 PR-1 Codecov 后第 2 个外部质量工具.

PR-2 内容:
- 新增 `sonar-project.properties` (仓库根, 12 行) — 含 `sonar.organization=sevenx77` + `sonar.projectKey=SevenX77_agent-harness` + `sonar.host.url=https://sonarcloud.io` + `sonar.sources` + `sonar.tests` + `sonar.python.version=3.11,3.12,3.13` + `sonar.python.coverage.reportPaths=coverage-backend.xml,coverage-graph-agent.xml` + `sonar.exclusions` + `sonar.test.exclusions`
- 改 `.github/workflows/ci.yml` (+32 行, 3 处):
  - `quality-gates` job 加 `actions/upload-artifact@v4` upload backend coverage XML 作 artifact `coverage-backend`
  - `graph-agent-tests` matrix job 加 `actions/upload-artifact@v4` upload graph-agent coverage XML, name `coverage-graph-agent-py${{ matrix.python-version }}` (按 matrix 区分)
  - 新增 `sonar-scan` job, `needs: [quality-gates, graph-agent-tests]`, 用 `actions/checkout@v4` (`fetch-depth: 0`) + `actions/download-artifact@v4` (`pattern: coverage-*` + `merge-multiple: true`) + `SonarSource/sonarqube-scan-action@v8` (env `SONAR_TOKEN` + `SONAR_HOST_URL`)

Action 版本 verify (PM 2026-05-29): `sonarqube-scan-action` latest stable 跳 v4→v8 (v8.0.0 唯一 breaking 是 `skipSignatureVerification` 默认 true→false 安全增强, yaml usage 兼容 v4), 主控 + a1 双 curl verify 后锁 @v8.

PR-2 是 report-only 接入: CI 不阻 merge, SonarCloud dashboard 使用 "Sonar Way" 默认 quality gate. 等 Codecov M1 真实基线与 Sonar "Coverage on new code >= 80%" 目标一致后, 再由后续 PR 切硬门.

stage 2.5 前置 (PM 在 ship 后做): sonarcloud.io 控制台建 organization `sevenx77` + project `SevenX77_agent-harness` + 绑 `SONAR_TOKEN` GitHub secret. SonarQube Scan action 只跑扫描, 不自动建 Cloud project.

Verification evidence from the Round 30 PR-2 run:
- pytest test_round30_pr2_sonarcloud_config.py: 2 passed (21 assertion, 含 a3 audit 补的 SF-1/SF-2/SF-3 6 条 must-fix)
- 4 contract gate: 38 passed
- 黄金原则零碰 物理实证: `git diff --stat HEAD -- src/ docs/engine/ contract-gate tests/ spec/` empty diff → 65 API / 92 errors / 33 events / 53 H2 / 14 FROZEN docs / R28 5 机制 全静

Audit chain:
- a3 PM 替身 audit 两轮 (tests-first 3 must-fix / src 0 must-fix), 必修全 a1 接受落地
- 主控 grep + pytest + curl 实证全程

NTH (defer 到 PR-3 周期): `sonar.exclusions` / `sonar.test.exclusions` 在 properties 落地但 test 没断言锁; 后续 PR 改 properties 时漏改 exclusions test 仍绿.

## Round 30 P1/P2 External Quality Tools Onboarding — PR-3 CodeQL

PR-3 CodeQL 已 ship (本 PR), 接 PR-1 Codecov + PR-2 SonarCloud 后第 3 个外部质量工具 (4 个里).

PR-3 内容:
- 新增 `.github/workflows/codeql.yml` (29 行) — Python 静态安全扫描 (SAST):
  - on: push.branches[main] + pull_request.branches[main] + schedule cron `"0 6 * * 1"` (周一 06:00, 跟 PR-4 Scorecard 07:00 错开 1 小时避 GitHub Actions runner 争用)
  - permissions: actions:read + contents:read + security-events:write (上报 SARIF 必需)
  - jobs.analyze: ubuntu-latest, name "Analyze (Python)"
  - steps: actions/checkout@v4 → github/codeql-action/init@v4 (languages: python + build-mode: none + queries: security-extended) → github/codeql-action/analyze@v4

Action 版本 verify (PM 2026-05-29): `github/codeql-action` latest stable = v4.36.0 (2026-05-22, non-prerelease). spec lock major `@v4` (跟 PR-1 @v6 / PR-2 @v8 同样 GitHub Actions 最佳实践 major pinning).

PR-3 是 report-only 接入: CI 不阻 merge, 扫描结果上报 GitHub Code Scanning Security tab. 等首轮 high/critical 基线清零后, 再由后续 PR 切硬门.

YAML 工程细节: codeql.yml 用 `"on":` (引号) 避免 PyYAML safe_load 把 unquoted `on` 解析成 boolean True (YAML 1.1 quirk, GitHub Actions parser 不受影响). a3 audit 实证 (`yaml.safe_load('on: foo')` 返 `{True: 'foo'}` vs `yaml.safe_load('"on": foo')` 返 `{'on': 'foo'}`), 工程修正合理.

Python 解释型语言, `build-mode: none` 必须 (CodeQL 不需 build artifact, 直接扫源码). `queries: security-extended` 加 mature SAST 规则集 (基础 `security-and-quality` 之上).

Verification evidence from the Round 30 PR-3 run:
- pytest test_round30_pr3_codeql_config.py: 2 passed (21 assertion, 含 a3 audit 补 SF-1 cron 具体值 lock)
- 4 contract gate: 38 passed
- 黄金原则零碰 物理实证: src 仅 2 untracked 新文件 (codeql.yml + test py), 零 modified 触及 65 API / 92 errors / 33 events / 53 H2 / 14 FROZEN docs / R28 5 机制

Audit chain:
- a3 PM 替身 audit 两轮 (tests-first 0 must-fix + 1 should-fix SF-1 / src 0 must-fix), 必修全 a1 接受落地
- 主控 grep + pytest + curl 实证全程

NTH (defer to PR-4 周期): jobs.analyze.name display name 断言 / step display name 断言 / helper fixture 化.
