# PR G (Schema Cleanup) Tasks

> Scope: PR G 只做 V0.3.0 hard cutover 收尾。执行顺序必须是 tests-first 红灯契约 -> 删除/迁移实现 -> 同步删/迁测试 -> 全量验证。  
> Guardrail: 本轮设计审计确认 `cognitive` 模块群是 LIVE，不得删除；`context_mapping` / `python_callable` / `codemod` / `<steps>` 是 dead 或 dead-but-wired，但必须按全链路 cutover 删除，不能只删表层字段。

## §0 审计结论固化

- `codemod/`：同意删。grep 仅命中 `src/graph_agent/codemod/v21_migrator.py`、`tests/core/test_v21_codemod.py`、`tests/fixtures/codemod_v20/**`、`tests/golden/codemod/**`；无 non-test 主路径 import。
- `context_mapping`：同意删，但 a2 迁移路径有漏。除 `harness.py:361/372/852`、`runner.py:3/351`、`io/context_resolver.py`、`io/__init__.py:5/11` 外，还必须同步处理 `tests/core/test_heartbeat_pulser.py:198`、`src/graph_agent/__init__.py:26-29` docstring、`src/graph_agent/skills/builtin/md-patch/SKILL.md:9`、active `skills/*/SKILL.md`。`core/validators/*` 侧经 import-graph 复验是纯 DEAD validator，不是 live context_mapping wiring，见 T6。Studio 残留不在 PR G engine scope，见 §10 Deferred。
- `cognitive` 4 模块：反对删除。`harness.py:28`、`llm_phase_node.py:32`、`graph_assembler.py:23-25/337` 证明 `finish.py` / `finish_task.py` / `md2json.py` / `md_patch.py` 是 V0.3.0 主路径 LIVE。只清 docstring 中误导性的 `V2.1` / legacy 词。
- `python_callable`：同意删字段/旧标签，但当前残留不只 codemod + 测试。主路径 AST 已是 `LogicNodeAST.actions`，`graph_assembler.py:207-217` 走 actions；但残留包括 `tests/golden/schema/*.json`、`tests/fixtures/*/LOGIC.md`、旧 V2.1 测试驱动。Studio welcome 错误文案不在 PR G engine scope，见 §10 Deferred。
- `<steps>`：同意删。Ground Truth 明令禁止复数壳；当前活残留在 `skill_builder.py:610-624` 和 `skill_builder.py:798-802`，并有旧断言 `tests/core/test_loader_xml_rendering.py:365-368`、`tests/core/test_manifest_phase_builders.py:81-85/244-246`。
- 26 个 `test_*_v21.py`：不能按文件名盲删。`test_v21_codemod.py` 可直接删；多数 core/cognitive/subagent 测的是仍存活的 V0.3.0 行为，必须迁移/重命名；e2e 业务 skill 驱动要迁到 `_v030.py` 或由同名 V0.3.0 覆盖后删除，严禁误删 `skills/` 多版本业务语料。

## §1 红灯契约测试先行

- [ ] T1. 新增 PR G grep gate 红灯测试。
  - 文件：新增 `packages/graph-agent/tests/core/test_pr_g_schema_cleanup_contract.py`。
  - 断言删除后 `packages/graph-agent/src/graph_agent` 内无 `graph_agent.codemod` / `v21_migrator` / `ContextResolver` / `context_resolver` / `context_mapping` / `python_callable` / `<python_callable>` / `<steps>` 的真实使用或生成。
  - grep gate 必须做语义过滤：允许 V0.3.0 负向断言和拒绝测试输入，例如 `assert "<steps>" not in prompt`、`assert "</steps>" not in prompt`、`<steps>` 作为 bad fixture 触发 `[F-v3-agent-body-tag-unknown]`；禁止 `.ast.python_callable` 读取、schema required、fixture `<python_callable>`、active skill/context wiring 等真实 legacy 使用。
  - 实现方式可用 Python line classifier 或 `rg` 后二次过滤；allowlist 必须逐行写清楚原因，不能用目录级 blanket allowlist 放过 active tests。
  - 预期先红：当前 grep 命中上述所有项。

- [ ] T2. 新增 import-error 红灯测试，证明删除后引擎不会 import 已删模块。
  - 文件：新增 `packages/graph-agent/tests/core/test_pr_g_removed_imports.py`。
  - 断言 `import graph_agent.codemod.v21_migrator`、`import graph_agent.io.context_resolver` 失败。
  - 断言 `import graph_agent.cognitive.finish`、`finish_task`、`md2json`、`md_patch` 成功，防止误删 live cognitive。
  - 预期先红：当前 codemod/context_resolver 仍可 import。

- [ ] T3. 新增 V0.3.0 e2e 保活红灯/绿灯基线。
  - 文件：扩展或新增 `packages/graph-agent/tests/e2e/test_pr_g_v030_cutover_e2e.py`。
  - 覆盖 `tests/fixtures/v030_e2e_pipeline` 的 compile + assemble + fake LLM run。
  - 断言 prompt 无 `<steps>` 壳，LOGIC 用 `actions`/`<action>`，GRAPH 用 inline `io`，无 `context_mapping`。

## §2 Codemod 全删 [BREAKING][A 类]

- [ ] T4. 删除 codemod 工具和专属测试/fixture/golden，并保持 grep gate 绿。
  - 删除：`packages/graph-agent/src/graph_agent/codemod/v21_migrator.py`、空目录 `packages/graph-agent/src/graph_agent/codemod/`。
  - 删除：`packages/graph-agent/tests/core/test_v21_codemod.py`。
  - 删除：`packages/graph-agent/tests/fixtures/codemod_v20/**`、`packages/graph-agent/tests/golden/codemod/**`。
  - 同步：任何 `v21_migrator` / `codemod_v20` import、README 或 CI scanner 测试引用。
  - 迁移路径：不提供兼容；V0.3.0 已定稿，旧 schema 2.0 -> V2.1 一次性工具退出主线。

## §3 Context Mapping 全链路删除 [BREAKING][A 类]

- [ ] T5. 切断 engine runtime 和 public API 的 `context_mapping`。
  - 删除：`packages/graph-agent/src/graph_agent/io/context_resolver.py`。
  - 修改：`packages/graph-agent/src/graph_agent/io/__init__.py:5-11` 移除 `ContextResolver` export。
  - 修改：`packages/graph-agent/src/graph_agent/core/harness.py:361-372` 移除构造参数和 `_context_mapping`；`harness.py:840-861` 改为 inline io/raw inputs 路径。
  - 修改：`packages/graph-agent/src/graph_agent/core/runner.py:3-4/351` 移除 ContextResolver 文案；保持 V0.3.0 `_run_v21_skill_dict` 后续按新命名收敛。
  - 修改：`packages/graph-agent/src/graph_agent/__init__.py:26-29` 移除 ContextResolver 文案。
  - 迁移路径：GRAPH.md frontmatter `io.inputs` / `io.outputs` inline dict + StateMapper/phase IO。

- [ ] T6. 删除 5 个 dead `core/validators` 模块及其测试/豁免。
  - 复验要求：实施前逐个重跑 import-graph，确认 `template_variables` / `prompt_quality` / `validator_required` / `tool_paths` / `persona_resolution` 仍无 V0.3.0 主路径 caller；若发现 live caller，先停下 flag，不得删除。
  - 当前审计实证：5 个 `check_*` 仅在各自模块/测试中出现，`packages/graph-agent/src` 无外部 caller；`template_variables`、`validator_required`、`tool_paths`、`persona_resolution` module import 已因已删 manifest 类型失败，`prompt_quality` 可 import 但 0 live caller。
  - 删除：`packages/graph-agent/src/graph_agent/core/validators/template_variables.py`、`prompt_quality.py`、`validator_required.py`、`tool_paths.py`、`persona_resolution.py`；同步清理 `core/validators/__init__.py` 若有 export。
  - 删除/迁移对应测试：`tests/core/validators/test_template_variables.py`、`test_prompt_quality.py`、`test_persona_resolution.py`、`test_tool_paths.py`，以及 `tests/cognitive/test_finish_v2.py` 中仅覆盖 `validator_required` 的死测试块。
  - 同步删除 `packages/graph-agent/tests/conftest.py:108-110` 的 3 个非 `test_v21_*` collection-ignore 豁免；删豁免后不得再有 collection ImportError。
  - 修改：`packages/graph-agent/src/graph_agent/skills/builtin/md-patch/SKILL.md:9`，迁到 V0.3.0 结构或从 active skill 集移除。
  - 同步迁/删：相关 engine unit/integration 断言，不保留旧字段兼容分支。

## §4 Python Callable 删除 [BREAKING][A 类]

- [ ] T7. 清除 `.ast.python_callable` schema、fixtures 和用户可见错误文案。
  - 修改：`packages/graph-agent/tests/golden/schema/logic_node_ast.schema.json`、`phase_ast_union.schema.json`，以 `actions` 为唯一 LOGIC 字段。
  - 迁移：`packages/graph-agent/tests/fixtures/fake_canvas_fanout/**/LOGIC.md`、`tests/fixtures/canvas_serializer/with_comments_v21/**/LOGIC.md` 到 `actions: [...]` + `<action>...</action>`。
  - 迁移/删除 active 测试真实读取：`tests/integration/skills/text_segmentation/test_cognitive_flow_smoke.py:26`、`tests/integration/skills/event_extraction/test_cognitive_flow_smoke.py:36`、`tests/integration/skills/test_loader_based_smoke.py:123`，从 `.ast.python_callable` 断言迁到 `LogicNodeAST.actions` 或随旧 V1/V2 驱动删除。
  - 迁移路径：旧 `<python_callable>` 一律删除；V0.3.0 LOGIC 使用 phase-local `actions/<name>.py` + frontmatter `actions` + body `<action>`。

## §5 `<steps>` 壳删除 [BREAKING][A 类]

- [ ] T8. 删除 `skill_builder.py` 里的 `<steps>` 硬编码拼接。
  - 修改：`packages/graph-agent/src/graph_agent/core/skill_builder.py:610-624`，删除 `_append_steps_to_prompt` 或改为无壳 splat。
  - 同步修改 caller：`packages/graph-agent/src/graph_agent/core/skill_builder.py:301`、`skill_builder.py:923` 不得继续调用已删除的 `_append_steps_to_prompt`，否则会留下 NameError。
  - 修改：`packages/graph-agent/src/graph_agent/core/skill_builder.py:798-802`，删除 `<steps>` 包裹，改为 V0.3.0 cognitive template 的 thinking_style/单数 `<step>` 语义。
  - 同步迁/删：`tests/core/test_loader_xml_rendering.py:365-368`、`tests/core/test_manifest_phase_builders.py:81-85/244-246` 等旧 `<steps>` 断言。
  - 迁移路径：SKILL.md body 只允许平铺 `<step>`；prompt 装配直接 splat，不再生成复数壳。

## §6 Cognitive Docstring 清理（非删除）

- [ ] T9. 只清理 cognitive 模块误导性注释，不改核心逻辑。
  - 修改：`packages/graph-agent/src/graph_agent/cognitive/finish_task.py:1/22/36`。
  - 修改：`packages/graph-agent/src/graph_agent/cognitive/md2json.py:1/15/30`。
  - 修改：`packages/graph-agent/src/graph_agent/cognitive/md_patch.py:1`。
  - 视 grep 结果同步清理：`cognitive/context_facade.py:1`、`cognitive/critic.py:1`、`runtime/__init__.py:1`、`core/actions.py:1`、`core/graph_assembler.py:1/93` 等仍把 live V0.3.0 路径称为 V2.1 的 docstring。
  - 保留验证：T2 import 保活测试必须证明 `finish.py` / `finish_task.py` / `md2json.py` / `md_patch.py` 仍可 import。

## §7 26 个 `test_*_v21.py` 分流

- [ ] T10. 直接删除纯 codemod 测试。
  - 删除：`packages/graph-agent/tests/core/test_v21_codemod.py`。
  - 理由：只覆盖已退役 codemod。

- [ ] T11. 迁移/重命名 live cognitive 测试。
  - 迁移：`tests/cognitive/test_v21_finish_task.py` -> `test_v030_finish_task.py`。
  - 迁移：`tests/cognitive/test_v21_critic.py` -> `test_v030_critic.py`。
  - 不删除对应 cognitive 源模块。

- [ ] T12. 迁移/重命名 live core 行为测试，删旧 V2.1 helper。
  - 迁移：`test_v21_actions_loader.py`、`test_v21_actions_keys.py`、`test_v21_graph_assembly.py`、`test_v21_graph_assembly_fanout.py`、`test_v21_cache.py`、`test_v21_compiler_facade.py`、`test_v21_graph_serializer.py`、`test_v21_loader.py`、`test_v21_purity.py`、`test_v21_subagents_loader.py`、`test_v21_subagent_executor.py`。
  - 迁移/删除第 26 个文件：`tests/integration/test_v21_subagent_executor.py`，并同步删除 `packages/graph-agent/tests/conftest.py:112` collection-ignore 豁免。
  - 改名为 `_v030.py` 或并入现有 `test_action_registry_v030.py`、`test_round14_skill_compilation_cutover.py`、`test_execution_runtime_v030.py`。
  - 同 task 内迁移 `tests/fixtures/fake_canvas_fanout`、`tests/fixtures/subagent_minimal`、`tests/fixtures/canvas_serializer/with_comments_v21`；不要把仍有业务价值的 fixture 误删。

- [ ] T13. 处理 AST schema / guide 旧测试。
  - 迁移：`test_v21_ast_schema.py` 到 V0.3.0 AST golden；删除 `SkillNodeAST` / `python_callable` golden 污染。
  - 迁移或删除：`test_v21_skill_authoring_guide_example.py`。若 authoring guide 仍是 active 文档，则改成 V0.3.0 hello-world；若文档已废弃，则同 task 删除测试和旧章节。

- [ ] T14. 迁移 e2e 业务 skill 驱动，不删 `skills/` corpus。
  - 迁移：`test_hello_world_v21.py`、`test_text_segmentation_v21.py`、`test_event_extraction_v21.py`、`test_batch_analysis_v21.py`、`test_global_synthesis_v21.py`、`test_v21_all_skills_smoke.py` 到 `_v030.py`。
  - 迁移或删除：`test_producer_v21.py`、`test_product_manual_v21.py`、`test_subgraph_sample_v21.py`。当前 grep/`find` 显示 producer/product-manual/subgraph-sample 路径不在 active `skills/` 根清单；若无 V0.3.0 corpus，删除旧测试驱动，不删除业务语料。
  - 同 task 内更新 `packages/graph-agent/tests/conftest.py:107-159` 的 xfail/skip 清单，不能留下 `test_v21_*` 通配豁免；T6/T12 负责额外的 validators 与 integration collection-ignore 项。

- [ ] T15. 清理 remaining active test references and quarantine holes.
  - 处置 `tests/core/test_heartbeat_pulser.py:198` 的 `harness._context_mapping = None`，随 T5 删除 `_context_mapping` 后迁移为新状态断言或删除旧断言。
  - 审计 `packages/graph-agent/tests/conftest.py:95-113` 所有 legacy quarantine；PR G 范围内的 collection-ignore / xfail 项必须被删除、迁移或改成 V0.3.0 合法测试，不能靠 conftest 隐藏 ImportError。
  - 保留合法负向断言测试：例如 `<steps>` 不出现在 V0.3.0 prompt、`<steps>` bad input 被拒绝。这些行应由 T1/T16 语义 grep gate allowlist 明确放行。

## §8 新发现 legacy 入口收敛

- [ ] T16. 清理非 §0.5 表内但 grep 命中的 legacy 入口。
  - Engine：`core/skill_builder.py` / `core/skill_validator.py` / `core/validators/*` 中对 `GraphSkillDef`、`LLMPhase`、schema 2.0 pipeline 的 runtime 引用要么删除，要么迁成 V0.3.0 AST；不得保留会在 import 时引用不存在 manifest 类型的死代码。
  - Runner：`core/runner.py:467-478` `_run_v21_skill_dict` 改名/收敛为 V0.3.0 入口，用户可见文案不再称 V2.1。
  - 删除纪律：实施前每个符号先 import-graph 复验确认无 V0.3.0 主路径依赖，红灯 import-keepalive 测试 + grep guard 兜底，漏判即引擎崩。

## §9 全量验证

- [ ] T17. 全量 pytest 与 grep guard 转绿。
  - 运行：`cd packages/graph-agent && pytest`。
  - 运行 grep guard：
    - `rg -n "context_mapping|ContextResolver|context_resolver" packages/graph-agent/src packages/graph-agent/tests skills`，再由 T1 line classifier 排除明确历史文档/合法负向断言；`tests/core/test_heartbeat_pulser.py:198` 这类真实 `_context_mapping` 使用不得放行。
    - `rg -n "python_callable|<python_callable>|codemod_v20|v21_migrator" packages/graph-agent/src packages/graph-agent/tests skills`，允许显式的 rejection/negative assertion 行；禁止 `.ast.python_callable` 读取、schema required、fixture `<python_callable>`、codemod 实体。
    - `rg -n "<steps>|</steps>" packages/graph-agent/src packages/graph-agent/tests`，允许 `not in` 负向断言和 bad input rejection fixture；禁止 source 生成 `<steps>` 或测试期待 `<steps>` 存在。
    - `rg --files packages/graph-agent/tests | rg "test_.*v21.*\\.py$"` must return no files.
    - `rg -n "collect_ignore_glob|test_v21_|core/validators/test_" packages/graph-agent/tests/conftest.py` must not hide PR G collection errors.
  - 手动 spot-check：V0.3.0 fixture compile/run path still green; cognitive modules still import.

## §10 Deferred (Out Of PR G Engine Scope)

以下 Studio V2.1 / legacy 字符串残留不破坏引擎、无被删引擎符号的 import 依赖，且 charter 未纳入 PR G，故 defer 到未来独立 Studio 清理 PR：

- Studio backend：`apps/studio/backend/app/services/skills.py` 中的 V2.1 命名、`node_schema_v21`、`F-v21-*` 错误码，以及 `apps/studio/backend/app/templates/*.SKILL.md` 中的 schema 2.0 / `context_mapping` 模板。
- Studio frontend：`apps/studio/frontend/src/api/types.ts`、`src/utils/graph.ts`、`src/components/studio/panels/panel-files.ts` 等 schema 2.0 / 2.1 分支。
- Studio generator / UX 文案：`apps/studio/frontend/src/templates/skillMdGenerator.ts` 的旧字段生成/读取逻辑，以及 `apps/studio/frontend/src/components/welcome/WelcomePage.tsx` 中的 `python_callable` 错误文案和对应测试。
