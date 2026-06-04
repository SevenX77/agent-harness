---
spec: engine-mvp0-rebuild-v030/round-15-PR-C-execution-runtime
phase: PR C execution-runtime tasks
owner: a1 tasks / a2 design+requirements+research / a3 gate
scope: C1+C2+C4+C5+C6+C7+C8+D4, tests-first, [BREAKING] V0.3.0 hard cutover
---

# PR C: Execution Runtime Tasks

## §0 Scope / PR Structure / Workflow

本 PR 只做 execution-runtime 收敛范围: C1, C2, C4, C5, C6, C7, C8, D4。C3 SkillResolver DI、D1 inline IO、D3 reader sandbox 已 merge, 本轮只补 execution-runtime 闭环和测试迁移。

唯一格式权威:

- Cognitive Template: `docs/engine/mvp0/skill-spec/00-FORMAT-GROUND-TRUTH.md` §5。
- 错误码总册: `docs/engine/mvp0/skill-spec/11-error-code-spec.md`。
- 原始 task 定义: `.kiro/specs/engine-mvp0-rebuild-v030/tasks.md` `### C. execution-runtime` + `### D` D4。

PR 结构: 1 个统一 PR, 内部 3 commit。

- Commit 1: C1 + C2, 物理退役 V2.1 exit_contract 注入, cognitive template 对齐 §5 8 插槽。
- Commit 2: C4 + C5 + C7, reference reader 装配期 fallback, builtin resource tools, ActionRegistry 沙盒与 LOGIC 输出字段 fatal。
- Commit 3: C6 + D4 + C8, subagent/SUBGRAPH resolver runtime 闭环, child flow 深拷贝, e2e 和 resolver fixture 大迁移。

合并工作流:

- feature branch 完成后用 `git merge --no-ff` 合入 `stage/engine-v030`。
- 不直接进 `main`。
- 每个 commit 必须保持本 PR 局部测试可解释; 最终 PR 必须通过 CI gate checklist。

[BREAKING] cutover discipline:

- `!` 标记的 task 是 hard cutover, 必须同 PR 同步改 src/tests/fixtures。
- 先写红灯 failing tests, 再实施转绿; 不允许 `xfail` / blanket skip 掩盖本轮 V0.3.0 contract。
- 不保留 V2.1 runtime fallback, 不用旧路径包装成 V0.3.0 facade。
- unit + integration + e2e 覆盖必须同步, 尤其 exit_contract、prompt、resource tools、ActionRegistry、SUBGRAPH/subagent。

## §1 依赖图

```text
c15.1 Tests-first red suite
  ├─> c15.2 ! C1 exit_contract physical retirement
  │     └─> c15.3 ! C2 cognitive template 8 slots
  │           └─> c15.4 C4 reference reader assembly-time fallback
  │                 ├─> c15.5 C5 builtin read_reference/read_example tools
  │                 └─> c15.6 ! C7 ActionRegistry sandbox + LOGIC output fatal
  ├─> c15.7 ! C6/D4 subagent/SUBGRAPH resolver runtime + child flow deepcopy
  └─> c15.8 test/fixture migration sweep
        └─> c15.9 C8 integration/e2e closure
              └─> c15.10 CI gate + risk scans
```

## §2 c15.1: Tests-first red suite (first task)

**目标**: 先写失败测试锁定 §5 8 插槽、错误码、沙盒规则和 child isolation。此 task 只改 tests/fixtures, 不改 src。后续实施必须让这些红灯转绿。

**Files**:

- 新增 `packages/graph-agent/tests/cognitive/test_v030_cognitive_template_slots.py`
- 新增 `packages/graph-agent/tests/tools/test_builtin_resource_tools.py`
- 新增 `packages/graph-agent/tests/core/test_action_registry_v030.py`
- 新增 `packages/graph-agent/tests/core/test_reference_reader_assembly_fallback.py`
- 新增/更新 `packages/graph-agent/tests/core/test_gamma2_child_graph_isolation.py`
- 新增 `packages/graph-agent/tests/e2e/test_execution_runtime_v030.py`

**Red tests**:

- `test_v030_cognitive_template_slots.py`
  - 断言 8 固定容器: `role`, `goal`, `thinking_style`, `knowledge_base`, `examples`, `ambiguity_feedback`, `protocol_citation`, `critical_reminders`。
  - 断言没有独立 `<steps>` slot; SKILL.md body `<step>` 内容在 `<thinking_style>` 的 "建议步骤:" 下。
  - 断言 `<knowledge_base>` 含 `{aligned_concepts_and_critical_corrections_markdown}` 对应内容和 reference registry listing。
  - 断言 `<examples>` 同时含 inline examples 和 document example registry listing。
  - 断言 `<exit_contract>` 位于 prompt 末尾, 且含 `output_schema`。
- `test_builtin_resource_tools.py`
  - `read_reference` 合法 id 返回当前 phase registry 对应 markdown。
  - `read_example` 合法 id 覆盖 body inline example 与 document example。
  - 未声明 reference id 不做 file I/O, 返回/抛 `[F-v3-resource-reference-not-found]`。
  - 未声明 example id 不做 file I/O, 返回/抛 `[F-v3-resource-example-not-found]`。
  - 跨 skill/path 逃逸不读文件, 不泄漏未注册资源。
- `test_action_registry_v030.py`
  - action name 含 `/`, `\`, `.`, `..`, 绝对路径, module path 均 fatal。
  - 只允许 `phases/<phase_id>/actions/<name>.py` 或 common action registry。
  - action 动态返回未声明字段 fatal `[F-v3-logic-output-field-undeclared]`, 且不回写。
  - action 通过 `ctx.data` 就地突变写未声明字段同样 fatal `[F-v3-logic-output-field-undeclared]`, 覆盖 `_dict_delta(before | updates, data)` 旁路且不回写。
- `test_reference_reader_assembly_fallback.py`
  - mock reader timeout / 抛异常 / 输出非法均发 WARN `[F-v3-reference-reader-failed]`。
  - fallback markdown 截原始 reference 前 3000 tokens 并进入 system prompt `<knowledge_base>`。
  - reference path 非法仍 compile fatal `[F-v3-resource-reference-path-invalid]`, 不走 fallback。
  - reader 只在 `_build_skill_node()` 装配期计算一次, 不在 `_skill_node()` 每轮重复跑。
- `test_gamma2_child_graph_isolation.py`
  - 单元级红灯断言 child flow 是 parent flow 深拷贝: 改 child nested flow 不影响 parent flow, 且 `subagent_depth` 递增。
- `test_execution_runtime_v030.py`
  - minimal Agent run 断言 §5 cognitive system prompt 和 `{aligned_concepts...}` 非空。
  - `read_example` 合法调用返回 document example markdown。
  - SUBGRAPH `target_skill` 全链路执行。
  - child data/messages 不继承 parent, child flow 深拷贝并递增 depth。

**依赖**: none。

**验收**:

- 当前实现下这些测试必须红灯, 红灯原因对应缺失行为或精确错误码。
- 不允许通过 skip/xfail/quarantine 获得假绿。

## §3 c15.2: ! C1 ExitContractRegistry 退役 (Commit 1)

**目标**: 删除 V2.1 per-turn exit_contract 注入链, 输出契约只由 cognitive template 末尾 hardcode。

**Files / verified lines**:

- `packages/graph-agent/src/graph_agent/runtime/exit_contract.py:8`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/src/graph_agent/cognitive/prompt.py:20`
- `packages/graph-agent/tests/runtime/test_exit_contract.py:7`
- `packages/graph-agent/tests/cognitive/test_prompt.py:75`

**WHAT**:

- 删除或退役 `runtime/exit_contract.py` 的 `inject_exit_contract()` active path。
- 清理 `graph_assembler.py` / tests 对 `inject_exit_contract` 的 import 和调用依赖。
- `<exit_contract>` 固定 XML 文案只在 `prompt.py` V0.3.0 system template 末尾生成, 内层拼 `output_schema`。
- 保证 Agent loop 每轮不再追加 exit_contract HumanMessage。

**依赖**: c15.1。

**测试影响**:

- `tests/runtime/test_exit_contract.py` 删除或改为 system prompt 末尾单次出现断言。
- `tests/cognitive/test_prompt.py` 更新为 `<exit_contract>` 末尾 + `output_schema` substring。
- 旧 agent loop message history tests 改断言: exit_contract 只在 system prompt 末尾出现一次。

**风险点**:

- 旧测试可能断言 exit_contract 是最后一条 HumanMessage; 需迁移为 system prompt contract。
- Prompt 文案变化大, 只断言关键 substring, 不做全文 snapshot。

**错误码**: none。

## §4 c15.3: ! C2 Cognitive Template 8 插槽对齐 §5 (Commit 1)

**目标**: `apply_v030_cognitive_template()` 严格对齐 ground truth §5, 废弃独立 `<steps>` 壳和旧 `knowledge_base` 简单插值。

**Files / verified lines**:

- `packages/graph-agent/src/graph_agent/cognitive/prompt.py:130`
- `packages/graph-agent/src/graph_agent/cognitive/prompt.py:186`
- `packages/graph-agent/src/graph_agent/cognitive/prompt.py:192`
- `packages/graph-agent/src/graph_agent/cognitive/prompt.py:196`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:396`
- `docs/engine/mvp0/skill-spec/00-FORMAT-GROUND-TRUTH.md:204`

**WHAT**:

- 重写 V0.3.0 template 为 8 固定容器:
  - `<role>`: skill role + optional llm role prefix section。
  - `<goal>`: skill goal。
  - `<thinking_style>`: hardcode thinking rules + "建议步骤:" + body `<step>` splat。
  - `<knowledge_base>`: reader 修正报告 + read_reference 提示 + reference registry listing。
  - `<examples>`: inline examples + document example registry listing。
  - `<ambiguity_feedback>`: log_ambiguity hardcode。
  - `<protocol_citation>`: citation hardcode + body `<protocol>` splat。
  - `<critical_reminders>`: finish_task / diagnostics_md / business_data_md hardcode。
- 删除独立 `<steps>` slot。
- 删除 `<document_examples>` 子壳依赖, 按 §5 文案列入 `<examples>`。
- 追加 hardcoded `<exit_contract>` + `{output_schema}`。
- `_agent_system_prompt()` 传入 `knowledge_base_markdown`, `reference_registry_listing`, `example_registry_listing` 等动态 slot。

**依赖**: c15.2。

**测试影响**:

- `tests/cognitive/test_prompt.py` 升级到 §5 slot substring。
- `tests/core/test_loader_xml_rendering.py` 迁移 `<steps>` 旧结构断言。
- `tests/core/test_manifest_phase_builders.py` 迁移 `<steps>` 旧结构断言。
- `tests/fixtures/test_v030_agent_demo_compiles.py` 更新 prompt slot 断言。

**风险点**:

- prompt snapshot 脆弱; 只测关键 slot 和位置关系。
- `phase_name` 参数若不再直接入 prompt, 测试不要误断言旧文案。

**错误码**:

- `[F-v3-cognitive-slot-render-failed]` for slot 序列化异常。
- `[F-v3-cognitive-output-schema-render-failed]` for output schema render 异常。

## §5 c15.4: C4 Reference Reader 装配期调用 + fallback (Commit 2)

**目标**: Agent node 装配前运行 builtin reference reader, 输出 knowledge_base markdown; 失败 WARN 降级但不阻断主 Agent run。

**Files / verified lines**:

- `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py:13`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:159`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:259`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:327`
- `docs/engine/mvp0/skill-spec/09-builtin-modules-spec.md:15`
- `docs/engine/mvp0/skill-spec/09-builtin-modules-spec.md:50`

**WHAT**:

- 在 `graph_assembler._build_skill_node()` 构建 Agent node 前计算一次 `knowledge_base_markdown`, 闭包进 `_agent_system_prompt()`。
- 不在 `_skill_node()` 内调用 reader; `_skill_node()` 每次 invoke/loop 只消费已计算 prompt。
- 扩展 `ReaderSandboxState` 输入:
  - `skill_id`
  - `phase_id`
  - `references`
  - `max_output_tokens`
  - `language`
  - `timeout_s`
- `ReferenceReaderRuntime` 增加真实 timeout wrapper, 默认 60s。
- reader success: 取 `markdown` 写入 `{aligned_concepts_and_critical_corrections_markdown}`。
- reader timeout / exception / output invalid: WARN `[F-v3-reference-reader-failed]`, fallback 为每份 reference 原文前 3000 tokens + warning header。
- reference path 非法或不可读仍是 compile fatal `[F-v3-resource-reference-path-invalid]`, 不进入 fallback。

**依赖**: c15.3。

**测试影响**:

- 新增/更新 `tests/core/test_reference_reader_assembly_fallback.py`。
- 更新 `tests/core/test_gamma2_reference_reader_sandbox.py`, 断言 sandbox 输入包含 references/max_output_tokens/language 且不继承 parent data/messages。
- 更新 Agent prompt tests, 断言 fallback markdown 进入 `<knowledge_base>`。

**风险点**:

- 同步 reader 会阻塞 assembly; timeout 必须真实生效。
- fallback 只能吞 reader 推理失败, 不能吞 reference path fatal。
- 不要在每个 ReAct turn 重跑 reader。

**错误码**:

- `[F-v3-reference-reader-input-invalid]`
- `[F-v3-reference-reader-output-invalid]`
- `[F-v3-reference-reader-failed]`
- `[F-v3-resource-reference-path-invalid]`

## §6 c15.5: C5 builtin `read_reference` / `read_example` tools (Commit 2)

**目标**: 将 runtime resource tools 从 graph_assembler 内联闭包收口为 builtin modules, 默认注入 Agent runtime, 严格限制当前 phase registry。

**Files / verified lines**:

- 新建 `packages/graph-agent/src/graph_agent/tools/builtin/read_reference.py`
- 新建 `packages/graph-agent/src/graph_agent/tools/builtin/read_example.py`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:424`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:434`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:457`
- `packages/graph-agent/src/graph_agent/tools/builtin/__init__.py`
- `docs/engine/mvp0/skill-spec/09-builtin-modules-spec.md:75`
- `docs/engine/mvp0/skill-spec/11-error-code-spec.md:133`
- `docs/engine/mvp0/skill-spec/11-error-code-spec.md:139`

**WHAT**:

- 新增 `read_reference(reference_id, query="", mode="excerpt")` builtin tool。
- 新增 `read_example(example_id, query="")` builtin tool。
- Agent runtime 默认注入两个 tools, 即使 frontmatter `tools:` 未显式列出。
- tools 只能访问当前 Agent phase `references` / `examples` registry。
- 未声明 id 不做 file I/O, 直接返回/抛稳定 runtime code:
  - `read_reference` miss -> `[F-v3-resource-reference-not-found]`
  - `read_example` miss -> `[F-v3-resource-example-not-found]`
- 参数非法使用 `[F-v3-tool-argument-invalid]`。
- 跨 skill/path 逃逸不读文件; path 不可读使用对应 resource path invalid。
- 删除或最小化 `graph_assembler._agent_resource_tools()` 内联业务逻辑, 只保留绑定/闭包 registry 所需 glue。

**依赖**: c15.4。

**测试影响**:

- 新增 `packages/graph-agent/tests/tools/test_builtin_resource_tools.py`。
- 更新 `tests/core/test_v030_agent_compilation.py`, `tests/core/test_gamma2_reference_reader_sandbox.py` 中工具名/绑定断言。
- 迁移当前错误码断言: 不再用 `[F-v3-resource-reference-id-invalid]` 或 `[F-v3-resource-example-invalid]` 表示 runtime id miss。

**风险点**:

- `[F-v3-mention-target-not-found]` 是编译期 mention 静态校验码, 不得用于 runtime tool id miss。
- 即使 registry 为空, prompt 提到 builtin tools 时行为要一致; 空 registry 调用应返回 not-found, 不应导致工具缺失。

**错误码**:

- `[F-v3-resource-reference-not-found]`
- `[F-v3-resource-example-not-found]`
- `[F-v3-tool-argument-invalid]`
- `[F-v3-resource-reference-path-invalid]`
- `[F-v3-resource-example-path-invalid]`

## §7 c15.6: ! C7 ActionRegistry 一级寻址校验 + LOGIC output fatal (Commit 2)

**目标**: Action runtime 只能按一级 action name 寻址, 禁止路径/模块逃逸; action 返回未声明字段必须 fatal, 不截断。

**Files / verified lines**:

- `packages/graph-agent/src/graph_agent/core/actions.py:23`
- `packages/graph-agent/src/graph_agent/core/actions.py:31`
- `packages/graph-agent/src/graph_agent/core/loader.py:303`
- `packages/graph-agent/src/graph_agent/core/loader.py:359`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:203`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:751`
- `docs/engine/mvp0/skill-spec/03-logic-md-spec.md:80`
- `docs/engine/mvp0/skill-spec/11-error-code-spec.md:76`

**WHAT**:

- `ActionRegistry.resolve(phase_id, name)` 增加一级 name 校验:
  - 禁止 `/`
  - 禁止 `\`
  - 禁止 `.`
  - 禁止 `..`
  - 禁止绝对路径
  - 禁止 module path
  - 只允许合法 action key。
- loader/registry 只接受 `phases/<phase_id>/actions/<name>.py` 或 Engine/Studio common action registry。
- action 返回非 dict 使用 `[F-v3-logic-action-return-invalid]`。
- action 返回 dict 含未声明 `io.outputs` 字段时抛 `[F-v3-logic-output-field-undeclared]`, 不截断、不回写。
- action 通过 `ctx.data` 就地突变产生的 `_dict_delta(before | updates, data)` 更新也必须过 declared-key 校验; 未声明字段抛 `[F-v3-logic-output-field-undeclared]`, 不得绕过 `_validate_logic_update_keys()` 后回写。
- 替换旧 `[F-v3-actions-keys]` active runtime 断言。

**依赖**: c15.1, c15.5 可并行但同 Commit 2 合并。

**测试影响**:

- 新增 `tests/core/test_action_registry_v030.py`。
- 更新 `tests/core/test_v21_actions_keys.py`: `[F-v3-actions-keys]` -> `[F-v3-logic-output-field-undeclared]`。
- 补红灯覆盖 `ctx.data` 就地突变未声明字段, 防止 `_dict_delta` delta 路径绕过 LOGIC output declared-key 校验。
- 更新 `tests/core/test_v21_actions_loader.py` / `tests/core/validators/test_tool_paths_escape.py` 里旧 action path/name 断言。

**风险点**:

- 截断多余字段会隐藏 action bug; 必须 fatal。
- compile-time static return key check 和 runtime dynamic key check 都要对齐同一错误码。

**错误码**:

- `[F-v3-logic-action-name-invalid]`
- `[F-v3-logic-action-not-found]`
- `[F-v3-logic-action-entrypoint-missing]`
- `[F-v3-logic-action-return-invalid]`
- `[F-v3-logic-output-field-undeclared]`

## §8 c15.7: ! C6 + D4 subagent/SUBGRAPH resolver runtime + child flow deepcopy (Commit 3)

**目标**: subagent/SUBGRAPH runtime 只走 `target_skill` + `SkillResolverProtocol`, child graph 使用隔离 data/messages 和深拷贝 flow。

**Files / verified lines**:

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:218`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:237`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:588`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:617`
- `packages/graph-agent/src/graph_agent/core/loader.py:419`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:44`
- `.kiro/specs/engine-mvp0-rebuild-v030/tasks.md:421`

**WHAT**:

- SUBGRAPH node runtime 用 `target_skill` resolver metadata, 不暴露 `child_graph_path` public tool arg。
- subagent dynamic tool 内部只使用 `target_skill` / resolver resolved root, 不接受用户 path。
- child initial state:
  - `data.inputs` = explicit parent phase input / validated tool input。
  - `data.phase_outputs` = `{}`。
  - `data.scratch` = `{}`。
  - `messages` = `[]`。
  - `flow` = parent flow deep copy + `subagent_depth + 1`。
- 修 `graph_assembler.py:617-623` 直接传 `parent_state.get("flow", {})` 的 parent flow alias。
- SUBGRAPH parent output 回写只通过 declared output mapping; duplicate child output key fatal `[F-v3-runtime-state-mapping-failed]`。

**依赖**: c15.1, c15.4, c15.5。

**测试影响**:

- 更新 `tests/integration/test_v21_subagent_executor.py`。
- 更新 `tests/core/test_gamma2_child_graph_isolation.py`。
- 新增/更新 `tests/e2e/test_execution_runtime_v030.py` SUBGRAPH target_skill case。
- path-based subagent fixture 迁移为 resolver fixture。

**风险点**:

- child flow shallow copy 会污染 parent retry/depth state。
- resolver compile cache 若不纳入 registry 身份, child registry 不同但 root 相同会污染。

**错误码**:

- `[F-v3-resolver-missing]`
- `[F-v3-resolver-skill-id-invalid]`
- `[F-v3-skill-not-registered]`
- `[F-v3-resolver-path-invalid]`
- `[F-v3-runtime-state-mapping-failed]`

## §9 c15.8: Test / fixture migration sweep (Commit 3)

**目标**: 同步迁移旧测试和 fixture, 防止 C3 强制 DI、C1/C2 prompt cutover、C7 错误码切换造成全量假红。

**Files / verified lines**:

- `packages/graph-agent/tests/runtime/test_exit_contract.py:7`
- `packages/graph-agent/tests/cognitive/test_prompt.py:75`
- `packages/graph-agent/tests/core/test_loader_xml_rendering.py`
- `packages/graph-agent/tests/core/test_manifest_phase_builders.py`
- `packages/graph-agent/tests/core/test_v21_actions_keys.py:69`
- `packages/graph-agent/tests/core/test_delta_skill_resolution_red.py:98`
- `packages/graph-agent/tests/core/test_skill_resolver_protocol.py:108`
- all tests matched by `rg -n "compile_skill\\(|assemble_graph\\(|run_skill\\(" packages/graph-agent/tests -g '*.py'`

**WHAT**:

- 建立统一 resolver fixture/helper, 供旧 `compile_skill()` / `assemble_graph()` / `run_skill()` tests 显式传 `skill_resolver`。
- 迁移旧 `compile_skill(..., cache=True)` tests, 确认 cache namespace bump 后 resolver registry 不污染。
- 删除或改写 `test_exit_contract.py`。
- `test_prompt.py` 升级为 §5 substring。
- `<steps>` 旧结构断言迁移: 不再期待独立 `<steps>` slot。
- `test_v21_actions_keys.py` 错误码迁移到 `[F-v3-logic-output-field-undeclared]`。
- path-based subagent/SUBGRAPH fixtures 迁移为 `target_skill` + resolver registry。

**依赖**: c15.2-c15.7。

**测试影响**:

- 大量旧 V2.1 命名测试可保留文件名, 但 active assertion 必须 V0.3.0 contract。
- 不允许通过 broad skip 跳过旧 suite。

**风险点**:

- resolver fixture 大迁移是本 PR 最大碰撞面。
- 缓存 key 若只看 root, 同 root 不同 registry 会复用旧 compiled child metadata。

**错误码**:

- follow touched suites; no new code-specific error code。

## §10 c15.9: C8 execution-runtime integration / e2e closure (Commit 3)

**目标**: 用最小真实路径证明 C1-C7+D4 在 execution-runtime 中闭环。

**Files**:

- `packages/graph-agent/tests/integration/`
- `packages/graph-agent/tests/e2e/test_execution_runtime_v030.py`
- e2e fixtures under `packages/graph-agent/tests/fixtures/` as needed

**WHAT**:

- minimal Agent run:
  - system prompt 含 §5 8 slots。
  - `<knowledge_base>` 非空。
  - `<exit_contract>` 末尾含 output_schema。
- reference reader fallback:
  - mock timeout / exception / invalid output。
  - `[F-v3-reference-reader-failed]` warning markdown 进入 prompt。
- builtin tools:
  - `read_example` 合法调用。
  - id miss 使用 runtime not-found 码。
- SUBGRAPH:
  - `target_skill` resolver 全链路。
  - child data/messages 不泄漏。
  - child flow deep copy + depth。

**依赖**: c15.8。

**测试影响**:

- 新增 V0.3.0 e2e fixtures。
- 旧 `*_v21` e2e 若仍 active, 迁移断言到 V0.3.0 或隔离到 non-active legacy corpus。

**风险点**:

- e2e 不应依赖真实 LLM; 用 fake chat model / fake reader。
- 避免 snapshot 全文, 断言关键行为。

**错误码**:

- `[F-v3-reference-reader-failed]`
- `[F-v3-resource-reference-not-found]`
- `[F-v3-resource-example-not-found]`
- `[F-v3-runtime-state-mapping-failed]`
- resolver domain codes as applicable。

## §11 c15.10: CI Gate Checklist + High-risk Scans

**目标**: 最终 PR gate, 确认 hard cutover 没有半旧半新路径。

**Required tests**:

- `pytest packages/graph-agent/tests/cognitive/test_v030_cognitive_template_slots.py -v`
- `pytest packages/graph-agent/tests/tools/test_builtin_resource_tools.py -v`
- `pytest packages/graph-agent/tests/core/test_action_registry_v030.py -v`
- `pytest packages/graph-agent/tests/core/test_reference_reader_assembly_fallback.py -v`
- `pytest packages/graph-agent/tests/e2e/test_execution_runtime_v030.py -v`
- `pytest packages/graph-agent/tests/runtime/test_state_mapper.py -v`
- `pytest packages/graph-agent/tests/core/test_delta_skill_resolution_red.py -v`
- full graph-agent unit/integration/e2e suite used by repo CI

**Required scans**:

- `rg -n "inject_exit_contract|runtime/exit_contract|from graph_agent.runtime.exit_contract" packages/graph-agent/src packages/graph-agent/tests`
- `rg -n "<steps>|</steps>|<document_examples>|</document_examples>" packages/graph-agent/src/graph_agent/cognitive packages/graph-agent/tests`
- `rg -n "F-v3-actions-keys|resource-reference-id-invalid|resource-example-invalid|mention-target-not-found" packages/graph-agent/src/graph_agent packages/graph-agent/tests`
- `rg -n "read_reference.py|read_example.py" packages/graph-agent/src/graph_agent/tools/builtin`
- `rg -n "parent_state.get\\(\"flow\", \\{\\}\\)|child_graph_path|sub_skill_ref|_resolve_subagent_root" packages/graph-agent/src/graph_agent packages/graph-agent/tests`
- `rg -n "compile_skill\\(|assemble_graph\\(|run_skill\\(" packages/graph-agent/tests -g '*.py'` followed by fixture audit for explicit `skill_resolver`

**High-risk collision checklist**:

- Prompt snapshot: assert key substrings/ordering only, not full prompt MD5.
- Cache namespace bump: resolver/registry identity participates in cache key or namespace.
- Resolver fixture migration: all active tests pass explicit resolver or no-op resolver.
- C4 trigger point: reader runs in `_build_skill_node()` once, never per `_skill_node()` loop.
- C5 error codes: runtime id miss uses `[F-v3-resource-reference-not-found]` / `[F-v3-resource-example-not-found]`.
- C7 output policy: undeclared LOGIC output field fatal `[F-v3-logic-output-field-undeclared]`, no truncation.
- D4 flow: child flow deep copy, child messages empty, child data isolated.

**依赖**: c15.9。

**验收**:

- CI green。
- scans have no active unexpected hits。
- PR report records changed tests, fixture migration, and merge target `stage/engine-v030`.
