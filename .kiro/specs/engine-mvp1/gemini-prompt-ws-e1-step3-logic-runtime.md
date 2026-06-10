---
ws_id: WS-E1-step3-logic-runtime
artifact: gemini-prompt
status: ready-for-gemini
created: 2026-06-08
task_file: .kiro/specs/engine-mvp1/task-ws-e1-step3-logic-runtime.md
requirements: .kiro/specs/engine-mvp1/requirements-ws-e1-step3-logic-runtime.md
---

# Gemini Prompt - WS-E1 Step3 LOGIC Runtime Contract

```text
你是 /Users/sevenx/.config/superpowers/worktrees/agent-harness/codex-engine-mvp1-e1-logic-task 工作区的 engine 模块实现者。请按 TDD 执行 WS-E1 Step3 LOGIC runtime contract：RED 测试已由 Codex 写好，并已通过 PM/Claude 契约门审查。你的任务是只做最小 GREEN 实现，不扩范围。

工作区：
/Users/sevenx/.config/superpowers/worktrees/agent-harness/codex-engine-mvp1-e1-logic-task

当前分支 / 基线：
codex/engine-mvp1-e1-logic-task
HEAD: c9e363eb

任务书：
.kiro/specs/engine-mvp1/task-ws-e1-step3-logic-runtime.md

需求书：
.kiro/specs/engine-mvp1/requirements-ws-e1-step3-logic-runtime.md

必须先读并回述关键现状：
- .kiro/specs/engine-mvp1/requirements-ws-e1-step3-logic-runtime.md
  重点：MVP1 design / alignment 是绝对真理；旧 live code 和旧测试冲突视为 drift。
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
  重点：_build_logic_node、_validate_logic_update_keys、_dict_delta、phase_inputs_from_state。
- packages/graph-agent/src/graph_agent/core/loader.py
  只读：_validate_action_signature 当前要求 action 第一参数名是 context/ctx。不要改 loader.py。
- packages/graph-agent/src/graph_agent/cognitive/context_facade.py
  只读：旧 mutable Context facade。不要改 context_facade.py。
- 已批准 RED 测试：
  - packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py
  - packages/graph-agent/tests/core/test_context_facade_logic_action.py
  - packages/graph-agent/tests/core/test_action_registry_v030.py
  - packages/graph-agent/tests/core/validators/test_purity_le2.py

已批准 RED 命令：
uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_context_facade_logic_action.py packages/graph-agent/tests/core/test_action_registry_v030.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q

当前预期 RED：
8 failed, 23 passed

失败形状必须保持干净：
- action 收到 Context 而不是 dict：Context:hello vs dict:hello。
- 多 action 链中后一个 action 读不到前一个 action 返回的 normalized，得到 missing 而不是 HELLO。
- context.set / context.update / item assignment / setdefault 仍通过 diff 写入 business data。
- 旧 Context facade 测试现在期望 dict:scored 1 segments，但当前得到 Context:scored 1 segments。
- action_registry mutation 回归当前把 foo 从 1 改成 99。

允许修改：
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- 必要时只做不削弱契约的测试维护：
  - packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py
  - packages/graph-agent/tests/core/test_context_facade_logic_action.py
  - packages/graph-agent/tests/core/test_action_registry_v030.py

禁止修改：
- packages/graph-agent/src/graph_agent/core/loader.py
- packages/graph-agent/src/graph_agent/core/manifest.py
- packages/graph-agent/src/graph_agent/core/purity.py
- packages/graph-agent/src/graph_agent/core/error_registry.py
- packages/graph-agent/src/graph_agent/cognitive/context_facade.py
- packages/graph-agent/src/graph_agent/core/checkpointer.py
- packages/graph-agent/src/graph_agent/core/state.py
- packages/graph-agent/src/graph_agent/middleware/tracing.py
- packages/graph-agent/src/graph_agent/middleware/tool_error.py
- packages/graph-agent/src/graph_agent/middleware/loop_detection.py
- packages/graph-agent/src/graph_agent/middleware/nudge_injector.py
- apps/studio/**
- packages/graph-agent-gateway/**

目标行为：
1. LOGIC action 的 runtime 实参是 plain dict，不是 Context facade。
2. 这个 dict 来自当前 phase 的 io.inputs 切片，加上前面 action 显式 return 的 dict 增量。
3. action 链唯一合法写回来源是每个 action 返回的 dict。
4. context.set / context.update / item assignment / setdefault 等 mutation 不再隐式写入 blackboard。实现可以让这些 mutation 只改本地临时 dict，或触发可观测失败；不能偷偷写回 business data。
5. 返回 dict 的 key 仍必须是当前 phase io.outputs.properties 子集；未声明 key 继续报 [F-v3-logic-output-field-undeclared]。
6. 返回非 dict 继续报 [F-v3-logic-action-return-invalid]。
7. WS-E6 purity hard bans 保持 GREEN；本任务不实现 purity。

重要注记：
- RED 中 action 第一参数名仍叫 context，是为了不把 loader.py 拉进本 WS。断言的是 runtime 实参类型和行为必须是 dict。
- 如果你认为必须改 loader.py 才能完成参数名 cleanup，请停下汇报，不要擅自扩 owns。

绝对不做：
- 不实现 iterate。
- 不实现 subgraph io inputs 放宽。
- 不实现文件 lazy 注入、artifact business_data_md 或 InputFileInjectedEvent。
- 不实现 middleware 后三槽。
- 不修改 purity scanner、error registry、loader、manifest、context_facade、state、checkpoint。
- 不修改 Studio 或 gateway。
- 不更新 baseline；GREEN 后只报告真实落地行为，由 Codex/PM 决定 baseline 回写。

执行顺序：
1. 先运行 RED 命令，确认仍是 8 failed, 23 passed 且失败形状如上。
2. 按 task 文件 Phase 1 -> Phase 4 实现，每阶段跑对应命令。
3. 最后跑完整 Step3 验证：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_context_facade_logic_action.py packages/graph-agent/tests/core/test_action_registry_v030.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q
4. 跑 baseline regression：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_purity_le2.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q
5. 跑 mypy：
   uv run mypy packages/graph-agent/src/graph_agent/core/graph_assembler.py
6. 跑 scope / hygiene：
   git diff -- packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/src/graph_agent/core/manifest.py packages/graph-agent/src/graph_agent/core/purity.py packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/cognitive/context_facade.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/middleware/nudge_injector.py
   git status --short -- apps/studio packages/graph-agent-gateway uv.lock
   git diff --check -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_context_facade_logic_action.py packages/graph-agent/tests/core/test_action_registry_v030.py

回报格式：
1. 修改了哪些文件。
2. 每条验证命令的结果摘要。
3. 明确说明 forbidden engine files、apps/studio/**、packages/graph-agent-gateway/**、uv.lock 是否无 WS-E1 Step3 diff。
4. 说明最终 LOGIC runtime 行为：action 实参对象、action-chain 返回值传递、mutation 通道、输出校验。
5. 若有任何 hard-exit 项无法满足，说明原因并停下，不要扩大范围。
```
