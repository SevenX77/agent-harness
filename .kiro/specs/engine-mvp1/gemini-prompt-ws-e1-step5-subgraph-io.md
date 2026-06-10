---
ws_id: WS-E1-step5-subgraph-io
artifact: gemini-prompt
status: ready-for-gemini
created: 2026-06-09
task_file: .kiro/specs/engine-mvp1/task-ws-e1-step5-subgraph-io.md
requirements: .kiro/specs/engine-mvp1/requirements-ws-e1-step5-subgraph-io.md
---

# Gemini Prompt - WS-E1 Step5 Subgraph IO Relaxation

```text
你是 /Users/sevenx/.config/superpowers/worktrees/agent-harness/codex-engine-mvp1-e1-iterate-task 工作区的 engine 模块实现者。请按 TDD 执行 WS-E1 Step5 subgraph IO relaxation：RED 测试已由 Codex 写好，并已通过 PM/Claude 契约门审查。你的任务是只做最小 GREEN 实现，不扩范围。

工作区：
/Users/sevenx/.config/superpowers/worktrees/agent-harness/codex-engine-mvp1-e1-iterate-task

当前分支 / 基线：
codex/engine-mvp1-e1-iterate-task
HEAD: d38f57eb feat(engine): add iterate runtime contracts

注意：当前 worktree 里已有未提交的 Step5 requirements、RED 测试、旧测试口径转换和 traceability metadata 改动。这些是已通过契约门的输入，不是实现结果。

任务书：
.kiro/specs/engine-mvp1/task-ws-e1-step5-subgraph-io.md

需求书：
.kiro/specs/engine-mvp1/requirements-ws-e1-step5-subgraph-io.md

铁律：
1. MVP1 design/alignment 是绝对真理。
2. 旧 live code 或旧测试如果还断言 MVP0 子图 inputs 1:1 行为，视为 drift；冲突测试必须删除或改成 MVP1 RED/GREEN，不得保留原断言。
3. 已批准 RED 测试是实现契约；不要削弱测试来变绿。
4. 只做 Step5：子图 inputs 放宽，outputs 仍严校。

必须先读并回述关键现状：
- .kiro/specs/engine-mvp1/requirements-ws-e1-step5-subgraph-io.md
  重点：目标行为、owns_files、forbidden files、MVP1 SSOT、旧 MVP0 测试 drift 规则。
- .kiro/specs/engine-mvp1/task-ws-e1-step5-subgraph-io.md
  重点：Phase 0 到 Phase 5、Hard Exit Checklist、验证命令。
- docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md
  重点：E1 子图 io 放宽，只放 inputs，outputs 保留。
- docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md
  重点：SUBGRAPH io.inputs 从父图 blackboard 切片，父子字段不再 1:1。
- docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md
  重点：subgraph domain 错误码。
- packages/graph-agent/src/graph_agent/core/loader.py
  重点：_validate_subgraph_io_contracts。当前它同时比较 inputs 和 outputs，这是 RED 的失败点。
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
  只读 grounding：_wrap_phase_runtime_node、_build_subgraph_node。不要改，除非测试证明 loader-only 无法满足 runtime contract，并先停下回报。
- packages/graph-agent/src/graph_agent/runtime/state_mapper.py
  只读 grounding：StateMapper.build_phase_input / wrap_phase_output。不要改，除非测试证明 loader-only 无法满足 runtime contract，并先停下回报。

已批准 RED / drift 测试：
- packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py
- packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_allowed_at_compile_time
- packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_output_mismatch_is_rejected_at_compile_time
- packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py::test_corrupted_skill_raises_dedicated_located_code[subgraph-io-mismatch]

先运行 RED：
uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q

当前预期 RED：
3 failed, 1 passed

失败形状必须保持干净：
- parent input superset 当前失败在 loader._validate_subgraph_io_contracts，信息是 inputs do not match。
- different input sets 当前失败在 loader._validate_subgraph_io_contracts，信息是 inputs do not match。
- runtime relaxed-input case 当前也先失败在 compile 阶段的 inputs mirror 校验。
- output mismatch 用例已经通过，证明 outputs strict 没有丢。

再运行旧测试口径转换验证：
uv run pytest packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_allowed_at_compile_time packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_output_mismatch_is_rejected_at_compile_time -q

当前预期：
1 failed, 1 passed

允许修改：
- packages/graph-agent/src/graph_agent/core/loader.py

已经由 Codex 改好的契约/测试/metadata 输入可保留；除非发现夹具错误，否则不要改弱：
- .kiro/specs/engine-mvp1/requirements-ws-e1-step5-subgraph-io.md
- .kiro/specs/engine-mvp1/task-ws-e1-step5-subgraph-io.md
- .kiro/specs/engine-mvp1/gemini-prompt-ws-e1-step5-subgraph-io.md
- packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py
- packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py
- packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py
- packages/graph-agent/spec/features.yaml
- packages/graph-agent/tests/fixtures/round28/valid_features_primary_owners.yaml
- packages/graph-agent/tests/fixtures/round28/valid_features_runtime_compat.yaml

禁止修改：
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- packages/graph-agent/src/graph_agent/runtime/state_mapper.py
- packages/graph-agent/src/graph_agent/core/runner.py
- packages/graph-agent/src/graph_agent/io/**
- packages/graph-agent/src/graph_agent/tools/builtin/read_file.py
- packages/graph-agent/src/graph_agent/callbacks/events.py
- packages/graph-agent/src/graph_agent/callbacks/emit.py
- packages/graph-agent/src/graph_agent/middleware/**
- packages/graph-agent/src/graph_agent/core/checkpointer.py
- packages/graph-agent/src/graph_agent/core/state.py
- apps/studio/**
- packages/graph-agent-gateway/**

目标行为：
1. 父 SUBGRAPH.md io.inputs 与子 GRAPH.md io.inputs 不一致时，compile 不得仅因 inputs mismatch 报 [F-v3-subgraph-io-mismatch]。
2. 父 SUBGRAPH.md io.inputs 是子 GRAPH.md io.inputs 超集时，compile 放行。
3. 父 SUBGRAPH.md io.inputs 与子 GRAPH.md io.inputs 是不同集合时，compile 放行。
4. runtime 中，父 blackboard 有子图需要字段时，子图能跑通；子图 action 只能看见 child GRAPH.md 自己声明的 io.inputs 切片。
5. 父 SUBGRAPH.md io.outputs 与子 GRAPH.md io.outputs 不一致时，仍 compile-time fatal。
6. outputs mismatch 仍使用 [F-v3-subgraph-io-mismatch]，错误信息应能看出是 outputs mismatch。
7. 不引入 alias/mapping 语法，不做文件 lazy import，不做 artifact/business_data_md，不做 InputFileInjectedEvent，不做 runner/io/read_file/storage/callback/middleware/checkpoint/state 改动。

实现建议边界：
- 最小实现应集中在 loader._validate_subgraph_io_contracts。
- 保留 child compile / resolver / recursion cache 行为。
- 不要跳过 child load；只改变 inputs mirror 校验。
- 如果 runtime slicing 测试在 loader 放宽后仍失败，先停下汇报，不要直接改 graph_assembler.py 或 state_mapper.py。

执行顺序：
1. 先运行 RED 命令，确认仍是 3 failed, 1 passed 且失败形状如上。
2. 运行 round14 核心转换命令，确认 inputs allowed 红、outputs strict 绿。
3. 最小修改 loader.py，让 input mismatch compile 放行。
4. 跑 targeted GREEN：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py::test_subgraph_input_mismatch_compiles_without_mirror_contract packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_allowed_at_compile_time -q
5. 确认 outputs strict：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py::test_subgraph_output_mismatch_still_fatals_with_existing_code packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_output_mismatch_is_rejected_at_compile_time 'packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py::test_corrupted_skill_raises_dedicated_located_code[subgraph-io-mismatch]' -q
6. 确认 runtime slicing：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py::test_subgraph_runtime_slices_parent_blackboard_with_relaxed_inputs -q
7. 跑完整 Step5 验证：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_allowed_at_compile_time packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_output_mismatch_is_rejected_at_compile_time 'packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py::test_corrupted_skill_raises_dedicated_located_code[subgraph-io-mismatch]' -q
8. 跑 traceability：
   uv run pytest --collect-only packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_allowed_at_compile_time -q
   rg "test_subgraph_io_input_mismatch_is_rejected_at_compile_time" packages/graph-agent/spec/features.yaml packages/graph-agent/tests -g "*.py" -g "*.yaml"
   第二条预期无输出、exit code 1；旧名字只允许留在 requirements 说明或 MVP0 历史文档，不要为本 WS 修改 MVP0 文档。
9. 跑 round28 manifest：
   uv run pytest packages/graph-agent/tests/test_round28_contract_manifests.py -q
10. 跑 Step3/Step4 回归：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_context_facade_logic_action.py packages/graph-agent/tests/core/test_action_registry_v030.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q
11. 跑 create-agent / purity / diagnostics baseline：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_purity_le2.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q
12. 跑 mypy：
   uv run mypy packages/graph-agent/src/graph_agent/core/loader.py
13. 跑 scope / hygiene：
   git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/runtime/state_mapper.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/io packages/graph-agent/src/graph_agent/tools/builtin/read_file.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/middleware packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py
   git status --short -- apps/studio packages/graph-agent-gateway uv.lock
   git diff --check -- packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py packages/graph-agent/spec/features.yaml packages/graph-agent/tests/fixtures/round28/valid_features_primary_owners.yaml packages/graph-agent/tests/fixtures/round28/valid_features_runtime_compat.yaml .kiro/specs/engine-mvp1/requirements-ws-e1-step5-subgraph-io.md .kiro/specs/engine-mvp1/task-ws-e1-step5-subgraph-io.md .kiro/specs/engine-mvp1/gemini-prompt-ws-e1-step5-subgraph-io.md

uv.lock 注意：
- uv run 可能摸脏 uv.lock。
- 本 WS 没有依赖变更；如果 uv.lock 被摸脏，执行 git restore -- uv.lock。

不要更新 baseline，除非用户/PM 明确要求。GREEN 后只报告真实落地行为，交给 Codex/PM 回写：
- docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md
- docs/engine/mvp1/01-contract/02-skill-syntax/baseline.md
- docs/engine/mvp1/01-contract/03-compile-rules/baseline.md 如错误码语义/文案真的变化才改。

回报格式：
1. 修改了哪些文件。
2. 每条验证命令的结果摘要。
3. 明确说明 forbidden engine files、apps/studio/**、packages/graph-agent-gateway/**、uv.lock 是否无 WS-E1 Step5 diff。
4. 说明最终 subgraph IO 行为：inputs compile 行为、runtime slicing 行为、outputs mismatch 行为。
5. baseline 是否留给 Codex/PM 回写。
6. 若有任何 hard-exit 项无法满足，说明原因并停下，不要扩大范围。
```
