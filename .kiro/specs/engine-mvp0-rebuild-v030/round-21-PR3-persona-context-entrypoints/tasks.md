# WS3 PR-3 Tasks: Persona及死码簇拆除、Context 字典面与旧入口收口

## Cutover Discipline

本 PR 按 design v4 执行，全面根除 `build_graph_nodes` 等连带死码，不恢复 Persona，不深度重构 `md_to_json` / `md-patch`，也不改变 `run_skill` 的公开失败返回契约。

实施必须 tests-first：
- 先写 Context、`run_skill`、`md_to_json` deferred guard 红灯，并真实跑出失败。
- 再做生产代码转绿。
- Persona 相关测试是迁移，不是删除：保留 `_guard_v030_root` 对无效 V0.3 root 的拒绝断言，只去掉 Persona 语义和死词。
- `run_skill` 仍返回 `WorkflowResult(success=False, error=...)`，不得改成向公开调用方冒泡未捕获异常。
- PR-6 之前不尝试修复 `md-patch` 的旧 context 注入工具流；本 PR 只加 guard，避免裸漏 `KeyError("final_results")`。

已核对的当前断点：
- `core/skill_builder.py` 仍残留整个已废弃且调用即崩溃的 `build_graph_nodes` / `_inject_persona` 等闭环死码簇。
- `core/personas.py` 仍保留已废弃的 `resolve_persona` 业务实现。
- `cognitive/context_facade.py` 当前缺少 `__getitem__` / `__setitem__` / `__contains__` / `setdefault`。
- `tools/md_to_json.py` fallback 在 `run_skill(...)` 后直接读取 `result["context"]["final_results"]`，缺少 `result.success` guard。
- `_run_skill_dict` 当前对非 `GRAPH.md` 目录仍会进入 legacy load path，入口错误不够干净，且对外暴露错误码时存在丢失风险。

## Tasks

### 1. Red: Context 字典访问与真实 LOGIC action 红灯

Files:
- `packages/graph-agent/tests/**`

Steps:
- 新增或扩展 `Context` 单元测试，直接构造 `Context({"existing": 1}, phase_id="p", run_id="r")`。
- 断言以下行为目标：
  - `context["new_key"] = 123` 后底层黑板可读。
  - `context["existing"] == 1`。
  - `"existing" in context` 为真，缺失 key 为假。
  - `context.setdefault("items", []).append("x")` 能就地写回黑板。
  - 缺失 key 的 `context["missing"]` 抛 `KeyError("missing")`。
- 增加一个真实 LOGIC action 集成测试，优先复用 `packages/graph-agent/tests/fixtures/v030_e2e_pipeline/phases/score/actions/score.py` 中的 `context["segments"]` 路径，或构造等价最小 V0.3 LOGIC fixture。
- 集成测试必须执行到 `Context` facade 包装后的 action，而不是只直接 import action 函数。

Acceptance:
- 在不改生产代码时，新增单元测试因 `Context` 不支持 item assignment / subscription / `setdefault` 失败。
- 真实 LOGIC action 集成测试因 `context["segments"]` 的 `TypeError` 失败。
- 不新增 skip/xfail。

### 2. Red: `run_skill` 单文件入口干净失败红灯

Files:
- `packages/graph-agent/tests/core/**`

Steps:
- 新增独立测试，创建普通 `.md` 文件或根级 `SKILL.md` 单文件。
- 调用公开 `run_skill(file_path, skill_resolver=mock_skill_resolver)`。
- 断言返回对象保持公开契约：
  - `result.success is False`
  - `result.error` 包含 `[F-v3-graph-root-missing]` (注意：因 `runner.py:213` 将 exc 转为 `str(exc)`，需确保底层的 payload `code` 被序列化到 `error` 字符串中，以防此断言假红/假绿)
  - `result.context == {}`
- 测试不得期待 `run_skill` 向外抛异常；异常抛出只允许发生在 `_run_skill_dict` 层或更底层直接调用测试中。
- 该测试必须独立于任务 3 的三个迁移测试，避免把 root guard 行为和 persona 清理混在一起。

Acceptance:
- 在不改生产代码时，此测试应红灯，红灯原因应体现当前错误码缺失、错误不稳定，或未按预期返回失败 `WorkflowResult`。
- 不通过 monkeypatch `load_workflow_from_md` 制造假绿。

### 3. Red: `md_to_json` deferred-path guard 红灯

Files:
- `packages/graph-agent/tests/tools/test_md_to_json.py` 或相邻工具测试文件

Steps:
- 构造会进入 `md_to_json` patch 分支的输入：至少一个结构性错误，且不是 `semantic_only`。
- monkeypatch `graph_agent.tools.md_to_json.run_skill` 返回 `WorkflowResult` 等价失败对象，或真实调用到当前失败的 `_PATCH_SKILL_MD` 路径；推荐 monkeypatch 返回对象以稳定隔离本 PR 的 guard 行为。
- 断言 `md_to_json(...)` 在 `result.success is False` 时抛清晰 `SkillLoadError`，错误消息包含 `md_to_json` / `md-patch` / deferred 或 `[F-v3-graph-root-missing]` 关键上下文。
- 断言失败类型不是 `KeyError`，且不会继续访问 `result["context"]["final_results"]`。
- 保留现有 `test_md_to_json_patch_path_sends_wrapped_error_items` 的成功 fake path 语义，后续实现不得破坏已存在的 wrapper 入参断言。

Acceptance:
- 在不改生产代码时，此测试应因裸漏 `KeyError("final_results")` 或未抛预期 `SkillLoadError` 而红。
- 不在本任务中改 `skills/builtin/md-patch` 的目录结构或工具签名。

### 4. Red/Migrate: 三个 Persona 专属测试去 Persona 化，保留 root guard 断言

Files:
- `packages/graph-agent/tests/core/test_personas_relative_path.py`
- `packages/graph-agent/tests/core/validators/test_persona_resolution_validation_error.py`
- `packages/graph-agent/tests/core/test_compile_skill_persona_resolution_integration.py`

Steps:
- 将三组测试迁移为 `_guard_v030_root` / V0.3 root rejection 语义，文件名和测试名去 Persona 化。
- 保留三类拒绝断言：
  - schema-2.0 root `SKILL.md` 被拒绝，错误包含 `schema 2.0 root SKILL.md is not supported` 或标准 `[F-v3-graph-root-missing]` payload。
  - 只有 `subskills/.../SKILL.md` 但缺 root `GRAPH.md` 的目录被拒绝，错误包含 `missing required GRAPH.md`。
  - 直接把 `.md` 文件路径交给 `compile_skill` / `SkillLoader.compile_skill` 被拒绝，错误包含 `expects a skill root directory` 或标准 `[F-v3-graph-root-missing]` payload。
- 测试数据中的 `adopted_persona` 字段应移除或替换为普通 schema-2.0 legacy marker，确保后续 rg gate 归零。
- 不删除这些保护性测试；只迁移命名和测试数据。

Acceptance:
- 迁移后测试继续守护 V0.3 root guard 行为。
- 该任务可与任务 1-3 同属红灯阶段，但必须在 Persona 生产代码拆除前完成或同步完成，以避免测试直接引用死词。

### 5. Green: 拆除 `build_graph_nodes` 等整块死码簇与旧暴露

Files:
- `packages/graph-agent/src/graph_agent/core/personas.py`
- `packages/graph-agent/src/graph_agent/core/skill_builder.py`
- `packages/graph-agent/src/graph_agent/core/__init__.py`
- `packages/graph-agent/src/graph_agent/__init__.py`
- 其他仅在 rg gate 中命中的 Persona 残留文件

Steps:
- 删除或清空 `core/personas.py` 中 Persona 业务实现；若保留空文件，只保留无业务含义的兼容壳，并确保不命中 rg gate。
- 从 `skill_builder.py` 进行彻底根除：
  - 删除 `build_graph_nodes`、`_inject_persona`、`_phase_from_agent_manifest_for_nodes`、`_llm_phase_for_node`、`_phase_from_agent_skill`、`_phase_from_graph_phase` 等构成循环依赖的整簇死码函数。
  - 删除 `from graph_agent.core.personas import resolve_persona`
  - 删除 `TYPE_CHECKING` 块中对 `AgentSkillDef`, `GraphSkillDef`, `LLMPhase`, `LogicPhase`, `PersonaSkillDef` 的导入，消除 `ImportError` 和 mypy 隐患。
- 从 public/internal `__init__.py` 删除任何 `core.personas` 或 Persona 相关导出；若当前没有导出，保持不新增。
- 不新增任何 V0.3 persona schema、parser 或 fallback。

Acceptance:
- `python -c "import graph_agent.core.skill_builder"` 正常通过，且由于连根拔起，不再掩盖内部深层的 import 崩溃问题。
- `rg "build_graph_nodes|_inject_persona|PersonaSkillDef|adopted_persona|resolve_persona|core\\.personas" packages/graph-agent/src/graph_agent packages/graph-agent/tests` 输出为空。
- 任务 4 的迁移测试仍通过。

### 6. Green: 为 `Context` 补 4 个最小 dict 方法

Files:
- `packages/graph-agent/src/graph_agent/cognitive/context_facade.py`
- `packages/graph-agent/tests/**`

Steps:
- 在 `Context` 实现：
  - `__getitem__(self, key: str) -> Any`
  - `__setitem__(self, key: str, value: Any) -> None`
  - `__contains__(self, key: str) -> bool`
  - `setdefault(self, key: str, default: Any = None) -> Any`
- `__getitem__` 对缺失 key 抛原生 `KeyError(key)`。
- `__setitem__` 复用 `self.set`，保证写入 `_blackboard`。
- `setdefault` 必须返回存入或已存在的对象本身，支持 `context.setdefault("items", []).append(...)` 后被 `_dict_delta` 识别。
- 不在本 PR 扩大到完整 `MutableMapping`，除非实现所需；不得顺手改变 `update(**fields)` 的既有签名。

Acceptance:
- 任务 1 的 Context 单测和真实 LOGIC action 集成测试转绿。
- 现有 `score.py` fixture 的 `context["segments"]` 路径不再抛 `TypeError`。

### 7. Green: `_run_skill_dict` 非 V0.3 root 统一标准失败

Files:
- `packages/graph-agent/src/graph_agent/core/runner.py`
- `packages/graph-agent/tests/core/**`

Steps:
- 在 `_run_skill_dict` resolve `skill_path` 后尽早判断入口形态。
- 仅当 `skill_path.is_dir()` 且 `(skill_path / "GRAPH.md").is_file()` 时进入 `_run_v030_skill_dict`。
- 其他情况，包括：
  - 不存在路径
  - 普通 `.md` 文件
  - 根级 legacy `SKILL.md`
  - 存在但缺 `GRAPH.md` 的目录
  均抛 `SkillLoadError`，附带 `make_error_payload("[F-v3-graph-root-missing]", ..., source_path=skill_path)`。
- **关键依赖满足:** 确保 `SkillLoadError` 或其 payload 机制的 `__str__` 能够把 `code`（如 `[F-v3-graph-root-missing]`）显式暴露给字符串，以满足 `runner.py:213` 的 `error=str(exc)` 转换。
- 错误消息应清楚说明 V0.3.0 `run_skill` 需要 skill root 目录且必须包含 `GRAPH.md`。
- 不改变公开 `run_skill` 的 `except GraphAgentError` 包装逻辑；公开调用方仍获得 `WorkflowResult(success=False, error=...)`。
- 若 `_run_skill_dict` 直接被测试调用，则可以断言其抛出 `SkillLoadError` 及 payload code。

Acceptance:
- 任务 2 的 `run_skill` 红灯转绿：`success=False` 且 `error` 包含 `[F-v3-graph-root-missing]`。
- `test_run_skill_requires_resolver_v3_code` 等 resolver 缺参测试仍按 resolver 优先级工作：缺 resolver 时仍先报 `[F-v3-resolver-missing]`。
- 不再走 legacy `load_workflow_from_md` 分支处理单文件入口。

### 8. Green: `md_to_json` 增加 deferred-path guard

Files:
- `packages/graph-agent/src/graph_agent/tools/md_to_json.py`
- `packages/graph-agent/tests/tools/test_md_to_json.py`

Steps:
- 在 `result = run_skill(...)` 后、读取 `final_results` 前检查返回对象：
  - 若 `getattr(result, "success", True) is False`，抛 `SkillLoadError`。
  - 错误消息说明 `md_to_json` patch fallback / `md-patch` deferred path 失败，并包含原始 `result.error`。
  - 若 `result` 是旧测试 fake dict 且没有 `success` 属性，保持现有成功测试兼容。
- 成功路径继续支持当前 fake dict / `WorkflowResult` 的 `result["context"]["final_results"]` 访问形态。
- 不修改 `_PATCH_SKILL_MD` 指针，不升级 `skills/builtin/md-patch`，不改 `patch_tools.py` 签名。

Acceptance:
- 任务 3 的 deferred guard 红灯转绿。
- 现有 `test_md_to_json_patch_path_sends_wrapped_error_items` 继续通过。
- `rg "_PATCH_SKILL_MD" packages/graph-agent/src/graph_agent/tools/md_to_json.py` 仍只显示当前 deferred 指针，不在本 PR 中伪装已修复 md-patch。

### 9. Scope Guard: 明确 PR-6 deferral 不被误修

Files:
- No production file expected beyond tasks 5-8.
- Tests may only assert current guard behavior.

Steps:
- 不改造 `packages/graph-agent/src/graph_agent/skills/builtin/md-patch/SKILL.md` 为 V0.3 目录。
- 不重写 `packages/graph-agent/src/graph_agent/skills/builtin/md-patch/script/patch_tools.py` 的 context 注入工具流。
- 不更新 pyproject/version/README public API 数量等元数据维护项，除非实现事实漂移直接要求；这些属于 PR-6。
- 若测试需要模拟 md-patch 失败，使用 monkeypatch `run_skill` 或最小 fixture，不依赖真实 LLM。

Acceptance:
- `git diff -- packages/graph-agent/src/graph_agent/skills/builtin/md-patch` 为空，除非后续 PM 明确扩大 PR-3 范围。
- `md_to_json` 只新增失败 guard，不声称 patch fallback 已可用。

### 10. Final Verification: 诚实绿与 grep gate

Files:
- No additional files expected.

Commands:
- `rg "build_graph_nodes|_inject_persona|PersonaSkillDef|adopted_persona|resolve_persona|core\\.personas" packages/graph-agent/src/graph_agent packages/graph-agent/tests`
- `rg "_inject_persona|Persona injection" packages/graph-agent/src/graph_agent packages/graph-agent/tests`
- `rg "result\\[\"context\"\\]\\[\"final_results\"\\]" packages/graph-agent/src/graph_agent/tools/md_to_json.py -n`
- `uv run pytest packages/graph-agent/tests/core packages/graph-agent/tests/tools`
- If time permits: `uv run pytest packages/graph-agent/tests`

Acceptance:
- Persona 及 `build_graph_nodes` 死码簇 rg gate 归零。
- `_inject_persona` / Persona docstring gate 归零。
- `md_to_json.py` 中读取 `final_results` 前存在 `result.success` failure guard；代码 review 确认不会裸漏 `KeyError`。
- 新增红灯全部转绿。
- 旧语料 deferral 不被改动，不新增 skip/xfail。
- 确认 `skill_builder.py` 中的无效 `TYPE_CHECKING` import 被清理，不引发 mypy 红灯。
- 全量 pytest 若执行，应为 `0 failed`；不以固定 passed 数作为唯一验收，仍以既有 deferral 状态不变为准。
