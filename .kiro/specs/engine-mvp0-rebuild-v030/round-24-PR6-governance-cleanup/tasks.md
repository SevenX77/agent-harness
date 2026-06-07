# WS3 PR-6 Tasks: Governance Cleanup 零风险纯减法

## Cutover Discipline

本 PR 只做治理收尾：删除已失效 API / 死代码，并修正一段过时文档。范围必须保持纯减法或文档纠偏，非 [BREAKING]，不新增兼容层、不引入新行为。

实施注意：
- 纯删除任务没有传统 tests-first 红灯；验收以删除后全量测试不崩和 grep 实证 0 残留为准。
- 不删除仍有价值的 parser 测试。`packages/graph-agent/tests/core/test_parse_skill_file.py` 还覆盖 `parse_markdown_parts`，只能删除 `parse_skill_file` 相关 import 和用例，保留并继续运行 `parse_markdown_parts` 测试。
- `packages/graph-agent/src/graph_agent/__init__.py` 当前没有真实 re-export `parse_skill_file`，但 docstring 仍提到该内部 helper；为满足残留引用清理，应删除该 docstring 提及。
- 不修改 Studio、Tauri、gateway、运行时行为或非 PR-6 文档。

已核对的当前事实：
- `packages/graph-agent/src/graph_agent/core/parser.py` 中 `parse_skill_file(path)` 只调用 `_fatal(...)`，消息为 `schema 2.0 parse_skill_file is not supported; use GRAPH.md`。
- `parse_skill_file` 残留在 `core/parser.py` docstring、定义、`__all__`，`packages/graph-agent/src/graph_agent/__init__.py` docstring，以及 `packages/graph-agent/tests/core/test_parse_skill_file.py` 的 import / 单个测试中。
- `packages/graph-agent/src/graph_agent/core/skill_validator.py` 存在，但 `packages/graph-agent/src` 与 `packages/graph-agent/tests` 下 0 import；活代码区提及是 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py` 的注释，配置残留是 `pyproject.toml` 的 mypy legacy quarantine entry。
- `DehydratedCompiledSkill` 只出现在 `docs/engine/mvp0/skill-compilation/mvp0-alignment.md`，源码 0 命中；当前缓存实现是 `dict` snapshot round-trip，版本开关在 `core/cache.py` 的 cache key payload `"format": "v2"`。

## Tasks

### 1. Remove: 删除 `parse_skill_file` 死 API

Files:
- `packages/graph-agent/src/graph_agent/core/parser.py`
- `packages/graph-agent/src/graph_agent/__init__.py`
- `packages/graph-agent/tests/core/test_parse_skill_file.py`

Steps:
- 从 `parser.py` 删除 `parse_skill_file(path)` 函数。
- 从 `parser.py` 的 `__all__` 删除 `"parse_skill_file"`。
- 清理 `parser.py` 顶部 docstring 和相关注释中对 `parse_skill_file` 的说明，改为只描述仍存在的 parser helper。
- 清理 `graph_agent/__init__.py` docstring 中对 `parse_skill_file` 的提及；该文件当前没有真实 import / `__all__` 导出需要删除。
- 在 `test_parse_skill_file.py` 中删除 `parse_skill_file` import 和 `test_parse_skill_file_is_removed_schema20_api` 用例。
- 保留同文件内所有 `parse_markdown_parts` 测试和必要的 `SkillLoadError` import。

Acceptance:
- `rg -n "parse_skill_file" packages/graph-agent/src packages/graph-agent/tests` 无输出。
- `uv run pytest packages/graph-agent/tests/core/test_parse_skill_file.py` 通过。

### 2. Remove: 删除 `skill_validator.py` 死代码并修正注释

Files:
- `packages/graph-agent/src/graph_agent/core/skill_validator.py`
- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py`
- `pyproject.toml`

Steps:
- 删除整个 `packages/graph-agent/src/graph_agent/core/skill_validator.py` 文件。
- 修正 `cognitive_flow.py` 中 `_validate_finish_args` 对缺失 `output_schema` 的注释，不再提 `skill_validator.py`。
- 新注释应描述当前现实：能进入 `finish_task` 校验的 phase 应已在 V0.3.0 编译/装配链路中带有 compiled output schema；缺失时属于上游 wiring 或绕过编译校验的错误，必须 fail loud。
- 从 `pyproject.toml` 的 mypy legacy quarantine module list 中删除 `graph_agent.core.skill_validator`。
- 不改 `_validate_finish_args` 的运行时错误行为。

Acceptance:
- `test ! -e packages/graph-agent/src/graph_agent/core/skill_validator.py`
- `rg -n "skill_validator" packages/graph-agent/src packages/graph-agent/tests pyproject.toml` 无输出。

### 3. Docs: 修正 skill compilation cache 过时示意

Files:
- `docs/engine/mvp0/skill-compilation/mvp0-alignment.md`

Steps:
- 重写 `Data Model / State` 中 `DehydratedCompiledSkill` / `schema_version` 代码块附近内容。
- 删除 `DehydratedCompiledSkill(BaseModel)` 示例和 snapshot 内 `schema_version` 字段说法。
- 改为准确描述当前实现：
  - `save_to_cache` 将 `CompiledSkill` 降为普通 JSON dict snapshot。
  - snapshot 顶层包含 `raw`、`manifest`、`nodes`、`subagents_by_phase`、`phase_tokens`。
  - `load_from_cache` 通过 `GraphManifest.model_validate(...)`、`TypeAdapter(PhaseAST)`、`build_subagent_input_model(...)`、`_inject_subagent_tools(...)` 重建运行期对象。
  - 缓存格式版本不是 snapshot 业务字段，而是 `compute_cache_key(...)` payload 中的 `"format": "v2"`，用于让旧 snapshot 自动 miss。
- 保持该章节其它 V0.3.0 编译、resolver、递归 guard 语义不变。

Acceptance:
- `rg -n "DehydratedCompiledSkill" docs/engine/mvp0/skill-compilation/mvp0-alignment.md packages/graph-agent/src packages/graph-agent/tests` 无输出。
- `rg -n "\"format\": \"v2\"|format.*v2|_dehydrate_compiled_skill|_rehydrate_compiled_skill" packages/graph-agent/src/graph_agent/core/cache.py docs/engine/mvp0/skill-compilation/mvp0-alignment.md` 能定位到代码事实与文档说明。

### 4. Governance: 注册 pytest marker

Files:
- `packages/graph-agent/pyproject.toml`

Steps:
- 在 `[tool.pytest.ini_options]` 下注册 `tier1` marker。
- marker 说明应表达该分层用于核心 / 冒烟层测试。
- 保留 `packages/graph-agent/tests/tools/test_dual_run_shadow.py` 上的 `@pytest.mark.tier1`，不通过删除测试标记规避 warning。
- grep 全仓 `@pytest.mark.*`，确认除 pytest 内置 mark 外没有其它未注册自定义 marker。

Acceptance:
- `uv run pytest packages/graph-agent/tests -q 2>&1 | grep -i "PytestUnknownMark"` 无输出。
- `uv run pytest packages/graph-agent/tests` 0 failed。

### 5. Final Verification: 全量测试与 grep gate

Files:
- No additional files expected.

Commands:
- `uv run pytest packages/graph-agent/tests`
- `uv run pytest packages/graph-agent/tests/core/test_parse_skill_file.py`
- `rg -n "parse_skill_file" packages/graph-agent/src packages/graph-agent/tests`
- `test ! -e packages/graph-agent/src/graph_agent/core/skill_validator.py`
- `rg -n "skill_validator" packages/graph-agent/src packages/graph-agent/tests pyproject.toml`
- `rg -n "DehydratedCompiledSkill" docs/engine/mvp0/skill-compilation/mvp0-alignment.md packages/graph-agent/src packages/graph-agent/tests`
- `rg -n "\"format\": \"v2\"|format.*v2" packages/graph-agent/src/graph_agent/core/cache.py`
- `uv run pytest packages/graph-agent/tests -q 2>&1 | grep -i "PytestUnknownMark"`
- `git diff --name-only`

Acceptance:
- `uv run pytest packages/graph-agent/tests` 0 failed。
- 删除目标在 src/tests/doc 约定范围内 0 残留引用。
- `git diff --name-only` 只出现 PR-6 允许的文件：
  - `.kiro/specs/engine-mvp0-rebuild-v030/round-24-PR6-governance-cleanup/tasks.md`
  - `packages/graph-agent/src/graph_agent/core/parser.py`
  - `packages/graph-agent/src/graph_agent/__init__.py`
  - `packages/graph-agent/tests/core/test_parse_skill_file.py`
  - `packages/graph-agent/src/graph_agent/core/skill_validator.py`
  - `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py`
  - `pyproject.toml`
  - `packages/graph-agent/pyproject.toml`
  - `docs/engine/mvp0/skill-compilation/mvp0-alignment.md`
- 不出现 skip/xfail/collect_ignore 或弱化测试断言。
