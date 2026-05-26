# WS3 PR-1 Tasks: 去掩盖与 Resolver 契约修复

## Cutover Discipline

本 PR 必须把“撤掉 resolver 默认值猴补丁”与“修复生产入口 resolver 注入”放在同一个原子变更内完成。不得先只撤 resolver 掩盖导致主干长期红灯，也不得只补生产代码而保留 `conftest.py` 对 resolver-required API 的默认值注入。

设计命名统一为 `LocalWorkspaceResolver`。`research.md` 中出现过的旧候选命名视为命名漂移，后续实现和文档均使用 `LocalWorkspaceResolver`。

PR-1 不删除语料布局迁移 deferral：`conftest.py` 中 V1/V2.1 语料相关的 `xfail(strict=False)`，以及 `test_loader_based_smoke.py` 的模块级 skip，属于 PR G Section 10，不属于 resolver demask。验收口径使用“resolver 范围诚实绿”，不锁死 `981 passed` 这类历史数字；现有语料 deferral 预期保留。

生产 resolver 落点必须明确：`skill_resolver_protocol.py` 保留为协议、错误和校验定义；具体文件系统实现放在 `graph_agent.core.local_workspace_resolver`，避免把 concrete implementation 塞进纯 protocol 文件。

## Tasks

### 1. Red: 删除 resolver 默认值猴补丁，暴露真实缺参红灯 [BREAKING]

Files:
- `packages/graph-agent/tests/conftest.py`

Steps:
- 删除 `_set_kw_default` helper。
- 删除 `pytest_configure` 中对 `compile_skill`、`assemble_graph`、`SkillLoader.compile_skill`、`load_workflow_from_md`、`run_skill`、`_run_skill_dict`、`_run_v030_skill_dict`、`build_skill_tool`、`parallel_map`、`md_to_json` 的 `skill_resolver` 默认值注入。
- 保留或重命名现有 `TestSkillResolver` / `TEST_SKILL_RESOLVER`，但只作为显式 fixture 的实现基础，不再改函数签名或 `__kwdefaults__` / `__signature__`。

Acceptance:
- `rg "__kwdefaults__|__signature__|_set_kw_default|pytest_configure" packages/graph-agent/tests/conftest.py` 不再命中 resolver 默认值注入逻辑。
- 在只完成本任务后运行受影响测试，应出现真实的 `TypeError: missing ... skill_resolver` 或 `[F-v3-resolver-missing]` 红灯，证明掩盖已移除。

### 2. Scope Guard: 保留语料 xfail/skip deferral，恢复 resolver 诚实测试面 [BREAKING]

Files:
- `packages/graph-agent/tests/conftest.py`
- `packages/graph-agent/tests/integration/skills/test_loader_based_smoke.py`

Steps:
- 保留 `pytest_collection_modifyitems` 中给 `_V21_CORPUS_DEFERRED_TESTS` / `_V1_SKILL_AWAITING_CUTOVER_TESTS` 添加 `pytest.mark.xfail(strict=False)` 的语料 deferral。
- 保留 `_V21_CORPUS_DEFERRED_TESTS` / `_V1_SKILL_AWAITING_CUTOVER_TESTS` 集合；它们记录的是 PR G Section 10 语料迁移债务，不是 resolver 缺参掩盖。
- 保留 `test_loader_based_smoke.py` 顶部 `pytest.skip(..., allow_module_level=True)`；不要在 PR-1 里顺手 unskip，该文件还包含与 resolver 无关的 loader/corpus 后续清理风险。
- 不新增任何 `xfail`、`skip` 或模块级 skip 来隐藏 resolver-missing 红灯。

Acceptance:
- `rg "strict=False|allow_module_level=True|_V21_CORPUS_DEFERRED_TESTS|_V1_SKILL_AWAITING_CUTOVER_TESTS" packages/graph-agent/tests/conftest.py packages/graph-agent/tests/integration/skills/test_loader_based_smoke.py` 仍只命中上述语料 deferral，不出现新的 resolver 掩盖。
- 在只完成任务 1-2 后运行测试，红灯应反映真实缺 resolver 问题；语料 deferral 继续保持预期 xfail/skip 状态。

### 3. Green: 新增生产级 `LocalWorkspaceResolver`

Files:
- `packages/graph-agent/src/graph_agent/core/local_workspace_resolver.py`
- `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py`
- `packages/graph-agent/src/graph_agent/__init__.py`
- `packages/graph-agent/tests/core/test_skill_resolver_protocol.py`

Steps:
- 在 `local_workspace_resolver.py` 中实现 `LocalWorkspaceResolver`，保持 `SkillResolverProtocol` 的强制注入设计，不把 `skill_resolver` 改回可选。
- `skill_resolver_protocol.py` 只保留 `SkillResolverProtocol`、`SkillResolutionError`、`validate_skill_id` 等协议/错误/校验定义；不要在该文件中放 concrete filesystem resolver。
- 暴露一个稳定 public import path，供 CLI、README 和测试共同使用；若 README 从 `graph_agent` 顶层导入，则同步更新 `__init__.py`。
- 构造参数接受 `search_paths: Iterable[str | Path] | None = None`；`None` 默认使用当前工作目录和当前工作目录下的 `skills/`，建议搜索顺序为 `Path.cwd()` 后 `Path.cwd() / "skills"`，以支持 CLI 传入显式 skill root 以及常见 workspace skills 目录。
- `resolve_skill(skill_id)` 必须先复用 `validate_skill_id`，再在 search paths 中支持两类映射：
  - 直接目录名：`base / skill_id`
  - dotted id：`base / skill_id.replace(".", "/")`
- 命中条件必须是目录且包含 `GRAPH.md`。
- 未命中时抛 `SkillResolutionError(skill_id, "...", code="[F-v3-skill-not-registered]")`，错误消息包含 search paths，便于 CLI 诊断。

Acceptance:
- 新单测覆盖：直接目录、`skills/` 子目录、dotted id、非法 skill id、未注册 skill。
- 不新增全局单例，不在 `compile_skill` / `run_skill` 内部自动创建 resolver。
- 不新增旧候选 resolver 命名。

### 4. Green: CLI 显式注入 `LocalWorkspaceResolver`

Files:
- `packages/graph-agent/src/graph_agent/core/runner.py`
- `packages/graph-agent/tests/core/test_runner_startup_invariants.py`

Steps:
- 在 `runner.main()` 解析参数后实例化 `LocalWorkspaceResolver`。
- CLI 默认 search paths 使用当前工作目录和 `./skills`；若 `--skill` 是目录路径，仍直接作为 root 执行，但 resolver 需用于 subgraph/subagent 解析。
- 调用 `run_skill(..., skill_resolver=resolver, ...)`。
- 增加自动化 CLI 回归测试：用 monkeypatch/fixture 驱动 `runner.main()`，拦截 `run_skill` 调用，断言调用包含显式 `skill_resolver`，且该对象是 `LocalWorkspaceResolver`。
- 自动化测试还要断言 resolver search paths 来自 CLI/workspace 上下文的确定性路径，例如当前工作目录与 `./skills`，不得依赖全局临时目录扫描。
- 保持 Bootstrap / dotenv / settings 的既有顺序约束。

Acceptance:
- 自动化测试在 `runner.main()` 遗漏 `skill_resolver` 时失败。
- `python -m graph_agent --skill <v0.3 skill root> --inputs '{}'` 不再因为缺少 `skill_resolver` 在入口处失败。
- `runner.main` 测试不依赖 `conftest.py` 默认值注入。

### 5. Green: 修复 `tools/dual_run_shadow.py` 的独立运行 resolver 注入

Files:
- `packages/graph-agent/tools/dual_run_shadow.py`
- `packages/graph-agent/tests/tools/test_dual_run_shadow.py`

Steps:
- 在 shadow 工具中实例化 `LocalWorkspaceResolver`，search paths 至少包含 `skill_root`、`skill_root.parent`、`skill_root.parent / "registry"`，以覆盖 fixture 中常见的 sibling/registry subskill 布局。
- `_run_v21` 调用 `compile_skill(skill_root, cache=False, skill_resolver=resolver)`。
- `assemble_graph(..., skill_resolver=resolver)`。
- 增加/调整回归测试，证明 `compile_skill` 与 `assemble_graph` 两条 shadow 路径都收到显式 resolver。
- 不通过 pytest fixture 或 monkeypatch 隐式补参。

Acceptance:
- `tests/tools/test_dual_run_shadow.py` 在无 `conftest.py` 猴补丁时通过。
- 直接运行 `python packages/graph-agent/tools/dual_run_shadow.py <skill_root> --chat-fixture hello-world` 不再因缺少 resolver 失败。

### 6. Green: 测试改成显式 resolver fixture

Files:
- `packages/graph-agent/tests/conftest.py`
- All affected `packages/graph-agent/tests/**/*.py`

Steps:
- 在 `conftest.py` 暴露显式 fixture，例如 `test_skill_resolver()`，返回当前 `TestSkillResolver` 实例或等价实现。
- fixture 必须只使用当前测试声明的 `tmp_path` / workspace roots / fixture roots，解析结果可预测、作用域清晰。
- 禁止使用 `/tmp/pytest-of-*` glob、`Path("/tmp")` 扫描、跨全局临时目录的 `rglob(skill_id)` fallback，或任何“碰巧找到别的测试产物”的解析逻辑。
- 批量修正所有直接调用 resolver-required API 的测试，显式声明 fixture 并传参：
  - `compile_skill(..., skill_resolver=test_skill_resolver)`
  - `assemble_graph(..., skill_resolver=test_skill_resolver)`
  - `SkillLoader().compile_skill(..., skill_resolver=test_skill_resolver)`
  - `load_workflow_from_md(..., skill_resolver=test_skill_resolver)`
  - `run_skill(..., skill_resolver=test_skill_resolver)`
  - `parallel_map(..., skill_resolver=test_skill_resolver)`
  - `md_to_json(..., skill_resolver=test_skill_resolver)`
  - `build_skill_tool(..., skill_resolver=test_skill_resolver)`
- 不修改生产函数签名来迁就测试。

Acceptance:
- `rg "compile_skill\\([^\\n]*\\)|assemble_graph\\([^\\n]*\\)|run_skill\\([^\\n]*\\)" packages/graph-agent/tests` 人工抽查确认 resolver-required 调用已显式传参，允许多行调用通过代码 review 覆盖。
- `rg "__kwdefaults__|__signature__|_set_kw_default" packages/graph-agent/tests` 无 resolver 默认值猴补丁命中。
- `rg 'pytest-of-|Path\("/tmp"\)|rglob\(skill_id\)' packages/graph-agent/tests` 无 fixture/global tmp 解析命中。
- `rg "strict=False|allow_module_level=True" packages/graph-agent/tests` 只命中任务 2 保留的语料 deferral。
- 全量测试达到诚实绿；不以固定 passed 数作为硬验收。

### 7. Green: README 示例按新契约更新 [BREAKING]

Files:
- `packages/graph-agent/README.md`

Steps:
- 将 Quick Start 和迁移示例从旧 `SKILL.md` 文件路径改为 V0.3 skill root / `GRAPH.md` 语义一致的示例。
- 示例中显式导入并实例化 `LocalWorkspaceResolver`。
- 示例调用 `run_skill(..., skill_resolver=resolver, ...)`。
- Public API 表与实际导出保持一致；不要继续写“12 names”或导出不存在的 `GraphAgentHarness`。

Acceptance:
- README 不再展示不传 `skill_resolver` 的 `run_skill` 示例。
- README 从任务 3 建立的同一个 public path 导入 `LocalWorkspaceResolver`。
- README 不再声称过期的 public API 数量。
- README 对 conftest 行为变更明确为测试内部 [BREAKING]，下游生产 API 的迁移路径是显式 resolver。

### 8. Final Verification: 证明无掩盖、入口可用、测试诚实绿

Files:
- No additional files expected.

Commands:
- `rg "__kwdefaults__|__signature__|_set_kw_default" packages/graph-agent/tests`
- `rg "strict=False|allow_module_level=True|_V21_CORPUS_DEFERRED_TESTS|_V1_SKILL_AWAITING_CUTOVER_TESTS" packages/graph-agent/tests/conftest.py packages/graph-agent/tests/integration/skills/test_loader_based_smoke.py`
- `rg 'pytest-of-|Path\("/tmp"\)|rglob\(skill_id\)' packages/graph-agent/tests`
- `rg "旧候选 resolver 命名" .kiro/specs/engine-mvp0-rebuild-v030/round-19-PR1-demask-resolver packages/graph-agent/src packages/graph-agent/tests packages/graph-agent/README.md`
- `uv run pytest packages/graph-agent/tests`
- CLI smoke using one V0.3 fixture skill root.
- dual-run shadow smoke using the hello-world/chat fixture path used by existing tests.

Acceptance:
- No resolver monkeypatch remains for this scope.
- Existing corpus non-strict xfail/module-level skip remain documented as PR G Section 10 deferral, not resolver-missing masks.
- No resolver fixture depends on global `/tmp` discovery or broad temp-dir globbing.
- No old resolver implementation/doc usage remains; only `LocalWorkspaceResolver`.
- Full suite is green under honest explicit resolver wiring.
- CLI and `dual_run_shadow.py` work outside pytest, with automated regressions proving explicit resolver injection.
