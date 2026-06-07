---
spec: engine-mvp0-rebuild-v030/round-12-PR-delta-skill-resolution-cutover
phase: PR δ (skill-resolution hard cutover)
owner: a1 主笔 tasks.md / a2 spec author / a3 PM-proxy audit
工程量: 36h (Resolver-only 24h, 含 Studio backend migration; SUBGRAPH Smoke 12h)
依赖: PR α (#91) / PR γ (#92) / PR β (#93) 已 ship, main green
---

# PR δ: Skill Resolution Hard Cutover Tasks

## §0 Scope 和硬边界

PR δ 只做 skill-resolution hard cutover: 所有跨 skill 寻址从 legacy 相对路径切到 `target_skill + SkillResolverProtocol`。本 PR 必须删除 subagent legacy path fallback, 强制核心入口显式接收 `skill_resolver`, 并补 SUBGRAPH `target_skill` 最小 compile/runtime smoke。

本 PR 不做 γ2 的 state/IO 隔离。SUBGRAPH 在 PR δ 只完成“如何找到 child skill root 并能跑 smoke”, 不改变 child graph blackboard isolation、phase_outputs 规范化或 smart reducer 语义。

继承不动:

- ModelResolverProtocol 和 Gateway 行为不改。
- PR γ 的 Agent `exit_contract` 删除、validator bool、middleware order 不改。
- PR β 的 CognitiveFlowMiddleware `finish_task` / `ask_clarification` 接管不改。

## §1 Tests-first 总顺序

PR δ 按 SOP-05 / SOP-08 执行, 合并是最后一步。红灯测试先落地, src 只能为让红灯变绿而改。每个 src 改动必须在同 PR 携带对应 unit/integration/smoke 测试。

依赖图:

```text
δ.1 tests-first resolver contract
  ├─> δ.2 tests-first subagent path removal
  ├─> δ.3 tests-first required resolver entrypoints
  ├─> δ.4 tests-first Studio backend injection
  └─> δ.5 tests-first SUBGRAPH target_skill smoke
        └─> δ.6-δ.10 src implementation
              └─> δ.11 docs/report
                    └─> δ.12 ship gate
```

## §2 δ.1 Red tests: resolver error contract and code normalization (1.5h)

Files:

- `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:18`
- `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:35`
- `packages/graph-agent/tests/core/test_skill_resolver_protocol.py:1`
- `docs/engine/mvp0/skill-spec/10-skill-resolver-protocol-spec.md:33`
- `docs/engine/mvp0/skill-spec/11-error-code-spec.md:147-151`

Tasks:

- Add failing tests asserting invalid skill id raises `[F-v3-resolver-skill-id-invalid]`, not current `[F-v3-invalid-skill-id]`.
- Add failing tests for resolver miss `[F-v3-skill-not-registered]`.
- Add failing tests for resolver returning non-directory or directory without `GRAPH.md` as `[F-v3-resolver-path-invalid]`.
- Add failing tests for missing resolver as `[F-v3-resolver-missing]` at compile/assembly boundaries.

Cutover discipline:

- No src change in this task.
- Tests must assert exact error code strings, not broad `Exception`.

Acceptance:

- These tests fail on current main for invalid-id code and missing-resolver code.

Dependencies: none.

## §3 δ.2 Red tests: remove `SubagentSpec.path` and legacy fixtures (2h)

Files:

- `packages/graph-agent/src/graph_agent/core/manifest.py:97-110`
- `packages/graph-agent/src/graph_agent/core/loader.py:362-388`
- `packages/graph-agent/src/graph_agent/core/loader.py:488-524`
- `packages/graph-agent/tests/core/test_v21_subagents_loader.py`
- `packages/graph-agent/tests/core/test_skill_resolver_protocol.py`
- `packages/graph-agent/tests/fixtures/subagent_minimal/`
- new `packages/graph-agent/tests/fixtures/v030_skill_registry/`

Tasks:

- Add failing test that `phase_config.subagents[].path` is rejected by AST/frontmatter validation.
- Add failing test that `target_skill` is required on every subagent.
- Add failing grep-style test that active fixtures no longer contain `path: subskills/`.
- Add replacement registry fixture pattern under `v030_skill_registry`: parent and child skill roots are flat siblings, linked by `target_skill`.
- Add failing integration test that parent Agent subagent compiles only when resolver is passed.

Cutover discipline:

- Do not keep legacy `path` test as compatibility coverage.
- Delete or rewrite path-based fixture users in the implementation phase; no `pytest.mark.skip`.

Acceptance:

- `rg "path: subskills|_resolve_subagent_root|SubagentSpec.path" packages/graph-agent/src packages/graph-agent/tests` has no active match after implementation.

Dependencies: δ.1.

## §4 δ.3 Red tests: required `skill_resolver` entrypoints (3h)

Files:

- `packages/graph-agent/src/graph_agent/core/compiler.py:41-47`
- `packages/graph-agent/src/graph_agent/core/runner.py:162-175`
- `packages/graph-agent/src/graph_agent/core/runner.py:243`
- `packages/graph-agent/src/graph_agent/core/runner.py:471`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:69-75`
- `packages/graph-agent/src/graph_agent/core/loader.py:145-149`
- `packages/graph-agent/src/graph_agent/core/loader.py:251`
- `packages/graph-agent/tests/core/`
- `packages/graph-agent/tests/integration/`
- `packages/graph-agent/tests/e2e/`

Tasks:

- Add failing tests that public `compile_skill`, `SkillLoader.compile_skill`, `assemble_graph`, `run_skill`, and runner helper entrypoints require explicit `skill_resolver`.
- Add test-only `InMemorySkillResolver` / `NoopSkillResolver` helper and use it in tests that are not specifically testing missing resolver.
- Add failing test that cache behavior is not silently keyed differently by resolver absence; since resolver is required, no code path should rely on `skill_resolver is None` for cache.
- Add migration checklist for existing tests calling engine entrypoints without resolver.

Cutover discipline:

- Test migration happens in same PR as signature change.
- Do not create default global resolver or fallback resolver.

Acceptance:

- Grep guard after implementation: `rg "skill_resolver: SkillResolverProtocol \\| None|skill_resolver=None|skill_resolver is None" packages/graph-agent/src/graph_agent/core` returns no unintended production entrypoint match.

Dependencies: δ.1, δ.2.

## §5 δ.4 Red tests: Studio backend resolver injection migration (2h)

Files:

- `apps/studio/backend/app/services/predictor.py:72`
- `apps/studio/backend/app/services/predictor.py:219`
- `apps/studio/backend/app/services/validator.py:79`
- `apps/studio/backend/app/services/run_manager.py:231`
- `apps/studio/backend/app/services/skills.py:294`
- `apps/studio/backend/app/services/skills.py:313`
- `apps/studio/backend/app/services/skills.py:1058`
- `apps/studio/backend/app/services/skills.py:1072`
- `apps/studio/backend/app/services/skill_resolver.py`
- `apps/studio/backend/tests/`

Tasks:

- Add failing tests that Studio run, predict, validation, and skill compile helpers pass a backend `StudioSkillResolver` or equivalent explicit resolver into Engine calls.
- Add smoke test for missing/unregistered skill id surfacing structured resolver error through Studio path.
- Add tests that existing Studio operations not involving child skills still pass an explicit no-op or Studio resolver.

Cutover discipline:

- Studio backend migration is same PR as engine signature break. Do not split.
- Do not mutate frontend/Tauri in PR δ unless a backend test proves it is required.

Acceptance:

- Grep guard after implementation: `rg "compile_skill\\(|SkillLoader\\(.*compile_skill|run_skill\\(" apps/studio/backend/app/services` shows every Engine call has explicit resolver injection or a local wrapper that injects it.

Dependencies: δ.3.

## §6 δ.5 Red tests: SUBGRAPH `target_skill` compile/runtime smoke (3h)

Files:

- `packages/graph-agent/src/graph_agent/core/manifest.py:146-152`
- `packages/graph-agent/src/graph_agent/core/loader.py:1099-1116`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:191-208`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:711-724`
- new `packages/graph-agent/tests/core/test_v030_subgraph_target_skill.py`

Tasks:

- Add failing AST test: `SubgraphNodeAST.sub_skill_ref` rejected, `target_skill` required.
- Add failing loader test: `SUBGRAPH.md` with `target_skill` parses and calls resolver during compile/assembly path.
- Add failing runtime smoke: parent graph SUBGRAPH phase resolves child root through `SkillResolverProtocol` and invokes child graph.
- Assert PR δ does not implement γ2 isolation: child graph state/IO behavior remains current runtime semantics unless explicitly changed by resolver handoff.

Cutover discipline:

- SUBGRAPH smoke must stay focused on resolver closure, not blackboard isolation.
- No `_resolve_sub_skill_path` path fallback remains after implementation.

Acceptance:

- `rg "sub_skill_ref|_resolve_sub_skill_path" packages/graph-agent/src packages/graph-agent/tests` has no active production/test dependency except historical docs if scoped outside src/tests.

Dependencies: δ.1, δ.3.

## §7 δ.6 Src: normalize resolver error codes and protocol helper (2h)

Files:

- `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:18-67`
- `packages/graph-agent/src/graph_agent/core/exceptions.py`
- `packages/graph-agent/tests/core/test_skill_resolver_protocol.py`

Tasks:

- Change invalid id code to `[F-v3-resolver-skill-id-invalid]`.
- Ensure invalid returned path uses `[F-v3-resolver-path-invalid]`, not generic not-registered.
- Add/normalize missing resolver helper so callers use `[F-v3-resolver-missing]`.
- Preserve `SkillResolutionError` as the resolver-domain exception type.

Cutover discipline:

- Only resolver-domain errors change here; do not touch model resolver / gateway error codes.

Acceptance:

- δ.1 tests green.

Dependencies: δ.1.

## §8 δ.7 Src: hard remove subagent legacy path fallback (4h)

Files:

- `packages/graph-agent/src/graph_agent/core/manifest.py:97-110`
- `packages/graph-agent/src/graph_agent/core/loader.py:362-424`
- `packages/graph-agent/src/graph_agent/core/loader.py:488-524`
- `packages/graph-agent/tests/core/test_v21_subagents_loader.py`
- `packages/graph-agent/tests/core/test_skill_resolver_protocol.py`
- `packages/graph-agent/tests/fixtures/subagent_minimal/`
- `packages/graph-agent/tests/fixtures/v030_skill_registry/`

Tasks:

- Delete `SubagentSpec.path`.
- Make `SubagentSpec.target_skill` required.
- Delete `_resolve_subagent_root`.
- Simplify `_compile_subagent_metadata` to always call `resolve_skill_root(skill_resolver, spec.target_skill)`.
- Migrate path-based tests and fixtures to flat registry + resolver fixture.
- Ensure dynamic subagent tool metadata keeps `target_skill` and no longer exposes legacy `subagent_path` as path provenance.

Cutover discipline:

- No compatibility alias for `path`.
- No branch that recovers path from phase root.

Acceptance:

- δ.2 tests green.
- Grep guard: no `_resolve_subagent_root`; no `SubagentSpec.path`; no `path: subskills` in active tests.

Dependencies: δ.2, δ.6.

## §9 δ.8 Src: require resolver at engine entrypoints (4h)

Files:

- `packages/graph-agent/src/graph_agent/core/compiler.py:41-65`
- `packages/graph-agent/src/graph_agent/core/runner.py:162-175`
- `packages/graph-agent/src/graph_agent/core/runner.py:243`
- `packages/graph-agent/src/graph_agent/core/runner.py:471-491`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:69-75`
- `packages/graph-agent/src/graph_agent/core/loader.py:145-149`
- `packages/graph-agent/src/graph_agent/core/loader.py:251`
- `packages/graph-agent/src/graph_agent/core/skill_tool_factory.py:107`
- `packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py:225`
- `packages/graph-agent/src/graph_agent/tools/md_to_json.py:565`

Tasks:

- Change public entry signatures to `skill_resolver: SkillResolverProtocol` without default.
- Update internal facade and nested calls to pass resolver explicitly.
- Update tests and test helpers with explicit `NoopSkillResolver` or registry resolver.
- Remove cache branches that only exist for `skill_resolver is None`.
- Check nested tool wrappers that call `run_skill` and either require resolver in their own construction or fail with `[F-v3-resolver-missing]`.

Cutover discipline:

- Do not use a module-level singleton resolver.
- Do not keep optional resolver for "pure" tests; pure tests pass no-op resolver explicitly.

Acceptance:

- δ.3 tests green.
- Grep guard for optional resolver in core entrypoint files passes.

Dependencies: δ.3, δ.6, δ.7.

## §10 δ.9 Src: Studio backend resolver injection (4h)

Files:

- `apps/studio/backend/app/services/skill_resolver.py`
- `apps/studio/backend/app/services/predictor.py:72`
- `apps/studio/backend/app/services/predictor.py:219`
- `apps/studio/backend/app/services/validator.py:79`
- `apps/studio/backend/app/services/run_manager.py:231`
- `apps/studio/backend/app/services/skills.py:294`
- `apps/studio/backend/app/services/skills.py:313`
- `apps/studio/backend/app/services/skills.py:1058`
- `apps/studio/backend/app/services/skills.py:1072`
- `apps/studio/backend/tests/`

Tasks:

- Reuse or update Studio backend resolver implementation so it conforms to required `SkillResolverProtocol`.
- Inject resolver into every Studio backend Engine call affected by PR δ.
- Add tests for run, predict, validation, and skills service compile paths.
- Ensure Studio skill import/registry miss maps to `[F-v3-skill-not-registered]` or `[F-v3-resolver-path-invalid]`.

Cutover discipline:

- Studio backend is not optional in this PR because Engine entry signatures become breaking.
- Do not implement frontend/Tauri UX unless backend tests require a new public route; this PR is backend migration only.

Acceptance:

- δ.4 tests green.
- `pytest apps/studio/backend/tests/` remains green.

Dependencies: δ.4, δ.8.

## §11 δ.10 Src: SUBGRAPH target_skill smoke implementation (8h)

Files:

- `packages/graph-agent/src/graph_agent/core/manifest.py:146-152`
- `packages/graph-agent/src/graph_agent/core/loader.py:1099-1116`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:191-208`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:711-724`
- `packages/graph-agent/tests/core/test_v030_subgraph_target_skill.py`
- `packages/graph-agent/tests/core/test_v21_graph_assembly.py`

Tasks:

- Remove `SubgraphNodeAST.sub_skill_ref`.
- Make `SubgraphNodeAST.target_skill` required.
- Parse `SUBGRAPH.md` target from frontmatter/body shape agreed in design.
- Replace `_resolve_sub_skill_path(phase_ast.sub_skill_ref)` with resolver-based `resolve_skill_root(skill_resolver, phase_ast.target_skill)`.
- Add compile smoke and runtime smoke for SUBGRAPH `target_skill`.
- Keep state/IO isolation unchanged and document the γ2 boundary in tests.

Cutover discipline:

- Delete `_resolve_sub_skill_path` if no longer used.
- Do not introduce child blackboard isolation here.

Acceptance:

- δ.5 tests green.
- SUBGRAPH smoke is green under current runtime semantics.

Dependencies: δ.5, δ.6, δ.8.

## §12 δ.11 Docs sync and PR report (1.5h)

Files:

- `docs/engine/mvp0/skill-resolution/logic-explained.md`
- `docs/engine/mvp0/skill-resolution/mvp0-alignment.md`
- `.kiro/specs/engine-mvp0-rebuild-v030/round-12-PR-delta-skill-resolution-cutover/PR-REPORT.md`
- `.kiro/specs/engine-mvp0-rebuild-v030/round-12-PR-delta-skill-resolution-cutover/{requirements,design,research,tasks}.md`

Tasks:

- Update logic-explained to current code translation after implementation.
- Remove statements saying legacy `path` is still current behavior.
- Add PM-friendly PR report with `设计 / 实现 / 验收` sections.
- Mention honest scope: PR δ closes resolver seeking, but γ2 still owns state/IO isolation.

Cutover discipline:

- Docs sync happens after src/tests are green; do not pre-document unimplemented behavior.

Acceptance:

- Docs no longer describe `_resolve_subagent_root` / `SubagentSpec.path` as active current behavior.

Dependencies: δ.6-δ.10.

## §13 δ.12 Ship gate and merge readiness (1h)

Files:

- whole repo, no new functional files unless a gate reveals test/doc drift.

Required commands:

```bash
pytest packages/graph-agent/tests/
pytest apps/studio/backend/tests/
ruff check packages/graph-agent/src packages/graph-agent/tests apps/studio/backend/app apps/studio/backend/tests
mypy packages/graph-agent/src apps/studio/backend/app
rg "SubagentSpec\\.path|_resolve_subagent_root|path: subskills|sub_skill_ref|_resolve_sub_skill_path|\\[F-v3-invalid-skill-id\\]" packages/graph-agent/src packages/graph-agent/tests apps/studio/backend/app apps/studio/backend/tests
gh run list --branch main --limit 3
```

Expected grep result:

- No active src/test/backend matches for removed subagent path fallback.
- No active `sub_skill_ref` / `_resolve_sub_skill_path`.
- No `[F-v3-invalid-skill-id]`; use `[F-v3-resolver-skill-id-invalid]`.

Cutover discipline:

- No skipped hooks.
- No partial pytest presented as ship gate.
- Merge only after CI green and review/audit PASS.

Acceptance:

- All local gates pass.
- PR CI green.
- a2/a3 audit findings closed or explicitly documented as non-blocking.

Dependencies: δ.11.

## §14 工程量汇总

| Task | 工时 |
|---|---:|
| δ.1 Resolver error contract red tests | 1.5h |
| δ.2 Subagent path removal red tests | 2h |
| δ.3 Required resolver entrypoint red tests | 3h |
| δ.4 Studio backend injection red tests | 2h |
| δ.5 SUBGRAPH target_skill red tests | 3h |
| δ.6 Resolver error code src | 2h |
| δ.7 Subagent hard cutover src | 4h |
| δ.8 Required resolver entrypoints src | 4h |
| δ.9 Studio backend migration src | 4h |
| δ.10 SUBGRAPH target_skill smoke src | 8h |
| δ.11 Docs sync + PR report | 1.5h |
| δ.12 Ship gate | 1h |
| **合计** | **36h** |

说明: design 锁定的核心预算是 36h = Resolver-only 24h + SUBGRAPH Smoke 12h。上表为了 tests-first 和 ship gate 显式拆项, 其中 Studio backend migration 计入 Resolver-only; SUBGRAPH 子集由 δ.5 + δ.10 + 对应 docs/gate 验收组成。

## §15 CI Gate Checklist

- [ ] `pytest packages/graph-agent/tests/`
- [ ] `pytest apps/studio/backend/tests/`
- [ ] `ruff check packages/graph-agent/src packages/graph-agent/tests apps/studio/backend/app apps/studio/backend/tests`
- [ ] `mypy packages/graph-agent/src apps/studio/backend/app`
- [ ] `rg "SubagentSpec\\.path|_resolve_subagent_root|path: subskills|sub_skill_ref|_resolve_sub_skill_path|\\[F-v3-invalid-skill-id\\]" packages/graph-agent/src packages/graph-agent/tests apps/studio/backend/app apps/studio/backend/tests` returns no active cutover residue.
- [ ] `gh run list --branch main --limit 3` confirms recent main CI green.
- [ ] No skipped hooks, no `pytest -k` partial green presented as full green.
- [ ] Unit + integration + Studio backend tests updated in same PR as breaking signature changes.
