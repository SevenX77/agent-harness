---
ws_id: WS-E7-golden-resume
artifact: gemini-prompt
status: ready-for-gemini
created: 2026-06-10
task_file: .kiro/specs/engine-mvp1/task-ws-e7-golden-resume.md
requirements: .kiro/specs/engine-mvp1/requirements-ws-e7-golden-resume.md
contract_gate: "passed by Codex PM on 2026-06-10; approved RED result is 12 failed on missing public Engine APIs"
---

# Gemini Prompt - WS-E7 Golden / Resume

```text
你是 /Users/sevenx/Documents/coding/agent-harness/.worktrees/engine-mvp1-ws-e7-golden-resume 工作区的 engine 模块实现者。请按 TDD 执行 WS-E7 golden/resume：RED 测试已由 Codex 写好，并已通过 PM 契约门审查。你的任务是只做最小 GREEN 实现，不扩范围。

工作区：
/Users/sevenx/Documents/coding/agent-harness/.worktrees/engine-mvp1-ws-e7-golden-resume

当前分支 / 基线：
codex/engine-mvp1-ws-e7-golden-resume
HEAD: 2f7128c30e1901fe42a26a6782d225af6e8ecdb4

任务书：
.kiro/specs/engine-mvp1/task-ws-e7-golden-resume.md

需求书：
.kiro/specs/engine-mvp1/requirements-ws-e7-golden-resume.md

铁律：
1. 已批准 RED 测试是实现契约；不要削弱测试来变绿。
2. 使用 superpowers:test-driven-development。先跑 RED，看到同样形状失败，再写最小 GREEN。
3. 不改 apps/studio/**，不改 packages/graph-agent-gateway/**。
4. 不把 golden 写进 skill 源码树，不创建 workspace_dir/predict/latest_predict.json。
5. 不把 stale 重新做成 compile-time fatal。
6. 不做 Error Contract V2 P0-3/P1/P2，不做复杂 HITL UI，不做 messages compaction/checkpoint data delta。
7. 如果必须触碰 forbidden files，立即停下报告需要 PM 扩 scope；不要先改了再解释。

必须先读并回述关键现状：
- .kiro/specs/engine-mvp1/requirements-ws-e7-golden-resume.md
  重点：RED 锁定的 API 签名、resume 复用 run_id 政策、Golden report 形状、禁止范围。
- .kiro/specs/engine-mvp1/task-ws-e7-golden-resume.md
  重点：Phase 0 到 Phase 6、Hard Exit Checklist。
- docs/engine/mvp1/03-api-contract/mvp1-alignment.md
  重点：run/predict/compile public API、Golden API 面、Resume API 面。
- docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md
  重点：唯一 base + checkpoint_ns、resume 通过 get_state_history/update_state/重新 invoke。
- docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md
  重点：WS-E5 已有外层/AGENT/iterate namespace，但完整 resume 产品未实现。
- docs/engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment.md
  重点：golden 在 .workspace/golden、逐节点 diff、stale 在 eval 期。
- docs/engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/baseline.md
  重点：engine 当前不读 .workspace/golden，没有 evaluate_golden_baseline；studio 有整 final_state diff 算法可参考但不能被 Engine import。
- docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md
  重点：workspace_dir 必填绝对路径、runs/golden/test_inputs 固定户型、predict/latest_predict 已废。
- packages/graph-agent/src/graph_agent/__init__.py
  重点：当前 public exports 缺 resume_skill / evaluate_golden_baseline。
- packages/graph-agent/src/graph_agent/core/runner.py
  重点：_validate_workspace_dir、run_skill/predict_skill、_write_workflow_result_artifacts、V0.3 graph invoke/checkpointer wiring。
- packages/graph-agent/src/graph_agent/core/checkpointer.py
  重点：resolve_checkpointer/get_checkpointer/reset_checkpointer；可放 checkpoint selector helper。
- packages/graph-agent/src/graph_agent/core/result.py
  重点：RunResult/WorkflowMetrics，可选 typed report model 落点。
- packages/graph-agent/src/graph_agent/core/_predict_internal/**
  重点：可放 golden eval helper，避免继续堆大 runner.py。

已批准 RED 测试：
- packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py
- packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py
- packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py

先运行 RED：
uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py -q

当前预期 RED：
12 failed

失败形状必须保持干净：
- resume 测试失败为：graph_agent.resume_skill must be a public callable。
- golden 测试失败为：graph_agent.evaluate_golden_baseline must be a public callable。
- 没有语法、夹具、compile、purity、环境错误。
- Codex 已临时自检 resume fixture：现有 run_skill 能跑完 deterministic skill，并能找到 draft-before-final checkpoint。

允许修改：
- packages/graph-agent/src/graph_agent/core/runner.py
- packages/graph-agent/src/graph_agent/core/checkpointer.py
- packages/graph-agent/src/graph_agent/core/result.py
- packages/graph-agent/src/graph_agent/core/_predict_internal/**
- packages/graph-agent/src/graph_agent/__init__.py
- packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py 只允许修夹具错误，不允许削弱契约
- packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py 只允许修夹具错误，不允许削弱契约
- packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py 只允许修夹具错误，不允许削弱契约
- .kiro/specs/engine-mvp1/requirements-ws-e7-golden-resume.md
- .kiro/specs/engine-mvp1/task-ws-e7-golden-resume.md
- .kiro/specs/engine-mvp1/gemini-prompt-ws-e7-golden-resume.md

禁止修改：
- apps/studio/**
- packages/graph-agent-gateway/**
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- packages/graph-agent/src/graph_agent/core/loader.py
- packages/graph-agent/src/graph_agent/io/**
- packages/graph-agent/src/graph_agent/tools/builtin/read_file.py
- packages/graph-agent/src/graph_agent/callbacks/events.py
- packages/graph-agent/src/graph_agent/callbacks/emit.py
- packages/graph-agent/src/graph_agent/middleware/**

目标行为：
1. 新增 public Engine API：graph_agent.resume_skill(...) -> RunResult。
2. 新增 public Engine API：graph_agent.evaluate_golden_baseline(...) -> dict/report。
3. 两个 API 都强制 workspace_dir 为绝对路径，并且只在 workspace_dir 下读写 artifacts。
4. resume 支持 checkpoint_id 精确选择，支持 checkpoint_ns + latest 选择。
5. resume 使用原 run_id 作为 LangGraph thread_id 和 workspace_dir/runs/<run_id> 追踪键；RunResult.run_id == run_id。
6. resume 通过 LangGraph checkpoint/history/update-state/re-invoke 语义续跑，不允许从头重跑假装 resume。
7. context_overrides 只更新 business blackboard，不写 runtime/callback/compiled graph/config 等不可持久化对象。
8. HITL human_response 接受结构化 {content: str, tool_call_id?: str}，拒绝纯 string 和缺 content 的 dict。
9. evaluate_golden_baseline 读取 workspace_dir/golden/<baseline_id>/baseline.json 与 cases/*.json。
10. case 绑定键是 phase_id；不得用 Studio run id、canvas node DTO、skill 源码 golden.json。
11. deterministic LOGIC case exact match -> passed。
12. expected_output 值不等 -> failed + 字段级 diff。
13. 当前 phase io.outputs.required 新增字段而 expected_output 缺失 -> stale；compile_skill 不 fatal。
14. report 写 workspace_dir/golden/<baseline_id>/report.json，返回值与文件同形。
15. 不创建 workspace_dir/predict/latest_predict.json，不在 skill tree 写 golden.json。

实现提示，不是额外需求：
- 可以在 runner.py 暴露入口，内部委派到 checkpointer.py / _predict_internal helper，避免 runner.py 继续膨胀。
- golden field diff 不要 import Studio app 代码；可以复制最小必要算法或写 Engine-local helper。
- RunResult 已有 _write_workflow_result_artifacts 可复用。
- 若 public API contract snapshot 测试因新增 exports 失败，先报告需要更新的 public API contract 指纹/快照，不要绕过 guard。

执行顺序：
1. 读任务书、需求书、SSOT、源码，回述关键现状和最小落点判断。
2. 运行 approved RED 命令，确认仍是 12 failed 且失败形状如上。
3. 确认生产 scope 无初始 WS-E7 diff：
   git diff -- packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/src/graph_agent/core/_predict_internal packages/graph-agent/src/graph_agent/__init__.py apps/studio packages/graph-agent-gateway
4. 按 task Phase 1 加 public API surface，跑：
   uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py::test_resume_skill_public_api_signature_is_locked packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_evaluate_golden_baseline_public_api_signature_is_locked -q
5. 实现 workspace_dir validation，跑：
   uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py::test_resume_rejects_relative_workspace_dir packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_evaluate_golden_rejects_relative_workspace_dir -q
6. 实现 golden eval，分步跑：
   uv run pytest packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_deterministic_logic_case_exact_match_writes_passed_report -q
   uv run pytest packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_golden_value_mismatch_returns_failed_case_with_field_diff -q
   uv run pytest packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_required_output_missing_from_expected_marks_case_stale_not_compile_fatal -q
   uv run pytest packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py::test_golden_eval_uses_workspace_golden_not_skill_source_or_predict_latest -q
7. 实现 resume，分步跑：
   uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py::test_resume_from_checkpoint_applies_business_context_overrides_without_rerunning_upstream -q
   uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py::test_resume_selector_preserves_checkpoint_namespace_boundaries -q
   uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py::test_resume_human_response_is_structured_and_plain_string_is_rejected -q
8. 跑 e2e：
   uv run pytest packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py -q
9. 跑完整 WS-E7：
   uv run pytest packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py -q
10. 跑 required regressions：
   uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py -q
   uv run pytest packages/graph-agent/tests/core/test_workspace_dir_contract_red.py apps/studio/backend/tests/test_workspace_dir_contract_red.py -q
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py packages/graph-agent/tests/core/test_ws_e1_io_runtime_red.py packages/graph-agent/tests/e2e/test_ws_e1_io_runtime.py packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py packages/graph-agent/tests/e2e/test_ws_e4_runtime_trace_events.py -q
   uv run pytest packages/graph-agent/tests/test_public_api_contract.py -q
11. 跑 scope / hygiene：
   git diff -- apps/studio packages/graph-agent-gateway packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/src/graph_agent/io packages/graph-agent/src/graph_agent/tools/builtin/read_file.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/middleware
   git status --short -- uv.lock
   git diff --check -- .kiro/specs/engine-mvp1/requirements-ws-e7-golden-resume.md .kiro/specs/engine-mvp1/task-ws-e7-golden-resume.md .kiro/specs/engine-mvp1/gemini-prompt-ws-e7-golden-resume.md packages/graph-agent/tests/core/test_ws_e7_resume_contract_red.py packages/graph-agent/tests/core/test_ws_e7_golden_eval_red.py packages/graph-agent/tests/e2e/test_ws_e7_golden_resume.py packages/graph-agent/src/graph_agent/core/runner.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/src/graph_agent/core/_predict_internal packages/graph-agent/src/graph_agent/__init__.py

uv.lock 注意：
- 本 WS 没有依赖变更；如果 uv.lock 被 uv run 摸脏，恢复它。

不要更新 baseline，除非用户/PM 明确要求。GREEN 后只报告真实落地行为，交给 Codex/PM 回写：
- docs/engine/mvp1/_impl/IMPL_PLAN.md
- docs/engine/mvp1/03-api-contract/baseline.md
- docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md
- docs/engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/baseline.md
- docs/engine/mvp1/01-contract/01-physical-layout/baseline.md

回报格式：
1. 修改了哪些文件。
2. 每条验证命令的结果摘要。
3. 是否完全留在 owns_files；如果没有，给出 PM 扩 scope 的明确记录。
4. Resume 行为：selector、checkpoint/thread 语义、context_overrides、HITL validation、artifact policy。
5. Golden eval 行为：workspace layout、case schema、diff format、stale handling、report path。
6. 明确说明 forbidden files、apps/studio/**、packages/graph-agent-gateway/**、uv.lock 是否无未经授权 diff。
7. baseline 是否留给 Codex/PM 回写。
8. 若 hard-exit 未满足，说明原因并停下，不要扩大范围。
```
